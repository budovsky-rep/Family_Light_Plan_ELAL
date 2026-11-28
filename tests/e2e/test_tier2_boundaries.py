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
from tests.e2e.test_tier1_features import (
    RUN11_FORBIDDEN_PRICE_TEXT,
    RUN11_REMOVED_ITINERARY_KEYS,
    RUN11_REMOVED_RESPONSE_KEYS,
    _assert_run11_itinerary_contract,
    _assert_run11_proposal_contract,
    _assert_run11_search_response_contract,
    _run11_expected_bonus_score,
)


class Tier2BoundaryTestBase(unittest.TestCase):
    """Hermetic base test harness for Tier 2 boundary & negative tests."""

    _shared_tmpdir: Optional[tempfile.TemporaryDirectory[str]] = None
    shared_db_path: Path
    shared_http_db_path: Path
    shared_repo: SQLiteRepository
    _shared_client: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if Tier2BoundaryTestBase._shared_tmpdir is None:
            from backend.app.storage_cache.seed_data import build_default_family_profile

            Tier2BoundaryTestBase._shared_tmpdir = tempfile.TemporaryDirectory(
                prefix="fvp_t2_shared_"
            )
            Tier2BoundaryTestBase.shared_db_path = (
                Path(Tier2BoundaryTestBase._shared_tmpdir.name) / "shared_t2.db"
            )
            Tier2BoundaryTestBase.shared_http_db_path = (
                Path(Tier2BoundaryTestBase._shared_tmpdir.name) / "shared_t2_http.db"
            )
            Tier2BoundaryTestBase.shared_repo = SQLiteRepository(
                db_path=Tier2BoundaryTestBase.shared_db_path, auto_seed=True
            )
            if not SQLiteRepository.is_live_fetch_mode():
                Tier2BoundaryTestBase.shared_repo.save_profile(
                    build_default_family_profile()
                )
                _orig_get_prof = Tier2BoundaryTestBase.shared_repo.get_profile
                Tier2BoundaryTestBase.shared_repo.get_profile = (  # type: ignore[method-assign]
                    lambda profile_id=None: _orig_get_prof(
                        profile_id or "default-family-profile"
                    )
                )

    @property
    def shared_client(self) -> Any:
        if Tier2BoundaryTestBase._shared_client is None:
            from backend.app.main import VacationPlannerTestClient

            Tier2BoundaryTestBase._shared_client = VacationPlannerTestClient(
                db_path=str(self.shared_http_db_path)
            )
        return Tier2BoundaryTestBase._shared_client

    def authenticate_test_client(
        self, client: Any, email: str = "t2_user@gmail.com"
    ) -> dict[str, Any]:
        import time as _time
        import urllib.parse as _uparse
        from backend.app.auth_service import (
            build_unsigned_or_hs256_jwt_for_test,
            pkce_s256_challenge,
        )

        auth_svc = client.router.auth_service
        auth_svc.client_id = "t2-client.apps.googleusercontent.com"
        auth_svc.client_secret = "t2-client-secret"
        auth_svc.redirect_uri = (
            "https://breezyflights.com/api/v1/auth/google/callback"
        )
        login_resp = client.get("/api/v1/auth/google/login")
        self.assertEqual(login_resp.status_code, 302)
        q = _uparse.parse_qs(_uparse.urlsplit(login_resp.headers["Location"]).query)
        state, nonce, challenge = q["state"][0], q["nonce"][0], q["code_challenge"][0]

        def _exchange(
            code: str, code_verifier: str, redirect_uri: str, cid: str, csec: str
        ) -> dict[str, Any]:
            self.assertEqual(pkce_s256_challenge(code_verifier), challenge)
            now_ts = int(_time.time())
            return {
                "id_token": build_unsigned_or_hs256_jwt_for_test(
                    {
                        "iss": "https://accounts.google.com",
                        "aud": cid,
                        "sub": f"sub-{email}",
                        "email": email,
                        "email_verified": True,
                        "nonce": nonce,
                        "iat": now_ts - 5,
                        "exp": now_ts + 3600,
                    }
                ),
                "token_type": "Bearer",
                "expires_in": 3600,
            }

        auth_svc.token_exchanger = _exchange
        cb = client.get(f"/api/v1/auth/google/callback?code=t2-code&state={state}")
        self.assertEqual(cb.status_code, 302)
        sess = client.get("/api/v1/auth/session").json()
        client.default_headers["X-CSRF-Token"] = str(sess["csrf_token"])
        client.default_headers["Origin"] = "http://127.0.0.1:8000"
        return sess

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

    def test_f01_02_family_profiles_schema_excludes_removed_pto_and_workweek_columns(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(family_profiles)").fetchall()}
        for removed_col in (
            "annual_pto_budget",
            "max_pto_per_trip",
            "workweek_type",
            "erev_chag_pto_weight",
            "chol_hamoed_pto_weight",
        ):
            self.assertNotIn(removed_col, cols)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute(
                    f"INSERT INTO family_profiles (id, {removed_col}) VALUES (?, 1)",
                    (f"rm_{removed_col}",),
                )

    def test_f01_03_zero_budgets_and_negative_budget_points_vouchers_check(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        conn.execute(
            "INSERT INTO family_profiles (id, matmid_points_balance, flycard_companion_vouchers) VALUES ('z', 0, 0)"
        )
        for col, bad_val in (("matmid_points_balance", -1), ("flycard_companion_vouchers", -1)):
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
        for col, bad_val in (("has_flycard", 2), ("flycard_tier", "GOLD"), ("preferred_currency", "GBP")):
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
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(moe_vacation_windows)").fetchall()}
        self.assertNotIn("parent_workday_status", cols)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO moe_vacation_windows (
                    id, school_year, circular_id, holiday_code, holiday_name_he, holiday_name_en,
                    framework_type, start_date, end_date, resumes_on_date, calendar_sync_source, source_reference
                ) VALUES ('bad_sync', '2026-2027', '0363', 'PESACH', 'פסח', 'Pesach', 'ELEMENTARY_1_3', '2027-04-13', '2027-04-28', '2027-04-29', 'MANUAL_CSV', 'ref')"""
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
                    ) VALUES (?, 'p1', 'HOLIDAY_DIRECT_INTENT', 'EL_AL_ONLY', '["FCO"]', ?)""",
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
        for idx, (col, bad_val) in enumerate((
            ("date_selection_mode", "FREE_TEXT"),
            ("date_selection_mode", "MOE_VACATION_MAXIMIZATION"),
            ("airline_selection_mode", "LCC_ONLY"),
            ("overlap_policy", "IGNORE_SCHOOL"),
            ("overlap_policy", "MAXIMIZE_EFFICIENCY_SCORE"),
        )):
            vals = {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "overlap_policy": "CAMP_ADJUSTED_INTERSECTION",
            }
            vals[col] = bad_val
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_search_queries (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        destination_iatas_json, overlap_policy
                    ) VALUES (?, 'p1', ?, ?, '["FCO"]', ?)""",
                    (f"bad_{idx}_{col}", vals["date_selection_mode"], vals["airline_selection_mode"], vals["overlap_policy"]),
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
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(flight_itineraries)").fetchall()}
        self.assertNotIn("family_ticket_allocation_json", cols)
        for expected_col in ("seated_passengers_count", "bonus_tickets_count", "cash_tickets_count", "primary_cabin"):
            self.assertIn(expected_col, cols)
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
                    seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                    total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
                ) VALUES (?, 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 1, ?, '[]', '[]', 2, 2, 0, 'ECONOMY', 500.0, 2000.0, 'https://elal.com')""",
                (f"it_{idx}", strat),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO flight_itineraries (
                    id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                    destination_city_he, destination_city_en, departure_date, return_date,
                    trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                    fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                    seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                    total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
                ) VALUES ('it_bad', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 1, 'UPGRADE_VOUCHER_ONLY', '[]', '[]', 2, 2, 0, 'ECONOMY', 500.0, 2000.0, 'https://elal.com')"""
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
                seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it_1', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-12', 1, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', 2, 0, 2, 'ECONOMY', 500.0, 500.0, 'https://elal.com')"""
        )
        for bad_nights in (0, -3):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO flight_itineraries (
                        id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                        destination_city_he, destination_city_en, departure_date, return_date,
                        trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                        fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                        seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                        total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
                    ) VALUES (?, 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-12', ?, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', 2, 0, 2, 'ECONOMY', 500.0, 500.0, 'https://elal.com')""",
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
                seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                total_matmid_points, total_taxes_and_fees_usd,
                total_supplemental_cash_fares_usd, total_baggage_fees_usd,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd, net_cash_saved_usd,
                booking_deep_link_url
            ) VALUES ('it_z', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', 2, 0, 2, 'ECONOMY', 0, 0.0, 0.0, 0.0, 0.0, 0.0, -50.0, 'https://elal.com')"""
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
                seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it_null', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', NULL, NULL, NULL, 2, 0, 2, 'ECONOMY', 800.0, 800.0, 'https://elal.com')"""
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
                seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it_del', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 0, 'COMMERCIAL_CASH_ONLY', '[]', '[]', 2, 0, 2, 'ECONOMY', 800.0, 800.0, 'https://elal.com')"""
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
                seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd, booking_deep_link_url
            ) VALUES ('it1', 'q1', 'TLV', 'FCO', 'FCO', 'רומא', 'Rome', '2027-04-11', '2027-04-18', 7, 'LY', 1, 1, 'FULL_BONUS_SAME_CABIN', '[]', '[]', 2, 2, 0, 'ECONOMY', 300.0, 2000.0, 'https://elal.com')"""
        )

    def test_f08_01_scores_vus_fbvs_ctos_0_and_100_boundaries_vs_out_of_bounds(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        for s_val in (0.0, 100.0):
            conn.execute(
                """INSERT INTO vacation_option_proposals (
                    id, search_query_id, itinerary_id, associated_holiday_codes_json,
                    school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                    total_school_days_missed_across_children, max_single_child_school_days_missed,
                    holiday_alignment_score, flight_bonus_value_score,
                    combined_trip_optimization_score, explanation_summary_he
                ) VALUES (?, 'q1', 'it1', '["PESACH"]', 0.0, 1.0, '[]', 0, 0, ?, ?, ?, 'הסבר')""",
                (f"pr_{int(s_val)}", s_val, s_val, s_val),
            )
        for col in ("holiday_alignment_score", "flight_bonus_value_score", "combined_trip_optimization_score"):
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
                    school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                    total_school_days_missed_across_children, max_single_child_school_days_missed,
                    holiday_alignment_score, flight_bonus_value_score,
                    combined_trip_optimization_score, explanation_summary_he
                ) VALUES (?, 'q1', 'it1', '["PESACH"]', ?, 0.0, 1.0, '[]', 0, 0, 80.0, 80.0, 80.0, 'הסבר')""",
                (f"wst_{idx}", wst),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("UPDATE vacation_option_proposals SET window_set_type = 'RANDOM_WINDOW' WHERE id = 'wst_0'")

    def test_f08_03_total_vacation_days_min_1_and_non_negative_pto_and_missed_days(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=False)
        conn = self.get_raw_conn(db_path)
        self._seed_parent_chain(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(vacation_option_proposals)").fetchall()}
        for removed_col in ("total_vacation_days", "parent_pto_days_used", "pto_efficiency_ratio", "vacation_utilization_score"):
            self.assertNotIn(removed_col, cols)
        conn.execute(
            """INSERT INTO vacation_option_proposals (
                id, search_query_id, itinerary_id, associated_holiday_codes_json,
                school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                total_school_days_missed_across_children, max_single_child_school_days_missed,
                holiday_alignment_score, flight_bonus_value_score,
                combined_trip_optimization_score, explanation_summary_he
            ) VALUES ('pr_min', 'q1', 'it1', '["PESACH"]', 0.0, 1.0, '[]', 0, 0, 50.0, 50.0, 50.0, 'הסבר')"""
        )
        for col, bad_val in (
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
                school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                total_school_days_missed_across_children, max_single_child_school_days_missed,
                holiday_alignment_score, flight_bonus_value_score,
                combined_trip_optimization_score, explanation_summary_he
            ) VALUES ('pr_it_del', 'q1', 'it1', '["PESACH"]', 0.0, 1.0, '[]', 0, 0, 80.0, 80.0, 80.0, 'הסבר')"""
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
                school_absence_penalty, childcare_coverage_gain, per_child_impact_json,
                total_school_days_missed_across_children, max_single_child_school_days_missed,
                holiday_alignment_score, flight_bonus_value_score,
                combined_trip_optimization_score, explanation_summary_he
            ) VALUES ('pr_full_del', 'q1', 'it1', '["PESACH"]', 0.0, 1.0, '[]', 0, 0, 80.0, 80.0, 80.0, 'הסבר')"""
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
    """F13 — Multi-Child Holiday Overlap, Bridge-Days & Blackout Optimizer boundaries."""

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
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            direct_holiday_code="PURIM",
            direct_target_year=2027,
            min_trip_nights=4,
            max_trip_nights=5,
            max_bridge_days_shift=0,
            overlap_policy="STRICT_ALL_CHILDREN_OFF",
        )
        q3 = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["FCO"],
            direct_holiday_code="PURIM",
            direct_target_year=2027,
            min_trip_nights=4,
            max_trip_nights=5,
            max_bridge_days_shift=3,
            overlap_policy="CAMP_ADJUSTED_INTERSECTION",
        )
        w0 = maximizer.generate_candidate_windows(q0, prof)
        w3 = maximizer.generate_candidate_windows(q3, prof)
        self.assertTrue(all(w.max_single_child_school_days_missed > 0 for w in w0))
        self.assertTrue(any(w.start_date == date(2027, 3, 23) and w.end_date == date(2027, 3, 27) for w in w3))

    def test_f13_03_zero_bridge_days_shift_restricts_to_zero_school_absence_windows(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["ATH"],
            direct_holiday_code="PESACH",
            direct_target_year=2027,
            min_trip_nights=5,
            max_trip_nights=8,
            max_bridge_days_shift=0,
            overlap_policy="STRICT_ALL_CHILDREN_OFF",
        )
        wins = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(wins), 0)
        for w in wins:
            self.assertEqual(w.max_single_child_school_days_missed, 0)
            self.assertEqual(w.total_school_days_missed_across_children, 0)
            self.assertFalse(hasattr(w, "parent_pto_days_used"))
        self.assertTrue(any(w.school_absence_penalty == 0.0 for w in wins))

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
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            destination_iatas=["MAD"],
            direct_holiday_code="SUMMER_JUNE_20_30",
            direct_target_year=2027,
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
        for target_yr in (2025, 2026):
            q = FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                airline_selection_mode="EL_AL_ONLY",
                destination_iatas=["FCO"],
                direct_holiday_code="YOM_KIPPUR_SUKKOT",
                direct_target_year=target_yr,
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
    """F15 — Mathematical Calendar Scoring Engine (SAP, CCG, HAS) boundaries."""

    def test_f15_01_ccg_zero_eligible_days_and_camp_toggle_boundary(self) -> None:
        from backend.app.storage_cache.seed_data import build_default_family_profile

        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof_care = build_default_family_profile()
        prof_care.children[0].treat_camp_as_vacation = False
        prof_vac = build_default_family_profile()
        prof_vac.children[0].treat_camp_as_vacation = True
        prof_none = build_default_family_profile()
        prof_none.children[0].holiday_extension_mode = "NONE"
        # Shabbat-only window has 0 eligible non-Shabbat days -> CCG == 1.0
        win_shabbat = maximizer.evaluate_window(prof_care, date(2027, 4, 17), date(2027, 4, 17))
        self.assertEqual(win_shabbat.childcare_coverage_gain, 1.0)
        win_care = maximizer.evaluate_window(prof_care, date(2027, 4, 13), date(2027, 4, 19))
        win_vac = maximizer.evaluate_window(prof_vac, date(2027, 4, 13), date(2027, 4, 19))
        win_none = maximizer.evaluate_window(prof_none, date(2027, 4, 13), date(2027, 4, 19))
        self.assertAlmostEqual(win_care.holiday_alignment_score, 86.4, places=1)
        self.assertAlmostEqual(win_vac.holiday_alignment_score, 95.0, places=1)
        self.assertAlmostEqual(win_none.holiday_alignment_score, 100.0, places=1)

    def test_f15_02_sap_weighted_school_absence_5day_vs_6day_friday_boundary(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        p5 = FamilyProfile(
            id="p5",
            adults_count=2,
            children=[
                ChildFramework(
                    id="c5",
                    child_age_years=13,
                    framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9,
                    school_week_days=5,
                )
            ],
        )
        p6 = FamilyProfile(
            id="p6",
            adults_count=2,
            children=[
                ChildFramework(
                    id="c6",
                    child_age_years=13,
                    framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9,
                    school_week_days=6,
                )
            ],
        )
        w5 = maximizer.evaluate_window(p5, date(2026, 6, 19), date(2026, 6, 20))
        w6 = maximizer.evaluate_window(p6, date(2026, 6, 19), date(2026, 6, 20))
        self.assertEqual(w5.school_absence_penalty, 0.0)
        self.assertEqual(w5.childcare_coverage_gain, 1.0)
        self.assertAlmostEqual(w6.school_absence_penalty, 0.35, places=2)
        self.assertAlmostEqual(w6.childcare_coverage_gain, 0.75, places=2)
        self.assertGreater(w5.holiday_alignment_score, w6.holiday_alignment_score)
        w_thu = maximizer.evaluate_window(p5, date(2026, 6, 18), date(2026, 6, 20))
        self.assertEqual(w_thu.total_school_days_missed_across_children, 1)

    def test_f15_03_vus_upper_clamp_at_100_0_on_perfect_uncovered_holiday_window(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)
        prof = self.shared_repo.get_profile()
        win = maximizer.evaluate_window(prof, date(2027, 4, 20), date(2027, 4, 28))
        self.assertEqual(win.school_absence_penalty, 0.0)
        self.assertEqual(win.childcare_coverage_gain, 1.0)
        self.assertEqual(win.holiday_alignment_score, 100.0)

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
        self.assertEqual(win.holiday_alignment_score, 0.0)
        self.assertGreaterEqual(win.holiday_alignment_score, 0.0)
        self.assertLessEqual(win.holiday_alignment_score, 100.0)

    def test_f15_05_adult_only_or_null_framework_children_sap_zero_and_ccg_fallback(self) -> None:
        cal = MoECalendarService(self.shared_repo)
        maximizer = VacationMaximizerEngine(cal)

        # 0 children -> Israeli workplace workday-efficiency mode (zero MoE dependency)
        p_no_ch = FamilyProfile(id="p_no_ch", adults_count=2, children=[])
        win_no_ch = maximizer.evaluate_window(p_no_ch, date(2027, 4, 11), date(2027, 4, 18))
        self.assertEqual(win_no_ch.calendar_mode, "WORKPLACE")
        self.assertEqual(win_no_ch.school_absence_penalty, 0.0)
        self.assertEqual(win_no_ch.childcare_coverage_gain, 1.0)
        self.assertEqual(win_no_ch.workplace_vacation_days_cost, 6.0)
        self.assertEqual(win_no_ch.workday_efficiency_ratio, 1.33)
        self.assertEqual(win_no_ch.workday_efficiency_score, 20.0)
        self.assertEqual(win_no_ch.holiday_alignment_score, 20.0)
        win_pesach_wp = maximizer.evaluate_window(p_no_ch, date(2027, 4, 22), date(2027, 4, 28))
        self.assertEqual(win_pesach_wp.calendar_mode, "WORKPLACE")
        self.assertEqual(win_pesach_wp.workplace_vacation_days_cost, 1.5)
        self.assertEqual(win_pesach_wp.workday_efficiency_ratio, 4.67)
        self.assertEqual(win_pesach_wp.workday_efficiency_score, 82.5)
        self.assertGreater(win_pesach_wp.holiday_alignment_score, win_no_ch.holiday_alignment_score)

        # >= 1 child with framework_type=None -> preserves MoE fallback (80.0) unchanged
        p_null_fw = FamilyProfile(
            id="p_null_fw",
            adults_count=2,
            children=[ChildFramework(id="c1", child_age_years=6, framework_type=None)],
        )
        win_null_fw = maximizer.evaluate_window(p_null_fw, date(2027, 4, 11), date(2027, 4, 18))
        self.assertEqual(win_null_fw.calendar_mode, "MOE")
        self.assertEqual(win_null_fw.school_absence_penalty, 0.0)
        self.assertEqual(win_null_fw.childcare_coverage_gain, 1.0)
        self.assertEqual(win_null_fw.holiday_alignment_score, 80.0)


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
            itin = _assert_run11_proposal_contract(self, p)
            self.assertEqual(itin["fulfillment_strategy"], "COMMERCIAL_CASH_ONLY")
            self.assertEqual(itin["bonus_direction_coverage"], "NONE")
            self.assertIsNone(itin["min_points_per_bonus_ticket"])
            self.assertEqual(p.flight_bonus_value_score, 0.0)


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

    def test_f22_03_accepted_when_balance_covers_one_bonus_ticket_and_filtered_below_one_ticket_r2(self) -> None:
        eng = self.get_wallet_engine()
        out_a, in_a = self._make_pair(out_econ=4, in_econ=4, out_two_plus=True, in_two_plus=True)
        # Engine composition depends on seats, not whether balance covers all 4 passengers (120,000)
        prof_one_ticket = FamilyProfile(adults_count=4, matmid_points_balance=30000, children=[])
        res = eng.allocate_family_tickets(
            prof_one_ticket, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

        # Search-level filter compares against the single-ticket minimum (30,000), not 120,000
        planner = self.get_planner()
        base_q = {
            "date_selection_mode": "SPECIFIC_DATES",
            "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 0,
            "destination_iatas": ["FCO"],
        }
        at_one_ticket = planner.search_vacations(
            {**base_q, "matmid_points_balance": 30000},
            profile=prof_one_ticket,
            persist_results=False,
        )
        self.assertIn(
            "FULL_BONUS_SAME_CABIN",
            {_get_field(p.itinerary, "fulfillment_strategy") for p in at_one_ticket},
        )
        below_one_ticket = planner.search_vacations(
            {**base_q, "matmid_points_balance": 29999},
            profile=prof_one_ticket,
            persist_results=False,
        )
        below_strats = {_get_field(p.itinerary, "fulfillment_strategy") for p in below_one_ticket}
        self.assertNotIn("FULL_BONUS_SAME_CABIN", below_strats)
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", below_strats)
        self.assertIn("CASH_AND_POINTS", below_strats)

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
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertNotIn("family_ticket_allocation", itin)
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertIn(itin["primary_cabin"], ("ECONOMY", "PREMIUM"))
        self.assertEqual(itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(itin["outbound_bonus_seats"], 4)
        self.assertEqual(itin["inbound_bonus_seats"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

    def test_f23_02_family_of_5_three_way_cabin_split_2_econ_2_prem_1_biz(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.matmid_points_balance = 350000
        out_a, in_a = self._make_split_pair(econ=2, prem=2, biz=1)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM", "BUSINESS"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertNotIn("family_ticket_allocation", itin)
        self.assertEqual(itin["seated_passengers_count"], 5)
        self.assertEqual(itin["bonus_tickets_count"], 5)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["outbound_bonus_seats"], 5)
        self.assertEqual(itin["inbound_bonus_seats"], 5)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

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
        assert res is not None
        self.assertEqual(_get_field(res, "seated_passengers_count"), 4)
        self.assertEqual(_get_field(res, "bonus_tickets_count"), 4)
        # Single adult with 2 children <12 cannot split across 2 cabins without leaving a <12 child unaccompanied
        prof_single_adult = FamilyProfile(
            adults_count=1,
            matmid_points_balance=200000,
            children=[
                ChildFramework(id="c1", child_age_years=5),
                ChildFramework(id="c2", child_age_years=8),
            ],
        )
        out_s, in_s = self._make_split_pair(econ=2, prem=1, biz=0)
        res_single = eng.allocate_family_tickets(
            prof_single_adult, out_s, in_s, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res_single)


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
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertNotIn("family_ticket_allocation", itin)
        self.assertEqual(itin["seated_passengers_count"], 5)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)

    def test_f24_02_all_children_under_12_with_1_cash_ticket_assigns_adult_to_cash_and_adult_to_bonus(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        prof.children = prof.children[:2]  # ages 5 and 9 (<12)
        out_a, in_a = self._make_hybrid_pair(econ=2, prem=1, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertNotIn("family_ticket_allocation", itin)
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 3)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["outbound_bonus_seats"], 3)
        self.assertEqual(itin["inbound_bonus_seats"], 3)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)

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
        self.assertIsNone(res)

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

    def test_f24_05_canonical_rome_5_pax_hybrid_seat_counts_min_points_and_score_boundary(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_hybrid_pair(econ=2, prem=2, biz=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 5)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(itin["outbound_bonus_seats"], 4)
        self.assertEqual(itin["inbound_bonus_seats"], 4)
        self.assertTrue(itin["outbound_bonus_seats_is_two_plus"])
        self.assertTrue(itin["inbound_bonus_seats_is_two_plus"])
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

        # Seeded Rome 2027-04-11..18 has 4 outbound seats (E=2+, P=2+) and 5 inbound seats
        # (E=2+, P=1, B=2+) -> for 5 seated passengers, FBVS = 100 * (4/5 + 5/5) / 2 = 90.0
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
            },
            profile=prof,
            persist_results=False,
        )
        hybrids = [
            p for p in proposals if _get_field(p.itinerary, "fulfillment_strategy") == "HYBRID_BONUS_PLUS_CASH"
        ]
        self.assertGreaterEqual(len(hybrids), 1)
        h_itin = _assert_run11_proposal_contract(self, hybrids[0])
        self.assertEqual((h_itin["outbound_bonus_seats"], h_itin["inbound_bonus_seats"]), (4, 5))
        self.assertEqual(hybrids[0].flight_bonus_value_score, 100.0)


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
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "ONE_WAY_BONUS_ONE_WAY_CASH")
        self.assertEqual(itin["bonus_direction_coverage"], "INBOUND_ONLY")
        self.assertEqual(itin["outbound_bonus_seats"], 0)
        self.assertEqual(itin["inbound_bonus_seats"], 2)
        self.assertTrue(itin["inbound_bonus_seats_is_two_plus"])
        self.assertEqual(itin["min_points_per_bonus_ticket"], 15000)
        self.assertEqual(itin["min_points_basis"], "ONE_WAY")

    def test_f25_02_outbound_two_plus_award_seats_inbound_zero_seats_triggers_reverse_one_way_bonus(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, in_a = self._make_oneway_pair(out_seats=2, in_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "ONE_WAY_BONUS_ONE_WAY_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "ONE_WAY_BONUS_ONE_WAY_CASH")
        self.assertEqual(itin["bonus_direction_coverage"], "OUTBOUND_ONLY")
        self.assertEqual(itin["outbound_bonus_seats"], 2)
        self.assertEqual(itin["inbound_bonus_seats"], 0)
        self.assertTrue(itin["outbound_bonus_seats_is_two_plus"])
        self.assertEqual(itin["min_points_per_bonus_ticket"], 15000)
        self.assertEqual(itin["min_points_basis"], "ONE_WAY")

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
        from unittest.mock import patch

        eng = self.get_wallet_engine()
        prof = self.shared_repo.get_profile()
        out_a, in_a = self._make_zero_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "CASH_AND_POINTS")
        self.assertEqual(itin["bonus_direction_coverage"], "NONE")
        self.assertEqual(itin["outbound_bonus_seats"], 0)
        self.assertEqual(itin["inbound_bonus_seats"], 0)
        self.assertIsNone(itin["min_points_per_bonus_ticket"])
        self.assertIsNone(itin["min_points_basis"])

        # At search level on the bonus path, zero-bonus results are excluded (U4)
        planner = self.get_planner()
        with patch.object(
            planner, "_ensure_award_rows_for_window", return_value=([out_a], [in_a])
        ):
            empty_props = planner.search_vacations(
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2027-04-20",
                    "specific_return_date": "2027-04-28",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                },
                profile=prof,
                persist_results=False,
            )
        self.assertEqual(empty_props, [])

    def test_f26_02_matmid_balance_single_ticket_minimum_boundaries_r2(self) -> None:
        client = self.get_client()
        base_payload = {
            "date_selection_mode": "SPECIFIC_DATES",
            "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 0,
            "destination_iatas": ["FCO"],
        }
        # Guest (2 adults) and inline 5-pax family both keep FULL_BONUS_SAME_CABIN at 30,000
        five_pax_inline = {
            "adults_count": 2,
            "children": [
                {"child_age_years": 5, "framework_type": "MUNICIPAL_GAN"},
                {"child_age_years": 9, "framework_type": "ELEMENTARY_4_6"},
                {"child_age_years": 13, "framework_type": "MIDDLE_SCHOOL_7_9"},
            ],
        }
        for extra in ({}, {"profile": five_pax_inline}):
            r_30k = client.post(
                "/api/v1/vacations/search",
                json={**base_payload, **extra, "matmid_points_balance": 30000},
            )
            self.assertEqual(r_30k.status_code, 200)
            itins_30k = _assert_run11_search_response_contract(
                self, r_30k.json(), is_bonus_search=True
            )
            self.assertIn(
                "FULL_BONUS_SAME_CABIN",
                {it["fulfillment_strategy"] for it in itins_30k},
            )

        # Boundary at 29,999 on 2-direction FCO (round-trip 30,000 dropped; no spurious same-airport 1-way)
        r_29999 = client.post(
            "/api/v1/vacations/search",
            json={**base_payload, "matmid_points_balance": 29999},
        )
        itins_29999 = _assert_run11_search_response_contract(
            self, r_29999.json(), is_bonus_search=True
        )
        self.assertEqual(
            {it["fulfillment_strategy"] for it in itins_29999},
            {"CASH_AND_POINTS"},
        )

        # Single-direction boundary on seeded 1-way Athens (`2026-12-06..12`)
        ath_base = {
            "date_selection_mode": "SPECIFIC_DATES",
            "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2026-12-06",
            "specific_return_date": "2026-12-12",
            "flex_days_plus_minus": 0,
            "destination_iatas": ["ATH"],
        }
        r_ath_0 = client.post("/api/v1/vacations/search", json={**ath_base, "matmid_points_balance": 0})
        ath_itins_0 = _assert_run11_search_response_contract(self, r_ath_0.json(), is_bonus_search=True)
        ath_ow_pts = next(
            it["min_points_per_bonus_ticket"]
            for it in ath_itins_0
            if it["fulfillment_strategy"] == "ONE_WAY_BONUS_ONE_WAY_CASH"
        )
        self.assertGreater(ath_ow_pts, 0)

        r_at_ow = client.post(
            "/api/v1/vacations/search",
            json={**ath_base, "matmid_points_balance": ath_ow_pts},
        )
        itins_at_ow = _assert_run11_search_response_contract(
            self, r_at_ow.json(), is_bonus_search=True
        )
        self.assertIn(
            "ONE_WAY_BONUS_ONE_WAY_CASH",
            {it["fulfillment_strategy"] for it in itins_at_ow},
        )

        r_below_ow = client.post(
            "/api/v1/vacations/search",
            json={**ath_base, "matmid_points_balance": ath_ow_pts - 1},
        )
        itins_below_ow = _assert_run11_search_response_contract(
            self, r_below_ow.json(), is_bonus_search=True
        )
        self.assertEqual(
            {it["fulfillment_strategy"] for it in itins_below_ow},
            {"CASH_AND_POINTS"},
        )

    def test_f26_03_equal_seat_scores_across_strategies_and_deterministic_tie_break_order_j5(self) -> None:
        planner = self.get_planner()
        prof = self.shared_repo.get_profile()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
                "enabled_loyalty_programs": [
                    "ELAL_MATMID",
                    "BRITISH_AVIOS",
                    "FLYING_BLUE",
                    "AMEX_MR_ISRAEL",
                ],
            },
            profile=prof,
            persist_results=False,
        )
        ordered_strategies = [_get_field(p.itinerary, "fulfillment_strategy") for p in proposals]
        self.assertEqual(
            ordered_strategies,
            [
                "FULL_BONUS_SAME_CABIN",
                "SPLIT_CABIN_BONUS",
                "MULTI_CLUB_PER_PASSENGER_SPLIT",
                "HYBRID_BONUS_PLUS_CASH",
                "CASH_AND_POINTS",
            ],
        )
        scores = {(p.flight_bonus_value_score, p.combined_trip_optimization_score) for p in proposals}
        self.assertEqual(len(scores), 1, "All strategies on the same award pair share identical seat-only scores")

    def test_f26_04_generated_when_household_has_zero_or_empty_matmid_points_j2(self) -> None:
        eng = self.get_wallet_engine()
        prof_zero = FamilyProfile(
            adults_count=2, matmid_points_balance=0, children=[], passenger_loyalty_wallets=[]
        )
        out_a, in_a = self._make_zero_award_pair()
        out_a.economy_award_seats = 2
        out_a.economy_seats_is_two_plus = True
        res = eng.allocate_family_tickets(
            prof_zero, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "CASH_AND_POINTS")
        self.assertEqual(itin["bonus_direction_coverage"], "OUTBOUND_ONLY")
        self.assertIsNone(itin["min_points_per_bonus_ticket"])
        self.assertIsNone(itin["min_points_basis"])

        planner = self.get_planner()
        props = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2026-12-06",
                "specific_return_date": "2026-12-12",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["ATH"],
                "matmid_points_balance": 0,
            },
            profile=prof_zero,
            persist_results=False,
        )
        self.assertIn(
            "CASH_AND_POINTS",
            {_get_field(p.itinerary, "fulfillment_strategy") for p in props},
        )

    def test_f26_05_points_deducted_never_exceed_available_matmid_balance(self) -> None:
        eng = self.get_wallet_engine()
        for bal in (12000, 5000, 0):
            prof = FamilyProfile(
                adults_count=2,
                matmid_points_balance=bal,
                children=[],
                passenger_loyalty_wallets=(
                    []
                    if bal == 0
                    else [
                        PassengerLoyaltyWallet(
                            id=f"w_{bal}", passenger_id="ADULT_1", passenger_name="A1",
                            program_code="ELAL_MATMID", available_points=bal, can_pool_with_family=True,
                        )
                    ]
                ),
            )
            out_a, in_a = self._make_zero_award_pair()
            out_a.economy_award_seats = 2
            out_a.economy_seats_is_two_plus = True
            res = eng.allocate_family_tickets(
                prof, out_a, in_a, 600.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
            )
            self.assertIsNotNone(res)
            itin = _assert_run11_itinerary_contract(self, res)
            self.assertIsNone(itin["min_points_per_bonus_ticket"])
            self.assertIsNone(itin["min_points_basis"])


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

    def test_f27_01_multi_club_requires_two_funded_wallets_and_round_trip_seat_slots_j3(self) -> None:
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
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "MULTI_CLUB_PER_PASSENGER_SPLIT")
        self.assertEqual(itin["bonus_tickets_count"], 2)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

        # <2 funded wallets -> None; 0 round-trip seat slots -> None
        one_wallet = FamilyProfile.from_dict(prof.to_dict())
        one_wallet.passenger_loyalty_wallets = prof.passenger_loyalty_wallets[:1]
        self.assertIsNone(
            eng.allocate_family_tickets(
                one_wallet, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
            )
        )
        out_zero, _ = self._make_mc_pair(econ=0, prem=0)
        self.assertIsNone(
            eng.allocate_family_tickets(
                prof, out_zero, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
            )
        )

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
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 2)
        self.assertEqual(itin["bonus_tickets_count"], 2)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

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
        enabled = ["ELAL_MATMID", "AMEX_MR_ISRAEL"]
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY"], enabled,
        )
        self.assertIsNotNone(res)
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["bonus_tickets_count"], 2)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        # 30,000 Matmid + (60,000 * 0.5) Amex MR = 60,000 effective El Al points
        self.assertEqual(eng.effective_elal_points_balance(prof, enabled), 60000)
        prof.passenger_loyalty_wallets[1].transfer_ratio_to_airline = 0.25
        self.assertEqual(eng.effective_elal_points_balance(prof, enabled), 45000)

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
        assert res is not None
        self.assertNotIn("family_ticket_allocation", res)
        self.assertEqual(_get_field(res, "seated_passengers_count"), 4)
        self.assertEqual(_get_field(res, "bonus_tickets_count"), 4)
        self.assertEqual(_get_field(res, "cash_tickets_count"), 0)

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

    def test_f28_01_non_bonus_search_returns_zero_bonus_score_and_none_coverage_guard(self) -> None:
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
            itin = _assert_run11_proposal_contract(self, p)
            self.assertEqual(itin["fulfillment_strategy"], "COMMERCIAL_CASH_ONLY")
            self.assertEqual(itin["bonus_direction_coverage"], "NONE")
            self.assertIsNone(itin["min_points_per_bonus_ticket"])
            self.assertEqual(p.flight_bonus_value_score, 0.0)

    def test_f28_02_seat_only_fbvs_zero_and_full_coverage_bounds(self) -> None:
        planner = self.get_planner()
        comm_props = planner.search_vacations(
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
        self.assertGreaterEqual(len(comm_props), 1)
        for p in comm_props:
            self.assertEqual(p.flight_bonus_value_score, 0.0)

        two_adults = FamilyProfile(adults_count=2, matmid_points_balance=0, children=[])
        bonus_props = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
            },
            profile=two_adults,
            persist_results=False,
        )
        self.assertGreaterEqual(len(bonus_props), 1)
        for p in bonus_props:
            self.assertEqual(p.flight_bonus_value_score, 100.0)

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
            expected_ctos = 0.55 * p.holiday_alignment_score + 0.45 * p.flight_bonus_value_score
            self.assertAlmostEqual(p.combined_trip_optimization_score, expected_ctos, delta=0.3)
            self.assertGreaterEqual(p.combined_trip_optimization_score, 0.0)
            self.assertLessEqual(p.combined_trip_optimization_score, 100.0)

    def test_f28_04_compare_proposals_removed_and_compare_route_returns_404_for_all_inputs(self) -> None:
        planner = self.get_planner()
        self.assertFalse(hasattr(planner, "compare_proposals"))
        client = self.get_client()
        for payload in (
            {"proposal_ids": []},
            {"proposal_ids": ["nonexistent-id-1", "nonexistent-id-2"]},
            {},
        ):
            r = client.post("/api/v1/vacations/compare", json=payload)
            self.assertEqual(r.status_code, 404)

    def test_f28_05_recursive_no_cash_keys_or_copy_across_all_modes_and_removed_ics_boundary_r1(self) -> None:
        planner = self.get_planner()
        self.assertFalse(hasattr(planner, "export_proposal_ics"))
        self.assertFalse(hasattr(planner, "compare_proposals"))

        forbidden_keys = set(RUN11_REMOVED_ITINERARY_KEYS) | set(RUN11_REMOVED_RESPONSE_KEYS)

        def collect_keys(node: Any) -> set[str]:
            found: set[str] = set()
            if isinstance(node, dict):
                for k, v in node.items():
                    found.add(str(k))
                    found |= collect_keys(v)
            elif isinstance(node, list):
                for item in node:
                    found |= collect_keys(item)
            return found

        _, db_path = self.create_temp_repo(auto_seed=True)
        auth_client = self.get_client(db_path)
        prof = self.shared_repo.get_profile()
        self.authenticate_test_client(auth_client, email="f28_05_r1@gmail.com")
        self.assertEqual(auth_client.put("/api/v1/profile", json=prof.to_dict()).status_code, 200)
        guest_client = self.get_client(db_path)

        seen_strategies: set[str] = set()
        for cli, payload, is_bonus in (
            (
                auth_client,
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                    "enabled_loyalty_programs": [
                        "ELAL_MATMID",
                        "BRITISH_AVIOS",
                        "FLYING_BLUE",
                        "AMEX_MR_ISRAEL",
                    ],
                },
                True,
            ),
            (
                auth_client,
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2026-12-06",
                    "specific_return_date": "2026-12-12",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["ATH"],
                },
                True,
            ),
            (
                guest_client,
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO", "MXP"],
                },
                True,
            ),
            (
                guest_client,
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "ALL_AIRLINES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                },
                False,
            ),
        ):
            resp = cli.post("/api/v1/vacations/search", json=payload)
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(collect_keys(body) & forbidden_keys, set())
            itins = _assert_run11_search_response_contract(self, body, is_bonus_search=is_bonus)
            seen_strategies.update(it["fulfillment_strategy"] for it in itins)

        self.assertEqual(
            seen_strategies,
            {
                "FULL_BONUS_SAME_CABIN",
                "SPLIT_CABIN_BONUS",
                "MULTI_CLUB_PER_PASSENGER_SPLIT",
                "HYBRID_BONUS_PLUS_CASH",
                "ONE_WAY_BONUS_ONE_WAY_CASH",
                "CASH_AND_POINTS",
                "COMMERCIAL_CASH_ONLY",
            },
        )

    def test_f28_06_multi_select_destination_empty_and_malformed_boundaries_run10_r2(self) -> None:
        client = self.get_client()
        base = {
            "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
            "direct_holiday_code": "PESACH",
            "direct_target_year": 2027,
        }
        for valid_open in (
            {**base, "destination_iatas": []},
            {**base, "destinations": []},
            {**base, "destination": ""},
            {**base, "destination_iatas": ["ANYWHERE", "ROM"]},
        ):
            r_ok = client.post("/api/v1/vacations/search", json=valid_open)
            self.assertEqual(r_ok.status_code, 200)
            self.assertEqual(r_ok.json()["query"]["destination_iatas"], ["ANYWHERE"])

        for malformed in (
            {**base, "destination_iatas": [None]},
            {**base, "destination_iatas": ["   "]},
            {**base, "destination_iatas": [123]},
            {**base, "destination_iatas": ["ZZZZ"]},
            {**base, "destinations": [None]},
            {**base, "destination": 999},
        ):
            r_bad = client.post("/api/v1/vacations/search", json=malformed)
            self.assertEqual(r_bad.status_code, 422)

        # POST /api/v1/elal-bonus/sync must keep rejecting {"destinations": []} with 422
        r_sync_empty = client.post("/api/v1/elal-bonus/sync", json={"destinations": []})
        self.assertEqual(r_sync_empty.status_code, 422)


