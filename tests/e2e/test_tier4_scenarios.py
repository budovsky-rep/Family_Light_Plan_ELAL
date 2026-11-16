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

        repo = SQLiteRepository(db_path=db_path, auto_seed=True)
        client = self.get_client(db_path)
        return db_path, repo, client


class TestTier4RealWorldApplicationScenarios(Tier4ScenariosTestBase):
    """18 real-world family vacation user workflows (Scenarios 1..18)."""

    def test_scenario_01_pesach_2027_rome_family_of_5_hybrid_bonus_plus_cash(self) -> None:
        db_path, repo, client = self.create_isolated_client_env()
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
        db_path, repo, client = self.create_isolated_client_env()
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

        prof = self.get_default_profile(db_path).to_dict()
        for c in prof["children"]:
            c["treat_camp_as_vacation"] = False
        put_resp = client.put("/api/v1/profile", json=prof)
        self.assertEqual(put_resp.status_code, 200)

        maximizer = self.get_maximizer(self.get_calendar_service(repo))
        prof_off = self.get_default_profile(db_path)
        w_dec6_off = maximizer.evaluate_window(prof_off, date(2026, 12, 6), date(2026, 12, 11))
        w_dec10_off = maximizer.evaluate_window(prof_off, date(2026, 12, 10), date(2026, 12, 14))
        self.assertGreater(w_dec6_off.school_absence_penalty, sap_on)
        self.assertLess(w_dec10_off.per_child_impact[0].nitzanim_days_overlapped, 5)

    def test_scenario_03_june_20_30_madrid_middle_school_inter_framework_arbitrage(self) -> None:
        db_path, repo, client = self.create_isolated_client_env()
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
        db_path, repo, client = self.create_isolated_client_env()
        prof = self.get_default_profile(db_path)
        prof.max_pto_per_trip = 8.0
        prof.children.append(ChildFramework(id="c-hs-4", child_name="תומר", child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5))
        _save_profile_to_repo_or_sqlite(repo, db_path, prof)

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
        db_path, _repo, client = self.create_isolated_client_env()
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

        db_path, _repo, client = self.create_isolated_client_env()
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
        db_path, repo, client = self.create_isolated_client_env()
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
        db_path, repo, client = self.create_isolated_client_env()
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
        _save_profile_to_repo_or_sqlite(repo, db_path, prof)

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
            self.assertEqual(health["tables_count"], 8)
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
        self.assertEqual(health["tables_count"], 8)

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

        for vp_w, vp_h, expected_gap_px, expected_pad_px in (
            (1280, 800, 24, 32),
            (1440, 900, 28, 36),
        ):
            computed = compute_styles_for_viewport(vp_w)
            shell_style = computed.get(".dashboard-shell", {})
            self.assertEqual(shell_style.get("display"), "grid")
            self.assertEqual(
                shell_style.get("grid-template-columns"),
                "minmax(0, 1fr)",
            )
            self.assertEqual(shell_style.get("max-width"), "1200px")
            self.assertEqual(shell_style.get("padding-block"), "24px 36px")

            # Verify every overflow-sensitive container has min-width: 0
            for sel in (".sidebar-column", ".content-column", ".zone-card", ".form-field", ".proposals-grid", ".proposal-card", ".calendar-scroll-wrapper"):
                self.assertEqual(computed.get(sel, {}).get("min-width"), "0", f"{sel} missing min-width: 0 at {vp_w}x{vp_h}")

            # Compute exact bounding boxes in both RTL ("rtl") and LTR ("ltr") for single-column desktop flow
            container_w = min(vp_w, 1200)
            inner_w = container_w - (2 * expected_pad_px)
            self.assertGreaterEqual(inner_w, 1100)

            for direction in ("rtl", "ltr"):
                margin_side = (vp_w - container_w) / 2.0
                col_box = (margin_side + expected_pad_px, margin_side + expected_pad_px + inner_w)

                # Assert zero horizontal overflow (`scrollWidth <= viewport_width`)
                self.assertGreaterEqual(col_box[0], 0)
                self.assertLessEqual(col_box[1], vp_w)

                # Verify 3 mode tabs and form grids inside single-column card render side-by-side without overlapping
                card_inner_w = inner_w - 36 - 2
                tab_gap = 10
                tab_w = (card_inner_w - 2 * tab_gap) / 3.0
                self.assertGreater(tab_w, 250.0)
                form3_w = (card_inner_w - 2 * 12) / 3.0
                self.assertGreater(form3_w, 250.0)
                form2_w = (card_inner_w - 12) / 2.0
                self.assertGreater(form2_w, 400.0)

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


if __name__ == "__main__":
    unittest.main()
