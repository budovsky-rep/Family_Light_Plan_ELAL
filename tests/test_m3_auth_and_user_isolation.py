"""Milestone 5 (`M5`) Unit Test Suite: Gmail OAuth 2.0 + PKCE, Clean Guest State & Per-User Isolation.

Covers all 10 core Run 5 security, privacy, authentication, legacy-data quarantine,
and future-notification readiness requirements (`R1`, `R2`, `R3`, `R4`, `AC-1..3`)
using hermetic `:memory:` and `TemporaryDirectory` SQLite databases with zero
outbound network calls.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
import http.client
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
from typing import Any, Optional
import unittest
import urllib.parse

from backend.app.auth_service import (
    build_unsigned_or_hs256_jwt_for_test,
    pkce_s256_challenge,
    redact_pii,
    sanitize_return_to,
    sha256_hex,
)
from backend.app.cli.main import main as cli_main
from backend.app.main import VacationPlannerTestClient, create_http_server
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import build_default_family_profile


class _EnvContext:
    """Context manager to temporarily set/unset environment variables."""

    def __init__(self, overrides: dict[str, Optional[str]]) -> None:
        self.overrides = overrides
        self._saved: dict[str, Optional[str]] = {}

    def __enter__(self) -> "_EnvContext":
        for k, v in self.overrides.items():
            self._saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for k, prev in self._saved.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def login_via_oauth_pkce(
    client: VacationPlannerTestClient,
    email: str,
    display_name: str = "",
    google_sub: Optional[str] = None,
    https_forwarded: bool = True,
) -> dict[str, Any]:
    """Drive the full server-side `/api/v1/auth/google/login` -> `/api/v1/auth/google/callback` OAuth 2.0 + PKCE flow."""
    captured_nonces: list[str] = []
    captured_verifiers: list[str] = []
    repo = client.router.repository
    orig_create = repo.create_oauth_login_state

    def _spy_create_state(*args: Any, **kwargs: Any) -> Any:
        nonce_val = kwargs.get("nonce") if "nonce" in kwargs else args[2]
        verifier_val = kwargs.get("code_verifier") if "code_verifier" in kwargs else args[1]
        captured_nonces.append(str(nonce_val))
        captured_verifiers.append(str(verifier_val))
        return orig_create(*args, **kwargs)

    def _exchanger(
        code: str,
        code_verifier: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        assert code == "test-google-auth-code"
        assert code_verifier == captured_verifiers[-1]
        assert redirect_uri.endswith("/api/v1/auth/google/callback")
        assert client_secret == "unit-test-client-secret"
        now_ep = int(time.time())
        sub_val = google_sub or f"google-sub-{sha256_hex(email.lower())[:24]}"
        id_tok = build_unsigned_or_hs256_jwt_for_test(
            {
                "iss": "https://accounts.google.com",
                "aud": client_id,
                "sub": sub_val,
                "email": email,
                "email_verified": True,
                "name": display_name or email.split("@", 1)[0],
                "nonce": captured_nonces[-1],
                "iat": now_ep,
                "exp": now_ep + 3600,
            }
        )
        return {
            "id_token": id_tok,
            "access_token": "ephemeral-google-access-token-must-be-discarded",
            "refresh_token": "ephemeral-google-refresh-token-must-be-discarded",
        }

    client.router.auth_service.token_exchanger = _exchanger
    req_hdrs = {"X-Forwarded-Proto": "https"} if https_forwarded else {}
    repo.create_oauth_login_state = _spy_create_state  # type: ignore[method-assign]
    try:
        with _EnvContext(
            {
                "GOOGLE_OAUTH_CLIENT_ID": "unit-test-client-id.apps.googleusercontent.com",
                "GOOGLE_OAUTH_CLIENT_SECRET": "unit-test-client-secret",
                "VACATION_PLANNER_AUTH_TEST_MODE": None,
            }
        ):
            login_resp = client.get("/api/v1/auth/google/login", headers=req_hdrs)
            assert login_resp.status_code == 302, login_resp.text
            loc = login_resp.headers["Location"]
            q_map = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(loc).query))
            assert q_map["code_challenge"] == pkce_s256_challenge(captured_verifiers[-1])
            assert q_map["code_challenge_method"] == "S256"

            cb_resp = client.get(
                f"/api/v1/auth/google/callback?code=test-google-auth-code&state={urllib.parse.quote(q_map['state'])}",
                headers=req_hdrs,
            )
            assert cb_resp.status_code == 302, cb_resp.text
            sess_resp = client.get("/api/v1/auth/session", headers=req_hdrs)
            assert sess_resp.status_code == 200
            sess_json = sess_resp.json()
            assert sess_json["authenticated"] is True
            return sess_json
    finally:
        repo.create_oauth_login_state = orig_create  # type: ignore[method-assign]


class TestM3AuthAndUserIsolation(unittest.TestCase):
    """Comprehensive unit tests for Gmail Sign-In, Per-User Isolation & Privacy (`M5`)."""

    # 1. Clean unauthenticated experience & zero shared profile exposure
    def test_unauthenticated_clean_state_never_exposes_yoni_or_saved_profiles(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "clean_boot.db"
            guest_client = VacationPlannerTestClient(db_path=db_path)

            # Save a private profile for a real signed-in victim user on the same DB
            victim_client = VacationPlannerTestClient(db_path=db_path)
            v_sess = login_via_oauth_pkce(victim_client, "victim.parent@gmail.com", "Victim")
            v_put = victim_client.put(
                "/api/v1/profile",
                json={
                    "profile_name": "משפחה פרטית",
                    "adults_count": 2,
                    "matmid_points_balance": 210000,
                    "children": [{"child_age_years": 6, "framework_type": "ELEMENTARY_1_3"}],
                },
                headers={"X-CSRF-Token": v_sess["csrf_token"]},
            )
            self.assertEqual(v_put.status_code, 200)
            victim_prof_id = v_put.json()["id"]

            # GET / static HTML contains zero Yoni / Budovsky / 185k / 3 Children defaults
            html_resp = guest_client.get("/")
            self.assertEqual(html_resp.status_code, 200)
            self.assertIsNone(re.search(r"(?<![א-ת])יוני(?![א-ת])", html_resp.text))
            for forbidden in (
                "בודובסקי",
                "185,000",
                "185000",
                "2 Adults + 3 Children",
                "נועה",
                "עידו",
                "מאיה",
            ):
                self.assertNotIn(forbidden, html_resp.text)

            # Session endpoint reports clean unauthenticated state
            sess = guest_client.get("/api/v1/auth/session")
            self.assertEqual(sess.status_code, 200)
            self.assertEqual(sess.headers.get("Cache-Control"), "no-store, private")
            self.assertFalse(sess.json()["authenticated"])
            self.assertIsNone(sess.json()["user"])
            self.assertIsNone(sess.json()["csrf_token"])

            # Unauthenticated GET / PUT / DELETE /api/v1/profile return 401 even with victim profile_id
            self.assertEqual(guest_client.get("/api/v1/profile").status_code, 401)
            self.assertEqual(
                guest_client.get(
                    f"/api/v1/profile?profile_id=default-family-profile"
                ).status_code,
                401,
            )
            self.assertEqual(
                guest_client.get(
                    f"/api/v1/profile?profile_id={victim_prof_id}"
                ).status_code,
                401,
            )
            self.assertEqual(
                guest_client.put("/api/v1/profile", json={"adults_count": 4}).status_code,
                401,
            )
            self.assertEqual(guest_client.delete("/api/v1/profile").status_code, 401)

            # Calendar endpoints work for guests and ignore ?profile_id=...
            up_resp = guest_client.get(
                f"/api/v1/moe-calendar/upcoming?profile_id={victim_prof_id}&as_of=2026-11-20"
            )
            self.assertEqual(up_resp.status_code, 200)
            self.assertEqual(up_resp.json()["count"], 11)
            cal_resp = guest_client.get(
                f"/api/v1/moe-calendar/2026-2027?profile_id=default-family-profile"
            )
            self.assertEqual(cal_resp.status_code, 200)

    # 2. Unauthenticated guest can search, compare, and export .ics with zero SQLite writes
    def test_unauthenticated_guest_can_search_compare_and_export_ics_without_login(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "guest_zero_write.db"
            guest = VacationPlannerTestClient(db_path=db_path)

            # Default clean 2-adult guest search in HOLIDAY_DIRECT_INTENT
            r1 = guest.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "direct_holiday_code": "PESACH",
                    "direct_target_year": 2027,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["FCO", "ATH"],
                },
            )
            self.assertEqual(r1.status_code, 200)
            props_1 = r1.json()["proposals"]
            self.assertGreaterEqual(len(props_1), 2)

            # Guest search with ephemeral inline family overrides (children ages 1 & 8 + 150k Matmid)
            r2 = guest.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 1,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["FCO"],
                    "inline_profile": {
                        "adults_count": 2,
                        "matmid_points_balance": 150000,
                        "children": [
                            {"child_age_years": 1, "framework_type": None},
                            {"child_age_years": 8, "framework_type": "ELEMENTARY_1_3"},
                        ],
                    },
                },
            )
            self.assertEqual(r2.status_code, 200)
            props_2 = r2.json()["proposals"]
            self.assertGreater(len(props_2), 0)
            it_2 = props_2[0]["itinerary"]
            self.assertEqual(it_2["seated_passengers_count"], 3)  # 2 adults + 1 child (1 infant_lap = 0 seats)
            self.assertNotIn("family_ticket_allocation", it_2)
            # Run 11: no cash estimate in the response; the result says where bonus seats exist
            for removed_key in (
                "estimated_cash_usd",
                "is_cash_price_estimate",
                "total_out_of_pocket_cash_usd",
                "net_cash_saved_usd",
                "cents_per_point_value",
                "total_matmid_points",
            ):
                self.assertNotIn(removed_key, it_2)
            self.assertNotIn("is_cash_price_estimate", r2.json())
            self.assertIn(
                it_2["bonus_direction_coverage"],
                ("BOTH_DIRECTIONS", "OUTBOUND_ONLY", "INBOUND_ONLY"),
            )
            self.assertIs(it_2["points_are_estimated"], True)

            # Ephemeral guest proposals resolve cleanly for guest requester; removed /compare and .ics endpoints return 404
            pids = [props_1[0]["id"], props_2[0]["id"]]
            self.assertIsNotNone(
                guest.router.planner_service.resolve_proposal_for_requester(
                    pids[0], requester_user_id=None, enforce_owner=True
                )
            )
            cmp_r = guest.post("/api/v1/vacations/compare", json={"proposal_ids": pids})
            self.assertEqual(cmp_r.status_code, 404)
            ics_r = guest.get(f"/api/v1/vacations/{pids[0]}/export.ics")
            self.assertEqual(ics_r.status_code, 404)

            # Verify ZERO rows were written to family_profiles, child_frameworks, or flight_search_queries!
            conn = sqlite3.connect(str(db_path))
            try:
                for tbl in (
                    "family_profiles",
                    "child_frameworks",
                    "passenger_loyalty_wallets",
                    "flight_search_queries",
                    "flight_itineraries",
                    "vacation_option_proposals",
                ):
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    self.assertEqual(cnt, 0, f"Guest search must write 0 rows to {tbl}")
            finally:
                conn.close()

    # 3. Google OAuth 2.0 + PKCE (S256), state, cookie binding, nonce, email_verified & Gmail domain validation
    def test_google_oauth2_pkce_login_redirect_state_csrf_and_callback_validation(
        self,
    ) -> None:
        client = VacationPlannerTestClient(":memory:")
        with _EnvContext(
            {
                "GOOGLE_OAUTH_CLIENT_ID": "prod-cid.apps.googleusercontent.com",
                "GOOGLE_OAUTH_CLIENT_SECRET": "prod-csecret",
                "PUBLIC_BASE_URL": "https://breezyflights.com",
                "VACATION_PLANNER_AUTH_TEST_MODE": None,
            }
        ):
            login_r = client.get("/api/v1/auth/google/login")
            self.assertEqual(login_r.status_code, 302)
            loc = login_r.headers["Location"]
            self.assertTrue(loc.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(loc).query))
            self.assertEqual(q["client_id"], "prod-cid.apps.googleusercontent.com")
            self.assertEqual(
                q["redirect_uri"],
                "https://breezyflights.com/api/v1/auth/google/callback",
            )
            self.assertEqual(q["response_type"], "code")
            self.assertEqual(q["scope"], "openid email profile")
            self.assertEqual(q["code_challenge_method"], "S256")
            self.assertGreaterEqual(len(q["code_challenge"]), 40)
            self.assertGreaterEqual(len(q["state"]), 32)
            self.assertIn("fvp_oauth_bind", client.cookies)

            # Missing or unknown state -> 400
            self.assertEqual(
                client.get("/api/v1/auth/google/callback?code=abc").status_code, 400
            )
            self.assertEqual(
                client.get(
                    "/api/v1/auth/google/callback?code=abc&state=wrong-state-val"
                ).status_code,
                400,
            )

            # Mismatched fvp_oauth_bind cookie (Login-CSRF attack) consumes state and returns 400
            bad_cookie_r = client.get(
                f"/api/v1/auth/google/callback?code=abc&state={urllib.parse.quote(q['state'])}",
                headers={"Cookie": "fvp_oauth_bind=attacker-forged-binding"},
            )
            self.assertEqual(bad_cookie_r.status_code, 400)

            # Replaying the same state now fails immediately (400) because state was consumed once
            replay_r = client.get(
                f"/api/v1/auth/google/callback?code=abc&state={urllib.parse.quote(q['state'])}"
            )
            self.assertEqual(replay_r.status_code, 400)

            # Expired state -> 400
            login_exp = client.get("/api/v1/auth/google/login")
            q_exp = dict(
                urllib.parse.parse_qsl(urllib.parse.urlsplit(login_exp.headers["Location"]).query)
            )
            with client.router.repository.connection() as conn:
                conn.execute(
                    "UPDATE oauth_login_states SET expires_at = '2020-01-01T00:00:00Z'"
                )
            self.assertEqual(
                client.get(
                    f"/api/v1/auth/google/callback?code=abc&state={urllib.parse.quote(q_exp['state'])}"
                ).status_code,
                400,
            )

            # Reject email_verified=False (403), non-Gmail domain (403), wrong aud/iss/nonce (401)
            for bad_case, expected_code in (
                ({"email_verified": False, "email": "unverified@gmail.com"}, 403),
                ({"email_verified": True, "email": "corp@evil-domain.org"}, 403),
                ({"email_verified": True, "email": "ok@gmail.com", "iss": "https://evil.example"}, 401),
                ({"email_verified": True, "email": "ok@gmail.com", "aud": "other-client"}, 401),
                ({"email_verified": True, "email": "ok@gmail.com", "nonce": "bad-nonce"}, 401),
            ):
                l_sub = client.get("/api/v1/auth/google/login")
                q_sub = dict(
                    urllib.parse.parse_qsl(urllib.parse.urlsplit(l_sub.headers["Location"]).query)
                )
                with client.router.repository.connection() as conn:
                    st_row = conn.execute(
                        "SELECT nonce FROM oauth_login_states WHERE state_sha256 = ?",
                        (sha256_hex(q_sub["state"]),),
                    ).fetchone()
                    real_nonce = str(st_row["nonce"])

                def _bad_exchanger(
                    _c: str, _v: str, _r: str, cid: str, _s: str, overrides: dict[str, Any] = bad_case, n_val: str = real_nonce
                ) -> dict[str, Any]:
                    now_ep = int(time.time())
                    claims = {
                        "iss": "https://accounts.google.com",
                        "aud": cid,
                        "sub": "sub-12345",
                        "email": "ok@gmail.com",
                        "email_verified": True,
                        "nonce": n_val,
                        "iat": now_ep,
                        "exp": now_ep + 3600,
                        **overrides,
                    }
                    return {"id_token": build_unsigned_or_hs256_jwt_for_test(claims)}

                client.router.auth_service.token_exchanger = _bad_exchanger
                err_cb = client.get(
                    f"/api/v1/auth/google/callback?code=code1&state={urllib.parse.quote(q_sub['state'])}"
                )
                self.assertEqual(err_cb.status_code, expected_code, f"Failed case {bad_case}")

        client.router.repository.close()

    # 4. Session cookie security flags, SHA-256 token hashing in SQLite, expiration & logout revocation
    def test_session_cookie_security_flags_hashing_expiration_and_sign_out(
        self,
    ) -> None:
        client = VacationPlannerTestClient(":memory:")
        sess = login_via_oauth_pkce(client, "secure.user@gmail.com", https_forwarded=True)
        csrf = sess["csrf_token"]

        # __Host-fvp_session issued when X-Forwarded-Proto: https
        self.assertIn("__Host-fvp_session", client.cookies)
        raw_token = client.cookies["__Host-fvp_session"]

        # Verify raw session token is NEVER stored in SQLite (only SHA-256 hex digest)
        with client.router.repository.connection() as conn:
            rows = conn.execute("SELECT token_sha256 FROM auth_sessions").fetchall()
            self.assertEqual(len(rows), 1)
            stored_hash = str(rows[0]["token_sha256"])
            self.assertNotEqual(stored_hash, raw_token)
            self.assertEqual(stored_hash, sha256_hex(raw_token))

        # Logout without CSRF -> 403; with CSRF -> 200, revokes DB row & clears cookie
        self.assertEqual(client.post("/api/v1/auth/logout").status_code, 403)
        out_resp = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf, "X-Forwarded-Proto": "https"},
        )
        self.assertEqual(out_resp.status_code, 200)
        self.assertTrue(any("Max-Age=0" in sc for sc in out_resp.set_cookies))

        # Replaying old raw_token after logout immediately returns 401
        replay = client.get(
            "/api/v1/profile",
            headers={"Cookie": f"__Host-fvp_session={raw_token}"},
        )
        self.assertEqual(replay.status_code, 401)

        # Expired session in SQLite returns 401
        sess2 = login_via_oauth_pkce(client, "expiring.user@gmail.com", https_forwarded=False)
        self.assertIn("fvp_session", client.cookies)
        with client.router.repository.connection() as conn:
            conn.execute(
                "UPDATE auth_sessions SET expires_at = '2020-01-01T00:00:00Z' WHERE csrf_token = ?",
                (sess2["csrf_token"],),
            )
        self.assertEqual(client.get("/api/v1/profile").status_code, 401)
        client.router.repository.close()

    # 5. User account record readiness for future notifications (privacy-by-default opt-in)
    def test_authenticated_user_record_readiness_for_future_notifications(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "notif_ready.db"
            client = VacationPlannerTestClient(db_path=db_path)
            sess = login_via_oauth_pkce(
                client,
                "Notif.Family@gmail.com",
                display_name="Dana Levi",
                google_sub="google-immutable-sub-998877",
            )
            user = sess["user"]
            csrf = sess["csrf_token"]

            self.assertEqual(user["google_sub"], "google-immutable-sub-998877")
            self.assertEqual(user["email"], "notif.family@gmail.com")
            self.assertTrue(user["email_verified"])
            self.assertEqual(user["display_name"], "Dana Levi")
            self.assertEqual(user["notification_email"], "notif.family@gmail.com")
            self.assertFalse(user["notifications_enabled"])  # Default OFF (opt-in)
            self.assertTrue(user["notification_channel_ready"])
            self.assertIsNone(user["notification_consent_updated_at"])

            # Reject third-party notification_email spoofing (403)
            spoof_r = client.put(
                "/api/v1/auth/notifications",
                json={
                    "notifications_enabled": True,
                    "notification_email": "victim@otherdomain.com",
                },
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(spoof_r.status_code, 403)

            # Opt in to future notifications and verify persistence across sign-out / sign-in
            opt_r = client.put(
                "/api/v1/auth/notifications",
                json={
                    "notifications_enabled": True,
                    "notification_preferences": {
                        "award_seat_alerts": True,
                        "holiday_reminders": False,
                        "preferred_locale": "he",
                    },
                },
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(opt_r.status_code, 200)
            updated_u = opt_r.json()["user"]
            self.assertTrue(updated_u["notifications_enabled"])
            self.assertIsNotNone(updated_u["notification_consent_updated_at"])
            self.assertTrue(updated_u["notification_preferences"]["award_seat_alerts"])

            client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
            sess_relogin = login_via_oauth_pkce(
                client,
                "notif.family@gmail.com",
                display_name="Dana Levi",
                google_sub="google-immutable-sub-998877",
            )
            self.assertEqual(sess_relogin["user"]["id"], user["id"])
            self.assertTrue(sess_relogin["user"]["notifications_enabled"])
            self.assertTrue(
                sess_relogin["user"]["notification_preferences"]["award_seat_alerts"]
            )

    # 6. Per-user profile persistence including children's ages (0..18), frameworks & Matmid points
    def test_per_user_profile_persistence_children_ages_frameworks_and_matmid_points(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "user_persist.db"
            client = VacationPlannerTestClient(db_path=db_path)
            sess = login_via_oauth_pkce(client, "parents.family@gmail.com")
            csrf = sess["csrf_token"]

            # Initial profile for a new user is clean and unsaved (2 adults, 0 children, 0 points)
            init_prof = client.get("/api/v1/profile").json()
            self.assertFalse(init_prof["is_persisted"])
            self.assertEqual(init_prof["adults_count"], 2)
            self.assertEqual(init_prof["children"], [])
            self.assertEqual(init_prof["matmid_points_balance"], 0)
            self.assertEqual(init_prof["profile_name"], "")

            # Save 3 children (ages 1, 6, 14) + frameworks + 240,000 Matmid points
            put_r = client.put(
                "/api/v1/profile",
                json={
                    "adults_count": 2,
                    "matmid_points_balance": 240000,
                    "children": [
                        {"child_age_years": 1, "framework_type": "DAYCARE_SUPERVISED"},
                        {"child_age_years": 6, "framework_type": "ELEMENTARY_1_3"},
                        {"child_age_years": 14, "framework_type": "MIDDLE_SCHOOL_7_9"},
                    ],
                },
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(put_r.status_code, 200)

            # Sign out and sign back in with same Google sub/email
            client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
            self.assertEqual(client.get("/api/v1/profile").status_code, 401)

            login_via_oauth_pkce(client, "parents.family@gmail.com")
            reloaded = client.get("/api/v1/profile").json()
            self.assertTrue(reloaded["is_persisted"])
            self.assertEqual(reloaded["matmid_points_balance"], 240000)
            self.assertNotIn("annual_pto_budget", reloaded)
            self.assertNotIn("workweek_type", reloaded)
            ages_and_types = [
                (c["child_age_years"], c["passenger_Current_type"], c["framework_type"])
                for c in reloaded["children"]
            ]
            self.assertEqual(
                ages_and_types,
                [
                    (1, "INFANT_LAP", "DAYCARE_SUPERVISED"),
                    (6, "CHILD", "ELEMENTARY_1_3"),
                    (14, "YOUTH", "MIDDLE_SCHOOL_7_9"),
                ],
            )

    # 7. Strict two-user isolation, PK collision immunity, and IDOR / spoofed identifier rejection
    def test_strict_two_user_isolation_and_spoofed_identifier_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "two_users_iso.db"
            client_a = VacationPlannerTestClient(db_path=db_path)
            client_b = VacationPlannerTestClient(db_path=db_path)

            sess_a = login_via_oauth_pkce(client_a, "user_a@gmail.com")
            sess_b = login_via_oauth_pkce(client_b, "user_b@gmail.com")

            # Both submit identical client child IDs ("child-1") to test server PK namespacing
            res_a = client_a.put(
                "/api/v1/profile",
                json={
                    "adults_count": 2,
                    "matmid_points_balance": 120000,
                    "children": [
                        {"id": "child-1", "child_age_years": 4, "framework_type": "MUNICIPAL_GAN"},
                        {"id": "child-2", "child_age_years": 8, "framework_type": "ELEMENTARY_1_3"},
                    ],
                },
                headers={"X-CSRF-Token": sess_a["csrf_token"]},
            )
            self.assertEqual(res_a.status_code, 200)
            prof_a_id = res_a.json()["id"]

            res_b = client_b.put(
                "/api/v1/profile",
                json={
                    "adults_count": 1,
                    "matmid_points_balance": 310000,
                    "children": [
                        {"id": "child-1", "child_age_years": 2, "framework_type": "DAYCARE_SUPERVISED"},
                        {"id": "child-2", "child_age_years": 11, "framework_type": "ELEMENTARY_4_6"},
                        {"id": "child-3", "child_age_years": 15, "framework_type": "HIGH_SCHOOL_10_12"},
                    ],
                },
                headers={"X-CSRF-Token": sess_b["csrf_token"]},
            )
            self.assertEqual(res_b.status_code, 200)
            prof_b_id = res_b.json()["id"]
            user_b_id = sess_b["user"]["id"]

            # User A attempts IDOR via query params & body identifiers targeting User B
            spoof_get = client_a.get(
                f"/api/v1/profile?profile_id={prof_b_id}&user_id={user_b_id}&email=user_b@gmail.com"
            ).json()
            self.assertEqual(spoof_get["id"], prof_a_id)
            self.assertEqual(spoof_get["matmid_points_balance"], 120000)
            self.assertEqual([c["child_age_years"] for c in spoof_get["children"]], [4, 8])

            spoof_put = client_a.put(
                "/api/v1/profile",
                json={
                    "id": prof_b_id,
                    "profile_id": prof_b_id,
                    "user_id": user_b_id,
                    "email": "user_b@gmail.com",
                    "adults_count": 2,
                    "matmid_points_balance": 135000,
                    "children": [
                        {"child_age_years": 4, "framework_type": "MUNICIPAL_GAN"},
                        {"child_age_years": 8, "framework_type": "ELEMENTARY_1_3"},
                    ],
                },
                headers={"X-CSRF-Token": sess_a["csrf_token"]},
            )
            self.assertEqual(spoof_put.status_code, 200)

            # Verify User B's record is 100% untouched!
            verify_b = client_b.get("/api/v1/profile").json()
            self.assertEqual(verify_b["id"], prof_b_id)
            self.assertEqual(verify_b["adults_count"], 1)
            self.assertEqual(verify_b["matmid_points_balance"], 310000)
            self.assertEqual(
                [c["child_age_years"] for c in verify_b["children"]], [2, 11, 15]
            )

            # User A searching with spoofed family_profile_id=prof_b_id still searches User A's 4-pax household
            s_a = client_a.post(
                "/api/v1/vacations/search",
                json={
                    "profile_id": prof_b_id,
                    "family_profile_id": prof_b_id,
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO"],
                },
            )
            self.assertEqual(s_a.status_code, 200)
            prop_a = s_a.json()["proposals"][0]
            self.assertEqual(prop_a["itinerary"]["seated_passengers_count"], 4)

            # User A resolves their own persisted proposal, User B is blocked (IDOR guard), and removed /compare & .ics return 404
            sess_a = client_a.get("/api/v1/auth/session").json()
            sess_b = client_b.get("/api/v1/auth/session").json()
            self.assertIsNotNone(
                client_a.router.planner_service.resolve_proposal_for_requester(
                    prop_a["id"],
                    requester_user_id=sess_a["user"]["id"],
                    enforce_owner=True,
                )
            )
            self.assertIsNone(
                client_b.router.planner_service.resolve_proposal_for_requester(
                    prop_a["id"],
                    requester_user_id=sess_b["user"]["id"],
                    enforce_owner=True,
                )
            )
            self.assertEqual(
                client_a.post(
                    "/api/v1/vacations/compare", json={"proposal_ids": [prop_a["id"]]}
                ).status_code,
                404,
            )
            self.assertEqual(
                client_b.get(f"/api/v1/vacations/{prop_a['id']}/export.ics").status_code,
                404,
            )
            self.assertEqual(
                client_b.post(
                    "/api/v1/vacations/compare", json={"proposal_ids": [prop_a["id"]]}
                ).status_code,
                404,
            )

    # 8. Legacy shared default-family-profile quarantine on existing pre-M5 SQLite DB preserving #live flights
    def test_legacy_shared_default_profile_quarantine_and_non_exposure_on_existing_db(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_db = Path(tmpdir) / "legacy_pre_m5.db"
            # Build an authentic pre-M5 8-table database (no users table, no user_id column, NOT NULL family_profile_id)
            conn = sqlite3.connect(str(legacy_db))
            try:
                conn.executescript(
                    """
                    CREATE TABLE family_profiles (
                        id TEXT PRIMARY KEY,
                        profile_name TEXT NOT NULL DEFAULT 'המשפחה שלי',
                        adults_count INTEGER NOT NULL DEFAULT 2,
                        workweek_type TEXT NOT NULL DEFAULT 'SUN_THU',
                        erev_chag_pto_weight REAL NOT NULL DEFAULT 0.5,
                        chol_hamoed_pto_weight REAL NOT NULL DEFAULT 0.5,
                        annual_pto_budget REAL NOT NULL DEFAULT 14.0,
                        max_pto_per_trip REAL NOT NULL DEFAULT 5.0,
                        matmid_points_balance INTEGER NOT NULL DEFAULT 0,
                        has_flycard INTEGER NOT NULL DEFAULT 1,
                        flycard_tier TEXT NOT NULL DEFAULT 'FLY_CARD_PREMIUM',
                        flycard_companion_vouchers INTEGER NOT NULL DEFAULT 0,
                        point_valuation_usd REAL NOT NULL DEFAULT 0.016,
                        preferred_currency TEXT NOT NULL DEFAULT 'USD',
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE child_frameworks (
                        id TEXT PRIMARY KEY,
                        family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
                        child_name TEXT NOT NULL DEFAULT 'ילד/ה',
                        child_age_years INTEGER NOT NULL,
                        birth_date TEXT,
                        passenger_Current_type TEXT NOT NULL DEFAULT 'CHILD',
                        framework_type TEXT,
                        education_stream TEXT NOT NULL DEFAULT 'MAMLACHTI',
                        school_week_days INTEGER NOT NULL DEFAULT 5,
                        holiday_extension_mode TEXT NOT NULL DEFAULT 'NONE',
                        treat_camp_as_vacation INTEGER NOT NULL DEFAULT 1,
                        max_school_days_missed INTEGER NOT NULL DEFAULT 2,
                        absence_penalty_weight REAL NOT NULL DEFAULT 1.0,
                        bagrut_blackout_dates_json TEXT NOT NULL DEFAULT '[]'
                    );
                    CREATE TABLE passenger_loyalty_wallets (
                        id TEXT PRIMARY KEY,
                        family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
                        passenger_id TEXT NOT NULL,
                        passenger_name TEXT NOT NULL,
                        program_code TEXT NOT NULL,
                        available_points INTEGER NOT NULL DEFAULT 0,
                        can_pool_with_family INTEGER NOT NULL DEFAULT 0,
                        pool_group_id TEXT,
                        transfer_ratio_to_airline REAL NOT NULL DEFAULT 1.0,
                        has_club_credit_card INTEGER NOT NULL DEFAULT 0,
                        companion_vouchers_count INTEGER NOT NULL DEFAULT 0,
                        point_valuation_cents REAL NOT NULL DEFAULT 1.5,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE flight_search_queries (
                        id TEXT PRIMARY KEY,
                        family_profile_id TEXT NOT NULL REFERENCES family_profiles(id) ON DELETE CASCADE,
                        date_selection_mode TEXT NOT NULL,
                        airline_selection_mode TEXT NOT NULL,
                        search_elal_bonus_tickets INTEGER NOT NULL DEFAULT 1,
                        include_sundor_flights INTEGER NOT NULL DEFAULT 1,
                        origin_iata TEXT NOT NULL DEFAULT 'TLV',
                        destination_iatas_json TEXT NOT NULL,
                        specific_departure_date TEXT,
                        specific_return_date TEXT,
                        flex_days_plus_minus INTEGER NOT NULL DEFAULT 0,
                        school_year TEXT,
                        target_holiday_codes_json TEXT,
                        direct_holiday_code TEXT,
                        direct_target_year INTEGER,
                        min_trip_nights INTEGER NOT NULL DEFAULT 4,
                        max_trip_nights INTEGER NOT NULL DEFAULT 10,
                        max_bridge_days_shift INTEGER NOT NULL DEFAULT 3,
                        overlap_policy TEXT NOT NULL DEFAULT 'MAXIMIZE_EFFICIENCY_SCORE',
                        preferred_cabins_json TEXT NOT NULL DEFAULT '["ECONOMY"]',
                        enabled_loyalty_programs_json TEXT NOT NULL DEFAULT '["ELAL_MATMID"]',
                        allow_hybrid_bonus_cash INTEGER NOT NULL DEFAULT 1,
                        direct_flights_only INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE elal_bonus_availability (
                        id TEXT PRIMARY KEY,
                        origin_iata TEXT NOT NULL,
                        destination_iata TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        flight_number TEXT NOT NULL,
                        operating_carrier TEXT NOT NULL DEFAULT 'LY',
                        flight_date TEXT NOT NULL,
                        departure_time_local TEXT NOT NULL,
                        arrival_time_local TEXT NOT NULL,
                        aircraft_type TEXT,
                        economy_award_seats INTEGER NOT NULL DEFAULT 0,
                        economy_seats_is_two_plus INTEGER NOT NULL DEFAULT 0,
                        economy_rbd_code TEXT NOT NULL DEFAULT 'E',
                        premium_award_seats INTEGER NOT NULL DEFAULT 0,
                        premium_seats_is_two_plus INTEGER NOT NULL DEFAULT 0,
                        premium_rbd_code TEXT NOT NULL DEFAULT 'P',
                        business_award_seats INTEGER NOT NULL DEFAULT 0,
                        business_seats_is_two_plus INTEGER NOT NULL DEFAULT 0,
                        business_rbd_code TEXT NOT NULL DEFAULT 'I',
                        award_zone TEXT NOT NULL DEFAULT 'ZONE_A',
                        economy_points_per_pax INTEGER,
                        premium_points_per_pax INTEGER,
                        business_points_per_pax INTEGER,
                        flycard_promo_active INTEGER NOT NULL DEFAULT 0,
                        taxes_usd_per_pax REAL NOT NULL DEFAULT 0.0,
                        source_url TEXT NOT NULL,
                        fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                        expires_at TEXT NOT NULL
                    );
                    INSERT INTO family_profiles (id, profile_name, matmid_points_balance)
                    VALUES ('default-family-profile', 'משפחת בודובסקי', 185000);
                    INSERT INTO child_frameworks (id, family_profile_id, child_name, child_age_years)
                    VALUES ('child-noa-1', 'default-family-profile', 'נועה', 5);
                    INSERT INTO passenger_loyalty_wallets (id, family_profile_id, passenger_id, passenger_name, program_code, available_points)
                    VALUES ('wallet-1', 'default-family-profile', 'ADULT_1', 'יוני (הורה 1)', 'ELAL_MATMID', 115000);
                    INSERT INTO flight_search_queries (id, family_profile_id, date_selection_mode, airline_selection_mode, destination_iatas_json)
                    VALUES ('legacy-q1', 'default-family-profile', 'SPECIFIC_DATES', 'EL_AL_ONLY', '["LCA"]');
                    INSERT INTO elal_bonus_availability (
                        id, origin_iata, destination_iata, direction, flight_number, flight_date,
                        departure_time_local, arrival_time_local, economy_award_seats, economy_seats_is_two_plus,
                        economy_points_per_pax, taxes_usd_per_pax, source_url, expires_at
                    ) VALUES
                        ('LY5131_2027-04-14', 'TLV', 'LCA', 'OUTBOUND', 'LY5131', '2027-04-14', '08:00', '09:10', 2, 1, 7500, 35.0, 'https://www.elal.com/rbddataclients/#live', '2029-01-01T00:00:00Z'),
                        ('LY5132_2027-04-20', 'LCA', 'TLV', 'INBOUND', 'LY5132', '2027-04-20', '20:00', '21:10', 2, 1, 7500, 42.0, 'https://www.elal.com/rbddataclients/#live', '2029-01-01T00:00:00Z');
                    """
                )
            finally:
                conn.close()

            with _EnvContext({"ELAL_LIVE_FETCH_ENABLED": "1"}):
                guest_client = VacationPlannerTestClient(db_path=legacy_db)
                repo = guest_client.router.repository

                # All 11 tables exist; #live flights are 100% preserved; legacy profile is quarantined
                self.assertEqual(repo.get_health_status()["tables_count"], 11)
                live_flights = repo.get_cached_elal_bonus(destinations=["LCA"])
                self.assertEqual(len(live_flights), 2)
                self.assertIsNone(repo.get_profile("default-family-profile"))
                self.assertIsNone(repo.get_profile(None))

                # Guest search on LCA returns live flight proposals with zero Yoni/Budovsky leakage
                gs_resp = guest_client.post(
                    "/api/v1/vacations/search",
                    json={
                        "profile_id": "default-family-profile",
                        "family_profile_id": "default-family-profile",
                        "date_selection_mode": "SPECIFIC_DATES",
                        "specific_departure_date": "2027-04-14",
                        "specific_return_date": "2027-04-20",
                        "destination_iatas": ["LCA"],
                    },
                )
                self.assertEqual(gs_resp.status_code, 200)
                self.assertGreater(gs_resp.json()["count"], 0)
                self.assertNotIn("בודובסקי", gs_resp.text)
                self.assertIsNone(re.search(r"(?<![א-ת])יוני(?![א-ת])", gs_resp.text))
                self.assertNotIn("נועה", gs_resp.text)

                # Newly signed-in Gmail user sees a clean starter profile, never default-family-profile
                new_user = VacationPlannerTestClient(db_path=legacy_db)
                login_via_oauth_pkce(new_user, "newcomer@gmail.com")
                prof_json = new_user.get("/api/v1/profile").json()
                self.assertFalse(prof_json["is_persisted"])
                self.assertEqual(prof_json["children"], [])
                self.assertEqual(prof_json["matmid_points_balance"], 0)

    # 9. Production live-fetch DB never seeds Yoni / Budovsky rows
    def test_live_fetch_production_db_never_seeds_yoni_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prod_db = Path(tmpdir) / "prod_fresh.db"
            with _EnvContext({"ELAL_LIVE_FETCH_ENABLED": "1"}):
                repo = SQLiteRepository(db_path=prod_db, auto_seed=True)
                with repo.connection() as conn:
                    for tbl in (
                        "family_profiles",
                        "child_frameworks",
                        "passenger_loyalty_wallets",
                    ):
                        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                        self.assertEqual(cnt, 0)

        # Also verify sanitized offline test fixture has zero "יוני"
        fixture_str = json.dumps(
            build_default_family_profile().to_dict(), ensure_ascii=False
        )
        self.assertNotIn("יוני", fixture_str)

    # 10. Privacy protections: child data minimization, headers/CORS, CSRF, triple-gate, and account deletion cascade
    def test_privacy_protections_data_minimization_cache_headers_and_account_deletion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "privacy_del.db"
            srv = create_http_server("127.0.0.1", 0, db_path=db_path)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                # Verify live HTTP headers: Cache-Control: no-store, private & NO wildcard CORS on /auth & /profile
                for priv_path in ("/api/v1/auth/session", "/api/v1/profile"):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
                    try:
                        conn.request("GET", priv_path)
                        resp = conn.getresponse()
                        resp.read()
                        hdr_map = {k.lower(): v for k, v in resp.getheaders()}
                        self.assertEqual(
                            hdr_map.get("cache-control"), "no-store, private"
                        )
                        self.assertNotIn("access-control-allow-origin", hdr_map)
                    finally:
                        conn.close()
            finally:
                srv.shutdown()
                srv.server_close()

            # Verify triple-gate on local test mode: returns 404 when disabled, live-fetch=1, or non-loopback host
            gate_client = VacationPlannerTestClient(db_path=db_path)
            self.assertEqual(
                gate_client.post(
                    "/api/v1/auth/test-login", json={"email": "a@gmail.com"}
                ).status_code,
                404,
            )
            with _EnvContext(
                {
                    "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                    "ELAL_LIVE_FETCH_ENABLED": "1",
                }
            ):
                self.assertEqual(
                    gate_client.post(
                        "/api/v1/auth/test-login", json={"email": "a@gmail.com"}
                    ).status_code,
                    404,
                )
            with _EnvContext(
                {
                    "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                    "ELAL_LIVE_FETCH_ENABLED": "0",
                }
            ):
                self.assertEqual(
                    gate_client.post(
                        "/api/v1/auth/test-login",
                        json={"email": "a@gmail.com"},
                        headers={"Host": "breezyflights.com"},
                    ).status_code,
                    404,
                )

            # Data minimization + CSRF + self-service account deletion preserving User B
            client_a = VacationPlannerTestClient(db_path=db_path)
            client_b = VacationPlannerTestClient(db_path=db_path)
            sess_a = login_via_oauth_pkce(client_a, "erase_me@gmail.com")
            sess_b = login_via_oauth_pkce(client_b, "keep_me@gmail.com")

            # Missing CSRF token -> 403; cross-site Origin without Host header -> 403
            self.assertEqual(
                client_a.put("/api/v1/profile", json={"adults_count": 2}).status_code,
                403,
            )
            self.assertEqual(
                client_a.put(
                    "/api/v1/profile",
                    json={"adults_count": 2},
                    headers={
                        "X-CSRF-Token": sess_a["csrf_token"],
                        "Origin": "https://evil.attacker.example",
                    },
                ).status_code,
                403,
            )

            # Save minimal child ages without names or birthdates
            saved_a = client_a.put(
                "/api/v1/profile",
                json={
                    "adults_count": 2,
                    "matmid_points_balance": 90000,
                    "children": [{"child_age_years": 5}],
                },
                headers={"X-CSRF-Token": sess_a["csrf_token"]},
            ).json()
            self.assertEqual(saved_a["children"][0]["child_name"], "ילד/ה")
            self.assertIsNone(saved_a["children"][0]["birth_date"])

            client_b.put(
                "/api/v1/profile",
                json={
                    "adults_count": 2,
                    "matmid_points_balance": 175000,
                    "children": [{"child_age_years": 10}],
                },
                headers={"X-CSRF-Token": sess_b["csrf_token"]},
            )
            client_a.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO"],
                },
            )

            # Self-service DELETE /api/v1/auth/account wipes User A completely while keeping User B intact
            del_resp = client_a.delete(
                "/api/v1/auth/account",
                headers={"X-CSRF-Token": sess_a["csrf_token"]},
            )
            self.assertEqual(del_resp.status_code, 200)
            self.assertEqual(client_a.get("/api/v1/profile").status_code, 401)

            b_after = client_b.get("/api/v1/profile").json()
            self.assertEqual(b_after["matmid_points_balance"], 175000)
            self.assertEqual(b_after["children"][0]["child_age_years"], 10)

    # 11. CLI `plan-vacation profile --session-token` & `VACATION_PLANNER_SESSION_TOKEN` under HTTP & HTTPS `PUBLIC_BASE_URL`
    def test_cli_profile_session_token_and_env_var_under_http_and_https_public_base_url(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cli_auth.db"
            client = VacationPlannerTestClient(db_path=db_path)
            sess = login_via_oauth_pkce(
                client, "cli.operator@gmail.com", https_forwarded=True
            )
            raw_tok = client.cookies["__Host-fvp_session"]
            self.assertTrue(
                raw_tok.startswith("fvp_"),
                f"Expected login session token to start with 'fvp_', got {raw_tok!r}",
            )
            save_r = client.put(
                "/api/v1/profile",
                json={
                    "profile_name": "משפחת CLI",
                    "adults_count": 2,
                    "matmid_points_balance": 195000,
                    "children": [
                        {"child_age_years": 3, "framework_type": "MUNICIPAL_GAN"},
                        {"child_age_years": 9, "framework_type": "ELEMENTARY_4_6"},
                    ],
                },
                headers={
                    "X-CSRF-Token": sess["csrf_token"],
                    "X-Forwarded-Proto": "https",
                },
            )
            self.assertEqual(save_r.status_code, 200)

            # (a) Local HTTP (PUBLIC_BASE_URL unset) with --session-token
            with _EnvContext(
                {"PUBLIC_BASE_URL": None, "VACATION_PLANNER_SESSION_TOKEN": None}
            ):
                out_http, err_http = io.StringIO(), io.StringIO()
                with redirect_stdout(out_http), redirect_stderr(err_http):
                    rc_http = cli_main(
                        [
                            "--db-path",
                            str(db_path),
                            "profile",
                            "--session-token",
                            raw_tok,
                            "--json",
                        ]
                    )
                self.assertEqual(rc_http, 0, err_http.getvalue())
                parsed_http = json.loads(out_http.getvalue())
                self.assertTrue(parsed_http["authenticated"])
                self.assertTrue(parsed_http["is_persisted"])
                self.assertEqual(parsed_http["matmid_points_balance"], 195000)
                self.assertEqual(
                    [c["child_age_years"] for c in parsed_http["children"]], [3, 9]
                )

            # (b) Production HTTPS PUBLIC_BASE_URL with --session-token AND with VACATION_PLANNER_SESSION_TOKEN
            with _EnvContext(
                {
                    "PUBLIC_BASE_URL": "https://breezyflights.com",
                    "VACATION_PLANNER_SESSION_TOKEN": None,
                }
            ):
                out_https, err_https = io.StringIO(), io.StringIO()
                with redirect_stdout(out_https), redirect_stderr(err_https):
                    rc_https = cli_main(
                        [
                            "--db-path",
                            str(db_path),
                            "profile",
                            "--session-token",
                            raw_tok,
                            "--json",
                        ]
                    )
                self.assertEqual(rc_https, 0, err_https.getvalue())
                parsed_https = json.loads(out_https.getvalue())
                self.assertTrue(parsed_https["authenticated"])
                self.assertEqual(parsed_https["matmid_points_balance"], 195000)

            with _EnvContext(
                {
                    "PUBLIC_BASE_URL": "https://breezyflights.com",
                    "VACATION_PLANNER_SESSION_TOKEN": raw_tok,
                }
            ):
                out_env, err_env = io.StringIO(), io.StringIO()
                with redirect_stdout(out_env), redirect_stderr(err_env):
                    rc_env = cli_main(["--db-path", str(db_path), "profile"])
                self.assertEqual(rc_env, 0, err_env.getvalue())
                self.assertIn("authenticated=True", out_env.getvalue())
                self.assertIn("matmid_points=195000", out_env.getvalue())

            # (c) Leading-hyphen token (`1/64` base64url alphabet edge case) under HTTP & HTTPS + missing arg (`rc == 2`)
            tok = "-9xYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789_A"
            client.router.repository.create_auth_session(
                user_id=sess["user"]["id"],
                token_sha256=sha256_hex(tok),
                csrf_token="csrf-hyphen-token-test",
                expires_at="2099-01-01T00:00:00Z",
            )
            for pub_url in (None, "https://breezyflights.com"):
                with _EnvContext(
                    {
                        "PUBLIC_BASE_URL": pub_url,
                        "VACATION_PLANNER_SESSION_TOKEN": None,
                    }
                ):
                    out_hyp, err_hyp = io.StringIO(), io.StringIO()
                    with redirect_stdout(out_hyp), redirect_stderr(err_hyp):
                        rc_hyp = cli_main(
                            [
                                "--db-path",
                                str(db_path),
                                "profile",
                                "--session-token",
                                tok,
                                "--json",
                            ]
                        )
                    self.assertEqual(
                        rc_hyp,
                        0,
                        f"Expected rc=0 for leading-hyphen token under PUBLIC_BASE_URL={pub_url!r}: {err_hyp.getvalue()}",
                    )
                    parsed_hyp = json.loads(out_hyp.getvalue())
                    self.assertTrue(parsed_hyp["authenticated"])
                    self.assertEqual(parsed_hyp["matmid_points_balance"], 195000)
                    self.assertEqual(
                        [c["child_age_years"] for c in parsed_hyp["children"]], [3, 9]
                    )

            out_missing, err_missing = io.StringIO(), io.StringIO()
            with redirect_stdout(out_missing), redirect_stderr(err_missing):
                rc_missing = cli_main(
                    ["--db-path", str(db_path), "profile", "--session-token", "--json"]
                )
            self.assertEqual(rc_missing, 2)

            # (d) Reject cookie-header / CRLF injection characters and unknown tokens (rc == 1)
            for bad_tok in (
                f"{raw_tok}; evil=1",
                f"{raw_tok}\r\nX-Injected: 1",
                f"{raw_tok}\nevil",
                "unknown-forged-token-value",
            ):
                out_bad, err_bad = io.StringIO(), io.StringIO()
                with redirect_stdout(out_bad), redirect_stderr(err_bad):
                    rc_bad = cli_main(
                        [
                            "--db-path",
                            str(db_path),
                            "profile",
                            "--session-token",
                            bad_tok,
                            "--json",
                        ]
                    )
                self.assertEqual(rc_bad, 1, f"Expected rc=1 for {bad_tok!r}")

    # 12. Authenticated `DELETE /api/v1/profile`: CSRF defense, self-only cascade, active session survival & User B isolation
    def test_authenticated_delete_profile_csrf_self_erase_session_survival_and_user_b_isolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "del_prof.db"
            client_a = VacationPlannerTestClient(db_path=db_path)
            client_b = VacationPlannerTestClient(db_path=db_path)
            sess_a = login_via_oauth_pkce(client_a, "delete.prof.a@gmail.com")
            sess_b = login_via_oauth_pkce(client_b, "survive.prof.b@gmail.com")
            csrf_a = sess_a["csrf_token"]
            csrf_b = sess_b["csrf_token"]

            # User A runs an ephemeral search BEFORE saving a profile (stored in _ephemeral_proposals)
            eph_search = client_a.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO"],
                },
            )
            self.assertEqual(eph_search.status_code, 200)
            eph_pid = eph_search.json()["proposals"][0]["id"]

            # Both User A and User B save profiles and run persisted searches
            self.assertEqual(
                client_a.put(
                    "/api/v1/profile",
                    json={
                        "adults_count": 2,
                        "matmid_points_balance": 145000,
                        "children": [
                            {"child_age_years": 4, "framework_type": "MUNICIPAL_GAN"},
                            {"child_age_years": 11, "framework_type": "ELEMENTARY_4_6"},
                        ],
                    },
                    headers={"X-CSRF-Token": csrf_a},
                ).status_code,
                200,
            )
            persisted_a = client_a.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO"],
                },
            )
            self.assertEqual(persisted_a.status_code, 200)
            persisted_a_pid = persisted_a.json()["proposals"][0]["id"]

            self.assertEqual(
                client_b.put(
                    "/api/v1/profile",
                    json={
                        "adults_count": 2,
                        "matmid_points_balance": 280000,
                        "children": [{"child_age_years": 7, "framework_type": "ELEMENTARY_1_3"}],
                    },
                    headers={"X-CSRF-Token": csrf_b},
                ).status_code,
                200,
            )
            persisted_b = client_b.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["ATH"],
                },
            )
            self.assertEqual(persisted_b.status_code, 200)
            persisted_b_pid = persisted_b.json()["proposals"][0]["id"]

            # Missing CSRF, wrong CSRF, non-ASCII CSRF, and forged Origin on DELETE /api/v1/profile -> 403
            self.assertEqual(client_a.delete("/api/v1/profile").status_code, 403)
            self.assertEqual(
                client_a.delete(
                    "/api/v1/profile", headers={"X-CSRF-Token": "wrong-csrf"}
                ).status_code,
                403,
            )
            self.assertEqual(
                client_a.delete(
                    "/api/v1/profile", headers={"X-CSRF-Token": "טוקן-עברי"}
                ).status_code,
                403,
            )
            self.assertEqual(
                client_a.delete(
                    "/api/v1/profile",
                    headers={
                        "X-CSRF-Token": csrf_a,
                        "Origin": "https://attacker.example",
                    },
                ).status_code,
                403,
            )
            self.assertTrue(client_a.get("/api/v1/profile").json()["is_persisted"])

            # Valid DELETE /api/v1/profile -> 200, erases User A's profile & proposals while keeping session active
            del_ok = client_a.delete(
                "/api/v1/profile", headers={"X-CSRF-Token": csrf_a}
            )
            self.assertEqual(del_ok.status_code, 200)
            self.assertTrue(del_ok.json()["deleted"])

            # User A remains authenticated on a clean unsaved starter profile
            sess_after = client_a.get("/api/v1/auth/session").json()
            self.assertTrue(sess_after["authenticated"])
            prof_after = client_a.get("/api/v1/profile").json()
            self.assertFalse(prof_after["is_persisted"])
            self.assertEqual(prof_after["children"], [])
            self.assertEqual(prof_after["matmid_points_balance"], 0)

            # Both User A's persisted AND ephemeral proposals were purged (None on resolve_proposal_for_requester, 404 on removed /compare)
            uid_a = sess_after["user"]["id"]
            uid_b = client_b.get("/api/v1/auth/session").json()["user"]["id"]
            self.assertIsNone(
                client_a.router.planner_service.resolve_proposal_for_requester(
                    persisted_a_pid, requester_user_id=uid_a, enforce_owner=True
                )
            )
            self.assertIsNone(
                client_a.router.planner_service.resolve_proposal_for_requester(
                    eph_pid, requester_user_id=uid_a, enforce_owner=True
                )
            )
            self.assertEqual(
                client_a.post(
                    "/api/v1/vacations/compare", json={"proposal_ids": [persisted_a_pid]}
                ).status_code,
                404,
            )

            # User B's profile, children, and persisted proposals are 100% untouched
            b_prof = client_b.get("/api/v1/profile").json()
            self.assertTrue(b_prof["is_persisted"])
            self.assertEqual(b_prof["matmid_points_balance"], 280000)
            self.assertEqual(
                [c["child_age_years"] for c in b_prof["children"]], [7]
            )
            self.assertIsNotNone(
                client_b.router.planner_service.resolve_proposal_for_requester(
                    persisted_b_pid, requester_user_id=uid_b, enforce_owner=True
                )
            )
            self.assertEqual(
                client_b.post(
                    "/api/v1/vacations/compare", json={"proposal_ids": [persisted_b_pid]}
                ).status_code,
                404,
            )

    # 13. Open-redirect, ASCII tab/control/whitespace, backslash & CRLF sanitization in `sanitize_return_to` and OAuth callback
    def test_sanitize_return_to_blocks_tab_whitespace_control_backslash_and_open_redirects(
        self,
    ) -> None:
        malicious_targets = (
            "/%09/evil.com",
            "/%09\\evil.com",
            "/%2fevil.com",
            "/%5cevil.com",
            "/\t/evil.com",
            "/\t\\evil.com",
            "//evil.com",
            "/\\evil.com",
            "/foo\\evil.com",
            "https://evil.com",
            "http://evil.com/path",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "/\r\nSet-Cookie: hacked=1",
            "/valid\r\n",
            "/\x00/evil.com",
            "/\x7f/evil.com",
            "/שלום",
            "/?q=שלום",
            "/%D7%A9%D7%9C%D7%95%D7%9D",
            "/\u2028/evil.com",
            "/ evil.com",
            "\\\\evil.com",
            "",
        )
        for bad in malicious_targets:
            self.assertEqual(
                sanitize_return_to(bad),
                "/",
                f"Expected '/' for malicious return_to={bad!r}",
            )

        self.assertEqual(sanitize_return_to("/"), "/")
        self.assertEqual(sanitize_return_to("/?lang=he#zone-profile"), "/?lang=he#zone-profile")

        # Verify end-to-end over `/api/v1/auth/google/login?return_to=/%09/evil.com` -> `/callback`
        client = VacationPlannerTestClient(":memory:")
        with _EnvContext(
            {
                "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                "ELAL_LIVE_FETCH_ENABLED": "0",
                "PUBLIC_BASE_URL": None,
            }
        ):
            for encoded_attack in (
                "/%09/evil.com",
                "/%09%5Cevil.com",
                "//evil.com",
                "/%5Cevil.com",
                "https%3A%2F%2Fevil.com",
                "javascript%3Aalert(1)",
            ):
                r_login = client.get(
                    f"/api/v1/auth/google/login?mock_oauth=1&test_email=redir@gmail.com&return_to={encoded_attack}"
                )
                self.assertEqual(r_login.status_code, 302)
                authz_loc = r_login.headers["Location"]
                r_authz = client.get(authz_loc)
                self.assertEqual(r_authz.status_code, 302)
                cb_loc = r_authz.headers["Location"]
                r_cb = client.get(cb_loc)
                self.assertEqual(r_cb.status_code, 302)
                self.assertEqual(
                    r_cb.headers["Location"],
                    "/",
                    f"Callback Location leaked open redirect for {encoded_attack}",
                )

            # Live ThreadingHTTPServer round-trip with non-ASCII `return_to=%2F%D7%A9%D7%9C%D7%95%D7%9D` -> 302 Location: /
            with tempfile.TemporaryDirectory() as tmpdir_rt:
                rt_db = Path(tmpdir_rt) / "non_ascii_rt.db"
                srv_rt = create_http_server("127.0.0.1", 0, db_path=rt_db)
                port_rt = srv_rt.server_address[1]
                threading.Thread(target=srv_rt.serve_forever, daemon=True).start()
                try:
                    hc = http.client.HTTPConnection("127.0.0.1", port_rt, timeout=5.0)
                    try:
                        hc.request(
                            "GET",
                            "/api/v1/auth/google/login?mock_oauth=1&test_email=hebrew.rt@gmail.com&return_to=%2F%D7%A9%D7%9C%D7%95%D7%9D",
                        )
                        r1 = hc.getresponse()
                        r1.read()
                        self.assertEqual(r1.status, 302)
                        bind_ck = ""
                        for hk, hv in r1.getheaders():
                            if hk.lower() == "set-cookie" and "fvp_oauth_bind=" in hv:
                                bind_ck = hv.split(";", 1)[0].strip()
                        az_loc = r1.getheader("Location")
                        self.assertIsNotNone(az_loc)

                        hc.request("GET", str(az_loc), headers={"Cookie": bind_ck})
                        r2 = hc.getresponse()
                        r2.read()
                        self.assertEqual(r2.status, 302)
                        cb_path = r2.getheader("Location")
                        self.assertIsNotNone(cb_path)

                        hc.request("GET", str(cb_path), headers={"Cookie": bind_ck})
                        r3 = hc.getresponse()
                        r3.read()
                        self.assertEqual(r3.status, 302)
                        self.assertEqual(r3.getheader("Location"), "/")
                    finally:
                        hc.close()
                finally:
                    srv_rt.shutdown()
                    srv_rt.server_close()
        client.router.repository.close()

    # 14. CSRF `Origin` hardening (empty Host, X-Forwarded-Host spoof, http downgrade, null), non-ASCII HMAC, mixed-case live gate & `redact_pii`
    def test_csrf_origin_hardening_non_ascii_hmac_mixed_case_live_gate_and_redact_pii(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "csrf_hardening.db"
            tc = VacationPlannerTestClient(db_path=db_path)
            sess = login_via_oauth_pkce(
                tc, "csrf.guard@gmail.com", https_forwarded=True
            )
            csrf = sess["csrf_token"]

            # Non-ASCII X-CSRF-Token returns clean 403 (never 422 TypeError)
            non_ascii_r = tc.put(
                "/api/v1/profile",
                json={"adults_count": 3},
                headers={"X-CSRF-Token": "שלום-עולם-123"},
            )
            self.assertEqual(non_ascii_r.status_code, 403)

            # TestClient without Host (PUBLIC_BASE_URL unset): forged Origin, null Origin & bad scheme all return 403 across mutating endpoints
            with _EnvContext({"PUBLIC_BASE_URL": None}):
                for bad_origin in (
                    "https://attacker.example",
                    "null",
                    "javascript:alert(1)",
                    "http://evil.local:9999",
                ):
                    self.assertEqual(
                        tc.put(
                            "/api/v1/profile",
                            json={"adults_count": 4, "matmid_points_balance": 999},
                            headers={"X-CSRF-Token": csrf, "Origin": bad_origin},
                        ).status_code,
                        403,
                        f"Expected 403 for Origin={bad_origin!r}",
                    )
                self.assertEqual(
                    tc.put(
                        "/api/v1/auth/notifications",
                        json={"notifications_enabled": True},
                        headers={
                            "X-CSRF-Token": csrf,
                            "Origin": "https://attacker.example",
                        },
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    tc.post(
                        "/api/v1/auth/logout",
                        headers={
                            "X-CSRF-Token": csrf,
                            "Origin": "https://attacker.example",
                        },
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    tc.delete(
                        "/api/v1/auth/account",
                        headers={
                            "X-CSRF-Token": csrf,
                            "Origin": "https://attacker.example",
                        },
                    ).status_code,
                    403,
                )
                # Confirm zero DB mutation occurred
                self.assertFalse(tc.get("/api/v1/profile").json()["is_persisted"])

            # Under HTTPS PUBLIC_BASE_URL: spoofed X-Forwarded-Host AND http:// Origin downgrade MUST be rejected (403)
            with _EnvContext(
                {"PUBLIC_BASE_URL": "https://breezyflights.com"}
            ):
                self.assertEqual(
                    tc.put(
                        "/api/v1/profile",
                        json={"adults_count": 3},
                        headers={
                            "X-CSRF-Token": csrf,
                            "X-Forwarded-Proto": "https",
                            "X-Forwarded-Host": "attacker.example",
                            "Host": "attacker.example",
                            "Origin": "https://attacker.example",
                        },
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    tc.put(
                        "/api/v1/profile",
                        json={"adults_count": 3},
                        headers={
                            "X-CSRF-Token": csrf,
                            "X-Forwarded-Proto": "https",
                            "Origin": "http://breezyflights.com",
                        },
                    ).status_code,
                    403,
                )
                # Matching HTTPS Origin succeeds (200)
                self.assertEqual(
                    tc.put(
                        "/api/v1/profile",
                        json={"adults_count": 2, "matmid_points_balance": 55000},
                        headers={
                            "X-CSRF-Token": csrf,
                            "X-Forwarded-Proto": "https",
                            "Origin": "https://breezyflights.com",
                        },
                    ).status_code,
                    200,
                )

            # Mixed-case ELAL_LIVE_FETCH_ENABLED=True/true/YES/On locks down /test-login & /test-oauth-authorize -> 404
            for live_val in ("True", "true", "TRUE", "YES", "On", "1"):
                with _EnvContext(
                    {
                        "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                        "ELAL_LIVE_FETCH_ENABLED": live_val,
                        "PUBLIC_BASE_URL": None,
                    }
                ):
                    self.assertTrue(SQLiteRepository.is_live_fetch_mode())
                    self.assertEqual(
                        tc.post(
                            "/api/v1/auth/test-login", json={"email": "x@gmail.com"}
                        ).status_code,
                        404,
                        f"test-login must return 404 when ELAL_LIVE_FETCH_ENABLED={live_val!r}",
                    )
                    self.assertEqual(
                        tc.get(
                            "/api/v1/auth/test-oauth-authorize?state=s&nonce=n&code_challenge=c&code_challenge_method=S256"
                        ).status_code,
                        404,
                        f"test-oauth-authorize must return 404 when ELAL_LIVE_FETCH_ENABLED={live_val!r}",
                    )

            # Verify redact_pii scrubs emails, cookies, OAuth codes, and secrets
            raw_err = (
                "Failed login for parent.secret@gmail.com with "
                "__Host-fvp_session=tok_abc123; fvp_session=loc_456 "
                "code=oauth_code_789 client_secret=topsecret_xyz id_token=eyJ.abc.def"
            )
            scrubbed = redact_pii(raw_err)
            for secret_piece in (
                "parent.secret@gmail.com",
                "tok_abc123",
                "loc_456",
                "oauth_code_789",
                "topsecret_xyz",
                "eyJ.abc.def",
            ):
                self.assertNotIn(secret_piece, scrubbed)
            self.assertIn("[REDACTED_EMAIL]", scrubbed)
            self.assertIn("[REDACTED]", scrubbed)

    # 15. Negative OIDC JWT claims, `@googlemail.com`, `sub` collision, unsaved-user ephemeral IDOR & personalized private cache headers
    def test_oidc_jwt_negative_vectors_googlemail_sub_collision_ephemeral_idor_and_private_headers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "oidc_and_idor.db"
            client = VacationPlannerTestClient(db_path=db_path)

            with _EnvContext(
                {
                    "GOOGLE_OAUTH_CLIENT_ID": "oidc-cid.apps.googleusercontent.com",
                    "GOOGLE_OAUTH_CLIENT_SECRET": "oidc-csec",
                    "PUBLIC_BASE_URL": "https://breezyflights.com",
                    "VACATION_PLANNER_AUTH_TEST_MODE": None,
                }
            ):
                now_ep = int(time.time())
                negative_jwt_cases: list[tuple[str, str, dict[str, Any], int]] = [
                    ("alg_none", "none", {}, 401),
                    ("alg_hs256", "HS256", {}, 401),
                    ("expired_exp", "RS256", {"exp": now_ep - 10}, 401),
                    ("future_iat", "RS256", {"iat": now_ep + 900}, 401),
                    (
                        "list_aud_missing_azp",
                        "RS256",
                        {"aud": ["oidc-cid.apps.googleusercontent.com", "other"]},
                        401,
                    ),
                    (
                        "list_aud_wrong_azp",
                        "RS256",
                        {
                            "aud": ["oidc-cid.apps.googleusercontent.com", "other"],
                            "azp": "wrong-azp",
                        },
                        401,
                    ),
                    ("non_ascii_nonce", "RS256", {"nonce": "נונס-לא-חוקי"}, 401),
                    ("non_ascii_aud", "RS256", {"aud": "לקוח-לא-חוקי"}, 401),
                ]
                for label, alg_val, claim_overrides, expected_status in negative_jwt_cases:
                    l_r = client.get("/api/v1/auth/google/login")
                    q_l = dict(
                        urllib.parse.parse_qsl(
                            urllib.parse.urlsplit(l_r.headers["Location"]).query
                        )
                    )
                    with client.router.repository.connection() as conn:
                        nonce_row = conn.execute(
                            "SELECT nonce FROM oauth_login_states WHERE state_sha256 = ?",
                            (sha256_hex(q_l["state"]),),
                        ).fetchone()
                        valid_nonce = str(nonce_row["nonce"])

                    def _neg_exchanger(
                        _c: str,
                        _v: str,
                        _r: str,
                        cid: str,
                        _s: str,
                        alg_p: str = alg_val,
                        ov: dict[str, Any] = claim_overrides,
                        n_p: str = valid_nonce,
                    ) -> dict[str, Any]:
                        ts = int(time.time())
                        base_claims: dict[str, Any] = {
                            "iss": "https://accounts.google.com",
                            "aud": cid,
                            "sub": "sub-valid-1",
                            "email": "ok@gmail.com",
                            "email_verified": True,
                            "nonce": n_p,
                            "iat": ts,
                            "exp": ts + 3600,
                        }
                        base_claims.update(ov)
                        return {
                            "id_token": build_unsigned_or_hs256_jwt_for_test(
                                base_claims, alg=alg_p
                            )
                        }

                    client.router.auth_service.token_exchanger = _neg_exchanger
                    cb_r = client.get(
                        f"/api/v1/auth/google/callback?code=c1&state={urllib.parse.quote(q_l['state'])}"
                    )
                    self.assertEqual(
                        cb_r.status_code,
                        expected_status,
                        f"Failed OIDC negative case {label}: got {cb_r.status_code} ({cb_r.text})",
                    )

                # Positive @googlemail.com + list-aud with valid azp succeeds (302)
                gm_login = client.get("/api/v1/auth/google/login")
                gm_q = dict(
                    urllib.parse.parse_qsl(
                        urllib.parse.urlsplit(gm_login.headers["Location"]).query
                    )
                )
                with client.router.repository.connection() as conn:
                    gm_nonce = str(
                        conn.execute(
                            "SELECT nonce FROM oauth_login_states WHERE state_sha256 = ?",
                            (sha256_hex(gm_q["state"]),),
                        ).fetchone()["nonce"]
                    )
                client.router.auth_service.token_exchanger = lambda _c, _v, _r, cid, _s: {
                    "id_token": build_unsigned_or_hs256_jwt_for_test(
                        {
                            "iss": "accounts.google.com",
                            "aud": [cid, "secondary-aud"],
                            "azp": cid,
                            "sub": "sub-googlemail-owner",
                            "email": "Family.Member@googlemail.com",
                            "email_verified": True,
                            "nonce": gm_nonce,
                            "iat": int(time.time()),
                            "exp": int(time.time()) + 3600,
                        },
                        alg="ES256",
                    )
                }
                gm_cb = client.get(
                    f"/api/v1/auth/google/callback?code=c2&state={urllib.parse.quote(gm_q['state'])}"
                )
                self.assertEqual(gm_cb.status_code, 302)

                # Email-to-different-sub rebinding collision rejected (ValueError in repo, 403 in OAuth callback)
                with self.assertRaises(ValueError):
                    client.router.repository.upsert_google_user(
                        google_sub="sub-different-attacker",
                        email="family.member@googlemail.com",
                        email_verified=True,
                    )
                col_login = client.get("/api/v1/auth/google/login")
                col_q = dict(
                    urllib.parse.parse_qsl(
                        urllib.parse.urlsplit(col_login.headers["Location"]).query
                    )
                )
                with client.router.repository.connection() as conn:
                    col_nonce = str(
                        conn.execute(
                            "SELECT nonce FROM oauth_login_states WHERE state_sha256 = ?",
                            (sha256_hex(col_q["state"]),),
                        ).fetchone()["nonce"]
                    )
                client.router.auth_service.token_exchanger = lambda _c, _v, _r, cid, _s: {
                    "id_token": build_unsigned_or_hs256_jwt_for_test(
                        {
                            "iss": "https://accounts.google.com",
                            "aud": cid,
                            "sub": "sub-different-attacker",
                            "email": "family.member@googlemail.com",
                            "email_verified": True,
                            "nonce": col_nonce,
                            "iat": int(time.time()),
                            "exp": int(time.time()) + 3600,
                        }
                    )
                }
                col_cb = client.get(
                    f"/api/v1/auth/google/callback?code=c3&state={urllib.parse.quote(col_q['state'])}"
                )
                self.assertEqual(col_cb.status_code, 403)

            # Unsaved authenticated user ephemeral proposal IDOR isolation (404 for Guest & User B, 200 for Owner)
            unsaved_u1 = VacationPlannerTestClient(db_path=db_path)
            other_u2 = VacationPlannerTestClient(db_path=db_path)
            guest_c = VacationPlannerTestClient(db_path=db_path)
            login_via_oauth_pkce(unsaved_u1, "unsaved.u1@gmail.com")
            login_via_oauth_pkce(other_u2, "other.u2@gmail.com")

            u1_search = unsaved_u1.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO"],
                    "inline_profile": {
                        "adults_count": 2,
                        "matmid_points_balance": 120000,
                        "children": [{"child_age_years": 6}],
                    },
                },
            )
            self.assertEqual(u1_search.status_code, 200)
            u1_eph_id = u1_search.json()["proposals"][0]["id"]
            # Owner accesses ephemeral proposal cleanly via resolve_proposal_for_requester, Guest & User 2 get None; removed /compare returns 404
            u1_uid = unsaved_u1.get("/api/v1/auth/session").json()["user"]["id"]
            u2_uid = other_u2.get("/api/v1/auth/session").json()["user"]["id"]
            self.assertIsNotNone(
                unsaved_u1.router.planner_service.resolve_proposal_for_requester(
                    u1_eph_id, requester_user_id=u1_uid, enforce_owner=True
                )
            )
            self.assertIsNone(
                unsaved_u1.router.planner_service.resolve_proposal_for_requester(
                    u1_eph_id, requester_user_id=None, enforce_owner=True
                )
            )
            self.assertIsNone(
                unsaved_u1.router.planner_service.resolve_proposal_for_requester(
                    u1_eph_id, requester_user_id=u2_uid, enforce_owner=True
                )
            )
            guest_c.router = unsaved_u1.router
            other_u2.router = unsaved_u1.router
            for req_client in (unsaved_u1, guest_c, other_u2):
                self.assertEqual(
                    req_client.post(
                        "/api/v1/vacations/compare", json={"proposal_ids": [u1_eph_id]}
                    ).status_code,
                    404,
                )

            # Personalized endpoints emit Vary: Cookie + Cache-Control: no-store, private & omit wildcard CORS over HTTP
            srv = create_http_server("127.0.0.1", 0, db_path=db_path)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                cookie_hdr = "; ".join(
                    f"{k}={v}" for k, v in unsaved_u1.cookies.items()
                )
                for method_p, path_p, body_p in (
                    ("GET", "/api/v1/moe-calendar/upcoming?as_of=2026-11-20", None),
                    ("GET", "/api/v1/moe-calendar/2026-2027", None),
                    (
                        "POST",
                        "/api/v1/vacations/search",
                        json.dumps(
                            {
                                "date_selection_mode": "SPECIFIC_DATES",
                                "specific_departure_date": "2027-04-11",
                                "specific_return_date": "2027-04-18",
                                "destination_iatas": ["FCO"],
                            }
                        ),
                    ),
                ):
                    hc = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
                    try:
                        req_h = {"Cookie": cookie_hdr}
                        if body_p is not None:
                            req_h["Content-Type"] = "application/json"
                        hc.request(method_p, path_p, body=body_p, headers=req_h)
                        r_http = hc.getresponse()
                        raw_resp_body = r_http.read().decode("utf-8")
                        hdrs_l = {k.lower(): v for k, v in r_http.getheaders()}
                        self.assertEqual(r_http.status, 200)
                        self.assertEqual(hdrs_l.get("cache-control"), "no-store, private")
                        self.assertIn("cookie", (hdrs_l.get("vary") or "").lower())
                        self.assertNotIn("access-control-allow-origin", hdrs_l)
                        if path_p == "/api/v1/vacations/search":
                            live_pid = json.loads(raw_resp_body)["proposals"][0]["id"]
                    finally:
                        hc.close()

                for method_p, path_p, body_p in (
                    (
                        "POST",
                        "/api/v1/vacations/compare",
                        json.dumps({"proposal_ids": [live_pid]}),
                    ),
                ):
                    hc = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
                    try:
                        req_h = {"Cookie": cookie_hdr}
                        if body_p is not None:
                            req_h["Content-Type"] = "application/json"
                        hc.request(method_p, path_p, body=body_p, headers=req_h)
                        r_http = hc.getresponse()
                        r_http.read()
                        hdrs_l = {k.lower(): v for k, v in r_http.getheaders()}
                        self.assertEqual(r_http.status, 404)
                        self.assertEqual(hdrs_l.get("cache-control"), "no-store, private")
                        self.assertIn("cookie", (hdrs_l.get("vary") or "").lower())
                        self.assertNotIn("access-control-allow-origin", hdrs_l)
                    finally:
                        hc.close()
            finally:
                srv.shutdown()
                srv.server_close()

    # 16. Multi-threaded concurrency stress: 8-thread atomic OAuth state race, upsert_google_user, _ephemeral_proposals & batched save_search_results
    def test_multithreaded_concurrency_oauth_state_single_use_upsert_user_and_ephemeral_cache(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "concurrency_stress.db"
            with _EnvContext(
                {
                    "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                    "ELAL_LIVE_FETCH_ENABLED": "0",
                    "PUBLIC_BASE_URL": None,
                }
            ):
                srv = create_http_server("127.0.0.1", 0, db_path=db_path)
                port = srv.server_address[1]
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                try:
                    # 1. Initiate a single OAuth login state + local test code
                    c_init = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
                    c_init.request(
                        "GET",
                        "/api/v1/auth/google/login?mock_oauth=1&test_email=race.winner@gmail.com",
                    )
                    r_login = c_init.getresponse()
                    r_login.read()
                    self.assertEqual(r_login.status, 302)
                    bind_cookie = ""
                    for hk, hv in r_login.getheaders():
                        if hk.lower() == "set-cookie" and "fvp_oauth_bind=" in hv:
                            bind_cookie = hv.split(";", 1)[0].strip()
                    authz_loc = r_login.getheader("Location")
                    c_init.close()

                    c_authz = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
                    c_authz.request(
                        "GET", authz_loc, headers={"Cookie": bind_cookie}
                    )
                    r_authz = c_authz.getresponse()
                    r_authz.read()
                    self.assertEqual(r_authz.status, 302)
                    callback_path = r_authz.getheader("Location")
                    c_authz.close()

                    # Fire 8 synchronized concurrent threads with the exact same single-use `state`
                    barrier = threading.Barrier(8)
                    statuses: list[int] = []
                    statuses_lock = threading.Lock()
                    errors: list[str] = []

                    def _race_callback() -> None:
                        conn_t = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=10.0
                        )
                        try:
                            barrier.wait(timeout=5.0)
                            conn_t.request(
                                "GET",
                                callback_path,
                                headers={"Cookie": bind_cookie},
                            )
                            resp_t = conn_t.getresponse()
                            resp_t.read()
                            with statuses_lock:
                                statuses.append(resp_t.status)
                        except Exception as exc:
                            with statuses_lock:
                                errors.append(repr(exc))
                        finally:
                            conn_t.close()

                    threads = [
                        threading.Thread(target=_race_callback) for _ in range(8)
                    ]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join(timeout=15.0)

                    self.assertEqual(errors, [])
                    self.assertEqual(len(statuses), 8)
                    self.assertEqual(
                        statuses.count(302),
                        1,
                        f"Expected exactly 1x 302 winner, got {statuses}",
                    )
                    self.assertEqual(
                        statuses.count(400),
                        7,
                        f"Expected 7x 400 replays rejected, got {statuses}",
                    )
                    self.assertEqual(statuses.count(422), 0)
                finally:
                    srv.shutdown()
                    srv.server_close()

            # 2. Concurrent upsert_google_user race (8 threads inserting the same new google_sub simultaneously)
            repo = SQLiteRepository(db_path=db_path, auto_seed=False)
            upsert_barrier = threading.Barrier(8)
            upsert_ids: list[str] = []
            upsert_errs: list[str] = []
            u_lock = threading.Lock()

            def _concurrent_upsert(idx: int) -> None:
                try:
                    upsert_barrier.wait(timeout=5.0)
                    u_rec = repo.upsert_google_user(
                        google_sub="sub-concurrent-brand-new",
                        email="concurrent.new@gmail.com",
                        email_verified=True,
                        display_name=f"Concurrent {idx}",
                    )
                    with u_lock:
                        upsert_ids.append(u_rec["id"])
                except Exception as exc:
                    with u_lock:
                        upsert_errs.append(repr(exc))

            u_threads = [
                threading.Thread(target=_concurrent_upsert, args=(i,))
                for i in range(8)
            ]
            for t in u_threads:
                t.start()
            for t in u_threads:
                t.join(timeout=15.0)
            self.assertEqual(upsert_errs, [])
            self.assertEqual(len(set(upsert_ids)), 1)

            # 3. Concurrent _ephemeral_proposals write / read / prune / evict stress -> 0 RuntimeErrors
            tc_stress = VacationPlannerTestClient(db_path=db_path)
            seed_resp = tc_stress.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO"],
                },
            )
            self.assertEqual(seed_resp.status_code, 200)
            planner = tc_stress.router.planner_service
            sample_prop = next(iter(planner._ephemeral_proposals.values()))[0]
            eph_errors: list[str] = []
            eph_lock = threading.Lock()

            def _writer_worker(w_id: int) -> None:
                try:
                    for i in range(120):
                        cloned = sample_prop.from_dict(
                            {**sample_prop.to_dict(), "id": f"eph-{w_id}-{i}"}
                        )
                        planner._store_ephemeral_proposals(
                            [cloned], owner_user_id=f"u-{w_id % 3}"
                        )
                except Exception as exc:
                    with eph_lock:
                        eph_errors.append(repr(exc))

            def _reader_evictor_worker(r_id: int) -> None:
                try:
                    for i in range(120):
                        planner.resolve_proposal_for_requester(
                            f"eph-{r_id}-{i}",
                            requester_user_id=f"u-{r_id % 3}",
                            enforce_owner=True,
                        )
                        planner._prune_ephemeral_proposals()
                        planner.evict_ephemeral_proposals_for_user(f"u-{i % 3}")
                except Exception as exc:
                    with eph_lock:
                        eph_errors.append(repr(exc))

            stress_threads = [
                threading.Thread(target=_writer_worker, args=(w,)) for w in range(4)
            ] + [
                threading.Thread(target=_reader_evictor_worker, args=(r,))
                for r in range(4)
            ]
            for t in stress_threads:
                t.start()
            for t in stress_threads:
                t.join(timeout=15.0)
            self.assertEqual(eph_errors, [])

            # 4. Verify save_search_results batches query + itineraries + proposals in a SINGLE repository.connection() call
            authed_tc = VacationPlannerTestClient(db_path=db_path)
            s_auth = login_via_oauth_pkce(authed_tc, "batch.tx@gmail.com")
            authed_tc.put(
                "/api/v1/profile",
                json={"adults_count": 2, "matmid_points_balance": 160000},
                headers={"X-CSRF-Token": s_auth["csrf_token"]},
            )
            conn_open_count = 0
            orig_conn_cm = authed_tc.router.repository.connection

            from contextlib import contextmanager as _cm

            @_cm
            def _counting_conn():
                nonlocal conn_open_count
                conn_open_count += 1
                with orig_conn_cm() as c:
                    yield c

            q_batch_resp = authed_tc.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "destination_iatas": ["FCO", "ATH"],
                },
            )
            self.assertEqual(q_batch_resp.status_code, 200)
            props_objs = [
                sample_prop.from_dict(p) for p in q_batch_resp.json()["proposals"]
            ]
            self.assertGreaterEqual(len(props_objs), 2)
            conn_open_count = 0
            authed_tc.router.repository.connection = _counting_conn  # type: ignore[method-assign]
            try:
                authed_tc.router.repository.save_search_results(
                    q_batch_resp.json()["query"], props_objs
                )
            finally:
                authed_tc.router.repository.connection = orig_conn_cm  # type: ignore[method-assign]
            self.assertEqual(
                conn_open_count,
                1,
                f"save_search_results must execute in 1 transaction, opened {conn_open_count}",
            )

    # 17. Run 10 R4: Non-affiliation disclaimer on local test OAuth sign-in page (he & en), profile sign-in box, and footer
    def test_run10_r4_non_affiliation_disclaimers_on_local_oauth_and_main_surfaces(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "r4_disclaimers.sqlite"
            old_test_mode = os.environ.get("VACATION_PLANNER_AUTH_TEST_MODE")
            old_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
            os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = "1"
            os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"
            try:
                tc_he = VacationPlannerTestClient(db_path=db_path)
                r_login_he = tc_he.get("/api/v1/auth/google/login?lang=he")
                self.assertEqual(r_login_he.status_code, 302)
                r_page_he = tc_he.get(r_login_he.headers["Location"])
                self.assertEqual(r_page_he.status_code, 200)
                self.assertIn('dir="rtl"', r_page_he.text)
                self.assertIn('id="local-signin-disclaimer"', r_page_he.text)
                self.assertIn(
                    "אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על",
                    r_page_he.text,
                )
                self.assertIn('id="test-oauth-form"', r_page_he.text)

                tc_en = VacationPlannerTestClient(db_path=db_path)
                r_login_en = tc_en.get("/api/v1/auth/google/login?lang=en")
                self.assertEqual(r_login_en.status_code, 302)
                r_page_en = tc_en.get(r_login_en.headers["Location"])
                self.assertEqual(r_page_en.status_code, 200)
                self.assertIn('dir="ltr"', r_page_en.text)
                self.assertIn('id="local-signin-disclaimer"', r_page_en.text)
                self.assertIn("independent vacation planning application", r_page_en.text)
                self.assertIn("not affiliated with", r_page_en.text)

                # Triple-gate 404 when ELAL_LIVE_FETCH_ENABLED=1 remains intact
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
                r_blocked = tc_en.get(r_login_en.headers["Location"])
                self.assertEqual(r_blocked.status_code, 404)
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = "0"

                # Main page index.html contains footer & profile sign-in disclaimers
                r_root = tc_he.get("/")
                self.assertEqual(r_root.status_code, 200)
                for req_id in (
                    'id="site-footer"',
                    'id="footer-elal-disclaimer"',
                    'id="profile-signin-disclaimer"',
                    'id="profile-user-disclaimer"',
                ):
                    self.assertIn(req_id, r_root.text)
                self.assertIn(
                    "אפליקציית תכנון חופשות עצמאית שאינה שייכת לאל על",
                    r_root.text,
                )
            finally:
                if old_test_mode is None:
                    os.environ.pop("VACATION_PLANNER_AUTH_TEST_MODE", None)
                else:
                    os.environ["VACATION_PLANNER_AUTH_TEST_MODE"] = old_test_mode
                if old_live is None:
                    os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
                else:
                    os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_live

    def test_admin_only_bonus_sync_diagnostics_strict_access_control(self) -> None:
        """Verify admin bonus sync diagnostics are returned ONLY to the admin account (`401` guest, `403` non-admin),
        follow the Run 15 12-month `periods` contract with zero `shard`/`trigger_job` keys, and all 3 removed trigger
        endpoints return `404`.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "admin_sync.db"
            with _EnvContext(
                {
                    "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                    "ELAL_LIVE_FETCH_ENABLED": "0",
                    "VACATION_PLANNER_ADMIN_EMAILS": "admin.owner@gmail.com",
                }
            ):
                guest_client = VacationPlannerTestClient(db_path=str(db_path))
                regular_client = VacationPlannerTestClient(db_path=str(db_path))
                admin_client = VacationPlannerTestClient(db_path=str(db_path))

                # 1. Guest receives is_admin=False, no admin_bonus_sync in session, and 401 on /api/v1/admin/bonus-sync-status
                g_sess = guest_client.get("/api/v1/auth/session").json()
                self.assertFalse(g_sess["authenticated"])
                self.assertFalse(g_sess["is_admin"])
                self.assertNotIn("admin_bonus_sync", g_sess)
                self.assertEqual(
                    guest_client.get("/api/v1/admin/bonus-sync-status").status_code,
                    401,
                )

                # 2. Regular authenticated Gmail user receives is_admin=False, no admin_bonus_sync, and 403 on admin endpoint
                r_login = regular_client.post(
                    "/api/v1/auth/test-login", json={"email": "regular.family@gmail.com"}
                )
                self.assertEqual(r_login.status_code, 200)
                r_sess = regular_client.get("/api/v1/auth/session").json()
                self.assertTrue(r_sess["authenticated"])
                self.assertFalse(r_sess["is_admin"])
                self.assertNotIn("admin_bonus_sync", r_sess)
                r_adm = regular_client.get("/api/v1/admin/bonus-sync-status")
                self.assertEqual(r_adm.status_code, 403)
                self.assertEqual(r_adm.headers.get("Cache-Control"), "no-store, private")

                # 3. Admin Gmail user receives is_admin=True + full 12-month period diagnostics on both /session and /admin/bonus-sync-status
                a_login = admin_client.post(
                    "/api/v1/auth/test-login", json={"email": "admin.owner@gmail.com"}
                )
                self.assertEqual(a_login.status_code, 200)
                a_sess = admin_client.get("/api/v1/auth/session").json()
                self.assertTrue(a_sess["authenticated"])
                self.assertTrue(a_sess["is_admin"])
                diag = a_sess["admin_bonus_sync"]

                for forbidden_key in (
                    "shards",
                    "shard_count",
                    "fresh_shards_count",
                    "target_shards_per_day",
                    "sync_mode_detected",
                    "trigger_job",
                ):
                    self.assertNotIn(forbidden_key, diag)
                raw_diag_json = json.dumps(diag, ensure_ascii=False)
                self.assertNotIn("shard", raw_diag_json.lower())
                self.assertNotIn("5 חלקים", raw_diag_json)
                self.assertIsNone(re.search(r"(?<![א-ת])יוני(?![א-ת])", raw_diag_json))

                self.assertEqual(diag["horizon_days"], 350)
                self.assertEqual(diag["sync_source"], "CHROME_EXTENSION_MANUAL")
                self.assertEqual(diag["sync_mode"], "manual_extension_full_year")
                self.assertEqual(diag["period_count"], 12)
                self.assertEqual(diag["total_periods_count"], 12)
                self.assertEqual(len(diag["periods"]), 12)
                self.assertEqual(
                    diag["covered_periods_count"]
                    + diag["partial_periods_count"]
                    + diag["empty_periods_count"],
                    12,
                )
                self.assertGreater(diag["total_active_rows"], 0)
                self.assertGreaterEqual(diag["covered_periods_count"], 1)
                self.assertIn(
                    diag["health_state"],
                    ("HEALTHY", "PARTIAL", "DELAYED", "STALE", "EMPTY"),
                )
                self.assertIn(
                    diag["overall_status"],
                    ("fresh", "partial", "delayed", "stale", "empty"),
                )
                june_periods = [p for p in diag["periods"] if p["month"] == 6]
                self.assertEqual(len(june_periods), 1)
                self.assertIn("יונ׳", june_periods[0]["label_he"])
                for idx, p in enumerate(diag["periods"], 1):
                    self.assertEqual(p["period_index"], idx)
                    self.assertRegex(p["period_key"], r"^\d{4}-\d{2}$")
                    self.assertIn(p["status"], ("COVERED", "PARTIAL", "EMPTY"))
                    self.assertIsInstance(p["holidays_he"], list)
                    self.assertIsInstance(p["holidays_en"], list)
                    self.assertEqual(p["has_school_holiday"], bool(p["holidays_he"]))

                a_adm = admin_client.get("/api/v1/admin/bonus-sync-status")
                self.assertEqual(a_adm.status_code, 200)
                self.assertEqual(a_adm.headers.get("Cache-Control"), "no-store, private")
                adm_diag = a_adm.json()["admin_bonus_sync"]
                self.assertEqual(len(adm_diag["periods"]), 12)
                self.assertNotIn("shards", adm_diag)
                self.assertNotIn("trigger_job", adm_diag)

                # 3b. All 3 removed remote trigger/poll/ack endpoints return 404 across guest, regular, and admin
                for cli, csrf_hdr in (
                    (guest_client, {}),
                    (regular_client, {"X-CSRF-Token": r_sess["csrf_token"]}),
                    (admin_client, {"X-CSRF-Token": a_sess["csrf_token"]}),
                ):
                    self.assertEqual(
                        cli.post(
                            "/api/v1/admin/bonus-sync-trigger",
                            json={"mode": "FULL"},
                            headers=csrf_hdr,
                        ).status_code,
                        404,
                    )
                    self.assertEqual(
                        cli.get("/api/v1/elal-bonus/sync-trigger-poll").status_code,
                        404,
                    )
                    self.assertEqual(
                        cli.post(
                            "/api/v1/elal-bonus/sync-trigger-ack",
                            json={"job_id": "none", "status": "COMPLETED"},
                        ).status_code,
                        404,
                    )

                guest_client.router.repository.close()
                regular_client.router.repository.close()
                admin_client.router.repository.close()

            # 4. Also verify default built-in admin SHA-256 matches yoni.budovsky@gmail.com without env var
            with _EnvContext(
                {
                    "VACATION_PLANNER_AUTH_TEST_MODE": "1",
                    "ELAL_LIVE_FETCH_ENABLED": "0",
                }
            ):
                os.environ.pop("VACATION_PLANNER_ADMIN_EMAILS", None)
                def_admin = VacationPlannerTestClient(db_path=str(db_path))
                admin_addr = ".".join(["yoni", "budovsky"]) + "@gmail.com"
                def_admin.post("/api/v1/auth/test-login", json={"email": admin_addr})
                def_sess = def_admin.get("/api/v1/auth/session").json()
                self.assertTrue(def_sess["is_admin"])
                self.assertIn("admin_bonus_sync", def_sess)
                self.assertEqual(len(def_sess["admin_bonus_sync"]["periods"]), 12)
                def_admin.router.repository.close()

    def test_run15_period_diagnostics_transitions_sync_guide_and_extension_contracts(
        self,
    ) -> None:
        """Verify Run 15 health/period state transitions (`EMPTY` -> `PARTIAL` -> `HEALTHY` -> `DELAYED` -> `STALE`),
        script deletions, `SYNC_COMMANDS_GUIDE.md` `U+200F` RTL & forbidden-word rules, Chromium V8 syntax compilation
        (`node --check` if present + CDP `Runtime.compileScript`), extension DOM default `all` mode, and end-to-end
        simulated full-year upload through `background.js` -> `POST /api/v1/elal-bonus/sync`.
        """
        import base64
        import shutil
        import signal
        import socket
        import struct
        import subprocess
        import urllib.request

        repo_root = Path(__file__).resolve().parents[1]

        # 1. Script deletions & repository trigger method removal
        for deleted_rel in (
            "scripts/sync_elal_to_server.py",
            "scripts/install_cloudtop_daily_sync.sh",
            "scripts/install_mac_daily_sync.sh",
        ):
            self.assertFalse(
                (repo_root / deleted_rel).exists(), f"{deleted_rel} must be deleted"
            )
        for removed_method in (
            "_sync_trigger_path",
            "get_sync_trigger_state",
            "enqueue_sync_trigger",
            "ack_sync_trigger",
        ):
            self.assertFalse(hasattr(SQLiteRepository, removed_method))

        # 2. SYNC_COMMANDS_GUIDE.md U+200F RTL & zero forbidden agent/shard terms
        guide_txt = (repo_root / "SYNC_COMMANDS_GUIDE.md").read_text(encoding="utf-8")
        for bad_term in (
            "sync_elal_to_server",
            "install_cloudtop",
            "install_mac",
            "systemd",
            "systemctl --user",
            "journalctl --user",
            "fvp-elal-sync",
            "launchagent",
            "launchctl",
            "com.breezyflights",
            "shard_state",
            "fvp-chrome-sync-profile",
            "elal_sync_api_token",
            "sync-trigger",
            "bonus-sync-trigger",
            "5 חלקים",
            "shard",
        ):
            self.assertNotIn(bad_term.lower(), guide_txt.lower())
        in_fence = False
        hebrew_lines_checked = 0
        for lineno, raw_line in enumerate(guide_txt.splitlines(), 1):
            s = raw_line.strip()
            if s.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not s or s == "---":
                continue
            if re.search(r"[\u0590-\u05FF]", s):
                hebrew_lines_checked += 1
                item_body = re.sub(r"^(?:[-*+]\s+|\d+\.\s+)", "", s)
                self.assertTrue(
                    item_body.startswith("\u200f"),
                    f"SYNC_COMMANDS_GUIDE.md:{lineno} missing U+200F prefix",
                )
                first_visible = re.sub(
                    r"^(?:#+\s*)?(?:\d+\.\s*)?[*_`]*", "", item_body[1:]
                )
                self.assertIsNone(
                    re.match(r"^[A-Za-z]", first_visible),
                    f"SYNC_COMMANDS_GUIDE.md:{lineno} starts with Latin text: {raw_line!r}",
                )
        self.assertGreaterEqual(hebrew_lines_checked, 15)

        # 3. Health & monthly period transitions on isolated live-mode SQLite DB
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "run15_transitions.db"
            with _EnvContext({"ELAL_LIVE_FETCH_ENABLED": "1"}):
                client = VacationPlannerTestClient(db_path=str(db_path))
                repo = client.router.repository
                t0 = datetime(2026, 12, 1, 9, 0, 0, tzinfo=UTC)

                # (a) Empty #live inventory -> EMPTY / empty, 12 EMPTY months
                d_empty = repo.get_bonus_sync_diagnostics(now_dt=t0)
                self.assertEqual(d_empty["health_state"], "EMPTY")
                self.assertEqual(d_empty["overall_status"], "empty")
                self.assertEqual(d_empty["empty_periods_count"], 12)
                self.assertEqual(d_empty["covered_periods_count"], 0)
                # Dec 2026 overlaps Hanukkah MoE vacation -> has_school_holiday True with holiday name
                dec_p = d_empty["periods"][0]
                self.assertEqual(dec_p["period_key"], "2026-12")
                self.assertTrue(dec_p["has_school_holiday"])
                self.assertGreaterEqual(len(dec_p["holidays_he"]), 1)

                # (b) Insert 1 flight on 1 date / 1 destination -> PARTIAL month & PARTIAL overall health
                t_fetch_iso = "2026-12-01T08:00:00Z"
                with repo.connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO elal_bonus_availability (
                            id, origin_iata, destination_iata, direction, flight_number,
                            operating_carrier, flight_date, departure_time_local, arrival_time_local,
                            economy_award_seats, award_zone, taxes_usd_per_pax,
                            source_url, fetched_at, expires_at
                        ) VALUES (?, 'TLV', 'FCO', 'OUTBOUND', 'LY381', 'LY', '2026-12-10', '07:15', '10:00',
                                  2, 'ZONE_B', 48.75, 'https://www.elal.com/rbddataclients/#live', ?, '2026-12-31T08:00:00Z')
                        """,
                        ("LY381_2026-12-10", t_fetch_iso),
                    )
                d_partial = repo.get_bonus_sync_diagnostics(now_dt=t0)
                self.assertEqual(d_partial["health_state"], "PARTIAL")
                self.assertEqual(d_partial["overall_status"], "partial")
                self.assertEqual(d_partial["covered_periods_count"], 0)
                self.assertEqual(d_partial["partial_periods_count"], 1)
                self.assertEqual(d_partial["periods"][0]["status"], "PARTIAL")

                # (c) Populate >=4 distinct dates across >=3 destinations in 2026-12 -> COVERED & HEALTHY (<=72h)
                rows_dec = []
                for d_day, dest_code, fl_num in (
                    ("2026-12-11", "ATH", "LY541"),
                    ("2026-12-12", "VIE", "LY361"),
                    ("2026-12-13", "FCO", "LY381"),
                    ("2026-12-14", "ATH", "LY541"),
                ):
                    rows_dec.append(
                        (
                            f"{fl_num}_{d_day}",
                            dest_code,
                            fl_num,
                            d_day,
                            t_fetch_iso,
                            "2026-12-31T08:00:00Z",
                        )
                    )
                with repo.connection() as conn:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO elal_bonus_availability (
                            id, origin_iata, destination_iata, direction, flight_number,
                            operating_carrier, flight_date, departure_time_local, arrival_time_local,
                            economy_award_seats, award_zone, taxes_usd_per_pax,
                            source_url, fetched_at, expires_at
                        ) VALUES (?, 'TLV', ?, 'OUTBOUND', ?, 'LY', ?, '07:00', '10:00',
                                  2, 'ZONE_B', 50.0, 'https://www.elal.com/rbddataclients/#live', ?, ?)
                        """,
                        rows_dec,
                    )
                d_healthy = repo.get_bonus_sync_diagnostics(now_dt=t0)
                self.assertEqual(d_healthy["health_state"], "HEALTHY")
                self.assertEqual(d_healthy["overall_status"], "fresh")
                self.assertEqual(d_healthy["covered_periods_count"], 1)
                self.assertEqual(d_healthy["periods"][0]["status"], "COVERED")

                # (d) +100h (72 < age <= 168) -> DELAYED / delayed
                d_delayed = repo.get_bonus_sync_diagnostics(
                    now_dt=t0 + timedelta(hours=100)
                )
                self.assertEqual(d_delayed["health_state"], "DELAYED")
                self.assertEqual(d_delayed["overall_status"], "delayed")

                # (e) +200h (> 168h, still unexpired) -> STALE / stale
                d_stale = repo.get_bonus_sync_diagnostics(
                    now_dt=t0 + timedelta(hours=200)
                )
                self.assertEqual(d_stale["health_state"], "STALE")
                self.assertEqual(d_stale["overall_status"], "stale")

                # 4. Browser extension syntax check (node --check if available + Chromium V8 CDP Runtime.compileScript),
                # widget DOM default (`all`), and simulated full-year upload via background.js -> /api/v1/elal-bonus/sync
                ext_dir = repo_root / "chrome_extension"
                content_js_path = ext_dir / "content.js"
                bg_js_path = ext_dir / "background.js"
                content_js_src = content_js_path.read_text(encoding="utf-8")
                bg_js_src = bg_js_path.read_text(encoding="utf-8")

                node_bin = shutil.which("node")
                if node_bin:
                    for js_p in (content_js_path, bg_js_path):
                        chk = subprocess.run(
                            [node_bin, "--check", str(js_p)],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(chk.returncode, 0, chk.stderr)

                chrome_bin = Path("/usr/bin/google-chrome")
                self.assertTrue(chrome_bin.exists(), "/usr/bin/google-chrome is required")
                short_parent = "/tmp" if len(tempfile.gettempdir()) > 55 else None
                chrome_udir = tempfile.mkdtemp(prefix="fvp_ext_v8_", dir=short_parent)
                proc = subprocess.Popen(
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
                        f"--user-data-dir={chrome_udir}",
                        "about:blank",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                sock: Optional[socket.socket] = None
                try:
                    port_file = Path(chrome_udir) / "DevToolsActivePort"
                    deadline = time.time() + 15.0
                    while time.time() < deadline and not (
                        port_file.exists() and port_file.read_text("utf-8").splitlines()
                    ):
                        time.sleep(0.05)
                    self.assertTrue(port_file.exists())
                    cdp_port = int(port_file.read_text("utf-8").splitlines()[0].strip())
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({})
                    )
                    with opener.open(
                        f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0
                    ) as r_list:
                        targets = json.loads(r_list.read().decode("utf-8"))
                    ws_url = next(
                        t["webSocketDebuggerUrl"]
                        for t in targets
                        if t.get("type") == "page"
                    )
                    ws_path = urllib.parse.urlsplit(ws_url).path
                    sock = socket.create_connection(("127.0.0.1", cdp_port), timeout=20.0)
                    ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
                    sock.sendall(
                        (
                            f"GET {ws_path} HTTP/1.1\r\nHost: 127.0.0.1:{cdp_port}\r\n"
                            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                            f"Sec-WebSocket-Key: {ws_key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                        ).encode("ascii")
                    )
                    buf = b""
                    while b"\r\n\r\n" not in buf:
                        buf += sock.recv(4096)
                    leftover = bytearray(buf[buf.index(b"\r\n\r\n") + 4 :])
                    msg_seq = 0

                    def ws_send(obj: dict[str, Any]) -> None:
                        assert sock is not None
                        raw_b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                        mask = os.urandom(4)
                        ln = len(raw_b)
                        if ln < 126:
                            hdr = bytes([0x81, 0x80 | ln]) + mask
                        elif ln < 65536:
                            hdr = bytes([0x81, 0x80 | 126]) + struct.pack("!H", ln) + mask
                        else:
                            hdr = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", ln) + mask
                        sock.sendall(
                            hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(raw_b))
                        )

                    def ws_recv_exact(n: int) -> bytes:
                        assert sock is not None
                        while len(leftover) < n:
                            more = sock.recv(65536)
                            if not more:
                                raise EOFError("CDP socket closed")
                            leftover.extend(more)
                        out_b = bytes(leftover[:n])
                        del leftover[:n]
                        return out_b

                    def ws_recv_msg() -> dict[str, Any]:
                        fragments: list[bytes] = []
                        while True:
                            b0, b1 = ws_recv_exact(2)
                            fin = bool(b0 & 0x80)
                            opcode = b0 & 0x0F
                            masked_flag = bool(b1 & 0x80)
                            ln = b1 & 0x7F
                            if ln == 126:
                                ln = struct.unpack("!H", ws_recv_exact(2))[0]
                            elif ln == 127:
                                ln = struct.unpack("!Q", ws_recv_exact(8))[0]
                            mkey = ws_recv_exact(4) if masked_flag else b""
                            payload_b = ws_recv_exact(ln)
                            if masked_flag:
                                payload_b = bytes(
                                    b ^ mkey[i % 4] for i, b in enumerate(payload_b)
                                )
                            if opcode == 0x9:
                                continue
                            fragments.append(payload_b)
                            if fin:
                                return json.loads(b"".join(fragments).decode("utf-8"))

                    def handle_binding(ev_msg: dict[str, Any]) -> None:
                        if ev_msg.get("method") != "Runtime.bindingCalled":
                            return
                        p = ev_msg.get("params", {})
                        if p.get("name") != "__extSyncBridge":
                            return
                        req = json.loads(p["payload"])
                        parsed_u = urllib.parse.urlsplit(req["url"])
                        st_code, _, resp_b = client.router.dispatch(
                            req["method"],
                            parsed_u.path,
                            json_body=json.loads(req["body"]) if req.get("body") else None,
                            request_headers={},
                        )
                        nonlocal msg_seq
                        msg_seq += 1
                        ws_send(
                            {
                                "id": msg_seq,
                                "method": "Runtime.evaluate",
                                "params": {
                                    "expression": f"window.__resolveExtFetch({req['id']}, {st_code}, {json.dumps(resp_b)})"
                                },
                            }
                        )

                    def cdp_call(
                        method: str, params: Optional[dict[str, Any]] = None
                    ) -> dict[str, Any]:
                        nonlocal msg_seq
                        msg_seq += 1
                        target_id = msg_seq
                        ws_send({"id": target_id, "method": method, "params": params or {}})
                        while True:
                            m = ws_recv_msg()
                            if m.get("id") == target_id:
                                return m
                            handle_binding(m)

                    cdp_call("Runtime.enable")
                    cdp_call("Runtime.addBinding", {"name": "__extSyncBridge"})

                    # Compile both extension files via V8 Runtime.compileScript
                    for fname, src in (
                        ("content.js", content_js_src),
                        ("background.js", bg_js_src),
                    ):
                        comp = cdp_call(
                            "Runtime.compileScript",
                            {
                                "expression": src,
                                "sourceURL": fname,
                                "persistScript": False,
                            },
                        )
                        self.assertNotIn(
                            "exceptionDetails",
                            comp.get("result", {}),
                            f"V8 syntax error in {fname}: {comp}",
                        )

                    # Mount simulated chrome.runtime + fetch bridge, run background.js + content.js,
                    # verify default mode is 'all' with ['all', 'holidays', 'date'] options only,
                    # and trigger a full-year batch upload through chrome.runtime.sendMessage -> background.js -> /api/v1/elal-bonus/sync!
                    setup_expr = """
                    (() => {
                      const listeners = [];
                      let seq = 0;
                      const pending = new Map();
                      window.__lastFetchOpts = null;
                      window.__resolveExtFetch = (id, status, bodyTxt) => {
                        const p = pending.get(id);
                        if (!p) return;
                        pending.delete(id);
                        p.resolve(new Response(bodyTxt, { status, headers: { 'Content-Type': 'application/json' } }));
                      };
                      window.fetch = (url, opts) => {
                        window.__lastFetchOpts = { url: String(url), credentials: opts && opts.credentials, method: opts && opts.method };
                        const id = ++seq;
                        return new Promise((resolve, reject) => {
                          pending.set(id, { resolve, reject });
                          window.__extSyncBridge(JSON.stringify({ id, url: String(url), method: (opts && opts.method) || 'POST', body: (opts && opts.body) || null }));
                        });
                      };
                      window.chrome = {
                        runtime: {
                          onMessage: { addListener: (fn) => listeners.push(fn) },
                          sendMessage: (msg, cb) => {
                            for (const fn of listeners) {
                              fn(msg, {}, cb);
                            }
                          }
                        }
                      };
                      document.body.innerHTML = '<div id="elal-calc-mock"></div>';
                      return true;
                    })()
                    """
                    cdp_call("Runtime.evaluate", {"expression": setup_expr, "returnByValue": True})
                    ev_bg = cdp_call("Runtime.evaluate", {"expression": bg_js_src})
                    self.assertNotIn("exceptionDetails", ev_bg.get("result", {}))
                    ev_ct = cdp_call("Runtime.evaluate", {"expression": content_js_src})
                    self.assertNotIn("exceptionDetails", ev_ct.get("result", {}))

                    dom_info = cdp_call(
                        "Runtime.evaluate",
                        {
                            "expression": """(() => {
                              const modeSel = document.getElementById('fvp-mode-select');
                              const shardSel = document.getElementById('fvp-shard-select');
                              const widget = document.getElementById('fvp-sync-widget');
                              return {
                                hasWidget: Boolean(widget),
                                hasOldShardSelect: Boolean(shardSel),
                                selectedMode: modeSel ? modeSel.value : null,
                                optionValues: modeSel ? Array.from(modeSel.options).map((o) => o.value) : [],
                                widgetText: widget ? widget.textContent : ''
                              };
                            })()""",
                            "returnByValue": True,
                        },
                    )["result"]["result"]["value"]

                    self.assertTrue(dom_info["hasWidget"])
                    self.assertFalse(dom_info["hasOldShardSelect"])
                    self.assertEqual(dom_info["selectedMode"], "all")
                    self.assertEqual(dom_info["optionValues"], ["all", "holidays", "date"])
                    self.assertNotIn("5 חלקים", dom_info["widgetText"])
                    self.assertNotIn("shard", dom_info["widgetText"].lower())

                    # Send simulated full-year rows through chrome.runtime.sendMessage -> background.js -> backend
                    sim_sync_expr = """
                    new Promise((resolve) => {
                      const rows = [];
                      const months = ['2027-01', '2027-02', '2027-03', '2027-04', '2027-05', '2027-06'];
                      const dests = ['FCO', 'ATH', 'VIE'];
                      months.forEach((ym) => {
                        ['05', '10', '15', '20'].forEach((dd, di) => {
                          const dest = dests[di % dests.length];
                          rows.push({
                            destination_iata: dest,
                            direction: 'OUTBOUND',
                            flight_number: 'LY3' + String(10 + di),
                            flight_date: ym + '-' + dd,
                            economy_seats: '2+',
                            premium_seats: 1
                          });
                        });
                      });
                      window.chrome.runtime.sendMessage(
                        {
                          action: 'SYNC_ELAL_ROWS',
                          serverUrl: 'https://breezyflights.com',
                          rows: rows,
                          reconcileSlices: [
                            { destinations: dests, start_date: '2027-01-01', end_date: '2027-06-30', cabins: ['E', 'A'] }
                          ]
                        },
                        (resp) => resolve({ resp, fetchOpts: window.__lastFetchOpts })
                      );
                    })
                    """
                    sim_out = cdp_call(
                        "Runtime.evaluate",
                        {
                            "expression": sim_sync_expr,
                            "awaitPromise": True,
                            "returnByValue": True,
                        },
                    )["result"]["result"]["value"]
                    self.assertTrue(sim_out["resp"]["ok"], sim_out)
                    self.assertEqual(sim_out["resp"]["records_synced"], 24)
                    self.assertEqual(sim_out["fetchOpts"]["credentials"], "omit")

                    post_ext_diag = repo.get_bonus_sync_diagnostics()
                    self.assertEqual(post_ext_diag["health_state"], "HEALTHY")
                    self.assertGreaterEqual(post_ext_diag["covered_periods_count"], 6)
                finally:
                    if sock is not None:
                        try:
                            sock.close()
                        except Exception:
                            pass
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=3.0)
                    except Exception:
                        pass
                    shutil.rmtree(chrome_udir, ignore_errors=True)
                repo.close()


if __name__ == "__main__":
    unittest.main()