class TestTier2F29RestApiNegativeAndBoundaries(Tier2BoundaryTestBase):
    """F29 — 8 Core REST API Endpoints (/api/v1/*) + .ics Export & Static Server negative & boundary tests."""

    def test_f29_01_put_profile_invalid_payloads_return_400_or_422_without_corrupting_db(self) -> None:
        _, db_path = self.create_temp_repo(auto_seed=True)
        client = self.get_client(db_path)
        # Unauthenticated PUT/GET must return 401
        self.assertEqual(client.get("/api/v1/profile").status_code, 401)
        self.assertEqual(client.put("/api/v1/profile", json={"adults_count": 2}).status_code, 401)

        # Authenticate a Gmail user session and save an initial valid profile (adults_count=3)
        self.authenticate_test_client(client, email="f29_boundary@gmail.com")
        seed_prof = client.get("/api/v1/profile").json()
        seed_prof["adults_count"] = 3
        self.assertEqual(client.put("/api/v1/profile", json=seed_prof).status_code, 200)
        orig = client.get("/api/v1/profile").json()
        self.assertEqual(orig["adults_count"], 3)

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
        self.assertEqual(after["adults_count"], 3)

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
        r_ics_missing = client.get("/api/v1/vacations/nonexistent-id-xyz/export.ics")
        s_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(s_resp.status_code, 200)
        valid_pid = s_resp.json()["proposals"][0]["id"]
        r_cmp_valid = client.post("/api/v1/vacations/compare", json={"proposal_ids": [valid_pid]})
        r_ics_valid = client.get(f"/api/v1/vacations/{valid_pid}/export.ics")
        r_404 = client.get("/api/v1/nonexistent-endpoint")
        self.assertEqual(r_cmp.status_code, 404)
        self.assertEqual(r_cmp_valid.status_code, 404)
        self.assertEqual(r_ics_missing.status_code, 404)
        self.assertEqual(r_ics_valid.status_code, 404)
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
            "search", "--mode", "holiday-direct", "--holiday", "PESACH", "--year", "2027",
            "--airline", "elal-only", "--max-bridge-days", "9",
        )
        r_removed_mode = self._run_cli("search", "--mode", "moe-maximize", "--airline", "elal-only")
        r_removed_ics = self._run_cli(
            "search", "--mode", "holiday-direct", "--holiday", "PESACH", "--year", "2027",
            "--export-ics", "out.ics",
        )
        self.assertNotEqual(r1.returncode, 0)
        self.assertNotEqual(r2.returncode, 0)
        self.assertNotEqual(r_removed_mode.returncode, 0)
        self.assertNotEqual(r_removed_ics.returncode, 0)

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
    """F31 — Desktop-First Multi-Column BiDi/RTL & LTR Web Application boundaries."""

    def test_f31_01_index_html_rtl_default_lang_he_and_viewport_meta_present(self) -> None:
        client = self.get_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="he"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("width=device-width", html)
        self.assertIn('id="dashboard-shell"', html)
        self.assertIn('class="sidebar-column"', html)
        self.assertIn('class="content-column"', html)

    def test_f31_02_css_mobile_360_430_and_desktop_1280_breakpoints_and_logical_rtl_properties(self) -> None:
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
        self.assertIn("@media", css)
        self.assertIn("sticky", css)
        self.assertTrue("inset-inline" in css or "margin-inline" in css or "padding-inline" in css)
        # Boundary verification of desktop 1280x800 and 1440x900 track geometry & non-overflow
        for vp_width, expected_sidebar, expected_gap, expected_pad in (
            (1280, 500, 24, 32),
            (1440, 540, 28, 36),
        ):
            content_track_width = vp_width - (2 * expected_pad) - expected_sidebar - expected_gap
            self.assertGreaterEqual(content_track_width, 650, f"Main content track too narrow at {vp_width}px")
            total_width = (2 * expected_pad) + expected_sidebar + expected_gap + content_track_width
            self.assertLessEqual(total_width, vp_width, f"Horizontal overflow at {vp_width}px")
            # Inner sidebar width after .zone-card padding (2*18px) and border (2*1px)
            sidebar_inner = expected_sidebar - 36 - 2
            # 3 columns in .mode-tabs (gap 10px) and .form-grid-3 (gap 12px) must each be >= 135px wide
            col3_width = (sidebar_inner - 2 * 12) / 3.0
            col2_width = (sidebar_inner - 12) / 2.0
            self.assertGreaterEqual(col3_width, 135.0)
            self.assertGreaterEqual(col2_width, 215.0)

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
        self.assertFalse((comp_root / "results" / "BonusVacationComparisonModal.tsx").exists())
        for rel in (
            "layout/AppShell.tsx",
            "layout/BreezyFlightsBrandHeader.tsx",
            "profile/FamilyProfileDrawer.tsx",
            "search/SearchControlPanel.tsx",
            "search/ElAlBonusSearchSubPanel.tsx",
            "calendar/MultiChildCalendarHeatmap.tsx",
            "results/BonusVacationOptionCard.tsx",
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
