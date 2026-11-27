"""Tier 1 Opaque-Box Feature Test Suite for family_vacation_planner.

Contains 160 isolated happy-path test methods (5 tests per feature across all
32 features F01..F32) strictly targeting the public contracts in PROJECT.md
and APPLICATION_PLAN.md with hermetic temporary SQLite database isolation.
"""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tests.e2e  # noqa: E402, F401

from backend.app.schemas import domain as domain_mod
from backend.app.schemas.domain import (
    AirlineSelectionMode,
    CandidateVacationWindow,
    ChildDayStatus,
    ChildFramework,
    ChildTripImpact,
    DailyFamilyCalendarMatrix,
    DateSelectionMode,
    ElAlBonusAvailability,
    FamilyProfile,
    FlightItinerary,
    FlightLeg,
    FlightSearchQuery,
    FulfillmentStrategy,
    HolidayExtensionMode,
    LoyaltyProgramCode,
    MoECalendarSyncStatus,
    MoEVacationWindow,
    MoEFrameworkType,
    PassengerLoyaltyWallet,
    VacationOptionProposal,
    classify_passenger_type,
    suggest_framework_for_age,
)


def _as_dict(obj: Any) -> dict[str, Any]:
    """Convert a domain object, dataclass, or dict to a plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dict or an object attribute."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, default)
    if isinstance(val, domain_mod.Enum):
        return val.value
    return val


# ----------------------------------------------------------------------------
# Run 11 response contract (shared by the Tier 1-4 suites)
# ----------------------------------------------------------------------------
# Keys that no planner response carries any more: cash estimate, saving, cents-per-point
# and the all-passenger points total / wallet deductions.
RUN11_REMOVED_ITINERARY_KEYS = (
    "total_taxes_and_fees_usd",
    "total_supplemental_cash_fares_usd",
    "total_baggage_fees_usd",
    "total_out_of_pocket_cash_usd",
    "estimated_cash_usd",
    "is_cash_price_estimate",
    "full_cash_benchmark_usd",
    "net_cash_saved_usd",
    "cents_per_point_value",
    "total_matmid_points",
    "points_used_by_wallet",
    "points_used_by_wallet_json",
)
RUN11_REMOVED_RESPONSE_KEYS = (
    "is_cash_price_estimate",
    "cash_pricing_disclaimer_he",
    "cash_pricing_disclaimer_en",
)
RUN11_NEW_ITINERARY_KEYS = (
    "bonus_direction_coverage",
    "outbound_bonus_seats",
    "inbound_bonus_seats",
    "outbound_bonus_seats_is_two_plus",
    "inbound_bonus_seats_is_two_plus",
    "min_points_per_bonus_ticket",
    "min_points_basis",
    "points_are_estimated",
)
RUN11_COVERAGE_VALUES = ("BOTH_DIRECTIONS", "OUTBOUND_ONLY", "INBOUND_ONLY", "NONE")
# Price wording that must not appear in text shown to a person (explanation, CLI line).
RUN11_FORBIDDEN_PRICE_TEXT = (
    "$",
    "¢",
    "הערכת",
    "חיסכון",
    "מזומן",
    "לא מחייב",
    "Est. Cash",
    "non-binding",
)
RUN11_DIRECTION_STATEMENTS_HE = {
    "BOTH_DIRECTIONS": "בונוס בשני הכיוונים",
    "OUTBOUND_ONLY": "בונוס בכיוון אחד בלבד — הלוך",
    "INBOUND_ONLY": "בונוס בכיוון אחד בלבד — חזור",
}


def _run11_expected_bonus_score(
    outbound_seats: Optional[int],
    inbound_seats: Optional[int],
    seated_passengers: int,
    outbound_two_plus: bool = False,
    inbound_two_plus: bool = False,
) -> float:
    """Documented seat-only bonus score: average share of the party each direction seats,
    with EL AL `2+` (`is_two_plus=True` and `seats >= 2`) counting as full 100% directional availability.
    """
    party = max(1, int(seated_passengers or 0))

    def _cov(seats: Optional[int], is_two_plus: bool) -> float:
        s = max(0, int(seats or 0))
        if s <= 0:
            return 0.0
        if is_two_plus and s >= 2:
            return 1.0
        return min(1.0, s / party)

    return round(
        100.0
        * (
            _cov(outbound_seats, outbound_two_plus)
            + _cov(inbound_seats, inbound_two_plus)
        )
        / 2.0,
        1,
    )


def _assert_run11_itinerary_contract(tc: unittest.TestCase, itinerary: Any) -> dict[str, Any]:
    """Assert the serialized itinerary follows the run-11 contract; return that dict."""
    data = _as_dict(itinerary)
    tc.assertTrue(data, "itinerary serializes to a non-empty dict")
    for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
        tc.assertNotIn(removed_key, data)
    for new_key in RUN11_NEW_ITINERARY_KEYS:
        tc.assertIn(new_key, data)

    coverage = data["bonus_direction_coverage"]
    tc.assertIn(coverage, RUN11_COVERAGE_VALUES)
    seats = {}
    for direction in ("outbound", "inbound"):
        value = data[f"{direction}_bonus_seats"]
        tc.assertTrue(
            value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0),
            f"{direction}_bonus_seats={value!r}",
        )
        two_plus = data[f"{direction}_bonus_seats_is_two_plus"]
        tc.assertIsInstance(two_plus, bool)
        if two_plus:
            tc.assertGreaterEqual(value or 0, 1, f"{direction}: a 2+ bucket has seats")
        seats[direction] = value or 0
    # The coverage statement is exactly what the two seat counts say
    expected_coverage = {
        (True, True): "BOTH_DIRECTIONS",
        (True, False): "OUTBOUND_ONLY",
        (False, True): "INBOUND_ONLY",
        (False, False): "NONE",
    }[(seats["outbound"] > 0, seats["inbound"] > 0)]
    tc.assertEqual(coverage, expected_coverage)

    min_points = data["min_points_per_bonus_ticket"]
    basis = data["min_points_basis"]
    if min_points is None:
        tc.assertIsNone(basis)
    else:
        tc.assertIsInstance(min_points, int)
        tc.assertGreater(min_points, 0)
        tc.assertIn(basis, ("ROUND_TRIP", "ONE_WAY"))
    strategy = data.get("fulfillment_strategy")
    if strategy in ("CASH_AND_POINTS", "COMMERCIAL_CASH_ONLY") or coverage == "NONE":
        tc.assertIsNone(min_points, f"{strategy} / {coverage} carries no points figure")
    tc.assertIs(data["points_are_estimated"], True)
    return data


def _assert_run11_proposal_contract(tc: unittest.TestCase, proposal: Any) -> dict[str, Any]:
    """Assert one planner result (object or API dict) follows the run-11 contract.

    Returns the serialized itinerary.
    """
    itin = _assert_run11_itinerary_contract(tc, _get_field(proposal, "itinerary"))
    explanation = _get_field(proposal, "explanation_summary_he")
    tc.assertIsInstance(explanation, str)
    tc.assertTrue(explanation.strip())
    for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
        tc.assertNotIn(forbidden, explanation)
    statement = RUN11_DIRECTION_STATEMENTS_HE.get(itin["bonus_direction_coverage"])
    if statement is not None:
        tc.assertIn(statement, explanation)
    # The bonus score is the documented function of seats per direction, 2+ flag, and party size
    tc.assertAlmostEqual(
        _get_field(proposal, "flight_bonus_value_score"),
        _run11_expected_bonus_score(
            itin["outbound_bonus_seats"],
            itin["inbound_bonus_seats"],
            itin["seated_passengers_count"],
            bool(itin.get("outbound_bonus_seats_is_two_plus")),
            bool(itin.get("inbound_bonus_seats_is_two_plus")),
        ),
        places=1,
    )
    return itin


def _assert_run11_search_response_contract(
    tc: unittest.TestCase,
    body: dict[str, Any],
    *,
    is_bonus_search: bool = True,
) -> list[dict[str, Any]]:
    """Assert a `/api/v1/vacations/search` JSON body obeys the run-11 contract."""
    tc.assertIsInstance(body, dict)
    for removed_top in RUN11_REMOVED_RESPONSE_KEYS:
        tc.assertNotIn(removed_top, body)
    proposals = body.get("proposals")
    tc.assertIsInstance(proposals, list)
    itins: list[dict[str, Any]] = []
    for prop in proposals:
        itin = _assert_run11_proposal_contract(tc, prop)
        if is_bonus_search:
            tc.assertNotEqual(itin["bonus_direction_coverage"], "NONE")
            tc.assertNotEqual(itin["fulfillment_strategy"], "COMMERCIAL_CASH_ONLY")
        if itin["fulfillment_strategy"] == "COMMERCIAL_CASH_ONLY":
            tc.assertEqual(itin["bonus_direction_coverage"], "NONE")
            tc.assertEqual(_get_field(prop, "flight_bonus_value_score"), 0.0)
        itins.append(itin)
    return itins


def _load_profile_from_sqlite(
    db_path: str | Path, profile_id: str = "default-family-profile"
) -> FamilyProfile:
    """Load a FamilyProfile with children and loyalty wallets from SQLite."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        prof_row = conn.execute(
            "SELECT * FROM family_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if prof_row is None:
            prof_row = conn.execute(
                "SELECT * FROM family_profiles LIMIT 1"
            ).fetchone()
        if prof_row is None:
            raise KeyError(f"Profile {profile_id!r} not found in {db_path}")
        pid = prof_row["id"]
        prof_dict = dict(prof_row)
        child_rows = conn.execute(
            "SELECT * FROM child_frameworks WHERE family_profile_id = ? ORDER BY child_age_years ASC",
            (pid,),
        ).fetchall()
        wallet_rows = conn.execute(
            "SELECT * FROM passenger_loyalty_wallets WHERE family_profile_id = ?",
            (pid,),
        ).fetchall()
        prof_dict["children"] = [dict(r) for r in child_rows]
        prof_dict["passenger_loyalty_wallets"] = [dict(r) for r in wallet_rows]
        return FamilyProfile.from_dict(prof_dict)
    finally:
        conn.close()


def _save_profile_to_repo_or_sqlite(
    repo: Any, db_path: str | Path, profile: FamilyProfile
) -> FamilyProfile:
    """Persist a FamilyProfile via repository method if available, else SQLite."""
    for method_name in ("save_profile", "upsert_profile", "update_profile", "save_family_profile"):
        fn = getattr(repo, method_name, None)
        if callable(fn):
            res = fn(profile)
            if isinstance(res, FamilyProfile):
                return res
            if isinstance(res, dict):
                return FamilyProfile.from_dict(res)
            return _load_profile_from_sqlite(db_path, profile.id)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO family_profiles (
                    id, profile_name, adults_count, matmid_points_balance,
                    has_flycard, flycard_tier, flycard_companion_vouchers,
                    point_valuation_usd, preferred_currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.profile_name,
                    profile.adults_count,
                    profile.matmid_points_balance,
                    1 if profile.has_flycard else 0,
                    profile.flycard_tier,
                    profile.flycard_companion_vouchers,
                    profile.point_valuation_usd,
                    profile.preferred_currency,
                ),
            )
            conn.execute(
                "DELETE FROM child_frameworks WHERE family_profile_id = ?",
                (profile.id,),
            )
            for child in profile.children:
                cd = child.to_dict()
                conn.execute(
                    """
                    INSERT INTO child_frameworks (
                        id, family_profile_id, child_name, child_age_years,
                        birth_date, passenger_Current_type, framework_type,
                        education_stream, school_week_days, holiday_extension_mode,
                        treat_camp_as_vacation, max_school_days_missed,
                        absence_penalty_weight, bagrut_blackout_dates_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cd["id"],
                        profile.id,
                        cd["child_name"],
                        cd["child_age_years"],
                        cd["birth_date"],
                        cd["passenger_Current_type"],
                        cd["framework_type"],
                        cd["education_stream"],
                        cd["school_week_days"],
                        cd["holiday_extension_mode"],
                        1 if cd["treat_camp_as_vacation"] else 0,
                        cd["max_school_days_missed"],
                        cd["absence_penalty_weight"],
                        cd["bagrut_blackout_dates_json"],
                    ),
                )
            conn.execute(
                "DELETE FROM passenger_loyalty_wallets WHERE family_profile_id = ?",
                (profile.id,),
            )
            for wallet in profile.passenger_loyalty_wallets:
                wd = wallet.to_dict()
                conn.execute(
                    """
                    INSERT INTO passenger_loyalty_wallets (
                        id, family_profile_id, passenger_id, passenger_name,
                        program_code, available_points, can_pool_with_family,
                        pool_group_id, transfer_ratio_to_airline,
                        has_club_credit_card, companion_vouchers_count,
                        point_valuation_cents
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        wd["id"],
                        profile.id,
                        wd["passenger_id"],
                        wd["passenger_name"],
                        wd["program_code"],
                        wd["available_points"],
                        1 if wd["can_pool_with_family"] else 0,
                        wd["pool_group_id"],
                        wd["transfer_ratio_to_airline"],
                        1 if wd["has_club_credit_card"] else 0,
                        wd["companion_vouchers_count"],
                        wd["point_valuation_cents"],
                    ),
                )
        return _load_profile_from_sqlite(db_path, profile.id)
    finally:
        conn.close()


class Tier1BaseTestCase(unittest.TestCase):
    """Shared hermetic base class for Tier 1 feature tests."""

    _shared_tmpdir: Optional[tempfile.TemporaryDirectory[str]] = None
    _shared_db_path: Optional[Path] = None
    _shared_repo: Any = None
    _shared_calendar_service: Any = None
    _shared_auto_updater: Any = None
    _shared_maximizer: Any = None
    _shared_elal_adapter: Any = None
    _shared_commercial_adapter: Any = None
    _shared_planner: Any = None
    _shared_client: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if Tier1BaseTestCase._shared_tmpdir is None:
            Tier1BaseTestCase._shared_tmpdir = tempfile.TemporaryDirectory(
                prefix="tier1_e2e_shared_"
            )
            Tier1BaseTestCase._shared_db_path = (
                Path(Tier1BaseTestCase._shared_tmpdir.name) / "tier1_shared.db"
            )

    @property
    def shared_db_path(self) -> Path:
        assert Tier1BaseTestCase._shared_db_path is not None
        return Tier1BaseTestCase._shared_db_path

    def get_repo(self) -> Any:
        if Tier1BaseTestCase._shared_repo is None:
            from backend.app.storage_cache.repository import SQLiteRepository
            from backend.app.storage_cache.seed_data import build_default_family_profile

            Tier1BaseTestCase._shared_repo = SQLiteRepository(
                db_path=self.shared_db_path, auto_seed=True
            )
            if not SQLiteRepository.is_live_fetch_mode():
                Tier1BaseTestCase._shared_repo.save_profile(
                    build_default_family_profile()
                )
        return Tier1BaseTestCase._shared_repo

    def get_calendar_service(self, repo: Any = None) -> Any:
        from backend.app.calendar_engine.moe_calendar_service import MoECalendarService

        if repo is not None:
            return MoECalendarService(repo)
        if Tier1BaseTestCase._shared_calendar_service is None:
            Tier1BaseTestCase._shared_calendar_service = MoECalendarService(
                self.get_repo()
            )
        return Tier1BaseTestCase._shared_calendar_service

    def get_auto_updater(self, repo: Any = None) -> Any:
        from backend.app.calendar_engine.moe_calendar_service import (
            MoECalendarAutoUpdaterService,
        )

        if repo is not None:
            return MoECalendarAutoUpdaterService(repo)
        if Tier1BaseTestCase._shared_auto_updater is None:
            Tier1BaseTestCase._shared_auto_updater = MoECalendarAutoUpdaterService(
                self.get_repo()
            )
        return Tier1BaseTestCase._shared_auto_updater

    def get_maximizer(self, calendar_service: Any = None) -> Any:
        from backend.app.vacation_optimizer.maximizer_engine import (
            VacationMaximizerEngine,
        )

        if calendar_service is not None:
            return VacationMaximizerEngine(calendar_service)
        if Tier1BaseTestCase._shared_maximizer is None:
            Tier1BaseTestCase._shared_maximizer = VacationMaximizerEngine(
                self.get_calendar_service()
            )
        return Tier1BaseTestCase._shared_maximizer

    def get_elal_adapter(self, repo: Any = None) -> Any:
        from backend.app.providers.elal_rbd_client import ElAlRbdDataClientAdapter

        if repo is not None:
            return ElAlRbdDataClientAdapter(repo)
        if Tier1BaseTestCase._shared_elal_adapter is None:
            Tier1BaseTestCase._shared_elal_adapter = ElAlRbdDataClientAdapter(
                self.get_repo()
            )
        return Tier1BaseTestCase._shared_elal_adapter

    def get_commercial_adapter(self, repo: Any = None) -> Any:
        from backend.app.providers.commercial_flights import AllAirlinesSearchAdapter

        if repo is not None:
            return AllAirlinesSearchAdapter(repo)
        if Tier1BaseTestCase._shared_commercial_adapter is None:
            Tier1BaseTestCase._shared_commercial_adapter = AllAirlinesSearchAdapter(
                self.get_repo()
            )
        return Tier1BaseTestCase._shared_commercial_adapter

    def get_wallet_engine(self) -> Any:
        from backend.app.planner_synthesizer.bonus_planner_service import (
            MultiClubWalletAllocationEngine,
        )

        return MultiClubWalletAllocationEngine()

    def get_planner(self, repo: Any = None) -> Any:
        from backend.app.planner_synthesizer.bonus_planner_service import (
            BonusVacationPlannerService,
        )

        if repo is not None:
            cal = self.get_calendar_service(repo)
            max_eng = self.get_maximizer(cal)
            elal = self.get_elal_adapter(repo)
            comm = self.get_commercial_adapter(repo)
            return BonusVacationPlannerService(repo, cal, max_eng, elal, comm)
        if Tier1BaseTestCase._shared_planner is None:
            r = self.get_repo()
            cal = self.get_calendar_service(r)
            max_eng = self.get_maximizer(cal)
            elal = self.get_elal_adapter(r)
            comm = self.get_commercial_adapter(r)
            Tier1BaseTestCase._shared_planner = BonusVacationPlannerService(
                r, cal, max_eng, elal, comm
            )
        return Tier1BaseTestCase._shared_planner

    def get_client(self, db_path: Optional[str | Path] = None) -> Any:
        from backend.app.main import VacationPlannerTestClient

        if db_path is not None:
            return VacationPlannerTestClient(db_path=str(db_path))
        if Tier1BaseTestCase._shared_client is None:
            assert Tier1BaseTestCase._shared_tmpdir is not None
            shared_http_db = (
                Path(Tier1BaseTestCase._shared_tmpdir.name) / "tier1_shared_http.db"
            )
            Tier1BaseTestCase._shared_client = VacationPlannerTestClient(
                db_path=str(shared_http_db)
            )
        return Tier1BaseTestCase._shared_client

    def authenticate_test_client(
        self,
        client: Any,
        email: str = "family@gmail.com",
        sub: Optional[str] = None,
        profile: Any = None,
    ) -> dict[str, Any]:
        """Complete real server-side Google OAuth 2.0 + PKCE login on `client` via injected token exchanger."""
        from backend.app.auth_service import (
            build_unsigned_or_hs256_jwt_for_test,
            pkce_s256_challenge,
        )

        auth_svc = client.router.auth_service
        auth_svc.client_id = "e2e-client.apps.googleusercontent.com"
        auth_svc.client_secret = "e2e-client-secret"
        auth_svc.redirect_uri = (
            "https://breezyflights.com/api/v1/auth/google/callback"
        )

        login_resp = client.get("/api/v1/auth/google/login")
        self.assertEqual(login_resp.status_code, 302)
        loc = login_resp.headers["Location"]
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)
        state = q["state"][0]
        nonce = q["nonce"][0]
        challenge = q["code_challenge"][0]

        def _exchange(
            code: str, code_verifier: str, redirect_uri: str, cid: str, csec: str
        ) -> dict[str, Any]:
            self.assertEqual(pkce_s256_challenge(code_verifier), challenge)
            now_ts = int(time.time())
            id_tok = build_unsigned_or_hs256_jwt_for_test(
                {
                    "iss": "https://accounts.google.com",
                    "aud": cid,
                    "sub": sub or f"google-sub-{email}",
                    "email": email,
                    "email_verified": True,
                    "name": email.split("@")[0].title(),
                    "nonce": nonce,
                    "iat": now_ts - 5,
                    "exp": now_ts + 3600,
                }
            )
            return {"id_token": id_tok, "token_type": "Bearer", "expires_in": 3600}

        auth_svc.token_exchanger = _exchange
        cb_resp = client.get(
            f"/api/v1/auth/google/callback?code=e2e-auth-code&state={state}"
        )
        self.assertEqual(cb_resp.status_code, 302)

        sess_resp = client.get("/api/v1/auth/session")
        self.assertEqual(sess_resp.status_code, 200)
        sess_json = sess_resp.json()
        self.assertTrue(sess_json.get("authenticated"))
        csrf_token = str(sess_json["csrf_token"])
        client.default_headers["X-CSRF-Token"] = csrf_token
        client.default_headers["Origin"] = "http://127.0.0.1:8000"

        if profile is not None:
            payload = (
                profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
            )
            put_resp = client.put("/api/v1/profile", json=payload)
            self.assertEqual(put_resp.status_code, 200, put_resp.text)
        return sess_json

    def make_isolated_env(
        self, auto_seed: bool = True
    ) -> tuple[Path, Any]:
        """Create an isolated temporary SQLite database and SQLiteRepository."""
        from backend.app.storage_cache.repository import SQLiteRepository
        from backend.app.storage_cache.seed_data import build_default_family_profile

        tmpdir = tempfile.TemporaryDirectory(prefix="tier1_iso_")
        self.addCleanup(tmpdir.cleanup)
        db_path = Path(tmpdir.name) / "isolated.db"
        repo = SQLiteRepository(db_path=db_path, auto_seed=auto_seed)
        if auto_seed and not SQLiteRepository.is_live_fetch_mode():
            repo.save_profile(build_default_family_profile())
        return db_path, repo

    def get_default_profile(self, db_path: Optional[str | Path] = None) -> FamilyProfile:
        target = db_path or self.shared_db_path
        if target == self.shared_db_path:
            self.get_repo()
        return _load_profile_from_sqlite(target, "default-family-profile")

    def _make_award_pair(
        self, econ_seats: int = 2, prem_seats: int = 2, biz_seats: int = 2
    ) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_fco",
            origin_iata="TLV",
            destination_iata="FCO",
            direction="OUTBOUND",
            flight_number="LY381",
            flight_date=date(2027, 4, 11),
            economy_award_seats=econ_seats,
            economy_seats_is_two_plus=econ_seats >= 2,
            premium_award_seats=prem_seats,
            premium_seats_is_two_plus=prem_seats >= 2,
            business_award_seats=biz_seats,
            business_seats_is_two_plus=biz_seats >= 2,
            award_zone="ZONE_B",
            economy_points_per_pax=15000,
            premium_points_per_pax=20500,
            business_points_per_pax=45000,
            taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_fco",
            origin_iata="FCO",
            destination_iata="TLV",
            direction="INBOUND",
            flight_number="LY384",
            flight_date=date(2027, 4, 18),
            economy_award_seats=econ_seats,
            economy_seats_is_two_plus=econ_seats >= 2,
            premium_award_seats=prem_seats,
            premium_seats_is_two_plus=prem_seats >= 2,
            business_award_seats=biz_seats,
            business_seats_is_two_plus=biz_seats >= 2,
            award_zone="ZONE_B",
            economy_points_per_pax=15000,
            premium_points_per_pax=20500,
            business_points_per_pax=45000,
            taxes_usd_per_pax=48.75,
        )
        return out_a, in_a


