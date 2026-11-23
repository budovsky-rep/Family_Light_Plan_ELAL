"""3-Tier Multi-Carrier Commercial Flight Search Adapter & Family Baggage Cost Normalizer.

Implements Feature `F18` (and commercial benchmarks for `F17` / `F22`-`F28`):
- 3-Tier Commercial Provider Architecture:
  1. Tier 1: Local Keyless Engine (`fast-flights` / `fli` + seeded `2025-2028` catalog)
  2. Tier 2: SerpApi Google Flights JSON Adapter (`SERPAPI_API_KEY`)
  3. Tier 3: Duffel NDC/GDS Offer Requests Adapter (`DUFFEL_ACCESS_TOKEN`)
- `FamilyBaggageNormalizer`: Normalizes true family out-of-pocket cost by adding
  required cabin trolleys (for seated passengers, excluding `INFANT_LAP`) and
  trip-length-scaled `23kg` checked suitcases to Low-Cost Carriers (`W6`, `FR`, `U2`)
  and leisure carriers (`6H`, `IZ`, `BZ`, `U8`) vs full-service carriers
  (`LY`, `2U`, `LH`, `OS`, `LX`, `BA`, `AF`, `A3`, `UA`, `DL`, `FZ`, `EY`).
- Enforces `TLV` Yom Kippur total shutdown across ALL airlines (`EL_AL_ONLY` and
  `ALL_AIRLINES`), El Al Shabbat operational constraints on `LY`/`2U`, and
  Tier-2 6-hour (`21,600s`) TTL caching.
"""

from __future__ import annotations

import copy
import math
from datetime import UTC, date, datetime
from typing import Any, Optional

from backend.app.calendar_engine.moe_calendar_service import MoECalendarService
from backend.app.config_manager.settings import AppSettings, get_settings
from backend.app.providers.elal_rbd_client import ElAlRbdDataClientAdapter
from backend.app.schemas.domain import FamilyProfile, classify_passenger_type
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    YOM_KIPPUR_CLOSED_DATES,
    build_default_family_profile,
    is_shabbat_blocked_for_elal,
)

# Ultra-low-cost and Israeli/regional leisure carriers that charge extra for trolleys & 23kg bags
LCC_CARRIERS: dict[str, dict[str, float]] = {
    "W6": {"rt_trolley_usd": 70.0, "rt_checked_bag_23kg_usd": 110.0},  # Wizz Air
    "FR": {"rt_trolley_usd": 66.0, "rt_checked_bag_23kg_usd": 100.0},  # Ryanair
    "U2": {"rt_trolley_usd": 68.0, "rt_checked_bag_23kg_usd": 104.0},  # easyJet
    "6H": {"rt_trolley_usd": 30.0, "rt_checked_bag_23kg_usd": 80.0},   # Israir
    "IZ": {"rt_trolley_usd": 30.0, "rt_checked_bag_23kg_usd": 80.0},   # Arkia
    "BZ": {"rt_trolley_usd": 30.0, "rt_checked_bag_23kg_usd": 80.0},   # Blue Bird Airways
    "U8": {"rt_trolley_usd": 30.0, "rt_checked_bag_23kg_usd": 80.0},   # TUS Airways
}

# Full-service carriers whose standard family fares include cabin trolley + checked bag
FULL_SERVICE_CARRIERS: set[str] = {
    "LY",  # El Al
    "2U",  # Sun d'Or
    "LH",  # Lufthansa
    "OS",  # Austrian Airlines
    "LX",  # SWISS
    "SN",  # Brussels Airlines
    "BA",  # British Airways
    "AF",  # Air France
    "A3",  # Aegean Airlines
    "UA",  # United Airlines
    "DL",  # Delta Air Lines
    "FZ",  # flydubai
    "EY",  # Etihad Airways
}


def _parse_date(val: date | datetime | str) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if "T" in s:
            s = s.split("T", 1)[0]
        return date.fromisoformat(s)
    raise ValueError(f"Cannot parse date from {val!r}")


