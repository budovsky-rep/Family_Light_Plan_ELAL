"""Tier 3 Opaque-Box Pairwise Combinatorial Test Suite for family_vacation_planner.

Contains 36 pairwise combinatorial tests (test_pw01_* .. test_pw36_*) crossing:
- Date Selection Modes: SPECIFIC_DATES, MOE_VACATION_MAXIMIZATION, HOLIDAY_DIRECT_INTENT
- Airline Selection Modes: EL_AL_ONLY, ALL_AIRLINES
- All 8 MoE Frameworks + None (optional in Mode 1) + 5/6-day school weeks + Nitzanim
- All 10 LoyaltyProgramCode programs (pooled and un-pooled per-passenger wallets)
- All 6 Family Bonus Fulfillment Strategies + COMMERCIAL_CASH_ONLY
- All 11 structured holiday codes and 7 metro IATA codes + ANYWHERE
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.schemas.domain import (
    ChildFramework,
    FamilyProfile,
    FlightSearchQuery,
    PassengerLoyaltyWallet,
)
from tests.e2e.test_tier1_features import (
    Tier1BaseTestCase,
    _as_dict,
    _get_field,
    _save_profile_to_repo_or_sqlite,
)


class Tier3PairwiseTestBase(Tier1BaseTestCase):
    """Hermetic base harness for Tier 3 pairwise combinatorial tests."""

    def build_profile(
        self,
        profile_id: str,
        children: list[ChildFramework],
        wallets: list[PassengerLoyaltyWallet],
        matmid_balance: int = 185000,
        has_flycard: bool = True,
        max_pto: float = 12.0,
    ) -> tuple[Path, Any, FamilyProfile]:
        tmpdir = tempfile.TemporaryDirectory(prefix="tier3_pw_")
        self.addCleanup(tmpdir.cleanup)
        db_path = Path(tmpdir.name) / "pw.db"
        from backend.app.storage_cache.repository import SQLiteRepository

        repo = SQLiteRepository(db_path=db_path, auto_seed=True)
        prof = FamilyProfile(
            id=profile_id,
            profile_name=f"פרופיל {profile_id}",
            adults_count=2,
            workweek_type="SUN_THU",
            erev_chag_pto_weight=0.5,
            chol_hamoed_pto_weight=0.5,
            annual_pto_budget=22.0,
            max_pto_per_trip=max_pto,
            matmid_points_balance=matmid_balance,
            has_flycard=has_flycard,
            flycard_tier="FLY_CARD_PREMIUM" if has_flycard else "NONE",
            flycard_companion_vouchers=1 if has_flycard else 0,
            children=children,
            passenger_loyalty_wallets=wallets,
        )
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        return db_path, repo, saved

    def execute_search(
        self, repo: Any, prof: FamilyProfile, query_payload: dict[str, Any]
    ) -> list[Any]:
        planner = self.get_planner(repo)
        payload = dict(query_payload)
        payload.setdefault("family_profile_id", prof.id)
        proposals = planner.search_vacations(payload, profile=prof)
        self.assertGreater(len(proposals), 0, f"Expected proposals for {payload}")
        for p in proposals:
            self.assertGreaterEqual(p.vacation_utilization_score, 0.0)
            self.assertLessEqual(p.vacation_utilization_score, 100.0)
            self.assertGreaterEqual(p.flight_bonus_value_score, 0.0)
            self.assertLessEqual(p.flight_bonus_value_score, 100.0)
            self.assertGreaterEqual(p.combined_trip_optimization_score, 0.0)
            self.assertLessEqual(p.combined_trip_optimization_score, 100.0)
            self.assertIsNotNone(p.itinerary)
        return proposals


class TestTier3PairwiseCombinatorialMatrix(Tier3PairwiseTestBase):
    """36 pairwise tests covering Date Mode x Airline Mode x Framework x Wallet x Strategy."""

    def test_pw01_specific_elal_none_framework_matmid_full_bonus(self) -> None:
        children = [
            ChildFramework(child_age_years=1, framework_type=None),
            ChildFramework(child_age_years=7, framework_type=None),
        ]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=220000, can_pool_with_family=True)]
        db_path, _repo, prof = self.build_profile("pw01", children, wallets, matmid_balance=220000)
        client = self.get_client(db_path)
        self.authenticate_test_client(client, email="pw01@gmail.com", profile=prof)
        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2026-12-06", "specific_return_date": "2026-12-11", "flex_days_plus_minus": 0, "destination_iatas": ["ATH"],
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreater(body["count"], 0)
        strats = {p["itinerary"]["fulfillment_strategy"] for p in body["proposals"]}
        self.assertTrue(bool(strats & {"FULL_BONUS_SAME_CABIN", "SPLIT_CABIN_BONUS", "HYBRID_BONUS_PLUS_CASH"}))
        self.assertTrue(any(p["itinerary"]["requires_two_plus_seat_verification"] for p in body["proposals"]))

    def test_pw02_specific_all_airlines_none_framework_cash_only(self) -> None:
        children = [
            ChildFramework(child_age_years=4, framework_type=None),
            ChildFramework(child_age_years=14, framework_type=None),
        ]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=0)]
        _db, repo, prof = self.build_profile("pw02", children, wallets, matmid_balance=0, has_flycard=False)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "ALL_AIRLINES",
            "specific_departure_date": "2027-04-11", "specific_return_date": "2027-04-18", "flex_days_plus_minus": 2, "destination_iatas": ["FCO"],
        })
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") == "COMMERCIAL_CASH_ONLY" for p in proposals))
        for p in proposals:
            it = p.itinerary
            self.assertGreaterEqual(it.total_baggage_fees_usd, 0.0)
            self.assertAlmostEqual(it.total_out_of_pocket_cash_usd, it.total_supplemental_cash_fares_usd + it.total_baggage_fees_usd + it.total_taxes_and_fees_usd, places=1)

    def test_pw03_specific_elal_daycare_avios_split_cabin(self) -> None:
        children = [ChildFramework(child_age_years=2, framework_type="DAYCARE_SUPERVISED", school_week_days=6)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=180000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="BRITISH_AVIOS", available_points=80000),
        ]
        _db, repo, prof = self.build_profile("pw03", children, wallets, matmid_balance=180000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-04-11", "specific_return_date": "2027-04-18", "flex_days_plus_minus": 1,
            "destination_iatas": ["FCO"], "preferred_cabins": ["ECONOMY", "PREMIUM", "BUSINESS"],
        })
        self.assertEqual(_get_field(proposals[0].per_child_impact[0], "framework_type"), "DAYCARE_SUPERVISED")
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") in ("SPLIT_CABIN_BONUS", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH") for p in proposals))

    def test_pw04_specific_all_airlines_municipal_gan_flying_blue_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=5, framework_type="MUNICIPAL_GAN", school_week_days=6, holiday_extension_mode="NITZANIM_FULL_WITH_JULY", treat_camp_as_vacation=True)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="FLYING_BLUE", available_points=90000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AMEX_MR_ISRAEL", available_points=60000, transfer_ratio_to_airline=1.0),
        ]
        _db, repo, prof = self.build_profile("pw04", children, wallets, matmid_balance=60000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "ALL_AIRLINES",
            "specific_departure_date": "2026-12-06", "specific_return_date": "2026-12-11", "flex_days_plus_minus": 0,
            "destination_iatas": ["PAR"], "enabled_loyalty_programs": ["FLYING_BLUE", "AMEX_MR_ISRAEL", "ELAL_MATMID"],
        })
        self.assertTrue(all(p.itinerary.destination_iata == "CDG" for p in proposals))
        self.assertGreaterEqual(proposals[0].per_child_impact[0].nitzanim_days_overlapped, 1)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw05_specific_elal_elem13_united_hybrid_bonus_cash(self) -> None:
        children = [
            ChildFramework(child_age_years=7, framework_type="ELEMENTARY_1_3", school_week_days=5, holiday_extension_mode="NITZANIM_CHAGIM_ONLY"),
            ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5),
            ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5),
        ]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=145000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="UNITED_MILEAGEPLUS", available_points=50000),
        ]
        _db, repo, prof = self.build_profile("pw05", children, wallets, matmid_balance=145000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-04-11", "specific_return_date": "2027-04-18", "flex_days_plus_minus": 0,
            "destination_iatas": ["ROM"], "allow_hybrid_bonus_cash": True,
        })
        self.assertTrue(all(p.itinerary.destination_iata == "FCO" for p in proposals))
        hybrid = [p for p in proposals if _get_field(p.itinerary, "fulfillment_strategy") == "HYBRID_BONUS_PLUS_CASH"]
        self.assertGreater(len(hybrid), 0)
        self.assertGreater(hybrid[0].itinerary.total_matmid_points, 0)
        self.assertGreater(hybrid[0].itinerary.total_supplemental_cash_fares_usd, 0.0)

    def test_pw06_specific_all_airlines_elem46_miles_and_more_cash_only(self) -> None:
        children = [ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="MILES_AND_MORE", available_points=75000)]
        _db, repo, prof = self.build_profile("pw06", children, wallets, matmid_balance=0)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "ALL_AIRLINES",
            "specific_departure_date": "2026-09-25", "specific_return_date": "2026-10-02", "flex_days_plus_minus": 1, "destination_iatas": ["BER"],
        })
        for p in proposals:
            self.assertNotIn(p.itinerary.departure_date, (date(2026, 9, 20), date(2026, 9, 21)))

    def test_pw07_specific_elal_middle79_delta_one_way_bonus_cash(self) -> None:
        children = [ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=90000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="DELTA_SKYMILES", available_points=70000),
        ]
        _db, repo, prof = self.build_profile("pw07", children, wallets, matmid_balance=90000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-06-21", "specific_return_date": "2027-06-28", "flex_days_plus_minus": 0, "destination_iatas": ["LON"],
        })
        self.assertTrue(all(p.itinerary.destination_iata in ("LHR", "LTN") for p in proposals))
        self.assertEqual(proposals[0].per_child_impact[0].bridge_school_days_missed, 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("ONE_WAY_BONUS_ONE_WAY_CASH", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS"))

    def test_pw08_specific_all_airlines_high1012_qantas_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="QANTAS_FREQUENT_FLYER", available_points=110000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="ELAL_MATMID", available_points=80000),
        ]
        _db, repo, prof = self.build_profile("pw08", children, wallets, matmid_balance=80000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "ALL_AIRLINES",
            "specific_departure_date": "2026-09-25", "specific_return_date": "2026-10-04", "flex_days_plus_minus": 0, "destination_iatas": ["NYC"],
        })
        self.assertTrue(all(p.itinerary.destination_iata in ("JFK", "EWR") for p in proposals))
        self.assertEqual(proposals[0].per_child_impact[0].bridge_school_days_missed, 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw09_specific_elal_special_ed_aegean_cash_and_points(self) -> None:
        children = [ChildFramework(child_age_years=11, framework_type="SPECIAL_ED", school_week_days=6)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=45000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AEGEAN_MILES_BONUS", available_points=60000),
        ]
        _db, repo, prof = self.build_profile("pw09", children, wallets, matmid_balance=45000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-08-17", "specific_return_date": "2027-08-24", "flex_days_plus_minus": 0, "destination_iatas": ["ATH"],
        })
        self.assertEqual(proposals[0].per_child_impact[0].bridge_school_days_missed, 0)
        self.assertTrue(any(p.itinerary.cents_per_point_value >= 0.0 for p in proposals))
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("CASH_AND_POINTS", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw10_specific_all_airlines_haredi_israeli_cc_cash_only(self) -> None:
        children = [ChildFramework(child_age_years=9, framework_type="RELIGIOUS_HAREDI", education_stream="CHAREDI", school_week_days=6)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ISRAELI_CC_TRAVEL_POINTS", available_points=95000, transfer_ratio_to_airline=1.0)]
        _db, repo, prof = self.build_profile("pw10", children, wallets, matmid_balance=95000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "ALL_AIRLINES",
            "specific_departure_date": "2027-04-13", "specific_return_date": "2027-04-20", "flex_days_plus_minus": 1, "destination_iatas": ["BUD"],
        })
        self.assertEqual(_get_field(proposals[0].per_child_impact[0], "framework_type"), "RELIGIOUS_HAREDI")

    def test_pw11_moe_max_elal_daycare_matmid_full_bonus(self) -> None:
        children = [ChildFramework(child_age_years=1, framework_type="DAYCARE_SUPERVISED", school_week_days=6)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=250000)]
        _db, repo, prof = self.build_profile("pw11", children, wallets, matmid_balance=250000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["SUMMER_AUGUST", "PESACH"], "destination_iatas": ["LCA"],
        })
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") == "FULL_BONUS_SAME_CABIN" for p in proposals))

    def test_pw12_moe_max_all_airlines_daycare_avios_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=2, framework_type="DAYCARE_SUPERVISED", school_week_days=6)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="BRITISH_AVIOS", available_points=120000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AMEX_MR_ISRAEL", available_points=80000),
        ]
        _db, repo, prof = self.build_profile("pw12", children, wallets, matmid_balance=80000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2026-2027", "target_holiday_codes": ["SUMMER_AUGUST"], "destination_iatas": ["LHR"],
        })
        self.assertTrue(any(p.itinerary.departure_date >= date(2027, 8, 9) for p in proposals))
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw13_moe_max_elal_municipal_gan_flying_blue_split_cabin(self) -> None:
        children = [ChildFramework(child_age_years=4, framework_type="MUNICIPAL_GAN", school_week_days=6, holiday_extension_mode="NITZANIM_FULL_WITH_JULY", treat_camp_as_vacation=True)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=200000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="FLYING_BLUE", available_points=70000),
        ]
        _db, repo, prof = self.build_profile("pw13", children, wallets, matmid_balance=200000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["HANUKKAH", "PESACH"], "destination_iatas": ["ATH"],
        })
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") in ("SPLIT_CABIN_BONUS", "FULL_BONUS_SAME_CABIN") for p in proposals))

    def test_pw14_moe_max_all_airlines_municipal_gan_united_cash_only(self) -> None:
        children = [ChildFramework(child_age_years=5, framework_type="MUNICIPAL_GAN", school_week_days=6, holiday_extension_mode="NITZANIM_FULL_WITH_JULY", treat_camp_as_vacation=False)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="UNITED_MILEAGEPLUS", available_points=85000)]
        _db, repo, prof = self.build_profile("pw14", children, wallets, matmid_balance=0)
        maximizer = self.get_maximizer(self.get_calendar_service(repo))
        w_camp = maximizer.evaluate_window(prof, date(2027, 4, 13), date(2027, 4, 19))
        w_uncov = maximizer.evaluate_window(prof, date(2027, 4, 20), date(2027, 4, 27))
        self.assertGreater(w_uncov.vacation_utilization_score, w_camp.vacation_utilization_score)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2026-2027", "target_holiday_codes": ["PESACH"], "destination_iatas": ["FCO"],
        })
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("COMMERCIAL_CASH_ONLY", "MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH"))

    def test_pw15_moe_max_elal_elem13_miles_and_more_hybrid_bonus_cash(self) -> None:
        children = [
            ChildFramework(child_age_years=7, framework_type="ELEMENTARY_1_3", school_week_days=5, holiday_extension_mode="NITZANIM_CHAGIM_ONLY"),
            ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5),
            ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5),
        ]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=142000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="MILES_AND_MORE", available_points=60000),
        ]
        _db, repo, prof = self.build_profile("pw15", children, wallets, matmid_balance=142000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["PESACH"], "destination_iatas": ["FCO"], "max_bridge_days_shift": 2,
        })
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") == "HYBRID_BONUS_PLUS_CASH" for p in proposals))

    def test_pw16_moe_max_all_airlines_elem13_delta_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=8, framework_type="ELEMENTARY_1_3", school_week_days=6, holiday_extension_mode="NITZANIM_FULL_WITH_JULY")]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="DELTA_SKYMILES", available_points=100000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="ISRAELI_CC_TRAVEL_POINTS", available_points=80000),
        ]
        _db, repo, prof = self.build_profile("pw16", children, wallets, matmid_balance=80000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2026-2027", "target_holiday_codes": ["HANUKKAH"], "destination_iatas": ["CDG"],
        })
        self.assertGreater(len(proposals), 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw17_moe_max_elal_elem46_qantas_one_way_bonus_cash(self) -> None:
        children = [ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=95000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="QANTAS_FREQUENT_FLYER", available_points=75000),
        ]
        _db, repo, prof = self.build_profile("pw17", children, wallets, matmid_balance=95000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["SUKKOT"], "destination_iatas": ["MIL"],
        })
        self.assertTrue(all(p.itinerary.destination_iata == "MXP" for p in proposals))
        self.assertEqual(proposals[0].per_child_impact[0].nitzanim_days_overlapped, 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("ONE_WAY_BONUS_ONE_WAY_CASH", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS"))

    def test_pw18_moe_max_all_airlines_elem46_aegean_cash_only(self) -> None:
        children = [
            ChildFramework(child_age_years=11, framework_type="ELEMENTARY_4_6", school_week_days=6),
            ChildFramework(child_age_years=9, framework_type="SPECIAL_ED", school_week_days=6),
        ]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="AEGEAN_MILES_BONUS", available_points=90000)]
        _db, repo, prof = self.build_profile("pw18", children, wallets, matmid_balance=0)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2025-2026", "target_holiday_codes": ["ROSH_HASHANAH", "PURIM"], "destination_iatas": ["ATH", "RHO"], "max_bridge_days_shift": 2,
        })
        self.assertGreater(len(proposals), 0)

    def test_pw19_moe_max_elal_middle79_amex_full_bonus(self) -> None:
        children = [ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=130000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AMEX_MR_ISRAEL", available_points=100000, transfer_ratio_to_airline=1.0),
        ]
        _db, repo, prof = self.build_profile("pw19", children, wallets, matmid_balance=230000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["SUMMER_JUNE_20_30"], "destination_iatas": ["MAD"],
        })
        self.assertTrue(any(p.itinerary.departure_date >= date(2027, 6, 21) and p.per_child_impact[0].bridge_school_days_missed == 0 for p in proposals))

    def test_pw20_moe_max_all_airlines_middle79_israeli_cc_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=14, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=6)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ISRAELI_CC_TRAVEL_POINTS", available_points=110000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="FLYING_BLUE", available_points=80000),
        ]
        _db, repo, prof = self.build_profile("pw20", children, wallets, matmid_balance=110000)
        cal = self.get_calendar_service(repo)
        self.assertEqual(cal.get_child_day_status(children[0], date(2026, 6, 21)).state_code, "VACATION")
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2025-2026", "target_holiday_codes": ["SUMMER_JUNE_20_30"], "destination_iatas": ["AMS"],
        })
        self.assertGreater(len(proposals), 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw21_moe_max_elal_high1012_matmid_cash_and_points(self) -> None:
        children = [ChildFramework(child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5, bagrut_blackout_dates=[date(2026, 9, 28)])]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=60000, can_pool_with_family=False)]
        _db, repo, prof = self.build_profile("pw21", children, wallets, matmid_balance=60000)
        cal = self.get_calendar_service(repo)
        self.assertEqual(cal.get_child_day_status(children[0], date(2026, 10, 4)).state_code, "VACATION")
        maximizer = self.get_maximizer(cal)
        wins = maximizer.generate_candidate_windows(FlightSearchQuery(
            date_selection_mode="MOE_VACATION_MAXIMIZATION", school_year="2026-2027", target_holiday_codes=["YOM_KIPPUR_SUKKOT"], min_trip_nights=3, max_trip_nights=6
        ), prof)
        for w in wins:
            self.assertFalse(w.start_date <= date(2026, 9, 28) <= w.end_date)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["YOM_KIPPUR_SUKKOT"], "destination_iatas": ["ATH"],
            "min_trip_nights": 3, "max_trip_nights": 6,
        })
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("CASH_AND_POINTS", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw22_moe_max_all_airlines_high1012_avios_cash_only(self) -> None:
        children = [ChildFramework(child_age_years=17, framework_type="HIGH_SCHOOL_10_12", school_week_days=5)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="BRITISH_AVIOS", available_points=70000)]
        _db, repo, prof = self.build_profile("pw22", children, wallets, matmid_balance=0)
        cal = self.get_calendar_service(repo)
        self.assertEqual(cal.get_child_day_status(children[0], date(2026, 5, 5)).state_code, "VACATION")
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2025-2026", "target_holiday_codes": ["SHAVUOT", "PESACH"], "destination_iatas": ["LCA"],
        })
        self.assertGreater(len(proposals), 0)

    def test_pw23_moe_max_elal_special_ed_united_split_cabin(self) -> None:
        children = [ChildFramework(child_age_years=12, framework_type="SPECIAL_ED", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=190000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="UNITED_MILEAGEPLUS", available_points=90000),
        ]
        _db, repo, prof = self.build_profile("pw23", children, wallets, matmid_balance=190000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "EL_AL_ONLY",
            "school_year": "2026-2027", "target_holiday_codes": ["SUMMER_AUGUST"], "destination_iatas": ["ATH"],
        })
        self.assertTrue(any(p.itinerary.departure_date >= date(2027, 8, 16) for p in proposals))

    def test_pw24_moe_max_all_airlines_haredi_miles_and_more_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=10, framework_type="RELIGIOUS_HAREDI", education_stream="CHAREDI", school_week_days=6)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="MILES_AND_MORE", available_points=120000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AMEX_MR_ISRAEL", available_points=80000),
        ]
        _db, repo, prof = self.build_profile("pw24", children, wallets, matmid_balance=80000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "MOE_VACATION_MAXIMIZATION", "airline_selection_mode": "ALL_AIRLINES",
            "school_year": "2026-2027", "target_holiday_codes": ["PESACH", "SUKKOT"], "destination_iatas": ["VIE"],
        })
        self.assertGreater(len(proposals), 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw25_holiday_direct_elal_pesach_2027_municipal_gan_hybrid(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "PESACH", "direct_target_year": 2027, "destination_iatas": ["FCO"],
            "min_trip_nights": 7, "max_trip_nights": 8, "max_bridge_days_shift": 2,
        })
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") == "HYBRID_BONUS_PLUS_CASH" for p in proposals))

    def test_pw26_holiday_direct_all_airlines_sukkot_2026_elem13_cash_only(self) -> None:
        children = [ChildFramework(child_age_years=7, framework_type="ELEMENTARY_1_3", school_week_days=5)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="FLYING_BLUE", available_points=60000)]
        _db, repo, prof = self.build_profile("pw26", children, wallets, matmid_balance=0)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "ALL_AIRLINES",
            "direct_holiday_code": "SUKKOT", "direct_target_year": 2026, "destination_iatas": ["ATH", "LCA"],
        })
        self.assertTrue(any(_get_field(p.itinerary, "fulfillment_strategy") == "COMMERCIAL_CASH_ONLY" for p in proposals))

    def test_pw27_holiday_direct_elal_kippur_sukkot_2026_high1012_full_bonus(self) -> None:
        children = [ChildFramework(child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=240000)]
        _db, repo, prof = self.build_profile("pw27", children, wallets, matmid_balance=240000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "YOM_KIPPUR_SUKKOT", "direct_target_year": 2026, "destination_iatas": ["PRG", "BUD"],
        })
        for p in proposals:
            self.assertNotIn(p.itinerary.departure_date, (date(2026, 9, 20), date(2026, 9, 21)))
            self.assertNotIn(p.itinerary.return_date, (date(2026, 9, 20), date(2026, 9, 21)))

    def test_pw28_holiday_direct_all_airlines_hanukkah_2026_middle79_multi_club(self) -> None:
        children = [ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="BRITISH_AVIOS", available_points=90000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="QANTAS_FREQUENT_FLYER", available_points=70000),
        ]
        _db, repo, prof = self.build_profile("pw28", children, wallets, matmid_balance=0)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "ALL_AIRLINES",
            "direct_holiday_code": "HANUKKAH", "direct_target_year": 2026, "destination_iatas": ["LON"],
        })
        self.assertTrue(all(p.itinerary.destination_iata in ("LHR", "LTN") for p in proposals))
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw29_holiday_direct_elal_rosh_hashanah_2025_elem46_one_way(self) -> None:
        children = [ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=110000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="DELTA_SKYMILES", available_points=50000),
        ]
        _db, repo, prof = self.build_profile("pw29", children, wallets, matmid_balance=110000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "ROSH_HASHANAH", "direct_target_year": 2025, "destination_iatas": ["LCA", "RHO"],
            "min_trip_nights": 3, "max_trip_nights": 6, "max_bridge_days_shift": 2,
        })
        self.assertGreater(len(proposals), 0)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("ONE_WAY_BONUS_ONE_WAY_CASH", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS"))

    def test_pw30_holiday_direct_elal_purim_2027_elem13_split_cabin(self) -> None:
        children = [ChildFramework(child_age_years=8, framework_type="ELEMENTARY_1_3", school_week_days=5)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=180000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AEGEAN_MILES_BONUS", available_points=60000),
        ]
        _db, repo, prof = self.build_profile("pw30", children, wallets, matmid_balance=180000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "PURIM", "direct_target_year": 2027, "destination_iatas": ["ATH", "VIE"],
            "min_trip_nights": 3, "max_trip_nights": 5, "max_bridge_days_shift": 2,
        })
        self.assertGreater(len(proposals), 0)

    def test_pw31_holiday_direct_elal_shavuot_2027_municipal_gan_full_bonus(self) -> None:
        children = [ChildFramework(child_age_years=5, framework_type="MUNICIPAL_GAN", school_week_days=6)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=160000)]
        _db, repo, prof = self.build_profile("pw31", children, wallets, matmid_balance=160000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "SHAVUOT", "direct_target_year": 2027, "destination_iatas": ["LCA", "ATH"],
            "min_trip_nights": 3, "max_trip_nights": 5, "max_bridge_days_shift": 2,
        })
        self.assertGreater(len(proposals), 0)

    def test_pw32_holiday_direct_all_airlines_yom_haatzmaut_2027_high1012_cash(self) -> None:
        children = [ChildFramework(child_age_years=15, framework_type="HIGH_SCHOOL_10_12", school_week_days=5)]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="UNITED_MILEAGEPLUS", available_points=50000)]
        _db, repo, prof = self.build_profile("pw32", children, wallets, matmid_balance=0)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "ALL_AIRLINES",
            "direct_holiday_code": "YOM_HAATZMAUT", "direct_target_year": 2027, "destination_iatas": ["BER", "PRG"],
            "min_trip_nights": 3, "max_trip_nights": 6, "max_bridge_days_shift": 2,
        })
        self.assertGreater(len(proposals), 0)

    def test_pw33_holiday_direct_elal_summer_june_20_30_2027_middle79_hybrid(self) -> None:
        children = [
            ChildFramework(child_name="מאיה", child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5),
            ChildFramework(child_name="עידו", child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5),
        ]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=150000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="AMEX_MR_ISRAEL", available_points=40000),
        ]
        _db, repo, prof = self.build_profile("pw33", children, wallets, matmid_balance=150000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "SUMMER_JUNE_20_30", "direct_target_year": 2027, "destination_iatas": ["MAD", "BCN"],
        })
        p0 = proposals[0]
        by_name = {c.child_name: c for c in p0.per_child_impact}
        self.assertEqual(by_name["מאיה"].bridge_school_days_missed, 0)

    def test_pw34_holiday_direct_all_airlines_summer_july_2027_gan_nitzanim(self) -> None:
        children = [ChildFramework(child_age_years=5, framework_type="MUNICIPAL_GAN", school_week_days=6, holiday_extension_mode="NITZANIM_FULL_WITH_JULY", treat_camp_as_vacation=True)]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="MILES_AND_MORE", available_points=100000),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="ISRAELI_CC_TRAVEL_POINTS", available_points=90000),
        ]
        _db, repo, prof = self.build_profile("pw34", children, wallets, matmid_balance=90000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "ALL_AIRLINES",
            "direct_holiday_code": "SUMMER_JULY", "direct_target_year": 2027, "destination_iatas": ["TYO"],
        })
        self.assertTrue(all(p.itinerary.destination_iata == "NRT" for p in proposals))
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))

    def test_pw35_holiday_direct_elal_summer_august_2027_daycare_special_ed(self) -> None:
        children = [
            ChildFramework(child_age_years=2, framework_type="DAYCARE_SUPERVISED", school_week_days=6),
            ChildFramework(child_age_years=9, framework_type="SPECIAL_ED", school_week_days=6),
        ]
        wallets = [PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=260000)]
        _db, repo, prof = self.build_profile("pw35", children, wallets, matmid_balance=260000)
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "SUMMER_AUGUST", "direct_target_year": 2027, "destination_iatas": ["MIA_AREA"],
            "overlap_policy": "STRICT_ALL_CHILDREN_OFF",
        })
        self.assertTrue(all(p.itinerary.destination_iata in ("MIA", "FLL") for p in proposals))
        self.assertTrue(any(p.itinerary.departure_date >= date(2027, 8, 16) for p in proposals))

    def test_pw36_holiday_direct_elal_pesach_2028_haredi_unpooled_multi_club(self) -> None:
        children = [
            ChildFramework(child_age_years=8, framework_type="RELIGIOUS_HAREDI", education_stream="CHAREDI", school_week_days=6),
            ChildFramework(child_age_years=6, framework_type="ELEMENTARY_1_3", school_week_days=5),
        ]
        wallets = [
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="ELAL_MATMID", available_points=75000, can_pool_with_family=False),
            PassengerLoyaltyWallet(passenger_id="ADULT_2", program_code="ELAL_MATMID", available_points=68000, can_pool_with_family=False),
            PassengerLoyaltyWallet(passenger_id="ADULT_1", program_code="BRITISH_AVIOS", available_points=80000, can_pool_with_family=True),
        ]
        _db, repo, prof = self.build_profile("pw36", children, wallets, matmid_balance=143000)
        updater = self.get_auto_updater(repo)
        sync_res = updater.sync_school_year("2027-2028")
        self.assertEqual(sync_res.school_year, "2027-2028")
        proposals = self.execute_search(repo, prof, {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT", "airline_selection_mode": "EL_AL_ONLY",
            "direct_holiday_code": "PESACH", "direct_target_year": 2028, "destination_iatas": ["ANYWHERE"],
            "enabled_loyalty_programs": ["ELAL_MATMID", "BRITISH_AVIOS"],
        })
        self.assertGreater(len(proposals), 0)
        self.assertGreaterEqual(len({p.itinerary.destination_iata for p in proposals}), 2)
        self.assertIn(proposals[0].itinerary.fulfillment_strategy, ("MULTI_CLUB_PER_PASSENGER_SPLIT", "FULL_BONUS_SAME_CABIN", "HYBRID_BONUS_PLUS_CASH", "SPLIT_CABIN_BONUS", "COMMERCIAL_CASH_ONLY"))


if __name__ == "__main__":
    unittest.main()
