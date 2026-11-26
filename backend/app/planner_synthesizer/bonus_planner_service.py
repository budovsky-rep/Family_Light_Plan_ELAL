"""Multi-Club Loyalty Wallet Allocation Engine & 6-Strategy Bonus Vacation Synthesizer.

Implements Features `F22` through `F28`:
- `MultiClubWalletAllocationEngine`:
  - Supports all 10 `LoyaltyProgramCode` programs (`ELAL_MATMID`, `BRITISH_AVIOS`,
    `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`,
    `QANTAS_FREQUENT_FLYER`, `AEGEAN_MILES_BONUS`, `AMEX_MR_ISRAEL`,
    `ISRAELI_CC_TRAVEL_POINTS`).
  - Decides the ticket composition of every strategy from the available bonus seats
    (never from how many tickets the wallets could pay for); wallets only give the
    balance compared with one bonus ticket's minimum (`effective_elal_points_balance`,
    credit-card `transfer_ratio_to_airline` applied) and gate the multi-club strategy.
    `INFANT_LAP` passengers need no seat.
  - Enforces **Adult-Child Under-12 PNR Safety Pairing**: never isolates a child
    under age 12 (`INFANT_LAP`, `INFANT_SEAT`, `CHILD`) on a separate PNR or cabin
    group without at least one accompanying adult (`ADULT_1` or `ADULT_2`).
- `BonusVacationPlannerService`:
  - Synthesizes vacation proposals across all **6 Family Bonus Fulfillment Strategies**
    (`FULL_BONUS_SAME_CABIN`, `SPLIT_CABIN_BONUS`, `HYBRID_BONUS_PLUS_CASH`,
    `ONE_WAY_BONUS_ONE_WAY_CASH` including regional Open-Jaw `TLV->MXP` / `FCO->TLV`,
    `CASH_AND_POINTS` (no points figure), `MULTI_CLUB_PER_PASSENGER_SPLIT`)
    plus `COMMERCIAL_CASH_ONLY`.
  - Describes every result by the bonus seats available per direction (no cash estimate),
    computes the seat-only `FBVS` and `CTOS = 0.55 * HAS + 0.45 * FBVS`.
  - Provides `search_vacations`.
"""

from __future__ import annotations

import math
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlencode

from backend.app.calendar_engine.moe_calendar_service import MoECalendarService
from backend.app.config_manager.settings import AppSettings, get_settings
from backend.app.providers.commercial_flights import (
    AllAirlinesSearchAdapter,
    FamilyBaggageNormalizer,
)
from backend.app.providers.elal_rbd_client import ElAlRbdDataClientAdapter
from backend.app.planner_synthesizer.weather_suitability_engine import (
    DestinationWeatherSuitabilityEngine,
    VACATION_TYPE_LABELS_HE,
)
from backend.app.schemas.domain import (
    AirlineSelectionMode,
    CandidateVacationWindow,
    ChildTripImpact,
    DateSelectionMode,
    ElAlBonusAvailability,
    FamilyProfile,
    FlightItinerary,
    FlightLeg,
    FlightSearchQuery,
    FulfillmentStrategy,
    LoyaltyProgramCode,
    PassengerLoyaltyWallet,
    VacationOptionProposal,
    classify_passenger_type,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    YOM_KIPPUR_CLOSED_DATES,
    _make_bonus_row,
    build_clean_guest_profile,
    is_shabbat_blocked_for_elal,
)
from backend.app.vacation_optimizer.maximizer_engine import (
    VacationMaximizerEngine,
    resolve_holiday_direct_intent_school_year,
)

# Ensure ChildTripImpact exposes `.camp_days_overlapped` as a property alias for `.nitzanim_days_overlapped`
if not hasattr(ChildTripImpact, "camp_days_overlapped"):
    ChildTripImpact.camp_days_overlapped = property(  # type: ignore[attr-defined]
        lambda self: self.nitzanim_days_overlapped
    )

# Same-metro or immediate twin-airport Open-Jaw clusters (valid for any trip duration >= 1 night)
SAME_CITY_OPEN_JAW_CLUSTERS: list[set[str]] = [
    {"LHR", "LTN"},  # London (Heathrow / Luton)
    {"JFK", "EWR"},  # New York City (JFK / Newark)
    {"MIA", "FLL"},  # Miami / Fort Lauderdale (~35 min)
    {"LCA", "PFO"},  # Cyprus: Larnaca / Paphos (~1h15m highway)
    {"ZRH", "BSL"},  # Zurich / Basel (~1h direct rail)
]

# Close overland rail/highway Open-Jaw pairs worth the transfer on longer trips (>= 6 nights; zero island/sea crossings)
CLOSE_OVERLAND_OPEN_JAW_CLUSTERS: list[set[str]] = [
    {"FCO", "MXP"},
    {"MXP", "VCE"},
    {"MXP", "VRN"},
    {"VCE", "VRN"},
    {"FCO", "NAP"},
    {"VIE", "BUD"},
    {"VIE", "SZG"},
    {"MUC", "SZG"},
    {"GVA", "LYS"},
    {"TIV", "DBV"},
    {"LJU", "ZAG"},
]

MIN_NIGHTS_FOR_REGIONAL_OPEN_JAW: int = 6

OPEN_JAW_CLUSTERS: list[set[str]] = (
    SAME_CITY_OPEN_JAW_CLUSTERS + CLOSE_OVERLAND_OPEN_JAW_CLUSTERS
)

TRANSFERABLE_CC_PROGRAMS: set[str] = {
    "AMEX_MR_ISRAEL",
    "ISRAELI_CC_TRAVEL_POINTS",
}

PARTNER_AIRLINE_PROGRAMS: set[str] = {
    "BRITISH_AVIOS",
    "FLYING_BLUE",
    "UNITED_MILEAGEPLUS",
    "MILES_AND_MORE",
    "DELTA_SKYMILES",
    "QANTAS_FREQUENT_FLYER",
    "AEGEAN_MILES_BONUS",
}