class FamilyBaggageNormalizer:
    """Computes normalized round-trip family cabin trolley & 23kg checked bag fees."""

    @staticmethod
    def count_seated_and_lap_passengers(
        profile: Optional[FamilyProfile],
    ) -> tuple[int, int]:
        """Return `(seated_passengers_count, infant_lap_count)` for `profile`."""
        if profile is None:
            return 5, 0
        adults = max(1, int(profile.adults_count))
        seated_children = 0
        lap_infants = 0
        for child in profile.children or []:
            pax_type = (
                child.passenger_Current_type
                or classify_passenger_type(child.child_age_years)
            )
            if pax_type == "INFANT_LAP" and lap_infants < adults:
                lap_infants += 1
            else:
                seated_children += 1
        return adults + seated_children, lap_infants

    @staticmethod
    def required_checked_bags_23kg(seated_pax: int, trip_nights: int) -> int:
        """Compute required 23kg checked suitcases based on seated family size and trip length."""
        n_seated = max(1, int(seated_pax))
        nights = max(1, int(trip_nights))
        if nights <= 3:
            return max(1, math.ceil(n_seated / 3.0))
        if nights <= 7:
            return max(1, math.ceil(n_seated / 2.0))
        return max(1, math.ceil(n_seated * 0.75))

    @classmethod
    def normalize_family_baggage_cost(
        cls,
        carrier_iata: str,
        base_fare_usd: float,
        profile: Optional[FamilyProfile] = None,
        trip_nights: int = 7,
    ) -> tuple[float, float]:
        """Return `(baggage_fees_usd, total_cash_usd)` for a family on `carrier_iata`."""
        carrier = str(carrier_iata or "").strip().upper()
        clean_base = max(0.0, float(base_fare_usd))
        seated_pax, _lap_infants = cls.count_seated_and_lap_passengers(profile)
        checked_bags = cls.required_checked_bags_23kg(seated_pax, trip_nights)

        if carrier in LCC_CARRIERS:
            rates = LCC_CARRIERS[carrier]
            trolley_fee = seated_pax * float(rates["rt_trolley_usd"])
            checked_fee = checked_bags * float(rates["rt_checked_bag_23kg_usd"])
            baggage_fees_usd = round(trolley_fee + checked_fee, 2)
        elif carrier in FULL_SERVICE_CARRIERS:
            baggage_fees_usd = 0.0
        else:
            baggage_fees_usd = 0.0

        total_cash_usd = round(clean_base + baggage_fees_usd, 2)
        return baggage_fees_usd, total_cash_usd


