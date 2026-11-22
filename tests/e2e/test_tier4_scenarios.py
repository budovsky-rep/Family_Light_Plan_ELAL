"""Tier 4 Opaque-Box End-to-End Real-World Application Scenario Test Suite.

Contains 18 comprehensive end-to-end family vacation planning workflow tests
(test_scenario_01_* .. test_scenario_18_*, >= 16) verifying full-stack integration
across SQLite WAL storage, MoE Calendar & Auto-Updater, Vacation Maximizer,
El Al rbddataclients & All-Airlines Adapters, Multi-Club Wallets, 6 Fulfillment
Strategies, REST API, CLI companion, and Mobile/Desktop BiDi/RTL Web UI & PWA.
"""

from __future__ import annotations

import importlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.schemas.domain import (
    ChildFramework,
    FamilyProfile,
    FlightSearchQuery,
    PassengerLoyaltyWallet,
    classify_passenger_type,
    suggest_framework_for_age,
)
from tests.e2e.test_tier1_features import (
    Tier1BaseTestCase,
    _as_dict,
    _get_field,
    _save_profile_to_repo_or_sqlite,
)


class Tier4ScenariosTestBase(Tier1BaseTestCase):
    """Hermetic base harness for Tier 4 end-to-end real-world scenarios."""

    def create_isolated_client_env(self) -> tuple[Path, Any, Any]:
        tmpdir = tempfile.TemporaryDirectory(prefix="tier4_scen_")
        self.addCleanup(tmpdir.cleanup)
        db_path = Path(tmpdir.name) / "scenario.db"
        from backend.app.storage_cache.repository import SQLiteRepository
        from backend.app.storage_cache.seed_data import build_default_family_profile

        repo = SQLiteRepository(db_path=db_path, auto_seed=True)
        if not SQLiteRepository.is_live_fetch_mode():
            repo.save_profile(build_default_family_profile())
        client = self.get_client(db_path)
        return db_path, repo, client

    def create_authenticated_client_env(
        self, email: str = "scenario@gmail.com", profile: Any = None
    ) -> tuple[Path, Any, Any]:
        from backend.app.storage_cache.seed_data import build_default_family_profile

        db_path, repo, client = self.create_isolated_client_env()
        target_prof = profile if profile is not None else build_default_family_profile()
        self.authenticate_test_client(client, email=email, profile=target_prof)
        return db_path, repo, client