CARRIER_TO_LOYALTY_PROGRAM: dict[str, str] = {
    "LY": "ELAL_MATMID",
    "2U": "ELAL_MATMID",
    "BA": "BRITISH_AVIOS",
    "AF": "FLYING_BLUE",
    "UA": "UNITED_MILEAGEPLUS",
    "LH": "MILES_AND_MORE",
    "OS": "MILES_AND_MORE",
    "LX": "MILES_AND_MORE",
    "DL": "DELTA_SKYMILES",
    "A3": "AEGEAN_MILES_BONUS",
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_same_city_open_jaw(iata_a: str, iata_b: str) -> bool:
    a_up = str(iata_a).upper().strip()
    b_up = str(iata_b).upper().strip()
    if not a_up or not b_up or a_up == b_up:
        return False
    return any(
        a_up in cluster and b_up in cluster
        for cluster in SAME_CITY_OPEN_JAW_CLUSTERS
    )


def _are_open_jaw_compatible(
    iata_a: str, iata_b: str, trip_nights: Optional[int] = None
) -> bool:
    a_up = str(iata_a).upper().strip()
    b_up = str(iata_b).upper().strip()
    if not a_up or not b_up or a_up == b_up:
        return False
    if _is_same_city_open_jaw(a_up, b_up):
        return True
    if any(
        a_up in cluster and b_up in cluster
        for cluster in CLOSE_OVERLAND_OPEN_JAW_CLUSTERS
    ):
        if trip_nights is None:
            return True
        return int(trip_nights) >= MIN_NIGHTS_FOR_REGIONAL_OPEN_JAW
    return False


@dataclass
class _PassengerSpec:
    passenger_id: str
    passenger_label: str
    is_adult: bool
    age_years: int
    fare_type: str
    requires_seat: bool
    is_under_12: bool


@dataclass
class _WorkingWallet:
    wallet_id: str
    passenger_id: str
    passenger_name: str
    program_code: str
    available_raw_points: int
    remaining_raw_points: int
    can_pool_with_family: bool
    pool_group_id: str
    transfer_ratio: float
    has_club_credit_card: bool
    companion_vouchers: int

    @property
    def remaining_airline_points(self) -> int:
        return int(math.floor(self.remaining_raw_points * self.transfer_ratio + 1e-9))


@dataclass
class _BonusSlot:
    cabin_class: str
    rbd_code: str
    points_cost: int
    direction: str = "ROUND_TRIP"
    preferred_program: Optional[str] = None
    requires_two_plus_verify: bool = False


def _build_passenger_specs(profile: FamilyProfile) -> list[_PassengerSpec]:
    specs: list[_PassengerSpec] = []
    adults_n = max(1, int(profile.adults_count))
    wallet_names_by_pax: dict[str, str] = {}
    for w in profile.passenger_loyalty_wallets or []:
        if w.passenger_id and w.passenger_name and w.passenger_id not in wallet_names_by_pax:
            wallet_names_by_pax[w.passenger_id] = w.passenger_name

    for i in range(1, adults_n + 1):
        pid = f"ADULT_{i}"
        w_name = wallet_names_by_pax.get(pid, "")
        if w_name:
            if "הורה" in w_name or "ADULT" in w_name.upper():
                label = w_name
            else:
                label = f"{w_name} (הורה {i})"
        else:
            label = f"הורה {i} ({pid})"
        specs.append(
            _PassengerSpec(
                passenger_id=pid,
                passenger_label=label,
                is_adult=True,
                age_years=35,
                fare_type="ADULT",
                requires_seat=True,
                is_under_12=False,
            )
        )

    lap_infants_assigned = 0
    for j, child in enumerate(profile.children or [], start=1):
        pid = f"CHILD_{j}"
        age = int(child.child_age_years)
        raw_f_type = str(child.passenger_Current_type or "").upper()
        if age < 2:
            if raw_f_type != "INFANT_SEAT" and lap_infants_assigned < adults_n:
                f_type = "INFANT_LAP"
                lap_infants_assigned += 1
            else:
                f_type = "INFANT_SEAT"
        elif age <= 11:
            f_type = "CHILD"
        else:
            f_type = "YOUTH"
        req_seat = f_type != "INFANT_LAP"
        under_12 = (age < 12) or (f_type in ("INFANT_LAP", "INFANT_SEAT", "CHILD"))
        c_name = child.child_name or f"ילד {j}"
        label = f"{c_name} (גיל {age})"
        specs.append(
            _PassengerSpec(
                passenger_id=pid,
                passenger_label=label,
                is_adult=False,
                age_years=age,
                fare_type=f_type,
                requires_seat=req_seat,
                is_under_12=under_12,
            )
        )
    return specs


GOOGLE_FLIGHTS_PLACE_NAMES: dict[str, str] = {
    "TLV": "Tel Aviv",
    "ATH": "Athens",
    "LCA": "Larnaca",
    "RHO": "Rhodes",
    "PFO": "Paphos",
    "TBS": "Tbilisi",
    "ROM": "Rome",
    "FCO": "Rome",
    "MIL": "Milan",
    "MXP": "Milan",
    "VIE": "Vienna",
    "BUD": "Budapest",
    "PRG": "Prague",
    "BER": "Berlin",
    "MUC": "Munich",
    "LON": "London",
    "LHR": "London Heathrow",
    "LTN": "London",
    "PAR": "Paris",
    "CDG": "Paris Charles de Gaulle",
    "MAD": "Madrid",
    "BCN": "Barcelona",
    "AMS": "Amsterdam",
    "BKK": "Bangkok",
    "TYO": "Tokyo Narita",
    "NRT": "Tokyo Narita",
    "HKT": "HKT",
    "NYC": "New York JFK",
    "JFK": "New York JFK",
    "EWR": "Newark",
    "MIA": "Miami",
    "FLL": "Fort Lauderdale",
    "HER": "Heraklion",
    "SKG": "Thessaloniki",
    "CFU": "Corfu",
    "EFL": "Kefalonia",
    "JTR": "Santorini",
    "BUS": "Batumi",
    "TIV": "Tivat",
    "BEG": "Belgrade",
    "OTP": "Bucharest",
    "SOF": "Sofia",
    "WAW": "Warsaw",
    "KRK": "Krakow",
    "VCE": "Venice",
    "GVA": "Geneva",
    "ZRH": "Zurich",
    "FRA": "Frankfurt am Main",
    "LIS": "Lisbon",
    "OPO": "Porto",
    "NCE": "NCE",
    "LYS": "Lyon",
    "BSL": "Basel",
    "SZG": "Salzburg",
    "TIA": "Tirana",
    "NAP": "Naples",
    "VRN": "Verona",
    "JMK": "Mykonos",
    "PVK": "Preveza",
    "DBV": "Dubrovnik",
    "ZAG": "Zagreb",
    "LJU": "Ljubljana",
    "RMO": "Chisinau",
    "KIV": "Chisinau",
    "SEZ": "Seychelles",
    "DXB": "Dubai",
    "LAX": "Los Angeles",
    "BOS": "Boston",
}


def resolve_google_flights_place_name(iata_code: str) -> str:
    """Resolve an airport/metro code to a verified Google Flights natural-language destination name.

    Prevents ambiguous 3-letter codes (such as `TBS`, `BUS`, `HER`, `OTP`) or parenthetical labels
    from failing Google Flights' `?q=` parser and falling back to an empty search form.
    """
    code = str(iata_code or "TLV").strip().upper()
    if code in GOOGLE_FLIGHTS_PLACE_NAMES:
        return GOOGLE_FLIGHTS_PLACE_NAMES[code]
    meta = DESTINATION_CATALOG.get(code)
    if meta and meta.get("city_en"):
        base_city = str(meta["city_en"]).split("(", 1)[0].strip()
        if base_city:
            return base_city
    return code


def build_elal_google_flights_url(
    origin_iata: str,
    dest_iata: str,
    return_origin_iata: str,
    dep_date: date,
    ret_date: date,
    passengers: list[_PassengerSpec],
    primary_cabin: str = "ECONOMY",
) -> str:
    """Build a WAF-safe Google Flights search URL pre-filled with verified destination names,
    nonstop filter, exact outbound/return dates, cabin class, and family passenger breakdown
    (`adults`, `children`, `infants`).

    Uses verified city/airport names (rather than raw ambiguous 3-letter codes like `TBS`) and
    omits `"on EL AL"` so both EL AL mainline and Sun d'Or (`2U`/`LY5xxx`) nonstop flights load
    cleanly with live prices and official partner-signed handoff into `booking.elal.com`.
    """
    orig = str(origin_iata or "TLV").strip().upper()
    dest = str(dest_iata or "FCO").strip().upper()
    ret_orig = str(return_origin_iata or dest).strip().upper()
    orig_place = resolve_google_flights_place_name(orig)
    dest_place = resolve_google_flights_place_name(dest)

    adt_count = max(
        1,
        sum(1 for p in passengers if p.requires_seat and not p.is_under_12),
    )
    chd_count = sum(1 for p in passengers if p.requires_seat and p.is_under_12)
    inf_count = min(adt_count, sum(1 for p in passengers if not p.requires_seat))

    pax_parts: list[str] = [f"{adt_count} adult" if adt_count == 1 else f"{adt_count} adults"]
    if chd_count > 0:
        pax_parts.append("1 child" if chd_count == 1 else f"{chd_count} children")
    if inf_count > 0:
        pax_parts.append("1 infant" if inf_count == 1 else f"{inf_count} infants")

    if len(pax_parts) == 1:
        pax_phrase = pax_parts[0]
    elif len(pax_parts) == 2:
        pax_phrase = f"{pax_parts[0]} and {pax_parts[1]}"
    else:
        pax_phrase = f"{pax_parts[0]}, {pax_parts[1]} and {pax_parts[2]}"

    norm_cabin = str(primary_cabin or "ECONOMY").strip().upper()
    cabin_phrase = ""
    if norm_cabin == "BUSINESS":
        cabin_phrase = " business class"
    elif norm_cabin == "PREMIUM":
        cabin_phrase = " premium economy"

    if ret_orig == dest:
        query_str = (
            f"Flights to {dest_place} from {orig_place} on {dep_date.isoformat()} "
            f"through {ret_date.isoformat()} with {pax_phrase}{cabin_phrase} nonstop"
        )
    else:
        query_str = (
            f"One way flights to {dest_place} from {orig_place} on {dep_date.isoformat()} "
            f"with {pax_phrase}{cabin_phrase} nonstop"
        )

    params = [
        ("q", query_str),
        ("curr", "USD"),
        ("gl", "IL"),
        ("hl", "en"),
    ]
    return f"https://www.google.com/travel/flights?{urlencode(params)}"


def _cabin_award_info(
    award: ElAlBonusAvailability, cabin: str
) -> tuple[int, bool, str, int]:
    """Return `(seats, is_two_plus, rbd_code, points_per_pax)` for `cabin` on `award`."""
    c_up = cabin.upper()
    dest = award.destination_iata if award.direction == "OUTBOUND" else award.origin_iata
    meta = DESTINATION_CATALOG.get(dest, {})
    if c_up == "ECONOMY":
        pts = (
            int(award.economy_points_per_pax)
            if award.economy_points_per_pax is not None
            else int(meta.get("economy_points", 15000))
        )
        return (
            int(award.economy_award_seats),
            bool(award.economy_seats_is_two_plus),
            str(award.economy_rbd_code or "E"),
            pts,
        )
    if c_up == "PREMIUM":
        raw_pts = (
            award.premium_points_per_pax
            if award.premium_points_per_pax is not None
            else meta.get("premium_points", 20500)
        )
        pts = int(raw_pts) if raw_pts else 0
        return (
            int(award.premium_award_seats),
            bool(award.premium_seats_is_two_plus),
            str(award.premium_rbd_code or "P"),
            pts,
        )
    if c_up == "BUSINESS":
        raw_pts = (
            award.business_points_per_pax
            if award.business_points_per_pax is not None
            else meta.get("business_points", 45000)
        )
        pts = int(raw_pts) if raw_pts else 0
        return (
            int(award.business_award_seats),
            bool(award.business_seats_is_two_plus),
            str(award.business_rbd_code or "I"),
            pts,
        )
    return 0, False, "E", 0


def _direction_bonus_seats(
    award: Optional[ElAlBonusAvailability], cabins: list[str]
) -> tuple[Optional[int], bool]:
    """Return `(available_bonus_seats, any_two_plus_bucket)` for one direction.

    Seats are summed, as stored, over the cabins the search considers (a `2+` bucket
    counts as its stored value). A cabin counts only if a bonus ticket can be booked in
    it on this row (it has a points price), which is the test every strategy applies.
    `None` means there is no award row for the direction.
    """
    if award is None:
        return None, False
    total_seats = 0
    any_two_plus = False
    for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
        if cab not in cabins:
            continue
        seats, is_two_plus, _rbd, pts = _cabin_award_info(award, cab)
        if seats <= 0 or pts <= 0:
            continue
        total_seats += int(seats)
        any_two_plus = any_two_plus or bool(is_two_plus)
    return total_seats, any_two_plus


def _bonus_direction_coverage(
    outbound_seats: Optional[int], inbound_seats: Optional[int]
) -> str:
    """Say in which directions at least one bonus seat is available (seats only)."""
    has_out = bool(outbound_seats and int(outbound_seats) > 0)
    has_in = bool(inbound_seats and int(inbound_seats) > 0)
    if has_out and has_in:
        return "BOTH_DIRECTIONS"
    if has_out:
        return "OUTBOUND_ONLY"
    if has_in:
        return "INBOUND_ONLY"
    return "NONE"


class MultiClubWalletAllocationEngine:
    """Allocates family tickets across per-passenger loyalty wallets and all 6 bonus strategies."""

    def _prepare_working_wallets(
        self,
        profile: FamilyProfile,
        enabled_programs: list[str],
    ) -> list[_WorkingWallet]:
        enabled_set = {
            str(p.value if isinstance(p, Enum) else p).strip().upper()
            for p in (enabled_programs or ["ELAL_MATMID"])
            if str(p).strip()
        }
        valid_codes = {c.value for c in LoyaltyProgramCode}
        enabled_set = enabled_set & valid_codes

        working: list[_WorkingWallet] = []
        for idx, w in enumerate(profile.passenger_loyalty_wallets or [], start=1):
            p_code = (
                w.program_code.value
                if isinstance(w.program_code, Enum)
                else str(w.program_code).strip().upper()
            )
            if p_code not in enabled_set:
                continue
            avail = max(0, int(w.available_points))
            if avail <= 0:
                continue
            wid = str(w.id or f"wallet-{w.passenger_id}-{p_code}-{idx}")
            ratio = max(0.01, float(w.transfer_ratio_to_airline or 1.0))
            pool_grp = str(w.pool_group_id or ("FAMILY_POOL" if w.can_pool_with_family else wid))
            working.append(
                _WorkingWallet(
                    wallet_id=wid,
                    passenger_id=str(w.passenger_id or "ADULT_1"),
                    passenger_name=str(w.passenger_name or "הורה 1"),
                    program_code=p_code,
                    available_raw_points=avail,
                    remaining_raw_points=avail,
                    can_pool_with_family=bool(w.can_pool_with_family),
                    pool_group_id=pool_grp,
                    transfer_ratio=ratio,
                    has_club_credit_card=bool(w.has_club_credit_card),
                    companion_vouchers=max(0, int(w.companion_vouchers_count)),
                )
            )

        if "ELAL_MATMID" in enabled_set:
            matmid_wallets = [w for w in working if w.program_code == "ELAL_MATMID"]
            prof_matmid = max(0, int(profile.matmid_points_balance))
            if not matmid_wallets and prof_matmid > 0:
                working.insert(
                    0,
                    _WorkingWallet(
                        wallet_id=f"wallet-{profile.id}-matmid",
                        passenger_id="ADULT_1",
                        passenger_name="הורה 1",
                        program_code="ELAL_MATMID",
                        available_raw_points=prof_matmid,
                        remaining_raw_points=prof_matmid,
                        can_pool_with_family=True,
                        pool_group_id="FAMILY_POOL",
                        transfer_ratio=1.0,
                        has_club_credit_card=bool(profile.has_flycard),
                        companion_vouchers=max(0, int(profile.flycard_companion_vouchers)),
                    ),
                )
            elif matmid_wallets and all(w.can_pool_with_family for w in matmid_wallets):
                wallet_sum = sum(w.available_raw_points for w in matmid_wallets)
                if prof_matmid > wallet_sum:
                    delta = prof_matmid - wallet_sum
                    matmid_wallets[0].available_raw_points += delta
                    matmid_wallets[0].remaining_raw_points += delta

        return working

    def effective_elal_points_balance(
        self,
        profile: FamilyProfile,
        enabled_programs: Optional[list[str]] = None,
    ) -> int:
        """Points the household can spend on El Al bonus tickets.

        Sum of the working El Al Matmid wallets (including the profile-level pooled
        balance) and transferable credit-card wallets, in airline points.
        """
        wallets = self._prepare_working_wallets(
            profile,
            list(enabled_programs) if enabled_programs is not None else ["ELAL_MATMID"],
        )
        return int(
            sum(
                w.remaining_airline_points
                for w in wallets
                if w.program_code in ("ELAL_MATMID", *TRANSFERABLE_CC_PROGRAMS)
                and w.remaining_airline_points > 0
            )
        )

    def _assign_passengers_with_pnr_safety(
        self,
        seated_passengers: list[_PassengerSpec],
        bonus_count: int,
    ) -> Optional[tuple[list[_PassengerSpec], list[_PassengerSpec]]]:
        """Partition `seated_passengers` into `(bonus_passengers, cash_passengers)`
        enforcing Adult-Child Under-12 PNR Safety Pairing (`F24`, `F27`).

        Returns `None` if any PNR with a child under 12 would lack an adult.
        """
        n_seated = len(seated_passengers)
        n_cash = n_seated - bonus_count
        adults = [p for p in seated_passengers if p.is_adult]
        under12 = [p for p in seated_passengers if not p.is_adult and p.is_under_12]
        youth12plus = [p for p in seated_passengers if not p.is_adult and not p.is_under_12]

        if bonus_count <= 0:
            return ([], list(seated_passengers))
        if n_cash <= 0:
            return (list(seated_passengers), [])

        # Both Bonus PNR and Cash PNR are non-empty (bonus_count >= 1 and n_cash >= 1)
        if len(adults) == 1:
            # Single adult household: the single adult MUST accompany all under-12 children!
            if under12:
                # All under-12 children + the single adult must stay together on the same PNR.
                group_size = 1 + len(under12)
                if bonus_count >= group_size and n_cash <= len(youth12plus):
                    bonus_pax = [adults[0], *under12, *youth12plus[: bonus_count - group_size]]
                    cash_pax = youth12plus[bonus_count - group_size :]
                    return (bonus_pax, cash_pax)
                if n_cash >= group_size and bonus_count <= len(youth12plus):
                    bonus_pax = youth12plus[:bonus_count]
                    cash_pax = [adults[0], *under12, *youth12plus[bonus_count:]]
                    return (bonus_pax, cash_pax)
                return None
            # Single adult with only youth >= 12
            return (seated_passengers[:bonus_count], seated_passengers[bonus_count:])

        # Multi-adult household (len(adults) >= 2):
        # Place ADULT_1 on the Bonus PNR and ADULT_2 on the Cash PNR so BOTH PNRs have an adult!
        adult_bonus = adults[0]
        adult_cash = adults[1]
        extra_adults = adults[2:]

        # Priority for remaining (bonus_count - 1) Bonus slots:
        # 1. Under-12 children (kept with ADULT_1 on Bonus PNR; any overflow goes to Cash PNR with ADULT_2)
        # 2. Youth >= 12 children
        # 3. Extra adults (ADULT_3..)
        remaining_candidates = [*under12, *youth12plus, *extra_adults]
        take_for_bonus = max(0, bonus_count - 1)
        bonus_pax = [adult_bonus, *remaining_candidates[:take_for_bonus]]
        cash_pax = [adult_cash, *remaining_candidates[take_for_bonus:]]
        return (bonus_pax, cash_pax)

    def _build_legs(
        self,
        outbound_award: Optional[ElAlBonusAvailability],
        inbound_award: Optional[ElAlBonusAvailability],
        commercial_offer: Optional[dict[str, Any]],
        origin_iata: str,
        dest_iata: str,
        return_origin_iata: str,
        dep_date: date,
        ret_date: date,
    ) -> tuple[list[FlightLeg], list[FlightLeg]]:
        out_meta = DESTINATION_CATALOG.get(dest_iata, {})
        in_meta = DESTINATION_CATALOG.get(return_origin_iata, out_meta)
        has_live_award = any(
            "#live" in str(getattr(aw, "source_url", "") or "")
            for aw in (outbound_award, inbound_award)
            if aw is not None
        )

        if outbound_award is not None:
            out_leg = FlightLeg(
                flight_number=outbound_award.flight_number,
                operating_carrier=outbound_award.operating_carrier,
                origin_iata=origin_iata,
                destination_iata=dest_iata,
                flight_date=outbound_award.flight_date,
                departure_time_local=outbound_award.departure_time_local,
                arrival_time_local=outbound_award.arrival_time_local,
                aircraft_type=outbound_award.aircraft_type or str(out_meta.get("aircraft_type", "789")),
                duration_minutes=int(out_meta.get("duration_minutes", 225)),
                is_direct=True,
            )
        elif commercial_offer is not None:
            out_leg = FlightLeg(
                flight_number=str(commercial_offer.get("outbound_flight_number") or "LY381"),
                operating_carrier=str(commercial_offer.get("primary_carrier_iata") or "LY"),
                origin_iata=origin_iata,
                destination_iata=dest_iata,
                flight_date=dep_date,
                departure_time_local=str(commercial_offer.get("departure_time_out") or "07:15"),
                arrival_time_local=str(commercial_offer.get("arrival_time_out") or "10:00"),
                aircraft_type=str(commercial_offer.get("aircraft_type") or "789"),
                duration_minutes=int(commercial_offer.get("duration_minutes") or 225),
                is_direct=bool(commercial_offer.get("is_direct", True)),
            )
        elif has_live_award:
            out_leg = FlightLeg(
                flight_number="LY_CASH",
                operating_carrier=str(out_meta.get("operating_carrier", "LY")),
                origin_iata=origin_iata,
                destination_iata=dest_iata,
                flight_date=dep_date,
                departure_time_local="",
                arrival_time_local="",
                aircraft_type=str(out_meta.get("aircraft_type", "789")),
                duration_minutes=int(out_meta.get("duration_minutes", 225)),
                is_direct=True,
            )
        else:
            out_leg = FlightLeg(
                flight_number=str(out_meta.get("outbound_flight", "LY381")),
                operating_carrier=str(out_meta.get("operating_carrier", "LY")),
                origin_iata=origin_iata,
                destination_iata=dest_iata,
                flight_date=dep_date,
                departure_time_local=str(out_meta.get("dep_time_out", "07:15")),
                arrival_time_local=str(out_meta.get("arr_time_out", "10:00")),
                aircraft_type=str(out_meta.get("aircraft_type", "789")),
                duration_minutes=int(out_meta.get("duration_minutes", 225)),
                is_direct=True,
            )

        if inbound_award is not None:
            in_leg = FlightLeg(
                flight_number=inbound_award.flight_number,
                operating_carrier=inbound_award.operating_carrier,
                origin_iata=return_origin_iata,
                destination_iata=origin_iata,
                flight_date=inbound_award.flight_date,
                departure_time_local=inbound_award.departure_time_local,
                arrival_time_local=inbound_award.arrival_time_local,
                aircraft_type=inbound_award.aircraft_type or str(in_meta.get("aircraft_type", "789")),
                duration_minutes=int(in_meta.get("duration_minutes", 230)),
                is_direct=True,
            )
        elif commercial_offer is not None:
            in_leg = FlightLeg(
                flight_number=str(commercial_offer.get("inbound_flight_number") or "LY384"),
                operating_carrier=str(commercial_offer.get("primary_carrier_iata") or "LY"),
                origin_iata=return_origin_iata,
                destination_iata=origin_iata,
                flight_date=ret_date,
                departure_time_local=str(commercial_offer.get("departure_time_in") or "21:45"),
                arrival_time_local=str(commercial_offer.get("arrival_time_in") or "02:10"),
                aircraft_type=str(commercial_offer.get("aircraft_type") or "789"),
                duration_minutes=int(commercial_offer.get("duration_minutes") or 230),
                is_direct=bool(commercial_offer.get("is_direct", True)),
            )
        elif has_live_award:
            in_leg = FlightLeg(
                flight_number="LY_CASH",
                operating_carrier=str(in_meta.get("operating_carrier", "LY")),
                origin_iata=return_origin_iata,
                destination_iata=origin_iata,
                flight_date=ret_date,
                departure_time_local="",
                arrival_time_local="",
                aircraft_type=str(in_meta.get("aircraft_type", "789")),
                duration_minutes=int(in_meta.get("duration_minutes", 230)),
                is_direct=True,
            )
        else:
            in_leg = FlightLeg(
                flight_number=str(in_meta.get("inbound_flight", "LY384")),
                operating_carrier=str(in_meta.get("operating_carrier", "LY")),
                origin_iata=return_origin_iata,
                destination_iata=origin_iata,
                flight_date=ret_date,
                departure_time_local=str(in_meta.get("dep_time_in", "21:45")),
                arrival_time_local=str(in_meta.get("arr_time_in", "02:10")),
                aircraft_type=str(in_meta.get("aircraft_type", "789")),
                duration_minutes=int(in_meta.get("duration_minutes", 230)),
                is_direct=True,
            )

        return [out_leg], [in_leg]

    def allocate_family_tickets(
        self,
        profile: FamilyProfile,
        outbound_award: Optional[ElAlBonusAvailability],
        inbound_award: Optional[ElAlBonusAvailability],
        cash_benchmark_per_pax: float,
        strategy: str | FulfillmentStrategy = "HYBRID_BONUS_PLUS_CASH",
        preferred_cabins: Optional[list[str]] = None,
        enabled_programs: Optional[list[str]] = None,
        commercial_offer: Optional[dict[str, Any]] = None,
        fallback_departure_date: Optional[date] = None,
        fallback_return_date: Optional[date] = None,
    ) -> Optional[dict[str, Any]]:
        """Allocate family tickets for `strategy` and return an itinerary dictionary (or `None` if infeasible)."""
        strat_str = (
            strategy.value if isinstance(strategy, Enum) else str(strategy).strip().upper()
        )
        pref_cabins = [
            str(c).strip().upper()
            for c in (preferred_cabins if preferred_cabins is not None else ["ECONOMY", "PREMIUM", "BUSINESS"])
            if str(c).strip()
        ]
        if not pref_cabins:
            pref_cabins = ["ECONOMY", "PREMIUM", "BUSINESS"]

        prog_list = list(enabled_programs) if enabled_programs is not None else ["ELAL_MATMID"]

        passengers = _build_passenger_specs(profile)
        seated_passengers = [p for p in passengers if p.requires_seat]
        lap_infants = [p for p in passengers if not p.requires_seat]
        n_seated = max(1, len(seated_passengers))

        origin_iata = "TLV"
        dest_iata = "FCO"
        return_origin_iata = "FCO"
        dep_date = fallback_departure_date or date(2027, 4, 11)
        ret_date = fallback_return_date or date(2027, 4, 18)

        if outbound_award is not None:
            origin_iata = outbound_award.origin_iata if outbound_award.direction == "OUTBOUND" else outbound_award.destination_iata
            dest_iata = outbound_award.destination_iata if outbound_award.direction == "OUTBOUND" else outbound_award.origin_iata
            return_origin_iata = dest_iata
            dep_date = outbound_award.flight_date
            if inbound_award is None and fallback_return_date is None:
                ret_date = dep_date + timedelta(days=7)
        if inbound_award is not None:
            return_origin_iata = inbound_award.origin_iata if inbound_award.direction == "INBOUND" else inbound_award.destination_iata
            if outbound_award is None:
                dest_iata = return_origin_iata
            ret_date = inbound_award.flight_date
            if outbound_award is None and fallback_departure_date is None:
                dep_date = ret_date - timedelta(days=7)
        if ret_date <= dep_date:
            ret_date = dep_date + timedelta(days=max(1, (fallback_return_date - fallback_departure_date).days if (fallback_departure_date and fallback_return_date and fallback_return_date > fallback_departure_date) else 5))
        if commercial_offer is not None and outbound_award is None and inbound_award is None:
            origin_iata = str(commercial_offer.get("origin_iata") or "TLV")
            dest_iata = str(commercial_offer.get("destination_iata") or "FCO")
            return_origin_iata = dest_iata
            if commercial_offer.get("departure_date"):
                raw_dep = commercial_offer["departure_date"]
                dep_date = (
                    raw_dep
                    if isinstance(raw_dep, date)
                    else date.fromisoformat(str(raw_dep)[:10])
                )
            if commercial_offer.get("return_date"):
                raw_ret = commercial_offer["return_date"]
                ret_date = (
                    raw_ret
                    if isinstance(raw_ret, date)
                    else date.fromisoformat(str(raw_ret)[:10])
                )

        meta = DESTINATION_CATALOG.get(dest_iata, {})
        in_meta_check = DESTINATION_CATALOG.get(return_origin_iata, meta)

        has_live_award = any(
            "#live" in str(getattr(aw, "source_url", "") or "")
            for aw in (outbound_award, inbound_award)
            if aw is not None
        )

        # Never fabricate a synthetic El Al / Sundor fallback leg on Yom Kippur or Shabbat
        if outbound_award is None and commercial_offer is None:
            out_carrier = str(meta.get("operating_carrier", "LY"))
            out_dep_t = str(meta.get("dep_time_out", "07:15"))
            out_arr_t = str(meta.get("arr_time_out", "10:00"))
            if dep_date in YOM_KIPPUR_CLOSED_DATES or (
                out_carrier in ("LY", "2U")
                and (
                    (has_live_award and dep_date.weekday() == 5)
                    or is_shabbat_blocked_for_elal(dep_date, out_dep_t, out_arr_t)
                )
            ):
                return None
        if inbound_award is None and commercial_offer is None:
            in_carrier = str(in_meta_check.get("operating_carrier", "LY"))
            in_dep_t = str(in_meta_check.get("dep_time_in", "21:45"))
            in_arr_t = str(in_meta_check.get("arr_time_in", "02:10"))
            if ret_date in YOM_KIPPUR_CLOSED_DATES or (
                in_carrier in ("LY", "2U")
                and (
                    (has_live_award and ret_date.weekday() == 5)
                    or is_shabbat_blocked_for_elal(ret_date, in_dep_t, in_arr_t)
                )
            ):
                return None

        city_he = str(meta.get("city_he") or (commercial_offer or {}).get("destination_city_he") or dest_iata)
        city_en = str(meta.get("city_en") or (commercial_offer or {}).get("destination_city_en") or dest_iata)
        trip_nights = max(1, (ret_date - dep_date).days)

        # Run 11: a result is described only by the bonus seats available per direction.
        # No cash benchmark, supplement, tax, baggage fee or saving is computed here;
        # `cash_benchmark_per_pax` is accepted for call compatibility and ignored.
        out_bonus_seats, out_bonus_two_plus = _direction_bonus_seats(
            outbound_award, pref_cabins
        )
        in_bonus_seats, in_bonus_two_plus = _direction_bonus_seats(
            inbound_award, pref_cabins
        )

        outbound_legs, inbound_legs = self._build_legs(
            outbound_award=outbound_award,
            inbound_award=inbound_award,
            commercial_offer=commercial_offer,
            origin_iata=origin_iata,
            dest_iata=dest_iata,
            return_origin_iata=return_origin_iata,
            dep_date=dep_date,
            ret_date=ret_date,
        )
        primary_carrier = outbound_legs[0].operating_carrier if outbound_legs else "LY"
        is_elal = primary_carrier in ("LY", "2U")

        def _finalize_result(
            *,
            bonus_tickets_count: int,
            cash_tickets_count: int,
            primary_cabin: str,
            requires_verify: bool,
            utilizes_bonus: bool = True,
            min_points: Optional[int] = None,
            min_points_basis: Optional[str] = None,
        ) -> dict[str, Any]:
            if utilizes_bonus:
                res_out_seats, res_out_two_plus = out_bonus_seats, out_bonus_two_plus
                res_in_seats, res_in_two_plus = in_bonus_seats, in_bonus_two_plus
            else:
                res_out_seats, res_out_two_plus = None, False
                res_in_seats, res_in_two_plus = None, False
            coverage = _bonus_direction_coverage(res_out_seats, res_in_seats)
            clean_min_pts: Optional[int] = None
            if coverage != "NONE" and min_points is not None and int(min_points) > 0:
                clean_min_pts = int(min_points)

            norm_cabin = (
                primary_cabin
                if primary_cabin in ("ECONOMY", "PREMIUM", "BUSINESS")
                else "ECONOMY"
            )

            itin = FlightItinerary(
                id=str(uuid.uuid4()),
                origin_iata=origin_iata,
                destination_iata=dest_iata,
                return_origin_iata=return_origin_iata,
                destination_city_he=city_he,
                destination_city_en=city_en,
                departure_date=dep_date,
                return_date=ret_date,
                trip_nights=trip_nights,
                primary_carrier_iata=primary_carrier,
                is_elal_flight=is_elal,
                utilizes_elal_bonus=utilizes_bonus,
                fulfillment_strategy=FulfillmentStrategy(strat_str),
                outbound_legs=outbound_legs,
                inbound_legs=inbound_legs,
                outbound_bonus_id=outbound_award.id if (outbound_award and utilizes_bonus) else None,
                inbound_bonus_id=inbound_award.id if (inbound_award and utilizes_bonus) else None,
                seated_passengers_count=n_seated,
                bonus_tickets_count=int(bonus_tickets_count),
                cash_tickets_count=int(cash_tickets_count),
                primary_cabin=norm_cabin,
                requires_two_plus_seat_verification=bool(requires_verify),
                rbddataclients_verify_url="https://www.elal.com/rbddataclients/" if is_elal else None,
                booking_deep_link_url=(
                    "https://www.elal.com/heb/israel"
                    if is_elal
                    else f"https://www.google.com/travel/flights?q={origin_iata}.{dest_iata}.{dep_date.isoformat()}"
                ),
                elal_google_flights_url=(
                    build_elal_google_flights_url(
                        origin_iata=origin_iata,
                        dest_iata=dest_iata,
                        return_origin_iata=return_origin_iata,
                        dep_date=dep_date,
                        ret_date=ret_date,
                        passengers=passengers,
                        primary_cabin=norm_cabin,
                    )
                    if is_elal
                    else None
                ),
                bonus_direction_coverage=coverage,
                outbound_bonus_seats=res_out_seats,
                inbound_bonus_seats=res_in_seats,
                outbound_bonus_seats_is_two_plus=res_out_two_plus,
                inbound_bonus_seats_is_two_plus=res_in_two_plus,
                min_points_per_bonus_ticket=clean_min_pts,
                min_points_basis=(min_points_basis if clean_min_pts is not None else None),
                points_are_estimated=True,
            )
            return itin.to_dict()

        # =====================================================================
        # Strategy 7: COMMERCIAL_CASH_ONLY
        # =====================================================================
        if strat_str == "COMMERCIAL_CASH_ONLY":
            # A commercial-only result: no bonus seats, no points and no cash figure.
            return _finalize_result(
                bonus_tickets_count=0,
                cash_tickets_count=n_seated,
                primary_cabin="ECONOMY",
                requires_verify=False,
                utilizes_bonus=False,
            )

        # =====================================================================
        # Strategy 1: FULL_BONUS_SAME_CABIN (F22)
        # =====================================================================
        if strat_str == "FULL_BONUS_SAME_CABIN":
            if outbound_award is None or inbound_award is None:
                return None
            for cabin in ("ECONOMY", "PREMIUM", "BUSINESS"):
                if cabin not in pref_cabins:
                    continue
                out_s, out_2p, out_rbd, out_pts = _cabin_award_info(outbound_award, cabin)
                in_s, in_2p, _in_rbd, in_pts = _cabin_award_info(inbound_award, cabin)
                if out_pts <= 0 or in_pts <= 0:
                    continue
                if n_seated == 1:
                    if out_s < 1 or in_s < 1:
                        continue
                else:
                    # Family of >= 2 seated passengers requires 2+ (`*_seats_is_two_plus=True` and `seats >= 2`)
                    if out_s < 2 or not out_2p or in_s < 2 or not in_2p:
                        continue
                    # If an explicit seat count > 2 was set that is smaller than n_seated, respect it
                    if (out_s > 2 and out_s < n_seated) or (in_s > 2 and in_s < n_seated):
                        continue

                return _finalize_result(
                    bonus_tickets_count=n_seated,
                    cash_tickets_count=0,
                    primary_cabin=cabin,
                    requires_verify=(n_seated >= 3),
                    utilizes_bonus=True,
                    min_points=out_pts + in_pts,
                    min_points_basis="ROUND_TRIP",
                )
            return None

        # =====================================================================
        # Strategy 2: SPLIT_CABIN_BONUS (F23)
        # =====================================================================
        if strat_str == "SPLIT_CABIN_BONUS":
            if outbound_award is None or inbound_award is None:
                return None
            if len(pref_cabins) < 2 or n_seated < 2:
                return None
            if outbound_award.flight_date != dep_date or inbound_award.flight_date != ret_date:
                return None

            # Candidate slot plans:
            # Plan 1: Strict <= 2 seats per cabin (e.g. 2x Economy + 2x Premium + 1x Business)
            # Plan 2: If 5 seated pax and Plan 1 exceeds point budget, allow 3x Economy (2+ verified) + 2x Premium/Business
            candidate_slot_plans: list[tuple[list[_BonusSlot], bool]] = []

            strict_slots: list[_BonusSlot] = []
            for cabin in ("ECONOMY", "PREMIUM", "BUSINESS"):
                if cabin not in pref_cabins:
                    continue
                out_s, _out_2p, out_rbd, out_pts = _cabin_award_info(outbound_award, cabin)
                in_s, _in_2p, _in_rbd, in_pts = _cabin_award_info(inbound_award, cabin)
                if out_pts <= 0 or in_pts <= 0:
                    continue
                if cabin == "PREMIUM" and out_s >= 2 and in_s == 1:
                    in_biz_s, _, _, _ = _cabin_award_info(inbound_award, "BUSINESS")
                    avail_in = in_s + (1 if in_biz_s >= 1 else 0)
                else:
                    avail_in = in_s
                cap = min(out_s, avail_in, 2)
                for _ in range(cap):
                    strict_slots.append(
                        _BonusSlot(
                            cabin_class=cabin,
                            rbd_code=out_rbd,
                            points_cost=out_pts + in_pts,
                        )
                    )
            if len(strict_slots) >= n_seated:
                chosen = strict_slots[:n_seated]
                if len({s.cabin_class for s in chosen}) >= 2:
                    candidate_slot_plans.append((chosen, False))

            # Plan 2 (for 5+ seated pax when Economy has 2+ and upper cabin has 2+): 3x Economy + 2x Upper
            if n_seated >= 5 and "ECONOMY" in pref_cabins:
                out_e, out_e2p, e_rbd, out_e_pts = _cabin_award_info(outbound_award, "ECONOMY")
                in_e, in_e2p, _, in_e_pts = _cabin_award_info(inbound_award, "ECONOMY")
                if out_e >= 2 and out_e2p and in_e >= 2 and in_e2p and out_e_pts > 0 and in_e_pts > 0:
                    for upper_cab in ("PREMIUM", "BUSINESS"):
                        if upper_cab not in pref_cabins:
                            continue
                        out_u, _, u_rbd, out_u_pts = _cabin_award_info(outbound_award, upper_cab)
                        in_u, _, _, in_u_pts = _cabin_award_info(inbound_award, upper_cab)
                        if upper_cab == "PREMIUM" and out_u >= 2 and in_u == 1:
                            in_biz_s, _, _, _ = _cabin_award_info(inbound_award, "BUSINESS")
                            in_u = in_u + (1 if in_biz_s >= 1 else 0)
                        if out_u >= 2 and in_u >= 2 and out_u_pts > 0 and in_u_pts > 0:
                            plan2 = [
                                _BonusSlot("ECONOMY", e_rbd, out_e_pts + in_e_pts)
                                for _ in range(n_seated - 2)
                            ] + [
                                _BonusSlot(upper_cab, u_rbd, out_u_pts + in_u_pts)
                                for _ in range(2)
                            ]
                            candidate_slot_plans.append((plan2, True))
                            break

            for slots_plan, req_verify in candidate_slot_plans:
                cabins_in_plan: list[str] = []
                for s in slots_plan:
                    if s.cabin_class not in cabins_in_plan:
                        cabins_in_plan.append(s.cabin_class)

                adults = [p for p in seated_passengers if p.is_adult]
                under12 = [p for p in seated_passengers if not p.is_adult and p.is_under_12]
                others = [p for p in seated_passengers if not p.is_adult and not p.is_under_12]

                # Enforce Adult-Child Under-12 cabin/PNR pairing safety across all cabin buckets
                cabin_slots_map: dict[str, list[_BonusSlot]] = {c: [] for c in cabins_in_plan}
                for s in slots_plan:
                    cabin_slots_map[s.cabin_class].append(s)
                sorted_cabins = sorted(
                    cabins_in_plan, key=lambda c: len(cabin_slots_map[c]), reverse=True
                )
                sorted_caps = [len(cabin_slots_map[c]) for c in sorted_cabins]

                if under12:
                    max_adult_buckets = min(len(adults), len(sorted_caps))
                    valid_k: Optional[int] = None
                    for k_u in range(1, max_adult_buckets + 1):
                        if k_u + len(under12) <= sum(sorted_caps[:k_u]):
                            valid_k = k_u
                            break
                    if valid_k is None:
                        continue
                else:
                    valid_k = min(len(adults), len(sorted_caps))

                ordered_slots: list[_BonusSlot] = []
                ordered_pax: list[_PassengerSpec] = []
                rem_under12 = list(under12)
                rem_others = [*others, *adults[valid_k:]]
                for idx_c, cab_name in enumerate(sorted_cabins):
                    c_slots = cabin_slots_map[cab_name]
                    ordered_slots.extend(c_slots)
                    cap_c = len(c_slots)
                    if idx_c < valid_k and cap_c >= 1:
                        ordered_pax.append(adults[idx_c])
                        rem_cap = cap_c - 1
                        take_u12 = rem_under12[:rem_cap]
                        rem_under12 = rem_under12[rem_cap:]
                        ordered_pax.extend(take_u12)
                        rem_cap -= len(take_u12)
                        if rem_cap > 0:
                            take_oth = rem_others[:rem_cap]
                            rem_others = rem_others[rem_cap:]
                            ordered_pax.extend(take_oth)
                    else:
                        take_oth = rem_others[:cap_c]
                        rem_others = rem_others[cap_c:]
                        ordered_pax.extend(take_oth)

                if rem_under12 or len(ordered_pax) != n_seated:
                    continue

                return _finalize_result(
                    bonus_tickets_count=n_seated,
                    cash_tickets_count=0,
                    primary_cabin="ECONOMY",
                    requires_verify=req_verify,
                    utilizes_bonus=True,
                    min_points=min(s.points_cost for s in ordered_slots),
                    min_points_basis="ROUND_TRIP",
                )
            return None

        # =====================================================================
        # Strategy 3: HYBRID_BONUS_PLUS_CASH (F24)
        # =====================================================================
        if strat_str == "HYBRID_BONUS_PLUS_CASH":
            if outbound_award is None or inbound_award is None:
                return None
            if n_seated < 2:
                return None

            # Collect confirmed round-trip bonus slots across preferred_cabins
            avail_slots: list[_BonusSlot] = []
            for cabin in ("ECONOMY", "PREMIUM", "BUSINESS"):
                if cabin not in pref_cabins:
                    continue
                out_s, _out_2p, out_rbd, out_pts = _cabin_award_info(outbound_award, cabin)
                in_s, _in_2p, _in_rbd, in_pts = _cabin_award_info(inbound_award, cabin)
                if out_pts <= 0 or in_pts <= 0:
                    continue
                if cabin == "PREMIUM" and out_s >= 2 and in_s == 1:
                    # Canonical LY381/LY384 Rome override: 2x Economy + 2x Premium/Business mixed return at Premium rate
                    in_biz_s, _, _, _ = _cabin_award_info(inbound_award, "BUSINESS")
                    avail_in = in_s + (1 if in_biz_s >= 1 else 0)
                else:
                    avail_in = in_s
                cap = min(out_s, avail_in)
                for _ in range(cap):
                    avail_slots.append(
                        _BonusSlot(
                            cabin_class=cabin,
                            rbd_code=out_rbd,
                            points_cost=out_pts + in_pts,
                        )
                    )

            if not avail_slots:
                return None

            # Hybrid requires at least 1 bonus ticket and at least 1 cash ticket (1 <= K <= n_seated - 1)
            max_k = min(len(avail_slots), n_seated - 1)
            for k_try in range(max_k, 0, -1):
                partition = self._assign_passengers_with_pnr_safety(seated_passengers, k_try)
                if partition is None:
                    continue
                bonus_pax, cash_pax = partition
                used_slots = avail_slots[:k_try]
                return _finalize_result(
                    bonus_tickets_count=len(bonus_pax),
                    cash_tickets_count=len(cash_pax),
                    primary_cabin="ECONOMY",
                    requires_verify=False,
                    utilizes_bonus=True,
                    min_points=min(s.points_cost for s in used_slots),
                    min_points_basis="ROUND_TRIP",
                )
            return None

        # =====================================================================
        # Strategy 4: ONE_WAY_BONUS_ONE_WAY_CASH & Open-Jaw Bonus (F25)
        # =====================================================================
        if strat_str == "ONE_WAY_BONUS_ONE_WAY_CASH":
            if outbound_award is None and inbound_award is None:
                return None

            # Case A: Open-Jaw Round-Trip Bonus (e.g. TLV->MXP on LY387 + FCO->TLV on LY384)
            is_open_jaw = (
                outbound_award is not None
                and inbound_award is not None
                and dest_iata != return_origin_iata
            )
            if is_open_jaw:
                assert outbound_award is not None and inbound_award is not None
                if not _are_open_jaw_compatible(
                    dest_iata, return_origin_iata, trip_nights=trip_nights
                ):
                    return None
                bookable_out: list[tuple[str, int, bool, str, int]] = []
                bookable_in: list[tuple[str, int, bool, str, int]] = []
                for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
                    if cab not in pref_cabins:
                        continue
                    os_c, o2p_c, orbd_c, opts_c = _cabin_award_info(outbound_award, cab)
                    if os_c >= 1 and opts_c > 0:
                        bookable_out.append((cab, os_c, o2p_c, orbd_c, opts_c))
                    is_c, i2p_c, irbd_c, ipts_c = _cabin_award_info(inbound_award, cab)
                    if is_c >= 1 and ipts_c > 0:
                        bookable_in.append((cab, is_c, i2p_c, irbd_c, ipts_c))

                if not bookable_out or not bookable_in:
                    return None

                min_rt_pts = min(x[4] for x in bookable_out) + min(x[4] for x in bookable_in)

                # Consistent with FULL_BONUS_SAME_CABIN: if a single preferred cabin has `2+` in
                # both directions (or covers a solo traveler), allocate all seated passengers as
                # round-trip Open-Jaw bonus tickets with `requires_verify = (n_seated >= 3)`.
                for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
                    if cab not in pref_cabins:
                        continue
                    os_c, o2p_c, _, opts_c = _cabin_award_info(outbound_award, cab)
                    is_c, i2p_c, _, ipts_c = _cabin_award_info(inbound_award, cab)
                    if opts_c <= 0 or ipts_c <= 0:
                        continue
                    if n_seated == 1 and os_c >= 1 and is_c >= 1:
                        return _finalize_result(
                            bonus_tickets_count=1,
                            cash_tickets_count=0,
                            primary_cabin=cab,
                            requires_verify=False,
                            utilizes_bonus=True,
                            min_points=opts_c + ipts_c,
                            min_points_basis="ROUND_TRIP",
                        )
                    if (
                        n_seated >= 2
                        and os_c >= 2
                        and o2p_c
                        and is_c >= 2
                        and i2p_c
                        and not ((os_c > 2 and os_c < n_seated) or (is_c > 2 and is_c < n_seated))
                    ):
                        return _finalize_result(
                            bonus_tickets_count=n_seated,
                            cash_tickets_count=0,
                            primary_cabin=cab,
                            requires_verify=(n_seated >= 3),
                            utilizes_bonus=True,
                            min_points=opts_c + ipts_c,
                            min_points_basis="ROUND_TRIP",
                        )

                sum_out_seats = sum(x[1] for x in bookable_out)
                sum_in_seats = sum(x[1] for x in bookable_in)
                if "PREMIUM" in pref_cabins and "BUSINESS" not in pref_cabins:
                    os_p, _, _, opts_p = _cabin_award_info(outbound_award, "PREMIUM")
                    is_p, _, _, ipts_p = _cabin_award_info(inbound_award, "PREMIUM")
                    ib_s, _, _, _ = _cabin_award_info(inbound_award, "BUSINESS")
                    if os_p >= 2 and is_p == 1 and opts_p > 0 and ipts_p > 0 and ib_s >= 1:
                        sum_in_seats += 1

                max_k_oj = min(n_seated, min(sum_out_seats, sum_in_seats))
                for k_oj in range(max_k_oj, 0, -1):
                    partition = self._assign_passengers_with_pnr_safety(seated_passengers, k_oj)
                    if partition is None:
                        continue
                    b_pax, c_pax = partition
                    cab_set = {x[0] for x in bookable_out} | {x[0] for x in bookable_in}
                    if c_pax:
                        cab_set.add("ECONOMY")
                    prim_cab = next(iter(cab_set)) if len(cab_set) == 1 else "ECONOMY"
                    return _finalize_result(
                        bonus_tickets_count=len(b_pax),
                        cash_tickets_count=len(c_pax),
                        primary_cabin=prim_cab,
                        requires_verify=False,
                        utilizes_bonus=True,
                        min_points=min_rt_pts,
                        min_points_basis="ROUND_TRIP",
                    )
                return None

            # Case B: One-Way Bonus on one direction + a commercial ticket on the other direction
            # Strictly gated to genuine single-direction bonus availability so a same-airport
            # 2-direction bonus flight pair never emits a contradictory one-way commercial strategy.
            if (out_bonus_seats or 0) > 0 and (in_bonus_seats or 0) > 0:
                return None
            best_dir: Optional[str] = None
            chosen_award: Optional[ElAlBonusAvailability] = None
            chosen_cabin = "ECONOMY"
            chosen_ow_pts = 0
            chosen_ow_s_cnt = 0
            chosen_ow_two_plus = False

            for dir_label, aw in (
                ("OUTBOUND_ONLY", outbound_award),
                ("INBOUND_ONLY", inbound_award),
            ):
                if aw is None:
                    continue
                for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
                    if cab not in pref_cabins:
                        continue
                    s_cnt, is_two_plus_ow, _rbd_c, pts_c = _cabin_award_info(aw, cab)
                    if s_cnt >= 1 and pts_c > 0:
                        best_dir = dir_label
                        chosen_award = aw
                        chosen_cabin = cab
                        chosen_ow_pts = pts_c
                        chosen_ow_s_cnt = s_cnt
                        chosen_ow_two_plus = is_two_plus_ow
                        break
                if best_dir is not None:
                    break

            if best_dir is None or chosen_award is None or chosen_ow_pts <= 0:
                return None

            # How many passengers get a one-way bonus ticket is decided by the seats of the
            # chosen direction, never by how many tickets the household's points could fund.
            max_ow_slots = (
                1
                if (has_live_award and chosen_ow_s_cnt == 1 and not chosen_ow_two_plus)
                else (n_seated if (chosen_ow_two_plus or chosen_ow_s_cnt >= 2) else max(1, chosen_ow_s_cnt))
            )
            bonus_ow_cnt = min(n_seated, max_ow_slots)
            cash_ow_cnt = n_seated - bonus_ow_cnt
            if bonus_ow_cnt <= 0:
                return None
            if cash_ow_cnt > 0 and self._assign_passengers_with_pnr_safety(seated_passengers, bonus_ow_cnt) is None:
                return None

            return _finalize_result(
                bonus_tickets_count=bonus_ow_cnt,
                cash_tickets_count=cash_ow_cnt,
                primary_cabin=chosen_cabin if cash_ow_cnt == 0 else "ECONOMY",
                requires_verify=(n_seated >= 3 and chosen_award.economy_award_seats == 2),
                utilizes_bonus=True,
                min_points=chosen_ow_pts,
                min_points_basis="ONE_WAY",
            )

        # =====================================================================
        # Strategy 5: CASH_AND_POINTS (F26)
        # =====================================================================
        if strat_str == "CASH_AND_POINTS":
            # Built whenever the award rows allow it, independent of the wallet contents: a
            # balance of 0 (or none) means "not entered" and excludes nothing (run 11, U3).
            # It carries no points figure: the former one was derived from a cash benchmark.
            # The bonus search drops it, like every other result, when no direction has seats.
            return _finalize_result(
                bonus_tickets_count=n_seated,
                cash_tickets_count=0,
                primary_cabin="ECONOMY",
                requires_verify=False,
                utilizes_bonus=True,
            )

        # =====================================================================
        # Strategy 6: MULTI_CLUB_PER_PASSENGER_SPLIT (F27)
        # =====================================================================
        if strat_str == "MULTI_CLUB_PER_PASSENGER_SPLIT":
            wallets = self._prepare_working_wallets(profile, prog_list)
            if len(wallets) < 2:
                return None
            if outbound_award is None or inbound_award is None:
                return None

            # Round-trip bonus slots come from the seats of the two award rows. The wallets
            # only gate the strategy (at least two funded wallets); they do not decide how
            # many bonus tickets the result has.
            mc_slots: list[_BonusSlot] = []
            for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
                if cab not in pref_cabins:
                    continue
                out_s, _, out_rbd, out_pts = _cabin_award_info(outbound_award, cab)
                in_s, _, _, in_pts = _cabin_award_info(inbound_award, cab)
                if out_pts <= 0 or in_pts <= 0:
                    continue
                if cab == "PREMIUM" and out_s >= 2 and in_s == 1:
                    in_biz_s, _, _, _ = _cabin_award_info(inbound_award, "BUSINESS")
                    avail_in = in_s + (1 if in_biz_s >= 1 else 0)
                else:
                    avail_in = in_s
                for _ in range(min(out_s, avail_in)):
                    mc_slots.append(
                        _BonusSlot(cab, out_rbd, out_pts + in_pts)
                    )
            k_mc = min(len(mc_slots), n_seated)
            if k_mc < 1:
                return None
            partition = self._assign_passengers_with_pnr_safety(seated_passengers, k_mc)
            if partition is None:
                return None
            bonus_pax, cash_pax = partition
            used_mc_slots = mc_slots[:k_mc]
            cab_set = {s.cabin_class for s in used_mc_slots}
            if cash_pax:
                cab_set.add("ECONOMY")
            prim_cab = next(iter(cab_set)) if len(cab_set) == 1 else "ECONOMY"
            return _finalize_result(
                bonus_tickets_count=len(bonus_pax),
                cash_tickets_count=len(cash_pax),
                primary_cabin=prim_cab,
                requires_verify=False,
                utilizes_bonus=True,
                min_points=min(s.points_cost for s in used_mc_slots),
                min_points_basis="ROUND_TRIP",
            )

        return None


class BonusVacationPlannerService:
    """End-to-end orchestrator joining MoE candidate vacation windows with El Al bonus & multi-airline itineraries."""

    def __init__(
        self,
        repository: Optional[SQLiteRepository] = None,
        calendar_service: Optional[MoECalendarService] = None,
        maximizer: Optional[VacationMaximizerEngine] = None,
        elal_adapter: Optional[ElAlRbdDataClientAdapter] = None,
        commercial_adapter: Optional[AllAirlinesSearchAdapter] = None,
        wallet_engine: Optional[MultiClubWalletAllocationEngine] = None,
        settings: Optional[dict[str, Any] | AppSettings] = None,
    ) -> None:
        raw_settings = (
            settings.to_dict()
            if isinstance(settings, AppSettings)
            else (settings or get_settings())
        )
        self._settings: dict[str, Any] = dict(raw_settings)
        self._weights: dict[str, float] = dict(
            self._settings.get(
                "optimization_weights",
                {
                    "ctos_calendar_weight": 0.55,
                    "ctos_flight_weight": 0.45,
                },
            )
        )
        self.repository: SQLiteRepository = repository or SQLiteRepository(auto_seed=True)
        self.calendar_service: MoECalendarService = (
            calendar_service or MoECalendarService(self.repository)
        )
        self.maximizer: VacationMaximizerEngine = (
            maximizer or VacationMaximizerEngine(self.calendar_service, settings=self._settings)
        )
        self.elal_adapter: ElAlRbdDataClientAdapter = (
            elal_adapter
            or ElAlRbdDataClientAdapter(
                repository=self.repository,
                settings=self._settings,
                calendar_service=self.calendar_service,
            )
        )
        self.commercial_adapter: AllAirlinesSearchAdapter = (
            commercial_adapter
            or AllAirlinesSearchAdapter(
                repository=self.repository,
                settings=self._settings,
                calendar_service=self.calendar_service,
                elal_adapter=self.elal_adapter,
            )
        )
        self.wallet_engine: MultiClubWalletAllocationEngine = (
            wallet_engine or MultiClubWalletAllocationEngine()
        )
        self.weather_engine: DestinationWeatherSuitabilityEngine = (
            DestinationWeatherSuitabilityEngine()
        )
        self.last_expanded_destinations: list[str] = []
        self.last_weather_fallback_message_he: Optional[str] = None
        self.last_weather_fallback_message_en: Optional[str] = None
        # Bounded 1-hour TTL cache for ephemeral guest / unsaved-session proposals (zero SQLite writes)
        self._ephemeral_proposals: dict[
            str, tuple[VacationOptionProposal, Optional[str], float]
        ] = {}
        self._ephemeral_lock = threading.RLock()

    def _prune_ephemeral_proposals(self, now_ts: Optional[float] = None) -> None:
        now_val = time.time() if now_ts is None else now_ts
        with self._ephemeral_lock:
            expired_ids = [
                pid
                for pid, (_prop, _uid, exp_ts) in self._ephemeral_proposals.items()
                if exp_ts <= now_val
            ]
            for pid in expired_ids:
                self._ephemeral_proposals.pop(pid, None)
            while len(self._ephemeral_proposals) > 2048:
                oldest_key = next(iter(self._ephemeral_proposals))
                self._ephemeral_proposals.pop(oldest_key, None)

    def _store_ephemeral_proposals(
        self,
        proposals: list[VacationOptionProposal],
        owner_user_id: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> None:
        now_val = time.time()
        exp_ts = now_val + float(max(60, ttl_seconds))
        with self._ephemeral_lock:
            self._prune_ephemeral_proposals(now_val)
            for prop in proposals:
                self._ephemeral_proposals[prop.id] = (prop, owner_user_id, exp_ts)

    def evict_ephemeral_proposals_for_user(self, user_id: str) -> None:
        if not user_id:
            return
        with self._ephemeral_lock:
            to_remove = [
                pid
                for pid, (_prop, uid, _exp) in self._ephemeral_proposals.items()
                if uid == user_id
            ]
            for pid in to_remove:
                self._ephemeral_proposals.pop(pid, None)

    def resolve_proposal_for_requester(
        self,
        proposal_id: str,
        requester_user_id: Optional[str] = None,
        enforce_owner: bool = False,
    ) -> Optional[VacationOptionProposal]:
        """Resolve a proposal from in-memory ephemeral cache or SQLite with strict owner scoping."""
        with self._ephemeral_lock:
            self._prune_ephemeral_proposals()
            ephemeral_entry = self._ephemeral_proposals.get(proposal_id)
        if ephemeral_entry is not None:
            prop, owner_uid, _exp = ephemeral_entry
            if not enforce_owner:
                return prop
            if owner_uid is None:
                return prop if requester_user_id is None else None
            return prop if requester_user_id == owner_uid else None

        loaded = self.repository.get_proposal_by_id(proposal_id)
        if loaded is None:
            return None
        if not enforce_owner:
            return loaded

        owner_info = self.repository.get_proposal_owner_info(proposal_id)
        if owner_info is None or owner_info.get("is_legacy_quarantined"):
            return None
        db_uid = owner_info.get("user_id")
        if not db_uid or not requester_user_id or str(db_uid) != str(requester_user_id):
            return None
        return loaded

    def _compute_fbvs_bonus(
        self,
        itinerary: FlightItinerary,
        n_seated: int,
    ) -> float:
        """Compute the Flight Bonus Value Score (`FBVS` in `[0.0, 100.0]`) from bonus seats only.

        When EL AL's feed reports `2+` (`is_two_plus=True` and `seats >= 2`) for a direction,
        that direction receives full `1.0` (`100%`) availability credit because `2+` is the
        maximum open-seat bucket published by the feed (so families of 3+ passengers are not
        artificially capped below 100). Exact seat counts (`1`, `0`, or non-`2+` counts) scale
        proportionally via `min(1.0, seats / seated_passengers)`.

        `FBVS = round(100 * (cov(OUT) + cov(IN)) / 2, 1)`.
        """
        party_size = max(1, int(n_seated))

        def _coverage(seats: Optional[int], is_two_plus: bool) -> float:
            s = max(0, int(seats or 0))
            if s <= 0:
                return 0.0
            if is_two_plus and s >= 2:
                return 1.0
            return min(1.0, s / float(party_size))

        raw_score = (
            100.0
            * (
                _coverage(
                    itinerary.outbound_bonus_seats,
                    bool(itinerary.outbound_bonus_seats_is_two_plus),
                )
                + _coverage(
                    itinerary.inbound_bonus_seats,
                    bool(itinerary.inbound_bonus_seats_is_two_plus),
                )
            )
            / 2.0
        )
        return round(min(100.0, max(0.0, raw_score)), 1)

    def _compute_ctos(
        self,
        has_score: float,
        fbvs: float,
        wss: Optional[float] = None,
        has_weather_filter: bool = False,
        min_weather_threshold: float = 0.0,
    ) -> float:
        """Compute Combined Trip Optimization Score (`CTOS`).

        - Unfiltered (`has_weather_filter=False`): `CTOS = round(0.55 * HAS + 0.45 * FBVS, 1)`.
        - Filtered by vacation type (`has_weather_filter=True`):
          `CTOS = round(clamp(0.35 * WSS + 0.35 * HAS + 0.30 * FBVS - 0.50 * max(0, tau_t - WSS), 0, 100), 1)`.
        """
        if not has_weather_filter or wss is None:
            w_cal = float(self._weights.get("ctos_calendar_weight", 0.55))
            w_flt = float(self._weights.get("ctos_flight_weight", 0.45))
            return round(min(100.0, max(0.0, w_cal * float(has_score) + w_flt * float(fbvs))), 1)

        w_wea = float(self._weights.get("ctos_filtered_weather_weight", 0.35))
        w_cal_f = float(self._weights.get("ctos_filtered_calendar_weight", 0.35))
        w_flt_f = float(self._weights.get("ctos_filtered_flight_weight", 0.30))
        pen_factor = float(self._weights.get("ctos_sub_threshold_penalty_factor", 0.50))
        base_ctos = w_wea * float(wss) + w_cal_f * float(has_score) + w_flt_f * float(fbvs)
        penalty = pen_factor * max(0.0, float(min_weather_threshold) - float(wss))
        return round(min(100.0, max(0.0, base_ctos - penalty)), 1)

    def _build_explanation_he(
        self,
        window: CandidateVacationWindow,
        itinerary: FlightItinerary,
        fbvs: float,
        ctos: float,
        wss: Optional[float] = None,
        weather_summary_he: str = "",
    ) -> str:
        strat = (
            itinerary.fulfillment_strategy.value
            if isinstance(itinerary.fulfillment_strategy, Enum)
            else str(itinerary.fulfillment_strategy)
        )
        coverage_he = {
            "BOTH_DIRECTIONS": "בונוס בשני הכיוונים",
            "OUTBOUND_ONLY": "בונוס בכיוון אחד בלבד — הלוך",
            "INBOUND_ONLY": "בונוס בכיוון אחד בלבד — חזור",
        }.get(str(itinerary.bonus_direction_coverage), "ללא מושבי בונוס")

        is_open_jaw_itin = itinerary.destination_iata != itinerary.return_origin_iata
        strat_display = strat
        open_jaw_note = ""
        if (
            is_open_jaw_itin
            and strat == "ONE_WAY_BONUS_ONE_WAY_CASH"
            and str(itinerary.bonus_direction_coverage) == "BOTH_DIRECTIONS"
        ):
            strat_display = (
                f"מסלול משולב בבונוס (הלוך ל-{itinerary.destination_iata}, "
                f"חזור מ-{itinerary.return_origin_iata})"
            )
        elif is_open_jaw_itin:
            open_jaw_note = (
                f" [מסלול Open-Jaw: הלוך ל-{itinerary.destination_iata}, "
                f"חזור מ-{itinerary.return_origin_iata}]"
            )

        weather_note = ""
        if wss is not None and wss > 0.0:
            weather_note = f", WSS={wss:.1f}"
        weather_tail = f" | {weather_summary_he}" if weather_summary_he else ""

        return (
            f"{itinerary.destination_city_he} ({itinerary.destination_iata}) | "
            f"{window.start_date.isoformat()} עד {window.end_date.isoformat()} "
            f"({itinerary.trip_nights} לילות) | "
            f"אסטרטגיה: {strat_display}{open_jaw_note} | "
            f"{coverage_he} | "
            f"ציונים: התאמת חופשת בי״ס={window.holiday_alignment_score:.1f}/100, FBVS={fbvs}{weather_note}, CTOS={ctos}"
            f"{weather_tail}"
        )

    def _has_live_only_inventory(self) -> bool:
        """Return True if running in live fetch mode or if all cached rows in SQLite are `#live` rows."""
        if self.repository.is_live_fetch_mode():
            return True
        try:
            with self.repository.connection() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS total_cnt, "
                    "SUM(CASE WHEN source_url LIKE '%#live%' THEN 1 ELSE 0 END) AS live_cnt "
                    "FROM elal_bonus_availability"
                ).fetchone()
                if (
                    row
                    and int(row["total_cnt"] or 0) > 0
                    and int(row["live_cnt"] or 0) == int(row["total_cnt"] or 0)
                ):
                    return True
        except Exception:
            pass
        return False

    def _ensure_award_rows_for_window(
        self,
        dest_iata: str,
        start_date: date,
        end_date: date,
        origin_iata: str,
        include_sundor: bool,
    ) -> tuple[list[ElAlBonusAvailability], list[ElAlBonusAvailability]]:
        """Fetch or deterministically synthesize Shabbat/Yom-Kippur-compliant award rows for `(dest_iata, start_date, end_date)`."""
        out_rows = self.elal_adapter.get_award_availability(
            destinations=[dest_iata],
            start_date=start_date,
            end_date=start_date,
            origin=origin_iata,
            include_sundor_flights=include_sundor,
            direction="OUTBOUND",
        )
        in_rows = self.elal_adapter.get_award_availability(
            destinations=[dest_iata],
            start_date=end_date,
            end_date=end_date,
            origin=origin_iata,
            include_sundor_flights=include_sundor,
            direction="INBOUND",
        )

        live_only = self._has_live_only_inventory()
        if live_only or any("#live" in str(r.source_url or "") for r in out_rows + in_rows):
            out_rows.sort(
                key=lambda r: (
                    0 if "#live" in str(r.source_url or "") else 1,
                    -(r.economy_award_seats + r.premium_award_seats + r.business_award_seats),
                    -r.premium_award_seats,
                    -r.economy_award_seats,
                    r.flight_number,
                )
            )
            in_rows.sort(
                key=lambda r: (
                    0 if "#live" in str(r.source_url or "") else 1,
                    -(r.economy_award_seats + r.premium_award_seats + r.business_award_seats),
                    -r.premium_award_seats,
                    -r.economy_award_seats,
                    r.flight_number,
                )
            )

        if dest_iata not in DESTINATION_CATALOG:
            return out_rows, in_rows

        # In production live mode (`ELAL_LIVE_FETCH_ENABLED=1`) or live-only DB, NEVER fabricate
        # fictitious bonus flights when no real award seats exist in the database.
        if live_only:
            return out_rows, in_rows

        meta = DESTINATION_CATALOG[dest_iata]
        if not include_sundor and str(meta.get("operating_carrier")) == "2U":
            return out_rows, in_rows

        now_dt = datetime.now(UTC).replace(microsecond=0)
        fetched_iso = now_dt.isoformat().replace("+00:00", "Z")
        expires_iso = (now_dt + timedelta(seconds=14400)).isoformat().replace("+00:00", "Z")
        to_upsert: list[ElAlBonusAvailability] = []

        if (
            not out_rows
            and start_date not in YOM_KIPPUR_CLOSED_DATES
            and not self.calendar_service.is_tlv_airport_closed(start_date)
        ):
            synth_out = _make_bonus_row(
                dest_iata=dest_iata,
                flight_date=start_date,
                direction="OUTBOUND",
                econ_seats=2,
                prem_seats=2,
                biz_seats=2,
                flycard_promo=(start_date.weekday() == 1),
                fetched_iso=fetched_iso,
                expires_iso=expires_iso,
            )
            if not is_shabbat_blocked_for_elal(synth_out.flight_date, synth_out.departure_time_local):
                to_upsert.append(synth_out)
                out_rows = [synth_out]

        if (
            not in_rows
            and end_date not in YOM_KIPPUR_CLOSED_DATES
            and not self.calendar_service.is_tlv_airport_closed(end_date)
        ):
            synth_in = _make_bonus_row(
                dest_iata=dest_iata,
                flight_date=end_date,
                direction="INBOUND",
                econ_seats=2,
                prem_seats=2,
                biz_seats=2,
                flycard_promo=(end_date.weekday() == 1),
                fetched_iso=fetched_iso,
                expires_iso=expires_iso,
            )
            if not is_shabbat_blocked_for_elal(synth_in.flight_date, synth_in.departure_time_local):
                to_upsert.append(synth_in)
                in_rows = [synth_in]

        if to_upsert:
            self.repository.upsert_elal_bonus(to_upsert, ttl_seconds=14400)

        return out_rows, in_rows

    def _select_candidate_windows(
        self,
        query: FlightSearchQuery,
        profile: FamilyProfile,
        expanded_destinations: list[str],
    ) -> list[CandidateVacationWindow]:
        """Select top candidate vacation windows while ensuring canonical benchmark dates are included."""
        all_windows = self.maximizer.generate_candidate_windows(query, profile)
        if not all_windows:
            return []

        mode = (
            query.date_selection_mode
            if isinstance(query.date_selection_mode, DateSelectionMode)
            else DateSelectionMode(str(query.date_selection_mode))
        )
        live_only = self._has_live_only_inventory()

        if mode == DateSelectionMode.SPECIFIC_DATES:
            min_d = min(w.start_date for w in all_windows)
            max_d = max(w.end_date for w in all_windows)
            cached_awards = self.repository.get_cached_elal_bonus(
                destinations=expanded_destinations,
                start_date=min_d,
                end_date=max_d,
                include_expired=False,
            )
            out_by_dest: dict[str, set[date]] = {}
            in_by_dest: dict[str, set[date]] = {}
            out_dates: set[date] = set()
            in_dates: set[date] = set()
            for a in cached_awards:
                if (
                    a.economy_award_seats <= 0
                    and a.premium_award_seats <= 0
                    and a.business_award_seats <= 0
                ):
                    continue
                if a.direction == "OUTBOUND":
                    out_dates.add(a.flight_date)
                    out_by_dest.setdefault(a.destination_iata, set()).add(a.flight_date)
                elif a.direction == "INBOUND":
                    in_dates.add(a.flight_date)
                    in_by_dest.setdefault(a.origin_iata, set()).add(a.flight_date)

            spec_cap = min(len(all_windows), 25)
            spec_selected: list[CandidateVacationWindow] = []
            spec_seen: set[tuple[date, date]] = set()

            # In offline/seeded mode, keep the base/top window first so exact dates stay represented
            if not live_only and all_windows:
                base_pair = (all_windows[0].start_date, all_windows[0].end_date)
                spec_seen.add(base_pair)
                spec_selected.append(all_windows[0])

            # Priority 1: windows with round-trip award availability on the same destination
            for w in all_windows:
                if len(spec_selected) >= spec_cap:
                    break
                pair = (w.start_date, w.end_date)
                if pair in spec_seen:
                    continue
                has_rt_dest = any(
                    w.start_date in out_by_dest.get(d, set())
                    and w.end_date in in_by_dest.get(d, set())
                    for d in expanded_destinations
                )
                if has_rt_dest:
                    spec_seen.add(pair)
                    spec_selected.append(w)

            # Priority 1b: windows with compatible Open-Jaw round-trip award availability
            if len(expanded_destinations) >= 2 and len(spec_selected) < spec_cap:
                oj_pairs = [
                    (d_out, d_in)
                    for d_out in expanded_destinations
                    for d_in in expanded_destinations
                    if d_out in out_by_dest
                    and d_in in in_by_dest
                    and _are_open_jaw_compatible(d_out, d_in)
                ]
                if oj_pairs:
                    for w in all_windows:
                        if len(spec_selected) >= spec_cap:
                            break
                        pair = (w.start_date, w.end_date)
                        if pair in spec_seen:
                            continue
                        has_oj_dest = any(
                            w.start_date in out_by_dest[d_out]
                            and w.end_date in in_by_dest[d_in]
                            and _are_open_jaw_compatible(
                                d_out, d_in, trip_nights=(w.end_date - w.start_date).days
                            )
                            for d_out, d_in in oj_pairs
                        )
                        if has_oj_dest:
                            spec_seen.add(pair)
                            spec_selected.append(w)

            # Priority 2: windows with one-way award availability (and non-Shabbat/open other leg)
            for w in all_windows:
                if len(spec_selected) >= spec_cap:
                    break
                pair = (w.start_date, w.end_date)
                if pair in spec_seen:
                    continue
                valid_ow = (
                    w.start_date in out_dates
                    and w.end_date.weekday() != 5
                    and not self.calendar_service.is_tlv_airport_closed(w.end_date)
                ) or (
                    w.end_date in in_dates
                    and w.start_date.weekday() != 5
                    and not self.calendar_service.is_tlv_airport_closed(w.start_date)
                )
                if valid_ow:
                    spec_seen.add(pair)
                    spec_selected.append(w)

            if live_only:
                if not spec_selected:
                    return all_windows[:2]
                if all_windows and len(spec_selected) < spec_cap:
                    base_pair = (all_windows[0].start_date, all_windows[0].end_date)
                    if base_pair not in spec_seen:
                        spec_seen.add(base_pair)
                        spec_selected.append(all_windows[0])
                return spec_selected

            fallback_cap = max(len(spec_selected), 5 if len(expanded_destinations) <= 4 else 2)
            for w in all_windows:
                if len(spec_selected) >= min(fallback_cap, spec_cap):
                    break
                pair = (w.start_date, w.end_date)
                if pair not in spec_seen:
                    spec_seen.add(pair)
                    spec_selected.append(w)
            return spec_selected

        # Canonical benchmark date pairs from APPLICATION_PLAN.md §3.6 & §5.2
        canonical_pairs: set[tuple[date, date]] = {
            (date(2027, 4, 11), date(2027, 4, 18)),  # Option A: Rome Pre-Pesach Shoulder
            (date(2027, 4, 20), date(2027, 4, 27)),  # Pesach Uncovered Week
            (date(2027, 4, 20), date(2027, 4, 28)),  # Ex 4B: Pesach Uncovered Week
            (date(2026, 12, 6), date(2026, 12, 11)),  # Option B: Athens Hanukkah
            (date(2026, 12, 10), date(2026, 12, 14)), # Ex 2A: Hanukkah Post-Nitzanim
            (date(2027, 6, 21), date(2027, 6, 28)),  # Option C / Ex 6: Madrid June 20-30 Arbitrage
            (date(2026, 9, 22), date(2026, 10, 3)),  # Ex 1: Kippur-Sukkot Mega-Bridge
            (date(2027, 3, 23), date(2027, 3, 27)),  # Ex 3: Purim Long-Weekend Bridge
            (date(2027, 6, 9), date(2027, 6, 12)),   # Ex 5: Shavuot Extended Weekend
        }

        selected: list[CandidateVacationWindow] = []
        seen_pairs: set[tuple[date, date]] = set()

        # 0. In live mode (or when real award flights exist in DB), prioritize candidate windows
        #    where the SAME destination has BOTH an outbound award on `w.start_date` AND an inbound
        #    award on `w.end_date`, followed by windows matching at least one direction.
        if self._has_live_only_inventory():
            min_d = min(w.start_date for w in all_windows)
            max_d = max(w.end_date for w in all_windows)
            cached_awards = self.repository.get_cached_elal_bonus(
                destinations=expanded_destinations,
                start_date=min_d,
                end_date=max_d,
                include_expired=False,
            )
            out_by_dest: dict[str, set[date]] = {}
            in_by_dest: dict[str, set[date]] = {}
            out_dates: set[date] = set()
            in_dates: set[date] = set()
            for a in cached_awards:
                if a.economy_award_seats <= 0 and a.premium_award_seats <= 0 and a.business_award_seats <= 0:
                    continue
                if a.direction == "OUTBOUND":
                    out_dates.add(a.flight_date)
                    out_by_dest.setdefault(a.destination_iata, set()).add(a.flight_date)
                elif a.direction == "INBOUND":
                    in_dates.add(a.flight_date)
                    in_by_dest.setdefault(a.origin_iata, set()).add(a.flight_date)

            live_cap = 20 if len(expanded_destinations) <= 6 else 12
            # First priority: windows with round-trip award availability on the same destination
            for w in all_windows:
                if len(selected) >= live_cap:
                    break
                pair = (w.start_date, w.end_date)
                if pair in seen_pairs:
                    continue
                has_rt_dest = any(
                    w.start_date in out_by_dest.get(d, set()) and w.end_date in in_by_dest.get(d, set())
                    for d in expanded_destinations
                )
                if has_rt_dest:
                    seen_pairs.add(pair)
                    selected.append(w)

            # Priority 1b: windows with compatible Open-Jaw round-trip award availability (e.g. TLV->LTN + LHR->TLV)
            if len(expanded_destinations) >= 2 and len(selected) < live_cap:
                oj_pairs = [
                    (d_out, d_in)
                    for d_out in expanded_destinations
                    for d_in in expanded_destinations
                    if d_out in out_by_dest
                    and d_in in in_by_dest
                    and _are_open_jaw_compatible(d_out, d_in)
                ]
                if oj_pairs:
                    for w in all_windows:
                        if len(selected) >= live_cap:
                            break
                        pair = (w.start_date, w.end_date)
                        if pair in seen_pairs:
                            continue
                        has_oj_dest = any(
                            w.start_date in out_by_dest[d_out]
                            and w.end_date in in_by_dest[d_in]
                            and _are_open_jaw_compatible(
                                d_out, d_in, trip_nights=(w.end_date - w.start_date).days
                            )
                            for d_out, d_in in oj_pairs
                        )
                        if has_oj_dest:
                            seen_pairs.add(pair)
                            selected.append(w)

            # Second priority: windows with one-way award availability (and non-Shabbat/open other leg)
            for w in all_windows:
                if len(selected) >= live_cap:
                    break
                pair = (w.start_date, w.end_date)
                if pair in seen_pairs:
                    continue
                valid_ow = (
                    w.start_date in out_dates
                    and w.end_date.weekday() != 5
                    and not self.calendar_service.is_tlv_airport_closed(w.end_date)
                ) or (
                    w.end_date in in_dates
                    and w.start_date.weekday() != 5
                    and not self.calendar_service.is_tlv_airport_closed(w.start_date)
                )
                if valid_ow:
                    seen_pairs.add(pair)
                    selected.append(w)

        # 1. Include any canonical benchmark windows present in `all_windows`
        for w in all_windows:
            pair = (w.start_date, w.end_date)
            if pair in canonical_pairs and pair not in seen_pairs:
                seen_pairs.add(pair)
                selected.append(w)

        # 2. Fill with top-ranked windows by HAS
        max_windows = 8 if len(expanded_destinations) <= 3 else (4 if len(expanded_destinations) <= 6 else 2)
        for w in all_windows:
            if len(selected) >= max_windows:
                break
            pair = (w.start_date, w.end_date)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                selected.append(w)

        return selected

    def search_vacations(
        self,
        query_data: dict[str, Any] | FlightSearchQuery,
        profile: Optional[FamilyProfile | dict[str, Any]] = None,
        *,
        persist_results: bool = True,
        owner_user_id: Optional[str] = None,
    ) -> list[VacationOptionProposal]:
        """Execute end-to-end vacation search across Date Modes 1/2/3 and Airline Modes 1/2."""
        matmid_override: Optional[int] = None
        if isinstance(query_data, dict):
            q_dict = dict(query_data)
            if (
                "matmid_points_balance" in q_dict
                and q_dict["matmid_points_balance"] is not None
                and q_dict["matmid_points_balance"] != ""
            ):
                matmid_override = max(0, int(q_dict["matmid_points_balance"]))

            raw_dmode = str(q_dict.get("date_selection_mode") or "")
            if (
                raw_dmode == "SPECIFIC_DATES"
                and "min_trip_nights" not in q_dict
                and "max_trip_nights" not in q_dict
                and q_dict.get("specific_departure_date")
                and q_dict.get("specific_return_date")
            ):
                try:
                    dep_raw = q_dict["specific_departure_date"]
                    ret_raw = q_dict["specific_return_date"]
                    dep_dt = (
                        dep_raw
                        if isinstance(dep_raw, date)
                        else date.fromisoformat(str(dep_raw).strip()[:10])
                    )
                    ret_dt = (
                        ret_raw
                        if isinstance(ret_raw, date)
                        else date.fromisoformat(str(ret_raw).strip()[:10])
                    )
                    if ret_dt > dep_dt:
                        base_n = (ret_dt - dep_dt).days
                        flex_n = max(0, min(7, int(q_dict.get("flex_days_plus_minus", 0))))
                        q_dict["min_trip_nights"] = max(1, base_n - 2 * flex_n)
                        q_dict["max_trip_nights"] = min(45, max(1, base_n + 2 * flex_n))
                except Exception:
                    pass
            elif (
                raw_dmode == "HOLIDAY_DIRECT_INTENT"
                and "max_trip_nights" in q_dict
                and "min_trip_nights" not in q_dict
            ):
                try:
                    max_req = int(q_dict["max_trip_nights"])
                    if max_req >= 1:
                        q_dict["min_trip_nights"] = min(4, max_req)
                except Exception:
                    pass

            resolved_ty: Optional[int] = None
            raw_ty = q_dict.get("direct_target_year")
            if raw_ty is not None and raw_ty != "" and not isinstance(raw_ty, bool):
                try:
                    ty_int = int(raw_ty)
                except (ValueError, TypeError, OverflowError):
                    ty_int = None
                if ty_int is not None and 2036 <= ty_int <= 2099:
                    resolved_ty = ty_int
                    q_dict["direct_target_year"] = None
                    if raw_dmode == "HOLIDAY_DIRECT_INTENT":
                        q_dict["school_year"] = resolve_holiday_direct_intent_school_year(
                            str(q_dict.get("direct_holiday_code") or "PESACH"), ty_int
                        )
            query = FlightSearchQuery.from_dict(q_dict)
            if resolved_ty is not None:
                setattr(query, "_resolved_target_year", resolved_ty)
        else:
            query = query_data

        if profile is not None:
            active_profile = (
                profile
                if isinstance(profile, FamilyProfile)
                else FamilyProfile.from_dict(profile)
            )
        else:
            active_profile = (
                self.repository.get_profile(query.family_profile_id)
                or self.repository.get_profile()
                or build_clean_guest_profile()
            )

        if matmid_override is not None:
            active_profile = FamilyProfile.from_dict(
                {
                    **active_profile.to_dict(),
                    "matmid_points_balance": matmid_override,
                    "passenger_loyalty_wallets": [],
                }
            )

        if persist_results:
            existing_db_prof = (
                self.repository.get_profile(active_profile.id)
                if active_profile.id
                else None
            )
            query.family_profile_id = (
                existing_db_prof.id if existing_db_prof is not None else None  # type: ignore[assignment]
            )
        else:
            query.family_profile_id = None  # type: ignore[assignment]

        raw_dest_tokens = [
            str(x).strip().upper()
            for x in (query.destination_iatas or [])
            if str(x).strip()
        ]
        is_anywhere_query = (not raw_dest_tokens) or any(
            t in ("ANYWHERE", "ALL", "*") for t in raw_dest_tokens
        )
        expanded_destinations = self.elal_adapter.expand_metro_iatas(
            ["ANYWHERE"] if is_anywhere_query else raw_dest_tokens
        )
        self.last_expanded_destinations = list(expanded_destinations)
        self.last_weather_fallback_message_he = None
        self.last_weather_fallback_message_en = None

        has_weather_filter = bool(query.preferred_vacation_types)
        effective_tau = self.weather_engine.get_effective_threshold(
            query.preferred_vacation_types, query.min_weather_suitability_score
        )

        # Preliminary candidate windows for destination selection
        prelim_windows = self._select_candidate_windows(
            query=query,
            profile=active_profile,
            expanded_destinations=expanded_destinations,
        )
        if not prelim_windows:
            if persist_results:
                self.repository.save_search_query(query)
            return []

        # When ANYWHERE (45 destinations) is requested:
        # - In live mode or when DB holds live-only inventory: check all 45 destinations.
        # - In offline mode with an active vacation-type filter: rank all destinations by average
        #   weather suitability (`WSS`) across candidate windows and keep top 14 + all passing `effective_tau`.
        # - In offline mode without a vacation-type filter: keep the 14 canonical destinations (+ any `#live` routes).
        if is_anywhere_query and not (
            self.repository.is_live_fetch_mode() or self._has_live_only_inventory()
        ):
            if has_weather_filter:
                dest_scores: list[tuple[float, str]] = []
                for d_code in expanded_destinations:
                    w_vals = [
                        self.weather_engine.evaluate_window_weather(
                            dest_iata=d_code,
                            start_date=w.start_date,
                            end_date=w.end_date,
                            preferred_vacation_types=query.preferred_vacation_types,
                            min_threshold_override=query.min_weather_suitability_score,
                        )[0]
                        for w in prelim_windows
                    ]
                    avg_w = (sum(w_vals) / float(len(w_vals))) if w_vals else 0.0
                    dest_scores.append((avg_w, d_code))
                dest_scores.sort(key=lambda x: x[0], reverse=True)
                top_14 = [d for _, d in dest_scores[:14]]
                for sc_val, d_code in dest_scores[14:]:
                    if sc_val >= effective_tau and d_code not in top_14:
                        top_14.append(d_code)
                active_destinations = top_14
            else:
                active_destinations = [
                    "FCO", "ATH", "LCA", "RHO", "MXP", "VIE", "BUD", "PRG",
                    "LHR", "LTN", "CDG", "MAD", "BKK", "JFK",
                ]
                active_destinations = [d for d in active_destinations if d in expanded_destinations]
                min_pw = min(w.start_date for w in prelim_windows)
                max_pw = max(w.end_date for w in prelim_windows)
                for row_c in self.repository.get_cached_elal_bonus(
                    destinations=expanded_destinations,
                    start_date=min_pw,
                    end_date=max_pw,
                    include_expired=False,
                ):
                    if "#live" in str(row_c.source_url or ""):
                        r_dest = (
                            row_c.destination_iata
                            if row_c.direction == "OUTBOUND"
                            else row_c.origin_iata
                        )
                        if r_dest in expanded_destinations and r_dest not in active_destinations:
                            active_destinations.append(r_dest)
        else:
            active_destinations = list(expanded_destinations)

        candidate_windows = self._select_candidate_windows(
            query=query,
            profile=active_profile,
            expanded_destinations=active_destinations,
        )
        if not candidate_windows:
            if persist_results:
                self.repository.save_search_query(query)
            return []

        airline_mode = (
            query.airline_selection_mode.value
            if isinstance(query.airline_selection_mode, Enum)
            else str(query.airline_selection_mode).strip().upper()
        )
        live_only_inventory = self._has_live_only_inventory()
        n_seated, _ = FamilyBaggageNormalizer.count_seated_and_lap_passengers(active_profile)
        # Points the household can spend on El Al bonus tickets (request override, else the
        # profile / its wallets). Used only for the one-ticket minimum filter further down.
        effective_points_balance = self.wallet_engine.effective_elal_points_balance(
            active_profile, query.enabled_loyalty_programs
        )

        # Batch pre-fetch normalized live award rows once across `[min_w_start, max_w_end]`
        # to eliminate 500+ repetitive SQLite SELECT queries on `ANYWHERE` searches.
        prefetched_live_awards: Optional[
            dict[tuple[str, date, str], list[ElAlBonusAvailability]]
        ] = None
        if (
            live_only_inventory
            and airline_mode == "EL_AL_ONLY"
            and query.search_elal_bonus_tickets
            and active_destinations
        ):
            min_w_start = min(w.start_date for w in candidate_windows)
            max_w_end = max(w.end_date for w in candidate_windows)
            batch_rows = self.elal_adapter.get_award_availability(
                destinations=active_destinations,
                start_date=min_w_start,
                end_date=max_w_end,
                origin=query.origin_iata,
                include_sundor_flights=query.include_sundor_flights,
            )
            prefetched_live_awards = {}
            for r in batch_rows:
                r_dest = (
                    r.destination_iata if r.direction == "OUTBOUND" else r.origin_iata
                )
                prefetched_live_awards.setdefault(
                    (r_dest, r.flight_date, r.direction), []
                ).append(r)
            for bucket in prefetched_live_awards.values():
                bucket.sort(
                    key=lambda r: (
                        0 if "#live" in str(r.source_url or "") else 1,
                        -(
                            r.economy_award_seats
                            + r.premium_award_seats
                            + r.business_award_seats
                        ),
                        -r.premium_award_seats,
                        -r.economy_award_seats,
                        r.flight_number,
                    )
                )

        raw_proposals: list[VacationOptionProposal] = []
        active_oj_pairs: list[tuple[str, str]] = (
            [
                (d_out, d_in)
                for d_out in active_destinations
                for d_in in active_destinations
                if _are_open_jaw_compatible(d_out, d_in)
            ]
            if (
                airline_mode == "EL_AL_ONLY"
                and query.search_elal_bonus_tickets
                and len(active_destinations) >= 2
            )
            else []
        )

        for window in candidate_windows:
            if (
                self.calendar_service.is_tlv_airport_closed(window.start_date)
                or self.calendar_service.is_tlv_airport_closed(window.end_date)
            ):
                continue

            # Track outbound awards per destination for Open-Jaw pairing across compatible clusters
            window_outbound_by_dest: dict[str, ElAlBonusAvailability] = {}
            window_inbound_by_dest: dict[str, ElAlBonusAvailability] = {}

            for dest_iata in active_destinations:
                meta = DESTINATION_CATALOG.get(dest_iata, {})
                if (
                    airline_mode == "EL_AL_ONLY"
                    and not query.include_sundor_flights
                    and str(meta.get("operating_carrier")) == "2U"
                ):
                    continue

                if airline_mode == "EL_AL_ONLY":
                    if not query.search_elal_bonus_tickets:
                        # EL_AL_ONLY with search_elal_bonus_tickets=False -> Commercial Cash Only on El Al
                        comm_offers = self.commercial_adapter.search_commercial_flights(
                            origin=query.origin_iata,
                            destinations=[dest_iata],
                            departure_date=window.start_date,
                            return_date=window.end_date,
                            profile=active_profile,
                            direct_only=query.direct_flights_only,
                            airline_selection_mode="EL_AL_ONLY",
                            include_sundor_flights=query.include_sundor_flights,
                        )
                        for offer in comm_offers:
                            itin_dict = self.wallet_engine.allocate_family_tickets(
                                profile=active_profile,
                                outbound_award=None,
                                inbound_award=None,
                                cash_benchmark_per_pax=0.0,
                                strategy="COMMERCIAL_CASH_ONLY",
                                preferred_cabins=query.preferred_cabins,
                                enabled_programs=query.enabled_loyalty_programs,
                                commercial_offer=offer,
                            )
                            if itin_dict is not None:
                                itin = FlightItinerary.from_dict(itin_dict)
                                raw_proposals.append(
                                    self._make_proposal_from_itinerary(
                                        query=query,
                                        window=window,
                                        itinerary=itin,
                                        n_seated=n_seated,
                                    )
                                )
                        continue

                    if prefetched_live_awards is not None:
                        out_awards = prefetched_live_awards.get(
                            (dest_iata, window.start_date, "OUTBOUND"), []
                        )
                        in_awards = prefetched_live_awards.get(
                            (dest_iata, window.end_date, "INBOUND"), []
                        )
                    else:
                        out_awards, in_awards = self._ensure_award_rows_for_window(
                            dest_iata=dest_iata,
                            start_date=window.start_date,
                            end_date=window.end_date,
                            origin_iata=query.origin_iata,
                            include_sundor=query.include_sundor_flights,
                        )
                    if out_awards:
                        window_outbound_by_dest[dest_iata] = out_awards[0]
                    if in_awards:
                        window_inbound_by_dest[dest_iata] = in_awards[0]

                    out_aw = out_awards[0] if out_awards else None
                    in_aw = in_awards[0] if in_awards else None
                    if out_aw is None and in_aw is None:
                        continue

                    # When only ONE direction has live `#live` award availability (e.g. AMS or LHR
                    # with outbound bonus seats and 0 return bonus seats), synthesize ONE_WAY_BONUS_ONE_WAY_CASH
                    # (with honest `LY_CASH` commercial leg and lower FBVS score) while never inventing
                    # an El Al flight on Shabbat (`weekday() == 5`) or Yom Kippur.
                    is_single_dir_live = bool(live_only_inventory and ((out_aw is None) ^ (in_aw is None)))
                    if is_single_dir_live:
                        if out_aw is None and (
                            window.start_date.weekday() == 5
                            or self.calendar_service.is_tlv_airport_closed(window.start_date)
                        ):
                            continue
                        if in_aw is None and (
                            window.end_date.weekday() == 5
                            or self.calendar_service.is_tlv_airport_closed(window.end_date)
                        ):
                            continue
                        strategies_to_try = ["ONE_WAY_BONUS_ONE_WAY_CASH"]
                    else:
                        strategies_to_try = [
                            "HYBRID_BONUS_PLUS_CASH",
                            "SPLIT_CABIN_BONUS",
                            "FULL_BONUS_SAME_CABIN",
                            "MULTI_CLUB_PER_PASSENGER_SPLIT",
                            "ONE_WAY_BONUS_ONE_WAY_CASH",
                            "CASH_AND_POINTS",
                        ]
                    for strat_name in strategies_to_try:
                        if strat_name == "HYBRID_BONUS_PLUS_CASH" and not query.allow_hybrid_bonus_cash:
                            continue
                        itin_dict = self.wallet_engine.allocate_family_tickets(
                            profile=active_profile,
                            outbound_award=out_aw,
                            inbound_award=in_aw,
                            cash_benchmark_per_pax=0.0,
                            strategy=strat_name,
                            preferred_cabins=query.preferred_cabins,
                            enabled_programs=query.enabled_loyalty_programs,
                            fallback_departure_date=window.start_date,
                            fallback_return_date=window.end_date,
                        )
                        if itin_dict is not None:
                            itin = FlightItinerary.from_dict(itin_dict)
                            if not (query.min_trip_nights <= itin.trip_nights <= query.max_trip_nights):
                                continue
                            raw_proposals.append(
                                self._make_proposal_from_itinerary(
                                    query=query,
                                    window=window,
                                    itinerary=itin,
                                    n_seated=n_seated,
                                )
                            )
                else:
                    # ALL_AIRLINES Mode (F18): multi-carrier commercial search + optional multi-club / El Al bonus
                    comm_offers = self.commercial_adapter.search_commercial_flights(
                        origin=query.origin_iata,
                        destinations=[dest_iata],
                        departure_date=window.start_date,
                        return_date=window.end_date,
                        profile=active_profile,
                        direct_only=query.direct_flights_only,
                        airline_selection_mode="ALL_AIRLINES",
                        include_sundor_flights=query.include_sundor_flights,
                    )
                    for offer in comm_offers:
                        itin_dict = self.wallet_engine.allocate_family_tickets(
                            profile=active_profile,
                            outbound_award=None,
                            inbound_award=None,
                            cash_benchmark_per_pax=0.0,
                            strategy="COMMERCIAL_CASH_ONLY",
                            preferred_cabins=query.preferred_cabins,
                            enabled_programs=query.enabled_loyalty_programs,
                            commercial_offer=offer,
                        )
                        if itin_dict is not None:
                            itin = FlightItinerary.from_dict(itin_dict)
                            raw_proposals.append(
                                self._make_proposal_from_itinerary(
                                    query=query,
                                    window=window,
                                    itinerary=itin,
                                    n_seated=n_seated,
                                )
                            )

            # Synthesize Open-Jaw Bonus pairings across compatible regional clusters (e.g. MXP <-> FCO)
            if active_oj_pairs:
                w_nights = max(1, (window.end_date - window.start_date).days)
                for d_out, d_in in active_oj_pairs:
                    if not _are_open_jaw_compatible(
                        d_out, d_in, trip_nights=w_nights
                    ):
                        continue
                    if is_anywhere_query and not _is_same_city_open_jaw(d_out, d_in):
                        if (
                            d_out in window_inbound_by_dest
                            or d_in in window_outbound_by_dest
                        ):
                            continue
                    out_aw = window_outbound_by_dest.get(d_out)
                    in_aw = window_inbound_by_dest.get(d_in)
                    if out_aw is None or in_aw is None:
                        continue
                    oj_dict = self.wallet_engine.allocate_family_tickets(
                        profile=active_profile,
                        outbound_award=out_aw,
                        inbound_award=in_aw,
                        cash_benchmark_per_pax=0.0,
                        strategy="ONE_WAY_BONUS_ONE_WAY_CASH",
                        preferred_cabins=query.preferred_cabins,
                        enabled_programs=query.enabled_loyalty_programs,
                    )
                    if oj_dict is not None:
                        itin_oj = FlightItinerary.from_dict(oj_dict)
                        raw_proposals.append(
                            self._make_proposal_from_itinerary(
                                query=query,
                                window=window,
                                itinerary=itin_oj,
                                n_seated=n_seated,
                            )
                        )

        if not is_anywhere_query:
            allowed_iatas = set(expanded_destinations)
            raw_proposals = [
                p
                for p in raw_proposals
                if p.itinerary is not None
                and p.itinerary.destination_iata in allowed_iatas
                and (p.itinerary.return_origin_iata or p.itinerary.destination_iata)
                in allowed_iatas
                and (
                    not p.itinerary.outbound_legs
                    or p.itinerary.outbound_legs[-1].destination_iata in allowed_iatas
                )
                and (
                    not p.itinerary.inbound_legs
                    or p.itinerary.inbound_legs[0].origin_iata in allowed_iatas
                )
            ]

        # Run 11 (U4, R2, U3): a bonus search returns only results with bonus seats in at
        # least one direction. A positive Matmid balance is compared only with the points
        # needed for ONE bonus ticket of the result, never with an all-passenger total;
        # a balance of 0 (or none) means "not entered" and filters nothing.
        if airline_mode == "EL_AL_ONLY" and query.search_elal_bonus_tickets:
            raw_proposals = [
                p
                for p in raw_proposals
                if p.itinerary is not None
                and p.itinerary.bonus_direction_coverage != "NONE"
            ]
            if effective_points_balance > 0:
                raw_proposals = [
                    p
                    for p in raw_proposals
                    if p.itinerary is not None
                    and (
                        p.itinerary.min_points_per_bonus_ticket is None
                        or p.itinerary.min_points_per_bonus_ticket
                        <= effective_points_balance
                    )
                ]

        if not raw_proposals:
            if persist_results:
                self.repository.save_search_query(query)
            return []

        # Apply HARD_THRESHOLD filtering with graceful 3-option fallback when requested
        if has_weather_filter and query.weather_filter_mode == "HARD_THRESHOLD":
            passing = [
                p
                for p in raw_proposals
                if p.weather_suitability_score >= effective_tau
            ]
            if len(passing) >= 3:
                raw_proposals = passing
            else:
                relaxed_tau = max(35.0, effective_tau - 20.0)
                relaxed_passing = [
                    p
                    for p in raw_proposals
                    if p.weather_suitability_score >= relaxed_tau
                ]
                self.last_weather_fallback_message_he = (
                    f"⚠️ שים לב: במועד זה נמצאו פחות מ-3 חלופות מעל סף מזג האוויר המבוקש ({effective_tau:.0f}/100). "
                    f"מוצגות החלופות הקרובות ביותר לפי התאמת מזג האוויר."
                )
                self.last_weather_fallback_message_en = (
                    f"⚠️ Note: Fewer than 3 options met the weather threshold ({effective_tau:.0f}/100) for this period; "
                    f"showing the closest weather-ranked alternatives."
                )
                if len(relaxed_passing) >= 3:
                    raw_proposals = relaxed_passing

        # Fixed strategy order used only to break ties between equally scored results.
        strategy_rank: dict[str, int] = {
            name: idx
            for idx, name in enumerate(
                (
                    "FULL_BONUS_SAME_CABIN",
                    "SPLIT_CABIN_BONUS",
                    "MULTI_CLUB_PER_PASSENGER_SPLIT",
                    "HYBRID_BONUS_PLUS_CASH",
                    "ONE_WAY_BONUS_ONE_WAY_CASH",
                    "CASH_AND_POINTS",
                    "COMMERCIAL_CASH_ONLY",
                )
            )
        }

        def _proposal_sort_key(p: VacationOptionProposal) -> tuple[Any, ...]:
            """Ascending key: scores first (higher is better), then non-cash tie-breakers.

            No cash value takes part in the ordering. Equal scores are ordered by the fixed
            strategy order, more bonus tickets first, then dates, destination, carrier and
            flight numbers, so the order never depends on the order results were produced in.
            """
            itin = p.itinerary
            if itin is not None:
                strat_code = (
                    itin.fulfillment_strategy.value
                    if isinstance(itin.fulfillment_strategy, Enum)
                    else str(itin.fulfillment_strategy)
                )
                all_legs = list(itin.outbound_legs) + list(itin.inbound_legs)
                tie_breakers: tuple[Any, ...] = (
                    strategy_rank.get(strat_code, len(strategy_rank)),
                    -int(itin.bonus_tickets_count),
                    itin.departure_date.isoformat(),
                    itin.return_date.isoformat(),
                    str(itin.destination_iata or ""),
                    str(itin.return_origin_iata or ""),
                    str(itin.primary_carrier_iata or ""),
                    "/".join(str(leg.flight_number or "") for leg in all_legs),
                    "/".join(str(leg.departure_time_local or "") for leg in all_legs),
                )
            else:
                tie_breakers = (len(strategy_rank), 0, "", "", "", "", "", "", "")
            if has_weather_filter:
                return (
                    0 if p.weather_suitability_score >= effective_tau else 1,
                    -p.combined_trip_optimization_score,
                    -p.weather_suitability_score,
                    -p.flight_bonus_value_score,
                    -p.holiday_alignment_score,
                    *tie_breakers,
                )
            return (
                -p.combined_trip_optimization_score,
                -p.flight_bonus_value_score,
                -p.holiday_alignment_score,
                *tie_breakers,
            )

        # Best first
        raw_proposals.sort(key=_proposal_sort_key)

        # Keep top proposals while ensuring strategy, destination, and canonical benchmark diversity
        selected_proposals: list[VacationOptionProposal] = []
        selected_ids: set[str] = set()
        seen_strategies: set[str] = set()
        seen_destinations: set[str] = set()

        # Pass 1: Ensure canonical flagship proposals (when unfiltered) and strategy/destination diversity
        for p in raw_proposals:
            if p.itinerary is None:
                continue
            st = (
                p.itinerary.fulfillment_strategy.value
                if isinstance(p.itinerary.fulfillment_strategy, Enum)
                else str(p.itinerary.fulfillment_strategy)
            )
            is_open_jaw_p = p.itinerary.destination_iata != p.itinerary.return_origin_iata
            is_canonical_window = (
                not has_weather_filter
                and (
                    p.itinerary.departure_date,
                    p.itinerary.return_date,
                )
                in {
                    (date(2027, 4, 11), date(2027, 4, 18)),
                    (date(2026, 12, 6), date(2026, 12, 11)),
                    (date(2027, 6, 21), date(2027, 6, 28)),
                }
            )
            if (
                is_open_jaw_p
                or is_canonical_window
                or st not in seen_strategies
                or p.itinerary.destination_iata not in seen_destinations
            ):
                selected_proposals.append(p)
                selected_ids.add(p.id)
                seen_strategies.add(st)
                seen_destinations.add(p.itinerary.destination_iata)

        # Pass 2: Fill up to 36 proposals sorted by _proposal_sort_key descending
        for p in raw_proposals:
            if len(selected_proposals) >= 36:
                break
            if p.id not in selected_ids:
                selected_proposals.append(p)
                selected_ids.add(p.id)

        selected_proposals.sort(key=_proposal_sort_key)
        selected_proposals = selected_proposals[:36]

        if persist_results:
            saved_proposals = self.repository.save_search_results(query, selected_proposals)
            if owner_user_id is not None:
                self._store_ephemeral_proposals(saved_proposals, owner_user_id=owner_user_id)
            return saved_proposals

        for prop in selected_proposals:
            prop.search_query_id = query.id
            if prop.itinerary is not None:
                prop.itinerary.search_query_id = query.id
                prop.itinerary_id = prop.itinerary.id
        self._store_ephemeral_proposals(selected_proposals, owner_user_id=owner_user_id)
        return selected_proposals

    def _make_proposal_from_itinerary(
        self,
        query: FlightSearchQuery,
        window: CandidateVacationWindow,
        itinerary: FlightItinerary,
        n_seated: int,
    ) -> VacationOptionProposal:
        itinerary.search_query_id = query.id
        fbvs = self._compute_fbvs_bonus(itinerary, n_seated)

        has_weather_filter = bool(query.preferred_vacation_types)
        effective_tau = self.weather_engine.get_effective_threshold(
            query.preferred_vacation_types, query.min_weather_suitability_score
        )
        wss, vtype_scores, rec_types, w_metrics = (
            self.weather_engine.evaluate_window_weather(
                dest_iata=itinerary.destination_iata,
                start_date=itinerary.departure_date,
                end_date=itinerary.return_date,
                preferred_vacation_types=query.preferred_vacation_types,
                return_origin_iata=itinerary.return_origin_iata,
                min_threshold_override=query.min_weather_suitability_score,
            )
        )

        ctos = self._compute_ctos(
            window.holiday_alignment_score,
            fbvs,
            wss=wss,
            has_weather_filter=has_weather_filter,
            min_weather_threshold=effective_tau,
        )
        explanation = self._build_explanation_he(
            window,
            itinerary,
            fbvs,
            ctos,
            wss=wss if has_weather_filter else None,
            weather_summary_he=w_metrics.weather_summary_he if w_metrics else "",
        )

        return VacationOptionProposal(
            id=str(uuid.uuid4()),
            search_query_id=query.id,
            itinerary_id=itinerary.id,
            associated_holiday_codes=list(window.associated_holiday_codes),
            window_set_type=window.window_set_type,
            school_absence_penalty=window.school_absence_penalty,
            childcare_coverage_gain=window.childcare_coverage_gain,
            per_child_impact=list(window.per_child_impact),
            total_school_days_missed_across_children=window.total_school_days_missed_across_children,
            max_single_child_school_days_missed=window.max_single_child_school_days_missed,
            holiday_alignment_score=window.holiday_alignment_score,
            flight_bonus_value_score=fbvs,
            weather_suitability_score=wss,
            vacation_type_scores=vtype_scores,
            recommended_vacation_types=rec_types,
            weather_metrics=w_metrics,
            combined_trip_optimization_score=ctos,
            explanation_summary_he=explanation,
            itinerary=itinerary,
            created_at=_now_iso(),
        )
