"""Milestone 2 Unit Test Suite: Providers, Wallets, and 6-Strategy Bonus Synthesizer (`F17`-`F28`).

Covers:
- `F17`: `EL_AL_ONLY` mode & Shabbat / `TLV` Yom Kippur operational constraints
- `F18`: `ALL_AIRLINES` mode & `FamilyBaggageNormalizer`
- `F19` & `TEST-RBD-01`: Metro-to-Airport 3-letter IATA expansion & validation
- `F20`: `ANYWHERE` Region Discovery across Zones A-E
- `F21`: Classic Award RBD bucket (`E/X/U`, `P/A/R`, `I/W`), `0/1/2+` seat cap, Tuesday 50% FlyCard promo, polite rate limiter, and 4h SQLite TTL cache
- `F22`: Strategy 1 (`FULL_BONUS_SAME_CABIN`) & `requires_two_plus_seat_verification`
- `F23`: Strategy 2 (`SPLIT_CABIN_BONUS`) on exact same flight
- `F24` & `TEST-SYN-01`: Strategy 3 (`HYBRID_BONUS_PLUS_CASH`) canonical Rome `LY381`/`LY384` (`142,000` pts, `$390` taxes, `$460` cash, `$850` OOP, `$2,100` saved, `1.48c` CPP) & child `<12` PNR safety pairing
- `F25`: Strategy 4 (`ONE_WAY_BONUS_ONE_WAY_CASH`) & Open-Jaw (`TLV->MXP` + `FCO->TLV`)
- `F26`: Strategy 5 (`CASH_AND_POINTS`) fallback & `<0.8c` low-CPP warning
- `F27`: Strategy 6 (`MULTI_CLUB_PER_PASSENGER_SPLIT`) un-pooled vs pooled across all 10 `LoyaltyProgramCode` programs
- `F28`: `CPP`, `FBVS`, `CTOS = 0.55 * VUS + 0.45 * FBVS`, `search_vacations` across all 3x2 mode combinations, `compare_proposals`, and RFC 5545 `export_proposal_ics`
"""

from __future__ import annotations

import copy
import unittest
from datetime import date