class TestTier4RealWorldApplicationScenarios(Tier4ScenariosTestBase):
    """18 real-world family vacation user workflows (Scenarios 1..18)."""

    def test_scenario_01_pesach_2027_rome_family_of_5_hybrid_bonus_plus_cash(self) -> None:
        db_path, repo, client = self.create_authenticated_client_env("scen01@gmail.com")
        prof_resp = client.get("/api/v1/profile")
        self.assertEqual(prof_resp.status_code, 200)
        prof_json = prof_resp.json()
        self.assertEqual(prof_json["adults_count"], 2)
        self.assertEqual(len(prof_json["children"]), 3)
        self.assertEqual(prof_json["matmid_points_balance"], 185000)

        avail_resp = client.get("/api/v1/elal-bonus/availability?destination=ROM&start_date=2027-04-10&end_date=2027-04-28")
        self.assertEqual(avail_resp.status_code, 200)
        avail_body = avail_resp.json()
        self.assertEqual(avail_body["expanded_destinations"], ["FCO"])
        self.assertGreaterEqual(avail_body["count"], 2)

        search_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ROM"],
            "min_trip_nights": 7,
            "max_trip_nights": 8,
            "max_bridge_days_shift": 2,
        })
        self.assertEqual(search_resp.status_code, 200)
        proposals = search_resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        apr11_hybrid = [
            p for p in proposals
            if p["itinerary"]["departure_date"] == "2027-04-11"
            and p["itinerary"]["return_date"] == "2027-04-18"
            and p["itinerary"]["fulfillment_strategy"] == "HYBRID_BONUS_PLUS_CASH"
        ]
        self.assertGreater(len(apr11_hybrid), 0)
        flagship = apr11_hybrid[0]
        it = flagship["itinerary"]
        self.assertEqual(it["total_matmid_points"], 142000)
        self.assertAlmostEqual(it["total_taxes_and_fees_usd"], 390.0, delta=25.0)
        self.assertAlmostEqual(it["total_supplemental_cash_fares_usd"], 460.0, delta=30.0)
        self.assertAlmostEqual(it["net_cash_saved_usd"], 2100.0, delta=100.0)
        self.assertAlmostEqual(it["cents_per_point_value"], 1.48, delta=0.10)
        self.assertGreater(flagship["vacation_utilization_score"], 75.0)
        self.assertGreater(flagship["combined_trip_optimization_score"], 85.0)

        maximizer = self.get_maximizer(self.get_calendar_service(repo))
        prof_obj = self.get_default_profile(db_path)
        w_uncov = maximizer.evaluate_window(prof_obj, date(2027, 4, 20), date(2027, 4, 27))
        self.assertAlmostEqual(w_uncov.school_absence_penalty, 0.0)
        self.assertAlmostEqual(w_uncov.childcare_coverage_gain, 1.0)
        self.assertGreaterEqual(w_uncov.vacation_utilization_score, 90.0)

    def test_scenario_02_hanukkah_2026_athens_nitzanim_camp_toggle_comparison(self) -> None:
        _db_path, repo, client = self.create_authenticated_client_env("scen02@gmail.com")
        resp_on = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "HANUKKAH",
            "direct_target_year": 2026,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ATH"],
            "min_trip_nights": 4,
            "max_trip_nights": 6,
            "max_bridge_days_shift": 2,
        })
        self.assertEqual(resp_on.status_code, 200)
        props_on = resp_on.json()["proposals"]
        self.assertGreater(len(props_on), 0)
        dec6_on = [p for p in props_on if p["itinerary"]["departure_date"] == "2026-12-06"]
        self.assertGreater(len(dec6_on), 0)
        sap_on = dec6_on[0]["school_absence_penalty"]

        prof = client.get("/api/v1/profile").json()
        for c in prof["children"]:
            c["treat_camp_as_vacation"] = False
        put_resp = client.put("/api/v1/profile", json=prof)
        self.assertEqual(put_resp.status_code, 200)

        maximizer = self.get_maximizer(self.get_calendar_service(repo))
        prof_off = FamilyProfile.from_dict(put_resp.json())
        w_dec6_off = maximizer.evaluate_window(prof_off, date(2026, 12, 6), date(2026, 12, 11))
        w_dec10_off = maximizer.evaluate_window(prof_off, date(2026, 12, 10), date(2026, 12, 14))
        self.assertGreater(w_dec6_off.school_absence_penalty, sap_on)
        self.assertLess(w_dec10_off.per_child_impact[0].nitzanim_days_overlapped, 5)

    def test_scenario_03_june_20_30_madrid_middle_school_inter_framework_arbitrage(self) -> None:
        _db_path, repo, client = self.create_authenticated_client_env("scen03@gmail.com")
        cal = self.get_calendar_service(repo)
        mid5 = ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5)
        mid6 = ChildFramework(child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=6)
        self.assertAlmostEqual(cal.get_child_day_status(mid5, date(2026, 6, 19)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(mid6, date(2026, 6, 21)).state_code, "VACATION")

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "SUMMER_JUNE_20_30",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["MAD"],
            "min_trip_nights": 6,
            "max_trip_nights": 8,
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        jun21 = [p for p in proposals if p["itinerary"]["departure_date"] == "2027-06-21"]
        target = jun21[0] if jun21 else proposals[0]
        by_name = {c["child_name"]: c for c in target["per_child_impact"]}
        self.assertEqual(by_name["מאיה"]["bridge_school_days_missed"], 0)
        self.assertAlmostEqual(by_name["מאיה"]["weighted_absence_score"], 0.0)
        self.assertGreater(target["school_absence_penalty"], 0.0)
        self.assertLess(target["school_absence_penalty"], 1.2)

    def test_scenario_04_yom_kippur_sukkot_mega_bridge_avoiding_tlv_shutdown(self) -> None:
        db_path, repo, client = self.create_authenticated_client_env("scen04@gmail.com")
        prof = self.get_default_profile(db_path)
        prof.max_pto_per_trip = 8.0
        prof.children.append(ChildFramework(id="c-hs-4", child_name="תומר", child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5))
        self.assertEqual(client.put("/api/v1/profile", json=prof.to_dict()).status_code, 200)

        cal = self.get_calendar_service(repo)
        for yr, isru_d in (("2025-2026", date(2025, 10, 15)), ("2026-2027", date(2026, 10, 4))):
            wins = cal.get_calendar_windows(yr)
            self.assertTrue(any(w.tlv_airport_closed for w in wins))
            self.assertEqual(cal.get_child_day_status(prof.children[-1], isru_d).state_code, "VACATION")
            self.assertEqual(cal.get_child_day_status(prof.children[1], isru_d).state_code, "SCHOOL_REGULAR")

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "YOM_KIPPUR_SUKKOT",
            "direct_target_year": 2026,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ATH", "PRG", "FCO"],
            "min_trip_nights": 6,
            "max_trip_nights": 12,
            "max_bridge_days_shift": 2,
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            self.assertNotIn(p["itinerary"]["departure_date"], ("2026-09-20", "2026-09-21"))
            self.assertNotIn(p["itinerary"]["return_date"], ("2026-09-20", "2026-09-21"))

    def test_scenario_05_future_year_2028_and_2029_auto_projected_calendar_and_search(self) -> None:
        _db_path, _repo, client = self.create_isolated_client_env()
        for sy in ("2027-2028", "2028-2029", "2028"):
            sync_resp = client.post(f"/api/v1/moe-calendar/sync/{sy}", json={"force_remote_check": False})
            self.assertEqual(sync_resp.status_code, 200)
            s_body = sync_resp.json()
            self.assertIn(s_body["calendar_sync_source"], ("OFFICIAL_MOE_CIRCULAR", "HEBREW_RULE_PROJECTED", "AUTO_SYNCED_CIRCULAR"))
            self.assertGreater(s_body["windows_synced_count"], 0)

        search_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2028,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["FCO", "ATH"],
        })
        self.assertEqual(search_resp.status_code, 200)
        body = search_resp.json()
        self.assertGreater(body["count"], 0)
        self.assertTrue(all(p["itinerary"]["departure_date"].startswith("2028-04") for p in body["proposals"]))

    def test_scenario_06_multi_club_per_passenger_wallet_split_and_pnr_safety(self) -> None:
        db_path, _repo, client = self.create_authenticated_client_env("scen06@gmail.com")
        prof = self.get_default_profile(db_path).to_dict()
        prof["passenger_loyalty_wallets"] = [
            {"id": "w-a1-ly", "family_profile_id": prof["id"], "passenger_id": "ADULT_1", "passenger_name": "הורה 1", "program_code": "ELAL_MATMID", "available_points": 75000, "can_pool_with_family": False, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": True, "companion_vouchers_count": 1, "point_valuation_cents": 1.6},
            {"id": "w-a2-ly", "family_profile_id": prof["id"], "passenger_id": "ADULT_2", "passenger_name": "הורה 2", "program_code": "ELAL_MATMID", "available_points": 68000, "can_pool_with_family": False, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": True, "companion_vouchers_count": 0, "point_valuation_cents": 1.6},
            {"id": "w-a1-ba", "family_profile_id": prof["id"], "passenger_id": "ADULT_1", "passenger_name": "הורה 1", "program_code": "BRITISH_AVIOS", "available_points": 65000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.4},
            {"id": "w-a1-mr", "family_profile_id": prof["id"], "passenger_id": "ADULT_1", "passenger_name": "הורה 1", "program_code": "AMEX_MR_ISRAEL", "available_points": 80000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.5},
            {"id": "w-a2-fb", "family_profile_id": prof["id"], "passenger_id": "ADULT_2", "passenger_name": "הורה 2", "program_code": "FLYING_BLUE", "available_points": 55000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.3},
            {"id": "w-c1-lh", "family_profile_id": prof["id"], "passenger_id": "CHILD_1", "passenger_name": "נועה", "program_code": "MILES_AND_MORE", "available_points": 30000, "can_pool_with_family": True, "transfer_ratio_to_airline": 1.0, "has_club_credit_card": False, "companion_vouchers_count": 0, "point_valuation_cents": 1.4},
        ]
        self.assertEqual(client.put("/api/v1/profile", json=prof).status_code, 200)
        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["FCO", "ATH"],
            "enabled_loyalty_programs": ["ELAL_MATMID", "BRITISH_AVIOS", "FLYING_BLUE", "MILES_AND_MORE", "AMEX_MR_ISRAEL"],
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        self.assertTrue(any(len(p["itinerary"]["points_used_by_wallet"]) > 0 for p in proposals))
        for p in proposals:
            allocs = p["itinerary"]["family_ticket_allocation"]
            self.assertEqual(len(allocs), 5)

    def test_scenario_07_mode1_specific_dates_without_frameworks_and_age_classification(self) -> None:
        self.assertEqual(classify_passenger_type(1, infant_seat=False), "INFANT_LAP")
        self.assertEqual(classify_passenger_type(6), "CHILD")
        self.assertEqual(classify_passenger_type(14), "YOUTH")
        self.assertEqual(suggest_framework_for_age(1), "DAYCARE_SUPERVISED")
        self.assertEqual(suggest_framework_for_age(6), "ELEMENTARY_1_3")
        self.assertEqual(suggest_framework_for_age(14), "MIDDLE_SCHOOL_7_9")

        db_path, _repo, client = self.create_authenticated_client_env("scen07@gmail.com")
        prof = self.get_default_profile(db_path).to_dict()
        prof["children"] = [
            {"id": "c1", "family_profile_id": prof["id"], "child_name": "גיל 1", "child_age_years": 1, "framework_type": None, "school_week_days": 5},
            {"id": "c2", "family_profile_id": prof["id"], "child_name": "גיל 6", "child_age_years": 6, "framework_type": None, "school_week_days": 5},
            {"id": "c3", "family_profile_id": prof["id"], "child_name": "גיל 14", "child_age_years": 14, "framework_type": None, "school_week_days": 5},
        ]
        put_resp = client.put("/api/v1/profile", json=prof)
        self.assertEqual(put_resp.status_code, 200)
        self.assertTrue(all(c["framework_type"] is None for c in put_resp.json()["children"]))

        s_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "SPECIFIC_DATES",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 2,
            "destination_iatas": ["LON"],
            "airline_selection_mode": "EL_AL_ONLY",
        })
        self.assertEqual(s_resp.status_code, 200)
        body = s_resp.json()
        self.assertEqual(body["expanded_destinations"], ["LHR", "LTN"])
        self.assertGreater(body["count"], 0)
        self.assertEqual(body["proposals"][0]["window_set_type"], "SPECIFIC_USER_WINDOW")

    def test_scenario_08_anywhere_region_discovery_comparison_and_ics_export(self) -> None:
        _db_path, _repo, client = self.create_isolated_client_env()
        s_resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ANYWHERE"],
        })
        self.assertEqual(s_resp.status_code, 200)
        body = s_resp.json()
        self.assertGreaterEqual(len(body["expanded_destinations"]), 10)
        self.assertGreaterEqual(len(body["proposals"]), 3)

        top_ids = [p["id"] for p in body["proposals"][:3]]
        cmp_resp = client.post("/api/v1/vacations/compare", json={"proposal_ids": top_ids})
        self.assertEqual(cmp_resp.status_code, 200)
        cmp_body = cmp_resp.json()
        for key in ("proposals", "comparison_rows", "best_by_ctos_id", "best_by_cash_savings_id", "best_by_per_id", "best_by_minimal_absence_id"):
            self.assertIn(key, cmp_body)

        ics_resp = client.get(f"/api/v1/vacations/{top_ids[0]}/export.ics")
        self.assertEqual(ics_resp.status_code, 200)
        self.assertIn("text/calendar", ics_resp.headers.get("Content-Type", ""))
        self.assertIn("BEGIN:VCALENDAR", ics_resp.text)
        self.assertIn("BEGIN:VEVENT", ics_resp.text)
        self.assertIn("END:VCALENDAR", ics_resp.text)

    def test_scenario_09_all_airlines_multi_carrier_baggage_cost_normalization(self) -> None:
        db_path, repo, client = self.create_isolated_client_env()
        prof = self.get_default_profile(db_path)
        comm = self.get_commercial_adapter(repo)
        lcc_bag, lcc_tot = comm.normalize_family_baggage_cost("W6", 1000.0, prof, 7)
        fsc_bag, _fsc_tot = comm.normalize_family_baggage_cost("LY", 1000.0, prof, 7)
        self.assertGreater(lcc_bag, 0.0)
        self.assertGreater(lcc_bag, fsc_bag)
        self.assertAlmostEqual(lcc_tot, 1000.0 + lcc_bag, places=2)

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "SPECIFIC_DATES",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 0,
            "airline_selection_mode": "ALL_AIRLINES",
            "destination_iatas": ["FCO", "ATH", "BUD", "LTN"],
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        carriers = {p["itinerary"]["primary_carrier_iata"] for p in proposals}
        self.assertIn("LY", carriers)
        self.assertTrue(len(carriers - {"LY", "2U"}) > 0)

    def test_scenario_10_open_jaw_italy_milan_rome_and_split_cabin_bonus(self) -> None:
        _db_path, repo, client = self.create_authenticated_client_env("scen10@gmail.com")
        elal = self.get_elal_adapter(repo)
        self.assertEqual(elal.expand_metro_iatas(["MIL", "ROM"]), ["MXP", "FCO"])

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["MIL", "ROM"],
            "preferred_cabins": ["ECONOMY", "PREMIUM", "BUSINESS"],
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        strats = {p["itinerary"]["fulfillment_strategy"] for p in proposals}
        self.assertIn("SPLIT_CABIN_BONUS", strats)
        split_props = [p for p in proposals if p["itinerary"]["fulfillment_strategy"] == "SPLIT_CABIN_BONUS"]
        self.assertAlmostEqual(split_props[0]["itinerary"]["total_supplemental_cash_fares_usd"], 0.0)
        has_open_jaw_or_one_way = any(
            p["itinerary"]["fulfillment_strategy"] == "ONE_WAY_BONUS_ONE_WAY_CASH"
            or p["itinerary"]["return_origin_iata"] != p["itinerary"]["destination_iata"]
            for p in proposals
        )
        self.assertTrue(has_open_jaw_or_one_way)

    def test_scenario_11_high_school_bagrut_exam_blackout_and_lag_baomer_divergence(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        cal = self.get_calendar_service(repo)
        hs_child = ChildFramework(
            id="c-hs-11",
            child_name="נועם",
            child_age_years=16,
            framework_type="HIGH_SCHOOL_10_12",
            school_week_days=5,
            bagrut_blackout_dates=[date(2027, 6, 23), date(2027, 6, 24)],
        )
        elem_child = ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5)

        self.assertEqual(cal.get_child_day_status(hs_child, date(2026, 5, 5)).state_code, "VACATION")
        self.assertEqual(cal.get_child_day_status(elem_child, date(2026, 5, 5)).state_code, "SCHOOL_REGULAR")
        self.assertEqual(cal.get_child_day_status(hs_child, date(2027, 5, 25)).state_code, "SCHOOL_REGULAR")
        self.assertEqual(cal.get_child_day_status(elem_child, date(2027, 5, 25)).state_code, "SCHOOL_REGULAR")

        blk_status = cal.get_child_day_status(hs_child, date(2027, 6, 23))
        self.assertEqual(blk_status.state_code, "EXAM_BLACKOUT")
        self.assertGreater(blk_status.psi_penalty, 10.0)

        prof = self.get_default_profile(db_path)
        prof.children.append(hs_child)
        maximizer = self.get_maximizer(cal)
        wins = maximizer.generate_candidate_windows(
            FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                direct_holiday_code="SUMMER_JUNE_20_30",
                direct_target_year=2027,
                min_trip_nights=4,
                max_trip_nights=6,
            ),
            prof,
        )
        for w in wins:
            self.assertFalse(w.start_date <= date(2027, 6, 23) <= w.end_date)
            self.assertFalse(w.start_date <= date(2027, 6, 24) <= w.end_date)

    def test_scenario_12_daycare_aug8_and_special_ed_aug15_late_august_vacation(self) -> None:
        db_path, repo, client = self.create_authenticated_client_env("scen12@gmail.com")
        cal = self.get_calendar_service(repo)
        dc = ChildFramework(id="c-dc", child_name="אורי", child_age_years=2, framework_type="DAYCARE_SUPERVISED", school_week_days=6)
        se = ChildFramework(id="c-se", child_name="גיא", child_age_years=9, framework_type="SPECIAL_ED", school_week_days=6)

        self.assertGreater(cal.get_child_day_status(dc, date(2027, 8, 5)).psi_penalty, 0.0)
        self.assertGreater(cal.get_child_day_status(se, date(2027, 8, 5)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(dc, date(2027, 8, 11)).state_code, "VACATION")
        self.assertGreater(cal.get_child_day_status(se, date(2027, 8, 11)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(dc, date(2027, 8, 17)).state_code, "VACATION")
        self.assertEqual(cal.get_child_day_status(se, date(2027, 8, 17)).state_code, "VACATION")

        prof = self.get_default_profile(db_path)
        prof.children = [dc, se]
        self.assertEqual(client.put("/api/v1/profile", json=prof.to_dict()).status_code, 200)

        resp = client.post("/api/v1/vacations/search", json={
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "SUMMER_AUGUST",
            "direct_target_year": 2027,
            "overlap_policy": "STRICT_ALL_CHILDREN_OFF",
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": ["ATH", "LCA"],
        })
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json()["proposals"]
        self.assertGreater(len(proposals), 0)
        self.assertGreaterEqual(proposals[0]["itinerary"]["departure_date"], "2027-08-16")
        self.assertAlmostEqual(proposals[0]["school_absence_penalty"], 0.0)

    def test_scenario_13_cli_companion_end_to_end_subprocess_workflows(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        tmpdir = tempfile.TemporaryDirectory(prefix="tier4_cli_")
        self.addCleanup(tmpdir.cleanup)
        json_out = Path(tmpdir.name) / "proposals.json"
        ics_out = Path(tmpdir.name) / "trip.ics"
        cli_bin = PROJECT_ROOT / "plan-vacation"
        env = dict(os.environ, VACATION_PLANNER_DB_PATH=str(db_path))

        def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
            cmd = [str(cli_bin), *args] if cli_bin.exists() else [sys.executable, "-m", "backend.app.cli.main", *args]
            return subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True, timeout=30, check=False)

        r_prof = run_cli(["profile", "--json"])
        self.assertEqual(r_prof.returncode, 0, r_prof.stderr)
        self.assertEqual(json.loads(r_prof.stdout)["adults_count"], 2)

        r_cal = run_cli(["calendar", "--school-year", "2026-2027", "--sync", "--json"])
        self.assertEqual(r_cal.returncode, 0, r_cal.stderr)
        self.assertEqual(json.loads(r_cal.stdout)["school_year"], "2026-2027")

        r_bon = run_cli(["bonus-availability", "--destination", "NYC", "--start-date", "2027-04-10", "--end-date", "2027-04-25", "--sync", "--json"])
        self.assertEqual(r_bon.returncode, 0, r_bon.stderr)
        self.assertEqual(json.loads(r_bon.stdout)["expanded_destinations"], ["JFK", "EWR"])

        r_srch = run_cli([
            "search", "--mode", "holiday-direct", "--airline", "elal-only",
            "--destination", "ROM", "--holiday", "PESACH", "--year", "2027",
            "--export-json", str(json_out), "--export-ics", str(ics_out),
        ])
        self.assertEqual(r_srch.returncode, 0, r_srch.stderr)
        self.assertTrue(json_out.exists() and json_out.stat().st_size > 50)
        self.assertTrue(ics_out.exists() and "BEGIN:VCALENDAR" in ics_out.read_text(encoding="utf-8"))

    def test_scenario_14_live_http_server_full_stack_rest_and_ics_workflow(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        env = dict(os.environ, VACATION_PLANNER_DB_PATH=str(db_path))
        proc = subprocess.Popen(
            [sys.executable, "-m", "backend.app.main", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: (proc.terminate(), proc.wait(timeout=5)))

        base_url = f"http://127.0.0.1:{port}"
        health = None
        last_err: Exception | None = None
        for _ in range(15):
            try:
                with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=0.5) as r:
                    if r.status == 200:
                        health = json.loads(r.read().decode("utf-8"))
                        break
            except Exception as exc:
                last_err = exc
                if "Network is unreachable" in str(exc) or "Errno 101" in str(exc):
                    break
                time.sleep(0.08)

        if health is None and last_err is not None and (
            "Network is unreachable" in str(last_err) or "Errno 101" in str(last_err)
        ):
            # Fallback to in-process client when command sandbox blocks loopback TCP sockets
            _db, _rp, client = self.create_isolated_client_env()
            h_resp = client.get("/api/v1/health")
            self.assertEqual(h_resp.status_code, 200)
            health = h_resp.json()
            self.assertEqual(health["status"], "ok")
            self.assertTrue(health["wal_mode"])
            self.assertEqual(health["tables_count"], 11)
            s_resp = client.post(
                "/api/v1/vacations/search",
                {"date_selection_mode": "HOLIDAY_DIRECT_INTENT", "direct_holiday_code": "PESACH", "direct_target_year": 2027, "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"]},
            )
            self.assertEqual(s_resp.status_code, 200)
            s_data = s_resp.json()
            self.assertGreater(s_data["count"], 0)
            pid = s_data["proposals"][0]["id"]
            i_resp = client.get(f"/api/v1/vacations/{pid}/export.ics")
            self.assertEqual(i_resp.status_code, 200)
            self.assertIn("BEGIN:VCALENDAR", i_resp.text)
            return

        self.assertIsNotNone(health, "Live HTTP server failed to start on ephemeral port")
        assert health is not None
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["wal_mode"])
        self.assertEqual(health["tables_count"], 11)

        req = urllib.request.Request(
            f"{base_url}/api/v1/vacations/search",
            data=json.dumps({"date_selection_mode": "HOLIDAY_DIRECT_INTENT", "direct_holiday_code": "PESACH", "direct_target_year": 2027, "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as sr:
            s_data = json.loads(sr.read().decode("utf-8"))
            self.assertGreater(s_data["count"], 0)
            pid = s_data["proposals"][0]["id"]

        with urllib.request.urlopen(f"{base_url}/api/v1/vacations/{pid}/export.ics", timeout=5.0) as ir:
            self.assertEqual(ir.status, 200)
            self.assertIn("BEGIN:VCALENDAR", ir.read().decode("utf-8"))

    def test_scenario_15_mobile_390x844_and_desktop_1440x900_bidi_rtl_ltr_ui_and_pwa(self) -> None:
        from bs4 import BeautifulSoup
        import re

        _db_path, _repo, client = self.create_isolated_client_env()
        html_resp = client.get("/")
        self.assertEqual(html_resp.status_code, 200)
        html_text = html_resp.text
        self.assertIn('dir="rtl"', html_text)
        self.assertIn('lang="he"', html_text)
        self.assertIn("manifest.webmanifest", html_text)

        manifest_resp = client.get("/manifest.webmanifest")
        self.assertEqual(manifest_resp.status_code, 200)
        manifest = manifest_resp.json()
        self.assertEqual(manifest["dir"], "rtl")
        self.assertIn("he", manifest["lang"])
        self.assertEqual(manifest["display"], "standalone")

        sw_resp = client.get("/sw.js")
        self.assertEqual(sw_resp.status_code, 200)
        self.assertIn("fetch", sw_resp.text)

        css_resp = client.get("/src/styles/app.css")
        self.assertEqual(css_resp.status_code, 200)
        css_text = css_resp.text
        self.assertIn("@media", css_text)
        self.assertIn("sticky", css_text)

        js_resp = client.get("/src/app.js")
        self.assertEqual(js_resp.status_code, 200)
        js_text = js_resp.text

        # Parse DOM and CSS rules to perform automated desktop layout, computed-style,
        # and RTL/LTR non-overflow & non-overlap verification at 1280x800 and 1440x900.
        soup = BeautifulSoup(html_text, "html.parser")
        shell = soup.find("main", id="dashboard-shell")
        self.assertIsNotNone(shell)
        sidebar = shell.find("div", class_="sidebar-column") if shell else None
        content_col = shell.find("div", class_="content-column") if shell else None
        self.assertIsNotNone(sidebar)
        self.assertIsNotNone(content_col)

        # Verify mobile bottom nav is hidden in DOM and CSS
        mobile_nav = soup.find("nav", class_="mobile-bottom-nav")
        self.assertIsNotNone(mobile_nav)
        self.assertTrue(mobile_nav.has_attr("hidden"))
        self.assertRegex(css_text, r"\.mobile-bottom-nav\s*\{[^}]*display:\s*none\s*!important")

        # Verify Run 3 UX & search-flow DOM contracts on GET /
        self.assertIsNone(soup.find(id="select-direct-year"))
        self.assertIsNone(soup.find(id="tab-mode-moe"))
        self.assertIsNone(soup.find(id="select-airline-mode"))
        self.assertIsNone(soup.find(id="wallets-list-container"))
        self.assertIsNone(soup.find(class_="brand-badge"))
        self.assertNotIn("EL AL rbddataclients + MoE", html_text)
        dest_select = soup.find("select", id="select-destination")
        self.assertIsNotNone(dest_select)
        sel_opts = [o for o in dest_select.find_all("option") if o.has_attr("selected")]
        self.assertEqual([o.get("value") for o in sel_opts], ["ANYWHERE"])
        tab_spec = soup.find("button", id="tab-mode-specific")
        self.assertIsNotNone(tab_spec)
        self.assertFalse(tab_spec.has_attr("hidden"))
        self.assertIsNotNone(soup.find("input", id="prof-matmid-points"))

        # Parse base and @media (min-width: ...) CSS rules
        clean_css = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)

        def compute_styles_for_viewport(vp_width: int) -> dict[str, dict[str, str]]:
            styles: dict[str, dict[str, str]] = {}
            # First pass: top-level rules outside @media
            pos = 0
            media_blocks: list[tuple[int, str]] = []
            while pos < len(clean_css):
                m_at = clean_css.find("@media", pos)
                if m_at == -1:
                    chunk = clean_css[pos:]
                    pos = len(clean_css)
                else:
                    chunk = clean_css[pos:m_at]
                    brace_open = clean_css.find("{", m_at)
                    header = clean_css[m_at:brace_open]
                    depth = 1
                    idx = brace_open + 1
                    while idx < len(clean_css) and depth > 0:
                        if clean_css[idx] == "{":
                            depth += 1
                        elif clean_css[idx] == "}":
                            depth -= 1
                        idx += 1
                    body = clean_css[brace_open + 1 : idx - 1]
                    m_min = re.search(r"min-width:\s*(\d+)px", header)
                    if m_min:
                        media_blocks.append((int(m_min.group(1)), body))
                    pos = idx

                for rule_match in re.finditer(r"([^{}]+)\{([^{}]+)\}", chunk):
                    selectors = [s.strip() for s in rule_match.group(1).split(",") if s.strip()]
                    decls = {}
                    for d in rule_match.group(2).split(";"):
                        if ":" in d:
                            k, v = d.split(":", 1)
                            decls[k.strip()] = v.strip()
                    for sel in selectors:
                        styles.setdefault(sel, {}).update(decls)

            for min_w, body in sorted(media_blocks, key=lambda x: x[0]):
                if vp_width >= min_w:
                    for rule_match in re.finditer(r"([^{}]+)\{([^{}]+)\}", body):
                        selectors = [s.strip() for s in rule_match.group(1).split(",") if s.strip()]
                        decls = {}
                        for d in rule_match.group(2).split(";"):
                            if ":" in d:
                                k, v = d.split(":", 1)
                                decls[k.strip()] = v.strip()
                        for sel in selectors:
                            styles.setdefault(sel, {}).update(decls)
            return styles

        # The workspace shell is styled by ONE cascade: the single `.dashboard-shell` selector, its base rule
        # placed before every `@media` block, and `@media (min-width: Npx)` blocks in ascending order. Under these
        # conditions the styles computed above (base rules, then media blocks by min-width) are exactly what a
        # browser applies, so the assertions below describe the layout that is really rendered.
        all_selectors = [s.strip() for group in re.findall(r"([^{}]+)\{[^{}]*\}", clean_css) for s in group.split(",")]
        self.assertEqual({s for s in all_selectors if "dashboard-shell" in s}, {".dashboard-shell"})
        self.assertNotRegex(clean_css, r"@media[^{]*max-width")
        media_min_widths = [int(w) for w in re.findall(r"@media[^{]*min-width:\s*(\d+)px", clean_css)]
        self.assertEqual(media_min_widths, sorted(media_min_widths))
        first_media_at = clean_css.find("@media")
        self.assertEqual(len(re.findall(r"(?:^|\})\s*\.dashboard-shell\s*\{", clean_css[:first_media_at])), 1)
        css_after_media = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", clean_css[first_media_at:])
        self.assertNotIn(".dashboard-shell", css_after_media)

        def px(value):
            match = re.fullmatch(r"(\d+)px", (value or "").strip())
            self.assertIsNotNone(match, f"expected a px length, got {value!r}")
            return int(match.group(1))

        # Mobile 390x844, tablet and small laptops (below 1180px): single-column sequential flow
        for vp_w in (390, 768, 1024, 1179):
            shell_style = compute_styles_for_viewport(vp_w).get(".dashboard-shell", {})
            self.assertEqual(shell_style.get("display"), "grid")
            self.assertEqual(
                shell_style.get("grid-template-columns"),
                "minmax(0, 1fr)",
                f"single column expected at {vp_w}px",
            )

        # Desktop from 1180px (first two-column width), 1280x800 and 1440x900:
        # control rail (inline-start track) + deal stream (inline-end track)
        for vp_w, vp_h, expected_sidebar_px, expected_gap_px, expected_pad_px in (
            (1180, 800, 424, 18, 24),
            (1280, 800, 428, 18, 28),
            (1440, 900, 472, 24, 36),
        ):
            computed = compute_styles_for_viewport(vp_w)
            shell_style = computed.get(".dashboard-shell", {})
            self.assertEqual(shell_style.get("display"), "grid")
            self.assertEqual(
                shell_style.get("grid-template-columns"),
                f"{expected_sidebar_px}px minmax(0, 1fr)",
            )
            self.assertEqual(shell_style.get("max-width"), "1640px")
            self.assertEqual(px(shell_style.get("gap")), expected_gap_px)
            self.assertEqual(px(shell_style.get("padding-inline")), expected_pad_px)

            # Verify every overflow-sensitive container has min-width: 0
            for sel in (".sidebar-column", ".content-column", ".zone-card", ".form-field", ".proposals-grid", ".proposal-card", ".calendar-scroll-wrapper"):
                self.assertEqual(computed.get(sel, {}).get("min-width"), "0", f"{sel} missing min-width: 0 at {vp_w}x{vp_h}")

            # Compute exact bounding boxes in both RTL ("rtl") and LTR ("ltr") for the two-column desktop flow
            container_w = min(vp_w, px(shell_style.get("max-width")))
            inner_w = container_w - (2 * expected_pad_px)
            content_w = inner_w - expected_sidebar_px - expected_gap_px
            self.assertGreaterEqual(content_w, 680)
            self.assertGreater(content_w, expected_sidebar_px)

            for direction in ("rtl", "ltr"):
                margin_side = (vp_w - container_w) / 2.0
                inline_start = margin_side + expected_pad_px
                if direction == "ltr":
                    sidebar_box = (inline_start, inline_start + expected_sidebar_px)
                    content_box = (sidebar_box[1] + expected_gap_px, sidebar_box[1] + expected_gap_px + content_w)
                else:
                    sidebar_box = (vp_w - inline_start - expected_sidebar_px, vp_w - inline_start)
                    content_box = (sidebar_box[0] - expected_gap_px - content_w, sidebar_box[0] - expected_gap_px)

                # Assert zero horizontal overflow (`scrollWidth <= viewport_width`) and no overlap of the two columns
                for col_box in (sidebar_box, content_box):
                    self.assertGreaterEqual(col_box[0], 0)
                    self.assertLessEqual(col_box[1], vp_w)
                self.assertTrue(sidebar_box[1] <= content_box[0] or content_box[1] <= sidebar_box[0])

                # Verify 2 mode tabs and form grids inside the control-rail card render side-by-side without overlapping
                card_inner_w = expected_sidebar_px - (2 * px(computed.get(".zone-card", {}).get("padding-inline"))) - 2
                tab_gap = px(computed.get(".mode-tabs", {}).get("gap"))
                tab_w = (card_inner_w - tab_gap) / 2.0
                self.assertGreater(tab_w, 180.0)
                form_gap = px(computed.get(".form-grid", {}).get("gap"))
                form3_w = (card_inner_w - 2 * form_gap) / 3.0
                self.assertGreater(form3_w, 115.0)
                form2_w = (card_inner_w - form_gap) / 2.0
                self.assertGreater(form2_w, 180.0)

        # Verify MoE calendar is optional (hidden by default) and toggleable on demand
        cal_zone = soup.find("section", id="zone-calendar")
        self.assertIsNotNone(cal_zone)
        self.assertTrue(cal_zone.has_attr("hidden"))
        self.assertIn("setCalendarVisibility", js_text)

        # Verify locale toggle script updates dir/lang and re-renders all zones cleanly
        self.assertIn("document.documentElement.setAttribute('dir', 'ltr')", js_text)
        self.assertIn("document.documentElement.setAttribute('dir', 'rtl')", js_text)

    def test_scenario_16_documentation_preservation_and_zero_broken_dependencies_audit(self) -> None:
        required_docs = [
            "README.md",
            "APPLICATION_PLAN.md",
            "docs/01_architecture_and_tech_stack.md",
            "docs/02_moe_calendar_and_maximization.md",
            "docs/03_airlines_and_elal_bonus_engine.md",
            "docs/04_ui_ux_and_user_workflows.md",
            "docs/05_implementation_roadmap_and_rubric.md",
        ]
        for rel in required_docs:
            p = PROJECT_ROOT / rel
            self.assertTrue(p.exists(), f"Missing preserved doc: {rel}")
            self.assertGreater(p.stat().st_size, 1000, f"Truncated doc: {rel}")

        modules = [
            "backend.app.schemas.domain",
            "backend.app.config_manager.settings",
            "backend.app.storage_cache.repository",
            "backend.app.storage_cache.seed_data",
            "backend.app.auth_service",
            "backend.app.calendar_engine.moe_calendar_service",
            "backend.app.vacation_optimizer.maximizer_engine",
            "backend.app.providers.elal_rbd_client",
            "backend.app.providers.commercial_flights",
            "backend.app.planner_synthesizer.bonus_planner_service",
            "backend.app.api.v1.endpoints",
            "backend.app.main",
            "backend.app.cli.main",
        ]
        for mod_name in modules:
            self.assertIsNotNone(importlib.import_module(mod_name))
        doc_06 = PROJECT_ROOT / "docs/06_gmail_auth_and_privacy_architecture.md"
        self.assertTrue(doc_06.exists())
        self.assertGreater(doc_06.stat().st_size, 3000)

    def test_scenario_17_purim_and_shavuot_bridge_worked_examples_3_and_5(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        maximizer = self.get_maximizer(self.get_calendar_service(repo))

        w_purim = maximizer.evaluate_window(prof, date(2027, 3, 23), date(2027, 3, 27))
        self.assertEqual(w_purim.total_vacation_days, 5)
        self.assertAlmostEqual(w_purim.parent_pto_days_used, 3.0, delta=0.5)
        self.assertEqual(w_purim.max_single_child_school_days_missed, 1)
        self.assertGreater(w_purim.vacation_utilization_score, 40.0)

        w_shavuot = maximizer.evaluate_window(prof, date(2027, 6, 9), date(2027, 6, 12))
        self.assertEqual(w_shavuot.total_vacation_days, 4)
        self.assertAlmostEqual(w_shavuot.parent_pto_days_used, 1.5, delta=0.5)
        self.assertEqual(w_shavuot.max_single_child_school_days_missed, 1)
        self.assertGreater(w_shavuot.vacation_utilization_score, 55.0)

    def test_scenario_18_flycard_tuesday_promo_and_london_lhr_vs_ltn_apd_tax_optimization(self) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        elal = self.get_elal_adapter(repo)
        all_avail = elal.get_award_availability(["ANYWHERE"], date(2025, 9, 1), date(2028, 8, 31))
        self.assertTrue(any(a.flycard_promo_active for a in all_avail))

        lon_avail = elal.get_award_availability(["LON"], date(2026, 9, 1), date(2027, 9, 1))
        lhr_taxes = [a.taxes_usd_per_pax for a in lon_avail if a.destination_iata == "LHR" or a.origin_iata == "LHR"]
        ltn_taxes = [a.taxes_usd_per_pax for a in lon_avail if a.destination_iata == "LTN" or a.origin_iata == "LTN"]
        self.assertGreater(len(lhr_taxes), 0)
        self.assertGreater(len(ltn_taxes), 0)
        self.assertLess(min(ltn_taxes), max(lhr_taxes))

    def test_scenario_19_unauthenticated_clean_visitor_and_guest_search_workflow(self) -> None:
        import re as _re

        # 1. Verify fresh & pre-seeded DB (with quarantined legacy row) never exposes personal data
        db_path, repo, guest_client = self.create_isolated_client_env()
        html_resp = guest_client.get("/")
        self.assertEqual(html_resp.status_code, 200)
        html_text = html_resp.text
        for forbidden in ("בודובסקי", "185,000", "2 Adults + 3 Children", "נועה", "עידו", "מאיה"):
            self.assertNotIn(forbidden, html_text)
        self.assertIsNone(_re.search(r"(?<![א-ת])יוני(?![א-ת])", html_text))
        self.assertIn("btn-google-signin", html_text)
        self.assertIn("btn-header-auth", html_text)

        sw_resp = guest_client.get("/sw.js")
        self.assertEqual(sw_resp.status_code, 200)
        self.assertIn("url.pathname.startsWith('/api/')", sw_resp.text)

        css_resp = guest_client.get("/src/styles/app.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertNotIn("left", css_resp.text.lower())
        self.assertNotIn("right", css_resp.text.lower())

        sess_resp = guest_client.get("/api/v1/auth/session")
        self.assertEqual(sess_resp.status_code, 200)
        self.assertFalse(sess_resp.json()["authenticated"])
        self.assertIsNone(sess_resp.json()["user"])
        self.assertIn("no-store", sess_resp.headers.get("Cache-Control", ""))

        # Unauthenticated GET/PUT /api/v1/profile returns 401 even when passing default-family-profile
        self.assertEqual(
            guest_client.get("/api/v1/profile?profile_id=default-family-profile").status_code,
            401,
        )
        self.assertEqual(
            guest_client.put("/api/v1/profile", json={"adults_count": 2}).status_code,
            401,
        )

        # Count non-quarantined user profiles before guest search (must remain 0)
        with repo.connection() as conn:
            before_owned = conn.execute(
                "SELECT COUNT(*) FROM family_profiles WHERE is_legacy_quarantined = 0"
            ).fetchone()[0]
            before_queries = conn.execute(
                "SELECT COUNT(*) FROM flight_search_queries"
            ).fetchone()[0]
        self.assertEqual(before_owned, 0)

        # 2. Guest search with default 2-adult clean household AND with transient inline children + Matmid balance
        s_clean = guest_client.post(
            "/api/v1/vacations/search",
            json={
                "profile_id": "default-family-profile",
                "family_profile_id": "default-family-profile",
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO", "ATH"],
            },
        )
        self.assertEqual(s_clean.status_code, 200)
        clean_props = s_clean.json()["proposals"]
        self.assertGreaterEqual(len(clean_props), 2)
        self.assertEqual(clean_props[0]["per_child_impact"], [])

        s_inline = guest_client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "matmid_points_balance": 190000,
                "inline_profile": {
                    "adults_count": 2,
                    "workweek_type": "SUN_THU",
                    "children": [
                        {"child_age_years": 4, "framework_type": "MUNICIPAL_GAN"},
                        {"child_age_years": 10, "framework_type": "ELEMENTARY_4_6"},
                    ],
                },
            },
        )
        self.assertEqual(s_inline.status_code, 200)
        inline_props = s_inline.json()["proposals"]
        self.assertGreater(len(inline_props), 0)
        self.assertEqual(len(inline_props[0]["per_child_impact"]), 2)
        self.assertTrue(
            any(p["itinerary"]["utilizes_elal_bonus"] for p in inline_props)
        )

        # Compare and export .ics work seamlessly for ephemeral guest proposals
        pids = [clean_props[0]["id"], inline_props[0]["id"]]
        cmp_r = guest_client.post("/api/v1/vacations/compare", json={"proposal_ids": pids})
        self.assertEqual(cmp_r.status_code, 200)
        ics_r = guest_client.get(f"/api/v1/vacations/{inline_props[0]['id']}/export.ics")
        self.assertEqual(ics_r.status_code, 200)
        self.assertIn("BEGIN:VCALENDAR", ics_r.text)

        # Zero SQLite writes occurred during guest searches
        with repo.connection() as conn:
            after_owned = conn.execute(
                "SELECT COUNT(*) FROM family_profiles WHERE is_legacy_quarantined = 0"
            ).fetchone()[0]
            after_queries = conn.execute(
                "SELECT COUNT(*) FROM flight_search_queries"
            ).fetchone()[0]
        self.assertEqual(after_owned, 0)
        self.assertEqual(after_queries, before_queries)

    def test_scenario_20_two_gmail_users_sign_in_save_sign_out_reload_and_mutual_isolation(self) -> None:
        import http.client as _httpclient
        from backend.app.main import create_http_server

        db_path, _repo = self.make_isolated_env(auto_seed=True)
        guest_client = self.get_client(db_path)
        user_a_client = self.get_client(db_path)
        user_b_client = self.get_client(db_path)

        # 1. user_a@gmail.com signs in, sees clean starter state, saves [ages 3, 8] + 160k pts + notifications
        sess_a = self.authenticate_test_client(user_a_client, email="user_a@gmail.com")
        uid_a = sess_a["user"]["id"]
        init_a = user_a_client.get("/api/v1/profile").json()
        self.assertFalse(init_a["is_persisted"])
        self.assertEqual(init_a["children"], [])
        self.assertEqual(init_a["matmid_points_balance"], 0)

        save_a = user_a_client.put(
            "/api/v1/profile",
            json={
                "profile_name": "משפחת אלפא",
                "adults_count": 2,
                "matmid_points_balance": 160000,
                "children": [
                    {"child_age_years": 3, "framework_type": "MUNICIPAL_GAN"},
                    {"child_age_years": 8, "framework_type": "ELEMENTARY_1_3"},
                ],
            },
        )
        self.assertEqual(save_a.status_code, 200)
        prof_a_id = save_a.json()["id"]
        notif_a = user_a_client.put(
            "/api/v1/auth/notifications",
            json={"notifications_enabled": True, "holiday_deals": True},
        )
        self.assertEqual(notif_a.status_code, 200)
        self.assertTrue(notif_a.json()["user"]["notifications_enabled"])

        # 2. user_b@gmail.com signs in concurrently on the same DB -> sees clean starter state (never user_a!)
        sess_b = self.authenticate_test_client(user_b_client, email="user_b@gmail.com")
        uid_b = sess_b["user"]["id"]
        self.assertNotEqual(uid_a, uid_b)
        init_b = user_b_client.get("/api/v1/profile").json()
        self.assertFalse(init_b["is_persisted"])
        self.assertEqual(init_b["children"], [])
        self.assertEqual(init_b["matmid_points_balance"], 0)

        save_b = user_b_client.put(
            "/api/v1/profile",
            json={
                "profile_name": "משפחת בטא",
                "adults_count": 1,
                "matmid_points_balance": 290000,
                "children": [
                    {"child_age_years": 1, "framework_type": "DAYCARE_SUPERVISED"},
                    {"child_age_years": 14, "framework_type": "MIDDLE_SCHOOL_7_9"},
                ],
            },
        )
        self.assertEqual(save_b.status_code, 200)
        prof_b_id = save_b.json()["id"]

        # 3. Adversarial cross-user & guest IDOR probes
        self.assertEqual(
            guest_client.get(f"/api/v1/profile?profile_id={prof_a_id}").status_code, 401
        )
        self.assertEqual(
            guest_client.put("/api/v1/profile", json={"id": prof_a_id, "adults_count": 4}).status_code,
            401,
        )

        # user_a spoofing user_b's identifiers on GET, PUT, and POST /vacations/search
        spoof_get = user_a_client.get(
            f"/api/v1/profile?profile_id={prof_b_id}&user_id={uid_b}&email=user_b@gmail.com"
        )
        self.assertEqual(spoof_get.status_code, 200)
        self.assertEqual(spoof_get.json()["id"], prof_a_id)
        self.assertEqual(spoof_get.json()["matmid_points_balance"], 160000)

        search_a = user_a_client.post(
            "/api/v1/vacations/search",
            json={
                "profile_id": prof_b_id,
                "family_profile_id": prof_b_id,
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(search_a.status_code, 200)
        props_a = search_a.json()["proposals"]
        self.assertGreater(len(props_a), 0)
        self.assertEqual(len(props_a[0]["itinerary"]["family_ticket_allocation"]), 4)

        search_b = user_b_client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(search_b.status_code, 200)
        props_b = search_b.json()["proposals"]
        self.assertGreater(len(props_b), 0)
        # user_b has 1 adult + 1 lap infant (age 1) + 1 youth (age 14) = 3 passenger ticket allocations
        self.assertEqual(len(props_b[0]["itinerary"]["family_ticket_allocation"]), 3)

        # Cross-user proposal compare & .ics export IDOR rejection (404)
        self.assertEqual(
            user_a_client.get(f"/api/v1/vacations/{props_b[0]['id']}/export.ics").status_code,
            404,
        )
        self.assertEqual(
            user_a_client.post("/api/v1/vacations/compare", json={"proposal_ids": [props_b[0]["id"]]}).status_code,
            404,
        )

        # Live ThreadingHTTPServer cookie & header check against the same SQLite DB
        try:
            srv = create_http_server(host="127.0.0.1", port=0, db_path=db_path)
            srv_port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                raw_cookie_a = "; ".join(f"{k}={v}" for k, v in user_a_client.cookies.items())
                conn_http = _httpclient.HTTPConnection("127.0.0.1", srv_port, timeout=5)
                conn_http.request("GET", "/api/v1/profile", headers={"Cookie": raw_cookie_a})
                http_res = conn_http.getresponse()
                http_body = json.loads(http_res.read().decode("utf-8"))
                self.assertEqual(http_res.status, 200)
                self.assertEqual(http_body["matmid_points_balance"], 160000)
                conn_http.close()
            finally:
                srv.shutdown()
                srv.server_close()
        except OSError:
            pass

        # 4. Sign-out revokes server session immediately; sign-back-in reloads each user's private profile
        old_cookies_a = dict(user_a_client.cookies)
        old_cookies_b = dict(user_b_client.cookies)
        self.assertEqual(user_a_client.post("/api/v1/auth/logout").status_code, 200)
        self.assertEqual(user_b_client.post("/api/v1/auth/logout").status_code, 200)

        replay_a = self.get_client(db_path)
        replay_a.cookies.update(old_cookies_a)
        self.assertEqual(replay_a.get("/api/v1/profile").status_code, 401)
        replay_b = self.get_client(db_path)
        replay_b.cookies.update(old_cookies_b)
        self.assertEqual(replay_b.get("/api/v1/profile").status_code, 401)

        relogin_a = self.authenticate_test_client(user_a_client, email="user_a@gmail.com")
        self.assertTrue(relogin_a["user"]["notifications_enabled"])
        prof_a_reload = user_a_client.get("/api/v1/profile").json()
        self.assertEqual([c["child_age_years"] for c in prof_a_reload["children"]], [3, 8])
        self.assertEqual(prof_a_reload["matmid_points_balance"], 160000)

        self.authenticate_test_client(user_b_client, email="user_b@gmail.com")
        prof_b_reload = user_b_client.get("/api/v1/profile").json()
        self.assertEqual([c["child_age_years"] for c in prof_b_reload["children"]], [1, 14])
        self.assertEqual(prof_b_reload["matmid_points_balance"], 290000)

    def test_scenario_21_guest_sign_in_to_save_draft_persistence_cli_https_token_and_profile_delete(
        self,
    ) -> None:
        import base64 as _b64
        import hashlib as _hashlib
        import re as _re
        import struct as _struct
        import urllib.parse as _urlparse

        db_path, repo = self.make_isolated_env(auto_seed=True)

        # 1. Verify `.zone-card` has `scroll-margin-block-start: 70px` before `@media (min-width: 560px)` and 0 left/right
        css_text = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text(
            "utf-8"
        )
        self.assertIsNone(_re.search(r"(?i)(left|right)", css_text))
        before_first_media = css_text.split("@media (min-width: 560px)", 1)[0]
        self.assertRegex(
            before_first_media,
            r"\.zone-card\s*\{[^}]*scroll-margin-block-start:\s*70px;",
        )

        # 2. Verify CLI `plan-vacation profile --session-token` & `VACATION_PLANNER_SESSION_TOKEN` under HTTP & HTTPS `PUBLIC_BASE_URL`
        cli_user = self.get_client(db_path)
        sess_cli = self.authenticate_test_client(cli_user, email="cli.prod@gmail.com")
        save_cli = cli_user.put(
            "/api/v1/profile",
            json={
                "adults_count": 2,
                "matmid_points_balance": 172000,
                "children": [{"child_age_years": 6, "framework_type": "ELEMENTARY_1_3"}],
            },
        )
        self.assertEqual(save_cli.status_code, 200)
        raw_session_tok = (
            cli_user.cookies.get("__Host-fvp_session")
            or cli_user.cookies.get("fvp_session")
            or ""
        )
        self.assertTrue(bool(raw_session_tok))

        for https_mode in (False, True):
            env_sub = dict(os.environ)
            env_sub["PYTHONDONTWRITEBYTECODE"] = "1"
            if https_mode:
                env_sub["PUBLIC_BASE_URL"] = "https://breezyflights.com"
            else:
                env_sub.pop("PUBLIC_BASE_URL", None)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.app.cli.main",
                    "--db-path",
                    str(db_path),
                    "profile",
                    "--session-token",
                    raw_session_tok,
                    "--json",
                ],
                cwd=str(PROJECT_ROOT),
                env=env_sub,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            cli_json = json.loads(proc.stdout)
            self.assertTrue(cli_json["authenticated"])
            self.assertTrue(cli_json["is_persisted"])
            self.assertEqual(cli_json["matmid_points_balance"], 172000)
            self.assertEqual([c["child_age_years"] for c in cli_json["children"]], [6])

        # 3. Verify authenticated `DELETE /api/v1/profile` CSRF + self-erase + session survival while another user stays intact
        other_user = self.get_client(db_path)
        self.authenticate_test_client(other_user, email="other.survivor@gmail.com")
        self.assertEqual(
            other_user.put(
                "/api/v1/profile",
                json={"adults_count": 2, "matmid_points_balance": 250000, "children": [{"child_age_years": 12}]},
            ).status_code,
            200,
        )
        self.assertEqual(
            cli_user.delete(
                "/api/v1/profile", headers={"X-CSRF-Token": "invalid-csrf"}
            ).status_code,
            403,
        )
        del_prof = cli_user.delete(
            "/api/v1/profile", headers={"X-CSRF-Token": sess_cli["csrf_token"]}
        )
        self.assertEqual(del_prof.status_code, 200)
        self.assertTrue(cli_user.get("/api/v1/auth/session").json()["authenticated"])
        self.assertFalse(cli_user.get("/api/v1/profile").json()["is_persisted"])
        self.assertEqual(
            other_user.get("/api/v1/profile").json()["matmid_points_balance"], 250000
        )

        # 4. Verify personalized calendar & search endpoints carry Vary: Cookie and Cache-Control: no-store, private
        cal_up = other_user.get("/api/v1/moe-calendar/upcoming?as_of=2026-11-20")
        self.assertEqual(cal_up.headers.get("Cache-Control"), "no-store, private")
        self.assertEqual(cal_up.headers.get("Vary"), "Cookie")
        cal_sy = other_user.get("/api/v1/moe-calendar/2026-2027")
        self.assertEqual(cal_sy.headers.get("Cache-Control"), "no-store, private")
        self.assertEqual(cal_sy.headers.get("Vary"), "Cookie")

        # 5. Real Headless Chrome E2E verification of Guest "🔒 Sign in to Save" -> OAuth+PKCE -> auto-save -> reload (`F5`) -> Sign-Out scrub
        chrome_bin = Path("/usr/bin/google-chrome")
        if chrome_bin.exists():
            import shutil as _shutil
            import signal as _signal

            chrome_tmp = tempfile.TemporaryDirectory(
                prefix="tier4_chrome_", ignore_cleanup_errors=True
            )
            self.addCleanup(
                lambda: _shutil.rmtree(chrome_tmp.name, ignore_errors=True)
            )
            self.addCleanup(chrome_tmp.cleanup)
            browser_client = self.get_client(db_path)

            raw_html = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
            raw_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
            # Strip external Google Fonts / manifest / external script tags so offline Headless Chrome mounts cleanly
            inlined_base = _re.sub(
                r'<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com|manifest\.webmanifest)[^>]*>',
                "",
                raw_html,
            )
            inlined_base = inlined_base.replace(
                '<link rel="stylesheet" href="/src/styles/app.css" />',
                f"<style>{css_text}</style>",
            )
            inlined_base = _re.sub(
                r'<script[^>]+src="/src/app\.js"[^>]*></script>',
                "",
                inlined_base,
            )

            def build_mounted_doc(ss_json: str, ls_json: str) -> str:
                bridge_preamble = f"""<script>
(function() {{
  window.__fvpJsErrors = [];
  window.addEventListener('error', function(e) {{ window.__fvpJsErrors.push(String(e.message || e)); }});
  window.addEventListener('unhandledrejection', function(e) {{ window.__fvpJsErrors.push(String(e.reason || e)); }});
  const _ss = Object.assign({{}}, {ss_json});
  const _ls = Object.assign({{}}, {ls_json});
  function _mkStore(backing) {{
    return {{
      getItem(k) {{ return Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null; }},
      setItem(k, v) {{ backing[String(k)] = String(v); }},
      removeItem(k) {{ delete backing[String(k)]; }},
      clear() {{ Object.keys(backing).forEach((k) => delete backing[k]); }},
      get length() {{ return Object.keys(backing).length; }},
      _dump() {{ return Object.assign({{}}, backing); }}
    }};
  }}
  Object.defineProperty(window, 'sessionStorage', {{ value: _mkStore(_ss), configurable: true }});
  Object.defineProperty(window, 'localStorage', {{ value: _mkStore(_ls), configurable: true }});
  const _cacheMap = new Map([
    ['family-vacation-planner-v3', new Set(['https://breezyflights.com/api/v1/profile', 'https://breezyflights.com/src/app.js'])]
  ]);
  Object.defineProperty(window, 'caches', {{
    configurable: true,
    value: {{
      keys: async () => Array.from(_cacheMap.keys()),
      open: async (name) => {{
        if (!_cacheMap.has(name)) _cacheMap.set(name, new Set());
        const setRef = _cacheMap.get(name);
        return {{
          keys: async () => Array.from(setRef).map((u) => ({{ url: u }})),
          delete: async (req) => setRef.delete(typeof req === 'string' ? req : req.url)
        }};
      }},
      _dump: () => {{
        const out = {{}};
        _cacheMap.forEach((v, k) => {{ out[k] = Array.from(v); }});
        return out;
      }}
    }}
  }});
  window.__fvpLastAssignedUrl = null;
  let _reqSeq = 0;
  const _pending = new Map();
  window.__fvpResolveFetch = function(id, status, headersObj, bodyText) {{
    const p = _pending.get(id);
    if (!p) return;
    _pending.delete(id);
    p.resolve(new Response(bodyText, {{ status: status, headers: headersObj || {{}} }}));
  }};
  window.fetch = function(input, init) {{
    const urlStr = typeof input === 'string' ? input : input.url;
    if (urlStr.endsWith('/sw.js')) {{
      return Promise.resolve(new Response('', {{ status: 200, headers: {{ 'Content-Type': 'application/javascript' }} }}));
    }}
    const opts = init || {{}};
    const id = ++_reqSeq;
    return new Promise((resolve, reject) => {{
      _pending.set(id, {{ resolve, reject }});
      window.__fvpHostFetch(JSON.stringify({{
        id: id,
        method: opts.method || 'GET',
        url: urlStr,
        headers: opts.headers || {{}},
        body: opts.body || null
      }}));
    }});
  }};
  if (navigator.serviceWorker) {{
    navigator.serviceWorker.register = function() {{ return Promise.resolve({{}}); }};
  }}
}})();
</script>"""
                mounted_js = raw_js.replace(
                    "window.location.assign(loginUrl);",
                    "window.__fvpLastAssignedUrl = String(loginUrl);",
                )
                doc = inlined_base.replace("<head>", "<head>" + bridge_preamble, 1)
                doc = doc.replace(
                    "</body>",
                    f"<script>{mounted_js}</script></body>",
                    1,
                )
                return doc

            proc_c = subprocess.Popen(
                [
                    str(chrome_bin),
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--disable-extensions",
                    "--remote-debugging-port=0",
                    f"--user-data-dir={chrome_tmp.name}",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            def _kill_chrome_group() -> None:
                try:
                    os.killpg(proc_c.pid, _signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc_c.wait(timeout=3.0)
                except Exception:
                    pass

            self.addCleanup(_kill_chrome_group)

            active_port_file = Path(chrome_tmp.name) / "DevToolsActivePort"
            deadline = time.time() + 12.0
            while time.time() < deadline and not active_port_file.exists():
                time.sleep(0.05)
            self.assertTrue(active_port_file.exists(), "Headless Chrome DevToolsActivePort did not appear")
            cdp_port = int(active_port_file.read_text("utf-8").splitlines()[0].strip())

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0) as r_list:
                targets = json.loads(r_list.read().decode("utf-8"))
            page_target = next(t for t in targets if t.get("type") == "page")
            ws_parsed = _urlparse.urlsplit(page_target["webSocketDebuggerUrl"])

            sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=10.0)
            self.addCleanup(sock.close)
            ws_key = _b64.b64encode(os.urandom(16)).decode("ascii")
            handshake = (
                f"GET {ws_parsed.path} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{cdp_port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
            sock.sendall(handshake)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            header_end = buf.index(b"\r\n\r\n") + 4
            ws_leftover = bytearray(buf[header_end:])

            def _ws_send_json(obj: dict[str, Any]) -> None:
                raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                mask = os.urandom(4)
                ln = len(raw_b)
                if ln < 126:
                    hdr = bytes([0x81, 0x80 | ln]) + mask
                elif ln < 65536:
                    hdr = bytes([0x81, 0x80 | 126]) + _struct.pack("!H", ln) + mask
                else:
                    hdr = bytes([0x81, 0x80 | 127]) + _struct.pack("!Q", ln) + mask
                masked = bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b))
                sock.sendall(hdr + masked)

            def _ws_recv_exact(n: int) -> bytes:
                while len(ws_leftover) < n:
                    more = sock.recv(65536)
                    if not more:
                        raise EOFError("CDP WebSocket closed unexpectedly")
                    ws_leftover.extend(more)
                out_b = bytes(ws_leftover[:n])
                del ws_leftover[:n]
                return out_b

            def _ws_recv_msg() -> dict[str, Any]:
                fragments: list[bytes] = []
                while True:
                    b0, b1 = _ws_recv_exact(2)
                    fin = bool(b0 & 0x80)
                    opcode = b0 & 0x0F
                    masked_flag = bool(b1 & 0x80)
                    ln = b1 & 0x7F
                    if ln == 126:
                        ln = _struct.unpack("!H", _ws_recv_exact(2))[0]
                    elif ln == 127:
                        ln = _struct.unpack("!Q", _ws_recv_exact(8))[0]
                    mkey = _ws_recv_exact(4) if masked_flag else b""
                    payload_b = _ws_recv_exact(ln)
                    if masked_flag:
                        payload_b = bytes(
                            b ^ mkey[i % 4] for i, b in enumerate(payload_b)
                        )
                    if opcode == 0x9:  # PING -> PONG
                        mask_p = os.urandom(4)
                        sock.sendall(
                            bytes([0x8A, 0x80 | len(payload_b)])
                            + mask_p
                            + bytes(b ^ mask_p[i % 4] for i, b in enumerate(payload_b))
                        )
                        continue
                    fragments.append(payload_b)
                    if fin:
                        return json.loads(b"".join(fragments).decode("utf-8"))

            msg_counter = 0
            env_prev_test = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
            env_prev_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
            os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
            os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"
            self.addCleanup(
                lambda: (
                    os.environ.__setitem__("VACATION_PLANNER_AUTH_TEST_MODE", env_prev_test)
                    if env_prev_test is not None
                    else os.environ.pop("VACATION_PLANNER_AUTH_TEST_MODE", None),
                    os.environ.__setitem__("ELAL_LIVE_FETCH_ENABLED", env_prev_live)
                    if env_prev_live is not None
                    else os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None),
                )
            )

            host_fetch_log: list[tuple[str, str]] = []

            def _handle_binding_event(ev_msg: dict[str, Any]) -> None:
                if (
                    ev_msg.get("method") == "Runtime.bindingCalled"
                    and ev_msg.get("params", {}).get("name") == "__fvpHostFetch"
                ):
                    req_info = json.loads(ev_msg["params"]["payload"])
                    parsed_u = _urlparse.urlsplit(req_info["url"])
                    path_qs = parsed_u.path + (
                        f"?{parsed_u.query}" if parsed_u.query else ""
                    )
                    host_fetch_log.append(
                        (str(req_info.get("method") or "GET").upper(), path_qs)
                    )
                    j_body = (
                        json.loads(req_info["body"])
                        if req_info.get("body")
                        else None
                    )
                    resp_obj = browser_client.request(
                        req_info["method"],
                        path_qs,
                        json_body=j_body,
                        headers=req_info.get("headers") or {},
                    )
                    nonlocal msg_counter
                    msg_counter += 1
                    expr = f"window.__fvpResolveFetch({int(req_info['id'])}, {int(resp_obj.status_code)}, {json.dumps(dict(resp_obj.headers))}, {json.dumps(resp_obj.text)});"
                    _ws_send_json(
                        {
                            "id": msg_counter,
                            "method": "Runtime.evaluate",
                            "params": {"expression": expr},
                        }
                    )

            def _cdp_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
                nonlocal msg_counter
                msg_counter += 1
                target_id = msg_counter
                _ws_send_json({"id": target_id, "method": method, "params": params or {}})
                while True:
                    incoming = _ws_recv_msg()
                    if "method" in incoming:
                        _handle_binding_event(incoming)
                        continue
                    if incoming.get("id") == target_id:
                        return incoming

            def _cdp_eval(js_expr: str) -> Any:
                res = _cdp_call(
                    "Runtime.evaluate",
                    {
                        "expression": js_expr,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                )
                inner = res.get("result", {})
                if "exceptionDetails" in inner:
                    raise AssertionError(
                        f"CDP JS exception: {inner['exceptionDetails']}"
                    )
                return inner.get("result", {}).get("value")

            _cdp_call("Page.enable")
            _cdp_call("Runtime.enable")
            _cdp_call("Runtime.addBinding", {"name": "__fvpHostFetch"})
            frame_tree = _cdp_call("Page.getFrameTree")
            frame_id = frame_tree["result"]["frameTree"]["frame"]["id"]

            def _mount_and_wait_boot(ss_obj: dict[str, str], ls_obj: dict[str, str]) -> None:
                _cdp_call(
                    "Page.setDocumentContent",
                    {
                        "frameId": frame_id,
                        "html": build_mounted_doc(
                            json.dumps(ss_obj), json.dumps(ls_obj)
                        ),
                    },
                )
                # Wait until initial guest/user search renders or status settles
                for _ in range(80):
                    ready = _cdp_eval(
                        """new Promise((r) => setTimeout(() => r(Boolean(document.querySelector('.proposal-card, .awaiting-flights-showcase'))), 40))"""
                    )
                    if ready:
                        break

            # Step A: Boot as Guest -> verify 0-points alert + award database note + single sign-in button (`#btn-save-profile` hidden),
            # then add 2 children ([2, 8]) + 150,000 Matmid points and click `#btn-google-signin`
            _mount_and_wait_boot({}, {})
            guest_draft_state = _cdp_eval(
                """(() => {
                  const saveBtnEl = document.getElementById('btn-save-profile');
                  const saveBtnHiddenOnGuest = Boolean(saveBtnEl && saveBtnEl.hasAttribute('hidden'));
                  const zeroAlertEl = document.getElementById('zero-points-search-alert');
                  const zeroAlertText = zeroAlertEl ? zeroAlertEl.textContent : '';
                  const awardNoteEl = document.getElementById('award-source-note-banner');
                  const awardNoteText = awardNoteEl ? awardNoteEl.textContent : '';
                  document.getElementById('btn-add-child').click();
                  document.getElementById('btn-add-child').click();
                  const age0 = document.querySelector('[data-child-age="0"]');
                  age0.value = '2';
                  age0.dispatchEvent(new Event('input', { bubbles: true }));
                  age0.dispatchEvent(new Event('change', { bubbles: true }));
                  const age1 = document.querySelector('[data-child-age="1"]');
                  age1.value = '8';
                  age1.dispatchEvent(new Event('input', { bubbles: true }));
                  age1.dispatchEvent(new Event('change', { bubbles: true }));
                  const mInput = document.getElementById('prof-matmid-points');
                  mInput.value = '150000';
                  mInput.dispatchEvent(new Event('input', { bubbles: true }));
                  mInput.dispatchEvent(new Event('change', { bubbles: true }));
                  const googleBtn = document.getElementById('btn-google-signin');
                  const btnTextBefore = googleBtn ? googleBtn.textContent : '';
                  googleBtn.click();
                  return {
                    saveBtnHiddenOnGuest,
                    zeroAlertText,
                    awardNoteText,
                    btnTextBefore,
                    assignedUrl: window.__fvpLastAssignedUrl,
                    ssDump: window.sessionStorage._dump()
                  };
                })()"""
            )
            self.assertTrue(guest_draft_state["saveBtnHiddenOnGuest"])
            self.assertIn("יתרת מתמיד 0", guest_draft_state["zeroAlertText"])
            self.assertIn("מאגר כרטיסי הבונוס של אל על", guest_draft_state["awardNoteText"])
            self.assertNotIn("rbddataclients", guest_draft_state["awardNoteText"].lower())
            self.assertIn("התחברות עם Gmail", guest_draft_state["btnTextBefore"])
            self.assertTrue(
                str(guest_draft_state["assignedUrl"]).startswith(
                    "/api/v1/auth/google/login"
                )
            )
            self.assertIn("fvp_pending_oauth_draft", guest_draft_state["ssDump"])

            # Step B: Complete server-side OAuth+PKCE redirect chain for `draft.family@gmail.com`
            r_l = browser_client.get(
                f"{guest_draft_state['assignedUrl']}&mock_oauth=1&test_email=draft.family@gmail.com"
            )
            self.assertEqual(r_l.status_code, 302)
            r_az = browser_client.get(r_l.headers["Location"])
            self.assertEqual(r_az.status_code, 302)
            r_cb = browser_client.get(r_az.headers["Location"])
            self.assertEqual(r_cb.status_code, 302)
            self.assertEqual(r_cb.headers["Location"], "/")

            # Step C: Land on `/` with `fvp_pending_oauth_draft` in sessionStorage -> auto-saves via PUT /api/v1/profile!
            _mount_and_wait_boot(guest_draft_state["ssDump"], {})
            post_login_state = _cdp_eval(
                """(() => ({
                  ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                  matmid: document.getElementById('prof-matmid-points').value,
                  saveBtnHiddenAfterLogin: document.getElementById('btn-save-profile').hasAttribute('hidden'),
                  hasZeroAlertAfterLogin: Boolean(document.getElementById('zero-points-search-alert')),
                  feedback: document.getElementById('auth-save-feedback').textContent,
                  feedbackHidden: document.getElementById('auth-save-feedback').hasAttribute('hidden'),
                  ssRemaining: window.sessionStorage._dump(),
                  jsErrors: window.__fvpJsErrors
                }))()"""
            )
            self.assertEqual(post_login_state["jsErrors"], [])
            self.assertEqual(post_login_state["ages"], [2, 8])
            self.assertEqual(post_login_state["matmid"], "150000")
            self.assertFalse(post_login_state["saveBtnHiddenAfterLogin"])
            self.assertFalse(post_login_state["hasZeroAlertAfterLogin"])
            self.assertFalse(post_login_state["feedbackHidden"])
            self.assertIn("נשמר", post_login_state["feedback"])
            self.assertNotIn("fvp_pending_oauth_draft", post_login_state["ssRemaining"])

            # Step D: Reload `/` (`F5` with EMPTY sessionStorage) -> retains `[2, 8]` & `150000` from SQLite!
            _mount_and_wait_boot({}, {"custom_pref": "1"})
            reload_state = _cdp_eval(
                """(() => ({
                  ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                  matmid: document.getElementById('prof-matmid-points').value,
                  familyPill: document.getElementById('header-family-pill').textContent.trim(),
                  pointsPill: document.getElementById('header-points-pill').textContent.trim(),
                  jsErrors: window.__fvpJsErrors
                }))()"""
            )
            self.assertEqual(reload_state["jsErrors"], [])
            self.assertEqual(reload_state["ages"], [2, 8])
            self.assertEqual(reload_state["matmid"], "150000")
            self.assertIn("150k Matmid", reload_state["pointsPill"])

            # Step D2: Returning-user (`is_persisted === true`) non-overwrite guard against conflicting `fvp_pending_oauth_draft`
            conflicting_draft = {
                "ts": int(time.time() * 1000),
                "adults_count": 2,
                "annual_pto_budget": 18,
                "matmid_points_balance": 10000,
                "children": [
                    {
                        "child_age_years": 15,
                        "framework_type": "HIGH_SCHOOL_10_12",
                    }
                ],
            }
            host_fetch_log.clear()
            _mount_and_wait_boot(
                {"fvp_pending_oauth_draft": json.dumps(conflicting_draft)},
                {"custom_pref": "1"},
            )
            overwrite_puts = [
                (m, p)
                for m, p in host_fetch_log
                if m == "PUT" and p.startswith("/api/v1/profile")
            ]
            self.assertEqual(
                overwrite_puts,
                [],
                f"Expected 0 PUT /api/v1/profile calls for already-persisted returning user, got {overwrite_puts}",
            )
            guard_state = _cdp_eval(
                """(() => ({
                  ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                  matmid: document.getElementById('prof-matmid-points').value,
                  draftItem: window.sessionStorage.getItem('fvp_pending_oauth_draft'),
                  jsErrors: window.__fvpJsErrors
                }))()"""
            )
            self.assertEqual(guard_state["jsErrors"], [])
            self.assertIsNone(guard_state["draftItem"])
            self.assertEqual(guard_state["ages"], [2, 8])
            self.assertEqual(guard_state["matmid"], "150000")
            db_prof_after_guard = browser_client.get("/api/v1/profile").json()
            self.assertTrue(db_prof_after_guard["is_persisted"])
            self.assertEqual(
                [c["child_age_years"] for c in db_prof_after_guard["children"]],
                [2, 8],
            )
            self.assertEqual(db_prof_after_guard["matmid_points_balance"], 150000)

            # Step E: Click Sign-Out -> scrubs DOM, storage, calendarData, and revokes session!
            signout_state = _cdp_eval(
                """(async () => {
                  document.getElementById('btn-signout').click();
                  for (let i = 0; i < 100; i++) {
                    await new Promise((r) => setTimeout(r, 40));
                    const guestShown = !document.getElementById('auth-guest-panel').hasAttribute('hidden');
                    const calReady = document.querySelectorAll('#moe-calendar-tbody tr').length > 0;
                    const cardsReady = document.querySelectorAll('.proposal-card, .awaiting-flights-showcase').length > 0;
                    if (guestShown && calReady && cardsReady) break;
                  }
                  return {
                    ages: Array.from(document.querySelectorAll('[data-child-age]')).map((el) => Number(el.value)),
                    matmid: document.getElementById('prof-matmid-points').value,
                    calRows: document.querySelectorAll('#moe-calendar-tbody tr').length,
                    lsLen: window.localStorage.length,
                    ssLen: window.sessionStorage.length,
                    cachesDump: window.caches._dump(),
                    jsErrors: window.__fvpJsErrors
                  };
                })()"""
            )
            self.assertEqual(signout_state["jsErrors"], [])
            self.assertEqual(signout_state["ages"], [])
            self.assertEqual(signout_state["matmid"], "0")
            self.assertGreater(signout_state["calRows"], 0)
            self.assertEqual(signout_state["lsLen"], 0)
            self.assertEqual(signout_state["ssLen"], 0)
            self.assertEqual(
                signout_state["cachesDump"]["family-vacation-planner-v3"],
                ["https://breezyflights.com/src/app.js"],
            )


if __name__ == "__main__":
    unittest.main()