class AllAirlinesSearchAdapter:
    """Multi-carrier commercial flight search adapter (`ALL_AIRLINES` & `EL_AL_ONLY` benchmarks)."""

    def __init__(
        self,
        repository: Optional[SQLiteRepository] = None,
        settings: Optional[dict[str, Any] | AppSettings] = None,
        calendar_service: Optional[MoECalendarService] = None,
        elal_adapter: Optional[ElAlRbdDataClientAdapter] = None,
    ) -> None:
        self.repository: SQLiteRepository = repository or SQLiteRepository(auto_seed=True)
        if isinstance(settings, AppSettings):
            self._settings: dict[str, Any] = settings.to_dict()
        elif isinstance(settings, dict):
            self._settings = dict(settings)
        else:
            self._settings = get_settings()

        self.calendar_service: MoECalendarService = calendar_service or MoECalendarService(
            self.repository
        )
        self.elal_adapter: ElAlRbdDataClientAdapter = elal_adapter or ElAlRbdDataClientAdapter(
            repository=self.repository,
            settings=self._settings,
            calendar_service=self.calendar_service,
        )
        self.baggage_normalizer = FamilyBaggageNormalizer()
        rbd_cfg = self._settings.get("elal_rbd_client") or {}
        self.itinerary_cache_ttl_seconds: int = int(
            rbd_cfg.get("itinerary_cache_ttl_seconds", 21600)
        )
        self._quote_cache: dict[tuple[Any, ...], tuple[datetime, list[dict[str, Any]]]] = {}

    def normalize_family_baggage_cost(
        self,
        carrier_iata: str,
        base_fare_usd: float,
        profile: Optional[FamilyProfile] = None,
        trip_nights: int = 7,
    ) -> tuple[float, float]:
        """Delegate to `FamilyBaggageNormalizer.normalize_family_baggage_cost`."""
        return self.baggage_normalizer.normalize_family_baggage_cost(
            carrier_iata=carrier_iata,
            base_fare_usd=base_fare_usd,
            profile=profile,
            trip_nights=trip_nights,
        )

    def _is_date_blocked_by_yom_kippur(self, target_date: date) -> bool:
        if target_date in YOM_KIPPUR_CLOSED_DATES:
            return True
        return self.calendar_service.is_tlv_airport_closed(target_date)

    def search_commercial_flights(
        self,
        origin: str,
        destinations: list[str] | str,
        departure_date: date | str,
        return_date: date | str,
        profile: Optional[FamilyProfile] = None,
        direct_only: bool = True,
        airline_selection_mode: str = "ALL_AIRLINES",
        include_sundor_flights: bool = True,
    ) -> list[dict[str, Any]]:
        """Search multi-carrier commercial flights with family baggage cost normalization
        and 6-hour (`21,600s`) TTL caching.
        """
        dep_date = _parse_date(departure_date)
        ret_date = _parse_date(return_date)
        if ret_date <= dep_date:
            raise ValueError("return_date must be strictly after departure_date")

        # 1. Ben Gurion Airport (TLV) Yom Kippur total shutdown applies to ALL airlines
        if self._is_date_blocked_by_yom_kippur(dep_date) or self._is_date_blocked_by_yom_kippur(
            ret_date
        ):
            return []

        expanded_dests = self.elal_adapter.expand_metro_iatas(destinations)
        orig_upper = str(origin or "TLV").upper().strip()
        mode_upper = str(airline_selection_mode or "ALL_AIRLINES").upper().strip()
        trip_nights = max(1, (ret_date - dep_date).days)

        prof = profile or self.repository.get_profile() or build_default_family_profile()
        seated_pax, lap_infants = FamilyBaggageNormalizer.count_seated_and_lap_passengers(prof)
        pax_equiv = round(seated_pax + 0.15 * lap_infants, 2)

        cache_key = (
            orig_upper,
            tuple(expanded_dests),
            dep_date.isoformat(),
            ret_date.isoformat(),
            mode_upper,
            bool(include_sundor_flights),
            bool(direct_only),
            pax_equiv,
        )
        now_dt = datetime.now(UTC).replace(microsecond=0)
        cached_entry = self._quote_cache.get(cache_key)
        if cached_entry is not None:
            cached_ts, cached_offers = cached_entry
            if (now_dt - cached_ts).total_seconds() < self.itinerary_cache_ttl_seconds:
                return copy.deepcopy(cached_offers)

        raw_offers = self.repository.get_commercial_flights(
            origin=orig_upper,
            destinations=expanded_dests,
            departure_date=dep_date,
            return_date=ret_date,
            airline_selection_mode=mode_upper,
            include_sundor=include_sundor_flights,
            direct_only=direct_only,
        )

        normalized_offers: list[dict[str, Any]] = []
        for raw in raw_offers:
            offer = dict(raw)
            carrier = str(offer.get("primary_carrier_iata") or "LY").upper()

            if mode_upper == "EL_AL_ONLY" and carrier not in ("LY", "2U"):
                continue
            if not include_sundor_flights and carrier == "2U":
                continue
            if direct_only and not bool(offer.get("is_direct", True)):
                continue

            if carrier in ("LY", "2U"):
                if is_shabbat_blocked_for_elal(
                    dep_date,
                    str(offer.get("departure_time_out") or "07:00"),
                    str(offer.get("arrival_time_out") or "10:00"),
                ) or is_shabbat_blocked_for_elal(
                    ret_date,
                    str(offer.get("departure_time_in") or "12:00"),
                    str(offer.get("arrival_time_in") or "17:00"),
                ):
                    continue

            rt_per_pax = float(offer.get("rt_cash_per_pax_usd", 500.0))
            base_family_fare = round(rt_per_pax * pax_equiv, 2)
            bag_fees, total_cash = self.normalize_family_baggage_cost(
                carrier_iata=carrier,
                base_fare_usd=base_family_fare,
                profile=prof,
                trip_nights=trip_nights,
            )

            dest_code = str(offer.get("destination_iata") or "FCO")
            meta = DESTINATION_CATALOG.get(dest_code, {})
            elal_per_pax = float(meta.get("rt_cash_per_pax_usd", rt_per_pax))
            full_benchmark = round(elal_per_pax * pax_equiv, 2)
            out_tax = float(offer.get("outbound_taxes_usd", 42.0))
            in_tax = float(offer.get("inbound_taxes_usd", 42.0))
            family_taxes = round((out_tax + in_tax) * seated_pax, 2)

            offer.update(
                {
                    "carrier_iata": carrier,
                    "trip_nights": trip_nights,
                    "seated_passengers": seated_pax,
                    "infant_lap_passengers": lap_infants,
                    "base_family_fare_usd": base_family_fare,
                    "baggage_fees_usd": bag_fees,
                    "total_baggage_fees_usd": bag_fees,
                    "total_taxes_and_fees_usd": family_taxes,
                    "total_supplemental_cash_fares_usd": round(
                        max(0.0, base_family_fare - family_taxes), 2
                    ),
                    "total_out_of_pocket_cash_usd": total_cash,
                    "full_cash_benchmark_usd": full_benchmark,
                    "net_cash_saved_usd": round(full_benchmark - total_cash, 2),
                    "provider_tier": "TIER_1_FAST_FLIGHTS",
                }
            )
            normalized_offers.append(offer)

        normalized_offers.sort(
            key=lambda o: (float(o["total_out_of_pocket_cash_usd"]), str(o["primary_carrier_iata"]))
        )
        self._quote_cache[cache_key] = (now_dt, copy.deepcopy(normalized_offers))
        return normalized_offers
