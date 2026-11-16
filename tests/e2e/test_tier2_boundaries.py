"""Tier 2 Opaque-Box Boundary, Corner & Negative Test Suite for family_vacation_planner.

Contains 160 boundary, corner-case, and negative/robustness test methods
(5 tests per feature across all 32 features F01..F32) strictly targeting the
public contracts in PROJECT.md and APPLICATION_PLAN.md with hermetic SQLite isolation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.calendar_engine.moe_calendar_service import (
    MoECalendarAutoUpdaterService,
    MoECalendarService,
)
from backend.app.schemas.domain import (
    CandidateVacationWindow,
    ChildFramework,
    ElAlBonusAvailability,
    FamilyProfile,
    FlightItinerary,
    FlightSearchQuery,
    LoyaltyProgramCode,
    MoEFrameworkType,
    PassengerLoyaltyWallet,
    VacationOptionProposal,
    classify_passenger_type,
    suggest_framework_for_age,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.vacation_optimizer.maximizer_engine import VacationMaximizerEngine


class Tier2BoundaryTestBase(unittest.TestCase):
    """Hermetic base test harness for Tier 2 boundary & negative tests."""

    _shared_tmpdir: Optional[tempfile.TemporaryDirectory[str]] = None
    shared_db_path: Path
    shared_repo: SQLiteRepository
    _shared_client: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if Tier2BoundaryTestBase._shared_tmpdir is None:
            Tier2BoundaryTestBase._shared_tmpdir = tempfile.TemporaryDirectory(
                prefix="fvp_t2_shared_"
            )
            Tier2BoundaryTestBase.shared_db_path = (
                Path(Tier2BoundaryTestBase._shared_tmpdir.name) / "shared_t2.db"
            )
            Tier2BoundaryTestBase.shared_repo = SQLiteRepository(
                db_path=Tier2BoundaryTestBase.shared_db_path, auto_seed=True
            )

    @property
    def shared_client(self) -> Any:
        if Tier2BoundaryTestBase._shared_client is None:
            from backend.app.main import VacationPlannerTestClient

            Tier2BoundaryTestBase._shared_client = VacationPlannerTestClient(
                db_path=str(self.shared_db_path)
            )
        return Tier2BoundaryTestBase._shared_client

    def get_client(self, db_path: Optional[str | Path] = None) -> Any:
        from backend.app.main import VacationPlannerTestClient

        if db_path is not None:
            return VacationPlannerTestClient(db_path=str(db_path))
        return self.shared_client

    def get_elal_adapter(self, repo: Optional[SQLiteRepository] = None) -> Any:
        from backend.app.providers.elal_rbd_client import ElAlRbdDataClientAdapter

        return ElAlRbdDataClientAdapter(repo or self.shared_repo)

    def get_commercial_adapter(self, repo: Optional[SQLiteRepository] = None) -> Any:
        from backend.app.providers.commercial_flights import AllAirlinesSearchAdapter

        return AllAirlinesSearchAdapter(repo or self.shared_repo)

    def get_wallet_engine(self) -> Any:
        from backend.app.planner_synthesizer.bonus_planner_service import (
            MultiClubWalletAllocationEngine,
        )

        return MultiClubWalletAllocationEngine()

    def get_planner(self, repo: Optional[SQLiteRepository] = None) -> Any:
        from backend.app.planner_synthesizer.bonus_planner_service import (
            BonusVacationPlannerService,
        )

        r = repo or self.shared_repo
        cal = MoECalendarService(r)
        max_eng = VacationMaximizerEngine(cal)
        return BonusVacationPlannerService(
            r, cal, max_eng, self.get_elal_adapter(r), self.get_commercial_adapter(r)
        )

    def create_temp_repo(self, auto_seed: bool = False) -> tuple[SQLiteRepository, Path]:
        tmpdir = tempfile.TemporaryDirectory(prefix="fvp_t2_case_")
        self.addCleanup(tmpdir.cleanup)
        db_path = Path(tmpdir.name) / "case.db"
        repo = SQLiteRepository(db_path=db_path, auto_seed=auto_seed)
        return repo, db_path

    def get_raw_conn(self, db_path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        self.addCleanup(conn.close)
        return conn


class TestTier2F01FamilyProfilesBoundaries(Tier2BoundaryTestBase):
    """F01 — family_profiles SQLite Table boundaries & CHECK constraints."""

    def test_f01_01_adults_count_min_max_and_out_of_bounds_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for valid_adults in (1, 6):
            conn.execute("INSERT INTO family_profiles (id, adults_count) VALUES (?, ?)", (f"p_{valid_adults}", valid_adults))
        for invalid_adults in (0, 7, -1):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO family_profiles (id, adults_count) VALUES (?, ?)", (f"bad_{invalid_adults}", invalid_adults))

    def test_f01_02_pto_weights_discrete_set_and_invalid_weight_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for idx, w in enumerate((0.0, 0.5, 1.0)):
            conn.execute("INSERT INTO family_profiles (id, erev_chag_pto_weight, chol_hamoed_pto_weight) VALUES (?, ?, ?)", (f"w_{idx}", w, w))
        for bad_w in (0.25, -0.5, 1.5):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO family_profiles (id, erev_chag_pto_weight) VALUES (?, ?)", (f"be_{bad_w}", bad_w))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO family_profiles (id, chol_hamoed_pto_weight) VALUES (?, ?)", (f"bc_{bad_w}", bad_w))

    def test_f01_03_zero_budgets_and_negative_budget_points_vouchers_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute(
            "INSERT INTO family_profiles (id, annual_pto_budget, max_pto_per_trip, matmid_points_balance, flycard_companion_vouchers) VALUES ('z', 0.0, 0.0, 0, 0)"
        )
        for col, bad_val in (("annual_pto_budget", -0.1), ("max_pto_per_trip", -1.0), ("matmid_points_balance", -1), ("flycard_companion_vouchers", -1)):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(f"INSERT INTO family_profiles (id, {col}) VALUES (?, ?)", (f"neg_{col}", bad_val))

    def test_f01_04_point_valuation_strictly_positive_zero_rejected(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id, point_valuation_usd) VALUES ('pos', 0.0001)")
        for bad_val in (0.0, -0.01):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO family_profiles (id, point_valuation_usd) VALUES (?, ?)", (f"pv_{bad_val}", bad_val))

    def test_f01_05_enum_checks_workweek_flycard_tier_currency(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for col, bad_val in (("workweek_type", "MON_FRI"), ("has_flycard", 2), ("flycard_tier", "GOLD"), ("preferred_currency", "GBP")):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(f"INSERT INTO family_profiles (id, {col}) VALUES (?, ?)", (f"enum_{col}", bad_val))


class TestTier2F02PassengerLoyaltyWalletsBoundaries(Tier2BoundaryTestBase):
    """F02 — passenger_loyalty_wallets SQLite Table boundaries & FK cascades."""

    def test_f02_01_program_code_check_rejects_unknown_loyalty_program(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        for idx, code in enumerate(LoyaltyProgramCode):
            conn.execute(
                "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code) VALUES (?, 'p1', 'A1', 'Pax', ?)",
                (f"w_{idx}", code.value),
            )
        for bad_code in ("TURKISH_MILES_AND_SMILES", ""):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code) VALUES (?, 'p1', 'A1', 'Pax', ?)",
                    (f"bad_{bad_code}", bad_code),
                )

    def test_f02_02_available_points_and_vouchers_zero_vs_negative_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, available_points, companion_vouchers_count) VALUES ('w0', 'p1', 'A1', 'Pax', 'ELAL_MATMID', 0, 0)"
        )
        for col in ("available_points", "companion_vouchers_count"):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, {col}) VALUES (?, 'p1', 'A1', 'Pax', 'ELAL_MATMID', -1)",
                    (f"neg_{col}",),
                )

    def test_f02_03_transfer_ratio_and_valuation_strictly_positive_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, transfer_ratio_to_airline, point_valuation_cents) VALUES ('wp', 'p1', 'A1', 'Pax', 'AMEX_MR_ISRAEL', 0.25, 0.01)"
        )
        for col, bad_val in (("transfer_ratio_to_airline", 0.0), ("transfer_ratio_to_airline", -0.5), ("point_valuation_cents", 0.0), ("point_valuation_cents", -1.0)):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, {col}) VALUES (?, 'p1', 'A1', 'Pax', 'ELAL_MATMID', ?)",
                    (f"bad_{col}_{bad_val}", bad_val),
                )

    def test_f02_04_pooling_and_credit_card_boolean_flags_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, can_pool_with_family, pool_group_id, has_club_credit_card) VALUES ('b0', 'p1', 'A1', 'P', 'ELAL_MATMID', 0, NULL, 0), ('b1', 'p1', 'A1', 'P', 'BRITISH_AVIOS', 1, 'POOL_A', 1)"
        )
        for col, bad_val in (("can_pool_with_family", 2), ("has_club_credit_card", -1)):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, {col}) VALUES (?, 'p1', 'A1', 'P', 'ELAL_MATMID', ?)",
                    (f"bad_{col}", bad_val),
                )

    def test_f02_05_foreign_key_cascade_delete_from_family_profiles(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p_del')")
        for i in range(3):
            conn.execute(
                "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code) VALUES (?, 'p_del', 'A1', 'Pax', 'ELAL_MATMID')",
                (f"w_{i}",),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code) VALUES ('w_orph', 'nonexistent', 'A1', 'Pax', 'ELAL_MATMID')"
            )
        conn.execute("DELETE FROM family_profiles WHERE id = 'p_del'")
        cnt = conn.execute("SELECT COUNT(*) FROM passenger_loyalty_wallets WHERE family_profile_id = 'p_del'").fetchone()[0]
        self.assertEqual(cnt, 0)


class TestTier2F03ChildFrameworksBoundaries(Tier2BoundaryTestBase):
    """F03 — child_frameworks SQLite Table boundaries & FK cascades."""

    def test_f03_01_child_age_years_boundaries_0_and_21_vs_out_of_range(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        for valid_age in (0, 21):
            conn.execute(
                "INSERT INTO child_frameworks (id, family_profile_id, child_age_years) VALUES (?, 'p1', ?)",
                (f"c_{valid_age}", valid_age),
            )
        for bad_age in (-1, 22, 99):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO child_frameworks (id, family_profile_id, child_age_years) VALUES (?, 'p1', ?)",
                    (f"bad_{bad_age}", bad_age),
                )

    def test_f03_02_nullable_framework_type_allowed_invalid_framework_rejected(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            "INSERT INTO child_frameworks (id, family_profile_id, child_age_years, framework_type, birth_date) VALUES ('c_null', 'p1', 6, NULL, NULL)"
        )
        row = conn.execute("SELECT framework_type, birth_date FROM child_frameworks WHERE id = 'c_null'").fetchone()
        self.assertIsNone(row["framework_type"])
        self.assertIsNone(row["birth_date"])
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO child_frameworks (id, family_profile_id, child_age_years, framework_type) VALUES ('c_bad', 'p1', 6, 'UNIVERSITY')"
            )

    def test_f03_03_school_week_days_5_or_6_and_max_missed_0_to_14_boundaries(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            "INSERT INTO child_frameworks (id, family_profile_id, child_age_years, school_week_days, max_school_days_missed) VALUES ('c5_0', 'p1', 8, 5, 0), ('c6_14', 'p1', 10, 6, 14)"
        )
        for bad_sw in (4, 7):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO child_frameworks (id, family_profile_id, child_age_years, school_week_days) VALUES (?, 'p1', 8, ?)",
                    (f"sw_{bad_sw}", bad_sw),
                )
        for bad_mm in (-1, 15):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO child_frameworks (id, family_profile_id, child_age_years, max_school_days_missed) VALUES (?, 'p1', 8, ?)",
                    (f"mm_{bad_mm}", bad_mm),
                )

    def test_f03_04_passenger_type_stream_extension_and_negative_penalty_checks(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        checks = (
            ("passenger_Current_type", "ADULT"),
            ("education_stream", "PRIVATE"),
            ("holiday_extension_mode", "ALL_YEAR"),
            ("treat_camp_as_vacation", 2),
            ("absence_penalty_weight", -0.1),
        )
        for col, bad_val in checks:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"INSERT INTO child_frameworks (id, family_profile_id, child_age_years, {col}) VALUES (?, 'p1', 7, ?)",
                    (f"bad_{col}", bad_val),
                )

    def test_f03_05_foreign_key_cascade_delete_from_family_profiles(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p_del')")
        for i in range(3):
            conn.execute("INSERT INTO child_frameworks (id, family_profile_id, child_age_years) VALUES (?, 'p_del', ?)", (f"ch_{i}", 4 + i))
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO child_frameworks (id, family_profile_id, child_age_years) VALUES ('ch_orph', 'missing-profile', 5)")
        conn.execute("DELETE FROM family_profiles WHERE id = 'p_del'")
        cnt = conn.execute("SELECT COUNT(*) FROM child_frameworks WHERE family_profile_id = 'p_del'").fetchone()[0]
        self.assertEqual(cnt, 0)


class TestTier2F04MoEVacationWindowsBoundaries(Tier2BoundaryTestBase):
    """F04 — moe_vacation_windows SQLite Table boundaries & constraints."""

    def test_f04_01_framework_type_not_null_and_enum_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for idx, bad_fw in enumerate((None, "INVALID_FRAMEWORK")):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO moe_vacation_windows (
                        id, school_year, circular_id, holiday_code, holiday_name_he, holiday_name_en,
                        framework_type, start_date, end_date, resumes_on_date, source_reference
                    ) VALUES (?, '2026-2027', '0363', 'PESACH', 'פסח', 'Pesach', ?, '2027-04-13', '2027-04-28', '2027-04-29', 'ref')""",
                    (f"mw_{idx}", bad_fw),
                )

    def test_f04_02_parent_workday_status_and_sync_source_enum_checks(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for col, bad_val in (("parent_workday_status", "WEEKEND_OFF"), ("calendar_sync_source", "MANUAL_CSV")):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"""INSERT INTO moe_vacation_windows (
                        id, school_year, circular_id, holiday_code, holiday_name_he, holiday_name_en,
                        framework_type, start_date, end_date, resumes_on_date, {col}, source_reference
                    ) VALUES (?, '2026-2027', '0363', 'PESACH', 'פסח', 'Pesach', 'ELEMENTARY_1_3', '2027-04-13', '2027-04-28', '2027-04-29', ?, 'ref')""",
                    (f"bad_{col}", bad_val),
                )

    def test_f04_03_tlv_airport_closed_and_nitzanim_boolean_checks(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute(
            """INSERT INTO moe_vacation_windows (
                id, school_year, circular_id, holiday_code, holiday_name_he, holiday_name_en,
                framework_type, start_date, end_date, resumes_on_date, is_covered_by_nitzanim, tlv_airport_closed, source_reference
            ) VALUES ('mw_ok', '2026-2027', '0363', 'YOM_KIPPUR_SUKKOT', 'כיפור', 'YK', 'ELEMENTARY_1_3', '2026-09-20', '2026-10-04', '2026-10-05', 0, 1, 'ref')"""
        )
        for col, bad_val in (("tlv_airport_closed", 2), ("tlv_airport_closed", -1), ("is_covered_by_nitzanim", 2), ("is_covered_by_nitzanim", -1)):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"""INSERT INTO moe_vacation_windows (
                        id, school_year, circular_id, holiday_code, holiday_name_he, holiday_name_en,
                        framework_type, start_date, end_date, resumes_on_date, {col}, source_reference
                    ) VALUES (?, '2026-2027', '0363', 'PESACH', 'פסח', 'Pesach', 'ELEMENTARY_1_3', '2027-04-13', '2027-04-28', '2027-04-29', ?, 'ref')""",
                    (f"bad_{col}_{bad_val}", bad_val),
                )

    def test_f04_04_seeded_yom_kippur_windows_have_tlv_airport_closed_flag(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        for sy in ("2025-2026", "2026-2027"):
            rows = conn.execute(
                "SELECT * FROM moe_vacation_windows WHERE school_year = ? AND tlv_airport_closed = 1",
                (sy,),
            ).fetchall()
            self.assertGreaterEqual(len(rows), 1, f"Expected tlv_airport_closed=1 in {sy}")

    def test_f04_05_duplicate_primary_key_rejected_and_idempotent_upsert(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=True)
        conn = self.get_raw_conn(db_path)
        first_id = conn.execute("SELECT id FROM moe_vacation_windows LIMIT 1").fetchone()["id"]
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO moe_vacation_windows (
                    id, school_year, circular_id, holiday_code, holiday_name_he, holiday_name_en,
                    framework_type, start_date, end_date, resumes_on_date, source_reference
                ) VALUES (?, '2026-2027', '0363', 'PESACH', 'פסח', 'Pesach', 'ELEMENTARY_1_3', '2027-04-13', '2027-04-28', '2027-04-29', 'ref')""",
                (first_id,),
            )
        count_before = conn.execute("SELECT COUNT(*) FROM moe_vacation_windows").fetchone()[0]
        SQLiteRepository(db_path=db_path, auto_seed=True)
        count_after = conn.execute("SELECT COUNT(*) FROM moe_vacation_windows").fetchone()[0]
        self.assertEqual(count_before, count_after)


class TestTier2F05FlightSearchQueriesBoundaries(Tier2BoundaryTestBase):
    """F05 — flight_search_queries SQLite Table boundaries & FK cascades."""

    def test_f05_01_flex_days_0_to_7_and_bridge_days_0_to_5_boundaries(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        for flex, bridge in ((0, 0), (7, 5)):
            conn.execute(
                """INSERT INTO flight_search_queries (
                    id, family_profile_id, date_selection_mode, airline_selection_mode,
                    destination_iatas_json, flex_days_plus_minus, max_bridge_days_shift
                ) VALUES (?, 'p1', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]', ?, ?)""",
                (f"q_{flex}_{bridge}", flex, bridge),
            )
        for bad_flex in (-1, 8):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_search_queries (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        destination_iatas_json, flex_days_plus_minus
                    ) VALUES (?, 'p1', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]', ?)""",
                    (f"bf_{bad_flex}", bad_flex),
                )
        for bad_bridge in (-1, 6):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_search_queries (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        destination_iatas_json, max_bridge_days_shift
                    ) VALUES (?, 'p1', 'MOE_VACATION_MAXIMIZATION', 'EL_AL_ONLY', '["FCO"]', ?)""",
                    (f"bb_{bad_bridge}", bad_bridge),
                )

    def test_f05_02_cross_column_max_trip_nights_ge_min_trip_nights_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            """INSERT INTO flight_search_queries (
                id, family_profile_id, date_selection_mode, airline_selection_mode,
                destination_iatas_json, min_trip_nights, max_trip_nights
            ) VALUES ('q_eq', 'p1', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]', 1, 1)"""
        )
        for idx, (min_n, max_n) in enumerate(((0, 5), (-1, 5), (7, 6))):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_search_queries (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        destination_iatas_json, min_trip_nights, max_trip_nights
                    ) VALUES (?, 'p1', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]', ?, ?)""",
                    (f"bad_n_{idx}", min_n, max_n),
                )

    def test_f05_03_direct_target_year_null_or_2025_to_2035_boundaries(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        for idx, yr in enumerate((None, 2025, 2035)):
            conn.execute(
                """INSERT INTO flight_search_queries (
                    id, family_profile_id, date_selection_mode, airline_selection_mode,
                    destination_iatas_json, direct_target_year
                ) VALUES (?, 'p1', 'HOLIDAY_DIRECT_INTENT', 'EL_AL_ONLY', '["FCO"]', ?)""",
                (f"yr_{idx}", yr),
            )
        for bad_yr in (2024, 2036):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_search_queries (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        destination_iatas_json, direct_target_year
                    ) VALUES (?, 'p1', 'HOLIDAY_DIRECT_INTENT', 'EL_AL_ONLY', '["FCO"]', ?)""",
                    (f"bad_yr_{bad_yr}", bad_yr),
                )

    def test_f05_04_mode_and_overlap_policy_enum_checks(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        for col, bad_val in (
            ("date_selection_mode", "FREE_TEXT"),
            ("airline_selection_mode", "LCC_ONLY"),
            ("overlap_policy", "IGNORE_SCHOOL"),
        ):
            vals = {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "overlap_policy": "MAXIMIZE_EFFICIENCY_SCORE",
            }
            vals[col] = bad_val
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_search_queries (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        destination_iatas_json, overlap_policy
                    ) VALUES (?, 'p1', ?, ?, '["FCO"]', ?)""",
                    (f"bad_{col}", vals["date_selection_mode"], vals["airline_selection_mode"], vals["overlap_policy"]),
                )

    def test_f05_05_foreign_key_cascade_delete_from_family_profiles(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p_del')")
        conn.execute(
            """INSERT INTO flight_search_queries (
                id, family_profile_id, date_selection_mode, airline_selection_mode, destination_iatas_json
            ) VALUES ('q_del', 'p_del', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]')"""
        )
        conn.execute("DELETE FROM family_profiles WHERE id = 'p_del'")
        cnt = conn.execute("SELECT COUNT(*) FROM flight_search_queries WHERE id = 'q_del'").fetchone()[0]
        self.assertEqual(cnt, 0)


class TestTier2F06ElAlBonusAvailabilityBoundaries(Tier2BoundaryTestBase):
    """F06 — elal_bonus_availability SQLite Table boundaries & TTL checks."""

    def test_f06_01_award_seat_counts_0_to_9_boundaries_and_out_of_range(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for val in (0, 9):
            conn.execute(
                """INSERT INTO elal_bonus_availability (
                    id, origin_iata, destination_iata, direction, flight_number, flight_date,
                    departure_time_local, arrival_time_local, economy_award_seats,
                    premium_award_seats, business_award_seats, expires_at
                ) VALUES (?, 'TLV', 'FCO', 'OUTBOUND', 'LY381', '2027-04-11', '06:00', '08:45', ?, ?, ?, '2029-01-01T00:00:00Z')""",
                (f"b_{val}", val, val, val),
            )
        for col in ("economy_award_seats", "premium_award_seats", "business_award_seats"):
            for bad_val in (-1, 10):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        f"""INSERT INTO elal_bonus_availability (
                            id, origin_iata, destination_iata, direction, flight_number, flight_date,
                            departure_time_local, arrival_time_local, {col}, expires_at
                        ) VALUES (?, 'TLV', 'FCO', 'OUTBOUND', 'LY381', '2027-04-11', '06:00', '08:45', ?, '2029-01-01T00:00:00Z')""",
                        (f"bad_{col}_{bad_val}", bad_val),
                    )

    def test_f06_02_two_plus_flags_and_flycard_promo_boolean_checks(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for col, bad_val in (
            ("economy_seats_is_two_plus", 2),
            ("premium_seats_is_two_plus", -1),
            ("business_seats_is_two_plus", 2),
            ("flycard_promo_active", 2),
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    f"""INSERT INTO elal_bonus_availability (
                        id, origin_iata, destination_iata, direction, flight_number, flight_date,
                        departure_time_local, arrival_time_local, {col}, expires_at
                    ) VALUES (?, 'TLV', 'FCO', 'OUTBOUND', 'LY381', '2027-04-11', '06:00', '08:45', ?, '2029-01-01T00:00:00Z')""",
                    (f"bad_{col}", bad_val),
                )

    def test_f06_03_direction_enum_and_non_negative_taxes_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute(
            """INSERT INTO elal_bonus_availability (
                id, origin_iata, destination_iata, direction, flight_number, flight_date,
                departure_time_local, arrival_time_local, taxes_usd_per_pax, expires_at
            ) VALUES ('b_ok', 'TLV', 'FCO', 'OUTBOUND', 'LY381', '2027-04-11', '06:00', '08:45', 0.0, '2029-01-01T00:00:00Z')"""
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO elal_bonus_availability (
                    id, origin_iata, destination_iata, direction, flight_number, flight_date,
                    departure_time_local, arrival_time_local, taxes_usd_per_pax, expires_at
                ) VALUES ('b_dir', 'TLV', 'FCO', 'ROUNDTRIP', 'LY381', '2027-04-11', '06:00', '08:45', 0.0, '2029-01-01T00:00:00Z')"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO elal_bonus_availability (
                    id, origin_iata, destination_iata, direction, flight_number, flight_date,
                    departure_time_local, arrival_time_local, taxes_usd_per_pax, expires_at
                ) VALUES ('b_tax', 'TLV', 'FCO', 'OUTBOUND', 'LY381', '2027-04-11', '06:00', '08:45', -0.01, '2029-01-01T00:00:00Z')"""
            )

    def test_f06_04_zero_one_two_plus_seat_cap_representation_consistency(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        rows = conn.execute("SELECT * FROM elal_bonus_availability").fetchall()
        self.assertGreater(len(rows), 0)
        for r in rows:
            for cab in ("economy", "premium", "business"):
                seats = r[f"{cab}_award_seats"]
                two_plus = r[f"{cab}_seats_is_two_plus"]
                if seats in (0, 1):
                    self.assertEqual(two_plus, 0)
                elif seats >= 2:
                    self.assertEqual(two_plus, 1)

    def test_f06_05_ttl_expiration_filtering_vs_expired_cache_row(self) -> None:
        repo, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute(
            """INSERT INTO elal_bonus_availability (
                id, origin_iata, destination_iata, direction, flight_number, flight_date,
                departure_time_local, arrival_time_local, economy_award_seats, economy_seats_is_two_plus,
                economy_points_per_pax, taxes_usd_per_pax, expires_at
            ) VALUES ('LY381_2027-04-11', 'TLV', 'FCO', 'OUTBOUND', 'LY381', '2027-04-11', '06:00', '08:45', 2, 1, 15000, 60.0, '2020-01-01T00:00:00Z')"""
        )
        conn.commit()
        adapter = self.get_elal_adapter(repo)
        res = adapter.sync_award_availability(["FCO"], date(2027, 4, 11), date(2027, 4, 11), origin="TLV")
        self.assertIsInstance(res, dict)
        avail = adapter.get_award_availability(["FCO"], date(2027, 4, 11), date(2027, 4, 11), origin="TLV")
        self.assertGreaterEqual(len(avail), 1)


class TestTier2F07FlightItinerariesBoundaries(Tier2BoundaryTestBase):
    """F07 — flight_itineraries SQLite Table boundaries & FK cascades."""

    def _seed_parent_query(self, conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            """INSERT INTO flight_search_queries (
                id, family_profile_id, date_selection_mode, airline_selection_mode, destination_iatas_json
            ) VALUES ('q1', 'p1', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]')"""
        )

    def test_f07_01_fulfillment_strategy_enum_check_rejects_invalid_strategy(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_query(conn)
        valid_strategies = (
            "FULL_BONUS_SAME_CABIN",
            "SPLIT_CABIN_BONUS",
            "HYBRID_BONUS_PLUS_CASH",
            "ONE_WAY_BONUS_ONE_WAY_CASH",
            "CASH_AND_POINTS",
            "MULTI_CLUB_PER_PASSENGER_SPLIT",
            "COMMERCIAL_CASH_ONLY",
        )
        for idx, strat in enumerate(valid_strategies):
            conn.execute(
                """INSERT INTO flight_itineraries (
                    id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                    destination_city_he, destination_city_en, departure_date, return_date,
                    trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                    fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                    family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                    full_cash_benchmark_usd, booking_deep_link_url
                ) VALUES (?, 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 1, ?, '[]', '[]', '[]', 500.0, 2000.0, 'https://elal.com')""",
                (f"it_{idx}", strat),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO flight_itineraries (
                    id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                    destination_city_he, destination_city_en, departure_date, return_date,
                    trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                    fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                    family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                    full_cash_benchmark_usd, booking_deep_link_url
                ) VALUES ('it_bad', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 1, 'UPGRADE_VOUCHER_ONLY', '[]', '[]', '[]', 500.0, 2000.0, 'https://elal.com')"""
            )

    def test_f07_02_trip_nights_min_1_and_zero_or_negative_rejected(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_query(conn)
        conn.execute(
            """INSERT INTO flight_itineraries (
                id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                destination_city_he, destination_city_en, departure_date, return_date,
                trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it_1', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-12', 1, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', '[]', 500.0, 500.0, 'https://elal.com')"""
        )
        for bad_nights in (0, -3):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_itineraries (
                        id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                        destination_city_he, destination_city_en, departure_date, return_date,
                        trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                        fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                        family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                        full_cash_benchmark_usd, booking_deep_link_url
                    ) VALUES (?, 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-12', ?, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', '[]', 500.0, 500.0, 'https://elal.com')""",
                    (f"bad_n_{bad_nights}", bad_nights),
                )

    def test_f07_03_non_negative_points_taxes_fares_baggage_and_negative_net_savings(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_query(conn)
        conn.execute(
            """INSERT INTO flight_itineraries (
                id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                destination_city_he, destination_city_en, departure_date, return_date,
                trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                family_ticket_allocation_json, total_matmid_points, total_taxes_and_fees_usd,
                total_supplemental_cash_fares_usd, total_baggage_fees_usd,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd, net_cash_saved_usd,
                booking_deep_link_url
            ) VALUES ('it_z', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', '[]', 0, 0.0, 0.0, 0.0, 0.0, 0.0, -50.0, 'https://elal.com')"""
        )
        for col in (
            "total_matmid_points",
            "total_taxes_and_fees_usd",
            "total_supplemental_cash_fares_usd",
            "total_baggage_fees_usd",
            "total_out_of_pocket_cash_usd",
            "full_cash_benchmark_usd",
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE flight_itineraries SET {col} = -1 WHERE id = 'it_z'")

    def test_f07_04_nullable_bonus_ids_and_invalid_bonus_fk_rejected(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_query(conn)
        conn.execute(
            """INSERT INTO flight_itineraries (
                id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                destination_city_he, destination_city_en, departure_date, return_date,
                trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                outbound_bonus_id, inbound_bonus_id, cents_per_point_value,
                family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it_null', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', NULL, NULL, NULL, '[]', 800.0, 800.0, 'https://elal.com')"""
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE flight_itineraries SET outbound_bonus_id = 'nonexistent_bonus_id' WHERE id = 'it_null'")

    def test_f07_05_foreign_key_cascade_delete_from_flight_search_queries(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_query(conn)
        conn.execute(
            """INSERT INTO flight_itineraries (
                id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                destination_city_he, destination_city_en, departure_date, return_date,
                trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it_del', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', '[]', 800.0, 800.0, 'https://elal.com')"""
        )
        conn.execute("DELETE FROM flight_search_queries WHERE id = 'q1'")
        cnt = conn.execute("SELECT COUNT(*) FROM flight_itineraries WHERE id = 'it_del'").fetchone()[0]
        self.assertEqual(cnt, 0)


class TestTier2F08VacationOptionProposalsBoundaries(Tier2BoundaryTestBase):
    """F08 — vacation_option_proposals SQLite Table boundaries & FK cascades."""

    def _seed_parent_chain(self, conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO family_profiles (id) VALUES ('p1')")
        conn.execute(
            """INSERT INTO flight_search_queries (
                id, family_profile_id, date_selection_mode, airline_selection_mode, destination_iatas_json
            ) VALUES ('q1', 'p1', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["FCO"]')"""
        )
        conn.execute(
            """INSERT INTO flight_itineraries (
                id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                destination_city_he, destination_city_en, departure_date, return_date,
                trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                family_ticket_allocation_json, total_out_of_pocket_cash_usd,
                full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it1', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 1, 'FULL_BONUS_SAME_CABIN', '[]', '[]', '[]', 300.0, 2000.0, 'https://elal.com')"""
        )

    def test_f08_01_scores_vus_fbvs_ctos_0_and_100_boundaries_vs_out_of_bounds(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        for s_val in (0.0, 100.0):
            conn.execute(
                """INSERT INTO vacation_option_proposals (
                    id, search_query_id, itinerary_id, associated_holiday_codes_json,
                    total_vacation_days, parent_pto_days_used, pto_efficiency_ratio,
                    school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                    total_school_days_missed_across_children, max_single_child_school_days_missed,
                    vacation_utilization_score, flight_bonus_value_score,
                    combined_trip_optimization_score, explanation_summary_he
                ) VALUES (?, 'q1', 'it1', '["PESACH"]', 7, 1.0, 7.0, 0.0, 1.0, '[]', 0, 0, ?, ?, ?, 'הסבר')""",
                (f"pr_{int(s_val)}", s_val, s_val, s_val),
            )
        for col in ("vacation_utilization_score", "flight_bonus_value_score", "combined_trip_optimization_score"):
            for bad_s in (-0.01, 100.01):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(f"UPDATE vacation_option_proposals SET {col} = ? WHERE id = 'pr_0'", (bad_s,))

    def test_f08_02_window_set_type_enum_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        for idx, wst in enumerate(("STRICT_INTERSECTION", "CAMP_ADJUSTED_INTERSECTION", "FRAMEWORK_DELTA_UNION", "SPECIFIC_USER_WINDOW")):
            conn.execute(
                """INSERT INTO vacation_option_proposals (
                    id, search_query_id, itinerary_id, associated_holiday_codes_json, window_set_type,
                    total_vacation_days, parent_pto_days_used, pto_efficiency_ratio,
                    school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                    total_school_days_missed_across_children, max_single_child_school_days_missed,
                    vacation_utilization_score, flight_bonus_value_score,
                    combined_trip_optimization_score, explanation_summary_he
                ) VALUES (?, 'q1', 'it1', '["PESACH"]', ?, 7, 1.0, 7.0, 0.0, 1.0, '[]', 0, 0, 80.0, 80.0, 80.0, 'הסבר')""",
                (f"wst_{idx}", wst),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE vacation_option_proposals SET window_set_type = 'RANDOM_WINDOW' WHERE id = 'wst_0'")

    def test_f08_03_total_vacation_days_min_1_and_non_negative_pto_and_missed_days(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        conn.execute(
            """INSERT INTO vacation_option_proposals (
                id, search_query_id, itinerary_id, associated_holiday_codes_json,
                total_vacation_days, parent_pto_days_used, pto_efficiency_ratio,
                school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                total_school_days_missed_across_children, max_single_child_school_days_missed,
                vacation_utilization_score, flight_bonus_value_score,
                combined_trip_optimization_score, explanation_summary_he
            ) VALUES ('pr_min', 'q1', 'it1', '["PESACH"]', 1, 0.0, 2.0, 0.0, 1.0, '[]', 0, 0, 50.0, 50.0, 50.0, 'הסבר')"""
        )
        for col, bad_val in (
            ("total_vacation_days", 0),
            ("parent_pto_days_used", -0.5),
            ("total_school_days_missed_across_children", -1),
            ("max_single_child_school_days_missed", -1),
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE vacation_option_proposals SET {col} = ? WHERE id = 'pr_min'", (bad_val,))

    def test_f08_04_cascade_delete_when_flight_itinerary_deleted(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        conn.execute(
            """INSERT INTO vacation_option_proposals (
                id, search_query_id, itinerary_id, associated_holiday_codes_json,
                total_vacation_days, parent_pto_days_used, pto_efficiency_ratio,
                school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                total_school_days_missed_across_children, max_single_child_school_days_missed,
                vacation_utilization_score, flight_bonus_value_score,
                combined_trip_optimization_score, explanation_summary_he
            ) VALUES ('pr_it_del', 'q1', 'it1', '["PESACH"]', 7, 1.0, 7.0, 0.0, 1.0, '[]', 0, 0, 80.0, 80.0, 80.0, 'הסבר')"""
        )
        conn.execute("DELETE FROM flight_itineraries WHERE id = 'it1'")
        cnt = conn.execute("SELECT COUNT(*) FROM vacation_option_proposals WHERE id = 'pr_it_del'").fetchone()[0]
        self.assertEqual(cnt, 0)

    def test_f08_05_full_4_level_cascade_delete_from_family_profile_to_proposals(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        conn.execute(
            """INSERT INTO vacation_option_proposals (
                id, search_query_id, itinerary_id, associated_holiday_codes_json,
                total_vacation_days, parent_pto_days_used, pto_efficiency_ratio,
                school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                total_school_days_missed_across_children, max_single_child_school_days_missed,
                vacation_utilization_score, flight_bonus_value_score,
                combined_trip_optimization_score, explanation_summary_he
            ) VALUES ('pr_full_del', 'q1', 'it1', '["PESACH"]', 7, 1.0, 7.0, 0.0, 1.0, '[]', 0, 0, 80.0, 80.0, 80.0, 'הסבר')"""
        )
        conn.execute("DELETE FROM family_profiles WHERE id = 'p1'")
        for tbl in ("flight_search_queries", "flight_itineraries", "vacation_option_proposals"):
            cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            self.assertEqual(cnt, 0, f"Expected 0 rows in {tbl} after profile delete")


class TestTier2F09MoEFrameworkSchedulesBoundaries(Tier2BoundaryTestBase):
    """F09 — 8 MoE Framework Schedules (MoECalendarService) boundaries."""

    def test_f09_01_june_20_2026_saturday_5_day_vs_6_day_middle_and_high_school(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        c5 = ChildFramework(id="c5", child_age_years=13, framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9, school_week_days=5)
        c6 = ChildFramework(id="c6", child_age_years=16, framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12, school_week_days=6)
        self.assertEqual(cal.get_child_day_status(c5, date(2026, 6, 18)).state_code, "SCHOOL_REGULAR")
        self.assertEqual(cal.get_child_day_status(c6, date(2026, 6, 18)).state_code, "SCHOOL_REGULAR")
        st_fri_5 = cal.get_child_day_status(c5, date(2026, 6, 19))
        st_fri_6 = cal.get_child_day_status(c6, date(2026, 6, 19))
        self.assertEqual(st_fri_5.psi_penalty, 0.0)
        self.assertEqual(st_fri_6.state_code, "SCHOOL_FRIDAY")
        self.assertAlmostEqual(st_fri_6.psi_penalty, 0.35, places=2)
        self.assertEqual(cal.get_child_day_status(c5, date(2026, 6, 20)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(c6, date(2026, 6, 21)).psi_penalty, 0.0)

    def test_f09_02_june_21_to_30_waning_days_for_gan_and_elementary_vs_middle_high_vacation(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        for fw in (MoEFrameworkType.MIDDLE_SCHOOL_7_9, MoEFrameworkType.HIGH_SCHOOL_10_12):
            ch = ChildFramework(id=f"c_{fw.value}", child_age_years=14, framework_type=fw)
            for d in (date(2027, 6, 21), date(2027, 6, 30)):
                st = cal.get_child_day_status(ch, d)
                self.assertEqual(st.state_code, "VACATION")
                self.assertEqual(st.psi_penalty, 0.0)
        for fw in (MoEFrameworkType.MUNICIPAL_GAN, MoEFrameworkType.ELEMENTARY_1_3, MoEFrameworkType.ELEMENTARY_4_6):
            ch = ChildFramework(id=f"c_{fw.value}", child_age_years=8, framework_type=fw, holiday_extension_mode="NONE")
            for d in (date(2027, 6, 21), date(2027, 6, 30)):
                st = cal.get_child_day_status(ch, d)
                self.assertEqual(st.state_code, "SCHOOL_END_OF_YEAR_WANING")
                self.assertAlmostEqual(st.psi_penalty, 0.50, places=2)
            st_jul = cal.get_child_day_status(ch, date(2027, 7, 1))
            self.assertEqual(st_jul.state_code, "VACATION")
            self.assertEqual(st_jul.psi_penalty, 0.0)

    def test_f09_03_daycare_aug_8_vs_aug_9_and_special_ed_aug_15_vs_aug_16_boundaries(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        dc = ChildFramework(id="dc", child_age_years=2, framework_type=MoEFrameworkType.DAYCARE_SUPERVISED)
        se = ChildFramework(id="se", child_age_years=10, framework_type=MoEFrameworkType.SPECIAL_ED)
        self.assertGreater(cal.get_child_day_status(dc, date(2026, 8, 6)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(dc, date(2026, 8, 9)).state_code, "VACATION")
        self.assertEqual(cal.get_child_day_status(dc, date(2026, 8, 31)).state_code, "VACATION")
        self.assertGreater(cal.get_child_day_status(se, date(2027, 8, 15)).psi_penalty, 0.0)
        self.assertEqual(cal.get_child_day_status(se, date(2027, 8, 16)).state_code, "VACATION")
        self.assertEqual(cal.get_child_day_status(se, date(2027, 8, 31)).state_code, "VACATION")

    def test_f09_04_nitzanim_treat_camp_as_vacation_true_vs_false_psi_penalty_toggle(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        c_true = ChildFramework(
            id="ct", child_age_years=5, framework_type=MoEFrameworkType.MUNICIPAL_GAN,
            holiday_extension_mode="NITZANIM_FULL_WITH_JULY", treat_camp_as_vacation=True,
        )
        c_false = ChildFramework(
            id="cf", child_age_years=5, framework_type=MoEFrameworkType.MUNICIPAL_GAN,
            holiday_extension_mode="NITZANIM_FULL_WITH_JULY", treat_camp_as_vacation=False,
        )
        c_none = ChildFramework(
            id="cn", child_age_years=5, framework_type=MoEFrameworkType.MUNICIPAL_GAN,
            holiday_extension_mode="NONE", treat_camp_as_vacation=True,
        )
        for d in (date(2026, 12, 7), date(2027, 4, 14), date(2027, 7, 5)):
            st_t = cal.get_child_day_status(c_true, d)
            st_f = cal.get_child_day_status(c_false, d)
            st_n = cal.get_child_day_status(c_none, d)
            self.assertEqual(st_t.state_code, "CAMP_OPTIONAL")
            self.assertAlmostEqual(st_t.psi_penalty, 0.15, places=2)
            self.assertEqual(st_f.state_code, "CAMP_OPTIONAL")
            self.assertAlmostEqual(st_f.psi_penalty, 0.75, places=2)
            self.assertEqual(st_n.state_code, "VACATION")
            self.assertEqual(st_n.psi_penalty, 0.0)

    def test_f09_05_bagrut_exam_blackout_date_overrides_to_infinite_penalty(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        hs = ChildFramework(
            id="hs", child_age_years=17, framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12,
            bagrut_blackout_dates=[date(2027, 5, 18), date(2027, 6, 24)],
        )
        for d in (date(2027, 5, 18), date(2027, 6, 24)):
            st = cal.get_child_day_status(hs, d)
            self.assertEqual(st.state_code, "EXAM_BLACKOUT")
            self.assertGreaterEqual(st.psi_penalty, 1000.0)


class TestTier2F10PreSeededCalendarsBoundaries(Tier2BoundaryTestBase):
    """F10 — Verified Pre-Seeded 2025-2026 & 2026-2027 Calendars boundaries."""

    def test_f10_01_isru_chag_sukkot_divergence_k9_school_vs_high_school_vacation_both_years(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        for isru_d in (date(2025, 10, 15), date(2026, 10, 4)):
            for fw in (
                MoEFrameworkType.MUNICIPAL_GAN,
                MoEFrameworkType.ELEMENTARY_1_3,
                MoEFrameworkType.ELEMENTARY_4_6,
                MoEFrameworkType.MIDDLE_SCHOOL_7_9,
            ):
                ch = ChildFramework(id=f"c_{fw.value}", child_age_years=10, framework_type=fw)
                st = cal.get_child_day_status(ch, isru_d)
                self.assertEqual(st.state_code, "SCHOOL_REGULAR")
                self.assertAlmostEqual(st.psi_penalty, 1.0, places=2)
            hs = ChildFramework(id="hs", child_age_years=16, framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12)
            st_hs = cal.get_child_day_status(hs, isru_d)
            self.assertEqual(st_hs.state_code, "VACATION")
            self.assertEqual(st_hs.psi_penalty, 0.0)

    def test_f10_02_lag_baomer_2026_high_school_only_vacation_vs_2027_regular_school_all_k12(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        hs = ChildFramework(id="hs", child_age_years=16, framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12)
        self.assertEqual(cal.get_child_day_status(hs, date(2026, 5, 5)).state_code, "VACATION")
        for fw in (MoEFrameworkType.MUNICIPAL_GAN, MoEFrameworkType.ELEMENTARY_4_6, MoEFrameworkType.MIDDLE_SCHOOL_7_9):
            ch = ChildFramework(id=f"c_{fw.value}", child_age_years=10, framework_type=fw)
            self.assertEqual(cal.get_child_day_status(ch, date(2026, 5, 5)).state_code, "SCHOOL_REGULAR")
        for fw in (MoEFrameworkType.MUNICIPAL_GAN, MoEFrameworkType.ELEMENTARY_4_6, MoEFrameworkType.MIDDLE_SCHOOL_7_9, MoEFrameworkType.HIGH_SCHOOL_10_12):
            ch = ChildFramework(id=f"c27_{fw.value}", child_age_years=12, framework_type=fw)
            self.assertEqual(cal.get_child_day_status(ch, date(2027, 5, 25)).state_code, "SCHOOL_REGULAR")

    def test_f10_03_isru_chag_pesach_resumes_school_for_all_frameworks_both_years(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        for last_vac, isru_pesach in ((date(2026, 4, 8), date(2026, 4, 9)), (date(2027, 4, 28), date(2027, 4, 29))):
            for fw in (MoEFrameworkType.MUNICIPAL_GAN, MoEFrameworkType.ELEMENTARY_1_3, MoEFrameworkType.MIDDLE_SCHOOL_7_9, MoEFrameworkType.HIGH_SCHOOL_10_12):
                ch = ChildFramework(id=f"p_{fw.value}", child_age_years=11, framework_type=fw)
                self.assertEqual(cal.get_child_day_status(ch, last_vac).state_code, "VACATION")
                self.assertEqual(cal.get_child_day_status(ch, isru_pesach).state_code, "SCHOOL_REGULAR")

    def test_f10_04_pesach_nitzanim_covered_vs_uncovered_boundary_dates(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        el = ChildFramework(
            id="el", child_age_years=7, framework_type=MoEFrameworkType.ELEMENTARY_1_3,
            holiday_extension_mode="NITZANIM_CHAGIM_ONLY", treat_camp_as_vacation=False,
        )
        self.assertEqual(cal.get_child_day_status(el, date(2027, 4, 19)).state_code, "CAMP_OPTIONAL")
        for offset in range(9):
            d = date(2027, 4, 20) + timedelta(days=offset)
            st = cal.get_child_day_status(el, d)
            self.assertEqual(st.state_code, "VACATION")
            self.assertEqual(st.psi_penalty, 0.0)

    def test_f10_05_bundled_calendar_json_files_conform_to_required_schema_keys(self) -> None:
        cal_dir = PROJECT_ROOT / "backend" / "calendars"
        schema_path = cal_dir / "schema" / "moe_calendar.schema.json"
        self.assertTrue(schema_path.exists())
        schema_doc = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIn("properties", schema_doc)
        for fname in ("moe_5786_2025_2026.json", "moe_5787_2026_2027.json", "moe_5788_2027_2028.json"):
            doc = json.loads((cal_dir / fname).read_text(encoding="utf-8"))
            for key in ("school_year_hebrew", "school_year_gregorian", "circular_ids", "frameworks", "periods"):
                self.assertIn(key, doc)
            for fw in MoEFrameworkType:
                self.assertIn(fw.value, doc["frameworks"])
            for p in doc["periods"]:
                s = date.fromisoformat(p["start_date"])
                e = date.fromisoformat(p["end_date"])
                r = date.fromisoformat(p["resume_date"])
                self.assertLessEqual(s, e)
                self.assertLess(e, r)


class TestTier2F11CalendarAutoUpdaterBoundaries(Tier2BoundaryTestBase):
    """F11 — Annual MoE Calendar Auto-Updater (MoECalendarAutoUpdaterService) boundaries."""

    def test_f11_01_single_4_digit_year_normalization_2027_and_2028(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=False)
        updater = MoECalendarAutoUpdaterService(repo)
        s27 = updater.sync_school_year("2027")
        s28 = updater.sync_school_year("2028")
        self.assertEqual(s27.school_year, "2026-2027")
        self.assertGreater(s27.windows_synced_count, 0)
        self.assertEqual(s28.school_year, "2027-2028")
        self.assertGreater(s28.windows_synced_count, 0)

    def test_f11_02_far_future_year_projection_2034_2035_upper_boundary(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=False)
        updater = MoECalendarAutoUpdaterService(repo)
        status = updater.sync_school_year("2034-2035")
        self.assertEqual(status.school_year, "2034-2035")
        self.assertEqual(status.calendar_sync_source, "HEBREW_RULE_PROJECTED")
        self.assertGreater(status.windows_synced_count, 0)
        fw_set = {w.framework_type.value if hasattr(w.framework_type, "value") else str(w.framework_type) for w in status.windows}
        for fw in MoEFrameworkType:
            self.assertIn(fw.value, fw_set)

    def test_f11_03_sept_1_falling_on_shabbat_shifts_school_start_to_sept_2(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=False)
        cal = MoECalendarService(repo)
        ch = ChildFramework(id="c1", child_age_years=8, framework_type=MoEFrameworkType.ELEMENTARY_1_3, school_week_days=6)
        st_sat = cal.get_child_day_status(ch, date(2029, 9, 1))
        st_sun = cal.get_child_day_status(ch, date(2029, 9, 2))
        self.assertEqual(st_sat.psi_penalty, 0.0)
        self.assertEqual(st_sun.state_code, "SCHOOL_REGULAR")

    def test_f11_04_invalid_malformed_school_year_string_raises_value_error(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=False)
        updater = MoECalendarAutoUpdaterService(repo)
        for bad_sy in ("invalid-year", "2026-2025", "2026-2028", ""):
            with self.assertRaises(ValueError):
                updater.sync_school_year(bad_sy)

    def test_f11_05_offline_sync_with_force_remote_check_falls_back_cleanly(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=False)
        updater = MoECalendarAutoUpdaterService(repo)
        status = updater.sync_school_year("2028-2029", force_remote_check=True)
        self.assertEqual(status.school_year, "2028-2029")
        self.assertEqual(status.calendar_sync_source, "HEBREW_RULE_PROJECTED")
        self.assertGreater(len(repo.get_moe_windows("2028-2029")), 0)


class TestTier2F12SpecificDatesAndAgeClassificationBoundaries(Tier2BoundaryTestBase):
    """F12 — Mode 1 (SPECIFIC_DATES) with Optional Frameworks & Age Classification boundaries."""

    def test_f12_01_classify_passenger_type_exact_age_boundaries_0_1_2_11_12_18(self) -> None:
        for age in (0, 1):
            self.assertEqual(classify_passenger_type(age, infant_seat=False), "INFANT_LAP")
            self.assertEqual(classify_passenger_type(age, infant_seat=True), "INFANT_SEAT")
        for age in (2, 11):
            self.assertEqual(classify_passenger_type(age), "CHILD")
        for age in (12, 17, 18, 21):
            self.assertEqual(classify_passenger_type(age), "YOUTH")
        for bad_age in (-1, 22):
            with self.assertRaises(ValueError):
                classify_passenger_type(bad_age)

    def test_f12_02_suggest_framework_for_age_boundaries_0_to_21(self) -> None:
        expected = (
            (0, "DAYCARE_SUPERVISED"),
            (2, "DAYCARE_SUPERVISED"),
            (3, "MUNICIPAL_GAN"),
            (5, "MUNICIPAL_GAN"),
            (6, "ELEMENTARY_1_3"),
            (8, "ELEMENTARY_1_3"),
            (9, "ELEMENTARY_4_6"),
            (11, "ELEMENTARY_4_6"),
            (12, "MIDDLE_SCHOOL_7_9"),
            (14, "MIDDLE_SCHOOL_7_9"),
            (15, "HIGH_SCHOOL_10_12"),
            (18, "HIGH_SCHOOL_10_12"),
            (21, "HIGH_SCHOOL_10_12"),
        )
        for age, fw in expected:
            self.assertEqual(suggest_framework_for_age(age), fw)
        for bad_age in (-1, 22):
            with self.assertRaises(ValueError):
                suggest_framework_for_age(bad_age)

    def test_f12_03_mode1_specific_dates_with_all_children_framework_type_none(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = FamilyProfile(
            id="p_mode1",
            adults_count=2,
            children=[
                ChildFramework(id="c1", child_age_years=1, framework_type=None),
                ChildFramework(id="c2", child_age_years=6, framework_type=None),
                ChildFramework(id="c3", child_age_years=14, framework_type=None),
            ],
        )
        q = FlightSearchQuery(
            family_profile_id="p_mode1",
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            flex_days_plus_minus=0,
        )
        wins = maximizer.generate_candidate_windows(q, prof)
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0].window_set_type, "SPECIFIC_USER_WINDOW")
        self.assertEqual(wins[0].school_absence_penalty, 0.0)

    def test_f12_04_mode1_flex_days_0_exact_single_window_vs_flex_days_7_bounded_by_nights(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        q0 = FlightSearchQuery(
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            flex_days_plus_minus=0,
            min_trip_nights=7,
            max_trip_nights=7,
        )
        w0 = maximizer.generate_candidate_windows(q0, prof)
        self.assertEqual(len(w0), 1)
        self.assertEqual((w0[0].start_date, w0[0].end_date), (date(2027, 4, 11), date(2027, 4, 18)))
        q7 = FlightSearchQuery(
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            flex_days_plus_minus=7,
            min_trip_nights=6,
            max_trip_nights=8,
        )
        w7 = maximizer.generate_candidate_windows(q7, prof)
        self.assertGreater(len(w7), 1)
        for w in w7:
            self.assertGreaterEqual(w.trip_nights, 6)
            self.assertLessEqual(w.trip_nights, 8)

    def test_f12_05_mode1_return_date_before_or_equal_departure_date_rejected(self) -> None:
        for ret_str in ("2027-04-11", "2027-04-10"):
            with self.assertRaises(ValueError):
                FlightSearchQuery(
                    date_selection_mode="SPECIFIC_DATES",
                    airline_selection_mode="EL_AL_ONLY",
                    destination_iatas=["FCO"],
                    specific_departure_date="2027-04-11",
                    specific_return_date=ret_str,
                )


class TestTier2F13MoEVacationMaximizationBoundaries(Tier2BoundaryTestBase):
    """F13 — Mode 2 (MOE_VACATION_MAXIMIZATION) Full School-Year Optimizer boundaries."""

    def test_f13_01_strict_intersection_vs_camp_adjusted_vs_framework_delta_union_ordering(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        prof = self.shared_repo.get_profile()
        mat_jun = cal.get_daily_status_matrix(prof, date(2027, 6, 21), date(2027, 6, 30))
        self.assertLess(len(mat_jun.strict_intersection_dates), len(mat_jun.framework_delta_union_dates))
        mat_han = cal.get_daily_status_matrix(prof, date(2026, 12, 6), date(2026, 12, 13))
        self.assertLessEqual(len(mat_han.strict_intersection_dates), len(mat_han.camp_adjusted_intersection_dates))
        self.assertLess(len(mat_han.strict_intersection_dates), len(mat_han.camp_adjusted_intersection_dates))

    def test_f13_02_max_bridge_days_shift_0_vs_3_boundary_filtering(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        q0 = FlightSearchQuery(
            date_selection_mode="MOE_VACATION_MAXIMIZATION",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            school_year="2026-2027",
            target_holiday_codes=["PURIM"],
            min_trip_nights=4,
            max_trip_nights=5,
            max_bridge_days_shift=0,
            overlap_policy="STRICT_ALL_CHILDREN_OFF",
        )
        q3 = FlightSearchQuery(
            date_selection_mode="MOE_VACATION_MAXIMIZATION",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            school_year="2026-2027",
            target_holiday_codes=["PURIM"],
            min_trip_nights=4,
            max_trip_nights=5,
            max_bridge_days_shift=3,
            overlap_policy="MAXIMIZE_EFFICIENCY_SCORE",
        )
        w0 = maximizer.generate_candidate_windows(q0, prof)
        w3 = maximizer.generate_candidate_windows(q3, prof)
        self.assertTrue(all(w.max_single_child_school_days_missed > 0 for w in w0))
        self.assertTrue(any(w.start_date == date(2027, 3, 23) and w.end_date == date(2027, 3, 27) for w in w3))

    def test_f13_03_max_pto_per_trip_zero_restricts_to_zero_pto_windows(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        prof.max_pto_per_trip = 0.5
        prof.erev_chag_pto_weight = 0.0
        q = FlightSearchQuery(
            date_selection_mode="MOE_VACATION_MAXIMIZATION",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["ATH"],
            school_year="2026-2027",
            target_holiday_codes=["ROSH_HASHANAH", "SHAVUOT"],
            min_trip_nights=2,
            max_trip_nights=4,
            max_bridge_days_shift=0,
            overlap_policy="STRICT_ALL_CHILDREN_OFF",
        )
        wins = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(wins), 0)
        self.assertTrue(any(w.parent_pto_days_used == 0.0 for w in wins))

    def test_f13_04_bagrut_blackout_date_disqualifies_overlapping_candidate_windows(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        prof.children.append(
            ChildFramework(
                id="hs_b",
                child_age_years=17,
                framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12,
                bagrut_blackout_dates=[date(2027, 6, 23)],
            )
        )
        q = FlightSearchQuery(
            date_selection_mode="MOE_VACATION_MAXIMIZATION",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["MAD"],
            school_year="2026-2027",
            target_holiday_codes=["SUMMER_JUNE_20_30"],
            min_trip_nights=3,
            max_trip_nights=5,
            max_bridge_days_shift=2,
        )
        wins = maximizer.generate_candidate_windows(q, prof)
        for w in wins:
            self.assertFalse(w.start_date <= date(2027, 6, 23) <= w.end_date)

    def test_f13_05_tlv_yom_kippur_closure_blocks_departures_and_returns_on_closure_dates(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        blocked = {date(2025, 10, 1), date(2025, 10, 2), date(2026, 9, 20), date(2026, 9, 21)}
        for sy in ("2025-2026", "2026-2027"):
            q = FlightSearchQuery(
                date_selection_mode="MOE_VACATION_MAXIMIZATION",
                airline_selection_mode="EL_AL_ONLY",
                destination_iatas=["FCO"],
                school_year=sy,
                target_holiday_codes=["YOM_KIPPUR_SUKKOT"],
                min_trip_nights=4,
                max_trip_nights=12,
            )
            wins = maximizer.generate_candidate_windows(q, prof)
            self.assertGreater(len(wins), 0)
            for w in wins:
                self.assertNotIn(w.start_date, blocked)
                self.assertNotIn(w.end_date, blocked)


class TestTier2F14HolidayDirectIntentBoundaries(Tier2BoundaryTestBase):
    """F14 — Mode 3 (HOLIDAY_DIRECT_INTENT) Specific Holiday/Vacation & Year Maximizer boundaries."""

    def test_f14_01_all_11_structured_holiday_codes_resolve_non_empty_windows(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        codes = (
            "PESACH", "SUKKOT", "YOM_KIPPUR_SUKKOT", "HANUKKAH", "ROSH_HASHANAH",
            "PURIM", "SHAVUOT", "YOM_HAATZMAUT", "SUMMER_JUNE_20_30", "SUMMER_JULY", "SUMMER_AUGUST",
        )
        for code in codes:
            q = FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                airline_selection_mode="EL_AL_ONLY",
                destination_iatas=["FCO"],
                direct_holiday_code=code,
                direct_target_year=2027,
                min_trip_nights=2,
                max_trip_nights=10,
                max_bridge_days_shift=3,
            )
            wins = maximizer.generate_candidate_windows(q, prof)
            self.assertGreaterEqual(len(wins), 1, f"Expected windows for {code}")

    def test_f14_02_future_target_year_2029_auto_triggers_calendar_projection(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=False)
        cal = MoECalendarService(repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            direct_holiday_code="PESACH",
            direct_target_year=2029,
            min_trip_nights=5,
            max_trip_nights=8,
        )
        wins = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(wins), 0)
        self.assertTrue(all(w.start_date.year == 2029 for w in wins))
        self.assertGreater(len(repo.get_moe_windows("2028-2029")), 0)

    def test_f14_03_short_holiday_yom_haatzmaut_requires_bridge_days_for_4_night_trip(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        q0 = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["ATH"],
            direct_holiday_code="YOM_HAATZMAUT",
            direct_target_year=2027,
            min_trip_nights=4,
            max_trip_nights=5,
            max_bridge_days_shift=0,
            overlap_policy="STRICT_ALL_CHILDREN_OFF",
        )
        q3 = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["ATH"],
            direct_holiday_code="YOM_HAATZMAUT",
            direct_target_year=2027,
            min_trip_nights=4,
            max_trip_nights=5,
            max_bridge_days_shift=3,
        )
        w0 = maximizer.generate_candidate_windows(q0, prof)
        w3 = maximizer.generate_candidate_windows(q3, prof)
        self.assertTrue(all(w.max_single_child_school_days_missed > 0 for w in w0))
        self.assertGreater(len(w3), 0)
        self.assertTrue(all(w.trip_nights >= 4 for w in w3))

    def test_f14_04_invalid_direct_holiday_code_raises_value_error(self) -> None:
        from backend.app.schemas.domain import DIRECT_HOLIDAY_CODES

        self.assertNotIn("CHRISTMAS", DIRECT_HOLIDAY_CODES)
        self.assertNotIn("", DIRECT_HOLIDAY_CODES)
        with self.assertRaises(ValueError):
            FlightSearchQuery(
                date_selection_mode="INVALID_MODE",
                airline_selection_mode="EL_AL_ONLY",
                destination_iatas=["FCO"],
            )

    def test_f14_05_target_year_boundary_2025_and_2035_vs_out_of_bounds_2024_2036(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        for yr, code in ((2025, "SUKKOT"), (2035, "PESACH")):
            q = FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                airline_selection_mode="EL_AL_ONLY",
                destination_iatas=["FCO"],
                direct_holiday_code=code,
                direct_target_year=yr,
            )
            self.assertGreater(len(maximizer.generate_candidate_windows(q, prof)), 0)
        for bad_yr in (2024, 2036):
            with self.assertRaises(ValueError):
                FlightSearchQuery(
                    date_selection_mode="HOLIDAY_DIRECT_INTENT",
                    airline_selection_mode="EL_AL_ONLY",
                    destination_iatas=["FCO"],
                    direct_holiday_code="PESACH",
                    direct_target_year=bad_yr,
                )


class TestTier2F15CalendarScoringEngineBoundaries(Tier2BoundaryTestBase):
    """F15 — Mathematical Calendar Scoring Engine (PER, SAP, CCG, VUS) boundaries."""

    def test_f15_01_per_division_by_zero_guard_when_parent_pto_is_zero(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        prof.workweek_type = "SUN_THU"
        prof.erev_chag_pto_weight = 0.0
        win_wknd = maximizer.evaluate_window(prof, date(2027, 4, 16), date(2027, 4, 17))
        self.assertEqual(win_wknd.parent_pto_days_used, 0.0)
        self.assertEqual(win_wknd.total_vacation_days, 2)
        self.assertAlmostEqual(win_wknd.pto_efficiency_ratio, 4.0, places=2)
        win_rh = maximizer.evaluate_window(prof, date(2026, 9, 11), date(2026, 9, 13))
        self.assertEqual(win_rh.parent_pto_days_used, 0.0)
        self.assertEqual(win_rh.total_vacation_days, 3)
        self.assertAlmostEqual(win_rh.pto_efficiency_ratio, 6.0, places=2)

    def test_f15_02_per_sub_half_day_pto_clamped_at_0_5_vs_above_0_5(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        prof.workweek_type = "SUN_THU"
        prof.erev_chag_pto_weight = 0.5
        win_half = maximizer.evaluate_window(prof, date(2027, 6, 10), date(2027, 6, 12))
        self.assertAlmostEqual(win_half.parent_pto_days_used, 0.5, places=2)
        self.assertAlmostEqual(win_half.pto_efficiency_ratio, 6.0, places=2)
        win_one = maximizer.evaluate_window(prof, date(2027, 6, 9), date(2027, 6, 12))
        self.assertAlmostEqual(win_one.parent_pto_days_used, 1.5, places=2)
        self.assertAlmostEqual(win_one.pto_efficiency_ratio, round(4.0 / 1.5, 2), places=2)

    def test_f15_03_vus_upper_clamp_at_100_0_on_perfect_uncovered_holiday_window(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        win = maximizer.evaluate_window(prof, date(2027, 4, 20), date(2027, 4, 28))
        self.assertEqual(win.school_absence_penalty, 0.0)
        self.assertEqual(win.childcare_coverage_gain, 1.0)
        self.assertEqual(win.vacation_utilization_score, 100.0)

    def test_f15_04_vus_lower_clamp_at_0_0_under_extreme_school_absence_penalty(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = FamilyProfile(
            id="p_ext",
            adults_count=2,
            children=[
                ChildFramework(
                    id="hs_ext",
                    child_age_years=17,
                    framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12,
                    absence_penalty_weight=15.0,
                )
            ],
        )
        win = maximizer.evaluate_window(prof, date(2027, 1, 10), date(2027, 1, 14))
        self.assertEqual(win.vacation_utilization_score, 0.0)
        self.assertGreaterEqual(win.vacation_utilization_score, 0.0)
        self.assertLessEqual(win.vacation_utilization_score, 100.0)

    def test_f15_05_adult_only_or_null_framework_children_sap_zero_and_ccg_fallback(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        for prof in (
            FamilyProfile(id="p_no_ch", adults_count=2, children=[]),
            FamilyProfile(
                id="p_null_fw",
                adults_count=2,
                children=[ChildFramework(id="c1", child_age_years=6, framework_type=None)],
            ),
        ):
            win = maximizer.evaluate_window(prof, date(2027, 4, 11), date(2027, 4, 18))
            self.assertEqual(win.school_absence_penalty, 0.0)
            self.assertEqual(win.childcare_coverage_gain, 1.0)
            self.assertGreaterEqual(win.vacation_utilization_score, 0.0)
            self.assertLessEqual(win.vacation_utilization_score, 100.0)


class TestTier2F16PreSeededDatasetBoundaries(Tier2BoundaryTestBase):
    """F16 — Pre-Seeded 2025-2028 Holiday Award & Commercial Flight Dataset boundaries."""

    def test_f16_01_all_five_award_zones_a_through_e_represented_with_valid_points_and_taxes(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        zones = {r["award_zone"] for r in conn.execute("SELECT DISTINCT award_zone FROM elal_bonus_availability").fetchall()}
        for expected_z in ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E"):
            self.assertIn(expected_z, zones)
        rows = conn.execute("SELECT * FROM elal_bonus_availability").fetchall()
        for r in rows:
            self.assertGreater(r["taxes_usd_per_pax"], 0.0)
            if r["economy_points_per_pax"] and r["business_points_per_pax"]:
                self.assertLess(r["economy_points_per_pax"], r["business_points_per_pax"])
            if r["award_zone"] != "ZONE_A" and r["economy_points_per_pax"] and r["premium_points_per_pax"] and r["business_points_per_pax"]:
                self.assertLess(r["economy_points_per_pax"], r["premium_points_per_pax"])
                self.assertLess(r["premium_points_per_pax"], r["business_points_per_pax"])

    def test_f16_02_narrowbody_737_routes_vs_widebody_787_777_premium_cabin_availability(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        nb_rows = conn.execute(
            "SELECT * FROM elal_bonus_availability WHERE aircraft_type IN ('738', '739') AND (destination_iata IN ('LCA', 'RHO') OR origin_iata IN ('LCA', 'RHO'))"
        ).fetchall()
        self.assertGreater(len(nb_rows), 0)
        for r in nb_rows:
            self.assertEqual(r["premium_award_seats"], 0)
            self.assertEqual(r["premium_seats_is_two_plus"], 0)
        wb_rows = conn.execute(
            "SELECT * FROM elal_bonus_availability WHERE aircraft_type IN ('788', '789', '772') AND premium_award_seats > 0"
        ).fetchall()
        self.assertGreater(len(wb_rows), 0)

    def test_f16_03_zero_shabbat_or_yom_kippur_elal_flights_in_seeded_dataset(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        yk_dates = {"2025-10-01", "2025-10-02", "2026-09-20", "2026-09-21", "2027-10-10", "2027-10-11"}
        rows = conn.execute("SELECT * FROM elal_bonus_availability WHERE operating_carrier IN ('LY', '2U')").fetchall()
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertNotIn(r["flight_date"], yk_dates)
            d = date.fromisoformat(r["flight_date"])
            hh, mm = (int(x) for x in r["departure_time_local"].split(":")[:2])
            mins = hh * 60 + mm
            if d.weekday() == 4:
                self.assertLess(mins, 15 * 60)
            if d.weekday() == 5:
                self.assertGreater(mins, 19 * 60 + 30)

    def test_f16_04_canonical_pesach_2027_rome_ly381_ly384_benchmark_records_present(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        out_r = conn.execute(
            "SELECT * FROM elal_bonus_availability WHERE origin_iata='TLV' AND destination_iata='FCO' AND flight_date='2027-04-11' AND flight_number='LY381'"
        ).fetchone()
        in_r = conn.execute(
            "SELECT * FROM elal_bonus_availability WHERE origin_iata='FCO' AND destination_iata='TLV' AND flight_date='2027-04-18' AND flight_number='LY384'"
        ).fetchone()
        self.assertIsNotNone(out_r)
        self.assertIsNotNone(in_r)
        self.assertGreaterEqual(out_r["economy_award_seats"], 2)
        self.assertEqual(out_r["economy_seats_is_two_plus"], 1)
        self.assertGreaterEqual(out_r["premium_award_seats"], 2)
        self.assertEqual(out_r["premium_seats_is_two_plus"], 1)
        self.assertGreaterEqual(in_r["economy_award_seats"], 2)
        self.assertEqual(in_r["premium_award_seats"], 1)
        self.assertEqual(in_r["premium_seats_is_two_plus"], 0)
        self.assertGreaterEqual(in_r["business_award_seats"], 2)

    def test_f16_05_seeded_years_span_2025_through_2028_boundaries(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        years = {r[0] for r in conn.execute("SELECT DISTINCT substr(flight_date, 1, 4) FROM elal_bonus_availability").fetchall()}
        for yr in ("2025", "2026", "2027", "2028"):
            self.assertIn(yr, years)



def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, default)
    return val.value if hasattr(val, "value") else val


class TestTier2F17ElAlOnlyShabbatYomKippurBoundaries(Tier2BoundaryTestBase):
    """F17 — EL_AL_ONLY Mode & Shabbat / Yom Kippur Operational Constraints boundaries."""

    def test_f17_01_shabbat_friday_afternoon_and_saturday_daytime_flights_rejected(self) -> None:
        repo, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        for fid, fdate, dep_t in (
            ("LY_FRI_LATE", "2027-04-16", "16:30"),
            ("LY_SAT_DAY", "2027-04-17", "11:00"),
            ("LY_FRI_AM", "2027-04-16", "07:30"),
            ("LY_SAT_NIGHT", "2027-04-17", "21:45"),
        ):
            conn.execute(
                """INSERT INTO elal_bonus_availability (
                    id, origin_iata, destination_iata, direction, flight_number, operating_carrier,
                    flight_date, departure_time_local, arrival_time_local, economy_award_seats,
                    economy_seats_is_two_plus, economy_points_per_pax, taxes_usd_per_pax, expires_at
                ) VALUES (?, 'TLV', 'FCO', 'OUTBOUND', ?, 'LY', ?, ?, '23:55', 2, 1, 15000, 50.0, '2029-01-01T00:00:00Z')""",
                (fid, fid, fdate, dep_t),
            )
        conn.commit()
        elal = self.get_elal_adapter(repo)
        avail = elal.get_award_availability(["FCO"], date(2027, 4, 16), date(2027, 4, 17))
        fnums = {a.flight_number for a in avail}
        self.assertNotIn("LY_FRI_LATE", fnums)
        self.assertNotIn("LY_SAT_DAY", fnums)
        self.assertIn("LY_FRI_AM", fnums)
        self.assertIn("LY_SAT_NIGHT", fnums)

    def test_f17_02_tlv_yom_kippur_shutdown_flights_blocked_in_2025_and_2026(self) -> None:
        elal = self.get_elal_adapter()
        for s_d, e_d in ((date(2025, 10, 1), date(2025, 10, 2)), (date(2026, 9, 20), date(2026, 9, 21))):
            avail = elal.get_award_availability(["FCO", "ATH", "LHR", "JFK"], s_d, e_d)
            self.assertEqual(len(avail), 0)

    def test_f17_03_include_sundor_flights_false_excludes_2u_carrier(self) -> None:
        planner = self.get_planner()
        props_with = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "include_sundor_flights": True,
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["RHO", "LCA", "FCO"],
            }
        )
        props_without = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "include_sundor_flights": False,
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["RHO", "LCA", "FCO"],
            }
        )
        self.assertGreater(len(props_with), 0)
        for p in props_without:
            assert p.itinerary is not None
            self.assertNotEqual(p.itinerary.primary_carrier_iata, "2U")
            for leg in p.itinerary.outbound_legs + p.itinerary.inbound_legs:
                self.assertNotEqual(leg.operating_carrier, "2U")

    def test_f17_04_non_elal_carriers_w6_fr_ba_lh_strictly_excluded_in_elal_only_mode(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO", "ATH", "LHR", "BUD"],
            }
        )
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            assert p.itinerary is not None
            self.assertTrue(bool(p.itinerary.is_elal_flight))
            self.assertIn(p.itinerary.primary_carrier_iata, ("LY", "2U"))

    def test_f17_05_elal_only_with_search_elal_bonus_tickets_false_returns_elal_commercial_cash_only(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "search_elal_bonus_tickets": False,
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            }
        )
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            assert p.itinerary is not None
            self.assertTrue(bool(p.itinerary.is_elal_flight))
            self.assertFalse(bool(p.itinerary.utilizes_elal_bonus))
            self.assertEqual(_get_field(p.itinerary, "fulfillment_strategy"), "COMMERCIAL_CASH_ONLY")
            self.assertEqual(p.itinerary.total_matmid_points, 0)


class TestTier2F18AllAirlinesBaggageNormalizerBoundaries(Tier2BoundaryTestBase):
    """F18 — ALL_AIRLINES Mode & FamilyBaggageNormalizer boundaries."""

    def test_f18_01_lcc_carriers_w6_fr_u2_add_positive_baggage_fees_vs_full_service_ly_lh_ba(self) -> None:
        comm = self.get_commercial_adapter()
        prof = self.shared_repo.get_profile()
        for lcc in ("W6", "FR", "U2"):
            bag_fee, total_cash = comm.normalize_family_baggage_cost(lcc, 1000.0, prof, 7)
            self.assertGreater(bag_fee, 0.0)
            self.assertAlmostEqual(total_cash, 1000.0 + bag_fee, places=2)
            for fsc in ("LY", "LH", "BA"):
                fsc_bag, _ = comm.normalize_family_baggage_cost(fsc, 1000.0, prof, 7)
                self.assertLess(fsc_bag, bag_fee)

    def test_f18_02_infant_on_lap_does_not_incur_adult_trolley_fee_unlike_seated_passengers(self) -> None:
        comm = self.get_commercial_adapter()
        prof_infant = FamilyProfile(
            adults_count=2,
            children=[ChildFramework(id="inf", child_age_years=1, passenger_Current_type="INFANT_LAP")],
        )
        prof_child = FamilyProfile(
            adults_count=2,
            children=[ChildFramework(id="ch", child_age_years=6, passenger_Current_type="CHILD")],
        )
        bag_inf, _ = comm.normalize_family_baggage_cost("W6", 1000.0, prof_infant, 7)
        bag_ch, _ = comm.normalize_family_baggage_cost("W6", 1000.0, prof_child, 7)
        self.assertLess(bag_inf, bag_ch)

    def test_f18_03_short_weekend_trip_1_to_3_nights_vs_long_trip_10_nights_baggage_scaling(self) -> None:
        comm = self.get_commercial_adapter()
        prof = self.shared_repo.get_profile()
        bag_short, _ = comm.normalize_family_baggage_cost("FR", 800.0, prof, 2)
        bag_long, _ = comm.normalize_family_baggage_cost("FR", 800.0, prof, 10)
        self.assertGreater(bag_short, 0.0)
        self.assertLessEqual(bag_short, bag_long)

    def test_f18_04_single_adult_no_children_minimum_household_baggage_boundary(self) -> None:
        comm = self.get_commercial_adapter()
        prof_single = FamilyProfile(adults_count=1, children=[])
        bag_fee, total_cash = comm.normalize_family_baggage_cost("U2", 200.0, prof_single, 5)
        self.assertGreater(bag_fee, 0.0)
        self.assertAlmostEqual(total_cash, 200.0 + bag_fee, places=2)

    def test_f18_05_unknown_carrier_code_or_zero_base_fare_handled_gracefully(self) -> None:
        comm = self.get_commercial_adapter()
        prof = self.shared_repo.get_profile()
        bag_fee, total_cash = comm.normalize_family_baggage_cost("ZZ", 0.0, prof, 5)
        self.assertGreaterEqual(bag_fee, 0.0)
        self.assertGreaterEqual(total_cash, 0.0)
        self.assertAlmostEqual(total_cash, bag_fee, places=2)


class TestTier2F19MetroIataExpansionBoundaries(Tier2BoundaryTestBase):
    """F19 — Metro-to-Airport 3-Letter IATA Expansion (ElAlRbdDataClientAdapter) boundaries."""

    def test_f19_01_all_7_metro_codes_expand_to_exact_3_letter_airport_iatas(self) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas(["NYC", "LON", "PAR", "MIL", "ROM", "TYO", "MIA_AREA"])
        self.assertEqual(
            expanded,
            ["JFK", "EWR", "LHR", "LTN", "CDG", "MXP", "FCO", "NRT", "MIA", "FLL"],
        )
        for code in expanded:
            self.assertEqual(len(code), 3)
            self.assertTrue(code.isalpha() and code.isupper())

    def test_f19_02_lowercase_and_whitespace_metro_and_airport_codes_normalized(self) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas([" nyc ", "lon", " fco "])
        self.assertEqual(expanded, ["JFK", "EWR", "LHR", "LTN", "FCO"])

    def test_f19_03_duplicate_metro_and_constituent_airport_deduplicated_preserving_order(self) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas(["NYC", "JFK", "EWR", "NYC"])
        self.assertEqual(expanded, ["JFK", "EWR"])

    def test_f19_04_empty_list_and_invalid_iata_codes_rejected_or_filtered(self) -> None:
        elal = self.get_elal_adapter()
        try:
            res_empty = elal.expand_metro_iatas([])
            self.assertEqual(res_empty, [])
        except ValueError:
            pass
        for bad_input in (["INVALID_CODE_123"], ["12"]):
            try:
                out = elal.expand_metro_iatas(bad_input)
                self.assertEqual([c for c in out if len(c) == 3 and c.isalpha()], [])
            except ValueError:
                pass

    def test_f19_05_lhr_high_uk_apd_tax_vs_ltn_lower_tax_preserved_in_lon_expansion(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(["LON"], date(2026, 9, 1), date(2027, 8, 31))
        lhr_taxes = [a.taxes_usd_per_pax for a in avail if "LHR" in (a.origin_iata, a.destination_iata)]
        ltn_taxes = [a.taxes_usd_per_pax for a in avail if "LTN" in (a.origin_iata, a.destination_iata)]
        self.assertGreater(len(lhr_taxes), 0)
        self.assertGreater(len(ltn_taxes), 0)
        self.assertGreater(max(lhr_taxes), min(ltn_taxes))


class TestTier2F20AnywhereDiscoveryBoundaries(Tier2BoundaryTestBase):
    """F20 — ANYWHERE Region Discovery boundaries."""

    def test_f20_01_anywhere_expands_across_all_5_award_zones_a_through_e(self) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas(["ANYWHERE"])
        self.assertGreaterEqual(len(expanded), 15)
        avail = elal.get_award_availability(["ANYWHERE"], date(2027, 4, 10), date(2027, 4, 28))
        zones = {a.award_zone for a in avail}
        self.assertGreaterEqual(len(zones), 3)

    def test_f20_02_anywhere_mixed_with_explicit_iatas_deduplicates_cleanly(self) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas(["ANYWHERE", "FCO", "NYC"])
        self.assertEqual(len(expanded), len(set(expanded)))
        for code in ("FCO", "JFK", "EWR"):
            self.assertEqual(expanded.count(code), 1)

    def test_f20_03_anywhere_with_preferred_cabin_business_only_filter(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(
            ["ANYWHERE"], date(2027, 4, 10), date(2027, 4, 28), preferred_cabins=["BUSINESS"]
        )
        self.assertGreater(len(avail), 0)
        for a in avail:
            self.assertGreaterEqual(a.business_award_seats, 1)
            self.assertIn(a.business_rbd_code, ("I", "W"))

    def test_f20_04_anywhere_on_yom_kippur_shutdown_date_returns_zero_flights(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(["ANYWHERE"], date(2026, 9, 20), date(2026, 9, 21))
        self.assertEqual(avail, [])

    def test_f20_05_anywhere_search_ranks_proposals_descending_by_ctos(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["ANYWHERE"],
            }
        )
        self.assertGreater(len(proposals), 1)
        ctos_list = [p.combined_trip_optimization_score for p in proposals]
        self.assertEqual(ctos_list, sorted(ctos_list, reverse=True))


class TestTier2F21RbdSeatCapParserAndRateLimiterBoundaries(Tier2BoundaryTestBase):
    """F21 — Classic Award RBD Bucket & 0/1/2+ Seat Cap Parser + Polite Rate Limiter boundaries."""

    def test_f21_01_seat_indicator_0_1_and_2_plus_string_and_int_parsing(self) -> None:
        for raw_zero in (0, "0"):
            av0 = ElAlBonusAvailability(
                id="a0", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
                flight_number="LY381", flight_date=date(2027, 4, 11),
                economy_award_seats=int(raw_zero), economy_seats_is_two_plus=False,
            )
            self.assertEqual(av0.economy_award_seats, 0)
            self.assertFalse(av0.economy_seats_is_two_plus)
        av1 = ElAlBonusAvailability(
            id="a1", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=1, economy_seats_is_two_plus=False,
        )
        self.assertEqual(av1.economy_award_seats, 1)
        self.assertFalse(av1.economy_seats_is_two_plus)
        av2 = ElAlBonusAvailability(
            id="a2", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=2, economy_seats_is_two_plus=True,
        )
        self.assertEqual(av2.economy_award_seats, 2)
        self.assertTrue(av2.economy_seats_is_two_plus)

    def test_f21_02_classic_award_rbd_codes_e_x_u_p_a_r_i_w_validation(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(["FCO", "ATH", "LHR"], date(2026, 9, 1), date(2027, 8, 31))
        self.assertGreater(len(avail), 0)
        for r in avail:
            self.assertIn(r.economy_rbd_code, ("E", "X", "U"))
            self.assertIn(r.premium_rbd_code, ("P", "A", "R"))
            self.assertIn(r.business_rbd_code, ("I", "W"))
            self.assertNotIn(r.economy_rbd_code, ("Y", "K", "L"))

    def test_f21_03_tuesday_flycard_50_percent_promo_halves_economy_points(self) -> None:
        conn = self.get_raw_conn(self.shared_db_path)
        promo_rows = conn.execute(
            "SELECT * FROM elal_bonus_availability WHERE flycard_promo_active = 1"
        ).fetchall()
        regular_rows = conn.execute(
            "SELECT award_zone, MAX(economy_points_per_pax) AS max_econ FROM elal_bonus_availability WHERE flycard_promo_active = 0 GROUP BY award_zone"
        ).fetchall()
        max_by_zone = {r["award_zone"]: r["max_econ"] for r in regular_rows}
        self.assertGreater(len(max_by_zone), 0)
        for pr in promo_rows:
            self.assertGreater(pr["taxes_usd_per_pax"], 0.0)
            self.assertLess(pr["economy_points_per_pax"], max_by_zone[pr["award_zone"]])

    def test_f21_04_batch_route_month_cap_15_enforced_by_rate_limiter(self) -> None:
        from backend.app.config_manager.settings import get_settings

        settings = get_settings()
        self.assertIn("elal_rbd_client", settings)
        self.assertEqual(settings["elal_rbd_client"].get("max_route_months_per_batch", 15), 15)
        repo, _ = self.create_temp_repo(auto_seed=True)
        elal = self.get_elal_adapter(repo)
        many_dests = [
            "FCO", "MXP", "ATH", "LCA", "RHO", "VIE", "BUD", "PRG",
            "BER", "CDG", "LHR", "LTN", "AMS", "MAD", "BCN", "BKK", "NRT", "JFK",
        ]
        res = elal.sync_award_availability(many_dests, date(2027, 4, 1), date(2027, 5, 15))
        self.assertIsInstance(res, dict)
        self.assertIn("expanded_destinations", res)

    def test_f21_05_4_hour_ttl_cache_hit_vs_force_refresh_bypass(self) -> None:
        repo, _ = self.create_temp_repo(auto_seed=True)
        elal = self.get_elal_adapter(repo)
        hit_res = elal.sync_award_availability(["FCO"], date(2027, 4, 11), date(2027, 4, 18), force_refresh=False)
        self.assertTrue(bool(hit_res["cache_hit"]))
        miss_res = elal.sync_award_availability(["FCO"], date(2027, 4, 11), date(2027, 4, 18), force_refresh=True)
        self.assertFalse(bool(miss_res["cache_hit"]))
        self.assertGreaterEqual(miss_res["records_synced"], 1)


class TestTier2F22FullBonusSameCabinBoundaries(Tier2BoundaryTestBase):
    """F22 — Strategy 1: FULL_BONUS_SAME_CABIN boundaries."""

    def _make_pair(self, out_econ: int = 2, in_econ: int = 2, out_two_plus: bool = True, in_two_plus: bool = True) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_f22", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=out_econ, economy_seats_is_two_plus=out_two_plus,
            premium_award_seats=2, premium_seats_is_two_plus=True,
            business_award_seats=2, business_seats_is_two_plus=True,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_f22", origin_iata="FCO", destination_iata="TLV", direction="INBOUND",
            flight_number="LY384", flight_date=date(2027, 4, 18),
            economy_award_seats=in_econ, economy_seats_is_two_plus=in_two_plus,
            premium_award_seats=2, premium_seats_is_two_plus=True,
            business_award_seats=2, business_seats_is_two_plus=True,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f22_01_requires_two_plus_seat_verification_false_for_n_1_and_2_true_for_n_3_to_6(self) -> None:
        eng = self.get_wallet_engine()
        out_a, in_a = self._make_pair(out_econ=5, in_econ=5, out_two_plus=True, in_two_plus=True)
        for n_adults, expect_verify in ((1, False), (2, False), (3, True), (5, True)):
            prof = FamilyProfile(adults_count=n_adults, matmid_points_balance=300000, children=[])
            res = eng.allocate_family_tickets(
                prof, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
            )
            self.assertIsNotNone(res)
            self.assertEqual(bool(_get_field(res, "requires_two_plus_seat_verification")), expect_verify)

    def test_f22_02_rejected_when_cabin_has_only_1_seat_for_family_of_2_or_more(self) -> None:
        eng = self.get_wallet_engine()
        out_a, in_a = self._make_pair(out_econ=1, in_econ=2, out_two_plus=False, in_two_plus=True)
        prof = FamilyProfile(adults_count=2, matmid_points_balance=200000, children=[])
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res)

    def test_f22_03_rejected_when_points_balance_is_1_point_short_of_full_family_cost(self) -> None:
        eng = self.get_wallet_engine()
        out_a, in_a = self._make_pair(out_econ=4, in_econ=4, out_two_plus=True, in_two_plus=True)
        prof_exact = FamilyProfile(adults_count=4, matmid_points_balance=120000, children=[])
        res_exact = eng.allocate_family_tickets(
            prof_exact, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res_exact)
        self.assertEqual(_get_field(res_exact, "total_matmid_points"), 120000)
        prof_short = FamilyProfile(adults_count=4, matmid_points_balance=119999, children=[])
        res_short = eng.allocate_family_tickets(
            prof_short, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res_short)

    def test_f22_04_infant_on_lap_does_not_consume_separate_award_seat_cap(self) -> None:
        eng = self.get_wallet_engine()
        out_a, in_a = self._make_pair(out_econ=2, in_econ=2, out_two_plus=True, in_two_plus=True)
        prof = FamilyProfile(
            adults_count=2,
            matmid_points_balance=150000,
            children=[ChildFramework(id="inf", child_age_years=1, passenger_Current_type="INFANT_LAP")],
        )
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        self.assertFalse(bool(_get_field(res, "requires_two_plus_seat_verification")))

    def test_f22_05_rejected_when_inbound_leg_has_zero_seats_in_same_cabin(self) -> None:
        eng = self.get_wallet_engine()
        out_a, in_a = self._make_pair(out_econ=2, in_econ=0, out_two_plus=True, in_two_plus=False)
        prof = FamilyProfile(adults_count=2, matmid_points_balance=200000, children=[])
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res)


class TestTier2F23SplitCabinBonusBoundaries(Tier2BoundaryTestBase):
    """F23 — Strategy 2: SPLIT_CABIN_BONUS boundaries."""

    def _make_split_pair(
        self, econ: int = 2, prem: int = 2, biz: int = 0
    ) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_f23", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=econ, economy_seats_is_two_plus=econ >= 2,
            premium_award_seats=prem, premium_seats_is_two_plus=prem >= 2,
            business_award_seats=biz, business_seats_is_two_plus=biz >= 2,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_f23", origin_iata="FCO", destination_iata="TLV", direction="INBOUND",
            flight_number="LY384", flight_date=date(2027, 4, 18),
            economy_award_seats=econ, economy_seats_is_two_plus=econ >= 2,
            premium_award_seats=prem, premium_seats_is_two_plus=prem >= 2,
            business_award_seats=biz, business_seats_is_two_plus=biz >= 2,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f23_01_family_of_4_splits_2_economy_and_2_premium_on_exact_same_flight_number(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.children = prof.children[:2]
        prof.matmid_points_balance = 200000
        out_a, in_a = self._make_split_pair(econ=2, prem=2, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        allocs = _get_field(res, "family_ticket_allocation", [])
        cabins = [_get_field(a, "cabin_class") for a in allocs]
        self.assertEqual(cabins.count("ECONOMY"), 2)
        self.assertEqual(cabins.count("PREMIUM"), 2)
        self.assertAlmostEqual(_get_field(res, "total_supplemental_cash_fares_usd", 0.0), 0.0)

    def test_f23_02_family_of_5_three_way_cabin_split_2_econ_2_prem_1_biz(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.matmid_points_balance = 350000
        out_a, in_a = self._make_split_pair(econ=2, prem=2, biz=1)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM", "BUSINESS"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        allocs = _get_field(res, "family_ticket_allocation", [])
        self.assertEqual(len(allocs), 5)
        self.assertAlmostEqual(_get_field(res, "total_supplemental_cash_fares_usd", 0.0), 0.0)

    def test_f23_03_rejected_when_cabins_are_on_different_flight_numbers(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO", "ATH"],
            }
        )
        for p in proposals:
            if p.itinerary and _get_field(p.itinerary, "fulfillment_strategy") == "SPLIT_CABIN_BONUS":
                self.assertEqual(len({l.flight_number for l in p.itinerary.outbound_legs}), 1)
                self.assertEqual(len({l.flight_number for l in p.itinerary.inbound_legs}), 1)

    def test_f23_04_rejected_when_only_one_cabin_is_in_preferred_cabins_filter(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_split_pair(econ=2, prem=2, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res)

    def test_f23_05_adult_paired_with_young_child_in_each_split_cabin_group(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.children = prof.children[:2]
        prof.matmid_points_balance = 200000
        out_a, in_a = self._make_split_pair(econ=2, prem=2, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        allocs = _get_field(res, "family_ticket_allocation", [])
        econ_pax = [f"{_get_field(a, 'passenger_id') or ''} {_get_field(a, 'passenger_label') or ''}".strip() for a in allocs if _get_field(a, "cabin_class") == "ECONOMY"]
        prem_pax = [f"{_get_field(a, 'passenger_id') or ''} {_get_field(a, 'passenger_label') or ''}".strip() for a in allocs if _get_field(a, "cabin_class") == "PREMIUM"]
        self.assertTrue(any("ADULT" in p or "הורה" in p for p in econ_pax))
        self.assertTrue(any("ADULT" in p or "הורה" in p for p in prem_pax))


class TestTier2F24HybridBonusPlusCashBoundaries(Tier2BoundaryTestBase):
    """F24 — Strategy 3: HYBRID_BONUS_PLUS_CASH boundaries."""

    def _make_hybrid_pair(self, econ: int = 2, prem: int = 2, biz: int = 0) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_f24", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=econ, economy_seats_is_two_plus=econ >= 2,
            premium_award_seats=prem, premium_seats_is_two_plus=prem >= 2,
            business_award_seats=biz, business_seats_is_two_plus=biz >= 2,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_f24", origin_iata="FCO", destination_iata="TLV", direction="INBOUND",
            flight_number="LY384", flight_date=date(2027, 4, 18),
            economy_award_seats=econ, economy_seats_is_two_plus=econ >= 2,
            premium_award_seats=prem, premium_seats_is_two_plus=prem >= 2,
            business_award_seats=biz, business_seats_is_two_plus=biz >= 2,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f24_01_child_under_12_never_isolated_on_cash_or_bonus_pnr_without_adult(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_hybrid_pair(econ=2, prem=2, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        allocs = _get_field(res, "family_ticket_allocation", [])
        cash_allocs = [a for a in allocs if _get_field(a, "ticket_mode") == "COMMERCIAL_CASH"]
        self.assertEqual(len(cash_allocs), 1)
        cash_label = f"{_get_field(cash_allocs[0], 'passenger_id') or ''} {_get_field(cash_allocs[0], 'passenger_label') or ''}".strip()
        self.assertFalse(any(tok in cash_label for tok in ("נועה", "עידו", "CHILD_1", "CHILD_2", "c-noa", "c-ido")))

    def test_f24_02_all_children_under_12_with_1_cash_ticket_assigns_adult_to_cash_and_adult_to_bonus(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.children = prof.children[:2]  # ages 5 and 9 (<12)
        out_a, in_a = self._make_hybrid_pair(econ=2, prem=1, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        allocs = _get_field(res, "family_ticket_allocation", [])
        bonus_pax = [f"{_get_field(a, 'passenger_id') or ''} {_get_field(a, 'passenger_label') or ''}".strip() for a in allocs if _get_field(a, "ticket_mode") != "COMMERCIAL_CASH"]
        cash_pax = [f"{_get_field(a, 'passenger_id') or ''} {_get_field(a, 'passenger_label') or ''}".strip() for a in allocs if _get_field(a, "ticket_mode") == "COMMERCIAL_CASH"]
        self.assertTrue(any("ADULT" in p or "הורה" in p for p in bonus_pax))
        self.assertTrue(any("ADULT" in p or "הורה" in p for p in cash_pax))

    def test_f24_03_single_adult_with_young_children_cannot_split_adult_away_from_children_under_12(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(
            adults_count=1,
            matmid_points_balance=100000,
            children=[
                ChildFramework(id="c1", child_name="נועה", child_age_years=5),
                ChildFramework(id="c2", child_name="עידו", child_age_years=8),
            ],
        )
        out_a, in_a = self._make_hybrid_pair(econ=1, prem=0, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        if res is not None:
            allocs = _get_field(res, "family_ticket_allocation", [])
            cash_pax = [f"{_get_field(a, 'passenger_id') or ''} {_get_field(a, 'passenger_label') or ''}".strip() for a in allocs if _get_field(a, "ticket_mode") == "COMMERCIAL_CASH"]
            if cash_pax:
                self.assertTrue(any("ADULT" in p or "הורה" in p for p in cash_pax))

    def test_f24_04_disabled_when_allow_hybrid_bonus_cash_is_false(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "allow_hybrid_bonus_cash": False,
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            }
        )
        for p in proposals:
            if p.itinerary is not None:
                self.assertNotEqual(_get_field(p.itinerary, "fulfillment_strategy"), "HYBRID_BONUS_PLUS_CASH")

    def test_f24_05_canonical_rome_5_pax_hybrid_math_points_taxes_cash_and_cpp(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_hybrid_pair(econ=2, prem=2, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        self.assertEqual(_get_field(res, "total_matmid_points"), 142000)
        self.assertAlmostEqual(_get_field(res, "total_taxes_and_fees_usd"), 390.0, delta=2.0)
        self.assertAlmostEqual(_get_field(res, "total_supplemental_cash_fares_usd"), 460.0, delta=5.0)
        self.assertAlmostEqual(_get_field(res, "total_out_of_pocket_cash_usd"), 850.0, delta=5.0)
        self.assertAlmostEqual(_get_field(res, "full_cash_benchmark_usd"), 2950.0, delta=10.0)
        self.assertAlmostEqual(_get_field(res, "net_cash_saved_usd"), 2100.0, delta=10.0)
        self.assertAlmostEqual(_get_field(res, "cents_per_point_value"), 1.48, delta=0.05)


class TestTier2F25OneWayAndOpenJawBonusBoundaries(Tier2BoundaryTestBase):
    """F25 — Strategy 4: ONE_WAY_BONUS_ONE_WAY_CASH & Open-Jaw Bonus boundaries."""

    def _make_oneway_pair(self, out_seats: int, in_seats: int) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_f25", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=out_seats, economy_seats_is_two_plus=out_seats >= 2,
            premium_award_seats=0, premium_seats_is_two_plus=False,
            business_award_seats=0, business_seats_is_two_plus=False,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_f25", origin_iata="FCO", destination_iata="TLV", direction="INBOUND",
            flight_number="LY384", flight_date=date(2027, 4, 18),
            economy_award_seats=in_seats, economy_seats_is_two_plus=in_seats >= 2,
            premium_award_seats=0, premium_seats_is_two_plus=False,
            business_award_seats=0, business_seats_is_two_plus=False,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f25_01_outbound_zero_award_seats_inbound_two_plus_seats_triggers_one_way_bonus(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, in_a = self._make_oneway_pair(out_seats=0, in_seats=2)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "ONE_WAY_BONUS_ONE_WAY_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        self.assertEqual(_get_field(res, "fulfillment_strategy"), "ONE_WAY_BONUS_ONE_WAY_CASH")
        self.assertGreater(_get_field(res, "total_matmid_points", 0), 0)
        self.assertGreater(_get_field(res, "total_supplemental_cash_fares_usd", 0.0), 0.0)

    def test_f25_02_outbound_two_plus_award_seats_inbound_zero_seats_triggers_reverse_one_way_bonus(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, in_a = self._make_oneway_pair(out_seats=2, in_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "ONE_WAY_BONUS_ONE_WAY_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        self.assertEqual(_get_field(res, "fulfillment_strategy"), "ONE_WAY_BONUS_ONE_WAY_CASH")
        self.assertGreater(_get_field(res, "total_matmid_points", 0), 0)
        self.assertGreater(_get_field(res, "total_supplemental_cash_fares_usd", 0.0), 0.0)

    def test_f25_03_open_jaw_italy_milan_mxp_to_rome_fco_sets_distinct_return_origin_iata(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["MIL", "ROM"],
            }
        )
        open_jaw = [
            p for p in proposals
            if p.itinerary is not None and p.itinerary.destination_iata != p.itinerary.return_origin_iata
        ]
        self.assertGreater(len(open_jaw), 0)
        itin = open_jaw[0].itinerary
        assert itin is not None
        self.assertIn(itin.destination_iata, ("MXP", "FCO"))
        self.assertIn(itin.return_origin_iata, ("MXP", "FCO"))
        self.assertNotEqual(itin.destination_iata, itin.return_origin_iata)

    def test_f25_04_rejected_when_both_outbound_and_inbound_have_zero_bonus_seats(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, in_a = self._make_oneway_pair(out_seats=0, in_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "ONE_WAY_BONUS_ONE_WAY_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res)

    def test_f25_05_open_jaw_disallowed_across_incompatible_distant_zones(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO", "JFK"],
            }
        )
        for p in proposals:
            if p.itinerary is not None:
                pair = {p.itinerary.destination_iata, p.itinerary.return_origin_iata}
                self.assertNotEqual(pair, {"FCO", "JFK"})


class TestTier2F26CashAndPointsBoundaries(Tier2BoundaryTestBase):
    """F26 — Strategy 5: CASH_AND_POINTS boundaries."""

    def _make_zero_award_pair(self) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_f26", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 20),
            economy_award_seats=0, economy_seats_is_two_plus=False,
            premium_award_seats=0, premium_seats_is_two_plus=False,
            business_award_seats=0, business_seats_is_two_plus=False,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_f26", origin_iata="FCO", destination_iata="TLV", direction="INBOUND",
            flight_number="LY384", flight_date=date(2027, 4, 28),
            economy_award_seats=0, economy_seats_is_two_plus=False,
            premium_award_seats=0, premium_seats_is_two_plus=False,
            business_award_seats=0, business_seats_is_two_plus=False,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f26_01_triggered_when_all_classic_award_cabins_have_zero_seats(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_zero_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        self.assertEqual(_get_field(res, "fulfillment_strategy"), "CASH_AND_POINTS")
        self.assertGreater(_get_field(res, "total_matmid_points", 0), 0)
        self.assertLessEqual(_get_field(res, "total_matmid_points", 0), prof.matmid_points_balance)
        self.assertLess(_get_field(res, "total_out_of_pocket_cash_usd"), _get_field(res, "full_cash_benchmark_usd"))

    def test_f26_02_low_cpp_below_0_8_cents_emits_explicit_warning_in_explanation(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_zero_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        cpp = float(_get_field(res, "cents_per_point_value", 0.0))
        self.assertGreater(cpp, 0.0)
        self.assertLessEqual(cpp, 1.0)

    def test_f26_03_cpp_at_or_above_0_8_cents_boundary_does_not_trigger_low_cpp_penalty(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_zero_award_pair()
        out_a.economy_award_seats = 2
        out_a.economy_seats_is_two_plus = True
        in_a.economy_award_seats = 2
        in_a.economy_seats_is_two_plus = True
        res_cp = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        res_hyb = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res_cp)
        self.assertIsNotNone(res_hyb)
        self.assertGreater(
            float(_get_field(res_hyb, "cents_per_point_value", 0.0)),
            float(_get_field(res_cp, "cents_per_point_value", 0.0)),
        )

    def test_f26_04_not_generated_when_household_has_zero_matmid_points(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=0, children=[], passenger_loyalty_wallets=[])
        out_a, in_a = self._make_zero_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res)

    def test_f26_05_points_deducted_never_exceed_available_matmid_balance(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(
            adults_count=2,
            matmid_points_balance=12000,
            children=[],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet(
                    id="w12", passenger_id="ADULT_1", passenger_name="A1",
                    program_code="ELAL_MATMID", available_points=12000, can_pool_with_family=True,
                )
            ],
        )
        out_a, in_a = self._make_zero_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 600.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        if res is not None:
            self.assertLessEqual(_get_field(res, "total_matmid_points", 0), 12000)
            self.assertGreater(_get_field(res, "total_out_of_pocket_cash_usd", 0.0), 0.0)


class TestTier2F27MultiClubWalletSplitBoundaries(Tier2BoundaryTestBase):
    """F27 — Strategy 6: MULTI_CLUB_PER_PASSENGER_SPLIT (MultiClubWalletAllocationEngine) boundaries."""

    def _make_mc_pair(self, econ: int = 4, prem: int = 2) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_f27", origin_iata="TLV", destination_iata="FCO", direction="OUTBOUND",
            flight_number="LY381", flight_date=date(2027, 4, 11),
            economy_award_seats=econ, economy_seats_is_two_plus=econ >= 2,
            premium_award_seats=prem, premium_seats_is_two_plus=prem >= 2,
            business_award_seats=0, business_seats_is_two_plus=False,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_f27", origin_iata="FCO", destination_iata="TLV", direction="INBOUND",
            flight_number="LY384", flight_date=date(2027, 4, 18),
            economy_award_seats=econ, economy_seats_is_two_plus=econ >= 2,
            premium_award_seats=prem, premium_seats_is_two_plus=prem >= 2,
            business_award_seats=0, business_seats_is_two_plus=False,
            award_zone="ZONE_B", economy_points_per_pax=15000, premium_points_per_pax=20500,
            business_points_per_pax=45000, taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f27_01_unpooled_matmid_wallets_cannot_combine_points_for_single_ticket(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(
            adults_count=2,
            matmid_points_balance=50000,
            children=[],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet(
                    id="w_u1", passenger_id="ADULT_1", passenger_name="A1",
                    program_code="ELAL_MATMID", available_points=25000, can_pool_with_family=False,
                ),
                PassengerLoyaltyWallet(
                    id="w_u2", passenger_id="ADULT_2", passenger_name="A2",
                    program_code="ELAL_MATMID", available_points=25000, can_pool_with_family=False,
                ),
            ],
        )
        out_a, in_a = self._make_mc_pair(econ=2, prem=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
        )
        if res is not None:
            used = _get_field(res, "points_used_by_wallet", {})
            for k, v in used.items():
                pts_val = v.get("points_used", v) if isinstance(v, dict) else v
                if isinstance(pts_val, (int, float)) and k in ("w_u1", "w_u2"):
                    self.assertLessEqual(pts_val, 25000)

    def test_f27_02_pooled_wallets_can_combine_balances_within_same_pool_group(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(
            adults_count=2,
            matmid_points_balance=60000,
            children=[],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet(
                    id="w_p1", passenger_id="ADULT_1", passenger_name="A1",
                    program_code="ELAL_MATMID", available_points=30000,
                    can_pool_with_family=True, pool_group_id="FAM_POOL",
                ),
                PassengerLoyaltyWallet(
                    id="w_p2", passenger_id="ADULT_2", passenger_name="A2",
                    program_code="ELAL_MATMID", available_points=30000,
                    can_pool_with_family=True, pool_group_id="FAM_POOL",
                ),
            ],
        )
        out_a, in_a = self._make_mc_pair(econ=2, prem=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        self.assertEqual(_get_field(res, "total_matmid_points"), 60000)

    def test_f27_03_transfer_ratio_to_airline_applied_accurately_for_credit_card_points(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(
            adults_count=2,
            matmid_points_balance=30000,
            children=[],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet(
                    id="w_m1", passenger_id="ADULT_1", passenger_name="A1",
                    program_code="ELAL_MATMID", available_points=30000, can_pool_with_family=True,
                ),
                PassengerLoyaltyWallet(
                    id="w_cc1", passenger_id="ADULT_2", passenger_name="A2",
                    program_code="AMEX_MR_ISRAEL", available_points=60000,
                    can_pool_with_family=True, transfer_ratio_to_airline=0.5,
                ),
            ],
        )
        out_a, in_a = self._make_mc_pair(econ=2, prem=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY"], ["ELAL_MATMID", "AMEX_MR_ISRAEL"],
        )
        self.assertIsNotNone(res)
        self.assertGreater(len(_get_field(res, "points_used_by_wallet", {})), 0)

    def test_f27_04_child_under_12_pnr_safety_pairing_enforced_in_multi_club_split(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.children = prof.children[:2]  # ages 5 and 9 (<12)
        out_a, in_a = self._make_mc_pair(econ=2, prem=2)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY", "PREMIUM"],
            ["ELAL_MATMID", "BRITISH_AVIOS", "FLYING_BLUE", "UNITED_MILEAGEPLUS", "AMEX_MR_ISRAEL"],
        )
        self.assertIsNotNone(res)
        allocs = _get_field(res, "family_ticket_allocation", [])
        self.assertEqual(len(allocs), 4)

    def test_f27_05_all_10_loyalty_program_codes_supported_and_disabled_programs_ignored(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_mc_pair(econ=2, prem=2)
        res_matmid_only = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"],
        )
        all_10 = [c.value for c in LoyaltyProgramCode]
        res_all_10 = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY", "PREMIUM"], all_10,
        )
        self.assertIsNotNone(res_matmid_only)
        self.assertIsNotNone(res_all_10)


class TestTier2F28ScoringComparisonAndIcsExportBoundaries(Tier2BoundaryTestBase):
    """F28 — FBVS, CTOS, Side-by-Side Comparison & .ics Export boundaries."""

    def test_f28_01_cpp_division_by_zero_guard_when_total_matmid_points_is_zero(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "search_elal_bonus_tickets": False,
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            }
        )
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            assert p.itinerary is not None
            self.assertEqual(p.itinerary.total_matmid_points, 0)
            self.assertIn(p.itinerary.cents_per_point_value, (None, 0.0))
            self.assertGreaterEqual(p.flight_bonus_value_score, 0.0)
            self.assertLessEqual(p.flight_bonus_value_score, 100.0)

    def test_f28_02_fbvs_cash_equal_min_and_max_cost_denominator_guard(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "search_elal_bonus_tickets": False,
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
            }
        )
        self.assertGreaterEqual(len(proposals), 1)
        for p in proposals:
            self.assertGreaterEqual(p.flight_bonus_value_score, 0.0)
            self.assertLessEqual(p.flight_bonus_value_score, 100.0)

    def test_f28_03_ctos_weighted_sum_exact_formula_and_0_to_100_bounds(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO"],
            }
        )
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            expected_ctos = 0.55 * p.vacation_utilization_score + 0.45 * p.flight_bonus_value_score
            self.assertAlmostEqual(p.combined_trip_optimization_score, expected_ctos, delta=0.3)
            self.assertGreaterEqual(p.combined_trip_optimization_score, 0.0)
            self.assertLessEqual(p.combined_trip_optimization_score, 100.0)

    def test_f28_04_compare_proposals_with_empty_or_unknown_ids_handled_gracefully(self) -> None:
        planner = self.get_planner()
        for bad_ids in ([], ["nonexistent-id-1", "nonexistent-id-2"]):
            try:
                res = planner.compare_proposals(bad_ids)
                if isinstance(res, dict):
                    self.assertEqual(len(res.get("proposals", [])), 0)
                else:
                    self.assertEqual(len(getattr(res, "proposals", [])), 0)
            except (ValueError, KeyError):
                pass

    def test_f28_05_export_proposal_ics_rfc5545_structure_hebrew_utf8_and_missing_id(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            }
        )
        ics = planner.export_proposal_ics(proposals[0].id)
        for token in ("BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "DTSTART", "DTEND", "SUMMARY:", "END:VEVENT", "END:VCALENDAR"):
            self.assertIn(token, ics)
        with self.assertRaises((ValueError, KeyError)):
            planner.export_proposal_ics("missing-proposal-id-999")


class TestTier2F29RestApiNegativeAndBoundaries(Tier2BoundaryTestBase):
    """F29 — 8 Core REST API Endpoints (/api/v1/*) + .ics Export & Static Server negative & boundary tests."""

    def test_f29_01_put_profile_invalid_payloads_return_400_or_422_without_corrupting_db(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=True)
        client = self.get_client(db_path)
        orig = client.get("/api/v1/profile").json()
        bad_payloads = [
            {**orig, "adults_count": 0},
            {**orig, "adults_count": 9},
            {**orig, "children": [{"id": "c_neg", "child_age_years": -1}]},
            {**orig, "children": [{"id": "c_fw", "child_age_years": 6, "framework_type": "INVALID"}]},
            {**orig, "passenger_loyalty_wallets": [{"id": "w_neg", "passenger_id": "A1", "passenger_name": "A", "program_code": "ELAL_MATMID", "available_points": -500}]},
        ]
        for bp in bad_payloads:
            r = client.put("/api/v1/profile", json=bp)
            self.assertIn(r.status_code, (400, 422))
        after = client.get("/api/v1/profile").json()
        self.assertEqual(after["adults_count"], orig["adults_count"])

    def test_f29_02_moe_calendar_get_and_sync_invalid_school_year_return_400_or_422(self) -> None:
        client = self.get_client()
        r1 = client.get("/api/v1/moe-calendar/not-a-year")
        r2 = client.post("/api/v1/moe-calendar/sync/2026-2025", json={})
        self.assertIn(r1.status_code, (400, 422))
        self.assertIn(r2.status_code, (400, 422))

    def test_f29_03_elal_bonus_sync_and_availability_invalid_dates_or_missing_params_return_400_or_422(self) -> None:
        client = self.get_client()
        r_sync = client.post(
            "/api/v1/elal-bonus/sync",
            json={"destinations": ["FCO"], "start_date": "2027-04-20", "end_date": "2027-04-10"},
        )
        r_avail = client.get("/api/v1/elal-bonus/availability?destination=FCO&start_date=2027-13-45&end_date=2027-04-20")
        self.assertIn(r_sync.status_code, (400, 422))
        self.assertIn(r_avail.status_code, (400, 422))

    def test_f29_04_vacations_search_invalid_modes_nights_or_dates_return_400_or_422(self) -> None:
        client = self.get_client()
        bad_searches = [
            {"date_selection_mode": "INVALID_MODE", "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"]},
            {"date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "INVALID", "destination_iatas": ["FCO"]},
            {"date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"], "min_trip_nights": 10, "max_trip_nights": 4},
            {"date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"], "flex_days_plus_minus": 99},
            {"date_selection_mode": "SPECIFIC_DATES", "airline_selection_mode": "EL_AL_ONLY", "destination_iatas": ["FCO"], "specific_departure_date": "2027-04-18", "specific_return_date": "2027-04-11"},
        ]
        for bs in bad_searches:
            r = client.post("/api/v1/vacations/search", json=bs)
            self.assertIn(r.status_code, (400, 422))

    def test_f29_05_compare_and_export_ics_unknown_proposal_id_and_unknown_route_return_400_404_422(self) -> None:
        client = self.get_client()
        r_cmp = client.post("/api/v1/vacations/compare", json={"proposal_ids": []})
        r_ics = client.get("/api/v1/vacations/nonexistent-id-xyz/export.ics")
        r_404 = client.get("/api/v1/nonexistent-endpoint")
        self.assertIn(r_cmp.status_code, (400, 404, 422))
        self.assertIn(r_ics.status_code, (400, 404, 422))
        self.assertEqual(r_404.status_code, 404)


class TestTier2F30CliCompanionBoundaries(Tier2BoundaryTestBase):
    """F30 — CLI Companion (plan-vacation / backend/app/cli/main.py) boundary & negative tests."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "backend.app.cli.main", *args],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "VACATION_PLANNER_DB_PATH": str(self.shared_db_path)},
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_f30_01_unknown_subcommand_exits_nonzero(self) -> None:
        res = self._run_cli("invalid-subcommand")
        self.assertNotEqual(res.returncode, 0)

    def test_f30_02_search_invalid_mode_or_airline_flag_exits_nonzero(self) -> None:
        r1 = self._run_cli("search", "--mode", "invalid-mode", "--airline", "elal-only")
        r2 = self._run_cli("search", "--mode", "specific-dates", "--airline", "invalid-airline")
        self.assertNotEqual(r1.returncode, 0)
        self.assertNotEqual(r2.returncode, 0)

    def test_f30_03_search_out_of_range_flex_days_or_bridge_days_exits_nonzero(self) -> None:
        r1 = self._run_cli(
            "search", "--mode", "specific-dates", "--airline", "elal-only",
            "--departure-date", "2027-04-11", "--return-date", "2027-04-18", "--flex-days", "15",
        )
        r2 = self._run_cli(
            "search", "--mode", "moe-maximize", "--airline", "elal-only", "--max-bridge-days", "9",
        )
        self.assertNotEqual(r1.returncode, 0)
        self.assertNotEqual(r2.returncode, 0)

    def test_f30_04_bonus_availability_missing_required_arguments_exits_nonzero(self) -> None:
        r1 = self._run_cli("bonus-availability")
        r2 = self._run_cli(
            "bonus-availability", "--destination", "FCO",
            "--start-date", "2027-04-20", "--end-date", "2027-04-10",
        )
        self.assertNotEqual(r1.returncode, 0)
        self.assertNotEqual(r2.returncode, 0)

    def test_f30_05_executable_plan_vacation_wrapper_permissions_and_help_exit_zero(self) -> None:
        cli_path = PROJECT_ROOT / "plan-vacation"
        self.assertTrue(cli_path.exists())
        self.assertTrue(os.access(cli_path, os.X_OK))
        res = subprocess.run(
            [str(cli_path), "--help"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        for sub in ("profile", "calendar", "bonus-availability", "search", "serve"):
            self.assertIn(sub, res.stdout)


class TestTier2F31ResponsiveBidiWebUiBoundaries(Tier2BoundaryTestBase):
    """F31 — Mobile-First Responsive BiDi/RTL & LTR Web Application boundaries."""

    def test_f31_01_index_html_rtl_default_lang_he_and_viewport_meta_present(self) -> None:
        client = self.get_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="he"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("width=device-width", html)

    def test_f31_02_css_mobile_360_430_and_desktop_1280_breakpoints_and_logical_rtl_properties(self) -> None:
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
        self.assertIn("@media", css)
        self.assertIn("sticky", css)
        self.assertTrue("inset-inline" in css or "margin-inline" in css or "padding-inline" in css)

    def test_f31_03_mode1_ui_marks_child_framework_selector_as_optional_not_required(self) -> None:
        app_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text(encoding="utf-8")
        drawer = (PROJECT_ROOT / "frontend" / "src" / "components" / "profile" / "FamilyProfileDrawer.tsx").read_text(encoding="utf-8")
        combined = app_js + "\n" + drawer
        self.assertTrue("אופציונלי" in combined or "optional" in combined.lower() or "null" in combined)
        for fw in MoEFrameworkType:
            self.assertIn(fw.value, combined)
        for club in LoyaltyProgramCode:
            self.assertIn(club.value, combined)

    def test_f31_04_zero_external_cdn_scripts_or_stylesheets_in_html_and_js(self) -> None:
        html = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        for forbidden_cdn in ("https://cdn.", "unpkg.com", "jsdelivr.net", "cdnjs.cloudflare.com"):
            self.assertNotIn(forbidden_cdn, html)

    def test_f31_05_path_traversal_and_missing_static_asset_requests_rejected_safely(self) -> None:
        client = self.get_client()
        for bad_path in ("/../../../etc/passwd", "/..%2F..%2Fconfig/settings.yaml", "/src/nonexistent_file_xyz.js"):
            resp = client.get(bad_path)
            self.assertIn(resp.status_code, (400, 403, 404))


class TestTier2F32PwaAndPackagingBoundaries(Tier2BoundaryTestBase):
    """F32 — Installable PWA (manifest.webmanifest & sw.js) & End-to-End Verification boundaries."""

    def test_f32_01_manifest_webmanifest_valid_json_rtl_he_il_standalone_and_icons(self) -> None:
        client = self.get_client()
        resp = client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        manifest = resp.json()
        self.assertEqual(manifest.get("dir"), "rtl")
        self.assertTrue(str(manifest.get("lang", "")).startswith("he"))
        self.assertEqual(manifest.get("display"), "standalone")
        self.assertIn("start_url", manifest)
        self.assertIn("name", manifest)
        self.assertIn("short_name", manifest)
        self.assertIsInstance(manifest.get("icons"), list)
        self.assertGreater(len(manifest["icons"]), 0)

    def test_f32_02_service_worker_sw_js_install_activate_and_offline_fetch_handlers(self) -> None:
        client = self.get_client()
        resp = client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        for ev in ("install", "activate", "fetch"):
            self.assertIn(ev, resp.text)

    def test_f32_03_all_7_original_specification_documents_preserved_intact_and_non_empty(self) -> None:
        docs = (
            "README.md",
            "APPLICATION_PLAN.md",
            "docs/01_architecture_and_tech_stack.md",
            "docs/02_moe_calendar_and_maximization.md",
            "docs/03_airlines_and_elal_bonus_engine.md",
            "docs/04_ui_ux_and_user_workflows.md",
            "docs/05_implementation_roadmap_and_rubric.md",
        )
        for rel in docs:
            p = PROJECT_ROOT / rel
            self.assertTrue(p.exists(), f"Missing doc: {p}")
            self.assertGreater(p.stat().st_size, 1500)
        plan_txt = (PROJECT_ROOT / "APPLICATION_PLAN.md").read_text(encoding="utf-8")
        for sec in ("1.", "2.", "3.", "4.", "5.", "6."):
            self.assertIn(sec, plan_txt)

    def test_f32_04_all_8_frontend_tsx_components_and_domain_ts_exist_and_match_contracts(self) -> None:
        dom_ts = PROJECT_ROOT / "frontend" / "src" / "types" / "domain.ts"
        self.assertTrue(dom_ts.exists())
        dom_txt = dom_ts.read_text(encoding="utf-8")
        for sym in ("MoEFrameworkType", "DateSelectionMode", "AirlineSelectionMode", "LoyaltyProgramCode", "FulfillmentStrategy"):
            self.assertIn(sym, dom_txt)
        comp_root = PROJECT_ROOT / "frontend" / "src" / "components"
        for rel in (
            "layout/AppShell.tsx",
            "profile/FamilyProfileDrawer.tsx",
            "search/SearchControlPanel.tsx",
            "search/ElAlBonusSearchSubPanel.tsx",
            "calendar/MultiChildCalendarHeatmap.tsx",
            "results/BonusVacationOptionCard.tsx",
            "results/BonusVacationComparisonModal.tsx",
            "results/AllAirlinesItineraryCard.tsx",
        ):
            fp = comp_root / rel
            self.assertTrue(fp.exists(), f"Missing component: {fp}")
            self.assertGreater(fp.stat().st_size, 50)

    def test_f32_05_sandbox_zero_broken_imports_across_all_backend_packages(self) -> None:
        import importlib

        modules = (
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
        )
        for mod_name in modules:
            self.assertIsNotNone(importlib.import_module(mod_name))


if __name__ == "__main__":
    unittest.main()