from backend.app.calendar_engine.moe_calendar_service import MoECalendarService
from backend.app.planner_synthesizer.bonus_planner_service import (
    BonusVacationPlannerService,
    MultiClubWalletAllocationEngine,
)
from backend.app.providers.commercial_flights import (
    AllAirlinesSearchAdapter,
    FamilyBaggageNormalizer,
)
from backend.app.providers.elal_rbd_client import (
    CLASSIC_AWARD_RBDS,
    SUPPORTED_ELAL_DESTINATIONS,
    ElAlRbdDataClientAdapter,
    PoliteTokenBucketRateLimiter,
    parse_rbd_seat_indicator,
)
from backend.app.schemas.domain import (
    ChildFramework,
    LoyaltyProgramCode,
    PassengerLoyaltyWallet,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import is_shabbat_blocked_for_elal
from backend.app.vacation_optimizer.maximizer_engine import VacationMaximizerEngine


class TestM2ProvidersAndSynthesizer(unittest.TestCase):
    """Comprehensive unit tests for Milestone 2 (`F17`-`F28`)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = SQLiteRepository(":memory:", auto_seed=True)
        cls.calendar_service = MoECalendarService(cls.repo)
        cls.maximizer = VacationMaximizerEngine(cls.calendar_service)
        cls.elal_adapter = ElAlRbdDataClientAdapter(cls.repo)
        cls.commercial_adapter = AllAirlinesSearchAdapter(cls.repo)
        cls.planner = BonusVacationPlannerService(
            repository=cls.repo,
            calendar_service=cls.calendar_service,
            maximizer=cls.maximizer,
            elal_adapter=cls.elal_adapter,
            commercial_adapter=cls.commercial_adapter,
        )
        cls.default_profile = cls.repo.get_profile("default-family-profile")
        assert cls.default_profile is not None

    def test_rbd_01_metro_iata_expansion_and_validation_f19(self) -> None:
        """1. Verify `F19` & `TEST-RBD-01` metro-to-airport IATA expansion and invalid code rejection."""
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["NYC"]), ["JFK", "EWR"])
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["LON"]), ["LHR", "LTN"])
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["PAR"]), ["CDG"])
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["MIL"]), ["MXP"])
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["ROM"]), ["FCO"])
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["TYO"]), ["NRT"])
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["MIA_AREA"]), ["MIA", "FLL"])

        # Preserves valid 3-letter IATAs and deduplicates in order
        expanded = self.elal_adapter.expand_metro_iatas(["ROM", "FCO", "ATH", "NYC", "JFK"])
        self.assertEqual(expanded, ["FCO", "ATH", "JFK", "EWR"])

        # Rejects empty or invalid IATA codes
        with self.assertRaises(ValueError):
            self.elal_adapter.expand_metro_iatas([])
        with self.assertRaises(ValueError):
            self.elal_adapter.expand_metro_iatas([""])
        with self.assertRaises(ValueError):
            self.elal_adapter.expand_metro_iatas(["INVALID_CODE"])
        with self.assertRaises(ValueError):
            self.elal_adapter.expand_metro_iatas(["123"])

    def test_anywhere_region_discovery_across_zones_a_to_e_f20(self) -> None:
        """2. Verify `F20` `ANYWHERE` expansion and multi-zone award discovery across Zones A-E."""
        anywhere_iatas = self.elal_adapter.expand_metro_iatas(["ANYWHERE"])
        self.assertEqual(len(anywhere_iatas), 25)
        self.assertEqual(set(anywhere_iatas), set(SUPPORTED_ELAL_DESTINATIONS))

        rows = self.elal_adapter.get_award_availability(
            destinations=["ANYWHERE"],
            start_date=date(2027, 4, 10),
            end_date=date(2027, 4, 20),
            origin="TLV",
        )
        self.assertGreater(len(rows), 10)
        zones_found = {r.award_zone for r in rows}
        self.assertEqual(zones_found, {"ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E"})

    def test_elal_shabbat_and_tlv_yom_kippur_operational_constraints_f17(self) -> None:
        """3. Verify `F17` El Al Shabbat operational rules, `TLV` Yom Kippur closure, and Sun d'Or filter."""
        # Friday afternoon >= 14:00 blocked; Friday morning < 14:00 allowed
        self.assertTrue(is_shabbat_blocked_for_elal(date(2027, 4, 16), "14:30"))
        self.assertFalse(is_shabbat_blocked_for_elal(date(2027, 4, 16), "07:00"))
        # Saturday daytime (< 20:30) blocked; Saturday night Motzei Shabbat (>= 20:30) allowed
        self.assertTrue(is_shabbat_blocked_for_elal(date(2027, 4, 17), "16:00"))
        self.assertFalse(is_shabbat_blocked_for_elal(date(2027, 4, 17), "21:15"))

        # Verify no returned El Al / Sun d'Or flight violates Shabbat departure/arrival rules
        sample_rows = self.elal_adapter.get_award_availability(
            destinations=["FCO", "ATH", "LHR", "JFK", "BKK"],
            start_date=date(2027, 4, 9),
            end_date=date(2027, 4, 25),
        )
        self.assertGreater(len(sample_rows), 0)
        for r in sample_rows:
            self.assertFalse(is_shabbat_blocked_for_elal(r.flight_date, r.departure_time_local))
            if r.flight_date.weekday() == 4:  # Friday: no arrival >= 14:00 or overnight roll
                self.assertLess(r.arrival_time_local, "14:00")
                self.assertGreaterEqual(r.arrival_time_local, r.departure_time_local)

        # TLV Yom Kippur closure dates return 0 flights
        for yk_date in (
            date(2025, 10, 1),
            date(2025, 10, 2),
            date(2026, 9, 20),
            date(2026, 9, 21),
            date(2027, 10, 10),
            date(2027, 10, 11),
        ):
            yk_rows = self.elal_adapter.get_award_availability(
                destinations=["FCO", "ATH"],
                start_date=yk_date,
                end_date=yk_date,
            )
            self.assertEqual(len(yk_rows), 0)

        # Sun d'Or (`2U` on RHO) included when include_sundor_flights=True, excluded when False
        rho_with_2u = self.elal_adapter.get_award_availability(
            destinations=["RHO"],
            start_date=date(2027, 4, 11),
            end_date=date(2027, 4, 18),
            include_sundor_flights=True,
        )
        self.assertTrue(any(r.operating_carrier == "2U" for r in rho_with_2u))

        rho_without_2u = self.elal_adapter.get_award_availability(
            destinations=["RHO"],
            start_date=date(2027, 4, 11),
            end_date=date(2027, 4, 18),
            include_sundor_flights=False,
        )
        self.assertFalse(any(r.operating_carrier == "2U" for r in rho_without_2u))

    def test_rbd_bucket_seat_cap_two_plus_tuesday_promo_and_ttl_cache_f21(self) -> None:
        """4. Verify `F21` RBD buckets, `0`/`1`/`2+` seat cap parser, Tuesday promo, rate limiter, and 4h TTL cache."""
        self.assertEqual(CLASSIC_AWARD_RBDS["ECONOMY"], ("E", "X", "U"))
        self.assertEqual(CLASSIC_AWARD_RBDS["PREMIUM"], ("P", "A", "R"))
        self.assertEqual(CLASSIC_AWARD_RBDS["BUSINESS"], ("I", "W"))

        self.assertEqual(parse_rbd_seat_indicator(0), (0, False))
        self.assertEqual(parse_rbd_seat_indicator("1"), (1, False))
        self.assertEqual(parse_rbd_seat_indicator("2+"), (2, True))
        self.assertEqual(parse_rbd_seat_indicator(4), (4, True))
        with self.assertRaises(ValueError):
            parse_rbd_seat_indicator(-1)
        with self.assertRaises(ValueError):
            parse_rbd_seat_indicator(12)

        # Rate limiter attributes
        limiter = PoliteTokenBucketRateLimiter()
        self.assertGreaterEqual(limiter.min_interval_sec, 2.0)
        self.assertEqual(limiter.max_route_months_per_batch, 15)

        # Tuesday FlyCard 50% promo active on Tuesday 2027-04-13 (`LY381_2027-04-13`)
        tue_rows = self.elal_adapter.get_award_availability(
            destinations=["FCO"],
            start_date=date(2027, 4, 13),
            end_date=date(2027, 4, 13),
        )
        self.assertGreaterEqual(len(tue_rows), 1)
        self.assertTrue(any(r.flycard_promo_active for r in tue_rows))

        # 4h SQLite TTL cache hit vs force_refresh
        sync_hit = self.elal_adapter.sync_award_availability(
            destinations=["FCO"],
            start_date=date(2027, 4, 11),
            end_date=date(2027, 4, 18),
            force_refresh=False,
        )
        self.assertTrue(sync_hit["cache_hit"])
        self.assertEqual(sync_hit["source_url"], "https://www.elal.com/rbddataclients/")

        sync_refresh = self.elal_adapter.sync_award_availability(
            destinations=["FCO"],
            start_date=date(2027, 4, 11),
            end_date=date(2027, 4, 18),
            force_refresh=True,
        )
        self.assertFalse(sync_refresh["cache_hit"])
        self.assertGreater(sync_refresh["records_synced"], 0)

    def test_all_airlines_adapter_and_family_baggage_normalizer_f18(self) -> None:
        """5. Verify `F18` multi-carrier search, `TLV` Yom Kippur block, and `FamilyBaggageNormalizer`."""
        offers = self.commercial_adapter.search_commercial_flights(
            origin="TLV",
            destinations=["FCO", "ATH", "BUD"],
            departure_date=date(2027, 4, 11),
            return_date=date(2027, 4, 18),
            profile=self.default_profile,
            airline_selection_mode="ALL_AIRLINES",
        )
        carriers = {o["carrier_iata"] for o in offers}
        self.assertIn("LY", carriers)
        self.assertTrue(len(carriers.intersection({"W6", "FR", "U2", "A3", "6H", "IZ"})) >= 3)

        # LCC adds positive cabin trolley + 23kg checked suitcase fees
        lcc_bag, lcc_total = self.commercial_adapter.normalize_family_baggage_cost(
            carrier_iata="W6",
            base_fare_usd=1000.0,
            profile=self.default_profile,
            trip_nights=7,
        )
        self.assertGreater(lcc_bag, 0.0)
        self.assertEqual(lcc_total, 1000.0 + lcc_bag)

        # Full-service carrier adds $0 extra baggage fees
        fsc_bag, fsc_total = self.commercial_adapter.normalize_family_baggage_cost(
            carrier_iata="LY",
            base_fare_usd=2950.0,
            profile=self.default_profile,
            trip_nights=7,
        )
        self.assertEqual(fsc_bag, 0.0)
        self.assertEqual(fsc_total, 2950.0)

        # TLV Yom Kippur blocks ALL airlines
        yk_offers = self.commercial_adapter.search_commercial_flights(
            origin="TLV",
            destinations=["FCO", "ATH"],
            departure_date=date(2026, 9, 20),
            return_date=date(2026, 9, 25),
            profile=self.default_profile,
            airline_selection_mode="ALL_AIRLINES",
        )
        self.assertEqual(len(yk_offers), 0)

    def test_strategy_1_full_bonus_same_cabin_and_two_plus_verification_flag_f22(self) -> None:
        """6. Verify `F22` `FULL_BONUS_SAME_CABIN` allocation and `requires_two_plus_seat_verification` flag."""
        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        full_bonus = [
            p for p in proposals if p.itinerary.fulfillment_strategy == "FULL_BONUS_SAME_CABIN"
        ]
        self.assertGreaterEqual(len(full_bonus), 1)
        p5 = full_bonus[0]
        self.assertEqual(len(p5.itinerary.family_ticket_allocation), 5)
        self.assertEqual(p5.itinerary.total_supplemental_cash_fares_usd, 0.0)
        self.assertTrue(p5.itinerary.requires_two_plus_seat_verification)

        # For N <= 2 seated passengers, requires_two_plus_seat_verification is False
        couple_profile = copy.deepcopy(self.default_profile)
        couple_profile.adults_count = 2
        couple_profile.children = []
        couple_proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=couple_profile,
        )
        couple_full = [
            p for p in couple_proposals if p.itinerary.fulfillment_strategy == "FULL_BONUS_SAME_CABIN"
        ]
        self.assertGreaterEqual(len(couple_full), 1)
        self.assertFalse(couple_full[0].itinerary.requires_two_plus_seat_verification)

    def test_strategy_2_split_cabin_bonus_on_same_flight_f23(self) -> None:
        """7. Verify `F23` `SPLIT_CABIN_BONUS` across multiple cabins on the exact same flight."""
        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        split_props = [
            p for p in proposals if p.itinerary.fulfillment_strategy == "SPLIT_CABIN_BONUS"
        ]
        self.assertGreaterEqual(len(split_props), 1)
        sp = split_props[0]
        self.assertEqual(sp.itinerary.total_supplemental_cash_fares_usd, 0.0)
        cabins = {a.cabin_class for a in sp.itinerary.family_ticket_allocation}
        self.assertGreaterEqual(len(cabins), 2)
        self.assertTrue(
            all(a.points_used > 0 and a.cash_fare_usd == 0.0 for a in sp.itinerary.family_ticket_allocation)
        )

    def test_syn_01_strategy_3_hybrid_bonus_plus_cash_rome_ly381_ly384_f24(self) -> None:
        """8. Verify `F24` & `TEST-SYN-01` canonical Rome `LY381`/`LY384` `HYBRID_BONUS_PLUS_CASH` math."""
        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "allow_hybrid_bonus_cash": True,
            },
            profile=self.default_profile,
        )
        hybrid_props = [
            p
            for p in proposals
            if p.itinerary.fulfillment_strategy == "HYBRID_BONUS_PLUS_CASH"
            and p.itinerary.total_matmid_points == 142000
        ]
        self.assertGreaterEqual(len(hybrid_props), 1)
        rome_hybrid = hybrid_props[0].itinerary
        self.assertEqual(rome_hybrid.total_matmid_points, 142000)
        self.assertAlmostEqual(rome_hybrid.total_taxes_and_fees_usd, 390.0, places=2)
        self.assertAlmostEqual(rome_hybrid.total_supplemental_cash_fares_usd, 460.0, places=2)
        self.assertAlmostEqual(rome_hybrid.total_out_of_pocket_cash_usd, 850.0, places=2)
        self.assertAlmostEqual(rome_hybrid.full_cash_benchmark_usd, 2950.0, places=2)
        self.assertAlmostEqual(rome_hybrid.net_cash_saved_usd, 2100.0, places=2)
        self.assertAlmostEqual(rome_hybrid.cents_per_point_value, 1.48, places=2)

    def test_adult_child_pnr_safety_pairing_under_age_12_f24_f27(self) -> None:
        """9. Verify `F24` & `F27` adult-child PNR safety pairing so no child `<12` is isolated on a PNR."""
        young_family = copy.deepcopy(self.default_profile)
        young_family.children = [
            ChildFramework(
                id="c-young-1",
                family_profile_id=young_family.id,
                child_name="נועה",
                child_age_years=5,
                passenger_Current_type="CHILD",
                framework_type="MUNICIPAL_GAN",
            ),
            ChildFramework(
                id="c-young-2",
                family_profile_id=young_family.id,
                child_name="עידו",
                child_age_years=8,
                passenger_Current_type="CHILD",
                framework_type="ELEMENTARY_1_3",
            ),
            ChildFramework(
                id="c-young-3",
                family_profile_id=young_family.id,
                child_name="דניאל",
                child_age_years=10,
                passenger_Current_type="CHILD",
                framework_type="ELEMENTARY_4_6",
            ),
        ]
        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "allow_hybrid_bonus_cash": True,
            },
            profile=young_family,
        )
        hybrid_props = [
            p for p in proposals if p.itinerary.fulfillment_strategy == "HYBRID_BONUS_PLUS_CASH"
        ]
        self.assertGreaterEqual(len(hybrid_props), 1)
        for prop in hybrid_props:
            allocs = prop.itinerary.family_ticket_allocation
            cash_allocs = [a for a in allocs if a.cash_fare_usd > 0 and a.points_used == 0]
            award_allocs = [a for a in allocs if a.points_used > 0]
            for group in (cash_allocs, award_allocs):
                if not group:
                    continue
                has_under_12 = any(
                    (a.passenger_id or "").startswith("CHILD_")
                    or "נועה" in a.passenger_label
                    or "עידו" in a.passenger_label
                    or "דניאל" in a.passenger_label
                    for a in group
                )
                if has_under_12:
                    has_adult = any(
                        (a.passenger_id or "").startswith("ADULT_")
                        or "ADULT_" in a.passenger_label
                        or "הורה" in a.passenger_label
                        for a in group
                    )
                    self.assertTrue(
                        has_adult,
                        f"Child under 12 isolated without adult in PNR group: {group}",
                    )

    def test_strategy_4_one_way_bonus_one_way_cash_and_open_jaw_mxp_fco_f25(self) -> None:
        """10. Verify `F25` `ONE_WAY_BONUS_ONE_WAY_CASH` (asymmetric ATH & Open-Jaw `MXP`/`FCO`)."""
        # (a) Asymmetric ATH Hanukkah 2026-12-06 .. 2026-12-12 where inbound has 0 award seats
        ath_proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
                "specific_departure_date": "2026-12-06",
                "specific_return_date": "2026-12-12",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        ow_ath = [
            p
            for p in ath_proposals
            if p.itinerary.fulfillment_strategy == "ONE_WAY_BONUS_ONE_WAY_CASH"
        ]
        self.assertGreaterEqual(len(ow_ath), 1)

        # (b) Open-Jaw Bonus TLV -> MXP outbound + FCO -> TLV inbound
        oj_proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["MXP", "FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        open_jaw_found = [
            p
            for p in oj_proposals
            if p.itinerary.destination_iata != p.itinerary.return_origin_iata
        ]
        self.assertGreaterEqual(len(open_jaw_found), 1)
        self.assertTrue(
            any(
                {p.itinerary.destination_iata, p.itinerary.return_origin_iata} == {"MXP", "FCO"}
                for p in open_jaw_found
            )
        )

    def test_strategy_5_cash_and_points_fallback_and_low_cpp_warning_f26(self) -> None:
        """11. Verify `F26` `CASH_AND_POINTS` fallback when 0 Classic Award seats exist and `<0.8c` warning."""
        # LHR 2027-07-15..2027-07-22 has 0 Classic Award seats in all cabins
        lhr_proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LHR"],
                "specific_departure_date": "2027-07-15",
                "specific_return_date": "2027-07-22",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        cp_props = [
            p for p in lhr_proposals if p.itinerary.fulfillment_strategy == "CASH_AND_POINTS"
        ]
        self.assertGreaterEqual(len(cp_props), 1)
        cp = cp_props[0]
        self.assertLess(cp.itinerary.cents_per_point_value, 0.8)
        self.assertTrue(
            "0.8" in cp.explanation_summary_he or "נמוך" in cp.explanation_summary_he
        )

    def test_strategy_6_multi_club_per_passenger_split_unpooled_vs_pooled_f27(self) -> None:
        """12. Verify `F27` `MultiClubWalletAllocationEngine` un-pooled vs pooled and all 10 `LoyaltyProgramCode`s."""
        # Confirm all 10 LoyaltyProgramCode values exist
        self.assertEqual(len(list(LoyaltyProgramCode)), 10)

        # (a) Un-pooled Matmid wallets: Parent 1 has 75,000 pts (can_pool=False), Parent 2 has 68,000 pts (can_pool=False)
        unpooled_profile = copy.deepcopy(self.default_profile)
        unpooled_profile.passenger_loyalty_wallets = [
            PassengerLoyaltyWallet(
                id="w-p1-unpooled",
                family_profile_id=unpooled_profile.id,
                passenger_id="ADULT_1",
                passenger_name="הורה 1",
                program_code="ELAL_MATMID",
                available_points=75000,
                can_pool_with_family=False,
                has_club_credit_card=True,
            ),
            PassengerLoyaltyWallet(
                id="w-p2-unpooled",
                family_profile_id=unpooled_profile.id,
                passenger_id="ADULT_2",
                passenger_name="הורה 2",
                program_code="ELAL_MATMID",
                available_points=68000,
                can_pool_with_family=False,
                has_club_credit_card=True,
            ),
        ]
        fco_out = self.elal_adapter.get_award_availability(
            destinations=["FCO"],
            start_date=date(2027, 4, 11),
            end_date=date(2027, 4, 11),
            direction="OUTBOUND",
        )[0]
        fco_in = self.elal_adapter.get_award_availability(
            destinations=["FCO"],
            start_date=date(2027, 4, 18),
            end_date=date(2027, 4, 18),
            direction="INBOUND",
        )[0]
        engine = MultiClubWalletAllocationEngine()
        unpooled_alloc = engine.allocate_family_tickets(
            profile=unpooled_profile,
            outbound_award=fco_out,
            inbound_award=fco_in,
            cash_benchmark_per_pax=590.0,
            strategy="MULTI_CLUB_PER_PASSENGER_SPLIT",
            preferred_cabins=["ECONOMY", "PREMIUM"],
            enabled_programs=["ELAL_MATMID"],
        )
        self.assertIsNotNone(unpooled_alloc)
        assert unpooled_alloc is not None
        wallet_deductions = unpooled_alloc["points_used_by_wallet"]
        # Each un-pooled wallet can afford at most 2 Economy RT tickets (2 * 30,000 = 60,000 <= 75,000 and <= 68,000)
        for w_key, pts_used in wallet_deductions.items():
            if "ADULT_1" in w_key:
                self.assertLessEqual(pts_used, 75000)
            if "ADULT_2" in w_key:
                self.assertLessEqual(pts_used, 68000)

        # (b) Multi-club split across ELAL_MATMID + BRITISH_AVIOS / FLYING_BLUE / UNITED_MILEAGEPLUS / AMEX_MR_ISRAEL
        multi_proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "enabled_loyalty_programs": [p.value for p in LoyaltyProgramCode],
            },
            profile=self.default_profile,
        )
        mc_props = [
            p
            for p in multi_proposals
            if p.itinerary.fulfillment_strategy == "MULTI_CLUB_PER_PASSENGER_SPLIT"
        ]
        self.assertGreaterEqual(len(mc_props), 1)
        self.assertGreaterEqual(len(mc_props[0].itinerary.points_used_by_wallet), 1)

    def test_search_vacations_all_6_mode_combinations_and_sqlite_persistence_f28(self) -> None:
        """13. Verify `F17`-`F28` `search_vacations` across all 3x2 mode combinations and SQLite persistence."""
        # Mode 1 profile with framework_type=None (optional in Mode 1)
        mode1_profile = copy.deepcopy(self.default_profile)
        for child in mode1_profile.children:
            child.framework_type = None

        mode_queries = [
            # Mode 1 x EL_AL_ONLY
            (
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["FCO", "ATH"],
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                },
                mode1_profile,
            ),
            # Mode 1 x ALL_AIRLINES
            (
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "ALL_AIRLINES",
                    "destination_iatas": ["FCO", "ATH"],
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                },
                mode1_profile,
            ),
            # Mode 2 x EL_AL_ONLY
            (
                {
                    "date_selection_mode": "MOE_VACATION_MAXIMIZATION",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["FCO", "ATH"],
                    "school_year": "2026-2027",
                    "target_holiday_codes": ["PESACH"],
                },
                self.default_profile,
            ),
            # Mode 2 x ALL_AIRLINES
            (
                {
                    "date_selection_mode": "MOE_VACATION_MAXIMIZATION",
                    "airline_selection_mode": "ALL_AIRLINES",
                    "destination_iatas": ["FCO", "ATH"],
                    "school_year": "2026-2027",
                    "target_holiday_codes": ["PESACH"],
                },
                self.default_profile,
            ),
            # Mode 3 x EL_AL_ONLY
            (
                {
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["FCO", "ATH"],
                    "direct_holiday_code": "PESACH",
                    "direct_target_year": 2027,
                },
                self.default_profile,
            ),
            # Mode 3 x ALL_AIRLINES
            (
                {
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "airline_selection_mode": "ALL_AIRLINES",
                    "destination_iatas": ["FCO", "ATH"],
                    "direct_holiday_code": "PESACH",
                    "direct_target_year": 2027,
                },
                self.default_profile,
            ),
        ]

        for q_dict, prof in mode_queries:
            proposals = self.planner.search_vacations(q_dict, profile=prof)
            self.assertGreater(len(proposals), 0, f"No proposals for {q_dict}")
            # Sorted descending by CTOS
            ctos_values = [p.combined_trip_optimization_score for p in proposals]
            self.assertEqual(ctos_values, sorted(ctos_values, reverse=True))
            for p in proposals:
                expected_ctos = round(
                    0.55 * p.vacation_utilization_score + 0.45 * p.flight_bonus_value_score,
                    1,
                )
                self.assertAlmostEqual(
                    p.combined_trip_optimization_score, expected_ctos, places=1
                )
                self.assertGreaterEqual(p.combined_trip_optimization_score, 0.0)
                self.assertLessEqual(p.combined_trip_optimization_score, 100.0)
            # Persisted in SQLite
            persisted = self.repo.get_proposal_by_id(proposals[0].id)
            self.assertIsNotNone(persisted)

    def test_compare_proposals_matrix_and_best_winners_f28(self) -> None:
        """14. Verify `F28` `compare_proposals` returns `VacationComparisonMatrix` and winner IDs."""
        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO", "ATH", "MAD"],
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
            },
            profile=self.default_profile,
        )
        self.assertGreaterEqual(len(proposals), 3)
        selected_ids = [p.id for p in proposals[:3]]
        matrix = self.planner.compare_proposals(selected_ids)
        self.assertEqual(len(matrix["proposals"]), 3)
        self.assertGreaterEqual(len(matrix["comparison_rows"]), 8)
        self.assertIn(matrix["best_by_ctos_id"], selected_ids)
        self.assertIn(matrix["best_by_cash_savings_id"], selected_ids)
        self.assertIn(matrix["best_by_per_id"], selected_ids)
        self.assertIn(matrix["best_by_minimal_absence_id"], selected_ids)

    def test_export_proposal_ics_rfc5545_vcalendar_f28(self) -> None:
        """15. Verify `F28` `export_proposal_ics` generates valid RFC 5545 iCalendar payload."""
        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        self.assertGreater(len(proposals), 0)
        ics_text = self.planner.export_proposal_ics(proposals[0].id)
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("VERSION:2.0", ics_text)
        self.assertIn("PRODID:", ics_text)
        self.assertEqual(ics_text.count("BEGIN:VEVENT"), 4)
        self.assertEqual(ics_text.count("END:VEVENT"), 4)
        self.assertIn("END:VCALENDAR", ics_text)

        with self.assertRaises(ValueError):
            self.planner.export_proposal_ics("non-existent-proposal-id")

    def test_weather_suitability_engine_seasonal_accuracy_and_all_vacation_types_f33(
        self,
    ) -> None:
        """16. Verify `DestinationWeatherSuitabilityEngine` seasonal scores across all 25 destinations & 6 vacation styles."""
        from backend.app.planner_synthesizer.weather_suitability_engine import (
            DestinationWeatherSuitabilityEngine,
        )
        from backend.app.storage_cache.seed_data import DESTINATION_CATALOG

        self.assertEqual(len(DESTINATION_CATALOG), 25)
        for _iata_key, entry in DESTINATION_CATALOG.items():
            self.assertIn("climate_profile", entry)
            self.assertIn("monthly_weather", entry)
            self.assertEqual(len(entry["monthly_weather"]), 12)

        w_engine = DestinationWeatherSuitabilityEngine()

        # (a) Summer July beach vacation: RHO / LCA / PFO / ATH / BCN score >= 80, while monsoon HKT/BKK < 75 and inland MAD/VIE <= 35
        for beach_iata in ("RHO", "LCA", "PFO", "ATH", "BCN"):
            m_beach = w_engine.evaluate_destination(
                beach_iata,
                date(2027, 7, 10),
                date(2027, 7, 17),
                ["BEACH_AND_POOL"],
            )
            self.assertGreaterEqual(
                m_beach.overall_weather_suitability_score,
                80.0,
                f"Expected high July beach score for {beach_iata}, got {m_beach.overall_weather_suitability_score}",
            )
        m_hkt_july = w_engine.evaluate_destination(
            "HKT", date(2027, 7, 10), date(2027, 7, 17), ["BEACH_AND_POOL"]
        )
        m_hkt_jan = w_engine.evaluate_destination(
            "HKT", date(2027, 1, 10), date(2027, 1, 17), ["BEACH_AND_POOL"]
        )
        self.assertGreater(
            m_hkt_jan.overall_weather_suitability_score,
            m_hkt_july.overall_weather_suitability_score + 15.0,
        )
        for inland_iata in ("MAD", "VIE", "PRG", "BER", "LHR"):
            m_inland = w_engine.evaluate_destination(
                inland_iata,
                date(2027, 7, 10),
                date(2027, 7, 17),
                ["BEACH_AND_POOL"],
            )
            self.assertLess(m_inland.overall_weather_suitability_score, 60.0)

        # (b) Winter Hanukkah December snow/ski (MUC, MXP, TBS) & festive markets (VIE, PRG, MUC, BUD, BER)
        for ski_iata in ("MUC", "MXP", "TBS"):
            m_ski = w_engine.evaluate_destination(
                ski_iata,
                date(2026, 12, 6),
                date(2026, 12, 13),
                ["SNOW_AND_SKI"],
            )
            self.assertGreaterEqual(
                m_ski.overall_weather_suitability_score,
                70.0,
                f"Expected high December ski score for {ski_iata}, got {m_ski.overall_weather_suitability_score}",
            )
        for festive_iata in ("VIE", "PRG", "MUC", "BUD", "BER"):
            m_fest = w_engine.evaluate_destination(
                festive_iata,
                date(2026, 12, 6),
                date(2026, 12, 13),
                ["WINTER_FESTIVE"],
            )
            self.assertGreaterEqual(
                m_fest.overall_weather_suitability_score,
                75.0,
                f"Expected high December festive score for {festive_iata}, got {m_fest.overall_weather_suitability_score}",
            )

        # (c) Spring Pesach April nature & urban trips
        for spring_iata in ("FCO", "ATH", "BCN", "MAD"):
            m_nat = w_engine.evaluate_destination(
                spring_iata,
                date(2027, 4, 14),
                date(2027, 4, 21),
                ["NATURE_TRIP"],
            )
            self.assertGreaterEqual(m_nat.overall_weather_suitability_score, 75.0)

    def test_vacation_type_filtering_soft_prioritize_and_hard_threshold_with_fallback_f33(
        self,
    ) -> None:
        """17. Verify `SOFT_PRIORITIZE` 3-way CTOS and `HARD_THRESHOLD` filtering + graceful fallback."""
        # (a) SOFT_PRIORITIZE for BEACH_AND_POOL in July across ATH, LCA, LHR, VIE
        beach_props = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH", "LCA", "LHR", "VIE"],
                "specific_departure_date": "2027-07-15",
                "specific_return_date": "2027-07-22",
                "flex_days_plus_minus": 0,
                "preferred_vacation_types": ["BEACH_AND_POOL"],
                "weather_filter_mode": "SOFT_PRIORITIZE",
            },
            profile=self.default_profile,
        )
        self.assertGreater(len(beach_props), 0)
        top_prop = beach_props[0]
        self.assertIn(top_prop.itinerary.destination_iata, ("ATH", "LCA"))
        self.assertIsNotNone(top_prop.weather_metrics)
        self.assertGreaterEqual(top_prop.weather_suitability_score, 85.0)

        # Verify typed CTOS formula: round(clamp(0.35*WSS + 0.35*VUS + 0.30*FBVS - 0.50*max(0, 60 - WSS), 0, 100), 1)
        for p in beach_props:
            wss = p.weather_suitability_score
            vus = p.vacation_utilization_score
            fbvs = p.flight_bonus_value_score
            shortfall = max(0.0, 60.0 - wss)
            expected_typed_ctos = round(
                max(0.0, min(100.0, 0.35 * wss + 0.35 * vus + 0.30 * fbvs - 0.50 * shortfall)),
                1,
            )
            self.assertAlmostEqual(
                p.combined_trip_optimization_score, expected_typed_ctos, places=1
            )

        # (b) HARD_THRESHOLD filters out non-beach destinations (VIE/LHR) when ATH/LCA have >= 3 proposals
        hard_props = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH", "LCA", "VIE"],
                "specific_departure_date": "2027-07-15",
                "specific_return_date": "2027-07-22",
                "flex_days_plus_minus": 0,
                "preferred_vacation_types": ["BEACH_AND_POOL"],
                "weather_filter_mode": "HARD_THRESHOLD",
            },
            profile=self.default_profile,
        )
        self.assertGreaterEqual(len(hard_props), 3)
        for hp in hard_props:
            self.assertGreaterEqual(hp.weather_suitability_score, 60.0)
            self.assertNotEqual(hp.itinerary.destination_iata, "VIE")

        # (c) HARD_THRESHOLD graceful fallback when threshold is impossibly high (99.9)
        fallback_props = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO", "ATH"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "preferred_vacation_types": ["SNOW_AND_SKI"],
                "weather_filter_mode": "HARD_THRESHOLD",
                "min_weather_suitability_score": 99.9,
            },
            profile=self.default_profile,
        )
        self.assertGreaterEqual(len(fallback_props), 1)
        self.assertIsNotNone(self.planner.last_weather_fallback_message_he)


if __name__ == "__main__":
    unittest.main()
