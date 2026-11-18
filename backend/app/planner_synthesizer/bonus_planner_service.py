"""Multi-Club Loyalty Wallet Allocation Engine & 6-Strategy Bonus Vacation Synthesizer.

Implements Features `F22` through `F28`:
- `MultiClubWalletAllocationEngine`:
  - Supports all 10 `LoyaltyProgramCode` programs (`ELAL_MATMID`, `BRITISH_AVIOS`,
    `FLYING_BLUE`, `UNITED_MILEAGEPLUS`, `MILES_AND_MORE`, `DELTA_SKYMILES`,
    `QANTAS_FREQUENT_FLYER`, `AEGEAN_MILES_BONUS`, `AMEX_MR_ISRAEL`,
    `ISRAELI_CC_TRAVEL_POINTS`).
  - Enforces un-pooled (`can_pool_with_family=False`) whole-ticket allocation vs
    pooled (`can_pool_with_family=True`) family pool deduction, credit-card
    `transfer_ratio_to_airline`, FlyCard companion vouchers, and `INFANT_LAP`
    seat-cap exemption.
  - Enforces **Adult-Child Under-12 PNR Safety Pairing**: never isolates a child
    under age 12 (`INFANT_LAP`, `INFANT_SEAT`, `CHILD`) on a separate PNR or cabin
    group without at least one accompanying adult (`ADULT_1` or `ADULT_2`).
- `BonusVacationPlannerService`:
  - Synthesizes vacation proposals across all **6 Family Bonus Fulfillment Strategies**
    (`FULL_BONUS_SAME_CABIN`, `SPLIT_CABIN_BONUS`, `HYBRID_BONUS_PLUS_CASH`,
    `ONE_WAY_BONUS_ONE_WAY_CASH` including regional Open-Jaw `TLV->MXP` / `FCO->TLV`,
    `CASH_AND_POINTS` with `<0.8c` low-CPP warning, `MULTI_CLUB_PER_PASSENGER_SPLIT`)
    plus `COMMERCIAL_CASH_ONLY`.
  - Computes `CPP`, `FBVS` (Bonus & Cash modes), and `CTOS = 0.55 * VUS + 0.45 * FBVS`.
  - Provides `search_vacations`, `compare_proposals` (`VacationComparisonMatrix`),
    and RFC 5545 `export_proposal_ics`.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any, Optional

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
    PassengerTicketAllocation,
    VacationComparisonMatrix,
    VacationOptionProposal,
    classify_passenger_type,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    YOM_KIPPUR_CLOSED_DATES,
    _make_bonus_row,
    build_default_family_profile,
    is_shabbat_blocked_for_elal,
)
from backend.app.vacation_optimizer.maximizer_engine import VacationMaximizerEngine

# Ensure ChildTripImpact exposes `.camp_days_overlapped` as a property alias for `.nitzanim_days_overlapped`
if not hasattr(ChildTripImpact, "camp_days_overlapped"):
    ChildTripImpact.camp_days_overlapped = property(  # type: ignore[attr-defined]
        lambda self: self.nitzanim_days_overlapped
    )

# Compatible regional Open-Jaw airport clusters (never pair across distant zones like FCO and JFK)
OPEN_JAW_CLUSTERS: list[set[str]] = [
    {"FCO", "MXP"},
    {"LHR", "LTN"},
    {"BER", "MUC"},
    {"VIE", "BUD", "PRG"},
    {"MAD", "BCN"},
    {"CDG", "AMS"},
    {"ATH", "RHO"},
    {"LCA", "PFO"},
    {"BKK", "HKT"},
    {"JFK", "EWR"},
    {"MIA", "FLL"},
]

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


def _are_open_jaw_compatible(iata_a: str, iata_b: str) -> bool:
    a_up = str(iata_a).upper().strip()
    b_up = str(iata_b).upper().strip()
    if not a_up or not b_up or a_up == b_up:
        return False
    return any(a_up in cluster and b_up in cluster for cluster in OPEN_JAW_CLUSTERS)


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
    taxes_usd: float
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

    for j, child in enumerate(profile.children or [], start=1):
        pid = f"CHILD_{j}"
        age = int(child.child_age_years)
        f_type = str(
            child.passenger_Current_type or classify_passenger_type(age)
        ).upper()
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

    def _fund_single_slot(
        self,
        slot: _BonusSlot,
        passenger: _PassengerSpec,
        wallets: list[_WorkingWallet],
        points_used_by_wallet: dict[str, int],
        allow_partner_programs: bool = False,
        prefer_multi_wallet_split: bool = False,
    ) -> Optional[tuple[str, str]]:
        """Attempt to fund `slot.points_cost` as a whole ticket from `wallets`.

        Returns `(program_code, primary_wallet_id)` on success, or `None` if insufficient points.
        """
        cost = int(slot.points_cost)
        if cost <= 0:
            return ("ELAL_MATMID", "")

        def _is_program_compatible(w: _WorkingWallet) -> bool:
            if slot.preferred_program:
                return w.program_code in (slot.preferred_program, *TRANSFERABLE_CC_PROGRAMS)
            if allow_partner_programs:
                return True
            return w.program_code in ("ELAL_MATMID", *TRANSFERABLE_CC_PROGRAMS)

        compatible = [
            w for w in wallets if _is_program_compatible(w) and w.remaining_airline_points > 0
        ]
        if not compatible:
            return None

        # 1. Try un-pooled wallets FIRST: a single un-pooled wallet must cover the entire `cost`
        unpooled = [w for w in compatible if not w.can_pool_with_family]
        unpooled.sort(
            key=lambda w: (
                0 if w.passenger_id == passenger.passenger_id else 1,
                0 if w.program_code == "ELAL_MATMID" else 1,
                -w.remaining_airline_points,
            )
        )
        for uw in unpooled:
            if uw.remaining_airline_points >= cost:
                raw_needed = min(
                    uw.remaining_raw_points,
                    int(math.ceil(cost / uw.transfer_ratio - 1e-9)),
                )
                uw.remaining_raw_points -= raw_needed
                points_used_by_wallet[uw.wallet_id] = (
                    points_used_by_wallet.get(uw.wallet_id, 0) + raw_needed
                )
                return (uw.program_code, uw.wallet_id)

        # 2. Try pooled wallets (`can_pool_with_family == True`)
        pooled = [w for w in compatible if w.can_pool_with_family]
        if not pooled:
            return None

        # Build candidate pool groups:
        # Pool Group A: El Al Matmid + Transferable Israeli Credit Card Points
        elal_and_cc_pool = [
            w
            for w in pooled
            if w.program_code in ("ELAL_MATMID", *TRANSFERABLE_CC_PROGRAMS)
        ]
        if prefer_multi_wallet_split:
            # Order passenger's own wallet first, then other Matmid/CC wallets
            elal_and_cc_pool.sort(
                key=lambda w: (
                    0 if w.passenger_id == passenger.passenger_id else 1,
                    0 if w.program_code == "ELAL_MATMID" else 1,
                )
            )
        else:
            elal_and_cc_pool.sort(
                key=lambda w: (
                    0 if w.program_code == "ELAL_MATMID" else 1,
                    0 if w.passenger_id == passenger.passenger_id else 1,
                )
            )

        candidate_pools: list[list[_WorkingWallet]] = []
        if slot.preferred_program and slot.preferred_program in PARTNER_AIRLINE_PROGRAMS:
            partner_pool = [
                w
                for w in pooled
                if w.program_code in (slot.preferred_program, *TRANSFERABLE_CC_PROGRAMS)
            ]
            partner_pool.sort(
                key=lambda w: 0 if w.program_code == slot.preferred_program else 1
            )
            candidate_pools.append(partner_pool)
        else:
            if elal_and_cc_pool:
                candidate_pools.append(elal_and_cc_pool)
            if allow_partner_programs:
                for p_code in sorted(PARTNER_AIRLINE_PROGRAMS):
                    p_pool = [
                        w
                        for w in pooled
                        if w.program_code in (p_code, *TRANSFERABLE_CC_PROGRAMS)
                    ]
                    p_pool.sort(key=lambda w: 0 if w.program_code == p_code else 1)
                    if p_pool:
                        candidate_pools.append(p_pool)

        for pool in candidate_pools:
            total_eff = sum(w.remaining_airline_points for w in pool)
            if total_eff < cost:
                continue
            rem_pts = cost
            primary_prog = pool[0].program_code
            primary_wid = pool[0].wallet_id
            for w in pool:
                if rem_pts <= 0:
                    break
                w_eff = w.remaining_airline_points
                if w_eff <= 0:
                    continue
                take_eff = min(rem_pts, w_eff)
                raw_deduct = min(
                    w.remaining_raw_points,
                    int(math.ceil(take_eff / w.transfer_ratio - 1e-9)),
                )
                if raw_deduct > 0:
                    w.remaining_raw_points -= raw_deduct
                    points_used_by_wallet[w.wallet_id] = (
                        points_used_by_wallet.get(w.wallet_id, 0) + raw_deduct
                    )
                    rem_pts -= take_eff
            return (primary_prog, primary_wid)

        return None

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
        city_he = str(meta.get("city_he") or (commercial_offer or {}).get("destination_city_he") or dest_iata)
        city_en = str(meta.get("city_en") or (commercial_offer or {}).get("destination_city_en") or dest_iata)
        trip_nights = max(1, (ret_date - dep_date).days)

        bench_per_pax = (
            float(cash_benchmark_per_pax)
            if cash_benchmark_per_pax and float(cash_benchmark_per_pax) > 0
            else float(meta.get("rt_cash_per_pax_usd", 590.0))
        )
        full_cash_benchmark_usd = round(n_seated * bench_per_pax, 2)

        cat_rt = float(meta.get("rt_cash_per_pax_usd", bench_per_pax))
        if dest_iata in DESTINATION_CATALOG and abs(bench_per_pax - cat_rt) < 1.0:
            supp_cash_per_pax = float(
                meta.get("supplemental_single_pax_cash_usd", round(bench_per_pax * 0.78, 2))
            )
        else:
            supp_cash_per_pax = round(bench_per_pax * 0.78, 2)

        out_tax_per_pax = (
            float(outbound_award.taxes_usd_per_pax)
            if outbound_award is not None
            else float(meta.get("outbound_taxes_usd", 48.75))
        )
        in_tax_per_pax = (
            float(inbound_award.taxes_usd_per_pax)
            if inbound_award is not None
            else float(meta.get("inbound_taxes_usd", 48.75))
        )
        rt_tax_per_pax = round(out_tax_per_pax + in_tax_per_pax, 2)

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

        def _append_lap_infant_allocations(
            allocs: list[PassengerTicketAllocation],
        ) -> list[PassengerTicketAllocation]:
            if not lap_infants:
                return allocs
            ref_mode = allocs[0].ticket_mode if allocs else "ELAL_MATMID_BONUS"
            ref_dir = allocs[0].direction if allocs else "ROUND_TRIP"
            ref_cabin = allocs[0].cabin_class if allocs else "ECONOMY"
            ref_rbd = allocs[0].rbd_code if allocs else "E"
            ref_prog = allocs[0].program_code if allocs else "ELAL_MATMID"
            for inf in lap_infants:
                allocs.append(
                    PassengerTicketAllocation(
                        passenger_label=inf.passenger_label,
                        ticket_mode=ref_mode,
                        direction=ref_dir,
                        cabin_class=ref_cabin,
                        rbd_code=ref_rbd,
                        points_used=0,
                        cash_fare_usd=0.0,
                        taxes_usd=0.0,
                        passenger_id=inf.passenger_id,
                        program_code=ref_prog,
                        wallet_id=None,
                    )
                )
            return allocs

        def _finalize_result(
            allocs: list[PassengerTicketAllocation],
            points_by_wallet: dict[str, int],
            requires_verify: bool,
            utilizes_bonus: bool = True,
            baggage_fees_usd: float = 0.0,
            override_taxes_usd: Optional[float] = None,
            override_supp_cash_usd: Optional[float] = None,
        ) -> dict[str, Any]:
            full_allocs = _append_lap_infant_allocations(list(allocs))
            total_pts = sum(int(a.points_used) for a in full_allocs)
            total_taxes = (
                round(override_taxes_usd, 2)
                if override_taxes_usd is not None
                else round(sum(float(a.taxes_usd) for a in full_allocs), 2)
            )
            total_supp = (
                round(override_supp_cash_usd, 2)
                if override_supp_cash_usd is not None
                else round(sum(float(a.cash_fare_usd) for a in full_allocs), 2)
            )
            total_bag = round(float(baggage_fees_usd), 2)
            total_oop = round(total_taxes + total_supp + total_bag, 2)
            net_saved = round(full_cash_benchmark_usd - total_oop, 2)
            cpp_val: Optional[float] = None
            if total_pts > 0:
                cpp_val = round((net_saved * 100.0) / float(total_pts), 2)

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
                family_ticket_allocation=full_allocs,
                points_used_by_wallet={k: int(v) for k, v in points_by_wallet.items() if int(v) > 0},
                requires_two_plus_seat_verification=bool(requires_verify),
                total_matmid_points=total_pts,
                total_taxes_and_fees_usd=total_taxes,
                total_supplemental_cash_fares_usd=total_supp,
                total_baggage_fees_usd=total_bag,
                total_out_of_pocket_cash_usd=total_oop,
                full_cash_benchmark_usd=full_cash_benchmark_usd,
                net_cash_saved_usd=net_saved,
                cents_per_point_value=cpp_val,
                rbddataclients_verify_url="https://www.elal.com/rbddataclients/" if is_elal else None,
                booking_deep_link_url=(
                    f"https://www.elal.com/heb/booking?origin={origin_iata}&destination={dest_iata}"
                    f"&departureDate={dep_date.isoformat()}&returnDate={ret_date.isoformat()}"
                    if is_elal
                    else f"https://www.google.com/travel/flights?q={origin_iata}.{dest_iata}.{dep_date.isoformat()}"
                ),
            )
            return itin.to_dict()

        # =====================================================================
        # Strategy 7: COMMERCIAL_CASH_ONLY
        # =====================================================================
        if strat_str == "COMMERCIAL_CASH_ONLY":
            if commercial_offer is not None:
                bag_fee = float(commercial_offer.get("total_baggage_fees_usd", 0.0))
                fam_tax = float(commercial_offer.get("total_taxes_and_fees_usd", round(rt_tax_per_pax * n_seated, 2)))
                fam_supp = float(
                    commercial_offer.get(
                        "total_supplemental_cash_fares_usd",
                        round(max(0.0, full_cash_benchmark_usd - fam_tax), 2),
                    )
                )
            else:
                bag_fee, total_with_bag = FamilyBaggageNormalizer.normalize_family_baggage_cost(
                    carrier_iata=primary_carrier,
                    base_fare_usd=full_cash_benchmark_usd,
                    profile=profile,
                    trip_nights=trip_nights,
                )
                fam_tax = round(rt_tax_per_pax * n_seated, 2)
                fam_supp = round(max(0.0, (total_with_bag - bag_fee) - fam_tax), 2)

            per_pax_tax = round(fam_tax / n_seated, 2)
            per_pax_supp = round(fam_supp / n_seated, 2)
            allocs = [
                PassengerTicketAllocation(
                    passenger_label=p.passenger_label,
                    ticket_mode="COMMERCIAL_CASH",
                    direction="ROUND_TRIP",
                    cabin_class="ECONOMY",
                    rbd_code="Y",
                    points_used=0,
                    cash_fare_usd=per_pax_supp,
                    taxes_usd=per_pax_tax,
                    passenger_id=p.passenger_id,
                    program_code=None,
                    wallet_id=None,
                )
                for p in seated_passengers
            ]
            return _finalize_result(
                allocs=allocs,
                points_by_wallet={},
                requires_verify=False,
                utilizes_bonus=False,
                baggage_fees_usd=bag_fee,
                override_taxes_usd=fam_tax,
                override_supp_cash_usd=fam_supp,
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
                in_s, in_2p, in_rbd, in_pts = _cabin_award_info(inbound_award, cabin)
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

                rt_pts = out_pts + in_pts
                wallets = self._prepare_working_wallets(profile, prog_list)
                pts_by_wallet: dict[str, int] = {}
                allocs = []
                feasible = True
                for p in seated_passengers:
                    slot = _BonusSlot(
                        cabin_class=cabin,
                        rbd_code=out_rbd,
                        points_cost=rt_pts,
                        taxes_usd=rt_tax_per_pax,
                    )
                    funded = self._fund_single_slot(
                        slot=slot,
                        passenger=p,
                        wallets=wallets,
                        points_used_by_wallet=pts_by_wallet,
                        allow_partner_programs=False,
                    )
                    if funded is None:
                        feasible = False
                        break
                    prog_used, wid_used = funded
                    allocs.append(
                        PassengerTicketAllocation(
                            passenger_label=p.passenger_label,
                            ticket_mode="ELAL_MATMID_BONUS",
                            direction="ROUND_TRIP",
                            cabin_class=cabin,
                            rbd_code=out_rbd or in_rbd,
                            points_used=rt_pts,
                            cash_fare_usd=0.0,
                            taxes_usd=rt_tax_per_pax,
                            passenger_id=p.passenger_id,
                            program_code=prog_used,
                            wallet_id=wid_used or None,
                        )
                    )
                if feasible and len(allocs) == n_seated:
                    return _finalize_result(
                        allocs=allocs,
                        points_by_wallet=pts_by_wallet,
                        requires_verify=(n_seated >= 3),
                        utilizes_bonus=True,
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
                            taxes_usd=rt_tax_per_pax,
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
                                _BonusSlot("ECONOMY", e_rbd, out_e_pts + in_e_pts, rt_tax_per_pax)
                                for _ in range(n_seated - 2)
                            ] + [
                                _BonusSlot(upper_cab, u_rbd, out_u_pts + in_u_pts, rt_tax_per_pax)
                                for _ in range(2)
                            ]
                            candidate_slot_plans.append((plan2, True))
                            break

            for slots_plan, req_verify in candidate_slot_plans:
                wallets = self._prepare_working_wallets(profile, prog_list)
                pts_by_wallet = {}
                # Pair adults with young children across the split cabins:
                # Group slots by cabin in order of appearance
                cabins_in_plan: list[str] = []
                for s in slots_plan:
                    if s.cabin_class not in cabins_in_plan:
                        cabins_in_plan.append(s.cabin_class)

                adults = [p for p in seated_passengers if p.is_adult]
                under12 = [p for p in seated_passengers if not p.is_adult and p.is_under_12]
                others = [p for p in seated_passengers if not p.is_adult and not p.is_under_12]

                # Order passengers so Cabin 1 gets ADULT_1 + child(ren) and Cabin 2 gets ADULT_2 + child(ren)
                slots_in_c1 = sum(1 for s in slots_plan if s.cabin_class == cabins_in_plan[0])
                ordered_pax: list[_PassengerSpec] = []
                if len(adults) >= 2 and slots_in_c1 >= 1 and len(slots_plan) > slots_in_c1:
                    rem_pool = [*under12, *others, *adults[2:]]
                    c1_fill = rem_pool[: max(0, slots_in_c1 - 1)]
                    c2_fill = rem_pool[max(0, slots_in_c1 - 1) :]
                    ordered_pax = [adults[0], *c1_fill, adults[1], *c2_fill]
                else:
                    ordered_pax = list(seated_passengers)

                allocs = []
                feasible = True
                for p, slot in zip(ordered_pax, slots_plan):
                    funded = self._fund_single_slot(
                        slot=slot,
                        passenger=p,
                        wallets=wallets,
                        points_used_by_wallet=pts_by_wallet,
                        allow_partner_programs=False,
                    )
                    if funded is None:
                        feasible = False
                        break
                    prog_used, wid_used = funded
                    allocs.append(
                        PassengerTicketAllocation(
                            passenger_label=p.passenger_label,
                            ticket_mode="ELAL_MATMID_BONUS",
                            direction="ROUND_TRIP",
                            cabin_class=slot.cabin_class,
                            rbd_code=slot.rbd_code,
                            points_used=slot.points_cost,
                            cash_fare_usd=0.0,
                            taxes_usd=slot.taxes_usd,
                            passenger_id=p.passenger_id,
                            program_code=prog_used,
                            wallet_id=wid_used or None,
                        )
                    )
                if feasible and len(allocs) == n_seated:
                    return _finalize_result(
                        allocs=allocs,
                        points_by_wallet=pts_by_wallet,
                        requires_verify=req_verify,
                        utilizes_bonus=True,
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
                            taxes_usd=rt_tax_per_pax,
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
                wallets = self._prepare_working_wallets(profile, prog_list)
                pts_by_wallet = {}
                allocs = []
                feasible = True
                for p, slot in zip(bonus_pax, avail_slots[:k_try]):
                    funded = self._fund_single_slot(
                        slot=slot,
                        passenger=p,
                        wallets=wallets,
                        points_used_by_wallet=pts_by_wallet,
                        allow_partner_programs=False,
                    )
                    if funded is None:
                        feasible = False
                        break
                    prog_used, wid_used = funded
                    allocs.append(
                        PassengerTicketAllocation(
                            passenger_label=p.passenger_label,
                            ticket_mode="ELAL_MATMID_BONUS",
                            direction="ROUND_TRIP",
                            cabin_class=slot.cabin_class,
                            rbd_code=slot.rbd_code,
                            points_used=slot.points_cost,
                            cash_fare_usd=0.0,
                            taxes_usd=slot.taxes_usd,
                            passenger_id=p.passenger_id,
                            program_code=prog_used,
                            wallet_id=wid_used or None,
                        )
                    )
                if not feasible:
                    continue

                for cp in cash_pax:
                    allocs.append(
                        PassengerTicketAllocation(
                            passenger_label=cp.passenger_label,
                            ticket_mode="COMMERCIAL_CASH",
                            direction="ROUND_TRIP",
                            cabin_class="ECONOMY",
                            rbd_code="Y",
                            points_used=0,
                            cash_fare_usd=supp_cash_per_pax,
                            taxes_usd=0.0,
                            passenger_id=cp.passenger_id,
                            program_code=None,
                            wallet_id=None,
                        )
                    )

                return _finalize_result(
                    allocs=allocs,
                    points_by_wallet=pts_by_wallet,
                    requires_verify=False,
                    utilizes_bonus=True,
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
                out_s, _, out_rbd, out_pts = _cabin_award_info(outbound_award, "ECONOMY")
                in_s, _, _in_rbd, in_pts = _cabin_award_info(inbound_award, "ECONOMY")
                if out_s >= 1 and in_s >= 1 and out_pts > 0 and in_pts > 0:
                    wallets = self._prepare_working_wallets(profile, prog_list)
                    pts_by_wallet = {}
                    allocs = []
                    # Allocate as many RT open-jaw bonus seats as available, plus cash/OW for remainder
                    oj_slots: list[_BonusSlot] = []
                    for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
                        if cab not in pref_cabins:
                            continue
                        os_c, _, orbd_c, opts_c = _cabin_award_info(outbound_award, cab)
                        is_c, _, _, ipts_c = _cabin_award_info(inbound_award, cab)
                        if cab == "PREMIUM" and os_c >= 2 and is_c == 1:
                            ib_s, _, _, _ = _cabin_award_info(inbound_award, "BUSINESS")
                            is_c += 1 if ib_s >= 1 else 0
                        for _ in range(min(os_c, is_c)):
                            if opts_c > 0 and ipts_c > 0:
                                oj_slots.append(
                                    _BonusSlot(cab, orbd_c, opts_c + ipts_c, rt_tax_per_pax)
                                )
                    k_oj = min(len(oj_slots), n_seated)
                    partition = self._assign_passengers_with_pnr_safety(seated_passengers, k_oj)
                    if partition is not None and k_oj >= 1:
                        b_pax, c_pax = partition
                        feasible = True
                        for p, slot in zip(b_pax, oj_slots[:k_oj]):
                            funded = self._fund_single_slot(
                                slot=slot,
                                passenger=p,
                                wallets=wallets,
                                points_used_by_wallet=pts_by_wallet,
                            )
                            if funded is None:
                                feasible = False
                                break
                            prog_used, wid_used = funded
                            allocs.append(
                                PassengerTicketAllocation(
                                    passenger_label=p.passenger_label,
                                    ticket_mode="ELAL_MATMID_BONUS",
                                    direction="OPEN_JAW_ROUND_TRIP",
                                    cabin_class=slot.cabin_class,
                                    rbd_code=slot.rbd_code,
                                    points_used=slot.points_cost,
                                    cash_fare_usd=0.0,
                                    taxes_usd=slot.taxes_usd,
                                    passenger_id=p.passenger_id,
                                    program_code=prog_used,
                                    wallet_id=wid_used or None,
                                )
                            )
                        if feasible:
                            for cp in c_pax:
                                allocs.append(
                                    PassengerTicketAllocation(
                                        passenger_label=cp.passenger_label,
                                        ticket_mode="COMMERCIAL_CASH",
                                        direction="OPEN_JAW_ROUND_TRIP",
                                        cabin_class="ECONOMY",
                                        rbd_code="Y",
                                        points_used=0,
                                        cash_fare_usd=supp_cash_per_pax,
                                        taxes_usd=0.0,
                                        passenger_id=cp.passenger_id,
                                        program_code=None,
                                        wallet_id=None,
                                    )
                                )
                            return _finalize_result(
                                allocs=allocs,
                                points_by_wallet=pts_by_wallet,
                                requires_verify=False,
                                utilizes_bonus=True,
                            )

            # Case B: One-Way Bonus on one direction + One-Way Commercial Cash on the other direction
            best_dir: Optional[str] = None
            chosen_award: Optional[ElAlBonusAvailability] = None
            chosen_cabin = "ECONOMY"
            chosen_rbd = "E"
            chosen_ow_pts = 0
            chosen_ow_tax = out_tax_per_pax

            for dir_label, aw, tax_ow in (
                ("OUTBOUND_ONLY", outbound_award, out_tax_per_pax),
                ("INBOUND_ONLY", inbound_award, in_tax_per_pax),
            ):
                if aw is None:
                    continue
                for cab in ("ECONOMY", "PREMIUM", "BUSINESS"):
                    if cab not in pref_cabins:
                        continue
                    s_cnt, _, rbd_c, pts_c = _cabin_award_info(aw, cab)
                    if s_cnt >= 1 and pts_c > 0:
                        best_dir = dir_label
                        chosen_award = aw
                        chosen_cabin = cab
                        chosen_rbd = rbd_c
                        chosen_ow_pts = pts_c
                        chosen_ow_tax = round(float(tax_ow), 2)
                        break
                if best_dir is not None:
                    break

            if best_dir is None or chosen_award is None or chosen_ow_pts <= 0:
                return None

            ow_cash_per_pax = round(0.45 * bench_per_pax, 2)
            wallets = self._prepare_working_wallets(profile, prog_list)
            pts_by_wallet = {}
            allocs = []
            funded_any = False

            for p in seated_passengers:
                slot = _BonusSlot(
                    cabin_class=chosen_cabin,
                    rbd_code=chosen_rbd,
                    points_cost=chosen_ow_pts,
                    taxes_usd=chosen_ow_tax,
                    direction=best_dir,
                )
                funded = self._fund_single_slot(
                    slot=slot,
                    passenger=p,
                    wallets=wallets,
                    points_used_by_wallet=pts_by_wallet,
                )
                if funded is not None:
                    funded_any = True
                    prog_used, wid_used = funded
                    allocs.append(
                        PassengerTicketAllocation(
                            passenger_label=p.passenger_label,
                            ticket_mode="ONE_WAY_BONUS_PLUS_ONE_WAY_CASH",
                            direction=best_dir,
                            cabin_class=chosen_cabin,
                            rbd_code=chosen_rbd,
                            points_used=chosen_ow_pts,
                            cash_fare_usd=ow_cash_per_pax,
                            taxes_usd=chosen_ow_tax,
                            passenger_id=p.passenger_id,
                            program_code=prog_used,
                            wallet_id=wid_used or None,
                        )
                    )
                else:
                    allocs.append(
                        PassengerTicketAllocation(
                            passenger_label=p.passenger_label,
                            ticket_mode="COMMERCIAL_CASH",
                            direction="ROUND_TRIP",
                            cabin_class="ECONOMY",
                            rbd_code="Y",
                            points_used=0,
                            cash_fare_usd=bench_per_pax,
                            taxes_usd=0.0,
                            passenger_id=p.passenger_id,
                            program_code=None,
                            wallet_id=None,
                        )
                    )

            if not funded_any:
                return None

            return _finalize_result(
                allocs=allocs,
                points_by_wallet=pts_by_wallet,
                requires_verify=(n_seated >= 3 and chosen_award.economy_award_seats == 2),
                utilizes_bonus=True,
            )

        # =====================================================================
        # Strategy 5: CASH_AND_POINTS (F26)
        # =====================================================================
        if strat_str == "CASH_AND_POINTS":
            wallets = self._prepare_working_wallets(profile, prog_list)
            elal_wallets = [
                w
                for w in wallets
                if w.program_code in ("ELAL_MATMID", *TRANSFERABLE_CC_PROGRAMS)
                and w.remaining_airline_points > 0
            ]
            total_avail_pts = sum(w.remaining_airline_points for w in elal_wallets)
            if total_avail_pts <= 0:
                return None

            # Effective conversion rate: 0.72 cents per point ($0.0072/pt < 0.8c low-CPP threshold)
            cpp_rate_usd = 0.0072
            max_pts_by_fare = int(math.floor((0.45 * full_cash_benchmark_usd) / cpp_rate_usd))
            target_total_pts = min(total_avail_pts, n_seated * 15000, max(5000, max_pts_by_fare))
            # Round down to a clean multiple of n_seated where possible
            if target_total_pts >= n_seated:
                target_total_pts = (target_total_pts // n_seated) * n_seated
            if target_total_pts <= 0:
                return None

            pts_by_wallet = {}
            rem_to_deduct = target_total_pts
            actual_airline_pts = 0
            for w in elal_wallets:
                if rem_to_deduct <= 0:
                    break
                take_eff = min(rem_to_deduct, w.remaining_airline_points)
                raw_ded = min(
                    w.remaining_raw_points,
                    int(math.ceil(take_eff / w.transfer_ratio - 1e-9)),
                )
                if raw_ded > 0:
                    w.remaining_raw_points -= raw_ded
                    points_used_by_wallet_prev = pts_by_wallet.get(w.wallet_id, 0)
                    pts_by_wallet[w.wallet_id] = points_used_by_wallet_prev + raw_ded
                    actual_airline_pts += take_eff
                    rem_to_deduct -= take_eff

            if actual_airline_pts <= 0:
                return None

            discount_usd = round(actual_airline_pts * cpp_rate_usd, 2)
            total_taxes = round(n_seated * rt_tax_per_pax, 2)
            total_oop = round(max(total_taxes, full_cash_benchmark_usd - discount_usd), 2)
            total_supp = round(max(0.0, total_oop - total_taxes), 2)

            pts_per_pax = actual_airline_pts // n_seated
            pts_rem = actual_airline_pts - (pts_per_pax * n_seated)
            supp_per_pax = round(total_supp / n_seated, 2)

            allocs = []
            for idx, p in enumerate(seated_passengers):
                p_pts = pts_per_pax + (pts_rem if idx == 0 else 0)
                allocs.append(
                    PassengerTicketAllocation(
                        passenger_label=p.passenger_label,
                        ticket_mode="ELAL_CASH_AND_POINTS",
                        direction="ROUND_TRIP",
                        cabin_class="ECONOMY",
                        rbd_code="Y",
                        points_used=p_pts,
                        cash_fare_usd=supp_per_pax,
                        taxes_usd=rt_tax_per_pax,
                        passenger_id=p.passenger_id,
                        program_code="ELAL_MATMID",
                        wallet_id=elal_wallets[0].wallet_id if elal_wallets else None,
                    )
                )

            return _finalize_result(
                allocs=allocs,
                points_by_wallet=pts_by_wallet,
                requires_verify=False,
                utilizes_bonus=True,
                override_taxes_usd=total_taxes,
                override_supp_cash_usd=total_supp,
            )

        # =====================================================================
        # Strategy 6: MULTI_CLUB_PER_PASSENGER_SPLIT (F27)
        # =====================================================================
        if strat_str == "MULTI_CLUB_PER_PASSENGER_SPLIT":
            wallets = self._prepare_working_wallets(profile, prog_list)
            if not wallets:
                return None

            if outbound_award is not None and inbound_award is not None:
                _, _, econ_rbd, out_econ_pts = _cabin_award_info(outbound_award, "ECONOMY")
                _, _, _, in_econ_pts = _cabin_award_info(inbound_award, "ECONOMY")
                rt_econ_pts = (out_econ_pts or 15000) + (in_econ_pts or 15000)
                ow_econ_pts = out_econ_pts or 15000

                # Build candidate round-trip slots across preferred cabins + partner clubs
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
                            _BonusSlot(cab, out_rbd, out_pts + in_pts, rt_tax_per_pax)
                        )

                # If more seated passengers remain, partner airline clubs enabled in `prog_list`
                # can fulfill additional round-trip slots at `rt_econ_pts`
                partner_wallets = [
                    w for w in wallets if w.program_code in PARTNER_AIRLINE_PROGRAMS
                ]
                for pw in partner_wallets:
                    if len(mc_slots) >= n_seated:
                        break
                    if pw.remaining_airline_points >= rt_econ_pts:
                        mc_slots.append(
                            _BonusSlot(
                                cabin_class="ECONOMY",
                                rbd_code=econ_rbd,
                                points_cost=rt_econ_pts,
                                taxes_usd=rt_tax_per_pax,
                                preferred_program=pw.program_code,
                            )
                        )

                # Determine how many full RT slots can be funded
                test_wallets = self._prepare_working_wallets(profile, prog_list)
                test_used: dict[str, int] = {}
                funded_rt_count = 0
                for idx_s, slot in enumerate(mc_slots[:n_seated]):
                    pax_ref = seated_passengers[min(idx_s, n_seated - 1)]
                    if (
                        self._fund_single_slot(
                            slot=slot,
                            passenger=pax_ref,
                            wallets=test_wallets,
                            points_used_by_wallet=test_used,
                            allow_partner_programs=True,
                            prefer_multi_wallet_split=True,
                        )
                        is not None
                    ):
                        funded_rt_count += 1
                    else:
                        break

                if funded_rt_count >= 1:
                    partition = self._assign_passengers_with_pnr_safety(
                        seated_passengers, funded_rt_count
                    )
                    if partition is None:
                        return None
                    bonus_pax, cash_pax = partition
                    pts_by_wallet = {}
                    allocs = []
                    for p, slot in zip(bonus_pax, mc_slots[:funded_rt_count]):
                        funded = self._fund_single_slot(
                            slot=slot,
                            passenger=p,
                            wallets=wallets,
                            points_used_by_wallet=pts_by_wallet,
                            allow_partner_programs=True,
                            prefer_multi_wallet_split=True,
                        )
                        if funded is None:
                            return None
                        prog_used, wid_used = funded
                        t_mode = (
                            "ELAL_MATMID_BONUS"
                            if prog_used == "ELAL_MATMID"
                            else f"MULTI_CLUB_{prog_used}_BONUS"
                        )
                        allocs.append(
                            PassengerTicketAllocation(
                                passenger_label=p.passenger_label,
                                ticket_mode=t_mode,
                                direction="ROUND_TRIP",
                                cabin_class=slot.cabin_class,
                                rbd_code=slot.rbd_code,
                                points_used=slot.points_cost,
                                cash_fare_usd=0.0,
                                taxes_usd=slot.taxes_usd,
                                passenger_id=p.passenger_id,
                                program_code=prog_used,
                                wallet_id=wid_used or None,
                            )
                        )
                    for cp in cash_pax:
                        allocs.append(
                            PassengerTicketAllocation(
                                passenger_label=cp.passenger_label,
                                ticket_mode="COMMERCIAL_CASH",
                                direction="ROUND_TRIP",
                                cabin_class="ECONOMY",
                                rbd_code="Y",
                                points_used=0,
                                cash_fare_usd=supp_cash_per_pax,
                                taxes_usd=0.0,
                                passenger_id=cp.passenger_id,
                                program_code=None,
                                wallet_id=None,
                            )
                        )
                    return _finalize_result(
                        allocs=allocs,
                        points_by_wallet=pts_by_wallet,
                        requires_verify=False,
                        utilizes_bonus=True,
                    )

                # Fallback for un-pooled wallets that cannot cover a full RT (`30,000` pts)
                # but CAN cover an entire One-Way leg (`15,000 <= 25,000` pts, `test_f27_01`):
                pts_by_wallet = {}
                allocs = []
                ow_cash_per_pax = round(0.45 * bench_per_pax, 2)
                any_ow_funded = False
                for p in seated_passengers:
                    ow_slot = _BonusSlot(
                        cabin_class="ECONOMY",
                        rbd_code=econ_rbd,
                        points_cost=ow_econ_pts,
                        taxes_usd=round(out_tax_per_pax, 2),
                        direction="OUTBOUND_ONLY",
                    )
                    funded = self._fund_single_slot(
                        slot=ow_slot,
                        passenger=p,
                        wallets=wallets,
                        points_used_by_wallet=pts_by_wallet,
                        allow_partner_programs=True,
                        prefer_multi_wallet_split=True,
                    )
                    if funded is not None:
                        any_ow_funded = True
                        prog_used, wid_used = funded
                        allocs.append(
                            PassengerTicketAllocation(
                                passenger_label=p.passenger_label,
                                ticket_mode="ONE_WAY_BONUS_PLUS_ONE_WAY_CASH",
                                direction="OUTBOUND_ONLY",
                                cabin_class="ECONOMY",
                                rbd_code=econ_rbd,
                                points_used=ow_econ_pts,
                                cash_fare_usd=ow_cash_per_pax,
                                taxes_usd=round(out_tax_per_pax, 2),
                                passenger_id=p.passenger_id,
                                program_code=prog_used,
                                wallet_id=wid_used or None,
                            )
                        )
                    else:
                        allocs.append(
                            PassengerTicketAllocation(
                                passenger_label=p.passenger_label,
                                ticket_mode="COMMERCIAL_CASH",
                                direction="ROUND_TRIP",
                                cabin_class="ECONOMY",
                                rbd_code="Y",
                                points_used=0,
                                cash_fare_usd=bench_per_pax,
                                taxes_usd=0.0,
                                passenger_id=p.passenger_id,
                                program_code=None,
                                wallet_id=None,
                            )
                        )
                if any_ow_funded:
                    return _finalize_result(
                        allocs=allocs,
                        points_by_wallet=pts_by_wallet,
                        requires_verify=False,
                        utilizes_bonus=True,
                    )

            return None

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
                    "vus_alpha_per": 0.60,
                    "vus_beta_ccg": 0.40,
                    "vus_gamma_sap": 0.35,
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

    def _compute_fbvs_bonus(
        self,
        itinerary: FlightItinerary,
        n_seated: int,
    ) -> float:
        """Compute Flight Bonus Value Score (`FBVS_bonus` in `[0.0, 100.0]`)."""
        bonus_allocs = [
            a
            for a in itinerary.family_ticket_allocation
            if a.ticket_mode != "COMMERCIAL_CASH" and int(a.points_used) > 0
        ]
        n_bonus = len(bonus_allocs)
        strat = (
            itinerary.fulfillment_strategy.value
            if isinstance(itinerary.fulfillment_strategy, Enum)
            else str(itinerary.fulfillment_strategy)
        )

        if strat == "CASH_AND_POINTS":
            saved_ratio = min(
                1.0,
                max(
                    0.0,
                    itinerary.net_cash_saved_usd
                    / max(1.0, itinerary.full_cash_benchmark_usd),
                ),
            )
            seat_cov = 0.55 * saved_ratio
        elif strat == "ONE_WAY_BONUS_ONE_WAY_CASH" and itinerary.destination_iata == itinerary.return_origin_iata:
            seat_cov = 0.65 * min(1.0, n_bonus / float(max(1, min(n_seated, 4))))
        else:
            # 4 confirmed bonus seats on a single flight (`2x Econ + 2x Prem/Biz`) is 100% of El Al's 2+ cap
            seat_cov = min(1.0, n_bonus / float(max(1, min(n_seated, 4))))

        cpp = float(itinerary.cents_per_point_value or 0.0)
        cpp_norm = min(1.0, max(0.0, cpp / 1.45))

        all_direct = all(
            leg.is_direct
            for leg in (itinerary.outbound_legs + itinerary.inbound_legs)
        )
        sched_quality = 1.0 if all_direct else 0.65

        raw_score = 100.0 * (
            0.50 * seat_cov + 0.30 * cpp_norm + 0.20 * sched_quality
        )

        # Slight risk discount when assuming >2 seats in a single `2+` bucket vs confirmed split/hybrid
        if itinerary.requires_two_plus_seat_verification:
            raw_score -= 4.0
        # Slight penalty when low-CPP (<0.8c) Cash & Points is used
        if cpp > 0.0 and cpp < 0.80:
            raw_score = min(raw_score, 62.0)

        return round(min(100.0, max(0.0, raw_score)), 1)

    def _compute_ctos(
        self,
        vus: float,
        fbvs: float,
        wss: Optional[float] = None,
        has_weather_filter: bool = False,
        min_weather_threshold: float = 0.0,
    ) -> float:
        """Compute Combined Trip Optimization Score (`CTOS`).

        - Unfiltered (`has_weather_filter=False`): `CTOS = round(0.55 * VUS + 0.45 * FBVS, 1)`.
        - Filtered by vacation type (`has_weather_filter=True`):
          `CTOS = round(clamp(0.35 * WSS + 0.35 * VUS + 0.30 * FBVS - 0.50 * max(0, tau_t - WSS), 0, 100), 1)`.
        """
        if not has_weather_filter or wss is None:
            w_cal = float(self._weights.get("ctos_calendar_weight", 0.55))
            w_flt = float(self._weights.get("ctos_flight_weight", 0.45))
            return round(min(100.0, max(0.0, w_cal * float(vus) + w_flt * float(fbvs))), 1)

        w_wea = float(self._weights.get("ctos_filtered_weather_weight", 0.35))
        w_cal_f = float(self._weights.get("ctos_filtered_calendar_weight", 0.35))
        w_flt_f = float(self._weights.get("ctos_filtered_flight_weight", 0.30))
        pen_factor = float(self._weights.get("ctos_sub_threshold_penalty_factor", 0.50))
        base_ctos = w_wea * float(wss) + w_cal_f * float(vus) + w_flt_f * float(fbvs)
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
        cpp = itinerary.cents_per_point_value
        low_cpp_warn = ""
        if cpp is not None and cpp < 0.80:
            low_cpp_warn = f" [אזהרת שווי נקודה נמוך: {cpp:.2f}¢ < 0.80¢]"

        open_jaw_note = ""
        if itinerary.destination_iata != itinerary.return_origin_iata:
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
            f"({itinerary.trip_nights} לילות / {window.total_vacation_days} ימים) | "
            f"אסטרטגיה: {strat}{open_jaw_note} | "
            f"נקודות: {itinerary.total_matmid_points:,} | "
            f"תשלום במזומן: ${itinerary.total_out_of_pocket_cash_usd:,.2f} "
            f"(חיסכון נטו: ${itinerary.net_cash_saved_usd:,.2f}) | "
            f"ציונים: VUS={window.vacation_utilization_score}, FBVS={fbvs}{weather_note}, CTOS={ctos}"
            f"{low_cpp_warn}{weather_tail}"
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
                    -(r.economy_award_seats + r.premium_award_seats + r.business_award_seats),
                    -r.premium_award_seats,
                    -r.economy_award_seats,
                    r.flight_number,
                )
            )
            in_rows.sort(
                key=lambda r: (
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
        if mode == DateSelectionMode.SPECIFIC_DATES:
            cap = 5 if len(expanded_destinations) <= 4 else 2
            return all_windows[:cap]

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

            # Second priority: windows with one-way award availability
            for w in all_windows:
                if len(selected) >= live_cap:
                    break
                pair = (w.start_date, w.end_date)
                if (w.start_date in out_dates or w.end_date in in_dates) and pair not in seen_pairs:
                    seen_pairs.add(pair)
                    selected.append(w)

        # 1. Include any canonical benchmark windows present in `all_windows`
        for w in all_windows:
            pair = (w.start_date, w.end_date)
            if pair in canonical_pairs and pair not in seen_pairs:
                seen_pairs.add(pair)
                selected.append(w)

        # 2. Fill with top-ranked windows by VUS
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
    ) -> list[VacationOptionProposal]:
        """Execute end-to-end vacation search across Date Modes 1/2/3 and Airline Modes 1/2."""
        query = (
            query_data
            if isinstance(query_data, FlightSearchQuery)
            else FlightSearchQuery.from_dict(query_data)
        )

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
                or build_default_family_profile()
            )

        query.family_profile_id = active_profile.id
        if self.repository.get_profile(active_profile.id) is None:
            self.repository.save_profile(active_profile)

        expanded_destinations = self.elal_adapter.expand_metro_iatas(query.destination_iatas)
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
            self.repository.save_search_query(query)
            return []

        # When ANYWHERE (25 destinations) is requested:
        # - In live mode: check all destinations.
        # - In offline mode with an active vacation-type filter: rank all 25 destinations by average
        #   weather suitability (`WSS`) across candidate windows and keep top 14 + all passing `effective_tau`.
        # - In offline mode without a vacation-type filter: keep the 14 canonical destinations.
        if len(expanded_destinations) > 10 and not self.repository.is_live_fetch_mode():
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
        else:
            active_destinations = list(expanded_destinations)

        candidate_windows = self._select_candidate_windows(
            query=query,
            profile=active_profile,
            expanded_destinations=active_destinations,
        )
        if not candidate_windows:
            self.repository.save_search_query(query)
            return []

        airline_mode = (
            query.airline_selection_mode.value
            if isinstance(query.airline_selection_mode, Enum)
            else str(query.airline_selection_mode).strip().upper()
        )
        n_seated, _ = FamilyBaggageNormalizer.count_seated_and_lap_passengers(active_profile)

        raw_proposals: list[VacationOptionProposal] = []

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

                rt_bench_per_pax = float(meta.get("rt_cash_per_pax_usd", 590.0))

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
                                cash_benchmark_per_pax=rt_bench_per_pax,
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

                    # Evaluate all 6 bonus strategies on (out_aw, in_aw)
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
                            cash_benchmark_per_pax=rt_bench_per_pax,
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
                            cash_benchmark_per_pax=rt_bench_per_pax,
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
            if (
                airline_mode == "EL_AL_ONLY"
                and query.search_elal_bonus_tickets
                and len(active_destinations) >= 2
            ):
                for d_out in active_destinations:
                    for d_in in active_destinations:
                        if not _are_open_jaw_compatible(d_out, d_in):
                            continue
                        out_aw = window_outbound_by_dest.get(d_out)
                        in_aw = window_inbound_by_dest.get(d_in)
                        if out_aw is None or in_aw is None:
                            continue
                        bench_oj = float(
                            DESTINATION_CATALOG.get(d_out, {}).get("rt_cash_per_pax_usd", 590.0)
                        )
                        oj_dict = self.wallet_engine.allocate_family_tickets(
                            profile=active_profile,
                            outbound_award=out_aw,
                            inbound_award=in_aw,
                            cash_benchmark_per_pax=bench_oj,
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

        if not raw_proposals:
            self.repository.save_search_query(query)
            return []

        # Finalize FBVS_cash across commercial cash proposals in the batch and compute CTOS
        cash_proposals = [
            p
            for p in raw_proposals
            if p.itinerary is not None
            and p.itinerary.fulfillment_strategy == FulfillmentStrategy.COMMERCIAL_CASH_ONLY
        ]
        if cash_proposals:
            costs = [p.itinerary.total_out_of_pocket_cash_usd for p in cash_proposals if p.itinerary]
            benchmarks = [p.itinerary.full_cash_benchmark_usd for p in cash_proposals if p.itinerary]
            c_min = min(costs)
            c_max = max(max(costs), max(benchmarks) * 1.15, c_min + 250.0)
            denom = max(c_max - c_min, 1.0)
            for p in cash_proposals:
                assert p.itinerary is not None
                cost = p.itinerary.total_out_of_pocket_cash_usd
                all_dir = all(
                    leg.is_direct
                    for leg in (p.itinerary.outbound_legs + p.itinerary.inbound_legs)
                )
                stop_pen = 0.0 if all_dir else 12.0
                fbvs_c = round(
                    min(100.0, max(0.0, 100.0 * (1.0 - (cost - c_min) / denom) - stop_pen)),
                    1,
                )
                p.flight_bonus_value_score = fbvs_c
                p.combined_trip_optimization_score = self._compute_ctos(
                    p.vacation_utilization_score,
                    fbvs_c,
                    wss=p.weather_suitability_score,
                    has_weather_filter=has_weather_filter,
                    min_weather_threshold=effective_tau,
                )
                p.explanation_summary_he = self._build_explanation_he(
                    window=CandidateVacationWindow(
                        start_date=p.itinerary.departure_date,
                        end_date=p.itinerary.return_date,
                        total_vacation_days=p.total_vacation_days,
                        trip_nights=p.itinerary.trip_nights,
                        window_set_type=p.window_set_type,
                        associated_holiday_codes=p.associated_holiday_codes,
                        parent_pto_days_used=p.parent_pto_days_used,
                        pto_efficiency_ratio=p.pto_efficiency_ratio,
                        school_absence_penalty=p.school_absence_penalty,
                        childcare_coverage_gain=p.childcare_coverage_gain,
                        vacation_utilization_score=p.vacation_utilization_score,
                    ),
                    itinerary=p.itinerary,
                    fbvs=fbvs_c,
                    ctos=p.combined_trip_optimization_score,
                    wss=p.weather_suitability_score if has_weather_filter else None,
                    weather_summary_he=(
                        p.weather_metrics.weather_summary_he
                        if p.weather_metrics
                        else ""
                    ),
                )

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

        def _proposal_sort_key(p: VacationOptionProposal) -> tuple[Any, ...]:
            if has_weather_filter:
                return (
                    p.weather_suitability_score >= effective_tau,
                    p.combined_trip_optimization_score,
                    p.weather_suitability_score,
                    p.flight_bonus_value_score,
                    p.vacation_utilization_score,
                    p.itinerary.net_cash_saved_usd if p.itinerary else 0.0,
                )
            return (
                p.combined_trip_optimization_score,
                p.flight_bonus_value_score,
                p.vacation_utilization_score,
                p.itinerary.net_cash_saved_usd if p.itinerary else 0.0,
            )

        # Sort descending
        raw_proposals.sort(key=_proposal_sort_key, reverse=True)

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

        selected_proposals.sort(key=_proposal_sort_key, reverse=True)

        saved_proposals = self.repository.save_search_results(query, selected_proposals)
        return saved_proposals

    def _make_proposal_from_itinerary(
        self,
        query: FlightSearchQuery,
        window: CandidateVacationWindow,
        itinerary: FlightItinerary,
        n_seated: int,
    ) -> VacationOptionProposal:
        itinerary.search_query_id = query.id
        if itinerary.utilizes_elal_bonus:
            fbvs = self._compute_fbvs_bonus(itinerary, n_seated)
        else:
            fbvs = 70.0

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
            window.vacation_utilization_score,
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
            total_vacation_days=window.total_vacation_days,
            parent_pto_days_used=window.parent_pto_days_used,
            pto_efficiency_ratio=window.pto_efficiency_ratio,
            school_absence_penalty=window.school_absence_penalty,
            childcare_coverage_gain=window.childcare_coverage_gain,
            per_child_impact=list(window.per_child_impact),
            total_school_days_missed_across_children=window.total_school_days_missed_across_children,
            max_single_child_school_days_missed=window.max_single_child_school_days_missed,
            vacation_utilization_score=window.vacation_utilization_score,
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

    def compare_proposals(
        self,
        proposal_ids: list[str | VacationOptionProposal | dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a side-by-side `VacationComparisonMatrix` for 1..N proposals (`F28`)."""
        if not proposal_ids:
            raise ValueError("proposal_ids must not be empty")

        proposals: list[VacationOptionProposal] = []
        for item in proposal_ids:
            if isinstance(item, VacationOptionProposal):
                proposals.append(item)
            elif isinstance(item, dict):
                proposals.append(VacationOptionProposal.from_dict(item))
            else:
                loaded = self.repository.get_proposal_by_id(str(item))
                if loaded is not None:
                    proposals.append(loaded)

        if not proposals:
            raise ValueError(f"No matching proposals found for IDs: {proposal_ids!r}")

        best_by_ctos = max(
            proposals,
            key=lambda p: (
                p.combined_trip_optimization_score,
                p.vacation_utilization_score,
                p.flight_bonus_value_score,
            ),
        )
        best_by_savings = max(
            proposals,
            key=lambda p: (
                p.itinerary.net_cash_saved_usd if p.itinerary else 0.0,
                -(p.itinerary.total_out_of_pocket_cash_usd if p.itinerary else 999999.0),
            ),
        )
        best_by_per = max(
            proposals,
            key=lambda p: (
                p.pto_efficiency_ratio,
                -p.parent_pto_days_used,
                p.total_vacation_days,
            ),
        )
        best_by_absence = min(
            proposals,
            key=lambda p: (
                p.school_absence_penalty,
                p.total_school_days_missed_across_children,
                p.max_single_child_school_days_missed,
                -p.combined_trip_optimization_score,
            ),
        )
        best_by_weather = max(
            proposals,
            key=lambda p: (
                p.weather_suitability_score,
                p.combined_trip_optimization_score,
            ),
        )

        def _row(
            key: str, label_he: str, label_en: str, extractor: Any
        ) -> dict[str, Any]:
            vals_by_id = {p.id: extractor(p) for p in proposals}
            return {
                "metric_key": key,
                "label_he": label_he,
                "label_en": label_en,
                "values": vals_by_id,
                "values_list": [vals_by_id[p.id] for p in proposals],
            }

        comparison_rows = [
            _row(
                "destination",
                "יעד",
                "Destination",
                lambda p: (
                    f"{p.itinerary.destination_city_he} ({p.itinerary.destination_iata})"
                    if p.itinerary
                    else ""
                ),
            ),
            _row(
                "dates_and_duration",
                "תאריכים ומשך חופשה",
                "Dates & Duration",
                lambda p: (
                    f"{p.itinerary.departure_date.isoformat()} -> {p.itinerary.return_date.isoformat()} "
                    f"({p.itinerary.trip_nights} לילות / {p.total_vacation_days} ימים)"
                    if p.itinerary
                    else f"{p.total_vacation_days} ימים"
                ),
            ),
            _row(
                "flights",
                "טיסות",
                "Flights",
                lambda p: (
                    " / ".join(
                        [leg.flight_number for leg in p.itinerary.outbound_legs]
                        + [leg.flight_number for leg in p.itinerary.inbound_legs]
                    )
                    if p.itinerary
                    else ""
                ),
            ),
            _row(
                "fulfillment_strategy",
                "אסטרטגיית מימוש כרטיסים",
                "Fulfillment Strategy",
                lambda p: (
                    p.itinerary.fulfillment_strategy.value
                    if p.itinerary
                    and isinstance(p.itinerary.fulfillment_strategy, Enum)
                    else (str(p.itinerary.fulfillment_strategy) if p.itinerary else "")
                ),
            ),
            _row(
                "total_points",
                "סה\"כ נקודות מועדון",
                "Total Loyalty Points",
                lambda p: p.itinerary.total_matmid_points if p.itinerary else 0,
            ),
            _row(
                "out_of_pocket_cash_usd",
                "תשלום במזומן (כולל מסים וכבודה)",
                "Out-of-Pocket Cash (USD)",
                lambda p: p.itinerary.total_out_of_pocket_cash_usd if p.itinerary else 0.0,
            ),
            _row(
                "net_cash_saved_usd",
                "חיסכון נטו במזומן מול מחיר מלא",
                "Net Cash Saved (USD)",
                lambda p: p.itinerary.net_cash_saved_usd if p.itinerary else 0.0,
            ),
            _row(
                "cents_per_point",
                "שווי נקודה (CPP בסנט)",
                "Cents Per Point (CPP)",
                lambda p: p.itinerary.cents_per_point_value if p.itinerary else None,
            ),
            _row(
                "parent_pto_and_per",
                "ימי חופש הורים ומכפיל יעילות (PER)",
                "Parent PTO & PER",
                lambda p: {
                    "parent_pto_days_used": p.parent_pto_days_used,
                    "pto_efficiency_ratio": p.pto_efficiency_ratio,
                },
            ),
            _row(
                "school_days_missed",
                "ימי לימודים שהוחמצו וקנס היעדרות (SAP)",
                "School Absence Impact (SAP)",
                lambda p: {
                    "total_school_days_missed_across_children": p.total_school_days_missed_across_children,
                    "max_single_child_school_days_missed": p.max_single_child_school_days_missed,
                    "school_absence_penalty": p.school_absence_penalty,
                },
            ),
            _row(
                "weather_suitability",
                "התאמת מזג אוויר וסגנון חופשה",
                "Weather & Vacation Style Match",
                lambda p: {
                    "WSS": p.weather_suitability_score,
                    "vacation_type_scores": p.vacation_type_scores,
                    "weather_summary_he": (
                        p.weather_metrics.weather_summary_he
                        if p.weather_metrics
                        else ""
                    ),
                },
            ),
            _row(
                "scores",
                "ציוני אופטימיזציה (VUS / FBVS / WSS / CTOS)",
                "Optimization Scores",
                lambda p: {
                    "VUS": p.vacation_utilization_score,
                    "FBVS": p.flight_bonus_value_score,
                    "WSS": p.weather_suitability_score,
                    "CTOS": p.combined_trip_optimization_score,
                },
            ),
        ]

        matrix = VacationComparisonMatrix(
            proposals=proposals,
            comparison_rows=comparison_rows,
            best_by_ctos_id=best_by_ctos.id,
            best_by_cash_savings_id=best_by_savings.id,
            best_by_per_id=best_by_per.id,
            best_by_minimal_absence_id=best_by_absence.id,
            best_by_weather_id=best_by_weather.id,
        )
        return matrix.to_dict()

    def export_proposal_ics(
        self, proposal_id: str | VacationOptionProposal | dict[str, Any]
    ) -> str:
        """Export a `VacationOptionProposal` as an RFC 5545 iCalendar (`.ics`) document (`F28`)."""
        if isinstance(proposal_id, VacationOptionProposal):
            prop = proposal_id
        elif isinstance(proposal_id, dict):
            prop = VacationOptionProposal.from_dict(proposal_id)
        else:
            loaded = self.repository.get_proposal_by_id(str(proposal_id))
            if loaded is None:
                raise ValueError(f"VacationOptionProposal not found: {proposal_id!r}")
            prop = loaded

        itin = prop.itinerary
        now_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dep_date = itin.departure_date if itin else date(2027, 4, 11)
        ret_date = itin.return_date if itin else date(2027, 4, 18)
        dest_he = itin.destination_city_he if itin else "חופשה"
        dest_en = itin.destination_city_en if itin else "Rome"
        dest_iata = itin.destination_iata if itin else "FCO"
        orig_iata = itin.origin_iata if itin else "TLV"
        ret_orig_iata = itin.return_origin_iata if itin else dest_iata

        def _fmt_dt(d: date, hhmm: str) -> str:
            parts = str(hhmm or "08:00").strip().split(":")
            hh = int(parts[0]) if parts and parts[0].isdigit() else 8
            mm = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            return f"{d.strftime('%Y%m%d')}T{hh:02d}{mm:02d}00"

        lines: list[str] = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//FamilyVacationPlanner//MoE-ElAl-Bonus-Planner//HE",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:חופשה משפחתית - {dest_he} ({dest_en} / {dest_iata})",
            "X-WR-TIMEZONE:Asia/Jerusalem",
        ]

        # 1. Outbound Flight VEVENT
        out_leg = itin.outbound_legs[0] if (itin and itin.outbound_legs) else None
        out_fnum = out_leg.flight_number if out_leg else "LY381"
        out_dep_t = out_leg.departure_time_local if out_leg else "07:15"
        out_arr_t = out_leg.arrival_time_local if out_leg else "10:00"
        out_arr_date = (
            dep_date + timedelta(days=1) if out_arr_t < out_dep_t else dep_date
        )
        strategy_str = (
            itin.fulfillment_strategy.value
            if (itin and isinstance(itin.fulfillment_strategy, Enum))
            else (str(itin.fulfillment_strategy) if itin else "HYBRID_BONUS_PLUS_CASH")
        )
        pts_used = itin.total_matmid_points if itin else 0
        cash_used = itin.total_out_of_pocket_cash_usd if itin else 0.0
        saved_usd = itin.net_cash_saved_usd if itin else 0.0

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{prop.id}-outbound@familyvacationplanner.local",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART:{_fmt_dt(dep_date, out_dep_t)}",
                f"DTEND:{_fmt_dt(out_arr_date, out_arr_t)}",
                f"SUMMARY:טיסת הלוך {out_fnum} ({orig_iata} -> {dest_iata}) - {dest_he} ({dest_en})",
                f"LOCATION:{orig_iata}",
                (
                    f"DESCRIPTION:אסטרטגיה: {strategy_str} | נקודות: {pts_used} | "
                    f"מזומן: ${cash_used:.2f} | חיסכון: ${saved_usd:.2f}"
                ),
                "END:VEVENT",
            ]
        )

        # 2. Inbound Flight VEVENT
        in_leg = itin.inbound_legs[0] if (itin and itin.inbound_legs) else None
        in_fnum = in_leg.flight_number if in_leg else "LY384"
        in_dep_t = in_leg.departure_time_local if in_leg else "21:45"
        in_arr_t = in_leg.arrival_time_local if in_leg else "02:10"
        in_arr_date = (
            ret_date + timedelta(days=1) if in_arr_t < in_dep_t else ret_date
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{prop.id}-inbound@familyvacationplanner.local",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART:{_fmt_dt(ret_date, in_dep_t)}",
                f"DTEND:{_fmt_dt(in_arr_date, in_arr_t)}",
                f"SUMMARY:טיסת חזור {in_fnum} ({ret_orig_iata} -> {orig_iata})",
                f"LOCATION:{ret_orig_iata}",
                f"DESCRIPTION:טיסת חזור מ{dest_he} ({ret_orig_iata} -> {orig_iata})",
                "END:VEVENT",
            ]
        )

        # 3. MoE Holiday, Nitzanim & Per-Child School Impact VEVENT
        child_notes = " ; ".join(
            f"{c.child_name} ({c.framework_type.value if isinstance(c.framework_type, Enum) else (c.framework_type or 'ללא מסגרת')}): "
            f"חופשה={c.official_vacation_days}, ניצנים={c.nitzanim_days_overlapped}, ימי גשר={c.bridge_school_days_missed}"
            for c in prop.per_child_impact
        )
        holidays_str = ", ".join(prop.associated_holiday_codes) or "SPECIFIC_DATES"
        exclusive_end = (ret_date + timedelta(days=1)).strftime("%Y%m%d")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{prop.id}-moe-calendar@familyvacationplanner.local",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;VALUE=DATE:{dep_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{exclusive_end}",
                f"SUMMARY:לוח חופשות משרד החינוך וניצנים - {dest_he} ({holidays_str})",
                f"DESCRIPTION:VUS={prop.vacation_utilization_score} | SAP={prop.school_absence_penalty} | CCG={prop.childcare_coverage_gain} | {child_notes}",
                "END:VEVENT",
            ]
        )

        # 4. Parent PTO Reminder VEVENT
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{prop.id}-parent-pto@familyvacationplanner.local",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;VALUE=DATE:{dep_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{exclusive_end}",
                f"SUMMARY:תזכורת דיווח חופשה להורים (PTO: {prop.parent_pto_days_used} ימים | PER: {prop.pto_efficiency_ratio}x)",
                f"DESCRIPTION:סה\"כ {prop.total_vacation_days} ימי חופשה משפחתית תמורת {prop.parent_pto_days_used} ימי חופש הורים (CTOS={prop.combined_trip_optimization_score})",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        return "\r\n".join(lines) + "\r\n"