# ============================================================================
# Feature F01: family_profiles SQLite Table (5 tests)
# ============================================================================
class TestTier1F01FamilyProfiles(Tier1BaseTestCase):
    def test_f01_1_wal_mode_and_foreign_keys_enabled(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        conn = sqlite3.connect(str(db_path))
        try:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            self.assertEqual(str(journal_mode).lower(), "wal")
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            expected_tables = {
                "users",
                "auth_sessions",
                "oauth_login_states",
                "family_profiles",
                "passenger_loyalty_wallets",
                "child_frameworks",
                "moe_vacation_windows",
                "flight_search_queries",
                "elal_bonus_availability",
                "flight_itineraries",
                "vacation_option_proposals",
            }
            self.assertTrue(expected_tables.issubset(tables))
        finally:
            conn.close()

    def test_f01_2_default_seeded_family_profile_record(self) -> None:
        self.get_repo()
        profile = self.get_default_profile()
        self.assertEqual(profile.id, "default-family-profile")
        self.assertEqual(profile.profile_name, "משפחת בודובסקי")
        self.assertEqual(profile.adults_count, 2)
        self.assertNotIn("annual_pto_budget", profile.to_dict())
        self.assertNotIn("workweek_type", profile.to_dict())
        self.assertEqual(profile.matmid_points_balance, 185000)
        self.assertTrue(profile.has_flycard)
        self.assertEqual(profile.flycard_tier, "FLY_CARD_PREMIUM")
        self.assertEqual(profile.flycard_companion_vouchers, 1)
        self.assertAlmostEqual(profile.point_valuation_usd, 0.016)
        self.assertEqual(profile.preferred_currency, "USD")

    def test_f01_3_profile_roundtrip_omits_removed_pto_and_workweek_fields(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        prof.adults_count = 4
        prof.matmid_points_balance = 240000
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        self.assertEqual(saved.adults_count, 4)
        self.assertEqual(saved.matmid_points_balance, 240000)
        dumped = saved.to_dict()
        for removed_col in (
            "workweek_type",
            "erev_chag_pto_weight",
            "chol_hamoed_pto_weight",
            "annual_pto_budget",
            "max_pto_per_trip",
        ):
            self.assertNotIn(removed_col, dumped)

    def test_f01_4_flycard_tiers_and_companion_vouchers_persistence(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        for tier in ("NONE", "FLY_CARD", "FLY_CARD_PREMIUM"):
            prof = self.get_default_profile(db_path)
            prof.flycard_tier = tier
            prof.has_flycard = tier != "NONE"
            prof.flycard_companion_vouchers = 2
            prof.matmid_points_balance = 320000
            saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
            self.assertEqual(saved.flycard_tier, tier)
            self.assertEqual(saved.flycard_companion_vouchers, 2)
            self.assertEqual(saved.matmid_points_balance, 320000)
            roundtripped = FamilyProfile.from_dict(saved.to_dict())
            self.assertEqual(roundtripped.flycard_tier, tier)

    def test_f01_5_supported_currencies_and_point_valuation_persistence(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        for curr in ("USD", "ILS", "EUR"):
            prof = self.get_default_profile(db_path)
            prof.preferred_currency = curr
            prof.point_valuation_usd = 0.018
            saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
            self.assertEqual(saved.preferred_currency, curr)
            self.assertAlmostEqual(saved.point_valuation_usd, 0.018)
            dumped = saved.model_dump()
            self.assertEqual(dumped["preferred_currency"], curr)
            self.assertAlmostEqual(dumped["point_valuation_usd"], 0.018)


# ============================================================================
# Feature F02: passenger_loyalty_wallets SQLite Table (5 tests)
# ============================================================================
class TestTier1F02PassengerLoyaltyWallets(Tier1BaseTestCase):
    def test_f02_1_default_seeded_passenger_loyalty_wallets(self) -> None:
        self.get_repo()
        prof = self.get_default_profile()
        wallets = prof.passenger_loyalty_wallets
        self.assertGreaterEqual(len(wallets), 6)
        by_pax_prog = {
            (w.passenger_id, _get_field(w, "program_code")): w for w in wallets
        }
        self.assertIn(("ADULT_1", "ELAL_MATMID"), by_pax_prog)
        self.assertEqual(by_pax_prog[("ADULT_1", "ELAL_MATMID")].available_points, 115000)
        self.assertTrue(by_pax_prog[("ADULT_1", "ELAL_MATMID")].has_club_credit_card)
        self.assertEqual(by_pax_prog[("ADULT_1", "ELAL_MATMID")].companion_vouchers_count, 1)
        self.assertEqual(by_pax_prog[("ADULT_1", "BRITISH_AVIOS")].available_points, 65000)
        self.assertEqual(by_pax_prog[("ADULT_1", "AMEX_MR_ISRAEL")].available_points, 80000)
        self.assertEqual(by_pax_prog[("ADULT_2", "ELAL_MATMID")].available_points, 70000)
        self.assertEqual(by_pax_prog[("ADULT_2", "FLYING_BLUE")].available_points, 55000)
        self.assertEqual(by_pax_prog[("ADULT_2", "UNITED_MILEAGEPLUS")].available_points, 60000)

    def test_f02_2_all_ten_loyalty_program_codes_supported(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        all_codes = [c.value for c in LoyaltyProgramCode]
        self.assertEqual(len(all_codes), 10)
        prof.passenger_loyalty_wallets = [
            PassengerLoyaltyWallet(
                id=f"w-{idx}",
                family_profile_id=prof.id,
                passenger_id="ADULT_1",
                passenger_name="יוני (הורה 1)",
                program_code=code,
                available_points=50000 + idx * 1000,
                can_pool_with_family=True,
            )
            for idx, code in enumerate(all_codes)
        ]
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        self.assertEqual(len(saved.passenger_loyalty_wallets), 10)
        conn = sqlite3.connect(str(db_path))
        try:
            distinct_cnt = conn.execute(
                "SELECT COUNT(DISTINCT program_code) FROM passenger_loyalty_wallets WHERE family_profile_id = ?",
                (prof.id,),
            ).fetchone()[0]
            self.assertEqual(distinct_cnt, 10)
        finally:
            conn.close()

    def test_f02_3_family_pooling_and_pool_group_id_persistence(self) -> None:
        w_pooled = PassengerLoyaltyWallet(
            id="w-pool-1",
            passenger_id="ADULT_1",
            passenger_name="יוני",
            program_code="ELAL_MATMID",
            available_points=90000,
            can_pool_with_family=True,
            pool_group_id="POOL_MATMID_FAMILY",
        )
        w_unpooled = PassengerLoyaltyWallet(
            id="w-unpool-2",
            passenger_id="ADULT_2",
            passenger_name="הורה 2",
            program_code="ELAL_MATMID",
            available_points=60000,
            can_pool_with_family=False,
            pool_group_id=None,
        )
        rt1 = PassengerLoyaltyWallet.from_dict(w_pooled.to_dict())
        rt2 = PassengerLoyaltyWallet.from_dict(w_unpooled.to_dict())
        self.assertTrue(rt1.can_pool_with_family)
        self.assertEqual(rt1.pool_group_id, "POOL_MATMID_FAMILY")
        self.assertFalse(rt2.can_pool_with_family)
        self.assertIsNone(rt2.pool_group_id)

    def test_f02_4_transfer_ratio_vouchers_and_point_valuation_cents(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        prof.passenger_loyalty_wallets.append(
            PassengerLoyaltyWallet(
                id="w-cc-test",
                family_profile_id=prof.id,
                passenger_id="ADULT_1",
                passenger_name="יוני",
                program_code="ISRAELI_CC_TRAVEL_POINTS",
                available_points=100000,
                transfer_ratio_to_airline=0.8,
                has_club_credit_card=True,
                companion_vouchers_count=2,
                point_valuation_cents=1.75,
            )
        )
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        match = [w for w in saved.passenger_loyalty_wallets if w.id == "w-cc-test"][0]
        self.assertAlmostEqual(match.transfer_ratio_to_airline, 0.8)
        self.assertTrue(match.has_club_credit_card)
        self.assertEqual(match.companion_vouchers_count, 2)
        self.assertAlmostEqual(match.point_valuation_cents, 1.75)

    def test_f02_5_loyalty_wallets_index_and_cascade_delete_on_profile(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            indexes = {
                row[1]
                for row in conn.execute(
                    "PRAGMA index_list('passenger_loyalty_wallets')"
                ).fetchall()
            }
            self.assertIn("idx_loyalty_wallets_profile_pax", indexes)
            with conn:
                conn.execute(
                    "INSERT INTO family_profiles (id, profile_name) VALUES ('tmp-prof', 'Temp')"
                )
                conn.execute(
                    """
                    INSERT INTO passenger_loyalty_wallets (
                        id, family_profile_id, passenger_id, passenger_name, program_code, available_points
                    ) VALUES ('tmp-w1', 'tmp-prof', 'ADULT_1', 'Test', 'ELAL_MATMID', 10000)
                    """
                )
                conn.execute("DELETE FROM family_profiles WHERE id = 'tmp-prof'")
            remaining = conn.execute(
                "SELECT COUNT(*) FROM passenger_loyalty_wallets WHERE family_profile_id = 'tmp-prof'"
            ).fetchone()[0]
            self.assertEqual(remaining, 0)
        finally:
            conn.close()


# ============================================================================
# Feature F03: child_frameworks SQLite Table (5 tests)
# ============================================================================
class TestTier1F03ChildFrameworks(Tier1BaseTestCase):
    def test_f03_1_default_seeded_three_children_frameworks(self) -> None:
        self.get_repo()
        prof = self.get_default_profile()
        self.assertEqual(len(prof.children), 3)
        by_name = {c.child_name: c for c in prof.children}
        self.assertIn("נועה", by_name)
        self.assertIn("עידו", by_name)
        self.assertIn("מאיה", by_name)
        noa = by_name["נועה"]
        self.assertEqual(noa.child_age_years, 5)
        self.assertEqual(noa.passenger_Current_type, "CHILD")
        self.assertEqual(_get_field(noa, "framework_type"), "MUNICIPAL_GAN")
        self.assertEqual(noa.school_week_days, 6)
        self.assertEqual(
            _get_field(noa, "holiday_extension_mode"), "NITZANIM_FULL_WITH_JULY"
        )
        self.assertAlmostEqual(noa.absence_penalty_weight, 0.25)

        ido = by_name["עידו"]
        self.assertEqual(ido.child_age_years, 9)
        self.assertEqual(_get_field(ido, "framework_type"), "ELEMENTARY_4_6")
        self.assertEqual(ido.school_week_days, 5)
        self.assertAlmostEqual(ido.absence_penalty_weight, 0.75)

        maya = by_name["מאיה"]
        self.assertEqual(maya.child_age_years, 13)
        self.assertEqual(maya.passenger_Current_type, "YOUTH")
        self.assertEqual(_get_field(maya, "framework_type"), "MIDDLE_SCHOOL_7_9")
        self.assertAlmostEqual(maya.absence_penalty_weight, 1.0)

    def test_f03_2_nullable_framework_type_for_mode1_specific_dates(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        prof.children = [
            ChildFramework(
                id="c-null-1", child_name="תינוק", child_age_years=1, framework_type=None
            ),
            ChildFramework(
                id="c-null-2", child_name="ילד", child_age_years=7, framework_type=None
            ),
            ChildFramework(
                id="c-null-3", child_name="נער", child_age_years=15, framework_type=None
            ),
        ]
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        self.assertEqual(len(saved.children), 3)
        for child in saved.children:
            self.assertIsNone(child.framework_type)

    def test_f03_3_all_eight_moe_framework_types_and_education_streams(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        all_fws = [fw.value for fw in MoEFrameworkType]
        streams = ["MAMLACHTI", "MAMLACHTI_DATI", "CHAREDI", "SPECIAL_EDUCATION"]
        self.assertEqual(len(all_fws), 8)
        prof.children = [
            ChildFramework(
                id=f"c-fw-{i}",
                child_name=f"ילד {i}",
                child_age_years=min(18, 2 + i * 2),
                framework_type=fw,
                education_stream=streams[i % len(streams)],
            )
            for i, fw in enumerate(all_fws)
        ]
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        self.assertEqual(
            {_get_field(c, "framework_type") for c in saved.children}, set(all_fws)
        )
        self.assertEqual(
            {c.education_stream for c in saved.children}, set(streams)
        )

    def test_f03_4_passenger_fare_types_and_school_week_days_5_vs_6(self) -> None:
        cases = [
            (0, "INFANT_LAP", 6, "NONE"),
            (1, "INFANT_SEAT", 6, "NITZANIM_CHAGIM_ONLY"),
            (6, "CHILD", 5, "NITZANIM_FULL_WITH_JULY"),
            (14, "YOUTH", 5, "NONE"),
        ]
        for age, fare, week_days, ext_mode in cases:
            child = ChildFramework(
                child_age_years=age,
                passenger_Current_type=fare,
                school_week_days=week_days,
                holiday_extension_mode=ext_mode,
            )
            rt = ChildFramework.from_dict(child.to_dict())
            self.assertEqual(rt.passenger_Current_type, fare)
            self.assertEqual(rt.school_week_days, week_days)
            self.assertEqual(_get_field(rt, "holiday_extension_mode"), ext_mode)

    def test_f03_5_bagrut_blackout_dates_json_and_absence_limits(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        prof = self.get_default_profile(db_path)
        hs_child = ChildFramework(
            id="c-bagrut-1",
            child_name="תמר",
            child_age_years=16,
            framework_type="HIGH_SCHOOL_10_12",
            max_school_days_missed=3,
            absence_penalty_weight=1.35,
            bagrut_blackout_dates=[date(2027, 5, 18), date(2027, 6, 3)],
        )
        prof.children = [hs_child]
        saved = _save_profile_to_repo_or_sqlite(repo, db_path, prof)
        self.assertEqual(len(saved.children), 1)
        loaded_child = saved.children[0]
        self.assertEqual(loaded_child.max_school_days_missed, 3)
        self.assertAlmostEqual(loaded_child.absence_penalty_weight, 1.35)
        self.assertEqual(
            loaded_child.bagrut_blackout_dates,
            [date(2027, 5, 18), date(2027, 6, 3)],
        )


# ============================================================================
# Feature F04: moe_vacation_windows SQLite Table (5 tests)
# ============================================================================
class TestTier1F04MoEVacationWindows(Tier1BaseTestCase):
    def test_f04_1_seeded_moe_vacation_windows_for_5786_and_5787(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        try:
            rows = dict(
                conn.execute(
                    "SELECT school_year, COUNT(*) FROM moe_vacation_windows GROUP BY school_year"
                ).fetchall()
            )
            self.assertIn("2025-2026", rows)
            self.assertIn("2026-2027", rows)
            self.assertGreaterEqual(rows["2025-2026"], 40)
            self.assertGreaterEqual(rows["2026-2027"], 40)
        finally:
            conn.close()

    def test_f04_2_nitzanim_coverage_columns_populated_on_gan_and_elementary_1_3(
        self,
    ) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT * FROM moe_vacation_windows
                WHERE school_year = '2026-2027'
                  AND holiday_code IN ('HANUKKAH', 'PESACH', 'SUMMER_JULY')
                  AND framework_type IN ('MUNICIPAL_GAN', 'ELEMENTARY_1_3')
                """
            ).fetchall()
            self.assertGreaterEqual(len(rows), 4)
            for row in rows:
                self.assertEqual(row["is_covered_by_nitzanim"], 1)
                self.assertIsNotNone(row["nitzanim_start_date"])
                self.assertIsNotNone(row["nitzanim_end_date"])
        finally:
            conn.close()

    def test_f04_3_parent_workday_status_and_tlv_airport_closed_flags(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            kippur_rows = conn.execute(
                """
                SELECT * FROM moe_vacation_windows
                WHERE holiday_code LIKE '%KIPPUR%'
                """
            ).fetchall()
            self.assertGreater(len(kippur_rows), 0)
            self.assertTrue(any(r["tlv_airport_closed"] == 1 for r in kippur_rows))
            cols = {
                r[1]
                for r in conn.execute("PRAGMA table_info(moe_vacation_windows)").fetchall()
            }
            self.assertNotIn("parent_workday_status", cols)
        finally:
            conn.close()

    def test_f04_4_calendar_sync_source_and_circular_metadata(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT DISTINCT school_year, circular_id, calendar_sync_source FROM moe_vacation_windows"
            ).fetchall()
            self.assertGreater(len(rows), 0)
            sync_sources = {r["calendar_sync_source"] for r in rows}
            self.assertIn("OFFICIAL_MOE_CIRCULAR", sync_sources)
        finally:
            conn.close()

    def test_f04_5_index_idx_moe_vacation_year_framework_exists(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            indexes = {
                row[1]
                for row in conn.execute(
                    "PRAGMA index_list('moe_vacation_windows')"
                ).fetchall()
            }
            self.assertIn("idx_moe_vacation_year_framework", indexes)
            sample = conn.execute(
                "SELECT * FROM moe_vacation_windows LIMIT 1"
            ).fetchone()
            win = MoEVacationWindow.from_dict(dict(sample))
            rt = MoEVacationWindow.from_dict(win.to_dict())
            self.assertEqual(rt.id, win.id)
            self.assertEqual(rt.school_year, win.school_year)
        finally:
            conn.close()


# ============================================================================
# Feature F05: flight_search_queries SQLite Table (5 tests)
# ============================================================================
class TestTier1F05FlightSearchQueries(Tier1BaseTestCase):
    def test_f05_1_persist_mode1_specific_dates_query(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        q = FlightSearchQuery(
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="EL_AL_ONLY",
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            flex_days_plus_minus=2,
            destination_iatas=["FCO"],
        )
        repo.save_search_query(q)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM flight_search_queries WHERE date_selection_mode = 'SPECIFIC_DATES' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["flex_days_plus_minus"], 2)
            self.assertEqual(row["specific_departure_date"], "2027-04-11")
            self.assertEqual(row["specific_return_date"], "2027-04-18")
        finally:
            conn.close()

    def test_f05_2_rejects_removed_moe_vacation_maximization_mode(self) -> None:
        with self.assertRaises(ValueError):
            FlightSearchQuery(
                date_selection_mode="MOE_VACATION_MAXIMIZATION",
                airline_selection_mode="EL_AL_ONLY",
                school_year="2026-2027",
                destination_iatas=["FCO"],
            )
        coerced = FlightSearchQuery.from_dict(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "overlap_policy": "MAXIMIZE_EFFICIENCY_SCORE",
                "destination_iatas": ["FCO"],
            }
        )
        self.assertEqual(coerced.overlap_policy, "CAMP_ADJUSTED_INTERSECTION")

    def test_f05_3_persist_mode3_holiday_direct_intent_query(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            direct_holiday_code="PESACH",
            direct_target_year=2027,
            min_trip_nights=5,
            max_trip_nights=8,
            max_bridge_days_shift=2,
            destination_iatas=["FCO"],
        )
        repo.save_search_query(q)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM flight_search_queries WHERE date_selection_mode = 'HOLIDAY_DIRECT_INTENT' LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["direct_holiday_code"], "PESACH")
            self.assertEqual(row["direct_target_year"], 2027)
            self.assertEqual(row["min_trip_nights"], 5)
            self.assertEqual(row["max_trip_nights"], 8)
        finally:
            conn.close()

    def test_f05_4_persist_all_airlines_and_multi_club_query_fields(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        q = FlightSearchQuery(
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="ALL_AIRLINES",
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            destination_iatas=["FCO"],
            preferred_cabins=["ECONOMY", "BUSINESS"],
            enabled_loyalty_programs=["ELAL_MATMID", "BRITISH_AVIOS"],
            allow_hybrid_bonus_cash=True,
            direct_flights_only=True,
        )
        repo.save_search_query(q)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM flight_search_queries WHERE airline_selection_mode = 'ALL_AIRLINES' LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(
                json.loads(row["preferred_cabins_json"]), ["ECONOMY", "BUSINESS"]
            )
            self.assertEqual(
                json.loads(row["enabled_loyalty_programs_json"]),
                ["ELAL_MATMID", "BRITISH_AVIOS"],
            )
        finally:
            conn.close()

    def test_f05_5_flight_search_query_domain_model_roundtrip(self) -> None:
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            airline_selection_mode="EL_AL_ONLY",
            direct_holiday_code="SUKKOT",
            direct_target_year=2026,
            destination_iatas=["ATH", "FCO"],
            min_trip_nights=5,
            max_trip_nights=9,
        )
        dumped = q.model_dump()
        restored = FlightSearchQuery.model_validate(dumped)
        self.assertEqual(restored.id, q.id)
        self.assertEqual(restored.direct_holiday_code, "SUKKOT")
        self.assertEqual(restored.direct_target_year, 2026)
        self.assertEqual(restored.destination_iatas, ["ATH", "FCO"])


# ============================================================================
# Feature F06: elal_bonus_availability SQLite Table (5 tests)
# ============================================================================
class TestTier1F06ElAlBonusAvailability(Tier1BaseTestCase):
    def test_f06_1_seeded_elal_bonus_availability_inventory(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        try:
            total, zones = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT award_zone) FROM elal_bonus_availability"
            ).fetchone()
            self.assertGreater(total, 20)
            self.assertEqual(zones, 5)
        finally:
            conn.close()

    def test_f06_2_canonical_rome_ly381_ly384_award_rows(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            out_row = conn.execute(
                """
                SELECT * FROM elal_bonus_availability
                WHERE origin_iata = 'TLV' AND destination_iata = 'FCO'
                  AND flight_date = '2027-04-11'
                """
            ).fetchone()
            in_row = conn.execute(
                """
                SELECT * FROM elal_bonus_availability
                WHERE origin_iata = 'FCO' AND destination_iata = 'TLV'
                  AND flight_date = '2027-04-18'
                """
            ).fetchone()
            self.assertIsNotNone(out_row)
            self.assertIsNotNone(in_row)
            self.assertGreaterEqual(out_row["economy_award_seats"], 2)
            self.assertEqual(out_row["economy_seats_is_two_plus"], 1)
            self.assertEqual(out_row["award_zone"], "ZONE_B")
            self.assertGreaterEqual(in_row["economy_award_seats"], 2)
        finally:
            conn.close()

    def test_f06_3_rbd_codes_and_points_taxes_columns(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM elal_bonus_availability LIMIT 25"
            ).fetchall()
            self.assertGreater(len(rows), 0)
            for r in rows:
                self.assertIn(r["economy_rbd_code"], ("E", "X", "U"))
                self.assertIn(r["premium_rbd_code"], ("P", "A", "R"))
                self.assertIn(r["business_rbd_code"], ("I", "W"))
                self.assertGreater(r["taxes_usd_per_pax"], 0.0)
                self.assertTrue(
                    str(r["source_url"]).startswith("https://www.elal.com/rbddataclients")
                )
        finally:
            conn.close()

    def test_f06_4_ttl_timestamps_and_index_idx_elal_bonus_route_date(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            indexes = {
                row[1]
                for row in conn.execute(
                    "PRAGMA index_list('elal_bonus_availability')"
                ).fetchall()
            }
            self.assertIn("idx_elal_bonus_route_date", indexes)
            sample = conn.execute(
                "SELECT fetched_at, expires_at FROM elal_bonus_availability LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(sample)
            self.assertGreater(str(sample["expires_at"]), str(sample["fetched_at"]))
        finally:
            conn.close()

    def test_f06_5_elal_bonus_availability_domain_serialization(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM elal_bonus_availability WHERE destination_iata = 'FCO' LIMIT 1"
            ).fetchone()
            avail = ElAlBonusAvailability.from_dict(dict(row))
            rt = ElAlBonusAvailability.from_dict(avail.to_dict())
            self.assertEqual(rt.id, avail.id)
            self.assertEqual(rt.flight_number, avail.flight_number)
            self.assertEqual(rt.destination_iata, "FCO")
            self.assertEqual(rt.award_zone, "ZONE_B")
        finally:
            conn.close()


# ============================================================================
# Feature F07: flight_itineraries SQLite Table (5 tests)
# ============================================================================
class TestTier1F07FlightItineraries(Tier1BaseTestCase):
    def test_f07_1_search_persists_flight_itineraries_rows(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        planner = self.get_planner(repo)
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
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM flight_itineraries").fetchall()
            self.assertGreater(len(rows), 0)
            self.assertTrue(len(json.loads(rows[0]["outbound_legs_json"])) >= 1)
            self.assertTrue(len(json.loads(rows[0]["inbound_legs_json"])) >= 1)
        finally:
            conn.close()

    def test_f07_2_family_ticket_allocation_and_points_used_by_wallet_json(
        self,
    ) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        planner = self.get_planner(repo)
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            }
        )
        bonus_props = [
            p for p in proposals if _get_field(p.itinerary, "utilizes_elal_bonus")
        ]
        self.assertGreater(len(bonus_props), 0)
        itin = bonus_props[0].itinerary
        assert itin is not None
        self.assertGreaterEqual(itin.seated_passengers_count, 1)
        self.assertGreaterEqual(itin.bonus_tickets_count, 1)
        dumped = _assert_run11_proposal_contract(self, bonus_props[0])
        self.assertNotIn("family_ticket_allocation", dumped)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM flight_itineraries WHERE id = ?", (itin.id,)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["points_used_by_wallet_json"], "{}")
            self.assertEqual(row["total_matmid_points"], 0)
        finally:
            conn.close()

    def test_f07_3_persisted_search_for_signed_in_profile_omits_financial_fields(
        self,
    ) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)
        prof = self.get_default_profile(db_path)
        self.authenticate_test_client(
            client, email="f07_3_saved@gmail.com", profile=prof
        )
        resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreater(body["count"], 0)
        _assert_run11_search_response_contract(self, body, is_bonus_search=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            itin_rows = conn.execute("SELECT * FROM flight_itineraries").fetchall()
            prop_rows = conn.execute("SELECT * FROM vacation_option_proposals").fetchall()
            self.assertGreaterEqual(len(itin_rows), body["count"])
            self.assertGreaterEqual(len(prop_rows), body["count"])
            for row in itin_rows:
                self.assertEqual(row["total_taxes_and_fees_usd"], 0.0)
                self.assertEqual(row["total_supplemental_cash_fares_usd"], 0.0)
                self.assertEqual(row["total_baggage_fees_usd"], 0.0)
                self.assertEqual(row["total_out_of_pocket_cash_usd"], 0.0)
                self.assertEqual(row["full_cash_benchmark_usd"], 0.0)
                self.assertEqual(row["net_cash_saved_usd"], 0.0)
                self.assertIsNone(row["cents_per_point_value"])
                self.assertEqual(row["total_matmid_points"], 0)
            for prow in prop_rows:
                for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
                    self.assertNotIn(forbidden, prow["explanation_summary_he"])
        finally:
            conn.close()

    def test_f07_4_verification_and_deep_link_urls_populated(self) -> None:
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
        self.assertGreater(len(proposals), 0)
        itin = proposals[0].itinerary
        assert itin is not None
        self.assertTrue(
            str(itin.rbddataclients_verify_url).startswith(
                "https://www.elal.com/rbddataclients"
            )
        )
        self.assertTrue(str(itin.booking_deep_link_url).startswith("http"))

    def test_f07_5_flight_itinerary_and_leg_domain_serialization(self) -> None:
        leg = FlightLeg(
            flight_number="LY381",
            origin_iata="TLV",
            destination_iata="FCO",
            flight_date=date(2027, 4, 11),
        )
        itin = FlightItinerary(
            origin_iata="TLV",
            destination_iata="FCO",
            return_origin_iata="FCO",
            departure_date=date(2027, 4, 11),
            return_date=date(2027, 4, 18),
            trip_nights=7,
            outbound_legs=[leg],
            inbound_legs=[leg],
            seated_passengers_count=2,
            bonus_tickets_count=2,
            cash_tickets_count=0,
            primary_cabin="ECONOMY",
            bonus_direction_coverage="BOTH_DIRECTIONS",
            outbound_bonus_seats=2,
            inbound_bonus_seats=2,
            outbound_bonus_seats_is_two_plus=True,
            inbound_bonus_seats_is_two_plus=False,
            min_points_per_bonus_ticket=30000,
            min_points_basis="ROUND_TRIP",
            points_are_estimated=True,
        )
        dumped = _assert_run11_itinerary_contract(self, itin)
        self.assertNotIn("family_ticket_allocation", dumped)
        self.assertEqual(dumped["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(dumped["outbound_bonus_seats"], 2)
        self.assertEqual(dumped["inbound_bonus_seats"], 2)
        self.assertTrue(dumped["outbound_bonus_seats_is_two_plus"])
        self.assertFalse(dumped["inbound_bonus_seats_is_two_plus"])
        self.assertEqual(dumped["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(dumped["min_points_basis"], "ROUND_TRIP")
        restored = FlightItinerary.from_dict(dumped)
        self.assertEqual(restored.destination_iata, "FCO")
        self.assertEqual(len(restored.outbound_legs), 1)
        self.assertEqual(restored.seated_passengers_count, 2)
        self.assertEqual(restored.bonus_tickets_count, 2)
        self.assertEqual(restored.bonus_direction_coverage, "BOTH_DIRECTIONS")
        self.assertEqual(restored.outbound_bonus_seats, 2)
        self.assertEqual(restored.inbound_bonus_seats, 2)
        self.assertTrue(restored.outbound_bonus_seats_is_two_plus)
        self.assertFalse(restored.inbound_bonus_seats_is_two_plus)
        self.assertEqual(restored.min_points_per_bonus_ticket, 30000)
        self.assertEqual(restored.min_points_basis, "ROUND_TRIP")
        self.assertIs(restored.points_are_estimated, True)


# ============================================================================
# Feature F08: vacation_option_proposals SQLite Table (5 tests)
# ============================================================================
class TestTier1F08VacationOptionProposals(Tier1BaseTestCase):
    def test_f08_1_search_persists_vacation_option_proposals_rows(self) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        planner = self.get_planner(repo)
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
        conn = sqlite3.connect(str(db_path))
        try:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM vacation_option_proposals"
            ).fetchone()[0]
            self.assertGreaterEqual(cnt, len(proposals))
        finally:
            conn.close()

    def test_f08_2_proposal_scores_within_0_to_100_and_ctos_formula(self) -> None:
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
            self.assertGreaterEqual(p.holiday_alignment_score, 0.0)
            self.assertLessEqual(p.holiday_alignment_score, 100.0)
            self.assertNotIn("parent_pto_days_used", p.to_dict())
            self.assertNotIn("pto_efficiency_ratio", p.to_dict())
            self.assertGreaterEqual(p.flight_bonus_value_score, 0.0)
            self.assertLessEqual(p.flight_bonus_value_score, 100.0)
            self.assertGreaterEqual(p.combined_trip_optimization_score, 0.0)
            self.assertLessEqual(p.combined_trip_optimization_score, 100.0)
            expected_ctos = (
                0.55 * p.holiday_alignment_score
                + 0.45 * p.flight_bonus_value_score
            )
            self.assertAlmostEqual(
                p.combined_trip_optimization_score, expected_ctos, delta=0.5
            )

    def test_f08_3_per_child_impact_json_and_absence_counts(self) -> None:
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
        self.assertGreater(len(proposals), 0)
        p = proposals[0]
        self.assertEqual(len(p.per_child_impact), 3)
        missed_list = [c.bridge_school_days_missed for c in p.per_child_impact]
        self.assertEqual(
            p.total_school_days_missed_across_children, sum(missed_list)
        )
        self.assertEqual(p.max_single_child_school_days_missed, max(missed_list))

    def test_f08_4_hebrew_explanation_summary_and_holiday_codes(self) -> None:
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
        p = proposals[0]
        self.assertTrue(len(p.explanation_summary_he) > 0)
        self.assertTrue(
            any("\u0590" <= ch <= "\u05ff" for ch in p.explanation_summary_he)
        )
        self.assertIn(
            p.window_set_type,
            (
                "STRICT_INTERSECTION",
                "CAMP_ADJUSTED_INTERSECTION",
                "FRAMEWORK_DELTA_UNION",
                "SPECIFIC_USER_WINDOW",
            ),
        )

    def test_f08_5_index_idx_proposals_query_rank_and_descending_ctos_order(
        self,
    ) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        try:
            indexes = {
                row[1]
                for row in conn.execute(
                    "PRAGMA index_list('vacation_option_proposals')"
                ).fetchall()
            }
            self.assertIn("idx_proposals_query_rank", indexes)
        finally:
            conn.close()
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO", "ATH"],
            }
        )
        scores = [p.combined_trip_optimization_score for p in proposals]
        self.assertEqual(scores, sorted(scores, reverse=True))


# ============================================================================
# Feature F09: 8 MoE Framework Schedules (MoECalendarService) (5 tests)
# ============================================================================
class TestTier1F09MoEFrameworkSchedules(Tier1BaseTestCase):
    def test_f09_1_daycare_supervised_and_special_ed_august_schedules(self) -> None:
        cal = self.get_calendar_service()
        daycare_child = ChildFramework(
            child_age_years=2, framework_type="DAYCARE_SUPERVISED"
        )
        spec_ed_child = ChildFramework(
            child_age_years=10, framework_type="SPECIAL_ED"
        )
        s_dc_before = cal.get_child_day_status(daycare_child, date(2027, 8, 5))
        s_dc_after = cal.get_child_day_status(daycare_child, date(2027, 8, 12))
        self.assertGreater(s_dc_before.psi_penalty, 0.0)
        self.assertEqual(s_dc_after.state_code, "VACATION")
        self.assertAlmostEqual(s_dc_after.psi_penalty, 0.0)

        s_se_before = cal.get_child_day_status(spec_ed_child, date(2027, 8, 12))
        s_se_after = cal.get_child_day_status(spec_ed_child, date(2027, 8, 18))
        self.assertGreater(s_se_before.psi_penalty, 0.0)
        self.assertEqual(s_se_after.state_code, "VACATION")
        self.assertAlmostEqual(s_se_after.psi_penalty, 0.0)

    def test_f09_2_municipal_gan_and_elementary_1_3_nitzanim_vs_elementary_4_6(
        self,
    ) -> None:
        cal = self.get_calendar_service()
        gan_child = ChildFramework(
            child_age_years=5,
            framework_type="MUNICIPAL_GAN",
            holiday_extension_mode="NITZANIM_FULL_WITH_JULY",
            treat_camp_as_vacation=True,
        )
        e13_child = ChildFramework(
            child_age_years=7,
            framework_type="ELEMENTARY_1_3",
            holiday_extension_mode="NITZANIM_FULL_WITH_JULY",
            treat_camp_as_vacation=True,
        )
        e46_child = ChildFramework(
            child_age_years=10,
            framework_type="ELEMENTARY_4_6",
            holiday_extension_mode="NONE",
        )
        for d in (date(2027, 4, 14), date(2027, 7, 8)):
            st_gan = cal.get_child_day_status(gan_child, d)
            st_e13 = cal.get_child_day_status(e13_child, d)
            st_e46 = cal.get_child_day_status(e46_child, d)
            self.assertEqual(st_gan.state_code, "CAMP_OPTIONAL")
            self.assertAlmostEqual(st_gan.psi_penalty, 0.15)
            self.assertEqual(st_e13.state_code, "CAMP_OPTIONAL")
            self.assertAlmostEqual(st_e13.psi_penalty, 0.15)
            self.assertEqual(st_e46.state_code, "VACATION")
            self.assertAlmostEqual(st_e46.psi_penalty, 0.0)

    def test_f09_3_middle_school_7_9_hybrid_rule_isru_chag_and_june_20(self) -> None:
        cal = self.get_calendar_service()
        mid_child = ChildFramework(
            child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5
        )
        e46_child = ChildFramework(
            child_age_years=10, framework_type="ELEMENTARY_4_6", school_week_days=5
        )
        self.assertEqual(
            cal.get_child_day_status(mid_child, date(2026, 10, 4)).state_code,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            cal.get_child_day_status(mid_child, date(2026, 5, 5)).state_code,
            "SCHOOL_REGULAR",
        )
        st_mid_jun = cal.get_child_day_status(mid_child, date(2027, 6, 22))
        st_e46_jun = cal.get_child_day_status(e46_child, date(2027, 6, 22))
        self.assertEqual(st_mid_jun.state_code, "VACATION")
        self.assertAlmostEqual(st_mid_jun.psi_penalty, 0.0)
        self.assertEqual(st_e46_jun.state_code, "SCHOOL_END_OF_YEAR_WANING")
        self.assertAlmostEqual(st_e46_jun.psi_penalty, 0.50)

    def test_f09_4_high_school_10_12_isru_chag_sukkot_and_lag_baomer_5786(
        self,
    ) -> None:
        cal = self.get_calendar_service()
        hs_child = ChildFramework(
            child_age_years=16, framework_type="HIGH_SCHOOL_10_12", school_week_days=5
        )
        for d in (date(2025, 10, 15), date(2026, 10, 4), date(2026, 5, 5)):
            st = cal.get_child_day_status(hs_child, d)
            self.assertEqual(st.state_code, "VACATION")
            self.assertAlmostEqual(st.psi_penalty, 0.0)

    def test_f09_5_five_day_vs_six_day_school_week_friday_status_and_religious_haredi(
        self,
    ) -> None:
        cal = self.get_calendar_service()
        c5 = ChildFramework(
            child_age_years=8, framework_type="ELEMENTARY_1_3", school_week_days=5
        )
        c6 = ChildFramework(
            child_age_years=8, framework_type="ELEMENTARY_1_3", school_week_days=6
        )
        st5 = cal.get_child_day_status(c5, date(2026, 11, 13))
        st6 = cal.get_child_day_status(c6, date(2026, 11, 13))
        self.assertAlmostEqual(st5.psi_penalty, 0.0)
        self.assertEqual(st6.state_code, "SCHOOL_FRIDAY")
        self.assertAlmostEqual(st6.psi_penalty, 0.35)
        haredi_wins = cal.get_calendar_windows("2026-2027", "RELIGIOUS_HAREDI")
        self.assertGreater(len(haredi_wins), 0)


# ============================================================================
# Feature F10: Verified Pre-Seeded 5786 & 5787 Calendars (5 tests)
# ============================================================================
class TestTier1F10VerifiedPreSeededCalendars(Tier1BaseTestCase):
    def test_f10_1_bundled_moe_calendar_json_files_and_schema_exist(self) -> None:
        cal_dir = PROJECT_ROOT / "backend" / "calendars"
        files = [
            cal_dir / "moe_5786_2025_2026.json",
            cal_dir / "moe_5787_2026_2027.json",
            cal_dir / "moe_5788_2027_2028.json",
            cal_dir / "schema" / "moe_calendar.schema.json",
        ]
        for fpath in files:
            self.assertTrue(fpath.exists(), f"Missing calendar file: {fpath}")
            parsed = json.loads(fpath.read_text(encoding="utf-8"))
            self.assertIsInstance(parsed, dict)
            if "moe_578" in fpath.name:
                for key in (
                    "school_year_hebrew",
                    "school_year_gregorian",
                    "circular_ids",
                    "frameworks",
                    "periods",
                ):
                    self.assertIn(key, parsed)

    def test_f10_2_5786_2025_2026_exact_circular_holiday_dates(self) -> None:
        cal = self.get_calendar_service()
        wins = cal.get_calendar_windows("2025-2026", "ELEMENTARY_4_6")
        by_code = {w.holiday_code: w for w in wins}
        self.assertEqual(by_code["ROSH_HASHANAH"].start_date, date(2025, 9, 22))
        self.assertEqual(by_code["ROSH_HASHANAH"].end_date, date(2025, 9, 24))
        self.assertEqual(by_code["HANUKKAH"].start_date, date(2025, 12, 16))
        self.assertEqual(by_code["HANUKKAH"].end_date, date(2025, 12, 22))
        self.assertEqual(by_code["PURIM"].start_date, date(2026, 3, 3))
        self.assertEqual(by_code["PURIM"].end_date, date(2026, 3, 4))
        self.assertEqual(by_code["PESACH"].start_date, date(2026, 3, 24))
        self.assertEqual(by_code["PESACH"].end_date, date(2026, 4, 8))

    def test_f10_3_5787_2026_2027_exact_circular_holiday_dates(self) -> None:
        cal = self.get_calendar_service()
        wins = cal.get_calendar_windows("2026-2027", "ELEMENTARY_4_6")
        by_code = {w.holiday_code: w for w in wins}
        self.assertEqual(by_code["ROSH_HASHANAH"].start_date, date(2026, 9, 11))
        self.assertEqual(by_code["ROSH_HASHANAH"].end_date, date(2026, 9, 13))
        self.assertEqual(by_code["HANUKKAH"].start_date, date(2026, 12, 6))
        self.assertEqual(by_code["HANUKKAH"].end_date, date(2026, 12, 12))
        self.assertEqual(by_code["PURIM"].start_date, date(2027, 3, 23))
        self.assertEqual(by_code["PURIM"].end_date, date(2027, 3, 24))
        self.assertEqual(by_code["PESACH"].start_date, date(2027, 4, 13))
        self.assertEqual(by_code["PESACH"].end_date, date(2027, 4, 28))
        self.assertEqual(by_code["SHAVUOT"].start_date, date(2027, 6, 10))
        self.assertEqual(by_code["SHAVUOT"].end_date, date(2027, 6, 11))

    def test_f10_4_lag_baomer_5786_vs_5787_divergence(self) -> None:
        cal = self.get_calendar_service()
        hs = ChildFramework(child_age_years=16, framework_type="HIGH_SCHOOL_10_12")
        elem = ChildFramework(child_age_years=10, framework_type="ELEMENTARY_4_6")
        self.assertEqual(
            cal.get_child_day_status(hs, date(2026, 5, 5)).state_code, "VACATION"
        )
        self.assertEqual(
            cal.get_child_day_status(elem, date(2026, 5, 5)).state_code,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            cal.get_child_day_status(hs, date(2027, 5, 25)).state_code,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            cal.get_child_day_status(elem, date(2027, 5, 25)).state_code,
            "SCHOOL_REGULAR",
        )

    def test_f10_5_june_20_2026_saturday_shift_for_5day_vs_6day_schools(self) -> None:
        cal = self.get_calendar_service()
        mid5 = ChildFramework(
            child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=5
        )
        mid6 = ChildFramework(
            child_age_years=13, framework_type="MIDDLE_SCHOOL_7_9", school_week_days=6
        )
        self.assertAlmostEqual(
            cal.get_child_day_status(mid5, date(2026, 6, 19)).psi_penalty, 0.0
        )
        self.assertEqual(
            cal.get_child_day_status(mid5, date(2026, 6, 21)).state_code, "VACATION"
        )
        self.assertEqual(
            cal.get_child_day_status(mid6, date(2026, 6, 21)).state_code, "VACATION"
        )


# ============================================================================
# Feature F11: Annual MoE Calendar Auto-Updater (5 tests)
# ============================================================================
class TestTier1F11MoECalendarAutoUpdater(Tier1BaseTestCase):
    def test_f11_1_sync_school_year_2027_2028_5788(self) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        updater = self.get_auto_updater(repo)
        status = updater.sync_school_year("2027-2028")
        self.assertEqual(status.school_year, "2027-2028")
        self.assertIn("תשפ", status.school_year_hebrew)
        self.assertGreaterEqual(status.windows_synced_count, 8)

    def test_f11_2_sync_future_school_year_2028_2029_statutory_projection(
        self,
    ) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        updater = self.get_auto_updater(repo)
        status = updater.sync_school_year("2028-2029")
        self.assertEqual(status.school_year, "2028-2029")
        self.assertEqual(status.calendar_sync_source, "HEBREW_RULE_PROJECTED")
        self.assertGreaterEqual(status.windows_synced_count, 8)
        codes = {w.holiday_code for w in status.windows}
        for req in ("ROSH_HASHANAH", "HANUKKAH", "PURIM", "PESACH", "SHAVUOT"):
            self.assertIn(req, codes)

    def test_f11_3_normalize_four_digit_year_input_in_sync(self) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        updater = self.get_auto_updater(repo)
        s27 = updater.sync_school_year("2027")
        s28 = updater.sync_school_year("2028")
        self.assertEqual(s27.school_year, "2026-2027")
        self.assertEqual(s28.school_year, "2027-2028")

    def test_f11_4_projected_future_year_contains_nitzanim_and_kippur_closure(
        self,
    ) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        updater = self.get_auto_updater(repo)
        updater.sync_school_year("2028-2029")
        cal = self.get_calendar_service(repo)
        wins = cal.get_calendar_windows("2028-2029")
        gan_pesach = [
            w
            for w in wins
            if _get_field(w, "framework_type") == "MUNICIPAL_GAN"
            and w.holiday_code == "PESACH"
        ]
        self.assertGreater(len(gan_pesach), 0)
        self.assertTrue(gan_pesach[0].is_covered_by_nitzanim)
        kippur_wins = [w for w in wins if "KIPPUR" in w.holiday_code]
        self.assertTrue(any(w.tlv_airport_closed for w in kippur_wins))

    def test_f11_5_get_moe_calendar_endpoint_auto_projects_unseeded_future_year(
        self,
    ) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)
        resp = client.get("/api/v1/moe-calendar/2029-2030")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["school_year"], "2029-2030")
        self.assertGreater(len(body["windows"]), 0)


# ============================================================================
# Feature F12: Mode 1 (SPECIFIC_DATES) with Optional Frameworks (5 tests)
# ============================================================================
class TestTier1F12Mode1SpecificDates(Tier1BaseTestCase):
    def test_f12_1_classify_passenger_type_by_age_and_infant_seat(self) -> None:
        self.assertEqual(classify_passenger_type(0, infant_seat=False), "INFANT_LAP")
        self.assertEqual(classify_passenger_type(1, infant_seat=True), "INFANT_SEAT")
        self.assertEqual(classify_passenger_type(6), "CHILD")
        self.assertEqual(classify_passenger_type(14), "YOUTH")

    def test_f12_2_suggest_framework_for_age_across_all_age_brackets(self) -> None:
        self.assertEqual(suggest_framework_for_age(1), "DAYCARE_SUPERVISED")
        self.assertEqual(suggest_framework_for_age(4), "MUNICIPAL_GAN")
        self.assertEqual(suggest_framework_for_age(7), "ELEMENTARY_1_3")
        self.assertEqual(suggest_framework_for_age(10), "ELEMENTARY_4_6")
        self.assertEqual(suggest_framework_for_age(13), "MIDDLE_SCHOOL_7_9")
        self.assertEqual(suggest_framework_for_age(16), "HIGH_SCHOOL_10_12")

    def test_f12_3_mode1_exact_specific_dates_with_null_frameworks(self) -> None:
        prof = FamilyProfile(
            id="prof-mode1-null",
            adults_count=2,
            matmid_points_balance=185000,
            children=[
                ChildFramework(child_age_years=1, framework_type=None),
                ChildFramework(child_age_years=6, framework_type=None),
                ChildFramework(child_age_years=14, framework_type=None),
            ],
        )
        q = FlightSearchQuery(
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="EL_AL_ONLY",
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            flex_days_plus_minus=0,
            destination_iatas=["FCO"],
        )
        maximizer = self.get_maximizer()
        windows = maximizer.generate_candidate_windows(q, prof)
        self.assertGreaterEqual(len(windows), 1)
        self.assertEqual(windows[0].start_date, date(2027, 4, 11))
        self.assertEqual(windows[0].end_date, date(2027, 4, 18))
        self.assertEqual(windows[0].window_set_type, "SPECIFIC_USER_WINDOW")

    def test_f12_4_mode1_flexible_dates_expansion_within_min_max_nights(self) -> None:
        prof = self.get_default_profile()
        q = FlightSearchQuery(
            date_selection_mode="SPECIFIC_DATES",
            airline_selection_mode="EL_AL_ONLY",
            specific_departure_date=date(2027, 4, 13),
            specific_return_date=date(2027, 4, 20),
            flex_days_plus_minus=2,
            min_trip_nights=6,
            max_trip_nights=8,
            destination_iatas=["FCO"],
        )
        maximizer = self.get_maximizer()
        windows = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(windows), 1)
        for w in windows:
            nights = (w.end_date - w.start_date).days
            self.assertGreaterEqual(nights, 6)
            self.assertLessEqual(nights, 8)
            self.assertLessEqual(abs((w.start_date - date(2027, 4, 13)).days), 2)
            self.assertLessEqual(abs((w.end_date - date(2027, 4, 20)).days), 2)

    def test_f12_5_mode1_with_configured_frameworks_computes_moe_impact_overlay(
        self,
    ) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
            }
        )
        self.assertGreater(len(proposals), 0)
        p = proposals[0]
        self.assertEqual(len(p.per_child_impact), 3)
        self.assertNotIn("parent_pto_days_used", p.to_dict())
        self.assertGreater(p.holiday_alignment_score, 0.0)


# ============================================================================
# Feature F13: Multi-Child Holiday Overlap & Bridge-Shift Optimizer (5 tests)
# ============================================================================
class TestTier1F13Mode2MoEVacationMaximization(Tier1BaseTestCase):
    def test_f13_1_strict_all_children_off_intersection_set_i(self) -> None:
        prof = self.get_default_profile()
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            direct_holiday_code="PESACH",
            direct_target_year=2027,
            overlap_policy="STRICT_ALL_CHILDREN_OFF",
            max_bridge_days_shift=0,
            min_trip_nights=4,
            max_trip_nights=9,
        )
        maximizer = self.get_maximizer()
        windows = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(windows), 0)
        for w in windows:
            self.assertEqual(w.total_school_days_missed_across_children, 0)

    def test_f13_2_camp_adjusted_intersection_set_i_camp(self) -> None:
        prof = self.get_default_profile()
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            school_year="2026-2027",
            target_holiday_codes=["HANUKKAH", "PESACH"],
            overlap_policy="CAMP_ADJUSTED_INTERSECTION",
            max_bridge_days_shift=0,
            min_trip_nights=4,
            max_trip_nights=8,
        )
        maximizer = self.get_maximizer()
        windows = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(windows), 0)
        self.assertTrue(
            any(
                "HANUKKAH" in w.associated_holiday_codes
                or "PESACH" in w.associated_holiday_codes
                for w in windows
            )
        )

    def test_f13_3_framework_delta_union_set_u_june_20_30_arbitrage(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        w = maximizer.evaluate_window(
            prof,
            date(2027, 6, 21),
            date(2027, 6, 28),
            window_set_type="FRAMEWORK_DELTA_UNION",
            associated_holidays=["SUMMER_JUNE_20_30"],
        )
        by_name = {c.child_name: c for c in w.per_child_impact}
        self.assertEqual(by_name["מאיה"].bridge_school_days_missed, 0)
        self.assertAlmostEqual(by_name["מאיה"].weighted_absence_score, 0.0)
        self.assertTrue(
            any(
                d.state_code == "SCHOOL_END_OF_YEAR_WANING"
                for d in by_name["עידו"].daily_breakdown
            )
        )

    def test_f13_4_bridge_days_expansion_unlocks_pre_pesach_and_purim_windows(
        self,
    ) -> None:
        prof = self.get_default_profile()
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            school_year="2026-2027",
            target_holiday_codes=["PESACH", "PURIM"],
            max_bridge_days_shift=2,
            min_trip_nights=4,
            max_trip_nights=8,
            overlap_policy="CAMP_ADJUSTED_INTERSECTION",
        )
        maximizer = self.get_maximizer()
        windows = maximizer.generate_candidate_windows(q, prof)
        self.assertGreater(len(windows), 0)
        self.assertTrue(
            any(
                w.bridge_days_used > 0
                or w.max_single_child_school_days_missed > 0
                or w.start_date == date(2027, 4, 11)
                for w in windows
            )
        )

    def test_f13_5_filters_out_bagrut_blackouts_and_tlv_yom_kippur_departures(
        self,
    ) -> None:
        prof = self.get_default_profile()
        prof.children.append(
            ChildFramework(
                id="c-hs-blk",
                child_name="דניאל",
                child_age_years=16,
                framework_type="HIGH_SCHOOL_10_12",
                bagrut_blackout_dates=[date(2027, 4, 15)],
            )
        )
        q = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            school_year="2026-2027",
            target_holiday_codes=["PESACH", "YOM_KIPPUR_SUKKOT"],
            max_bridge_days_shift=2,
            min_trip_nights=4,
            max_trip_nights=8,
        )
        maximizer = self.get_maximizer()
        windows = maximizer.generate_candidate_windows(q, prof)
        for w in windows:
            self.assertFalse(w.start_date <= date(2027, 4, 15) <= w.end_date)
            self.assertNotIn(w.start_date, (date(2026, 9, 20), date(2026, 9, 21)))
            self.assertNotIn(w.end_date, (date(2026, 9, 20), date(2026, 9, 21)))


# ============================================================================
# Feature F14: Mode 3 (HOLIDAY_DIRECT_INTENT) Maximizer (5 tests)
# ============================================================================
class TestTier1F14Mode3HolidayDirectIntent(Tier1BaseTestCase):
    def test_f14_1_direct_intent_pesach_2027_maximizer(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO"],
                "min_trip_nights": 6,
                "max_trip_nights": 8,
                "max_bridge_days_shift": 2,
            }
        )
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            self.assertIn("PESACH", p.associated_holiday_codes)
            assert p.itinerary is not None
            self.assertEqual(p.itinerary.departure_date.month, 4)
            self.assertEqual(p.itinerary.departure_date.year, 2027)

    def test_f14_2_direct_intent_sukkot_and_kippur_sukkot_bridge_2026(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        for code in ("SUKKOT", "YOM_KIPPUR_SUKKOT"):
            q = FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                direct_holiday_code=code,
                direct_target_year=2026,
                min_trip_nights=5,
                max_trip_nights=12,
                max_bridge_days_shift=2,
            )
            wins = maximizer.generate_candidate_windows(q, prof)
            self.assertGreater(len(wins), 0)
            for w in wins:
                self.assertNotIn(
                    w.start_date, (date(2026, 9, 20), date(2026, 9, 21))
                )

    def test_f14_3_direct_intent_hanukkah_2026_and_purim_2027(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        q_han = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            direct_holiday_code="HANUKKAH",
            direct_target_year=2026,
            min_trip_nights=4,
            max_trip_nights=7,
            max_bridge_days_shift=2,
        )
        wins_han = maximizer.generate_candidate_windows(q_han, prof)
        self.assertGreater(len(wins_han), 0)
        self.assertTrue(all(w.start_date.month == 12 for w in wins_han))

        q_pur = FlightSearchQuery(
            date_selection_mode="HOLIDAY_DIRECT_INTENT",
            direct_holiday_code="PURIM",
            direct_target_year=2027,
            min_trip_nights=3,
            max_trip_nights=5,
            max_bridge_days_shift=2,
        )
        wins_pur = maximizer.generate_candidate_windows(q_pur, prof)
        self.assertGreater(len(wins_pur), 0)
        self.assertTrue(all(w.start_date.month == 3 for w in wins_pur))

    def test_f14_4_direct_intent_rosh_hashanah_shavuot_and_yom_haatzmaut(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        for code, yr, exp_month in (
            ("ROSH_HASHANAH", 2026, 9),
            ("SHAVUOT", 2027, 6),
            ("YOM_HAATZMAUT", 2027, 5),
        ):
            q = FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                direct_holiday_code=code,
                direct_target_year=yr,
                min_trip_nights=3,
                max_trip_nights=5,
                max_bridge_days_shift=2,
            )
            wins = maximizer.generate_candidate_windows(q, prof)
            self.assertGreater(len(wins), 0, f"No windows for {code} {yr}")
            self.assertTrue(any(w.start_date.month == exp_month for w in wins))

    def test_f14_5_direct_intent_summer_june_20_30_july_and_august(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        for code, exp_month in (
            ("SUMMER_JUNE_20_30", 6),
            ("SUMMER_JULY", 7),
            ("SUMMER_AUGUST", 8),
        ):
            q = FlightSearchQuery(
                date_selection_mode="HOLIDAY_DIRECT_INTENT",
                direct_holiday_code=code,
                direct_target_year=2027,
                min_trip_nights=4,
                max_trip_nights=8,
                max_bridge_days_shift=2,
            )
            wins = maximizer.generate_candidate_windows(q, prof)
            self.assertGreater(len(wins), 0)
            self.assertTrue(any(w.start_date.month == exp_month for w in wins))


# ============================================================================
# Feature F15: Mathematical Calendar Scoring Engine (SAP, CCG, HAS) (5 tests)
# ============================================================================
class TestTier1F15CalendarScoringEngine(Tier1BaseTestCase):
    def test_f15_1_worked_example_1_kippur_sukkot_mega_bridge_and_subwindow(
        self,
    ) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        w12 = maximizer.evaluate_window(prof, date(2026, 9, 22), date(2026, 10, 3))
        self.assertEqual(w12.trip_nights, 11)
        self.assertAlmostEqual(w12.school_absence_penalty, 0.0)
        self.assertAlmostEqual(w12.childcare_coverage_gain, 1.0)
        self.assertEqual(w12.holiday_alignment_score, 100.0)

        w8 = maximizer.evaluate_window(prof, date(2026, 9, 25), date(2026, 10, 2))
        self.assertEqual(w8.trip_nights, 7)
        self.assertAlmostEqual(w8.school_absence_penalty, 0.0)
        self.assertEqual(w8.holiday_alignment_score, 100.0)

    def test_f15_2_worked_example_3_purim_long_weekend_bridge(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        w = maximizer.evaluate_window(prof, date(2027, 3, 23), date(2027, 3, 27))
        self.assertEqual(w.trip_nights, 4)
        self.assertEqual(w.max_single_child_school_days_missed, 1)
        self.assertGreater(w.school_absence_penalty, 0.0)
        self.assertLess(w.school_absence_penalty, 1.2)
        self.assertAlmostEqual(w.holiday_alignment_score, 64.8, places=1)

    def test_f15_3_worked_example_4_pesach_pre_holiday_bridge_vs_uncovered_week(
        self,
    ) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        w_bridge = maximizer.evaluate_window(prof, date(2027, 4, 11), date(2027, 4, 18))
        w_uncov = maximizer.evaluate_window(prof, date(2027, 4, 20), date(2027, 4, 27))
        self.assertAlmostEqual(w_uncov.school_absence_penalty, 0.0)
        self.assertAlmostEqual(w_uncov.childcare_coverage_gain, 1.0)
        self.assertEqual(w_uncov.holiday_alignment_score, 100.0)
        self.assertEqual(w_bridge.max_single_child_school_days_missed, 2)
        self.assertGreater(w_bridge.holiday_alignment_score, 60.0)
        self.assertLess(w_bridge.holiday_alignment_score, w_uncov.holiday_alignment_score)

    def test_f15_4_worked_example_5_shavuot_extended_weekend(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        w = maximizer.evaluate_window(prof, date(2027, 6, 9), date(2027, 6, 12))
        self.assertEqual(w.trip_nights, 3)
        self.assertEqual(w.max_single_child_school_days_missed, 1)
        self.assertAlmostEqual(w.holiday_alignment_score, 67.5, places=1)

    def test_f15_5_worked_example_6_june_20_30_inter_framework_arbitrage(self) -> None:
        prof = self.get_default_profile()
        maximizer = self.get_maximizer()
        w = maximizer.evaluate_window(
            prof,
            date(2027, 6, 21),
            date(2027, 6, 28),
            window_set_type="FRAMEWORK_DELTA_UNION",
        )
        self.assertEqual(w.trip_nights, 7)
        by_name = {c.child_name: c for c in w.per_child_impact}
        self.assertEqual(by_name["מאיה"].bridge_school_days_missed, 0)
        self.assertGreaterEqual(w.holiday_alignment_score, 0.0)
        self.assertLessEqual(w.holiday_alignment_score, 100.0)


# ============================================================================
# Feature F16: Pre-Seeded 2025-2028 Holiday Award & Commercial Dataset (5 tests)
# ============================================================================
class TestTier1F16PreSeededFlightDataset(Tier1BaseTestCase):
    def test_f16_1_seeded_award_inventory_covers_all_five_zones_a_to_e(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        try:
            zones = {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT award_zone FROM elal_bonus_availability"
                ).fetchall()
            }
            self.assertEqual(
                zones, {"ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E"}
            )
        finally:
            conn.close()

    def test_f16_2_seeded_inventory_spans_years_2025_2026_2027_2028(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        try:
            years = {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT substr(flight_date, 1, 4) FROM elal_bonus_availability"
                ).fetchall()
            }
            for yr in ("2025", "2026", "2027", "2028"):
                self.assertIn(yr, years)
        finally:
            conn.close()

    def test_f16_3_flagship_holiday_routes_fco_ath_mad_present(self) -> None:
        repo = self.get_repo()
        fco = repo.get_cached_elal_bonus(
            ["FCO"], date(2027, 4, 11), date(2027, 4, 28)
        )
        ath = repo.get_cached_elal_bonus(
            ["ATH"], date(2026, 12, 6), date(2026, 12, 14)
        )
        mad = repo.get_cached_elal_bonus(
            ["MAD"], date(2027, 6, 21), date(2027, 6, 28)
        )
        self.assertGreaterEqual(len(fco), 2)
        self.assertGreaterEqual(len(ath), 2)
        self.assertGreaterEqual(len(mad), 2)

    def test_f16_4_seeded_commercial_flights_across_elal_and_foreign_carriers(
        self,
    ) -> None:
        repo = self.get_repo()
        offers = repo.get_commercial_flights(
            "TLV", ["FCO", "ATH", "LHR"], date(2027, 4, 11), date(2027, 4, 18)
        )
        self.assertGreater(len(offers), 0)
        carriers = {
            _get_field(o, "primary_carrier_iata") or _get_field(o, "carrier_iata")
            for o in offers
        }
        self.assertIn("LY", carriers)
        self.assertTrue(len(carriers - {"LY", "2U"}) > 0)

    def test_f16_5_seeded_pesach_2028_future_award_and_commercial_availability(
        self,
    ) -> None:
        repo = self.get_repo()
        avail_2028 = repo.get_cached_elal_bonus(
            ["FCO", "ATH"], date(2028, 4, 1), date(2028, 4, 25)
        )
        self.assertGreater(len(avail_2028), 0)


# ============================================================================
# Feature F17: EL_AL_ONLY Mode & Shabbat / Yom Kippur Constraints (5 tests)
# ============================================================================
class TestTier1F17ElAlOnlyAndConstraints(Tier1BaseTestCase):
    def test_f17_1_el_al_only_mode_returns_only_ly_and_2u_carriers(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO", "ATH"],
            }
        )
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            assert p.itinerary is not None
            self.assertTrue(bool(p.itinerary.is_elal_flight))
            self.assertIn(p.itinerary.primary_carrier_iata, ("LY", "2U"))

    def test_f17_2_el_al_shabbat_operational_constraint_enforced(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(
            ["FCO", "ATH", "LHR", "JFK"], date(2026, 9, 1), date(2027, 8, 31)
        )
        self.assertGreater(len(avail), 0)
        for row in avail:
            if row.operating_carrier == "LY":
                dep_hr = int(str(row.departure_time_local).split(":")[0])
                if row.flight_date.weekday() == 5:  # Saturday
                    self.assertGreaterEqual(dep_hr, 18)
                elif row.flight_date.weekday() == 4:  # Friday
                    self.assertLess(dep_hr, 16)

    def test_f17_3_tlv_yom_kippur_shutdown_blocks_flights(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "YOM_KIPPUR_SUKKOT",
                "direct_target_year": 2026,
                "destination_iatas": ["FCO", "ATH"],
            }
        )
        closed_dates = {date(2026, 9, 20), date(2026, 9, 21)}
        for p in proposals:
            assert p.itinerary is not None
            self.assertNotIn(p.itinerary.departure_date, closed_dates)
            self.assertNotIn(p.itinerary.return_date, closed_dates)

    def test_f17_4_include_sundor_flights_toggle_behavior(self) -> None:
        planner = self.get_planner()
        props_no_2u = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "include_sundor_flights": False,
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["RHO", "LCA", "FCO"],
            }
        )
        for p in props_no_2u:
            assert p.itinerary is not None
            self.assertEqual(p.itinerary.primary_carrier_iata, "LY")
            for leg in p.itinerary.outbound_legs + p.itinerary.inbound_legs:
                self.assertNotEqual(leg.operating_carrier, "2U")

    def test_f17_5_el_al_only_enables_rbddataclients_bonus_strategies(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "search_elal_bonus_tickets": True,
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
            }
        )
        self.assertTrue(
            any(
                p.itinerary is not None
                and bool(p.itinerary.utilizes_elal_bonus)
                and _get_field(p.itinerary, "fulfillment_strategy")
                != "COMMERCIAL_CASH_ONLY"
                for p in proposals
            )
        )


# ============================================================================
# Feature F18: ALL_AIRLINES Mode & FamilyBaggageNormalizer (5 tests)
# ============================================================================
class TestTier1F18AllAirlinesAndBaggageNormalizer(Tier1BaseTestCase):
    def test_f18_1_lcc_baggage_normalization_adds_trolley_and_checked_bag_fees(
        self,
    ) -> None:
        comm = self.get_commercial_adapter()
        prof = self.get_default_profile()
        for carrier in ("W6", "FR", "U2"):
            bag_fee, total_cash = comm.normalize_family_baggage_cost(
                carrier, 1000.0, prof, 7
            )
            self.assertGreater(bag_fee, 0.0)
            self.assertAlmostEqual(total_cash, 1000.0 + bag_fee, delta=0.05)

    def test_f18_2_full_service_carrier_baggage_normalization(self) -> None:
        comm = self.get_commercial_adapter()
        prof = self.get_default_profile()
        w6_bag, _ = comm.normalize_family_baggage_cost("W6", 1000.0, prof, 7)
        for carrier in ("LY", "LH", "BA", "AF"):
            bag_fee, total_cash = comm.normalize_family_baggage_cost(
                carrier, 2000.0, prof, 7
            )
            self.assertGreaterEqual(bag_fee, 0.0)
            self.assertLess(bag_fee, w6_bag)
            self.assertAlmostEqual(total_cash, 2000.0 + bag_fee, delta=0.05)

    def test_f18_3_israeli_leisure_carriers_israir_6h_and_arkia_iz_normalization(
        self,
    ) -> None:
        comm = self.get_commercial_adapter()
        prof = self.get_default_profile()
        for carrier in ("6H", "IZ"):
            bag_fee, total_cash = comm.normalize_family_baggage_cost(
                carrier, 1200.0, prof, 5
            )
            self.assertGreaterEqual(bag_fee, 0.0)
            self.assertAlmostEqual(total_cash, 1200.0 + bag_fee, delta=0.05)

    def test_f18_4_search_commercial_flights_returns_multiple_carriers(self) -> None:
        comm = self.get_commercial_adapter()
        prof = self.get_default_profile()
        offers = comm.search_commercial_flights(
            "TLV", ["FCO", "ATH", "BUD", "LHR"], date(2027, 4, 11), date(2027, 4, 18), prof
        )
        self.assertGreater(len(offers), 1)
        carriers = {
            _get_field(o, "primary_carrier_iata") or _get_field(o, "carrier_iata")
            for o in offers
        }
        self.assertGreater(len(carriers), 1)

    def test_f18_5_all_airlines_vacation_search_includes_commercial_and_multi_carrier_options(
        self,
    ) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "ALL_AIRLINES",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO", "ATH", "BUD"],
            }
        )
        self.assertGreater(len(proposals), 0)
        carriers = set()
        for p in proposals:
            itin = _assert_run11_proposal_contract(self, p)
            carriers.add(itin["primary_carrier_iata"])
            self.assertEqual(itin["fulfillment_strategy"], "COMMERCIAL_CASH_ONLY")
            self.assertEqual(itin["bonus_direction_coverage"], "NONE")
            self.assertIsNone(itin["min_points_per_bonus_ticket"])
            self.assertEqual(p.flight_bonus_value_score, 0.0)
        self.assertGreater(len(carriers), 1)


# ============================================================================
# Feature F19: Metro-to-Airport 3-Letter IATA Expansion (5 tests)
# ============================================================================
class TestTier1F19MetroToAirportExpansion(Tier1BaseTestCase):
    def test_f19_1_expand_nyc_and_lon_multi_airport_metro_codes(self) -> None:
        elal = self.get_elal_adapter()
        self.assertEqual(elal.expand_metro_iatas(["NYC"]), ["JFK", "EWR"])
        self.assertEqual(elal.expand_metro_iatas(["LON"]), ["LHR", "LTN"])

    def test_f19_2_expand_par_mil_rom_tyo_single_airport_metro_codes(self) -> None:
        elal = self.get_elal_adapter()
        self.assertEqual(
            elal.expand_metro_iatas(["PAR", "MIL", "ROM", "TYO"]),
            ["CDG", "MXP", "FCO", "NRT"],
        )

    def test_f19_3_expand_mia_area_and_mixed_iata_deduplication(self) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas(["MIA_AREA", "JFK", "NYC"])
        self.assertEqual(len(expanded), len(set(expanded)))
        for code in ("MIA", "FLL", "JFK", "EWR"):
            self.assertIn(code, expanded)

    def test_f19_4_get_award_availability_with_metro_code_rom_and_nyc(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(
            ["ROM", "NYC"], date(2027, 4, 10), date(2027, 4, 25)
        )
        self.assertGreater(len(avail), 0)
        for r in avail:
            self.assertNotIn(r.destination_iata, ("ROM", "NYC"))
            self.assertNotIn(r.origin_iata, ("ROM", "NYC"))

    def test_f19_5_rest_api_elal_bonus_availability_expands_metro_code(self) -> None:
        client = self.get_client()
        resp = client.get(
            "/api/v1/elal-bonus/availability?destination=LON&start_date=2027-04-10&end_date=2027-04-25"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["requested_destination"], "LON")
        self.assertEqual(data["expanded_destinations"], ["LHR", "LTN"])


# ============================================================================
# Feature F20: ANYWHERE Region Discovery (5 tests)
# ============================================================================
class TestTier1F20AnywhereRegionDiscovery(Tier1BaseTestCase):
    def test_f20_1_expand_anywhere_returns_destinations_across_all_five_zones(
        self,
    ) -> None:
        elal = self.get_elal_adapter()
        expanded = elal.expand_metro_iatas(["ANYWHERE"])
        self.assertGreaterEqual(len(expanded), 15)
        for sample in ("ATH", "FCO", "CDG", "LHR", "BKK", "JFK"):
            self.assertIn(sample, expanded)

    def test_f20_2_get_award_availability_anywhere_discovers_multi_destination_seats(
        self,
    ) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(
            ["ANYWHERE"], date(2027, 4, 11), date(2027, 4, 20)
        )
        dests = {
            r.destination_iata if r.origin_iata == "TLV" else r.origin_iata
            for r in avail
        }
        self.assertGreaterEqual(len(dests), 3)

    def test_f20_3_mode2_vacation_search_with_anywhere_discovers_best_destinations(
        self,
    ) -> None:
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
        dests = {p.itinerary.destination_iata for p in proposals if p.itinerary}
        self.assertGreaterEqual(len(dests), 2)

    def test_f20_4_mode3_holiday_direct_intent_with_anywhere(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "HANUKKAH",
                "direct_target_year": 2026,
                "destination_iatas": ["ANYWHERE"],
            }
        )
        self.assertGreater(len(proposals), 0)

    def test_f20_5_rest_api_vacations_search_anywhere_expands_destinations(
        self,
    ) -> None:
        client = self.get_client()
        resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["ANYWHERE"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(len(body["expanded_destinations"]), 10)
        self.assertGreater(body["count"], 0)


# ============================================================================
# Feature F21: Classic Award RBD Bucket & 0/1/2+ Seat Cap Parser (5 tests)
# ============================================================================
class TestTier1F21ClassicAwardRbdAndCache(Tier1BaseTestCase):
    def test_f21_1_seat_cap_two_plus_flags_match_seat_counts(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(
            ["FCO", "ATH", "LHR", "JFK"], date(2026, 9, 1), date(2027, 8, 31)
        )
        self.assertGreater(len(avail), 0)
        for r in avail:
            self.assertEqual(bool(r.economy_seats_is_two_plus), r.economy_award_seats >= 2)
            self.assertEqual(bool(r.premium_seats_is_two_plus), r.premium_award_seats >= 2)
            self.assertEqual(bool(r.business_seats_is_two_plus), r.business_award_seats >= 2)

    def test_f21_2_rbd_bucket_codes_for_economy_premium_and_business(self) -> None:
        elal = self.get_elal_adapter()
        avail = elal.get_award_availability(
            ["FCO", "ATH", "LHR"], date(2027, 4, 1), date(2027, 4, 30)
        )
        self.assertGreater(len(avail), 0)
        for r in avail:
            self.assertIn(r.economy_rbd_code, ("E", "X", "U"))
            self.assertIn(r.premium_rbd_code, ("P", "A", "R"))
            self.assertIn(r.business_rbd_code, ("I", "W"))

    def test_f21_3_zone_points_and_tuesday_flycard_promo_pricing(self) -> None:
        self.get_repo()
        conn = sqlite3.connect(str(self.shared_db_path))
        conn.row_factory = sqlite3.Row
        try:
            zone_min = dict(
                conn.execute(
                    "SELECT award_zone, MIN(economy_points_per_pax) FROM elal_bonus_availability WHERE flycard_promo_active = 0 GROUP BY award_zone"
                ).fetchall()
            )
            self.assertLessEqual(zone_min["ZONE_A"], zone_min["ZONE_B"])
            self.assertLess(zone_min["ZONE_B"], zone_min["ZONE_E"])
        finally:
            conn.close()

    def test_f21_4_sync_award_availability_four_hour_ttl_cache_hit(self) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        elal = self.get_elal_adapter(repo)
        res = elal.sync_award_availability(
            ["FCO"], date(2027, 4, 11), date(2027, 4, 18), force_refresh=False
        )
        self.assertTrue(bool(res["cache_hit"]))
        self.assertEqual(res["expanded_destinations"], ["FCO"])
        self.assertTrue(
            str(res["source_url"]).startswith("https://www.elal.com/rbddataclients")
        )

    def test_f21_5_sync_award_availability_force_refresh_updates_cache(self) -> None:
        _db_path, repo = self.make_isolated_env(auto_seed=True)
        elal = self.get_elal_adapter(repo)
        res = elal.sync_award_availability(
            ["FCO"], date(2027, 4, 11), date(2027, 4, 18), force_refresh=True
        )
        self.assertFalse(bool(res["cache_hit"]))
        self.assertGreaterEqual(res["records_synced"], 1)


# ============================================================================
# Feature F22: Strategy 1: FULL_BONUS_SAME_CABIN (5 tests)
# ============================================================================
class TestTier1F22StrategyFullBonusSameCabin(Tier1BaseTestCase):
    def _make_award_pair(
        self, econ_seats: int = 2, prem_seats: int = 2, biz_seats: int = 2
    ) -> tuple[ElAlBonusAvailability, ElAlBonusAvailability]:
        out_a = ElAlBonusAvailability(
            id="out_fco",
            origin_iata="TLV",
            destination_iata="FCO",
            direction="OUTBOUND",
            flight_number="LY381",
            flight_date=date(2027, 4, 11),
            economy_award_seats=econ_seats,
            economy_seats_is_two_plus=econ_seats >= 2,
            premium_award_seats=prem_seats,
            premium_seats_is_two_plus=prem_seats >= 2,
            business_award_seats=biz_seats,
            business_seats_is_two_plus=biz_seats >= 2,
            award_zone="ZONE_B",
            economy_points_per_pax=15000,
            premium_points_per_pax=20500,
            business_points_per_pax=45000,
            taxes_usd_per_pax=48.75,
        )
        in_a = ElAlBonusAvailability(
            id="in_fco",
            origin_iata="FCO",
            destination_iata="TLV",
            direction="INBOUND",
            flight_number="LY384",
            flight_date=date(2027, 4, 18),
            economy_award_seats=econ_seats,
            economy_seats_is_two_plus=econ_seats >= 2,
            premium_award_seats=prem_seats,
            premium_seats_is_two_plus=prem_seats >= 2,
            business_award_seats=biz_seats,
            business_seats_is_two_plus=biz_seats >= 2,
            award_zone="ZONE_B",
            economy_points_per_pax=15000,
            premium_points_per_pax=20500,
            business_points_per_pax=45000,
            taxes_usd_per_pax=48.75,
        )
        return out_a, in_a

    def test_f22_1_full_bonus_same_cabin_economy_for_two_adults(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, in_a = self._make_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "FULL_BONUS_SAME_CABIN")
        self.assertEqual(itin["bonus_tickets_count"], 2)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")
        self.assertFalse(bool(itin["requires_two_plus_seat_verification"]))

    def test_f22_2_full_bonus_same_cabin_for_five_pax_sets_two_plus_verification_flag(
        self,
    ) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.matmid_points_balance = 300000
        out_a, in_a = self._make_award_pair(econ_seats=5)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "FULL_BONUS_SAME_CABIN", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        self.assertTrue(bool(_get_field(res, "requires_two_plus_seat_verification")))
        self.assertEqual(_get_field(res, "seated_passengers_count"), 5)
        self.assertEqual(_get_field(res, "bonus_tickets_count"), 5)
        self.assertEqual(_get_field(res, "cash_tickets_count"), 0)
        self.assertNotIn("family_ticket_allocation", res)

    def test_f22_3_full_bonus_same_cabin_business_class_allocation(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=300000, children=[])
        out_a, in_a = self._make_award_pair()
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 1400.0, "FULL_BONUS_SAME_CABIN", ["BUSINESS"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(_get_field(res, "seated_passengers_count"), 2)
        self.assertEqual(_get_field(res, "bonus_tickets_count"), 2)
        self.assertEqual(_get_field(res, "primary_cabin"), "BUSINESS")

    def test_f22_4_full_bonus_same_cabin_filtered_by_single_ticket_minimum_r2(self) -> None:
        planner = self.get_planner()
        family_four = FamilyProfile(
            adults_count=2,
            matmid_points_balance=30000,
            children=[
                ChildFramework(child_age_years=6, framework_type="ELEMENTARY_1_3"),
                ChildFramework(child_age_years=9, framework_type="ELEMENTARY_4_6"),
            ],
            passenger_loyalty_wallets=[],
        )
        base_query = {
            "date_selection_mode": "SPECIFIC_DATES",
            "airline_selection_mode": "EL_AL_ONLY",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 0,
            "destination_iatas": ["FCO"],
        }
        # 30,000 pts covers 1 round-trip bonus ticket (far below 4 * 30,000 = 120,000): kept
        at_min = planner.search_vacations(
            {**base_query, "matmid_points_balance": 30000},
            profile=family_four,
            persist_results=False,
        )
        full_at_min = [
            p for p in at_min if _get_field(p.itinerary, "fulfillment_strategy") == "FULL_BONUS_SAME_CABIN"
        ]
        self.assertGreaterEqual(len(full_at_min), 1)
        itin = _assert_run11_proposal_contract(self, full_at_min[0])
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

        # 29,999 pts is 1 point short of 1 round-trip ticket on 2-direction FCO: round-trip dropped
        below_min = planner.search_vacations(
            {**base_query, "matmid_points_balance": 29999},
            profile=family_four,
            persist_results=False,
        )
        below_strats = {_get_field(p.itinerary, "fulfillment_strategy") for p in below_min}
        self.assertNotIn("FULL_BONUS_SAME_CABIN", below_strats)
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", below_strats)
        self.assertIn("CASH_AND_POINTS", below_strats)

        # Balance 0 means "not entered" (U3): full bonus is returned
        zero_bal = planner.search_vacations(
            {**base_query, "matmid_points_balance": 0},
            profile=family_four,
            persist_results=False,
        )
        zero_strats = {_get_field(p.itinerary, "fulfillment_strategy") for p in zero_bal}
        self.assertIn("FULL_BONUS_SAME_CABIN", zero_strats)

    def test_f22_5_full_bonus_same_cabin_deep_link_and_rbddataclients_url(self) -> None:
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
        self.assertGreater(len(proposals), 0)
        itin = proposals[0].itinerary
        assert itin is not None
        self.assertIn("elal.com", str(itin.rbddataclients_verify_url))
        self.assertIn("elal.com", str(itin.booking_deep_link_url))


# ============================================================================
# Feature F23: Strategy 2: SPLIT_CABIN_BONUS (5 tests)
# ============================================================================
class TestTier1F23StrategySplitCabinBonus(Tier1BaseTestCase):
    def test_f23_1_split_cabin_bonus_four_pax_two_economy_two_premium(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.children = prof.children[:2]
        prof.matmid_points_balance = 200000
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["primary_cabin"], "ECONOMY")
        self.assertEqual(itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(itin["outbound_bonus_seats"], 4)
        self.assertEqual(itin["inbound_bonus_seats"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

    def test_f23_2_split_cabin_bonus_two_economy_two_business_athens(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.children = prof.children[:2]
        prof.matmid_points_balance = 250000
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=0, biz_seats=2)
        out_a.economy_points_per_pax = in_a.economy_points_per_pax = 8500
        out_a.business_points_per_pax = in_a.business_points_per_pax = 25000
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 420.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "BUSINESS"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 17000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

    def test_f23_3_split_cabin_bonus_five_pax_across_three_cabins(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.matmid_points_balance = 300000
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=1)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM", "BUSINESS"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 5)
        self.assertEqual(itin["bonus_tickets_count"], 5)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["outbound_bonus_seats"], 5)
        self.assertEqual(itin["inbound_bonus_seats"], 5)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)

    def test_f23_4_split_cabin_bonus_same_flight_number_invariant(self) -> None:
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

    def test_f23_5_split_cabin_bonus_points_sum_matches_cabin_rates(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.children = prof.children[:2]
        prof.matmid_points_balance = 200000
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        res_ep = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "SPLIT_CABIN_BONUS", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        assert res_ep is not None
        itin_ep = _assert_run11_itinerary_contract(self, res_ep)
        self.assertEqual(
            itin_ep["min_points_per_bonus_ticket"],
            out_a.economy_points_per_pax + in_a.economy_points_per_pax,
        )
        self.assertEqual(itin_ep["min_points_basis"], "ROUND_TRIP")

        out_pb, in_pb = self._make_award_pair(econ_seats=0, prem_seats=2, biz_seats=2)
        res_pb = eng.allocate_family_tickets(
            prof, out_pb, in_pb, 590.0, "SPLIT_CABIN_BONUS", ["PREMIUM", "BUSINESS"], ["ELAL_MATMID"]
        )
        assert res_pb is not None
        itin_pb = _assert_run11_itinerary_contract(self, res_pb)
        self.assertEqual(
            itin_pb["min_points_per_bonus_ticket"],
            out_pb.premium_points_per_pax + in_pb.premium_points_per_pax,
        )
        self.assertEqual(itin_pb["min_points_basis"], "ROUND_TRIP")


# ============================================================================
# Feature F24: Strategy 3: HYBRID_BONUS_PLUS_CASH (5 tests)
# ============================================================================
class TestTier1F24StrategyHybridBonusPlusCash(Tier1BaseTestCase):
    def test_f24_1_flagship_rome_five_pax_four_bonus_plus_one_cash(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 5)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(itin["outbound_bonus_seats"], 4)
        self.assertEqual(itin["inbound_bonus_seats"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

    def test_f24_2_hybrid_bonus_plus_cash_when_only_two_award_seats_exist(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=0, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        assert res is not None
        self.assertEqual(_get_field(res, "seated_passengers_count"), 5)
        self.assertEqual(_get_field(res, "bonus_tickets_count"), 2)
        self.assertEqual(_get_field(res, "cash_tickets_count"), 3)

    def test_f24_3_hybrid_bonus_plus_cash_when_wallet_points_cover_partial_family(
        self,
    ) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.children = prof.children[:2]
        prof.matmid_points_balance = 30000
        for w in prof.passenger_loyalty_wallets:
            w.available_points = 15000 if _get_field(w, "program_code") == "ELAL_MATMID" else 0
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=1, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        # Composition comes from seats (3 round-trip seats for 4 passengers -> 3 bonus + 1 cash),
        # while the 1-ticket minimum (30,000) fits within the household's 30,000 balance.
        self.assertEqual(itin["seated_passengers_count"], 4)
        self.assertEqual(itin["bonus_tickets_count"], 3)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertLessEqual(itin["min_points_per_bonus_ticket"], prof.matmid_points_balance)

    def test_f24_4_adult_child_under_12_pnr_safety_pairing_enforced(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.children = prof.children[:2]  # ages 5 and 9 (<12)
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=0, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        assert res is not None
        self.assertEqual(_get_field(res, "seated_passengers_count"), 4)
        self.assertEqual(_get_field(res, "bonus_tickets_count"), 2)
        self.assertEqual(_get_field(res, "cash_tickets_count"), 2)
        # With only 1 adult + 2 children (<12), splitting across bonus+cash PNRs is disqualified
        prof_single = FamilyProfile.from_dict(prof.to_dict())
        prof_single.adults_count = 1
        res_single = eng.allocate_family_tickets(
            prof_single, out_a, in_a, 590.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNone(res_single)

    def test_f24_5_hybrid_composition_and_score_ignore_cash_benchmarks_and_taxes(
        self,
    ) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        out_low, in_low = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        out_low.taxes_usd_per_pax = in_low.taxes_usd_per_pax = 0.0
        out_high, in_high = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        out_high.taxes_usd_per_pax = in_high.taxes_usd_per_pax = 950.0

        res_low = eng.allocate_family_tickets(
            prof, out_low, in_low, 0.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        res_high = eng.allocate_family_tickets(
            prof, out_high, in_high, 9999.0, "HYBRID_BONUS_PLUS_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        assert res_low is not None and res_high is not None
        itin_low = _assert_run11_itinerary_contract(self, res_low)
        itin_high = _assert_run11_itinerary_contract(self, res_high)
        for key in (
            "fulfillment_strategy",
            "seated_passengers_count",
            "bonus_tickets_count",
            "cash_tickets_count",
            "bonus_direction_coverage",
            "outbound_bonus_seats",
            "inbound_bonus_seats",
            "min_points_per_bonus_ticket",
            "min_points_basis",
        ):
            self.assertEqual(itin_low[key], itin_high[key], key)
        self.assertEqual((itin_low["bonus_tickets_count"], itin_low["cash_tickets_count"]), (4, 1))


# ============================================================================
# Feature F25: Strategy 4: ONE_WAY_BONUS_ONE_WAY_CASH & Open-Jaw (5 tests)
# ============================================================================
class TestTier1F25StrategyOneWayAndOpenJaw(Tier1BaseTestCase):
    def test_f25_1_one_way_bonus_outbound_and_one_way_cash_inbound(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, _ = self._make_award_pair(econ_seats=2, prem_seats=0, biz_seats=0)
        _, in_a = self._make_award_pair(econ_seats=0, prem_seats=0, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "ONE_WAY_BONUS_ONE_WAY_CASH", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["bonus_direction_coverage"], "OUTBOUND_ONLY")
        self.assertEqual(itin["outbound_bonus_seats"], 2)
        self.assertEqual(itin["inbound_bonus_seats"], 0)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 15000)
        self.assertEqual(itin["min_points_basis"], "ONE_WAY")

    def test_f25_2_one_way_cash_outbound_and_one_way_bonus_inbound(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(adults_count=2, matmid_points_balance=185000, children=[])
        out_a, _ = self._make_award_pair(econ_seats=0, prem_seats=0, biz_seats=0)
        _, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "ONE_WAY_BONUS_ONE_WAY_CASH", ["ECONOMY", "PREMIUM"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["bonus_direction_coverage"], "INBOUND_ONLY")
        self.assertEqual(itin["outbound_bonus_seats"], 0)
        self.assertEqual(itin["inbound_bonus_seats"], 4)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 15000)
        self.assertEqual(itin["min_points_basis"], "ONE_WAY")

    def test_f25_3_open_jaw_italy_milan_mxp_to_rome_fco_search(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["MXP", "FCO"],
            }
        )
        self.assertGreater(len(proposals), 0)
        self.assertTrue(
            any(
                p.itinerary is not None
                and p.itinerary.destination_iata != p.itinerary.return_origin_iata
                for p in proposals
            )
        )

    def test_f25_4_open_jaw_itinerary_legs_match_airports(self) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["MXP", "FCO"],
            }
        )
        open_jaw = [
            p
            for p in proposals
            if p.itinerary and p.itinerary.destination_iata != p.itinerary.return_origin_iata
        ]
        self.assertGreater(len(open_jaw), 0)
        itin = open_jaw[0].itinerary
        assert itin is not None
        self.assertEqual(itin.outbound_legs[-1].destination_iata, itin.destination_iata)
        self.assertEqual(itin.inbound_legs[0].origin_iata, itin.return_origin_iata)
        self.assertEqual(itin.inbound_legs[-1].destination_iata, itin.origin_iata)

    def test_f25_5_mixed_strategy_kinds_and_direction_coverage_returned_without_cash_r3_r4(
        self,
    ) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)
        prof = self.get_default_profile(db_path)
        self.authenticate_test_client(client, email="f25_5_mixed@gmail.com", profile=prof)

        # Both-directions same-airport Rome fixture returns HYBRID_BONUS_PLUS_CASH and
        # CASH_AND_POINTS without any cash figures and without spurious 1-way strategy (Run 12 R2)
        fco_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
            },
        )
        self.assertEqual(fco_resp.status_code, 200)
        fco_itins = _assert_run11_search_response_contract(
            self, fco_resp.json(), is_bonus_search=True
        )
        fco_strats = {it["fulfillment_strategy"] for it in fco_itins}
        for mixed_kind in (
            "HYBRID_BONUS_PLUS_CASH",
            "CASH_AND_POINTS",
        ):
            self.assertIn(mixed_kind, fco_strats)
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", fco_strats)
        for it in fco_itins:
            self.assertEqual(it["bonus_direction_coverage"], "BOTH_DIRECTIONS")

        # Seeded one-direction Athens fixture (2026-12-06..12: outbound bonus, 0 inbound seats)
        ath_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2026-12-06",
                "specific_return_date": "2026-12-12",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["ATH"],
            },
        )
        self.assertEqual(ath_resp.status_code, 200)
        ath_body = ath_resp.json()
        ath_itins = _assert_run11_search_response_contract(
            self, ath_body, is_bonus_search=True
        )
        self.assertEqual(
            {it["fulfillment_strategy"] for it in ath_itins},
            {"ONE_WAY_BONUS_ONE_WAY_CASH", "CASH_AND_POINTS"},
        )
        for prop, it in zip(ath_body["proposals"], ath_itins):
            self.assertEqual(it["bonus_direction_coverage"], "OUTBOUND_ONLY")
            self.assertGreater(it["outbound_bonus_seats"], 0)
            self.assertEqual(it["inbound_bonus_seats"], 0)
            self.assertIn("בונוס בכיוון אחד בלבד — הלוך", prop["explanation_summary_he"])


# ============================================================================
# Feature F26: Strategy 5: CASH_AND_POINTS (5 tests)
# ============================================================================
class TestTier1F26StrategyCashAndPoints(Tier1BaseTestCase):
    def test_f26_1_cash_and_points_fallback_when_zero_classic_award_seats(self) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        out_a, in_a = self._make_award_pair(econ_seats=0, prem_seats=0, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "CASH_AND_POINTS", ["ECONOMY"], ["ELAL_MATMID"]
        )
        self.assertIsNotNone(res)
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "CASH_AND_POINTS")
        self.assertEqual(itin["bonus_direction_coverage"], "NONE")
        self.assertEqual(itin["outbound_bonus_seats"], 0)
        self.assertEqual(itin["inbound_bonus_seats"], 0)
        self.assertIsNone(itin["min_points_per_bonus_ticket"])
        self.assertIsNone(itin["min_points_basis"])

    def test_f26_2_scores_follow_available_bonus_seats_and_ignore_cash_r3(self) -> None:
        from unittest.mock import patch
        from backend.app.storage_cache.seed_data import DESTINATION_CATALOG

        db_path, repo = self.make_isolated_env(auto_seed=True)
        planner = self.get_planner(repo)
        family_four = FamilyProfile(
            adults_count=2,
            matmid_points_balance=0,
            children=[
                ChildFramework(child_age_years=6, framework_type="ELEMENTARY_1_3"),
                ChildFramework(child_age_years=9, framework_type="ELEMENTARY_4_6"),
            ],
            passenger_loyalty_wallets=[],
        )
        scores: dict[tuple[int, int, bool], tuple[float, float]] = {}
        for out_s, in_s, is_tp in (
            (1, 1, False),
            (2, 2, False),
            (2, 0, True),
            (2, 2, True),
            (4, 4, True),
        ):
            out_a, _ = self._make_award_pair(econ_seats=out_s, prem_seats=0, biz_seats=0)
            _, in_a = self._make_award_pair(econ_seats=in_s, prem_seats=0, biz_seats=0)
            out_a.economy_seats_is_two_plus = bool(is_tp and out_s >= 2)
            in_a.economy_seats_is_two_plus = bool(is_tp and in_s >= 2)
            with patch.object(
                planner, "_ensure_award_rows_for_window", return_value=([out_a], [in_a])
            ):
                props = planner.search_vacations(
                    {
                        "date_selection_mode": "SPECIFIC_DATES",
                        "airline_selection_mode": "EL_AL_ONLY",
                        "specific_departure_date": "2027-04-11",
                        "specific_return_date": "2027-04-18",
                        "flex_days_plus_minus": 0,
                        "destination_iatas": ["FCO"],
                    },
                    profile=family_four,
                    persist_results=False,
                )
            self.assertGreaterEqual(len(props), 1)
            expected_fbvs = _run11_expected_bonus_score(
                out_s,
                in_s,
                4,
                out_a.economy_seats_is_two_plus,
                in_a.economy_seats_is_two_plus,
            )
            self.assertAlmostEqual(props[0].flight_bonus_value_score, expected_fbvs, places=1)
            scores[(out_s, in_s, is_tp)] = (
                props[0].flight_bonus_value_score,
                props[0].combined_trip_optimization_score,
            )

        self.assertEqual(scores[(1, 1, False)][0], 25.0)
        self.assertEqual(scores[(2, 2, False)][0], 50.0)
        self.assertEqual(scores[(2, 0, True)][0], 50.0)
        self.assertEqual(scores[(2, 2, True)][0], 100.0)
        self.assertEqual(scores[(4, 4, True)][0], 100.0)
        self.assertLess(scores[(1, 1, False)][0], scores[(2, 2, False)][0])
        self.assertLess(scores[(2, 2, False)][0], scores[(2, 2, True)][0])
        self.assertLess(scores[(1, 1, False)][1], scores[(2, 2, False)][1])
        self.assertLess(scores[(2, 2, False)][1], scores[(2, 2, True)][1])

        # Changing destination cash reference values does not change scores
        inflated = {
            k: float(DESTINATION_CATALOG["FCO"][k]) * 10.0 + 750.0
            for k in (
                "rt_cash_per_pax_usd",
                "supplemental_single_pax_cash_usd",
                "five_pax_cash_benchmark_usd",
                "outbound_taxes_usd",
                "inbound_taxes_usd",
            )
        }
        out_2, in_2 = self._make_award_pair(econ_seats=2, prem_seats=0, biz_seats=0)
        out_2.taxes_usd_per_pax = in_2.taxes_usd_per_pax = 999.0
        with patch.dict(DESTINATION_CATALOG["FCO"], inflated), patch.object(
            planner, "_ensure_award_rows_for_window", return_value=([out_2], [in_2])
        ):
            props_inflated = planner.search_vacations(
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                },
                profile=family_four,
                persist_results=False,
            )
        self.assertEqual(
            (props_inflated[0].flight_bonus_value_score, props_inflated[0].combined_trip_optimization_score),
            scores[(2, 2, True)],
        )

    def test_f26_3_cash_and_points_carries_no_points_figure_or_low_value_penalty(
        self,
    ) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "destination_iatas": ["FCO"],
            }
        )
        by_strat = {_get_field(p.itinerary, "fulfillment_strategy"): p for p in proposals}
        self.assertIn("CASH_AND_POINTS", by_strat)
        self.assertIn("FULL_BONUS_SAME_CABIN", by_strat)
        cp_prop = by_strat["CASH_AND_POINTS"]
        cp_itin = _assert_run11_proposal_contract(self, cp_prop)
        self.assertIsNone(cp_itin["min_points_per_bonus_ticket"])
        self.assertIsNone(cp_itin["min_points_basis"])
        self.assertNotIn("0.8", cp_prop.explanation_summary_he)
        # Same seat-only bonus score as full bonus on the same flights (no low-CPP cap at 62)
        self.assertEqual(
            cp_prop.flight_bonus_value_score,
            by_strat["FULL_BONUS_SAME_CABIN"].flight_bonus_value_score,
        )

    def test_f26_4_cash_and_points_respects_family_matmid_balance(self) -> None:
        planner = self.get_planner()
        for balance in (0, 5000, 40000):
            prof = self.get_default_profile()
            prof.matmid_points_balance = balance
            prof.passenger_loyalty_wallets = (
                []
                if balance == 0
                else [
                    PassengerLoyaltyWallet(
                        id=f"w-cp-{balance}",
                        passenger_id="ADULT_1",
                        program_code="ELAL_MATMID",
                        available_points=balance,
                        can_pool_with_family=True,
                    )
                ]
            )
            props = planner.search_vacations(
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                    "matmid_points_balance": balance,
                },
                profile=prof,
                persist_results=False,
            )
            cp_props = [
                p for p in props if _get_field(p.itinerary, "fulfillment_strategy") == "CASH_AND_POINTS"
            ]
            self.assertGreaterEqual(len(cp_props), 1, f"balance={balance}")
            cp_itin = _assert_run11_proposal_contract(self, cp_props[0])
            self.assertIsNone(cp_itin["min_points_per_bonus_ticket"])
            self.assertEqual(cp_itin["bonus_direction_coverage"], "BOTH_DIRECTIONS")

    def test_f26_5_cash_and_points_present_in_search_proposals_on_sold_out_award_dates(
        self,
    ) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO", "ATH"],
            }
        )
        strategies = {
            _get_field(p.itinerary, "fulfillment_strategy")
            for p in proposals
            if p.itinerary
        }
        self.assertGreater(len(strategies), 1)


# ============================================================================
# Feature F27: Strategy 6: MULTI_CLUB_PER_PASSENGER_SPLIT (5 tests)
# ============================================================================
class TestTier1F27StrategyMultiClubWalletSplit(Tier1BaseTestCase):
    def test_f27_1_unpooled_matmid_wallets_allocate_integer_tickets_per_parent(
        self,
    ) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        prof.passenger_loyalty_wallets = [
            PassengerLoyaltyWallet(
                id="w-p1",
                passenger_id="ADULT_1",
                passenger_name="יוני",
                program_code="ELAL_MATMID",
                available_points=75000,
                can_pool_with_family=False,
            ),
            PassengerLoyaltyWallet(
                id="w-p2",
                passenger_id="ADULT_2",
                passenger_name="הורה 2",
                program_code="ELAL_MATMID",
                available_points=68000,
                can_pool_with_family=False,
            ),
        ]
        out_a, in_a = self._make_award_pair(econ_seats=4, prem_seats=0, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
        )
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "MULTI_CLUB_PER_PASSENGER_SPLIT")
        self.assertEqual(itin["seated_passengers_count"], 5)
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

        # Requires >= 2 funded wallets
        single_wallet_prof = FamilyProfile.from_dict(prof.to_dict())
        single_wallet_prof.passenger_loyalty_wallets = prof.passenger_loyalty_wallets[:1]
        self.assertIsNone(
            eng.allocate_family_tickets(
                single_wallet_prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
            )
        )

    def test_f27_2_pooled_family_wallets_combine_across_passengers(self) -> None:
        eng = self.get_wallet_engine()
        prof = FamilyProfile(
            adults_count=2,
            matmid_points_balance=90000,
            children=[ChildFramework(child_age_years=8, framework_type="ELEMENTARY_1_3")],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet(
                    id="w-pool-a",
                    passenger_id="ADULT_1",
                    passenger_name="יוני",
                    program_code="ELAL_MATMID",
                    available_points=45000,
                    can_pool_with_family=True,
                ),
                PassengerLoyaltyWallet(
                    id="w-pool-b",
                    passenger_id="ADULT_2",
                    passenger_name="הורה 2",
                    program_code="ELAL_MATMID",
                    available_points=45000,
                    can_pool_with_family=True,
                ),
            ],
        )
        out_a, in_a = self._make_award_pair(econ_seats=3, prem_seats=0, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof, out_a, in_a, 590.0, "MULTI_CLUB_PER_PASSENGER_SPLIT", ["ECONOMY"], ["ELAL_MATMID"]
        )
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["seated_passengers_count"], 3)
        self.assertEqual(itin["bonus_tickets_count"], 3)
        self.assertEqual(itin["cash_tickets_count"], 0)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)
        self.assertEqual(itin["min_points_basis"], "ROUND_TRIP")

    def test_f27_3_cross_club_split_elal_matmid_plus_british_avios_or_flying_blue(
        self,
    ) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        res = eng.allocate_family_tickets(
            prof,
            out_a,
            in_a,
            590.0,
            "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY", "PREMIUM"],
            ["ELAL_MATMID", "BRITISH_AVIOS", "FLYING_BLUE"],
        )
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "MULTI_CLUB_PER_PASSENGER_SPLIT")
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertEqual(itin["min_points_per_bonus_ticket"], 30000)

    def test_f27_4_credit_card_transferable_points_amex_mr_and_israeli_cc_conversion(
        self,
    ) -> None:
        eng = self.get_wallet_engine()
        prof = self.get_default_profile()
        out_a, in_a = self._make_award_pair(econ_seats=2, prem_seats=2, biz_seats=0)
        enabled = ["ELAL_MATMID", "AMEX_MR_ISRAEL", "ISRAELI_CC_TRAVEL_POINTS"]
        res = eng.allocate_family_tickets(
            prof,
            out_a,
            in_a,
            590.0,
            "MULTI_CLUB_PER_PASSENGER_SPLIT",
            ["ECONOMY", "PREMIUM"],
            enabled,
        )
        assert res is not None
        itin = _assert_run11_itinerary_contract(self, res)
        self.assertEqual(itin["fulfillment_strategy"], "MULTI_CLUB_PER_PASSENGER_SPLIT")
        self.assertEqual(itin["bonus_tickets_count"], 4)
        self.assertEqual(itin["cash_tickets_count"], 1)
        self.assertGreater(
            eng.effective_elal_points_balance(prof, enabled),
            eng.effective_elal_points_balance(prof, ["ELAL_MATMID"]),
        )

    def test_f27_5_search_vacations_synthesizes_multi_club_per_passenger_split_proposal(
        self,
    ) -> None:
        planner = self.get_planner()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "destination_iatas": ["FCO"],
                "enabled_loyalty_programs": [
                    "ELAL_MATMID",
                    "BRITISH_AVIOS",
                    "FLYING_BLUE",
                    "UNITED_MILEAGEPLUS",
                    "AMEX_MR_ISRAEL",
                ],
            }
        )
        self.assertTrue(
            any(
                p.itinerary
                and _get_field(p.itinerary, "fulfillment_strategy")
                == "MULTI_CLUB_PER_PASSENGER_SPLIT"
                for p in proposals
            )
        )


# ============================================================================
# Feature F28: FBVS, CTOS, Side-by-Side Comparison & Estimated Cash (5 tests)
# ============================================================================
class TestTier1F28ScoringComparisonAndIcsExport(Tier1BaseTestCase):
    def test_f28_1_fbvs_and_ctos_weighted_combination_accuracy(self) -> None:
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
        self.assertGreater(len(proposals), 0)
        for p in proposals:
            expected = 0.55 * p.holiday_alignment_score + 0.45 * p.flight_bonus_value_score
            self.assertAlmostEqual(p.combined_trip_optimization_score, expected, delta=0.3)

    def test_f28_2_compare_proposals_removed_from_service_api_and_frontend(
        self,
    ) -> None:
        import backend.app.schemas.domain as domain_mod

        planner = self.get_planner()
        self.assertFalse(hasattr(planner, "compare_proposals"))
        self.assertFalse(hasattr(domain_mod, "VacationComparisonMatrix"))

        client = self.get_client()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO", "ATH"],
            }
        )
        ids = [p.id for p in proposals[:2]]
        self.assertEqual(
            client.post("/api/v1/vacations/compare", json={"proposal_ids": ids}).status_code,
            404,
        )
        for rel_ui in ("index.html", "src/app.js", "src/styles/app.css"):
            ui_txt = (PROJECT_ROOT / "frontend" / rel_ui).read_text("utf-8")
            for removed_cmp_tok in (
                "btn-compare-selected",
                "sticky-compare-bar",
                "comparison-banner-container",
                "data-compare-id",
                "compare-check-label",
                "/api/v1/vacations/compare",
            ):
                self.assertNotIn(removed_cmp_tok, ui_txt)

    def test_f28_3_multi_select_destination_filtering_and_11plus_offline_cities(
        self,
    ) -> None:
        planner = self.get_planner()
        subset_props = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destinations": ["ROM", "ATH"],
            }
        )
        self.assertGreater(len(subset_props), 0)
        for p in subset_props:
            assert p.itinerary is not None
            self.assertIn(p.itinerary.destination_iata, {"FCO", "ATH"})
            self.assertIn(
                p.itinerary.return_origin_iata or p.itinerary.destination_iata,
                {"FCO", "ATH"},
            )

        eleven_non_flagship = [
            "BCN", "AMS", "BER", "MUC", "FRA", "GVA",
            "LIS", "NCE", "OTP", "SOF", "WAW",
        ]
        many_props = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": eleven_non_flagship,
            }
        )
        self.assertGreater(len(many_props), 0)
        for p in many_props:
            assert p.itinerary is not None
            self.assertIn(p.itinerary.destination_iata, set(eleven_non_flagship))

    def test_f28_4_no_cash_estimate_saving_or_cpp_across_all_returned_strategies_r1(
        self,
    ) -> None:
        db_path, repo = self.make_isolated_env(auto_seed=True)
        planner = self.get_planner(repo)
        self.assertFalse(hasattr(planner, "compare_proposals"))

        client = self.get_client(db_path)
        prof = self.get_default_profile(db_path)
        self.authenticate_test_client(client, email="f28_4_r1@gmail.com", profile=prof)

        seen_strategies: set[str] = set()
        for payload, is_bonus in (
            (
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO", "MXP"],
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
            resp = client.post("/api/v1/vacations/search", json=payload)
            self.assertEqual(resp.status_code, 200)
            itins = _assert_run11_search_response_contract(
                self, resp.json(), is_bonus_search=is_bonus
            )
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

    def test_f28_5_ics_export_removed_from_planner_service_and_rest_api(self) -> None:
        planner = self.get_planner()
        self.assertFalse(hasattr(planner, "export_proposal_ics"))
        client = self.get_client()
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
        pid = s_resp.json()["proposals"][0]["id"]
        self.assertEqual(client.get(f"/api/v1/vacations/{pid}/export.ics").status_code, 404)


# ============================================================================
# Feature F29: 8 Core REST API Endpoints + .ics Export & Server (5 tests)
# ============================================================================
class TestTier1F29RestApiEndpoints(Tier1BaseTestCase):
    def test_f29_1_health_and_profile_get_put_endpoints(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)
        h_resp = client.get("/api/v1/health")
        self.assertEqual(h_resp.status_code, 200)
        h_json = h_resp.json()
        self.assertEqual(h_json["status"], "ok")
        self.assertTrue(bool(h_json["wal_mode"]))
        self.assertEqual(h_json["tables_count"], 11)

        # Unauthenticated profile access is strictly rejected (401) and never leaks shared profiles
        unauth_get = client.get("/api/v1/profile")
        self.assertEqual(unauth_get.status_code, 401)
        self.assertNotIn("בודובסקי", unauth_get.text)
        unauth_put = client.put("/api/v1/profile", json={"adults_count": 2})
        self.assertEqual(unauth_put.status_code, 401)

        # Authenticated Gmail user gets clean starter profile and can persist updates
        self.authenticate_test_client(client, email="f29_user@gmail.com")
        g_resp = client.get("/api/v1/profile")
        self.assertEqual(g_resp.status_code, 200)
        prof_data = g_resp.json()
        prof_data["matmid_points_balance"] = 195000
        p_resp = client.put("/api/v1/profile", json=prof_data)
        self.assertEqual(p_resp.status_code, 200)
        self.assertNotIn("annual_pto_budget", p_resp.json())
        self.assertEqual(p_resp.json()["matmid_points_balance"], 195000)

    def test_f29_2_moe_calendar_get_and_sync_post_endpoints(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)
        g_resp = client.get("/api/v1/moe-calendar/2026-2027")
        self.assertEqual(g_resp.status_code, 200)
        self.assertEqual(g_resp.json()["school_year"], "2026-2027")
        self.assertGreater(len(g_resp.json()["windows"]), 0)

        s_resp = client.post(
            "/api/v1/moe-calendar/sync/2027-2028", json={"force_remote_check": False}
        )
        self.assertEqual(s_resp.status_code, 200)
        self.assertEqual(s_resp.json()["school_year"], "2027-2028")
        self.assertGreaterEqual(s_resp.json()["windows_synced_count"], 8)

    def test_f29_3_elal_bonus_sync_post_and_availability_get_endpoints(self) -> None:
        client = self.get_client()
        s_resp = client.post(
            "/api/v1/elal-bonus/sync",
            json={
                "destinations": ["ROM"],
                "start_date": "2027-04-10",
                "end_date": "2027-04-20",
                "origin": "TLV",
                "force_refresh": False,
            },
        )
        self.assertEqual(s_resp.status_code, 200)
        self.assertEqual(s_resp.json()["expanded_destinations"], ["FCO"])

        a_resp = client.get(
            "/api/v1/elal-bonus/availability?destination=ROM&start_date=2027-04-10&end_date=2027-04-20"
        )
        self.assertEqual(a_resp.status_code, 200)
        self.assertEqual(a_resp.json()["expanded_destinations"], ["FCO"])
        self.assertGreater(len(a_resp.json()["availability"]), 0)

    def test_f29_4_vacations_search_post_compare_post_and_ics_export_get_endpoints(
        self,
    ) -> None:
        client = self.get_client()
        s_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": ["FCO", "ATH"],
            },
        )
        self.assertEqual(s_resp.status_code, 200)
        props = s_resp.json()["proposals"]
        self.assertGreaterEqual(len(props), 2)
        pids = [p["id"] for p in props[:2]]

        c_resp = client.post("/api/v1/vacations/compare", json={"proposal_ids": pids})
        self.assertEqual(c_resp.status_code, 404)

        i_resp = client.get(f"/api/v1/vacations/{pids[0]}/export.ics")
        self.assertEqual(i_resp.status_code, 404)

        # Verify GET /api/v1/destinations/weather and typed vacation search
        w_resp = client.get(
            "/api/v1/destinations/weather?month=7&vacation_type=BEACH_AND_POOL"
        )
        self.assertEqual(w_resp.status_code, 200)
        w_body = w_resp.json()
        self.assertEqual(w_body["count"], 60)
        dest_codes_returned = {d["iata"] for d in w_body["destinations"]}
        for new_code in ("SZG", "TIA", "ZRH", "BSL", "NAP", "VRN", "LYS", "OPO", "JMK", "PVK", "DBV", "ZAG", "LJU", "RMO", "SEZ"):
            self.assertIn(new_code, dest_codes_returned)
        self.assertEqual(len(w_body["vacation_types_catalog"]), 7)
        top_dest = w_body["destinations"][0]
        self.assertGreaterEqual(top_dest["weather_suitability_score"], 85.0)

        typed_s_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "direct_holiday_code": "SUMMER_JULY",
                "direct_target_year": 2027,
                "destination_iatas": ["ATH", "LCA", "VIE"],
                "preferred_vacation_types": ["BEACH_AND_POOL"],
                "weather_filter_mode": "SOFT_PRIORITIZE",
            },
        )
        self.assertEqual(typed_s_resp.status_code, 200)
        typed_props = typed_s_resp.json()["proposals"]
        self.assertGreater(len(typed_props), 0)
        self.assertIn("weather_suitability_score", typed_props[0])
        self.assertIsNotNone(typed_props[0].get("weather_metrics"))
        self.assertIn(typed_props[0]["itinerary"]["destination_iata"], ("ATH", "LCA"))

        bad_vt_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "preferred_vacation_types": ["INVALID_VACATION_STYLE"],
            },
        )
        self.assertEqual(bad_vt_resp.status_code, 422)

    def test_f29_5_live_http_server_on_ephemeral_port_serves_api_and_health(
        self,
    ) -> None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "backend.app.main",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "VACATION_PLANNER_DB_PATH": str(self.shared_db_path)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            payload = None
            last_err: Optional[Exception] = None
            for _ in range(15):
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/v1/health", timeout=0.5
                    ) as r:
                        if r.status == 200:
                            payload = json.loads(r.read().decode("utf-8"))
                            break
                except Exception as exc:
                    last_err = exc
                    if "Network is unreachable" in str(exc) or "Errno 101" in str(exc):
                        break
                    time.sleep(0.08)
            if payload is None and last_err is not None and (
                "Network is unreachable" in str(last_err) or "Errno 101" in str(last_err)
            ):
                # Fallback when execution sandbox blocks loopback TCP sockets
                resp = self.get_client().get("/api/v1/health")
                self.assertEqual(resp.status_code, 200)
                payload = resp.json()
            self.assertIsNotNone(payload)
            assert payload is not None
            self.assertEqual(payload["status"], "ok")
        finally:
            proc.terminate()
            proc.wait(timeout=5)


# ============================================================================
# Feature F30: CLI Companion (plan-vacation / backend/app/cli/main.py) (5 tests)
# ============================================================================
class TestTier1F30CliCompanion(Tier1BaseTestCase):
    def _run_cli(self, *args: str, db_path: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
        target_db = db_path or self.shared_db_path
        if target_db == self.shared_db_path:
            self.get_repo()
        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "plan-vacation"), *args],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "VACATION_PLANNER_DB_PATH": str(target_db)},
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_f30_1_cli_profile_json_subcommand(self) -> None:
        from backend.app.auth_service import sha256_hex
        from backend.app.storage_cache.seed_data import build_default_family_profile

        db_path, repo = self.make_isolated_env(auto_seed=True)
        res = self._run_cli("profile", "--json", db_path=db_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("authenticated", True))
        self.assertIsNone(data["id"])
        self.assertEqual(data["adults_count"], 2)
        self.assertEqual(data["children"], [])
        self.assertEqual(data["matmid_points_balance"], 0)
        self.assertNotIn("בודובסקי", res.stdout)

        # Authenticated CLI profile inspection via --session-token
        user_rec = repo.upsert_google_user(
            google_sub="cli-sub-f30",
            email="cli_f30@gmail.com",
            email_verified=True,
            display_name="CLI User",
        )
        raw_tok = "cli-test-session-token-f30"
        repo.create_auth_session(
            user_id=user_rec["id"],
            token_sha256=sha256_hex(raw_tok),
            csrf_token="csrf-f30",
            ttl_seconds=3600,
        )
        saved_prof = build_default_family_profile()
        saved_prof.profile_name = "פרופיל CLI"
        repo.save_profile_for_user(user_rec["id"], saved_prof)

        auth_res = self._run_cli(
            "profile", "--session-token", raw_tok, "--json", db_path=db_path
        )
        self.assertEqual(auth_res.returncode, 0, auth_res.stderr)
        auth_data = json.loads(auth_res.stdout)
        self.assertEqual(auth_data["id"], f"user-profile-{user_rec['id']}")
        self.assertEqual(auth_data["adults_count"], 2)
        self.assertEqual(len(auth_data["children"]), 3)
        self.assertEqual(auth_data["matmid_points_balance"], 185000)

    def test_f30_2_cli_calendar_and_sync_json_subcommand(self) -> None:
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        res = self._run_cli("calendar", "--school-year", "2027-2028", "--sync", "--json", db_path=db_path)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["school_year"], "2027-2028")
        self.assertGreater(len(data["windows"]), 0)

    def test_f30_3_cli_bonus_availability_with_metro_expansion_json(self) -> None:
        res = self._run_cli(
            "bonus-availability",
            "--destination",
            "ROM",
            "--start-date",
            "2027-04-10",
            "--end-date",
            "2027-04-20",
            "--json",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertIn("FCO", data["expanded_destinations"])
        self.assertGreaterEqual(data["count"], 1)

    def test_f30_4_cli_search_holiday_direct_with_export_json_and_export_ics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jpath = Path(tmp) / "out.json"
            res = self._run_cli(
                "search",
                "--mode",
                "holiday-direct",
                "--airline",
                "elal-only",
                "--destination",
                "FCO",
                "--holiday",
                "PESACH",
                "--year",
                "2027",
                "--export-json",
                str(jpath),
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(jpath.exists())
            exported = json.loads(jpath.read_text("utf-8"))
            self.assertGreaterEqual(len(exported["proposals"]), 1)
            _assert_run11_search_response_contract(self, exported, is_bonus_search=True)
            self.assertIn("Bonus=", res.stdout)
            for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
                self.assertNotIn(forbidden, res.stdout)

            bad_ics = self._run_cli(
                "search",
                "--mode",
                "holiday-direct",
                "--destination",
                "FCO",
                "--holiday",
                "PESACH",
                "--export-ics",
                str(Path(tmp) / "removed.ics"),
            )
            self.assertNotEqual(bad_ics.returncode, 0)

    def test_f30_5_cli_module_invocation_and_serve_help(self) -> None:
        res = subprocess.run(
            [sys.executable, "-m", "backend.app.cli.main", "--help"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        for cmd in ("profile", "calendar", "bonus-availability", "search", "serve"):
            self.assertIn(cmd, res.stdout)


# ============================================================================
# Feature F31: Desktop-First Multi-Column BiDi/RTL & LTR Web Application (5 tests)
# ============================================================================
class TestTier1F31WebUiAndResponsiveBiDi(Tier1BaseTestCase):
    def test_f31_1_root_index_html_served_with_rtl_hebrew_and_4_zones(self) -> None:
        from bs4 import BeautifulSoup
        import re

        client = self.get_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text
        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="he"', html)
        self.assertIn("manifest.webmanifest", html)
        # Verify all 4 desktop workspace zones, desktop quick-nav, and multi-column form classes
        for zone_id in ('id="zone-search"', 'id="zone-profile"', 'id="zone-calendar"', 'id="zone-results"'):
            self.assertIn(zone_id, html)
        self.assertIn('class="desktop-zone-nav"', html)
        self.assertIn("form-grid-2", html)
        self.assertIn("form-grid-3", html)
        self.assertNotIn("margin-block-top", html)
        # Mobile bottom nav must be hidden on desktop
        self.assertRegex(html, r'<nav[^>]*class="mobile-bottom-nav"[^>]*hidden')

        # Run 3 + Run 7 + Run 14 UI invariants on GET /
        for removed_token in (
            'id="select-direct-year"',
            'id="tab-mode-moe"',
            "מקסום שנתי",
            'id="controls-moe-maximize"',
            'id="select-airline-mode"',
            "חברות תעופה ומועדון",
            'id="wallets-list-container"',
            'id="btn-add-wallet"',
            'id="family-clubs-totals-strip"',
            "EL AL rbddataclients + MoE",
            "brand-badge",
            'id="prof-pto-budget"',
            "תקציב חופש",
            "מקסום ימי חופש",
            "פירוט הקצאת",
            "btn-ics-link",
            "export.ics",
        ):
            self.assertNotIn(removed_token, html)
        for run14_token in (
            'id="workplace-calendar-table"',
            'id="workplace-calendar-tbody"',
            'id="calendar-modal-backdrop"',
            "לוח חגים ומועדים במשק",
            "חופשת עבודה",
        ):
            self.assertIn(run14_token, html)
        self.assertIsNone(
            re.search(r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])", html)
        )

        soup = BeautifulSoup(html, "html.parser")
        dest_sel = soup.find("select", id="select-destination")
        self.assertIsNotNone(dest_sel)
        selected_dest_opts = [o for o in dest_sel.find_all("option") if o.has_attr("selected")]
        self.assertEqual(len(selected_dest_opts), 1)
        self.assertEqual(selected_dest_opts[0].get("value"), "ANYWHERE")

        mode_tabs = soup.find(class_="mode-tabs")
        self.assertIsNotNone(mode_tabs)
        tab_btns = mode_tabs.find_all("button", class_="mode-tab-btn")
        self.assertEqual([b.get("id") for b in tab_btns], ["tab-mode-specific", "tab-mode-holiday"])
        tab_specific = tab_btns[0]
        tab_holiday = tab_btns[1]
        self.assertFalse(tab_specific.has_attr("hidden"))
        self.assertIn("active", tab_specific.get("class") or [])
        self.assertNotIn("active", tab_holiday.get("class") or [])
        c_spec = soup.find(id="controls-specific-dates")
        c_hol = soup.find(id="controls-holiday-direct")
        self.assertIsNotNone(c_spec)
        self.assertIsNotNone(c_hol)
        self.assertNotIn("display: none", c_spec.get("style") or "")
        self.assertIn("display: none", c_hol.get("style") or "")
        for manual_id in ("input-dep-date", "input-ret-date", "input-flex-days", "prof-matmid-points"):
            self.assertIsNotNone(soup.find(id=manual_id), f"Missing #{manual_id}")

        holiday_sel = soup.find("select", id="select-direct-holiday")
        self.assertIsNotNone(holiday_sel)
        h_opts = holiday_sel.find_all("option")
        self.assertEqual(len(h_opts), 11)
        for opt in h_opts:
            self.assertRegex(opt.text.strip(), r"\b20\d{2}\s*\(\d+\s*(?:ימים|יום)\)$")

    def test_f31_2_responsive_css_mobile_360_430_and_desktop_1280_breakpoints_and_logical_rtl(
        self,
    ) -> None:
        import re

        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        self.assertIn("@media", css)
        self.assertIn("sticky", css)
        self.assertTrue("inset-inline" in css or "margin-inline" in css or "padding-inline" in css)
        self.assertNotIn("padding-block: 18px 88px", css)
        self.assertNotIn("scroll-snap-type: x mandatory", css)
        self.assertRegex(css, r"\.mobile-bottom-nav\s*\{[^}]*display:\s*none\s*!important")
        self.assertRegex(css, r"\.mode-tabs\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertNotIn("#tab-mode-specific[hidden]", css)
        self.assertNotIn(".brand-badge", css)
        self.assertRegex(css, r"\.form-grid-2\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(css, r"\.form-grid-3\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)")

        # Verify the workspace shell layout that is really rendered: one column on mobile/tablet (360..1179px)
        # and control rail + deal stream side by side from 1180px (1280x800, 1440x900, wide desktop).
        # The shell is styled by ONE selector (`.dashboard-shell`) with mobile-first `@media (min-width: Npx)`
        # overrides only, so applying its declarations in source order is exactly what a browser computes.
        clean_css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotRegex(clean_css, r"@media[^{]*max-width")
        all_selectors = [s.strip() for group in re.findall(r"([^{}]+)\{[^{}]*\}", clean_css) for s in group.split(",")]
        self.assertEqual({s for s in all_selectors if "dashboard-shell" in s}, {".dashboard-shell"})
        block_pattern = re.compile(r"@media([^{]*)\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}|([^{}@]+)\{([^{}]*)\}")

        def shell_style_at(vp_width: int) -> dict[str, str]:
            style: dict[str, str] = {}
            for block in block_pattern.finditer(clean_css):
                if block.group(1) is not None:
                    min_width = re.search(r"min-width:\s*(\d+)px", block.group(1))
                    if min_width is None or vp_width < int(min_width.group(1)):
                        continue
                    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", block.group(2))
                else:
                    rules = [(block.group(3), block.group(4))]
                for selector_text, declarations in rules:
                    if ".dashboard-shell" not in [s.strip() for s in selector_text.split(",")]:
                        continue
                    for declaration in declarations.split(";"):
                        if ":" in declaration:
                            prop, value = declaration.split(":", 1)
                            style[prop.strip()] = value.strip()
            return style

        for vp_width in (360, 430, 768, 1024, 1179):
            narrow = shell_style_at(vp_width)
            self.assertEqual(narrow.get("display"), "grid")
            self.assertEqual(
                narrow.get("grid-template-columns"), "minmax(0, 1fr)", f"single column expected at {vp_width}px"
            )
        for vp_width, expected_tracks in (
            (1180, "412px minmax(0, 1fr)"),
            (1280, "414px minmax(0, 1fr)"),
            (1440, "416px minmax(0, 1fr)"),
            (1920, "416px minmax(0, 1fr)"),
        ):
            wide = shell_style_at(vp_width)
            self.assertEqual(wide.get("display"), "grid")
            self.assertEqual(
                wide.get("grid-template-columns"), expected_tracks, f"two columns expected at {vp_width}px"
            )
            self.assertEqual(wide.get("max-width"), "1640px")

    def test_f31_3_frontend_app_js_and_domain_ts_cover_all_modes_frameworks_and_clubs(
        self,
    ) -> None:
        app_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
        dom_ts = (PROJECT_ROOT / "frontend" / "src" / "types" / "domain.ts").read_text("utf-8")
        combined = app_js + "\n" + dom_ts
        for mode in ("SPECIFIC_DATES", "HOLIDAY_DIRECT_INTENT", "EL_AL_ONLY", "ALL_AIRLINES", "ANYWHERE"):
            self.assertIn(mode, combined)
        self.assertNotIn("MOE_VACATION_MAXIMIZATION", combined)
        for fw in MoEFrameworkType:
            self.assertIn(fw.value, combined)
        for club in LoyaltyProgramCode:
            self.assertIn(club.value, combined)
        # Verify dynamic child cards & Run 11 seat-based / cash-free contracts across served frontend files
        self.assertIn("form-grid form-grid-2", app_js)
        self.assertIn("desktop-nav-btn", app_js)
        for required_js_token in (
            "prof-matmid-points",
            "syncHouseholdMatmidBalance",
            "/api/v1/moe-calendar/upcoming",
            "applyHolidayDurationDefault",
            "HOLIDAY_DIRECT_INTENT",
            "SPECIFIC_DATES",
            "EL_AL_ONLY",
            "ELAL_MATMID",
            "ANYWHERE",
            "bonus-direction-statement",
            "bonus-lane",
            "bonus-lane-seats",
            "bonus-flight-num",
            "bonus-flight-times",
            "min-points-ticket",
            "renderWeatherTooltipHtml",
            "בונוס בשני הכיוונים",
            "בונוס בכיוון אחד בלבד — הלוך",
            "בונוס בכיוון אחד בלבד — חזור",
            "החל מ-",
        ):
            self.assertIn(required_js_token, app_js)
        for removed_js_token in (
            "data-remove-wallet",
            "wallets-list-container",
            "recalculateHouseholdPointsFromWallets",
            "select-airline-mode",
            "select-direct-year",
            "מקסום שנתי",
            "prof-pto-budget",
            "annual_pto_budget",
            "allocations-details",
            "formatGenericPassengerLabel",
            "btn-ics-link",
            "export.ics",
            "הערכת מחיר במזומן",
            "חיסכון משוער",
            "Est. Cash Price",
            "Est. Cash",
            "Est. Net Saved",
            "¢",
            "~$",
            "buildIntuitiveProposalSummary",
            "total_matmid_points",
            "total_out_of_pocket_cash_usd",
            "net_cash_saved_usd",
            "cents_per_point_value",
        ):
            self.assertNotIn(removed_js_token, app_js)
        for req_dom_ts_token in (
            "COMMERCIAL_CASH_ONLY",
            "bonus_direction_coverage",
            "outbound_bonus_seats",
            "inbound_bonus_seats",
            "min_points_per_bonus_ticket",
            "min_points_basis",
        ):
            self.assertIn(req_dom_ts_token, dom_ts)
        served_frontend_files = [
            PROJECT_ROOT / "frontend" / "index.html",
            PROJECT_ROOT / "frontend" / "src" / "app.js",
            PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css",
            PROJECT_ROOT / "frontend" / "src" / "types" / "domain.ts",
            PROJECT_ROOT / "frontend" / "public" / "sw.js",
            PROJECT_ROOT / "frontend" / "public" / "manifest.webmanifest",
            *(PROJECT_ROOT / "frontend" / "src" / "components").glob("*/*.tsx"),
        ]
        for sf_path in served_frontend_files:
            sf_text = sf_path.read_text("utf-8")
            for forbidden_ui_tok in (
                "הערכת מחיר במזומן",
                "חיסכון משוער",
                "¢",
                "~$",
                "Est. Cash",
                "Est. Net Saved",
                "COMMERCIAL_CASH_FARE",
            ):
                self.assertNotIn(
                    forbidden_ui_tok,
                    sf_text,
                    f"Forbidden Run 11 cash/price token {forbidden_ui_tok!r} found in {sf_path}",
                )
        self.assertIn("אין משיכה של טיסות מהשרת", app_js)
        # Verify vacation style & weather suitability controls in UI
        self.assertNotIn("weather-telemetry-strip", app_js)
        for vtype_token in (
            "BEACH_AND_POOL",
            "NATURE_TRIP",
            "URBAN_CULTURE",
            "FAMILY_ATTRACTIONS_PARKS",
            "SNOW_AND_SKI",
            "WINTER_FESTIVE",
            "weather_suitability_score",
            "stub-weather-card",
            "data-weather-compact",
            "stub-kpi-grid",
            'data-kpi="school-fit"',
            "data-school-missed",
            "kpi-missed-paren",
            "weather-tooltip",
            "kpi-tooltip",
        ):
            self.assertIn(vtype_token, combined)
        self.assertNotIn('data-kpi="bonus-value"', app_js)

        # Verify live-fetch mode (`ELAL_LIVE_FETCH_ENABLED=1`) never returns fictitious flights
        # even when an existing database already had seeded proposals/itineraries referencing bonus rows
        old_env = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        try:
            os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            live_db, _pre_repo = self.make_isolated_env(auto_seed=True)
            pre_client = self.get_client(live_db)
            pre_client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "direct_holiday_code": "PESACH",
                    "direct_target_year": 2027,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["MAD"],
                },
            )
            os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
            live_client = self.get_client(live_db)
            live_resp = live_client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "direct_holiday_code": "PESACH",
                    "direct_target_year": 2027,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["MAD"],
                },
            )
            self.assertEqual(live_resp.status_code, 200)
            live_body = live_resp.json()
            self.assertEqual(live_body["count"], 0)
            self.assertEqual(live_body["proposals"], [])
            self.assertIn("אין משיכה של טיסות מהשרת", str(live_body.get("status_message_he") or ""))

            # Now simulate the Chrome Extension pushing the real MAD table rows (2027-04-26 -> 2027-05-05)
            sync_resp = live_client.post(
                "/api/v1/elal-bonus/sync",
                json={
                    "origin": "TLV",
                    "destinations": ["MAD"],
                    "start_date": "2027-04-20",
                    "end_date": "2027-05-06",
                    "force_refresh": True,
                    "rbd_payload": [
                        {
                            "destination_iata": "MAD",
                            "direction": "OUTBOUND",
                            "flight_number": "LY0395",
                            "flight_date": "2027-04-26",
                            "economy_seats": 2,
                            "premium_seats": 0,
                            "business_seats": 0,
                        },
                        {
                            "destination_iata": "MAD",
                            "direction": "INBOUND",
                            "flight_number": "LY0398",
                            "flight_date": "2027-05-05",
                            "economy_seats": 2,
                            "premium_seats": 0,
                            "business_seats": 0,
                        },
                    ],
                },
            )
            self.assertEqual(sync_resp.status_code, 200)
            self.assertEqual(sync_resp.json()["records_synced"], 2)

            after_sync_resp = live_client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-26",
                    "specific_return_date": "2027-05-05",
                    "flex_days_plus_minus": 0,
                    "min_trip_nights": 8,
                    "max_trip_nights": 10,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["MAD"],
                },
            )
            self.assertEqual(after_sync_resp.status_code, 200)
            after_body = after_sync_resp.json()
            self.assertGreater(after_body["count"], 0)
            self.assertEqual(after_body["proposals"][0]["itinerary"]["departure_date"], "2027-04-26")
            self.assertEqual(after_body["proposals"][0]["itinerary"]["return_date"], "2027-05-05")

            # Verify one-way bonus in Hanukkah 2026 (2026-12-10 outbound only) respects window end_date and max_trip_nights<=10
            han_sync_resp = live_client.post(
                "/api/v1/elal-bonus/sync",
                json={
                    "origin": "TLV",
                    "destinations": ["CDG"],
                    "start_date": "2026-12-03",
                    "end_date": "2026-12-18",
                    "force_refresh": True,
                    "rbd_payload": [
                        {
                            "destination_iata": "CDG",
                            "direction": "OUTBOUND",
                            "flight_number": "LY0319",
                            "flight_date": "2026-12-10",
                            "economy_seats": 2,
                            "premium_seats": 0,
                            "business_seats": 0,
                        },
                        {
                            "destination_iata": "CDG",
                            "direction": "INBOUND",
                            "flight_number": "LY0328",
                            "flight_date": "2026-12-14",
                            "economy_seats": 2,
                            "premium_seats": 0,
                            "business_seats": 0,
                        },
                    ],
                },
            )
            self.assertEqual(han_sync_resp.status_code, 200)
            han_search_resp = live_client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "direct_holiday_code": "HANUKKAH",
                    "direct_target_year": 2026,
                    "min_trip_nights": 2,
                    "max_trip_nights": 10,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["ANYWHERE"],
                },
            )
            self.assertEqual(han_search_resp.status_code, 200)
            han_body = han_search_resp.json()
            self.assertGreater(han_body["count"], 0)
            for prop in han_body["proposals"]:
                itin = prop["itinerary"]
                self.assertGreaterEqual(itin["trip_nights"], 2)
                self.assertLessEqual(itin["trip_nights"], 10)
                self.assertTrue(itin["return_date"].startswith("2026-12-"))
        finally:
            if old_env is None:
                os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            else:
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_env

    def test_f31_4_all_eight_component_files_exist_and_implement_ui_zones(self) -> None:
        comp_root = PROJECT_ROOT / "frontend" / "src" / "components"
        self.assertFalse((comp_root / "results" / "BonusVacationComparisonModal.tsx").exists())
        rel_paths = [
            "layout/AppShell.tsx",
            "layout/BreezyFlightsBrandHeader.tsx",
            "profile/FamilyProfileDrawer.tsx",
            "search/SearchControlPanel.tsx",
            "search/ElAlBonusSearchSubPanel.tsx",
            "calendar/MultiChildCalendarHeatmap.tsx",
            "results/BonusVacationOptionCard.tsx",
            "results/AllAirlinesItineraryCard.tsx",
        ]
        for rp in rel_paths:
            fp = comp_root / rp
            self.assertTrue(fp.exists(), f"Missing component: {fp}")
            self.assertGreater(fp.stat().st_size, 100)

    def test_f31_5_bidirectional_rtl_hebrew_and_ltr_english_switcher_support(
        self,
    ) -> None:
        app_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        self.assertIn("rtl", app_js)
        self.assertIn("ltr", app_js)
        # Verify CSS uses logical properties rather than physical left/right offsets that break RTL/LTR symmetry
        for logical_prop in ("inset-inline-start", "margin-inline", "padding-inline", "border-inline-start", "border-inline-end", "text-align: start"):
            self.assertIn(logical_prop, css)
        for forbidden_physical in ("margin-left:", "margin-right:", "padding-left:", "padding-right:", "border-left:", "border-right:", "text-align: left", "text-align: right"):
            self.assertNotIn(forbidden_physical, css)

    def test_f31_6_run3_rolling_holidays_manual_flex_dates_and_household_matmid_pool(
        self,
    ) -> None:
        live_db, _ = self.make_isolated_env(auto_seed=True)
        client = self.get_client(live_db)

        # 1. Rolling 1-year holidays endpoint advances years automatically across reference dates
        up_26 = client.get("/api/v1/moe-calendar/upcoming?as_of=2026-11-19").json()
        up_27 = client.get("/api/v1/moe-calendar/upcoming?as_of=2027-05-15").json()
        self.assertEqual(up_26["count"], 11)
        self.assertEqual(up_27["count"], 11)
        map_26 = {h["holiday_code"]: h for h in up_26["holidays"]}
        map_27 = {h["holiday_code"]: h for h in up_27["holidays"]}
        self.assertEqual(map_26["HANUKKAH"]["target_year"], 2026)
        self.assertEqual(map_27["HANUKKAH"]["target_year"], 2027)
        self.assertEqual(map_26["PESACH"]["target_year"], 2027)
        self.assertEqual(map_27["PESACH"]["target_year"], 2028)
        self.assertEqual(map_26["YOM_HAATZMAUT"]["target_year"], 2027)
        self.assertEqual(map_27["YOM_HAATZMAUT"]["target_year"], 2028)

        # 2. YOM_KIPPUR_SUKKOT_BRIDGE (14d) vs SUKKOT (9d) & ANYWHERE default discovery
        bridge_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "YOM_KIPPUR_SUKKOT_BRIDGE",
                "direct_target_year": map_26["YOM_KIPPUR_SUKKOT_BRIDGE"]["target_year"],
                "max_trip_nights": map_26["YOM_KIPPUR_SUKKOT_BRIDGE"]["holiday_days"],
                "airline_selection_mode": "EL_AL_ONLY",
                "enabled_loyalty_programs": ["ELAL_MATMID"],
                "destination_iatas": ["ANYWHERE"],
                "matmid_points_balance": 185000,
            },
        )
        self.assertEqual(bridge_resp.status_code, 200)
        bridge_body = bridge_resp.json()
        self.assertGreater(bridge_body["count"], 0)
        self.assertGreaterEqual(len(bridge_body["expanded_destinations"]), 40)
        for p in bridge_body["proposals"]:
            self.assertTrue(p["itinerary"]["departure_date"].startswith("2027-10"))
            self.assertTrue(p["itinerary"]["is_elal_flight"])

        # 3. Manual Date Entry (`SPECIFIC_DATES`) + `±` flexibility + household Matmid balance pool (R2, U3)
        for matmid_bal in (30000, 300000, 0):
            man_resp = client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-12",
                    "specific_return_date": "2027-04-19",
                    "flex_days_plus_minus": 2,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "enabled_loyalty_programs": ["ELAL_MATMID"],
                    "destination_iatas": ["ANYWHERE"],
                    "matmid_points_balance": matmid_bal,
                },
            )
            self.assertEqual(man_resp.status_code, 200)
            man_body = man_resp.json()
            self.assertGreater(man_body["count"], 0)
            itins = _assert_run11_search_response_contract(
                self, man_body, is_bonus_search=True
            )
            for itin in itins:
                if matmid_bal > 0:
                    min_pts = itin["min_points_per_bonus_ticket"]
                    self.assertTrue(min_pts is None or min_pts <= matmid_bal)
                self.assertIn(itin["primary_carrier_iata"], ("LY", "2U"))
                self.assertGreaterEqual(itin["departure_date"], "2027-04-10")
                self.assertLessEqual(itin["departure_date"], "2027-04-14")
                self.assertGreaterEqual(itin["return_date"], "2027-04-17")
                self.assertLessEqual(itin["return_date"], "2027-04-21")
            if matmid_bal == 30000:
                self.assertTrue(
                    any(
                        it["fulfillment_strategy"] == "FULL_BONUS_SAME_CABIN"
                        and it["seated_passengers_count"] >= 2
                        for it in itins
                    ),
                    "30,000 covers 1 ticket of FULL_BONUS_SAME_CABIN even when >=2 pax total exceeds 30,000",
                )
            if matmid_bal == 0:
                self.assertTrue(
                    any(
                        (it["min_points_per_bonus_ticket"] or 0) > 0
                        for it in itins
                    ),
                    "balance 0 means not entered and returns bonus results with 1-ticket minimums",
                )

    def test_f31_7_run12_compact_stub_weather_non_contradictory_badges_and_kpi_tooltips(
        self,
    ) -> None:
        """Run 12 (`M12`): compact side-stub weather, non-contradictory strategy badges & KPI tooltips."""
        import re as _re

        app_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        subpanel_tsx = (
            PROJECT_ROOT / "frontend" / "src" / "components" / "search" / "ElAlBonusSearchSubPanel.tsx"
        ).read_text("utf-8")

        # R1: bottom weather block removed from app.js; compact weather inside `.proposal-pass-stub`
        self.assertNotIn("weather-telemetry-strip", app_js)
        self.assertIn('class="stub-weather-card" data-weather-compact="true"', app_js)
        stub_idx = app_js.index('<div class="proposal-pass-stub">')
        self.assertGreater(app_js.index("${stubWeatherHtml}"), stub_idx)

        # R2: context-aware Open-Jaw & direction-consistent strategy badges in app.js + tsx
        self.assertIn("resolveCardStrategyBadge", app_js)
        self.assertIn("מסלול משולב (הלוך ל-", app_js)
        self.assertIn("Open-jaw bonus (out to ", app_js)
        self.assertIn("resolveStrategyBadgeHe", subpanel_tsx)
        self.assertGreater(len(subpanel_tsx.encode("utf-8")), 100)

        # R3: compact stub KPI cell (with missed days in parentheses inside school-fit), weather + KPI tooltips, and CSS rules
        self.assertGreater(app_js.index('class="stub-kpi-grid"'), stub_idx)
        self.assertNotIn('data-kpi="school-missed"', app_js)
        self.assertNotIn('data-kpi="bonus-value"', app_js)
        self.assertNotIn("החופשה המומלצת ביותר", app_js)
        self.assertNotIn("בחירה מובילה", app_js)
        self.assertNotIn("formatRecommendationTierLabel", app_js)
        for req_js in (
            'data-kpi="school-fit"',
            "data-school-missed",
            "kpi-missed-paren",
            "weather-tooltip",
            "bonus-flight-num",
            "bonus-flight-times",
            'role="tooltip"',
            'התאמה לחופשת בי"ס',
            "התאמה לחופשת בית ספר וחיסורים",
            "מומלץ ביעד במזג אוויר זה:",
            "What to do in this weather:",
            "School Break Fit",
            "איך חושב:",
            "משמעות:",
            "How calculated:",
            "Meaning:",
        ):
            self.assertIn(req_js, app_js)

        # CSS BiDi & unclipped overflow invariants
        self.assertNotIn("left", css.lower())
        self.assertNotIn("right", css.lower())
        self.assertNotIn("ellipsis", css.lower())
        self.assertIn("overflow: visible;", css)
        self.assertIn(".stub-weather-card", css)
        self.assertIn(".kpi-tooltip", css)
        media_bp = [int(m) for m in _re.findall(r"@media\s*\(\s*min-width:\s*(\d+)px\s*\)", css)]
        self.assertEqual(media_bp, sorted(media_bp))

    def test_f31_8_run13_desktop_access_strip_passenger_window_and_account_area_static_contract(
        self,
    ) -> None:
        """Run 13 (`M13` unified): top-bar-only sign-in/sign-out/account popover + above-search travelers bar & passenger editor."""
        import re as _re
        from html.parser import HTMLParser

        html = self.get_client().get("/").text
        app_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")

        void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

        class _Outline(HTMLParser):
            """Records every element with its attributes, parent and element children."""

            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.nodes: list[dict[str, Any]] = []
                self.stack: list[int] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
                node = {"tag": tag, "attrs": dict(attrs), "parent": self.stack[-1] if self.stack else None, "children": []}
                self.nodes.append(node)
                idx = len(self.nodes) - 1
                if node["parent"] is not None:
                    self.nodes[node["parent"]]["children"].append(idx)
                if tag not in void_tags:
                    self.stack.append(idx)

            def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
                self.handle_starttag(tag, attrs)
                if tag not in void_tags:
                    self.stack.pop()

            def handle_endtag(self, tag: str) -> None:
                for pos in range(len(self.stack) - 1, -1, -1):
                    if self.nodes[self.stack[pos]]["tag"] == tag:
                        del self.stack[pos:]
                        break

        outline = _Outline()
        outline.feed(html)
        nodes = outline.nodes
        by_id = {n["attrs"]["id"]: n for n in nodes if n["attrs"].get("id")}

        def inside(node: dict[str, Any], ancestor_id: str) -> bool:
            cur = node
            while cur["parent"] is not None:
                cur = nodes[cur["parent"]]
                if cur["attrs"].get("id") == ancestor_id:
                    return True
            return False

        # 1. Control rail: ONLY `#household-summary-bar` sits above `#zone-search` (both mobile and desktop)
        rails = [n for n in nodes if n["attrs"].get("class") == "sidebar-column"]
        self.assertEqual(len(rails), 1)
        rail_child_ids = [nodes[i]["attrs"].get("id") for i in rails[0]["children"]]
        self.assertEqual(
            rail_child_ids, ["household-summary-bar", "zone-search", "zone-profile"]
        )
        for removed_dup_id in (
            "btn-header-household",
            "header-household-compact",
            "header-family-pill",
            "header-points-pill",
            "rail-access-strip",
            "btn-rail-account",
            "btn-rail-edit-travelers",
            "rail-household-text",
            "rail-account-email",
            "rail-account-label",
        ):
            self.assertNotIn(removed_dup_id, by_id, f"{removed_dup_id} must not exist")

        # 2. Required elements and single-ID uniqueness
        for req_id in (
            "header-auth-wrap",
            "btn-header-auth",
            "header-auth-label",
            "btn-header-account",
            "header-account-email",
            "header-account-short",
            "btn-header-signout",
            "header-auth-popover",
            "profile-auth-card",
            "btn-google-signin",
            "profile-signin-disclaimer",
            "profile-user-disclaimer",
            "auth-notif-label-short",
            "household-summary-bar",
            "household-summary-text",
            "btn-open-profile-sheet",
            "profile-save-error",
            "profile-save-feedback",
            "btn-save-profile",
            "btn-close-profile-sheet",
            "btn-apply-profile-sheet",
            "profile-sheet-backdrop",
            "mobile-thumb-dock",
        ):
            self.assertIn(req_id, by_id, f"Missing #{req_id}")
            self.assertEqual(html.count(f'id="{req_id}"'), 1)

        # 3. Auth lives EXCLUSIVELY inside `#app-header` -> `#header-auth-wrap` (never inside `#zone-profile` or `.sidebar-column`)
        for auth_child in (
            "btn-header-auth",
            "btn-header-account",
            "btn-header-signout",
            "header-auth-popover",
            "profile-auth-card",
            "btn-google-signin",
            "profile-signin-disclaimer",
            "profile-user-disclaimer",
        ):
            self.assertTrue(inside(by_id[auth_child], "app-header"), auth_child)
            self.assertTrue(inside(by_id[auth_child], "header-auth-wrap"), auth_child)
            self.assertFalse(inside(by_id[auth_child], "zone-profile"), auth_child)

        # 4. Above-search travelers edit button contract
        edit_btn = by_id["btn-open-profile-sheet"]
        self.assertTrue(inside(edit_btn, "household-summary-bar"))
        self.assertEqual(edit_btn["tag"], "button")
        self.assertEqual(edit_btn["attrs"].get("type"), "button")
        self.assertEqual(edit_btn["attrs"].get("aria-haspopup"), "dialog")
        self.assertEqual(edit_btn["attrs"].get("aria-expanded"), "false")
        self.assertEqual(edit_btn["attrs"].get("aria-controls"), "zone-profile")
        self.assertEqual(edit_btn["attrs"].get("data-he"), "עריכה")
        self.assertEqual(edit_btn["attrs"].get("data-en"), "Edit")
        self.assertEqual(edit_btn["attrs"].get("data-aria-he"), "עריכת הרכב הנוסעים")
        self.assertEqual(edit_btn["attrs"].get("data-aria-en"), "Edit travelers")
        self.assertEqual(edit_btn["attrs"].get("aria-label"), edit_btn["attrs"].get("data-aria-he"))

        # 5. Travelers editor (`#zone-profile`) keeps save button & save error/feedback inside `#zone-profile`
        for prof_child in ("btn-save-profile", "profile-save-error", "profile-save-feedback"):
            self.assertTrue(inside(by_id[prof_child], "zone-profile"), prof_child)
            self.assertFalse(inside(by_id[prof_child], "profile-auth-card"), prof_child)
        self.assertEqual(by_id["profile-save-error"]["attrs"].get("role"), "alert")
        self.assertIn("hidden", by_id["profile-save-error"]["attrs"])

        # 6. Every `[data-he][data-en]` element has both languages and is a leaf node
        for node in nodes:
            attrs = node["attrs"]
            self.assertEqual("data-he" in attrs, "data-en" in attrs, attrs)
            self.assertEqual("data-aria-he" in attrs, "data-aria-en" in attrs, attrs)
            if "data-he" in attrs:
                self.assertTrue(attrs["data-he"] and attrs["data-en"], attrs)
                self.assertEqual(node["children"], [], attrs)

        # 7. CSS: `#household-summary-bar` is visible across all viewports (never hidden at 1180px), and `#zone-profile`
        #    is closed by default (`display: none`) and opens as a wide modal (`clamp(720px, 54vw, 880px)`) at `>=1180px`
        base_css, media_tail = css.split("@media (min-width: 560px)", 1)
        self.assertRegex(base_css, r"\.household-summary-bar\s*\{[^}]*display:\s*flex;")
        self.assertRegex(base_css, r"#zone-profile\s*\{\s*display:\s*none;\s*\}")
        self.assertNotIn("household-summary-bar", media_tail)
        media_blocks = _re.split(r"@media\s*\(\s*min-width:\s*(\d+)px\s*\)", "@media (min-width: 560px)" + media_tail)
        blocks_by_width: dict[int, str] = {}
        for width_txt, block_txt in zip(media_blocks[1::2], media_blocks[2::2]):
            blocks_by_width[int(width_txt)] = blocks_by_width.get(int(width_txt), "") + block_txt
        self.assertIn(1180, blocks_by_width)
        desktop_block = blocks_by_width[1180]
        self.assertRegex(
            desktop_block,
            r'#zone-profile\[data-sheet-view="travelers"\]\s*\{[^}]*width:\s*clamp\(520px,\s*40vw,\s*580px\);',
        )
        self.assertIsNone(
            _re.search(r"#zone-profile,\s*#zone-profile\.is-sheet-open\s*\{[^}]*(display|position)\s*:", desktop_block)
        )

        # 8. JS state & handlers
        for req_js in (
            "isAuthPopoverOpen",
            "setAuthPopoverOpen",
            "profileSheetView",
            "data-sheet-view",
            "window.innerWidth < 1180",
            "closeProfileSheetOnBreakpointCross",
            "window.location.assign(loginUrl);",
            "profile-save-error",
        ):
            self.assertIn(req_js, app_js)
        self.assertEqual(app_js.count("window.location.assign(loginUrl);"), 1)

    def test_f31_9_run14_workplace_calendar_cost_zero_children_and_popup_contracts(
        self,
    ) -> None:
        """Run 14 (`M14`): statutory Israeli workplace calendar, 4-bucket workday cost, 0-children suppression & shared dual-calendar popup."""
        import re as _re
        from bs4 import BeautifulSoup

        html = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        app_js = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text("utf-8")
        domain_ts = (PROJECT_ROOT / "frontend" / "src" / "types" / "domain.ts").read_text("utf-8")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Shared toggleable popup markup & dual side-by-side ledgers
        cal_zone = soup.find("section", id="zone-calendar")
        self.assertIsNotNone(cal_zone)
        self.assertTrue(cal_zone.has_attr("hidden"))
        self.assertIn("calendar-popup-modal", cal_zone.get("class") or [])
        self.assertNotIn("בוגרים", cal_zone.get_text(" ", strip=True))

        dual_grid = cal_zone.find(id="calendar-dual-grid")
        self.assertIsNotNone(dual_grid)
        col_moe = dual_grid.find(id="calendar-col-moe")
        col_work = dual_grid.find(id="calendar-col-workplace")
        self.assertIsNotNone(col_moe)
        self.assertIsNotNone(col_work)
        self.assertIsNotNone(col_moe.find("table", id="moe-calendar-table"))
        self.assertIsNotNone(col_work.find("table", id="workplace-calendar-table"))
        self.assertIsNotNone(col_work.find("tbody", id="workplace-calendar-tbody"))
        self.assertIsNotNone(soup.find(id="calendar-modal-backdrop"))

        for trig_id in ("btn-toggle-calendar", "btn-mobile-dock-calendar"):
            trig = soup.find("button", id=trig_id)
            self.assertIsNotNone(trig, trig_id)
            self.assertEqual(trig.get("aria-haspopup"), "dialog")
            self.assertEqual(trig.get("aria-expanded"), "false")
            self.assertEqual(trig.get("aria-controls"), "zone-calendar")

        # 2. Terminology guard: zero standalone "בוגרים" across frontend assets
        bogrim_re = _re.compile(r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])")
        for asset_name, asset_txt in (
            ("index.html", html),
            ("app.js", app_js),
            ("app.css", css),
            ("domain.ts", domain_ts),
        ):
            self.assertIsNone(bogrim_re.search(asset_txt), f"Forbidden בוגרים in {asset_name}")

        # 3. CSS & JS Run 14 contracts
        self.assertNotIn("left", css.lower())
        self.assertNotIn("right", css.lower())
        self.assertNotIn("ellipsis", css.lower())
        for req_css in (
            ".flight-bonus-points-pill",
            '.stub-kpi-grid[data-paired-vacation="true"]',
            ".calendar-modal-backdrop",
            "#zone-calendar.is-calendar-open",
            ".calendar-dual-grid",
            ".work-holiday-table",
        ):
            self.assertIn(req_css, css)
        self.assertNotIn("stub-pax-summary", app_js)
        self.assertNotIn("stub-fare-ledger", app_js)
        for req_js in (
            "projectWorkplaceHolidaysClient",
            "computeTripWorkdaysClient",
            "lastSearchProfile",
            "hasChildrenInSearch",
            'data-kpi="workdays-cost"',
            "renderWorkplaceCalendarTable",
            "CALENDAR_MODAL_INERT_SELECTORS",
            "חופשת עבודה",
            "Workdays Off",
        ):
            self.assertIn(req_js, app_js)
        for req_html in (
            "לוח חגים ומועדים במשק",
            "Public &amp; Workplace Holidays",
            "לוח חופשות משרד החינוך",
            "School Vacation Calendar",
        ):
            self.assertIn(req_html, html)

        # Selective inert must NEVER include #app-header or #mobile-thumb-dock so 2nd click closes popup
        inert_block = app_js.split("CALENDAR_MODAL_INERT_SELECTORS", 1)[1].split("];", 1)[0]
        self.assertNotIn("#app-header", inert_block)
        self.assertNotIn("#mobile-thumb-dock", inert_block)

        # 4. REST API contracts on isolated DB
        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)

        cal_resp = client.get("/api/v1/moe-calendar/2026-2027")
        self.assertEqual(cal_resp.status_code, 200)
        cal_json = cal_resp.json()
        self.assertEqual(len(cal_json.get("workplace_holidays") or []), 10)
        self.assertNotIn("בוגרים", json.dumps(cal_json["workplace_holidays"], ensure_ascii=False))

        wp_resp = client.get("/api/v1/workplace-calendar/2026-2027")
        self.assertEqual(wp_resp.status_code, 200)
        self.assertEqual(wp_resp.json()["count"], 10)
        self.assertEqual(client.get("/api/v1/workplace-calendar/1899-1900").status_code, 422)

        srch = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2027-04-22",
                "specific_return_date": "2027-04-28",
                "flex_days_plus_minus": 0,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LCA", "FCO", "ATH"],
                "inline_profile": {"adults_count": 2, "matmid_points_balance": 0, "children": []},
            },
        )
        self.assertEqual(srch.status_code, 200)
        props = srch.json()["proposals"]
        self.assertGreater(len(props), 0)
        for p in props:
            self.assertEqual(p["workplace_vacation_days_cost"], 1.5)
            self.assertEqual(p["chol_hamoed_workdays_count"], 3)
            self.assertEqual(p["official_holiday_workdays_saved_count"], 2)
            self.assertEqual(p["weekend_days_count"], 2)
            self.assertEqual(p["holiday_or_weekend_days_count"], 4)
            for legacy_pto_key in (
                "total_vacation_days",
                "parent_pto_days_used",
                "pto_efficiency_ratio",
                "vacation_utilization_score",
            ):
                self.assertNotIn(legacy_pto_key, p)

    def test_f31_10_run15_admin_yearly_period_telemetry_and_zero_remote_trigger_contracts(
        self,
    ) -> None:
        """Run 15 static & API contract guard:
        - Frontend assets (`index.html`, `app.js`, `app.css`) contain zero remote trigger routes, zero 5-shard tokens,
          zero hardcoded admin identity strings (`yoni`, `budovsky`, `בודובסקי`), and zero standalone `'יוני'`.
        - CSS retains logical-only properties, ascending `min-width` breakpoints, and `#zone-profile[data-sheet-view="travelers"]` `clamp(520px, 40vw, 580px)`.
        - `GET /api/v1/admin/bonus-sync-status` enforces `401`/`403`/`200` SHA-256 admin gating and returns 12-month `periods` (`horizon_days == 350`, `'יונ׳'`), while removed trigger/poll/ack endpoints return `404`.
        """
        import re

        html_txt = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js_txt = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text(encoding="utf-8")
        css_txt = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"(?i)(left|right)", css_txt))
        self.assertNotIn("ellipsis", css_txt.lower())
        self.assertIsNone(re.search(r"@media[^{]*max-width", css_txt, re.IGNORECASE))
        widths = [
            int(m.group(1))
            for m in re.finditer(r"@media\s*\(\s*min-width:\s*(\d+)px\s*\)", css_txt)
        ]
        self.assertEqual(widths, sorted(widths))
        self.assertIn("clamp(520px, 40vw, 580px)", css_txt)

        forbidden_tokens = (
            "bonus-sync-trigger",
            "sync-trigger-poll",
            "sync-trigger-ack",
            "trigger_job",
            "next_shard",
            "admin-shard",
            "5 חלקים",
            "shard",
            "yoni",
            "budovsky",
            "בודובסקי",
        )
        for asset_name, asset_txt in (("index.html", html_txt), ("app.js", js_txt), ("app.css", css_txt)):
            low = asset_txt.lower()
            for bad in forbidden_tokens:
                self.assertNotIn(bad, low, f"Forbidden token {bad!r} in {asset_name}")
            self.assertIsNone(
                re.search(r"(?<![א-ת])יוני(?![א-ת])", asset_txt),
                f"Standalone 'יוני' found in {asset_name}",
            )

        db_path, _repo = self.make_isolated_env(auto_seed=True)
        old_mode = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
        old_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
        os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"
        self.addCleanup(
            lambda: os.environ.__setitem__("VACATION_PLANNER_AUTH_TEST_MODE", old_mode)
            if old_mode is not None
            else os.environ.pop("VACATION_PLANNER_AUTH_TEST_MODE", None)
        )
        self.addCleanup(
            lambda: os.environ.__setitem__("ELAL_LIVE_FETCH_ENABLED", old_live)
            if old_live is not None
            else os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
        )

        guest_cli = self.get_client(db_path)
        self.assertEqual(guest_cli.request("GET", "/api/v1/admin/bonus-sync-status").status_code, 401)
        self.assertEqual(guest_cli.request("POST", "/api/v1/admin/bonus-sync-trigger", json_body={}).status_code, 404)
        self.assertEqual(guest_cli.request("GET", "/api/v1/elal-bonus/sync-trigger-poll").status_code, 404)
        self.assertEqual(guest_cli.request("POST", "/api/v1/elal-bonus/sync-trigger-ack", json_body={}).status_code, 404)

        reg_cli = self.get_client(db_path)
        self.assertEqual(
            reg_cli.request("POST", "/api/v1/auth/test-login", json_body={"email": "family.demo@gmail.com"}).status_code,
            200,
        )
        self.assertEqual(reg_cli.request("GET", "/api/v1/admin/bonus-sync-status").status_code, 403)

        adm_cli = self.get_client(db_path)
        adm_email = ".".join(["yoni", "budovsky"]) + "@gmail.com"
        self.assertEqual(
            adm_cli.request("POST", "/api/v1/auth/test-login", json_body={"email": adm_email}).status_code,
            200,
        )
        adm_sess = adm_cli.request("GET", "/api/v1/auth/session").json()
        self.assertTrue(adm_sess["is_admin"])
        self.assertEqual(
            adm_cli.request(
                "POST",
                "/api/v1/admin/bonus-sync-trigger",
                json_body={},
                headers={"X-CSRF-Token": adm_sess["csrf_token"]},
            ).status_code,
            404,
        )
        adm_res = adm_cli.request("GET", "/api/v1/admin/bonus-sync-status")
        self.assertEqual(adm_res.status_code, 200)
        sync_obj = adm_res.json()["admin_bonus_sync"]
        self.assertEqual(sync_obj["horizon_days"], 350)
        self.assertEqual(len(sync_obj["periods"]), 12)
        self.assertNotIn("shards", sync_obj)
        self.assertNotIn("trigger_job", sync_obj)
        june_list = [p for p in sync_obj["periods"] if p["month"] == 6]
        self.assertEqual(len(june_list), 1)
        self.assertIn("יונ׳", june_list[0]["label_he"])

    def test_f31_11_run16_booking_handoff_modal_and_single_adult_url_contracts(
        self,
    ) -> None:
        """Run 16 (`M16`) static & API contracts:
        - `#booking-handoff-backdrop` & `#booking-handoff-modal` live at `<body>` root outside `#zone-results` & `#dashboard-shell`.
        - Leaf-only `[data-he][data-en]` and paired `[data-aria-he][data-aria-en]` on all modal markup.
        - `app.css` keeps zero `left`/`right`/`ellipsis`/`max-width`, ascending `@media (min-width: ...)`, and travelers `clamp(520px, 40vw, 580px)`.
        - Zero standalone `'בוגרים'`, zero `'yoni'`/`'budovsky'`/`'בודובסקי'`/standalone `'יוני'`.
        - `POST /api/v1/vacations/search` returns `elal_google_flights_single_adult_url` distinct from `elal_google_flights_url` when `seatedCount > 1` and equal when `1 adult, 0 children`.
        """
        import re as _re
        from urllib.parse import parse_qs, urlparse
        from bs4 import BeautifulSoup

        html_txt = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js_txt = (PROJECT_ROOT / "frontend" / "src" / "app.js").read_text(encoding="utf-8")
        css_txt = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
        ts_txt = (PROJECT_ROOT / "frontend" / "src" / "types" / "domain.ts").read_text(encoding="utf-8")

        soup = BeautifulSoup(html_txt, "html.parser")
        backdrop = soup.find(id="booking-handoff-backdrop")
        modal = soup.find(id="booking-handoff-modal")
        self.assertIsNotNone(backdrop)
        self.assertIsNotNone(modal)
        self.assertTrue(modal.has_attr("hidden"))
        self.assertIsNone(soup.select_one("#zone-results #booking-handoff-modal"))
        self.assertIsNone(soup.select_one("#dashboard-shell #booking-handoff-modal"))
        self.assertIsNone(soup.select_one("#dashboard-shell #booking-handoff-backdrop"))
        self.assertIsNotNone(modal.find(id="btn-close-booking-handoff"))
        self.assertIsNotNone(modal.find(id="booking-handoff-body"))
        self.assertIsNotNone(modal.find(id="booking-handoff-cta-group"))
        self.assertIsNotNone(modal.find("input", id="input-booking-handoff-suppress"))
        suppress_span = modal.find(id="booking-handoff-suppress-text")
        self.assertIsNotNone(suppress_span)
        self.assertEqual(suppress_span.get("data-he"), "אל תציג לי שוב את ההסבר במכשיר זה")
        self.assertEqual(suppress_span.get("data-en"), "Don't show this guide again on this device")

        self.assertIsNone(_re.search(r"(?i)(left|right)", css_txt))
        self.assertNotIn("ellipsis", css_txt.lower())
        self.assertIsNone(_re.search(r"@media[^{]*max-width", css_txt, _re.IGNORECASE))
        widths = [
            int(m.group(1))
            for m in _re.finditer(r"@media\s*\(\s*min-width:\s*(\d+)px\s*\)", css_txt)
        ]
        self.assertEqual(widths, sorted(widths))
        self.assertIn("clamp(520px, 40vw, 580px)", css_txt)

        bogrim_re = _re.compile(r"(?<![א-ת])(?:של\s+)?(?:ה|ל|ב|ו|ש|כ)?בוגרים(?![א-ת])")
        yoni_he_re = _re.compile(r"(?<![א-ת])יוני(?![א-ת])")
        for asset_name, asset_txt in (
            ("index.html", html_txt),
            ("app.js", js_txt),
            ("app.css", css_txt),
            ("domain.ts", ts_txt),
        ):
            self.assertIsNone(bogrim_re.search(asset_txt), f"Forbidden בוגרים in {asset_name}")
            self.assertIsNone(yoni_he_re.search(asset_txt), f"Forbidden standalone יוני in {asset_name}")
            low = asset_txt.lower()
            for bad in ("yoni", "budovsky", "בודובסקי"):
                self.assertNotIn(bad, low, f"Forbidden {bad!r} in {asset_name}")

        for req_js in (
            "BOOKING_HANDOFF_SUPPRESS_KEY",
            "fvp_elal_handoff_suppress_v1",
            "BOOKING_HANDOFF_INERT_SELECTORS",
            "resolveElAlSingleAdultGoogleFlightsUrl",
            "openBookingHandoffModal",
            "closeBookingHandoffModal",
            "syncBodyScrollLock",
            'data-booking-guide-trigger="true"',
        ):
            self.assertIn(req_js, js_txt)
        self.assertIn("elal_google_flights_single_adult_url: string | null;", ts_txt)

        db_path, _repo = self.make_isolated_env(auto_seed=True)
        client = self.get_client(db_path)

        # Multi-passenger (4 seated): single-adult URL distinct from full-party URL
        srch_multi = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "inline_profile": {
                    "adults_count": 2,
                    "matmid_points_balance": 120000,
                    "children": [
                        {"id": "c1", "child_name": "ילד", "child_age_years": 8, "framework_type": "ELEMENTARY_1_3"},
                        {"id": "c2", "child_name": "ילדה", "child_age_years": 5, "framework_type": "MUNICIPAL_GAN"},
                    ],
                },
            },
        )
        self.assertEqual(srch_multi.status_code, 200)
        props_m = srch_multi.json()["proposals"]
        self.assertGreater(len(props_m), 0)
        itin_m = props_m[0]["itinerary"]
        self.assertTrue(itin_m["elal_google_flights_url"].startswith("https://www.google.com/travel/flights"))
        self.assertTrue(
            itin_m["elal_google_flights_single_adult_url"].startswith("https://www.google.com/travel/flights")
        )
        self.assertNotEqual(
            itin_m["elal_google_flights_single_adult_url"],
            itin_m["elal_google_flights_url"],
        )
        qs_1a = {
            k: v[0]
            for k, v in parse_qs(urlparse(itin_m["elal_google_flights_single_adult_url"]).query).items()
        }
        self.assertEqual(qs_1a["curr"], "USD")
        self.assertEqual(qs_1a["gl"], "IL")
        self.assertEqual(qs_1a["hl"], "en")
        self.assertIn("with 1 adult", qs_1a["q"])
        self.assertTrue(qs_1a["q"].endswith("nonstop"))
        self.assertNotIn("on EL AL", qs_1a["q"])

        # Solo adult (1 seated, 0 children): single-adult URL equals full-party URL
        srch_solo = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "inline_profile": {"adults_count": 1, "matmid_points_balance": 120000, "children": []},
            },
        )
        self.assertEqual(srch_solo.status_code, 200)
        props_s = srch_solo.json()["proposals"]
        self.assertGreater(len(props_s), 0)
        itin_s = props_s[0]["itinerary"]
        self.assertEqual(
            itin_s["elal_google_flights_single_adult_url"],
            itin_s["elal_google_flights_url"],
        )


# ============================================================================
# Feature F32: Installable PWA & Preservation of 7 Specification Docs (5 tests)
# ============================================================================
class TestTier1F32InstallablePwaAndDocsPreservation(Tier1BaseTestCase):
    def test_f32_1_pwa_manifest_webmanifest_served_and_valid_rtl_standalone(
        self,
    ) -> None:
        client = self.get_client()
        resp = client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        manifest = resp.json()
        self.assertEqual(manifest["dir"], "rtl")
        self.assertTrue(str(manifest["lang"]).startswith("he"))
        self.assertEqual(manifest["display"], "standalone")

    def test_f32_2_service_worker_sw_js_served_and_implements_offline_caching(
        self,
    ) -> None:
        client = self.get_client()
        resp = client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        for ev in ("install", "activate", "fetch"):
            self.assertIn(ev, resp.text)

    def test_f32_3_seven_original_specification_documents_preserved_intact(
        self,
    ) -> None:
        docs = [
            "README.md",
            "APPLICATION_PLAN.md",
            "docs/01_architecture_and_tech_stack.md",
            "docs/02_moe_calendar_and_maximization.md",
            "docs/03_airlines_and_elal_bonus_engine.md",
            "docs/04_ui_ux_and_user_workflows.md",
            "docs/05_implementation_roadmap_and_rubric.md",
        ]
        for rel in docs:
            p = PROJECT_ROOT / rel
            self.assertTrue(p.exists(), f"Missing doc: {p}")
            self.assertGreater(p.stat().st_size, 4000)

    def test_f32_4_config_settings_yaml_exists_and_matches_contract(self) -> None:
        cfg = yaml.safe_load((PROJECT_ROOT / "config" / "settings.yaml").read_text("utf-8"))
        self.assertEqual(cfg["app"]["default_origin_iata"], "TLV")
        self.assertIn("https://www.elal.com/rbddataclients/", cfg["elal_rbd_client"]["base_url"])
        self.assertAlmostEqual(cfg["optimization_weights"]["ctos_calendar_weight"], 0.55)
        self.assertAlmostEqual(cfg["optimization_weights"]["ctos_flight_weight"], 0.45)

    def test_f32_5_zero_broken_imports_across_all_backend_packages_in_sandbox(
        self,
    ) -> None:
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
            "backend.app.cli.main",
            "backend.app.main",
        ]
        for mod_name in modules:
            self.assertIsNotNone(importlib.import_module(mod_name))

    def test_f32_6_run10_scoped_thailand_breezyflights_branding_and_three_surface_disclaimers(
        self,
    ) -> None:
        import re
        from bs4 import BeautifulSoup

        html = (PROJECT_ROOT / "frontend" / "index.html").read_text("utf-8")
        css = (PROJECT_ROOT / "frontend" / "src" / "styles" / "app.css").read_text("utf-8")
        soup = BeautifulSoup(html, "html.parser")

        # R3: Top header breezyflights branding (single wordmark, not duplicated inside #hero-eyebrow) + scoped --thai-* custom properties
        hdr_wordmark = soup.select_one("#app-header #header-title .brand-wordmark")
        self.assertIsNotNone(hdr_wordmark)
        self.assertEqual(hdr_wordmark.get_text(strip=True), "breezyflights")
        hero_brand = soup.select_one("#vacation-hero #hero-eyebrow .hero-brand-inline")
        self.assertIsNone(hero_brand)
        hero_eyebrow_el = soup.select_one("#vacation-hero #hero-eyebrow")
        self.assertIsNotNone(hero_eyebrow_el)
        self.assertNotIn("breezyflights", hero_eyebrow_el.get_text(" ", strip=True).lower())
        self.assertIsNotNone(soup.select_one("#vacation-hero svg.hero-scenic-svg"))
        hero_section = soup.find(id="vacation-hero")
        self.assertIsNotNone(hero_section)
        hero_txt = hero_section.get_text(" ", strip=True)
        for forbidden_hero_term in ("תאילנד", "Thailand", "בנגקוק", "פוקט", "Bangkok", "Phuket"):
            self.assertNotIn(forbidden_hero_term, hero_txt)
        self.assertIsNone(soup.find(id="hero-highlights"))
        self.assertEqual(soup.select("#vacation-hero .hero-highlight-chip"), [])

        root_match = re.search(r":root\s*\{([^}]*)\}", css)
        self.assertIsNotNone(root_match)
        self.assertNotIn("--thai-", root_match.group(1))
        self.assertIn("--thai-abyss-teal", css)

        # R2: Multi-select picker coexists with hidden <select id="select-destination" multiple>
        self.assertIsNotNone(soup.find("div", id="destination-multiselect"))
        dest_sel = soup.find("select", id="select-destination")
        self.assertIsNotNone(dest_sel)
        self.assertTrue(dest_sel.has_attr("multiple"))

        # R4: Footer, profile sign-in box, and local test OAuth page disclaimers
        for disc_id in (
            "footer-elal-disclaimer",
            "profile-signin-disclaimer",
            "profile-user-disclaimer",
        ):
            disc_el = soup.find(id=disc_id)
            self.assertIsNotNone(disc_el, f"Missing disclaimer #{disc_id}")
            self.assertIn(
                "אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על",
                disc_el.get_text(" ", strip=True),
            )
            self.assertIn("not affiliated with", disc_el.get("data-en", ""))


if __name__ == "__main__":
    unittest.main()
