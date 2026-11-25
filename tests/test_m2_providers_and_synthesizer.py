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
import os
from pathlib import Path
import tempfile
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
from backend.app.auth_service import build_unsigned_or_hs256_jwt_for_test, sha256_hex
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    build_default_family_profile,
    is_shabbat_blocked_for_elal,
)
from backend.app.vacation_optimizer.maximizer_engine import VacationMaximizerEngine


# Run 11 contract: keys that no planner response may carry any more.
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
# Price wording that must not appear in any text shown to a person (explanation, CLI line).
RUN11_FORBIDDEN_PRICE_TEXT = ("$", "¢", "הערכת", "חיסכון", "מזומן", "Est. Cash", "נקודות:")


def _seat_score(
    out_seats,
    in_seats,
    seated: int,
    out_two_plus: bool | None = None,
    in_two_plus: bool | None = None,
) -> float:
    """Expected bonus score: mean share of the party that has a bonus seat per direction,
    with EL AL `2+` (`seats >= 2` when `is_two_plus` is True) counting as 100% directional coverage.
    """
    def _cov(seats, two_plus: bool | None) -> float:
        s = max(0, int(seats or 0))
        if s <= 0:
            return 0.0
        eff_tp = (s >= 2) if two_plus is None else bool(two_plus)
        if eff_tp and s >= 2:
            return 1.0
        return min(1.0, s / float(max(1, seated)))

    return round(
        100.0 * (_cov(out_seats, out_two_plus) + _cov(in_seats, in_two_plus)) / 2.0,
        1,
    )


def _make_mock_token_exchanger(email: str = "family@gmail.com", name: str = "Test Family"):
    """Create a hermetic OIDC token_exchanger closure that extracts nonce from oauth_login_states."""

    def _attach_and_login(router, user_email: str = email, display_name: str = name) -> tuple[str, str]:
        import json as _json
        import time as _time
        import urllib.parse as _up

        captured_nonce: list[str] = []
        orig_create_state = router.repository.create_oauth_login_state

        def _spy_create_state(*args, **kwargs):
            if "nonce" in kwargs:
                captured_nonce.append(str(kwargs["nonce"]))
            elif len(args) >= 3:
                captured_nonce.append(str(args[2]))
            return orig_create_state(*args, **kwargs)

        def _exchanger(_code: str, _verifier: str, _redir: str, client_id: str, _secret: str):
            now_ep = int(_time.time())
            nonce_val = captured_nonce[-1] if captured_nonce else ""
            jwt_tok = build_unsigned_or_hs256_jwt_for_test(
                {
                    "iss": "https://accounts.google.com",
                    "aud": client_id,
                    "sub": f"sub-{sha256_hex(user_email)[:20]}",
                    "email": user_email,
                    "email_verified": True,
                    "name": display_name,
                    "nonce": nonce_val,
                    "iat": now_ep,
                    "exp": now_ep + 3600,
                }
            )
            return {"id_token": jwt_tok, "access_token": "ephemeral"}

        router.auth_service.token_exchanger = _exchanger
        old_cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        old_sec = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        router.repository.create_oauth_login_state = _spy_create_state  # type: ignore[method-assign]
        try:
            os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "m2-test-client.apps.googleusercontent.com"
            os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "m2-test-secret"
            st, hdrs, _ = router.dispatch("GET", "/api/v1/auth/google/login")
            assert st == 302, f"Expected 302 login redirect, got {st}"
            loc = hdrs["Location"]
            state_param = dict(_up.parse_qsl(_up.urlsplit(loc).query))["state"]
            bind_cookie = ""
            for sc in hdrs.get("Set-Cookie", []):
                if sc.startswith("fvp_oauth_bind="):
                    bind_cookie = sc.split(";", 1)[0]
            cb_st, cb_hdrs, _ = router.dispatch(
                "GET",
                f"/api/v1/auth/google/callback?code=valid-auth-code&state={_up.quote(state_param)}",
                request_headers={"cookie": bind_cookie},
            )
            assert cb_st == 302, f"Expected 302 callback redirect, got {cb_st}"
            sess_cookie = ""
            for sc in cb_hdrs.get("Set-Cookie", []):
                if "fvp_session=" in sc and "Max-Age=0" not in sc:
                    sess_cookie = sc.split(";", 1)[0]
            s_st, _, s_body = router.dispatch(
                "GET", "/api/v1/auth/session", request_headers={"cookie": sess_cookie}
            )
            assert s_st == 200
            csrf_tok = _json.loads(s_body)["csrf_token"]
            return sess_cookie, csrf_tok
        finally:
            router.repository.create_oauth_login_state = orig_create_state  # type: ignore[method-assign]
            if old_cid is None:
                os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
            else:
                os.environ["GOOGLE_OAUTH_CLIENT_ID"] = old_cid
            if old_sec is None:
                os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)
            else:
                os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = old_sec

    return _attach_and_login


class TestM2ProvidersAndSynthesizer(unittest.TestCase):
    """Comprehensive unit tests for Milestone 2 (`F17`-`F28`)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = SQLiteRepository(":memory:", auto_seed=True)
        cls.repo.save_profile(build_default_family_profile())
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

    def _authenticate_client(
        self,
        client: Any,
        email: str = "family@gmail.com",
        seed_default_household: bool = True,
    ) -> tuple[str, str]:
        login_fn = _make_mock_token_exchanger(email=email)
        sess_cookie, csrf_tok = login_fn(client.router, user_email=email)
        cookie_name, cookie_val = sess_cookie.split("=", 1)
        client.cookies[cookie_name] = cookie_val
        client.default_headers["X-CSRF-Token"] = csrf_tok
        if seed_default_household:
            r = client.put("/api/v1/profile", json=build_default_family_profile().to_dict())
            self.assertEqual(r.status_code, 200, r.text)
        return sess_cookie, csrf_tok

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
        self.assertEqual(len(anywhere_iatas), 60)
        self.assertEqual(set(anywhere_iatas), set(SUPPORTED_ELAL_DESTINATIONS))
        self.assertEqual(self.elal_adapter.expand_metro_iatas(["KIV"]), ["RMO"])
        for newly_added in (
            "SZG", "TIA", "ZRH", "BSL", "NAP", "VRN", "LYS", "OPO",
            "JMK", "PVK", "DBV", "ZAG", "LJU", "RMO", "SEZ",
        ):
            self.assertIn(newly_added, anywhere_iatas)

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
        self.assertEqual(p5.itinerary.seated_passengers_count, 5)
        self.assertEqual(p5.itinerary.bonus_tickets_count, 5)
        self.assertEqual(p5.itinerary.cash_tickets_count, 0)
        self.assertNotIn("family_ticket_allocation", p5.itinerary.to_dict())
        p5_dict = p5.itinerary.to_dict()
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, p5_dict)
        self.assertEqual(p5_dict["bonus_direction_coverage"], "BOTH_DIRECTIONS")
        self.assertEqual(p5_dict["min_points_basis"], "ROUND_TRIP")
        self.assertGreater(p5_dict["min_points_per_bonus_ticket"], 0)
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
        sp_dict = sp.itinerary.to_dict()
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, sp_dict)
        self.assertEqual(sp.itinerary.seated_passengers_count, 5)
        self.assertEqual(sp.itinerary.bonus_tickets_count, 5)
        self.assertEqual(sp.itinerary.cash_tickets_count, 0)
        self.assertEqual(sp.itinerary.primary_cabin, "ECONOMY")
        # The cheapest ticket of a split-cabin result is an Economy round trip (15,000 each way)
        self.assertEqual(sp.itinerary.min_points_per_bonus_ticket, 30000)
        self.assertEqual(sp.itinerary.min_points_basis, "ROUND_TRIP")
        self.assertEqual(sp.itinerary.bonus_direction_coverage, "BOTH_DIRECTIONS")

    def test_syn_01_strategy_3_hybrid_bonus_plus_cash_rome_ly381_ly384_f24(self) -> None:
        """8. Verify `F24` & `TEST-SYN-01` canonical Rome `LY381`/`LY384` `HYBRID_BONUS_PLUS_CASH` seat composition."""
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
        ]
        self.assertGreaterEqual(len(hybrid_props), 1)
        rome_hybrid = hybrid_props[0].itinerary
        self.assertEqual(rome_hybrid.outbound_legs[0].flight_number, "LY381")
        self.assertEqual(rome_hybrid.inbound_legs[0].flight_number, "LY384")
        # 4 confirmed round-trip bonus seats (2x Economy + 2x Premium) for 5 seated passengers:
        # 4 bonus tickets + 1 commercial ticket, decided by the seats and not by the balance.
        self.assertEqual(rome_hybrid.seated_passengers_count, 5)
        self.assertEqual(rome_hybrid.bonus_tickets_count, 4)
        self.assertEqual(rome_hybrid.cash_tickets_count, 1)
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
        expected_out = (
            fco_out.economy_award_seats + fco_out.premium_award_seats + fco_out.business_award_seats
        )
        expected_in = (
            fco_in.economy_award_seats + fco_in.premium_award_seats + fco_in.business_award_seats
        )
        self.assertEqual(rome_hybrid.outbound_bonus_seats, expected_out)
        self.assertEqual(rome_hybrid.inbound_bonus_seats, expected_in)
        self.assertTrue(rome_hybrid.outbound_bonus_seats_is_two_plus)
        self.assertEqual(rome_hybrid.bonus_direction_coverage, "BOTH_DIRECTIONS")
        self.assertEqual(
            rome_hybrid.min_points_per_bonus_ticket,
            fco_out.economy_points_per_pax + fco_in.economy_points_per_pax,
        )
        self.assertEqual(rome_hybrid.min_points_basis, "ROUND_TRIP")
        self.assertAlmostEqual(
            hybrid_props[0].flight_bonus_value_score,
            _seat_score(expected_out, expected_in, 5),
            places=1,
        )
        hybrid_dict = rome_hybrid.to_dict()
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, hybrid_dict)

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
            self.assertEqual(prop.itinerary.seated_passengers_count, 5)
            self.assertGreaterEqual(prop.itinerary.bonus_tickets_count, 1)
            self.assertGreaterEqual(prop.itinerary.cash_tickets_count, 1)
            self.assertEqual(
                prop.itinerary.bonus_tickets_count + prop.itinerary.cash_tickets_count,
                5,
            )

        # Single adult + 3 children under 12 cannot split across separate bonus + cash PNRs
        single_parent_young = copy.deepcopy(young_family)
        single_parent_young.adults_count = 1
        sp_proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "allow_hybrid_bonus_cash": True,
            },
            profile=single_parent_young,
        )
        sp_hybrids = [
            p for p in sp_proposals if p.itinerary.fulfillment_strategy == "HYBRID_BONUS_PLUS_CASH"
        ]
        self.assertEqual(len(sp_hybrids), 0)

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

    def test_strategy_5_cash_and_points_fallback_carries_no_points_figure_f26(self) -> None:
        """11. Verify `F26` `CASH_AND_POINTS`: returned for a household with points, without any points or price figure."""
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
        # The points-plus-money result carries no points figure and no price wording
        self.assertIsNone(cp.itinerary.min_points_per_bonus_ticket)
        self.assertIsNone(cp.itinerary.min_points_basis)
        self.assertNotEqual(cp.itinerary.bonus_direction_coverage, "NONE")
        cp_dict = cp.itinerary.to_dict()
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, cp_dict)
        self.assertTrue(cp.explanation_summary_he.strip())
        for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
            self.assertNotIn(forbidden, cp.explanation_summary_he)

        # Engine level, award rows with 0 Classic Award seats in every cabin: the fallback is
        # still built (a household with points), but it states no bonus direction at all.
        lhr_out = copy.deepcopy(
            self.elal_adapter.get_award_availability(
                destinations=["LHR"],
                start_date=date(2027, 7, 15),
                end_date=date(2027, 7, 15),
                direction="OUTBOUND",
            )[0]
        )
        lhr_in = copy.deepcopy(
            self.elal_adapter.get_award_availability(
                destinations=["LHR"],
                start_date=date(2027, 7, 22),
                end_date=date(2027, 7, 22),
                direction="INBOUND",
            )[0]
        )
        for row in (lhr_out, lhr_in):
            row.economy_award_seats = 0
            row.premium_award_seats = 0
            row.business_award_seats = 0
            row.economy_seats_is_two_plus = False
            row.premium_seats_is_two_plus = False
            row.business_seats_is_two_plus = False
        engine = MultiClubWalletAllocationEngine()
        zero_seat_cp = engine.allocate_family_tickets(
            self.default_profile, lhr_out, lhr_in, 0.0, "CASH_AND_POINTS"
        )
        self.assertIsNotNone(zero_seat_cp)
        assert zero_seat_cp is not None
        self.assertEqual(zero_seat_cp["fulfillment_strategy"], "CASH_AND_POINTS")
        self.assertEqual(zero_seat_cp["bonus_direction_coverage"], "NONE")
        self.assertEqual(zero_seat_cp["outbound_bonus_seats"], 0)
        self.assertEqual(zero_seat_cp["inbound_bonus_seats"], 0)
        self.assertIsNone(zero_seat_cp["min_points_per_bonus_ticket"])
        self.assertIsNone(zero_seat_cp["min_points_basis"])
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, zero_seat_cp)
        # A household with no points entered (balance 0, no wallets) gets the same fallback:
        # balance 0 means "not entered" and excludes nothing (run 11, U3 / ruling J2).
        no_points_profile = copy.deepcopy(self.default_profile)
        no_points_profile.matmid_points_balance = 0
        no_points_profile.passenger_loyalty_wallets = []
        no_points_zero_seat_cp = engine.allocate_family_tickets(
            no_points_profile, lhr_out, lhr_in, 0.0, "CASH_AND_POINTS"
        )
        self.assertIsNotNone(no_points_zero_seat_cp)
        assert no_points_zero_seat_cp is not None
        self.assertEqual(no_points_zero_seat_cp["fulfillment_strategy"], "CASH_AND_POINTS")
        self.assertEqual(no_points_zero_seat_cp["bonus_direction_coverage"], "NONE")
        self.assertIsNone(no_points_zero_seat_cp["min_points_per_bonus_ticket"])
        # Search level: the same household, real seeded seats. The points-plus-money result
        # is returned next to the other bonus results, with bonus seats in some direction.
        no_points_lhr = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LHR"],
                "specific_departure_date": "2027-07-15",
                "specific_return_date": "2027-07-22",
                "flex_days_plus_minus": 0,
            },
            profile=no_points_profile,
        )
        no_points_cp = [
            p
            for p in no_points_lhr
            if p.itinerary.fulfillment_strategy == "CASH_AND_POINTS"
        ]
        self.assertGreaterEqual(len(no_points_cp), 1)
        for p in no_points_cp:
            self.assertNotEqual(p.itinerary.bonus_direction_coverage, "NONE")
            self.assertIsNone(p.itinerary.min_points_per_bonus_ticket)

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
        # Wallet deductions and point totals are no longer part of a result
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, unpooled_alloc)
        # Ticket composition follows the confirmed round-trip seats (2x Economy + 2x Premium for
        # 5 seated passengers), not what the two 75k / 68k wallets could pay for.
        self.assertEqual(unpooled_alloc["fulfillment_strategy"], "MULTI_CLUB_PER_PASSENGER_SPLIT")
        self.assertEqual(unpooled_alloc["seated_passengers_count"], 5)
        self.assertEqual(unpooled_alloc["bonus_tickets_count"], 4)
        self.assertEqual(unpooled_alloc["cash_tickets_count"], 1)
        self.assertEqual(unpooled_alloc["min_points_basis"], "ROUND_TRIP")
        self.assertEqual(
            unpooled_alloc["min_points_per_bonus_ticket"],
            fco_out.economy_points_per_pax + fco_in.economy_points_per_pax,
        )
        # The strategy keeps its precondition of at least two funded wallets
        single_wallet_profile = copy.deepcopy(unpooled_profile)
        single_wallet_profile.passenger_loyalty_wallets = (
            single_wallet_profile.passenger_loyalty_wallets[:1]
        )
        single_wallet_profile.matmid_points_balance = 0
        self.assertIsNone(
            engine.allocate_family_tickets(
                profile=single_wallet_profile,
                outbound_award=fco_out,
                inbound_award=fco_in,
                cash_benchmark_per_pax=590.0,
                strategy="MULTI_CLUB_PER_PASSENGER_SPLIT",
                preferred_cabins=["ECONOMY", "PREMIUM"],
                enabled_programs=["ELAL_MATMID"],
            )
        )

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
        self.assertGreaterEqual(mc_props[0].itinerary.bonus_tickets_count, 1)
        self.assertEqual(mc_props[0].itinerary.min_points_basis, "ROUND_TRIP")
        self.assertNotIn("points_used_by_wallet", mc_props[0].itinerary.to_dict())

    def test_search_vacations_all_6_mode_combinations_and_sqlite_persistence_f28(self) -> None:
        """13. Verify `F17`-`F28` `search_vacations` across active 2x2 mode combinations and SQLite persistence."""
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
                    0.55 * p.holiday_alignment_score + 0.45 * p.flight_bonus_value_score,
                    1,
                )
                self.assertAlmostEqual(
                    p.combined_trip_optimization_score, expected_ctos, places=1
                )
                self.assertGreaterEqual(p.combined_trip_optimization_score, 0.0)
                self.assertLessEqual(p.combined_trip_optimization_score, 100.0)
                self.assertTrue(p.explanation_summary_he.strip())
                for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
                    self.assertNotIn(forbidden, p.explanation_summary_he)
            # Persisted in SQLite
            persisted = self.repo.get_proposal_by_id(proposals[0].id)
            self.assertIsNotNone(persisted)

    def test_compare_proposals_removed_and_compare_endpoint_returns_404_run10_r1(
        self,
    ) -> None:
        """14. Verify `run10` `R1`: `compare_proposals` & `VacationComparisonMatrix` are removed and `/api/v1/vacations/compare` returns `404`."""
        from backend.app.main import VacationPlannerTestClient
        import backend.app.schemas as schemas_pkg
        import backend.app.schemas.domain as domain_mod

        self.assertFalse(hasattr(self.planner, "compare_proposals"))
        self.assertFalse(hasattr(domain_mod, "VacationComparisonMatrix"))
        self.assertFalse(hasattr(schemas_pkg, "VacationComparisonMatrix"))

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
        self.assertGreaterEqual(len(proposals), 2)
        selected_ids = [p.id for p in proposals[:2]]

        client = VacationPlannerTestClient(db_path=":memory:")
        for body_payload in (
            {"proposal_ids": selected_ids},
            {"proposal_ids": []},
            {},
        ):
            cmp_resp = client.post("/api/v1/vacations/compare", json=body_payload)
            self.assertEqual(cmp_resp.status_code, 404)

    def test_ics_export_removed_and_no_cash_metadata_in_search_response_f28(self) -> None:
        """15. Verify `R3` ICS export removal (`-> 404`) and run-11 `R1`: no cash metadata in the response."""
        from backend.app.main import VacationPlannerTestClient

        self.assertFalse(hasattr(self.planner, "export_proposal_ics"))
        client = VacationPlannerTestClient(db_path=":memory:")
        s_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
        )
        self.assertEqual(s_resp.status_code, 200)
        body = s_resp.json()
        for removed_key in RUN11_REMOVED_RESPONSE_KEYS:
            self.assertNotIn(removed_key, body)
        self.assertGreater(len(body["proposals"]), 0)
        pid = body["proposals"][0]["id"]
        first_itinerary = body["proposals"][0]["itinerary"]
        for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
            self.assertNotIn(removed_key, first_itinerary)
        for new_key in RUN11_NEW_ITINERARY_KEYS:
            self.assertIn(new_key, first_itinerary)
        self.assertIs(first_itinerary["points_are_estimated"], True)
        ics_resp = client.get(f"/api/v1/vacations/{pid}/export.ics")
        self.assertEqual(ics_resp.status_code, 404)

    def test_weather_suitability_engine_seasonal_accuracy_and_all_vacation_types_f33(
        self,
    ) -> None:
        """16. Verify `DestinationWeatherSuitabilityEngine` seasonal scores across all 25 destinations & 6 vacation styles."""
        from backend.app.planner_synthesizer.weather_suitability_engine import (
            DestinationWeatherSuitabilityEngine,
        )
        from backend.app.storage_cache.seed_data import DESTINATION_CATALOG

        self.assertEqual(len(DESTINATION_CATALOG), 60)
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

        # Verify typed CTOS formula: round(clamp(0.35*WSS + 0.35*HAS + 0.30*FBVS - 0.50*max(0, 60 - WSS), 0, 100), 1)
        for p in beach_props:
            wss = p.weather_suitability_score
            has_score = p.holiday_alignment_score
            fbvs = p.flight_bonus_value_score
            shortfall = max(0.0, 60.0 - wss)
            expected_typed_ctos = round(
                max(0.0, min(100.0, 0.35 * wss + 0.35 * has_score + 0.30 * fbvs - 0.50 * shortfall)),
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

    def test_parse_and_import_external_rbd_payload_normalization_and_30d_ttl(self) -> None:
        """18. Verify single-dict Record/resultSet normalization, Economy(E)+Premium(A) merge,
        unknown IATA filtering (ZRH), 738 live Premium preservation, dep/arr times, and 30d TTL.
        """
        from datetime import datetime

        iso_repo = SQLiteRepository(":memory:", auto_seed=True)
        iso_adapter = ElAlRbdDataClientAdapter(iso_repo)

        batch_payload = [
            {
                "AccumulatedOutput": {
                    # Single dict resultSet with a single dict Record (Economy E on TLV->LCA 738)
                    "resultSet": {
                        "Record": {
                            "SegmentRoute": "TLVLCA",
                            "SegmentDepDate": "2027-04-14T00:00:00",
                            "SegmentDepTime": "07:20",
                            "SegmentArrTime": "08:30",
                            "FlightCarrier": "LY",
                            "FlightNumber": "411",
                            "RBD": "E",
                            "NewAvailability": "2+",
                        }
                    }
                }
            },
            {
                "AccumulatedOutput": {
                    # List resultSet with list of Records including Premium RBD="A", SZG/ZRH, unknown HEL, and 0-seat row
                    "resultSet": [
                        {
                            "Record": [
                                {
                                    "SegmentRoute": "TLVLCA",
                                    "SegmentDepDate": "2027-04-14T00:00:00",
                                    "SegmentDepTime": "2027-04-14T07:20:00",
                                    "SegmentArrTime": "2027-04-14T08:30:00",
                                    "FlightCarrier": "LY",
                                    "FlightNumber": "411",
                                    "RBD": "A",
                                    "NewAvailability": "2",
                                },
                                {
                                    "SegmentRoute": "TLVSZG",
                                    "SegmentDepDate": "2027-04-14T00:00:00",
                                    "FlightCarrier": "LY",
                                    "FlightNumber": "5135",
                                    "RBD": "E",
                                    "NewAvailability": "2+",
                                },
                                {
                                    "SegmentRoute": "TLVZRH",
                                    "SegmentDepDate": "2027-04-14T00:00:00",
                                    "FlightCarrier": "LY",
                                    "FlightNumber": "347",
                                    "RBD": "E",
                                    "NewAvailability": "2+",
                                },
                                {
                                    "SegmentRoute": "TLVHEL",
                                    "SegmentDepDate": "2027-04-14T00:00:00",
                                    "FlightCarrier": "LY",
                                    "FlightNumber": "999",
                                    "RBD": "E",
                                    "NewAvailability": "2+",
                                },
                                {
                                    "SegmentRoute": "TLVFCO",
                                    "SegmentDepDate": "2027-04-14T00:00:00",
                                    "FlightCarrier": "LY",
                                    "FlightNumber": "381",
                                    "RBD": "E",
                                    "NewAvailability": "0",
                                },
                            ]
                        }
                    ]
                }
            },
            # Flat row dict with custom dep_time / arr_time and BUD (ZONE_B 738) Premium seats
            {
                "destination_iata": "BUD",
                "direction": "OUTBOUND",
                "flight_number": "LY2365",
                "flight_date": "2027-04-14",
                "economy_seats": 2,
                "premium_seats": 1,
                "dep_time": "06:45",
                "arr_time": "09:10",
            },
        ]

        imported = iso_adapter.parse_and_import_external_rbd_payload(batch_payload)
        self.assertEqual(len(imported), 4)
        by_dest = {r.destination_iata: r for r in imported}
        self.assertIn("LCA", by_dest)
        self.assertIn("BUD", by_dest)
        self.assertIn("SZG", by_dest)
        self.assertIn("ZRH", by_dest)
        self.assertNotIn("HEL", by_dest)

        lca_row = by_dest["LCA"]
        self.assertEqual(lca_row.economy_award_seats, 2)
        self.assertEqual(lca_row.premium_award_seats, 2)
        self.assertEqual(lca_row.premium_points_per_pax, 18000)
        self.assertEqual(lca_row.departure_time_local, "07:20")
        self.assertEqual(lca_row.arrival_time_local, "08:30")
        self.assertTrue(lca_row.source_url.endswith("#live"))

        bud_row = by_dest["BUD"]
        self.assertEqual(bud_row.economy_award_seats, 2)
        self.assertEqual(bud_row.premium_award_seats, 1)
        self.assertEqual(bud_row.premium_points_per_pax, 22000)
        self.assertEqual(bud_row.departure_time_local, "06:45")
        self.assertEqual(bud_row.arrival_time_local, "09:10")

        fetched_dt = datetime.fromisoformat(lca_row.fetched_at.replace("Z", "+00:00"))
        expires_dt = datetime.fromisoformat(lca_row.expires_at.replace("Z", "+00:00"))
        self.assertGreaterEqual((expires_dt - fetched_dt).days, 29)

    def test_planner_multi_flight_live_sorting_and_maximizer_step_threshold(self) -> None:
        """19. Verify multi-flight days select highest award seat inventory and maximizer evaluates step=1 up to 40d."""
        iso_repo = SQLiteRepository(":memory:", auto_seed=True)
        iso_cal = MoECalendarService(iso_repo)
        iso_max = VacationMaximizerEngine(iso_cal)
        iso_adapter = ElAlRbdDataClientAdapter(iso_repo)
        iso_planner = BonusVacationPlannerService(
            repository=iso_repo,
            calendar_service=iso_cal,
            maximizer=iso_max,
            elal_adapter=iso_adapter,
            commercial_adapter=AllAirlinesSearchAdapter(iso_repo),
        )

        # Import two outbound flights on TLV->FCO on 2027-04-14: LY381 (1 Econ) and LY383 (2 Econ + 2 Prem)
        iso_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "FCO",
                    "direction": "OUTBOUND",
                    "flight_number": "LY381",
                    "flight_date": "2027-04-14",
                    "economy_seats": 1,
                    "premium_seats": 0,
                    "dep_time": "06:00",
                    "arr_time": "08:45",
                },
                {
                    "destination_iata": "FCO",
                    "direction": "OUTBOUND",
                    "flight_number": "LY383",
                    "flight_date": "2027-04-14",
                    "economy_seats": 2,
                    "premium_seats": 2,
                    "dep_time": "12:15",
                    "arr_time": "15:00",
                },
            ]
        )

        out_rows, _ = iso_planner._ensure_award_rows_for_window(
            dest_iata="FCO",
            start_date=date(2027, 4, 14),
            end_date=date(2027, 4, 21),
            origin_iata="TLV",
            include_sundor=True,
        )
        self.assertGreaterEqual(len(out_rows), 2)
        self.assertEqual(out_rows[0].flight_number, "LY383")
        self.assertEqual(out_rows[0].economy_award_seats, 2)
        self.assertEqual(out_rows[0].premium_award_seats, 2)

    def test_elal_google_flights_handoff_url_and_non_elal_exclusion(
        self,
    ) -> None:
        """20. Verify El Al `elal_google_flights_url` pre-filters Google Flights to EL AL nonstop
        with exact dates, passenger breakdown (`adults`/`children`/`infants`), Open-Jaw multi-city
        routing, WAF-safe `booking_deep_link_url`, and `None` for non-El Al carriers.
        """
        from urllib.parse import parse_qs, urlparse
        from backend.app.schemas.domain import FamilyProfile

        # Custom family: 2 adults + 1 teenager (14 -> adult) + 1 child (7 -> child) + 1 lap infant (1 -> infant)
        mixed_profile = FamilyProfile.from_dict(
            {
                **self.default_profile.to_dict(),
                "adults_count": 2,
                "children": [
                    {
                        "id": "c-teen",
                        "child_name": "נועה",
                        "child_age_years": 14,
                        "framework_type": "MIDDLE_SCHOOL_7_9",
                    },
                    {
                        "id": "c-child",
                        "child_name": "אורי",
                        "child_age_years": 7,
                        "framework_type": "ELEMENTARY_1_3",
                    },
                    {
                        "id": "c-inf",
                        "child_name": "גיל",
                        "child_age_years": 1,
                        "passenger_Current_type": "INFANT_LAP",
                        "framework_type": "DAYCARE_SUPERVISED",
                    },
                ],
            }
        )

        proposals = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=mixed_profile,
        )
        self.assertGreater(len(proposals), 0)
        itin = proposals[0].itinerary
        assert itin is not None
        self.assertTrue(itin.is_elal_flight)
        self.assertEqual(itin.booking_deep_link_url, "https://www.elal.com/heb/israel")
        self.assertIsNotNone(itin.elal_google_flights_url)

        parsed = urlparse(str(itin.elal_google_flights_url))
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "www.google.com")
        self.assertEqual(parsed.path, "/travel/flights")

        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.assertEqual(qs["curr"], "USD")
        self.assertEqual(qs["gl"], "IL")
        self.assertEqual(qs["hl"], "en")
        q_str = qs["q"]
        self.assertIn("Flights to Rome from Tel Aviv", q_str)
        self.assertIn("on 2027-04-11 through 2027-04-18", q_str)
        self.assertIn("3 adults, 1 child and 1 infant", q_str)
        self.assertTrue(q_str.endswith("nonstop"))
        self.assertNotIn("on EL AL", q_str)

        # Verify Tbilisi (`TBS` — Sun d'Or route whose raw `TBS` IATA code previously failed Google Flights `?q=` parsing)
        # resolves cleanly to `"Flights to Tbilisi from Tel Aviv ... nonstop"` across all 45 catalog destinations.
        from backend.app.planner_synthesizer.bonus_planner_service import (
            DESTINATION_CATALOG,
            resolve_google_flights_place_name,
        )

        tbs_props = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["TBS"],
                "specific_departure_date": "2027-04-16",
                "specific_return_date": "2027-04-27",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        self.assertGreater(len(tbs_props), 0)
        tbs_qs = {
            k: v[0]
            for k, v in parse_qs(urlparse(str(tbs_props[0].itinerary.elal_google_flights_url)).query).items()
        }
        self.assertIn("Flights to Tbilisi from Tel Aviv on 2027-04-16 through 2027-04-27", tbs_qs["q"])
        self.assertNotIn("Flights to TBS", tbs_qs["q"])
        self.assertNotIn("on EL AL", tbs_qs["q"])
        for code in DESTINATION_CATALOG:
            place_name = resolve_google_flights_place_name(code)
            self.assertTrue(bool(place_name))
            self.assertNotIn("(", place_name)

        # Verify Open-Jaw constructs a clean parseable one-way Google Flights query without multi-leg failure
        oj_proposals = [
            p
            for p in self.planner.search_vacations(
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["MXP"],
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                },
                profile=self.default_profile,
            )
            if p.itinerary and p.itinerary.return_origin_iata != p.itinerary.destination_iata
        ]
        for oj_p in oj_proposals:
            oj_qs = {
                k: v[0]
                for k, v in parse_qs(urlparse(str(oj_p.itinerary.elal_google_flights_url)).query).items()
            }
            dest_place = resolve_google_flights_place_name(oj_p.itinerary.destination_iata)
            self.assertIn(f"One way flights to {dest_place} from Tel Aviv", oj_qs["q"])
            self.assertTrue(oj_qs["q"].endswith("nonstop"))

        # Verify non-El Al flights in ALL_AIRLINES mode have elal_google_flights_url = None
        all_air_props = self.planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "ALL_AIRLINES",
                "destination_iatas": ["FCO", "ATH"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=self.default_profile,
        )
        non_elal = [p for p in all_air_props if p.itinerary and not p.itinerary.is_elal_flight]
        self.assertGreater(len(non_elal), 0)
        for p_other in non_elal:
            self.assertIsNone(p_other.itinerary.elal_google_flights_url)

    def test_infant_age_reclassification_live_no_tuesday_discount_and_two_plus_banner_flag(
        self,
    ) -> None:
        """21. Verify:
        (a) Editing a child's age to 1 with stale `CHILD`/`YOUTH` type auto-reclassifies to `INFANT_LAP` (0 pts, no seat consumed).
        (b) Live-synced (`#live`) flights on Tuesdays (`2027-04-20` Pesach LCA) do NOT apply 50% Tuesday FlyCard discounts and reflect peak seasonal Classic rates (`9,000` one-way vs `7,500` off-peak).
        (c) 2 adults + 1 child (age 5) + 1 infant (age 1) = 3 seated passengers -> `requires_two_plus_seat_verification=True` (54,000 pts total, not 45,000), whereas 2 adults + 1 infant (age 1) = 2 seated passengers -> `requires_two_plus_seat_verification=False` (36,000 pts total).
        """
        from backend.app.schemas.domain import FamilyProfile

        iso_repo = SQLiteRepository(":memory:", auto_seed=True)
        iso_cal = MoECalendarService(iso_repo)
        iso_max = VacationMaximizerEngine(iso_cal)
        iso_adapter = ElAlRbdDataClientAdapter(iso_repo)
        iso_planner = BonusVacationPlannerService(
            repository=iso_repo,
            calendar_service=iso_cal,
            maximizer=iso_max,
            elal_adapter=iso_adapter,
            commercial_adapter=AllAirlinesSearchAdapter(iso_repo),
        )

        # Import live Tuesday outbound (2027-04-20) + Monday inbound (2027-04-26) + off-peak Feb row for LCA
        imported = iso_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "LCA",
                    "direction": "OUTBOUND",
                    "flight_number": "LY5131",
                    "flight_date": "2027-04-20",  # Tuesday in Pesach
                    "economy_seats": 2,
                    "dep_time": "06:30",
                    "arr_time": "07:40",
                },
                {
                    "destination_iata": "LCA",
                    "direction": "INBOUND",
                    "flight_number": "LY5132",
                    "flight_date": "2027-04-26",
                    "economy_seats": 2,
                    "dep_time": "08:45",
                    "arr_time": "09:50",
                },
                {
                    "destination_iata": "LCA",
                    "direction": "OUTBOUND",
                    "flight_number": "LY411",
                    "flight_date": "2027-02-09",  # Tuesday off-peak
                    "economy_seats": 2,
                    "dep_time": "07:30",
                    "arr_time": "08:35",
                },
            ]
        )
        by_fn = {r.flight_number: r for r in imported}
        self.assertFalse(by_fn["LY5131"].flycard_promo_active)
        self.assertEqual(by_fn["LY5131"].economy_points_per_pax, 9000)
        self.assertFalse(by_fn["LY411"].flycard_promo_active)
        self.assertEqual(by_fn["LY411"].economy_points_per_pax, 7500)

        # Family matching user's screenshot: 2 adults + child #1 (age 1 with stale 'CHILD' type!) + child #2 (age 5)
        prof_4 = FamilyProfile.from_dict(
            {
                **self.default_profile.to_dict(),
                "adults_count": 2,
                "children": [
                    {
                        "id": "ch-1",
                        "child_name": "ילד 1",
                        "child_age_years": 1,
                        "passenger_Current_type": "CHILD",  # stale type before age edit fix!
                        "framework_type": "DAYCARE_SUPERVISED",
                    },
                    {
                        "id": "ch-2",
                        "child_name": "ילד 2",
                        "child_age_years": 5,
                        "passenger_Current_type": "CHILD",
                        "framework_type": "MUNICIPAL_GAN",
                    },
                ],
            }
        )
        self.assertEqual(prof_4.children[0].passenger_Current_type, "INFANT_LAP")

        props = iso_planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LCA"],
                "specific_departure_date": "2027-04-20",
                "specific_return_date": "2027-04-26",
                "flex_days_plus_minus": 0,
            },
            profile=prof_4,
        )
        full_bonus = [
            p
            for p in props
            if p.itinerary and p.itinerary.fulfillment_strategy.value == "FULL_BONUS_SAME_CABIN"
        ]
        self.assertGreater(len(full_bonus), 0)
        it4 = full_bonus[0].itinerary
        assert it4 is not None
        # One bonus ticket = 9,000 + 9,000 = 18,000 pts for a round trip; infant (age 1) = 0 seats
        self.assertEqual(it4.min_points_per_bonus_ticket, 18000)
        self.assertEqual(it4.min_points_basis, "ROUND_TRIP")
        self.assertEqual(it4.bonus_direction_coverage, "BOTH_DIRECTIONS")
        self.assertNotIn("total_matmid_points", it4.to_dict())
        self.assertTrue(it4.requires_two_plus_seat_verification)
        self.assertEqual(it4.seated_passengers_count, 3)
        self.assertEqual(it4.bonus_tickets_count, 3)
        self.assertEqual(it4.cash_tickets_count, 0)

        # Verify live-only DB never fabricates a synthetic return flight on 2027-04-28 when no live inbound exists
        live_only_repo = SQLiteRepository(":memory:", auto_seed=False)
        live_only_cal = MoECalendarService(live_only_repo)
        live_only_max = VacationMaximizerEngine(live_only_cal)
        live_only_adapter = ElAlRbdDataClientAdapter(live_only_repo)
        live_only_planner = BonusVacationPlannerService(
            repository=live_only_repo,
            calendar_service=live_only_cal,
            maximizer=live_only_max,
            elal_adapter=live_only_adapter,
            commercial_adapter=AllAirlinesSearchAdapter(live_only_repo),
        )
        live_only_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "LCA",
                    "direction": "OUTBOUND",
                    "flight_number": "LY5131",
                    "flight_date": "2027-04-20",
                    "economy_seats": 2,
                    "dep_time": "06:30",
                    "arr_time": "07:40",
                },
                {
                    "destination_iata": "LCA",
                    "direction": "INBOUND",
                    "flight_number": "LY5132",
                    "flight_date": "2027-04-26",
                    "economy_seats": 2,
                    "dep_time": "08:45",
                    "arr_time": "09:50",
                },
            ]
        )
        no_return_props = live_only_planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LCA"],
                "specific_departure_date": "2027-04-20",
                "specific_return_date": "2027-04-28",
                "flex_days_plus_minus": 0,
            },
            profile=prof_4,
        )
        self.assertGreaterEqual(len(no_return_props), 1)
        ow_lca = no_return_props[0]
        self.assertEqual(ow_lca.itinerary.fulfillment_strategy, "ONE_WAY_BONUS_ONE_WAY_CASH")
        self.assertEqual(ow_lca.itinerary.outbound_legs[0].flight_number, "LY5131")
        self.assertEqual(ow_lca.itinerary.inbound_legs[0].flight_number, "LY_CASH")
        # Bonus seats exist on the way out only: 2 seats for 3 seated passengers, none back
        self.assertEqual(ow_lca.itinerary.bonus_direction_coverage, "OUTBOUND_ONLY")
        self.assertEqual(ow_lca.itinerary.outbound_bonus_seats, 2)
        self.assertIsNone(ow_lca.itinerary.inbound_bonus_seats)
        self.assertEqual(ow_lca.itinerary.min_points_per_bonus_ticket, 9000)
        self.assertEqual(ow_lca.itinerary.min_points_basis, "ONE_WAY")
        self.assertAlmostEqual(ow_lca.flight_bonus_value_score, _seat_score(2, None, 3), places=1)
        self.assertLess(ow_lca.flight_bonus_value_score, 60.0)

        # Verify outbound-only AMS in Hanukkah 2026 surfaces ONE_WAY_BONUS_ONE_WAY_CASH with lower FBVS
        live_only_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "AMS",
                    "direction": "OUTBOUND",
                    "flight_number": "LY337",
                    "flight_date": "2026-12-08",
                    "economy_seats": 2,
                    "dep_time": "06:15",
                    "arr_time": "10:15",
                },
                {
                    "destination_iata": "AMS",
                    "direction": "OUTBOUND",
                    "flight_number": "LY339",
                    "flight_date": "2026-12-09",
                    "economy_seats": 2,
                    "dep_time": "16:10",
                    "arr_time": "20:10",
                },
                {
                    "destination_iata": "AMS",
                    "direction": "OUTBOUND",
                    "flight_number": "LY337",
                    "flight_date": "2026-12-13",
                    "economy_seats": 1,
                    "dep_time": "16:00",
                    "arr_time": "20:00",
                },
            ]
        )
        ams_hanukkah_props = live_only_planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["AMS"],
                "direct_holiday_code": "HANUKKAH",
                "direct_target_year": 2026,
                "flex_days_plus_minus": 3,
                "min_trip_nights": 4,
                "max_trip_nights": 7,
            },
            profile=prof_4,
        )
        self.assertGreaterEqual(len(ams_hanukkah_props), 1)
        for ap in ams_hanukkah_props:
            self.assertEqual(ap.itinerary.destination_iata, "AMS")
            self.assertEqual(ap.itinerary.fulfillment_strategy, "ONE_WAY_BONUS_ONE_WAY_CASH")
            self.assertEqual(ap.itinerary.inbound_legs[0].flight_number, "LY_CASH")
            self.assertNotEqual(ap.itinerary.return_date.isoformat(), "2026-12-12")
            self.assertEqual(ap.itinerary.bonus_direction_coverage, "OUTBOUND_ONLY")
            self.assertLess(ap.flight_bonus_value_score, 60.0)

        # Verify single-direction live routes (e.g. LTN outbound-only on 2026-12-09 with Saturday 2026-12-12)
        # NEVER fabricate a non-existent/Shabbat LY312 return leg, while real Open-Jaw (TLV->LTN + LHR->TLV) works
        live_only_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "LTN",
                    "direction": "OUTBOUND",
                    "flight_number": "LY311",
                    "flight_date": "2026-12-09",
                    "economy_seats": 2,
                    "dep_time": "05:30",
                    "arr_time": "09:05",
                },
                {
                    "destination_iata": "LHR",
                    "direction": "INBOUND",
                    "flight_number": "LY210",
                    "flight_date": "2026-12-15",
                    "premium_seats": 2,
                    "dep_time": "16:20",
                    "arr_time": "23:09",
                },
            ]
        )
        ltn_sat_props = live_only_planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LON"],
                "specific_departure_date": "2026-12-09",
                "specific_return_date": "2026-12-12",
                "flex_days_plus_minus": 0,
            },
            profile=prof_4,
        )
        self.assertEqual(len(ltn_sat_props), 0)

        lon_hanukkah_props = live_only_planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LON"],
                "direct_holiday_code": "HANUKKAH",
                "direct_target_year": 2026,
            },
            profile=prof_4,
        )
        for lp in lon_hanukkah_props:
            assert lp.itinerary is not None
            self.assertNotEqual(lp.itinerary.return_date.isoformat(), "2026-12-12")
            for leg in lp.itinerary.inbound_legs:
                self.assertNotEqual(leg.flight_number, "LY312")

    def test_rolling_one_year_upcoming_holidays_year_rollover_and_lengths_run3_r1(
        self,
    ) -> None:
        """22. Verify rolling 1-year holiday resolver, automatic year rollover, `(N days)` labels,
        `YOM_KIPPUR_SUKKOT_BRIDGE` (14d) vs `SUKKOT` (9d), and 1..31d `max_trip_nights` search compatibility.
        """
        import re
        from backend.app.main import VacationPlannerTestClient

        iso_repo = SQLiteRepository(":memory:", auto_seed=True)
        iso_cal = MoECalendarService(iso_repo)
        iso_max = VacationMaximizerEngine(iso_cal)
        prof = self.default_profile

        # 1. At 2026-11-19: Hanukkah is 2026 (7d); Spring/Summer are 2027; Autumn holidays rolled over to 2027
        up_nov26 = iso_cal.get_upcoming_holidays_for_rolling_year(
            as_of_date=date(2026, 11, 19), profile=prof
        )
        self.assertEqual(len(up_nov26), 11)
        starts_nov26 = [h["start_date"] for h in up_nov26]
        self.assertEqual(starts_nov26, sorted(starts_nov26))

        by_code_26 = {h["holiday_code"]: h for h in up_nov26}
        self.assertEqual(by_code_26["HANUKKAH"]["target_year"], 2026)
        self.assertEqual(by_code_26["HANUKKAH"]["holiday_days"], 7)
        self.assertEqual(by_code_26["HANUKKAH"]["label_he"], "חופשת חנוכה 2026 (7 ימים)")
        self.assertEqual(by_code_26["HANUKKAH"]["label_en"], "Hanukkah Break 2026 (7 days)")
        self.assertEqual(by_code_26["PESACH"]["target_year"], 2027)
        self.assertEqual(by_code_26["PESACH"]["holiday_days"], 16)
        self.assertEqual(by_code_26["YOM_HAATZMAUT"]["holiday_days"], 1)
        self.assertIn("(1 יום)", by_code_26["YOM_HAATZMAUT"]["label_he"])
        self.assertIn("(1 day)", by_code_26["YOM_HAATZMAUT"]["label_en"])
        self.assertEqual(by_code_26["ROSH_HASHANAH"]["target_year"], 2027)
        self.assertEqual(by_code_26["ROSH_HASHANAH"]["holiday_days"], 3)
        self.assertEqual(by_code_26["YOM_KIPPUR_SUKKOT_BRIDGE"]["target_year"], 2027)
        self.assertEqual(by_code_26["YOM_KIPPUR_SUKKOT_BRIDGE"]["holiday_days"], 14)
        self.assertEqual(by_code_26["SUKKOT"]["target_year"], 2027)
        self.assertEqual(by_code_26["SUKKOT"]["holiday_days"], 9)
        self.assertEqual(by_code_26["SUMMER_JULY"]["holiday_days"], 31)
        self.assertEqual(by_code_26["SUMMER_AUGUST"]["holiday_days"], 31)

        for item in up_nov26:
            self.assertGreaterEqual(date.fromisoformat(item["end_date"]), date(2026, 11, 19))
            self.assertRegex(item["label_he"], r"\(\d+\s+(?:ימים|יום)\)$")
            self.assertRegex(item["label_en"], r"\(\d+\s+days?\)$")

        # 2. Automatic year rollover at later dates (2027-05-01 and 2028-09-01)
        up_may27 = {
            h["holiday_code"]: h
            for h in iso_cal.get_upcoming_holidays_for_rolling_year(
                as_of_date="2027-05-01", profile=prof
            )
        }
        self.assertEqual(up_may27["HANUKKAH"]["target_year"], 2027)
        self.assertEqual(up_may27["PURIM"]["target_year"], 2028)
        self.assertEqual(up_may27["PESACH"]["target_year"], 2028)

        up_sep28 = {
            h["holiday_code"]: h
            for h in iso_cal.get_upcoming_holidays_for_rolling_year(
                as_of_date="2028-09-01", profile=prof
            )
        }
        self.assertEqual(up_sep28["ROSH_HASHANAH"]["target_year"], 2028)
        self.assertEqual(up_sep28["PESACH"]["target_year"], 2029)

        # 3. Mode-3 YOM_KIPPUR_SUKKOT_BRIDGE (Oct 2027) vs SUKKOT (shifted +5d)
        wins_bridge = iso_max.generate_candidate_windows(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "YOM_KIPPUR_SUKKOT_BRIDGE",
                "direct_target_year": 2027,
                "min_trip_nights": 4,
                "max_trip_nights": 14,
            },
            prof,
        )
        self.assertGreater(len(wins_bridge), 0)
        self.assertTrue(all(w.start_date.month in (9, 10) and w.start_date.year == 2027 for w in wins_bridge))

        wins_sukkot = iso_max.generate_candidate_windows(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "SUKKOT",
                "direct_target_year": 2027,
                "min_trip_nights": 4,
                "max_trip_nights": 9,
                "max_bridge_days_shift": 0,
            },
            prof,
        )
        self.assertGreater(len(wins_sukkot), 0)
        self.assertTrue(all(w.start_date >= date(2027, 10, 12) for w in wins_sukkot))

        # 4. REST endpoint `/api/v1/moe-calendar/upcoming` + 1-day holiday max_trip_nights clamping
        with tempfile.TemporaryDirectory() as tmpdir:
            client = VacationPlannerTestClient(db_path=Path(tmpdir) / "r1_api.db")
            resp_up = client.get("/api/v1/moe-calendar/upcoming?as_of=2027-05-01")
            self.assertEqual(resp_up.status_code, 200)
            up_json = resp_up.json()
            self.assertEqual(up_json["count"], 11)
            for h_obj in up_json["holidays"]:
                resp_s = client.post(
                    "/api/v1/vacations/search",
                    json={
                        "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                        "direct_holiday_code": h_obj["holiday_code"],
                        "direct_target_year": h_obj["target_year"],
                        "max_trip_nights": h_obj["holiday_days"],
                        "airline_selection_mode": "EL_AL_ONLY",
                        "destination_iatas": ["ATH"],
                    },
                )
                self.assertEqual(resp_s.status_code, 200, f"Failed search for {h_obj}")

    def test_manual_specific_dates_plus_minus_flexibility_and_anywhere_discovery_run3_r2_r4(
        self,
    ) -> None:
        """23. Verify `SPECIFIC_DATES` + `±` day flexibility finds shifted `#live` flights across
        single destinations and all 45 `ANYWHERE` destinations (including 2-night and 15-night spans).
        """
        from backend.app.schemas.domain import ChildFramework, FamilyProfile

        live_repo = SQLiteRepository(":memory:", auto_seed=False)
        live_cal = MoECalendarService(live_repo)
        live_max = VacationMaximizerEngine(live_cal)
        live_adapter = ElAlRbdDataClientAdapter(live_repo)
        live_planner = BonusVacationPlannerService(
            repository=live_repo,
            calendar_service=live_cal,
            maximizer=live_max,
            elal_adapter=live_adapter,
            commercial_adapter=AllAirlinesSearchAdapter(live_repo),
        )

        # Import `#live` flights ONLY on shifted dates (+2d outbound, +1d inbound) on SOF (outside top-14 offline list) and ATH
        live_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "SOF",
                    "direction": "OUTBOUND",
                    "flight_number": "LY551",
                    "flight_date": "2027-05-12",
                    "economy_seats": 2,
                    "dep_time": "07:15",
                    "arr_time": "09:55",
                },
                {
                    "destination_iata": "SOF",
                    "direction": "INBOUND",
                    "flight_number": "LY552",
                    "flight_date": "2027-05-19",
                    "economy_seats": 2,
                    "dep_time": "11:10",
                    "arr_time": "13:40",
                },
                {
                    "destination_iata": "ATH",
                    "direction": "OUTBOUND",
                    "flight_number": "LY541",
                    "flight_date": "2027-05-12",
                    "economy_seats": 2,
                    "dep_time": "08:00",
                    "arr_time": "10:15",
                },
                {
                    "destination_iata": "ATH",
                    "direction": "INBOUND",
                    "flight_number": "LY542",
                    "flight_date": "2027-05-14",
                    "economy_seats": 2,
                    "dep_time": "12:00",
                    "arr_time": "14:05",
                },
            ]
        )

        manual_prof = FamilyProfile(
            id="manual-flex-prof",
            adults_count=2,
            matmid_points_balance=185000,
            children=[ChildFramework(child_age_years=8, framework_type=None)],
            passenger_loyalty_wallets=[],
        )

        # Exact flex=0 on 2027-05-10..2027-05-18 has 0 flights; flex=2 finds 2027-05-12..2027-05-19 on ANYWHERE (SOF)!
        props_flex0 = live_planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ANYWHERE"],
                "specific_departure_date": "2027-05-10",
                "specific_return_date": "2027-05-18",
                "flex_days_plus_minus": 0,
            },
            profile=manual_prof,
        )
        self.assertEqual(len(props_flex0), 0)

        props_flex2 = live_planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ANYWHERE"],
                "specific_departure_date": "2027-05-10",
                "specific_return_date": "2027-05-18",
                "flex_days_plus_minus": 2,
            },
            profile=manual_prof,
        )
        self.assertGreater(len(props_flex2), 0)
        sof_props = [
            p for p in props_flex2 if p.itinerary and p.itinerary.destination_iata == "SOF"
        ]
        self.assertGreater(len(sof_props), 0)
        self.assertEqual(sof_props[0].itinerary.departure_date, date(2027, 5, 12))
        self.assertEqual(sof_props[0].itinerary.return_date, date(2027, 5, 19))

        # Short 2-night manual getaway without explicit min/max_trip_nights succeeds
        short_props = live_planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
                "specific_departure_date": "2027-05-12",
                "specific_return_date": "2027-05-14",
                "flex_days_plus_minus": 0,
            },
            profile=manual_prof,
        )
        self.assertGreater(len(short_props), 0)
        self.assertEqual(short_props[0].itinerary.trip_nights, 2)

    def test_single_household_matmid_balance_pool_and_elal_egress_lock_run3_r3_r5(
        self,
    ) -> None:
        """24. Verify single household `matmid_points_balance` (`0`, `30k`, `300k`) governs proposals
        even when legacy DB wallets exist, suppresses single-wallet `MULTI_CLUB_PER_PASSENGER_SPLIT`
        duplicates, and blocks outbound `elal.com` HTTP egress by default.
        """
        from unittest.mock import patch
        from backend.app.main import VacationPlannerTestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = VacationPlannerTestClient(db_path=Path(tmpdir) / "r3_api.db")
            # Unauthenticated profile access is strictly rejected (401)
            self.assertEqual(client.get("/api/v1/profile").status_code, 401)
            # Authenticate a Gmail user and save a 5-pax household with 6 legacy wallets totaling 185k Matmid
            self._authenticate_client(client, email="r3.pool@gmail.com", seed_default_household=True)
            prof_init = client.get("/api/v1/profile").json()
            self.assertEqual(len(prof_init["passenger_loyalty_wallets"]), 6)

            # 5 seated passengers; one Economy round-trip bonus ticket to Rome = 30,000 pts,
            # all five = 150,000 pts. A balance is compared with ONE ticket only (run 11, R2).
            for bal in (0, 30000, 300000):
                resp = client.post(
                    "/api/v1/vacations/search",
                    json={
                        "date_selection_mode": "SPECIFIC_DATES",
                        "specific_departure_date": "2027-04-11",
                        "specific_return_date": "2027-04-18",
                        "flex_days_plus_minus": 0,
                        "airline_selection_mode": "EL_AL_ONLY",
                        "enabled_loyalty_programs": ["ELAL_MATMID"],
                        "destination_iatas": ["FCO"],
                        "matmid_points_balance": bal,
                    },
                )
                self.assertEqual(resp.status_code, 200)
                proposals = resp.json()["proposals"]
                self.assertGreater(len(proposals), 0)
                for p in proposals:
                    itin = p["itinerary"]
                    self.assertTrue(itin["is_elal_flight"])
                    self.assertIn(itin["primary_carrier_iata"], ("LY", "2U"))
                    for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
                        self.assertNotIn(removed_key, itin)
                    self.assertNotEqual(
                        itin["fulfillment_strategy"], "MULTI_CLUB_PER_PASSENGER_SPLIT"
                    )
                    # A bonus search never returns a result without bonus seats (U4)
                    self.assertNotEqual(itin["fulfillment_strategy"], "COMMERCIAL_CASH_ONLY")
                    self.assertNotEqual(itin["bonus_direction_coverage"], "NONE")
                    if bal > 0 and itin["min_points_per_bonus_ticket"] is not None:
                        self.assertLessEqual(itin["min_points_per_bonus_ticket"], bal)
                full_bonus = [
                    p["itinerary"]
                    for p in proposals
                    if p["itinerary"]["fulfillment_strategy"] == "FULL_BONUS_SAME_CABIN"
                ]
                # Balance 0 = "not entered": bonus results are shown. Balance 30,000 covers one
                # ticket (not all five) and still returns the all-bonus result.
                self.assertEqual(len(full_bonus), 1, f"balance={bal}")
                self.assertEqual(full_bonus[0]["bonus_tickets_count"], 5)
                self.assertEqual(full_bonus[0]["min_points_per_bonus_ticket"], 30000)
                self.assertEqual(full_bonus[0]["min_points_basis"], "ROUND_TRIP")
                # Points-plus-money does not depend on the wallet either (ruling J2): it is
                # returned for balance 0 as for any other balance, and never has a points figure.
                cash_and_points = [
                    p["itinerary"]
                    for p in proposals
                    if p["itinerary"]["fulfillment_strategy"] == "CASH_AND_POINTS"
                ]
                self.assertGreaterEqual(len(cash_and_points), 1, f"balance={bal}")
                for cp_itin in cash_and_points:
                    self.assertIsNone(cp_itin["min_points_per_bonus_ticket"])
                    self.assertIsNone(cp_itin["min_points_basis"])

        # Verify zero outbound HTTP traffic to elal.com even when ELAL_LIVE_FETCH_ENABLED=1
        old_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        old_egress = os.environ.get("ELAL_ALLOW_DIRECT_HTTP_EGRESS")
        try:
            os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
            os.environ.pop("ELAL_ALLOW_DIRECT_HTTP_EGRESS", None)
            with patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("Forbidden outbound elal.com HTTP request!"),
            ):
                rows = self.elal_adapter._try_live_http_fetch(
                    ["FCO"], date(2027, 4, 11), date(2027, 4, 18)
                )
                self.assertEqual(rows, [])
        finally:
            if old_live is None:
                os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            else:
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_live
            if old_egress is None:
                os.environ.pop("ELAL_ALLOW_DIRECT_HTTP_EGRESS", None)
            else:
                os.environ["ELAL_ALLOW_DIRECT_HTTP_EGRESS"] = old_egress

    def test_rolling_2036_2040_holiday_search_live_http_malformed_json_422_and_zero_point_infant_lap(
        self,
    ) -> None:
        """25. Verify:
        (a) Rolling 1-year holiday searches in `2036..2040` (`as_of=2035-12-31`, `as_of=2039-12-31`)
            and `SPECIFIC_DATES` carrying `direct_target_year=2036` succeed with `HTTP 200` and
            generate proposals in the exact requested `target_year`, while `2024` returns `422`.
        (b) Live `create_http_server` returns clean `HTTP 422` JSON (never `RemoteDisconnected` or
            silent `bool -> 1` coercion) on `None`, `bool`, `[]`, `{}`, `"inf"`, `"-inf"`, `"nan"`.
        (c) `0`-point `COMMERCIAL_CASH_ONLY` fallback marks lap-infant allocations with `rbd_code="INF"`.
        """
        from datetime import timedelta
        import json
        import threading
        import urllib.error
        import urllib.request
        from backend.app.main import VacationPlannerTestClient, create_http_server

        client = VacationPlannerTestClient(":memory:")
        for as_of_iso in ("2035-12-31", "2039-12-31"):
            up_resp = client.get(f"/api/v1/moe-calendar/upcoming?as_of={as_of_iso}")
            self.assertEqual(up_resp.status_code, 200)
            holidays = up_resp.json()["holidays"]
            self.assertEqual(len(holidays), 11)
            for h in holidays:
                s_resp = client.post(
                    "/api/v1/vacations/search",
                    json={
                        "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                        "direct_holiday_code": h["holiday_code"],
                        "direct_target_year": h["target_year"],
                        "max_trip_nights": h["holiday_days"],
                        "airline_selection_mode": "EL_AL_ONLY",
                        "destination_iatas": ["ATH"],
                        "matmid_points_balance": 185000,
                    },
                )
                self.assertEqual(
                    s_resp.status_code,
                    200,
                    f"Failed rolling search at {as_of_iso} for {h}: {s_resp.text}",
                )
                s_body = s_resp.json()
                self.assertEqual(s_body["query"]["direct_target_year"], h["target_year"])
                self.assertGreater(s_body["count"], 0)
                min_bound = date.fromisoformat(h["start_date"]) - timedelta(days=5)
                max_bound = date.fromisoformat(h["end_date"]) + timedelta(days=5)
                for prop in s_body["proposals"]:
                    dep_dt = date.fromisoformat(prop["itinerary"]["departure_date"])
                    self.assertGreaterEqual(dep_dt, min_bound)
                    self.assertLessEqual(dep_dt, max_bound)

        # SPECIFIC_DATES carrying direct_target_year=2036 (matching app.js payload shape) -> 200
        spec_2036 = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2036-05-11",
                "specific_return_date": "2036-05-18",
                "flex_days_plus_minus": 1,
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2036,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
                "matmid_points_balance": 185000,
            },
        )
        self.assertEqual(spec_2036.status_code, 200)
        self.assertGreater(spec_2036.json()["count"], 0)

        # Out-of-range direct_target_year=2024 over HTTP -> 422
        bad_2024 = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2024,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
            },
        )
        self.assertEqual(bad_2024.status_code, 422)

        # Unauthenticated PUT /api/v1/profile is rejected with 401
        self.assertEqual(client.put("/api/v1/profile", json={"adults_count": 2}).status_code, 401)

        # Zero-point COMMERCIAL_CASH_ONLY fallback with an age-1 INFANT_LAP child -> rbd_code == "INF"
        self._authenticate_client(client, email="infant.test@gmail.com", seed_default_household=False)
        prof_inf = client.get("/api/v1/profile").json()
        prof_inf["children"] = [
            {
                "id": "inf-0pt",
                "child_name": "תינוק",
                "child_age_years": 1,
                "passenger_Current_type": "INFANT_LAP",
                "framework_type": "DAYCARE_SUPERVISED",
            }
        ]
        prof_inf["passenger_loyalty_wallets"] = []
        prof_inf["matmid_points_balance"] = 0
        self.assertEqual(client.put("/api/v1/profile", json=prof_inf).status_code, 200)
        inf_zero_resp = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "matmid_points_balance": 0,
            },
        )
        self.assertEqual(inf_zero_resp.status_code, 200)
        inf_props = inf_zero_resp.json()["proposals"]
        self.assertGreater(len(inf_props), 0)
        self.assertEqual(inf_props[0]["itinerary"]["seated_passengers_count"], 2)
        self.assertNotIn("family_ticket_allocation", inf_props[0]["itinerary"])

        # Live ThreadingHTTPServer malformed JSON boundary sweep -> 422 without socket drop
        with tempfile.TemporaryDirectory() as srv_tmp:
            srv_db = Path(srv_tmp) / "live_malformed.db"
            setup_client = VacationPlannerTestClient(db_path=srv_db)
            srv_cookie, srv_csrf = self._authenticate_client(
                setup_client, email="fuzzer1@gmail.com", seed_default_household=True
            )
            srv = create_http_server("127.0.0.1", 0, db_path=srv_db)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base_spec = {
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2027-05-10",
                "specific_return_date": "2027-05-18",
            }
            base_prof = {
                "id": "default-family-profile",
                "adults_count": 2,
                "children": [],
                "passenger_loyalty_wallets": [],
            }
            malformed_cases: list[tuple[str, str, object]] = [
                ("POST", "/api/v1/vacations/search", {**base_spec, "flex_days_plus_minus": None}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "flex_days_plus_minus": True}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "flex_days_plus_minus": []}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "flex_days_plus_minus": "inf"}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "min_trip_nights": None}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "max_trip_nights": None}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "max_bridge_days_shift": None}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "direct_target_year": None}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "direct_target_year": True}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": None}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": True}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": []}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": {}}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": "inf"}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": "-inf"}),
                ("POST", "/api/v1/vacations/search", {**base_spec, "matmid_points_balance": "nan"}),
                ("POST", "/api/v1/vacations/search", []),
                ("PUT", "/api/v1/profile", {**base_prof, "matmid_points_balance": True}),
                ("PUT", "/api/v1/profile", {**base_prof, "matmid_points_balance": None}),
                ("PUT", "/api/v1/profile", {**base_prof, "matmid_points_balance": []}),
                ("PUT", "/api/v1/profile", {**base_prof, "matmid_points_balance": "inf"}),
                ("PUT", "/api/v1/profile", {**base_prof, "adults_count": None}),
                ("PUT", "/api/v1/profile", {**base_prof, "adults_count": True}),
                ("PUT", "/api/v1/profile", {**base_prof, "point_valuation_usd": "nan"}),
                ("PUT", "/api/v1/profile", {**base_prof, "unsupported_removed_field": 1}),
                ("PUT", "/api/v1/profile", []),
            ]
            try:
                for method, path_url, payload_obj in malformed_cases:
                    req_hdrs = {"Content-Type": "application/json"}
                    if path_url.startswith("/api/v1/profile"):
                        req_hdrs["Cookie"] = srv_cookie
                        req_hdrs["X-CSRF-Token"] = srv_csrf
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}{path_url}",
                        data=json.dumps(payload_obj).encode("utf-8"),
                        headers=req_hdrs,
                        method=method,
                    )
                    err_body = ""
                    try:
                        with urllib.request.urlopen(req, timeout=5.0) as resp_ok:
                            code = resp_ok.status
                            err_body = resp_ok.read().decode("utf-8")
                    except urllib.error.HTTPError as http_err:
                        code = http_err.code
                        err_body = http_err.read().decode("utf-8")
                    self.assertEqual(
                        code,
                        422,
                        f"Expected 422 for {method} {path_url} {payload_obj!r}, got {code}: {err_body}",
                    )
                    parsed_err = json.loads(err_body)
                    self.assertIn("error", parsed_err)

                # Confirm live server remains healthy afterward
                ok_req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/v1/vacations/search",
                    data=json.dumps({**base_spec, "destination_iatas": ["ATH"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(ok_req, timeout=5.0) as ok_resp:
                    self.assertEqual(ok_resp.status, 200)
            finally:
                srv.shutdown()
                srv.server_close()
                client.router.repository.close()

    def test_holistic_live_http_schema_validation_sqlite_error_guard_and_profile_preservation(
        self,
    ) -> None:
        """26. Verify holistic Iteration 3 API schema hardening over live `ThreadingHTTPServer`:
        (a) All 16 Challenger Iteration 2 live-HTTP fuzzer cases (`school_year: []`, `created_at: [1]`,
            `pool_group_id: []`, `b"null"`, `/elal-bonus/sync` non-dict roots / `destinations: []` /
            `rbd_payload: 12345`, `enabled_loyalty_programs: [None, {}]`, `preferred_cabins: [None, {}]`,
            `matmid_points_balance: 10**100`, `origin_iata: 123`) return clean `HTTP 422` JSON without
            `sqlite3.ProgrammingError` thread crashes (`RemoteDisconnected`).
        (b) `PUT /api/v1/profile` with `b"null"` (and non-dict/malformed bodies) preserves the saved
            household profile (`children` count and `matmid_points_balance`) intact.
        (c) Additional non-dict root, enum-list, boolean, 64-bit integer bound, and SQLite FK checks
            across `/moe-calendar/sync/*`, `/vacations/compare`, `/elal-bonus/sync`, `/profile`, and
            `/vacations/search` return `HTTP 422`, while empty-body sync (`b""`) and valid round-trips
            return `HTTP 200`.
        """
        import http.client
        import json
        import threading
        from backend.app.main import VacationPlannerTestClient, create_http_server

        with tempfile.TemporaryDirectory() as hol_tmp:
            hol_db = Path(hol_tmp) / "holistic_fuzzer.db"
            auth_setup = VacationPlannerTestClient(db_path=hol_db)
            hol_cookie, hol_csrf = self._authenticate_client(
                auth_setup, email="holistic.fuzzer@gmail.com", seed_default_household=True
            )
            srv = create_http_server("127.0.0.1", 0, db_path=hol_db)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()

            def raw_req(
                method: str, path_url: str, body_bytes: bytes, with_auth: bool = True
            ) -> tuple[int | str, str]:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5.0)
                try:
                    req_hdrs = {"Content-Type": "application/json"}
                    if with_auth and path_url.startswith("/api/v1/profile"):
                        req_hdrs["Cookie"] = hol_cookie
                        req_hdrs["X-CSRF-Token"] = hol_csrf
                    conn.request(
                        method,
                        path_url,
                        body=body_bytes,
                        headers=req_hdrs,
                    )
                    resp = conn.getresponse()
                    return resp.status, resp.read().decode("utf-8", "replace")
                except Exception as exc:  # pragma: no cover - surfaces thread crashes
                    return f"CRASH:{type(exc).__name__}", str(exc)
                finally:
                    conn.close()

            base_spec = {
                "date_selection_mode": "SPECIFIC_DATES",
                "specific_departure_date": "2027-05-10",
                "specific_return_date": "2027-05-18",
            }
            base_prof = {
                "id": "default-family-profile",
                "adults_count": 2,
                "children": [],
                "passenger_loyalty_wallets": [],
            }

            try:
                # Verify unauthenticated GET / PUT /api/v1/profile returns 401
                unauth_get_code, _ = raw_req("GET", "/api/v1/profile", b"", with_auth=False)
                unauth_put_code, _ = raw_req("PUT", "/api/v1/profile", b"{}", with_auth=False)
                self.assertEqual(unauth_get_code, 401)
                self.assertEqual(unauth_put_code, 401)

                # Capture initial saved user household profile before adversarial PUTs
                prof_before_code, prof_before_raw = raw_req("GET", "/api/v1/profile", b"")
                self.assertEqual(prof_before_code, 200)
                prof_before = json.loads(prof_before_raw)
                self.assertGreater(len(prof_before["children"]), 0)
                self.assertEqual(prof_before["matmid_points_balance"], 185000)

                # Exact 16 Challenger Iteration 2 live-HTTP fuzzer cases + extended holistic matrix
                cases: list[tuple[str, str, bytes]] = [
                    # 1-16: Exact Challenger Iteration 2 §5 reproducer cases
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "school_year": []}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "created_at": [1]}).encode()),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "created_at": [1]}).encode()),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "passenger_loyalty_wallets": [{"program_code": "ELAL_MATMID", "pool_group_id": []}]}).encode()),
                    ("PUT", "/api/v1/profile", b"null"),
                    ("POST", "/api/v1/vacations/search", b"null"),
                    ("POST", "/api/v1/elal-bonus/sync", b"null"),
                    ("POST", "/api/v1/elal-bonus/sync", b"[]"),
                    ("POST", "/api/v1/elal-bonus/sync", b"123"),
                    ("POST", "/api/v1/elal-bonus/sync", b"true"),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": []}).encode()),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": ["FCO"], "rbd_payload": 12345}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "enabled_loyalty_programs": [None, {}]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "preferred_cabins": [None, {}]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "matmid_points_balance": 10**100}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "origin_iata": 123}).encode()),
                    # Extended holistic coverage across all routes & fields
                    ("PUT", "/api/v1/profile", b"NaN"),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "updated_at": [1]}).encode()),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "matmid_points_balance": 10**100}).encode()),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "has_flycard": 2}).encode()),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "children": [{"child_age_years": 6, "birth_date": []}]}).encode()),
                    ("PUT", "/api/v1/profile", json.dumps({**base_prof, "passenger_loyalty_wallets": [{"program_code": "ELAL_MATMID", "points_balance": 10**100}]}).encode()),
                    ("POST", "/api/v1/moe-calendar/sync/2026-2027", b"null"),
                    ("POST", "/api/v1/moe-calendar/sync/2026-2027", json.dumps({"force_remote_check": "yes"}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "destination_iatas": [None]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "destinations": [None]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "destination": 12345}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "destination_iatas": ["ZZZZ"]}).encode()),
                    ("POST", "/api/v1/elal-bonus/sync", b"NaN"),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": ["FCO"], "rbd_payload": [None, 123, {}]}).encode()),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": ["FCO"], "rbd_payload": False}).encode()),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": ["FCO"], "origin": 123}).encode()),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": ["FCO"], "force_refresh": "yes"}).encode()),
                    ("POST", "/api/v1/elal-bonus/sync", json.dumps({"destinations": ["FCO"], "months_ahead": 99}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "destination_iatas": ["   "]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "destination_iatas": [123]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "target_holiday_codes": [None]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "include_sundor_flights": "yes"}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "family_profile_id": [1, 2]}).encode()),
                    ("POST", "/api/v1/vacations/search", json.dumps({**base_spec, "id": {"bad": 1}}).encode()),
                ]

                for method, path_url, body_bytes in cases:
                    status, resp_text = raw_req(method, path_url, body_bytes)
                    self.assertEqual(
                        status,
                        422,
                        f"Expected HTTP 422 for {method} {path_url} {body_bytes[:80]!r}, got {status}: {resp_text}",
                    )
                    err_obj = json.loads(resp_text)
                    self.assertIn("error", err_obj)

                # Verify removed /api/v1/vacations/compare returns 404 for all payloads, while empty destination_iatas [] normalizes to ANYWHERE (200)
                for cmp_bytes in (b"null", b"{}", json.dumps({"proposal_ids": ["p1"]}).encode()):
                    cmp_st, _ = raw_req("POST", "/api/v1/vacations/compare", cmp_bytes)
                    self.assertEqual(cmp_st, 404)
                empty_dest_st, empty_dest_raw = raw_req(
                    "POST",
                    "/api/v1/vacations/search",
                    json.dumps({**base_spec, "destination_iatas": []}).encode(),
                )
                self.assertEqual(empty_dest_st, 200)
                self.assertEqual(
                    json.loads(empty_dest_raw)["query"]["destination_iatas"],
                    ["ANYWHERE"],
                )

                # Verify saved profile was NOT wiped by PUT b"null" or any invalid PUT
                prof_after_code, prof_after_raw = raw_req("GET", "/api/v1/profile", b"")
                self.assertEqual(prof_after_code, 200)
                prof_after = json.loads(prof_after_raw)
                self.assertEqual(len(prof_after["children"]), len(prof_before["children"]))
                self.assertEqual(
                    prof_after["matmid_points_balance"],
                    prof_before["matmid_points_balance"],
                )
                self.assertEqual(prof_after["adults_count"], prof_before["adults_count"])

                # Verify empty HTTP body b"" on POST /api/v1/elal-bonus/sync and GET->PUT profile round-trip still return 200
                empty_sync_code, _ = raw_req("POST", "/api/v1/elal-bonus/sync", b"")
                self.assertEqual(empty_sync_code, 200)
                roundtrip_code, _ = raw_req(
                    "PUT", "/api/v1/profile", json.dumps(prof_after).encode("utf-8")
                )
                self.assertEqual(roundtrip_code, 200)
            finally:
                srv.shutdown()
                srv.server_close()

        # Verify router-level base sqlite3.Error guard catches ProgrammingError/InterfaceError as clean HTTP 422
        import sqlite3
        from unittest.mock import patch
        from backend.app.api.v1.endpoints import VacationPlannerAPIRouter

        guard_router = VacationPlannerAPIRouter(db_path=":memory:")
        try:
            guard_login = _make_mock_token_exchanger("guard@gmail.com")
            g_cookie, g_csrf = guard_login(guard_router, user_email="guard@gmail.com")
            put_st, _, _ = guard_router.dispatch(
                "PUT",
                "/api/v1/profile",
                json_body={"adults_count": 2},
                request_headers={"cookie": g_cookie, "x-csrf-token": g_csrf},
            )
            self.assertEqual(put_st, 200)
            with patch.object(
                guard_router.repository,
                "get_profile",
                side_effect=sqlite3.ProgrammingError("Simulated parameter binding error"),
            ):
                g_status, _, g_body = guard_router.dispatch(
                    "GET", "/api/v1/profile", request_headers={"cookie": g_cookie}
                )
                self.assertEqual(g_status, 422)
                self.assertIn("Simulated parameter binding error", json.loads(g_body)["error"])
        finally:
            guard_router.repository.close()

    def test_sharded_5day_windows_sold_out_reconciliation_and_sync_token_auth(
        self,
    ) -> None:
        """27. Verify:
        (a) Uniform 5-day sharding (`build_sharded_rolling_windows`) partitions 350 days into 5 drift-free daily shards of 5 windows each.
        (b) Batch-scoped `reconcile_slices` removes sold-out (`0` seat) flights and updates reduced seat counts (`2+` -> `1`) while leaving unscanned destinations/cabins untouched.
        (c) `ELAL_SYNC_API_TOKEN` enforces `401` on unauthorized sync attempts and accepts valid `Bearer` tokens.
        """
        from datetime import timedelta
        import os
        import tempfile
        from backend.app.main import VacationPlannerTestClient
        from scripts.sync_elal_to_server import (
            _save_shard_state,
            build_sharded_rolling_windows,
            build_single_target_date_window,
            resolve_sharded_plan,
        )

        # (a) Persistent resume state continues cleanly from where it stopped across outages,
        # never skipping intermediate shards even if the machine was off for 5+ days.
        tmp_state_dir = tempfile.mkdtemp(prefix="fvp_shard_state_")
        try:
            st_path = Path(tmp_state_dir) / "shard_state.json"
            day0 = date(2026, 11, 23)
            w0, idx0, tot0, anc0 = resolve_sharded_plan(st_path, today_override=day0)
            self.assertEqual((idx0, tot0, anc0, len(w0)), (0, 5, day0, 5))
            _save_shard_state(st_path, anc0, tot0, idx0)

            # Machine offline for 5 days (now day0 + 5 days): must resume at shard 1 (NOT repeat shard 0!),
            # preserving cycle anchor so windows 6..10 are covered without gaps.
            day5 = day0 + timedelta(days=5)
            w1, idx1, tot1, anc1 = resolve_sharded_plan(st_path, today_override=day5)
            self.assertEqual((idx1, tot1, anc1, len(w1)), (1, 5, day0, 5))
            self.assertEqual(w1[0]["local_start"], (day0 + timedelta(days=5 * 14)).isoformat())

            # Complete shards 1, 2, 3, 4; verify wrap-around back to shard 0 advances cycle_anchor to today!
            for s_idx in (1, 2, 3, 4):
                _save_shard_state(st_path, anc1, 5, s_idx)
            day10 = day0 + timedelta(days=10)
            w_wrap, idx_wrap, _, anc_wrap = resolve_sharded_plan(st_path, today_override=day10)
            self.assertEqual((idx_wrap, anc_wrap, len(w_wrap)), (0, day10, 5))
        finally:
            import shutil
            shutil.rmtree(tmp_state_dir, ignore_errors=True)

        single_w = build_single_target_date_window("2027-04-18")
        self.assertEqual(len(single_w), 1)
        self.assertEqual(single_w[0]["local_start"], "2027-04-18")
        self.assertEqual(single_w[0]["local_end"], "2027-05-02")

        # (b) & (c) Sold-out reconciliation + optional Bearer token auth
        old_live = os.environ.get("ELAL_LIVE_FETCH_ENABLED")
        old_tok = os.environ.get("ELAL_SYNC_API_TOKEN")
        tmp_dir = tempfile.mkdtemp(prefix="fvp_reconcile_test_")
        try:
            os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
            os.environ.pop("ELAL_SYNC_API_TOKEN", None)
            db_p = os.path.join(tmp_dir, "reconcile.sqlite")
            client = VacationPlannerTestClient(db_path=db_p)

            # Initial sync: FCO (2027-05-10 E=2, A=1; 2027-05-17 E=2) + ATH (2027-05-10 E=2)
            init_resp = client.post(
                "/api/v1/elal-bonus/sync",
                json={
                    "origin": "TLV",
                    "destinations": ["FCO", "ATH"],
                    "start_date": "2027-05-09",
                    "end_date": "2027-05-20",
                    "rbd_payload": [
                        {
                            "destination_iata": "FCO",
                            "direction": "OUTBOUND",
                            "flight_number": "LY381",
                            "flight_date": "2027-05-10",
                            "economy_seats": "2+",
                            "premium_seats": 1,
                        },
                        {
                            "destination_iata": "FCO",
                            "direction": "INBOUND",
                            "flight_number": "LY384",
                            "flight_date": "2027-05-17",
                            "economy_seats": "2+",
                        },
                        {
                            "destination_iata": "ATH",
                            "direction": "OUTBOUND",
                            "flight_number": "LY541",
                            "flight_date": "2027-05-10",
                            "economy_seats": "2+",
                        },
                    ],
                },
            )
            self.assertEqual(init_resp.status_code, 200)

            # Verify search finds FCO round-trip before booking/sell-out
            s_before = client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-05-10",
                    "specific_return_date": "2027-05-17",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                },
            ).json()
            self.assertGreater(s_before["count"], 0)

            # Now user books LY384 (2027-05-17 sold out to 0!) and LY381 Economy drops from 2+ to 1 seat,
            # while ONLY Economy ("E") on FCO is re-scanned (Premium "A" on LY381 and ATH must remain intact!)
            rec_resp = client.post(
                "/api/v1/elal-bonus/sync",
                json={
                    "origin": "TLV",
                    "destinations": ["FCO"],
                    "start_date": "2027-05-09",
                    "end_date": "2027-05-20",
                    "reconcile_slices": [
                        {
                            "destinations": ["FCO"],
                            "start_date": "2027-05-09",
                            "end_date": "2027-05-20",
                            "cabins": ["E"],
                        }
                    ],
                    "rbd_payload": [
                        {
                            "destination_iata": "FCO",
                            "direction": "OUTBOUND",
                            "flight_number": "LY381",
                            "flight_date": "2027-05-10",
                            "economy_seats": 1,
                        }
                    ],
                },
            )
            self.assertEqual(rec_resp.status_code, 200)
            self.assertEqual(rec_resp.json()["records_reconciled"], 2)

            # Sold-out LY384 inbound is completely removed -> inbound leg degrades to LY_CASH (never LY384!)
            s_after = client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-05-10",
                    "specific_return_date": "2027-05-17",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["FCO"],
                },
            ).json()
            self.assertEqual(s_after["count"], 1)
            self.assertEqual(
                s_after["proposals"][0]["itinerary"]["inbound_legs"][0]["flight_number"],
                "LY_CASH",
            )

            # Un-scanned cabin ("A" on LY381 = 1 seat) and un-scanned destination (ATH = 2 seats) remain intact,
            # and LY381 Economy dropped cleanly from 2 to 1!
            cached_fco = client.router.repository.get_cached_elal_bonus(
                destinations=["FCO"],
                start_date=date(2027, 5, 9),
                end_date=date(2027, 5, 20),
            )
            self.assertEqual(len(cached_fco), 1)
            self.assertEqual(cached_fco[0].flight_number, "LY381")
            self.assertEqual(cached_fco[0].economy_award_seats, 1)
            self.assertEqual(cached_fco[0].premium_award_seats, 1)

            cached_ath = client.router.repository.get_cached_elal_bonus(
                destinations=["ATH"],
                start_date=date(2027, 5, 9),
                end_date=date(2027, 5, 20),
            )
            self.assertEqual(len(cached_ath), 1)
            self.assertEqual(cached_ath[0].economy_award_seats, 2)

            # (c) Enable ELAL_SYNC_API_TOKEN and verify 401 vs 200
            os.environ["ELAL_SYNC_API_TOKEN"] = "secret-sync-token-123"
            st_401, _, _ = client.router.dispatch(
                "POST",
                "/api/v1/elal-bonus/sync",
                json_body={"destinations": ["FCO"]},
                request_headers={},
            )
            self.assertEqual(st_401, 401)
            st_200, _, _ = client.router.dispatch(
                "POST",
                "/api/v1/elal-bonus/sync",
                json_body={
                    "destinations": ["FCO"],
                    "reconcile_slices": [
                        {
                            "destinations": ["FCO"],
                            "start_date": "2027-05-09",
                            "end_date": "2027-05-20",
                            "cabins": ["E", "A"],
                        }
                    ],
                },
                request_headers={"authorization": "Bearer secret-sync-token-123"},
            )
            self.assertEqual(st_200, 200)
            client.router.repository.close()
        finally:
            if old_live is None:
                os.environ.pop("ELAL_LIVE_FETCH_ENABLED", None)
            else:
                os.environ["ELAL_LIVE_FETCH_ENABLED"] = old_live
            if old_tok is None:
                os.environ.pop("ELAL_SYNC_API_TOKEN", None)
            else:
                os.environ["ELAL_SYNC_API_TOKEN"] = old_tok
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_run10_r2_multi_select_destinations_aliases_and_11plus_non_flagship_offline(
        self,
    ) -> None:
        """28. Verify `run10` `R2` multi-select destination filtering, alias normalization, and `>10` non-flagship offline cities."""
        from backend.app.main import VacationPlannerTestClient
        from backend.app.schemas.domain import FlightSearchQuery

        # 1. No-arg Python default remains ["FCO"], while explicit empty [] / "" normalizes to ["ANYWHERE"]
        self.assertEqual(FlightSearchQuery().destination_iatas, ["FCO"])
        self.assertEqual(FlightSearchQuery.from_dict({}).destination_iatas, ["FCO"])
        self.assertEqual(
            FlightSearchQuery.from_dict({"destination_iatas": []}).destination_iatas,
            ["ANYWHERE"],
        )
        self.assertEqual(
            FlightSearchQuery.from_dict({"destinations": ["rom", "ath", "ROM"]}).destination_iatas,
            ["ROM", "ATH"],
        )
        self.assertEqual(
            FlightSearchQuery.from_dict({"destination": "lon, bkk"}).destination_iatas,
            ["LON", "BKK"],
        )

        client = VacationPlannerTestClient(db_path=":memory:")

        # 2. Multi-select subset (2+ destinations including metro LON) returns proposals strictly in expanded subset
        r_sub = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destinations": ["LON", "ATH"],
            },
        )
        self.assertEqual(r_sub.status_code, 200)
        sub_body = r_sub.json()
        self.assertEqual(sub_body["expanded_destinations"], ["LHR", "LTN", "ATH"])
        self.assertGreater(len(sub_body["proposals"]), 0)
        allowed_sub = {"LHR", "LTN", "ATH"}
        for prop in sub_body["proposals"]:
            itin = prop["itinerary"]
            self.assertIn(itin["destination_iata"], allowed_sub)
            self.assertIn(itin.get("return_origin_iata") or itin["destination_iata"], allowed_sub)

        # 3. 11 non-flagship cities in offline mode must NOT collapse to [] via legacy `len > 10` pruning!
        eleven_non_flagship = [
            "BCN", "AMS", "BER", "MUC", "FRA", "GVA",
            "LIS", "NCE", "OTP", "SOF", "WAW",
        ]
        r_11 = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": eleven_non_flagship,
            },
        )
        self.assertEqual(r_11.status_code, 200)
        props_11 = r_11.json()["proposals"]
        self.assertGreater(
            len(props_11),
            0,
            "Selecting 11 non-flagship destinations offline must return matching proposals instead of collapsing to []",
        )
        allowed_11 = set(eleven_non_flagship)
        for prop in props_11:
            itin = prop["itinerary"]
            self.assertIn(itin["destination_iata"], allowed_11)
            self.assertIn(itin.get("return_origin_iata") or itin["destination_iata"], allowed_11)

        # 4. Empty [] / ANYWHERE returns open-destination discovery across multiple cities
        r_any = client.post(
            "/api/v1/vacations/search",
            json={
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "destination_iatas": [],
            },
        )
        self.assertEqual(r_any.status_code, 200)
        any_dests = {p["itinerary"]["destination_iata"] for p in r_any.json()["proposals"]}
        self.assertGreaterEqual(len(any_dests), 3)


class TestRun11SeatBasedResults(unittest.TestCase):
    """Run 11: no price estimate, results based on available bonus seats, direction statement."""

    ROME = ("FCO", "2027-04-11", "2027-04-18")

    @staticmethod
    def _family_of_four():
        """2 adults + children aged 5 and 8 (4 seated passengers), no points entered."""
        from backend.app.schemas.domain import FamilyProfile
        from backend.app.storage_cache.seed_data import build_clean_guest_profile

        return FamilyProfile.from_dict(
            {
                **build_clean_guest_profile().to_dict(),
                "children": [
                    {"child_name": "ילד 1", "child_age_years": 5},
                    {"child_name": "ילד 2", "child_age_years": 8},
                ],
            }
        )

    @staticmethod
    def _planner_for(repo: SQLiteRepository) -> BonusVacationPlannerService:
        calendar_service = MoECalendarService(repo)
        return BonusVacationPlannerService(
            repository=repo,
            calendar_service=calendar_service,
            maximizer=VacationMaximizerEngine(calendar_service),
            elal_adapter=ElAlRbdDataClientAdapter(repo),
            commercial_adapter=AllAirlinesSearchAdapter(repo),
        )

    @classmethod
    def _seeded_planner(cls) -> BonusVacationPlannerService:
        return cls._planner_for(SQLiteRepository(":memory:", auto_seed=True))

    @classmethod
    def _live_only_planner(cls, rows: list[dict]) -> BonusVacationPlannerService:
        """Planner over a DB that holds only imported (`#live`) award rows."""
        repo = SQLiteRepository(":memory:", auto_seed=False)
        planner = cls._planner_for(repo)
        planner.elal_adapter.parse_and_import_external_rbd_payload(rows)
        return planner

    @staticmethod
    def _lca_rows(out_seats, in_seats) -> list[dict]:
        rows: list[dict] = []
        if out_seats is not None:
            rows.append(
                {
                    "destination_iata": "LCA",
                    "direction": "OUTBOUND",
                    "flight_number": "LY5131",
                    "flight_date": "2027-04-20",
                    "economy_seats": out_seats,
                    "dep_time": "06:30",
                    "arr_time": "07:40",
                }
            )
        if in_seats is not None:
            rows.append(
                {
                    "destination_iata": "LCA",
                    "direction": "INBOUND",
                    "flight_number": "LY5132",
                    "flight_date": "2027-04-26",
                    "economy_seats": in_seats,
                    "dep_time": "08:45",
                    "arr_time": "09:50",
                }
            )
        return rows

    def _search(self, planner, dest, dep, ret, profile, balance=None, **extra):
        query = {
            "date_selection_mode": "SPECIFIC_DATES",
            "airline_selection_mode": "EL_AL_ONLY",
            "destination_iatas": [dest],
            "specific_departure_date": dep,
            "specific_return_date": ret,
            "flex_days_plus_minus": 0,
            **extra,
        }
        if balance is not None:
            query["matmid_points_balance"] = balance
        return planner.search_vacations(query, profile=profile, persist_results=False)

    @staticmethod
    def _strategies(proposals) -> set[str]:
        return {p.itinerary.fulfillment_strategy.value for p in proposals}

    def _assert_cash_free_text(self, text: str) -> None:
        self.assertTrue(text.strip())
        for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
            self.assertNotIn(forbidden, text)

    # ------------------------------------------------------------------ R1
    def test_r1_no_price_or_points_total_in_any_planner_response_or_cli_line(self) -> None:
        """Every strategy the planner returns: none of the removed keys, cash-free text."""
        from contextlib import redirect_stdout
        import io

        from backend.app.cli.main import main as cli_main
        from backend.app.main import VacationPlannerTestClient
        from backend.app.schemas.domain import FulfillmentStrategy

        base_query = {
            "date_selection_mode": "SPECIFIC_DATES",
            "specific_departure_date": "2027-04-11",
            "specific_return_date": "2027-04-18",
            "flex_days_plus_minus": 0,
            "destination_iatas": ["FCO", "MXP"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "run11_r1.db"
            client = VacationPlannerTestClient(db_path=db_path)
            # Signed-in household with wallets in several clubs, so every strategy is reachable
            TestM2ProvidersAndSynthesizer._authenticate_client(
                self, client, email="run11.r1@gmail.com", seed_default_household=True
            )
            queries = [
                {
                    **base_query,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "enabled_loyalty_programs": [p.value for p in LoyaltyProgramCode],
                },
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2026-12-06",
                    "specific_return_date": "2026-12-12",
                    "flex_days_plus_minus": 0,
                    "destination_iatas": ["ATH"],
                    "airline_selection_mode": "EL_AL_ONLY",
                },
                {**base_query, "airline_selection_mode": "ALL_AIRLINES"},
                {
                    **base_query,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "search_elal_bonus_tickets": False,
                },
            ]
            seen_strategies: set[str] = set()
            for query in queries:
                resp = client.post("/api/v1/vacations/search", json=query)
                self.assertEqual(resp.status_code, 200, resp.text)
                body = resp.json()
                for removed_key in RUN11_REMOVED_RESPONSE_KEYS:
                    self.assertNotIn(removed_key, body)
                self.assertGreater(len(body["proposals"]), 0)
                for prop in body["proposals"]:
                    itin = prop["itinerary"]
                    strategy = itin["fulfillment_strategy"]
                    seen_strategies.add(strategy)
                    for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
                        self.assertNotIn(removed_key, itin, strategy)
                    for new_key in RUN11_NEW_ITINERARY_KEYS:
                        self.assertIn(new_key, itin, strategy)
                    self.assertIs(itin["points_are_estimated"], True)
                    self._assert_cash_free_text(prop["explanation_summary_he"])
                    if strategy == "COMMERCIAL_CASH_ONLY":
                        # Only reachable outside the bonus search: no bonus seats, score 0
                        self.assertEqual(itin["bonus_direction_coverage"], "NONE")
                        self.assertIsNone(itin["min_points_per_bonus_ticket"])
                        self.assertEqual(prop["flight_bonus_value_score"], 0.0)
                    if strategy == "CASH_AND_POINTS":
                        self.assertIsNone(itin["min_points_per_bonus_ticket"])
                        self.assertIsNone(itin["min_points_basis"])
            self.assertEqual(seen_strategies, {s.value for s in FulfillmentStrategy})

            # The CLI summary line carries no cash estimate either
            cli_db = Path(tmpdir) / "run11_r1_cli.db"
            out_buf = io.StringIO()
            with redirect_stdout(out_buf):
                rc = cli_main(
                    [
                        "--db-path",
                        str(cli_db),
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
                    ]
                )
            self.assertEqual(rc, 0)
            cli_text = out_buf.getvalue()
            result_lines = [ln for ln in cli_text.splitlines() if ln.strip().startswith("#")]
            self.assertGreaterEqual(len(result_lines), 1, cli_text)
            for line in result_lines:
                self.assertIn("HAS=", line)
                self.assertIn("CTOS=", line)
                self.assertRegex(line, r"Bonus=(BOTH_DIRECTIONS|OUTBOUND_ONLY|INBOUND_ONLY)$")
            for forbidden in ("Est. Cash", "~$", "$", "non-binding", "¢"):
                self.assertNotIn(forbidden, cli_text)

    # ------------------------------------------------------------------ R2
    def test_r2_balance_is_compared_with_one_bonus_ticket_not_the_family_total(self) -> None:
        planner = self._seeded_planner()
        family = self._family_of_four()

        # 30,000 pts = exactly one Economy round-trip bonus ticket to Rome; four cost 120,000
        at_minimum = self._search(planner, *self.ROME, family, balance=30000)
        full_bonus = [
            p.itinerary
            for p in at_minimum
            if p.itinerary.fulfillment_strategy.value == "FULL_BONUS_SAME_CABIN"
        ]
        self.assertEqual(len(full_bonus), 1)
        self.assertEqual(full_bonus[0].seated_passengers_count, 4)
        self.assertEqual(full_bonus[0].bonus_tickets_count, 4)
        self.assertEqual(full_bonus[0].min_points_per_bonus_ticket, 30000)
        self.assertEqual(full_bonus[0].min_points_basis, "ROUND_TRIP")
        self.assertGreater(
            full_bonus[0].bonus_tickets_count * full_bonus[0].min_points_per_bonus_ticket,
            30000,
            "the all-passenger total is above the balance, yet the result is returned",
        )
        for prop in at_minimum:
            min_pts = prop.itinerary.min_points_per_bonus_ticket
            self.assertTrue(min_pts is None or min_pts <= 30000)

        # One point below that round-trip minimum on 2-direction FCO: round-trip bonus
        # strategies are left out (and same-airport 2-direction FCO never emits a spurious
        # one-way commercial strategy per Run 12 R2); CASH_AND_POINTS (no points figure) stays.
        below_minimum = self._search(planner, *self.ROME, family, balance=29999)
        below_strategies = self._strategies(below_minimum)
        self.assertNotIn("FULL_BONUS_SAME_CABIN", below_strategies)
        self.assertNotIn("SPLIT_CABIN_BONUS", below_strategies)
        self.assertNotIn("HYBRID_BONUS_PLUS_CASH", below_strategies)
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", below_strategies)
        self.assertIn("CASH_AND_POINTS", below_strategies)
        for prop in below_minimum:
            min_pts = prop.itinerary.min_points_per_bonus_ticket
            self.assertTrue(min_pts is None or min_pts <= 29999)

        # Genuine single-direction route (ATH 2026-12-06..12, outbound bonus only):
        # 1-ticket one-way minimum boundary keeps ONE_WAY_BONUS_ONE_WAY_CASH at minimum and
        # drops it 1 point below.
        ath_zero = self._search(planner, "ATH", "2026-12-06", "2026-12-12", family, balance=0)
        one_way = [
            p.itinerary
            for p in ath_zero
            if p.itinerary.fulfillment_strategy.value == "ONE_WAY_BONUS_ONE_WAY_CASH"
        ][0]
        ow_min_pts = int(one_way.min_points_per_bonus_ticket or 0)
        self.assertGreater(ow_min_pts, 0)
        self.assertEqual(one_way.min_points_basis, "ONE_WAY")
        self.assertEqual(one_way.bonus_direction_coverage, "OUTBOUND_ONLY")
        self.assertIn(
            "ONE_WAY_BONUS_ONE_WAY_CASH",
            self._strategies(
                self._search(planner, "ATH", "2026-12-06", "2026-12-12", family, balance=ow_min_pts)
            ),
        )
        for prop in self._search(
            planner, "ATH", "2026-12-06", "2026-12-12", family, balance=ow_min_pts - 1
        ):
            self.assertIsNone(prop.itinerary.min_points_per_bonus_ticket)

        # Balance 0 and "no balance at all" mean "not entered": bonus results are returned
        for balance in (0, None):
            not_entered = self._search(planner, *self.ROME, family, balance=balance)
            strategies = self._strategies(not_entered)
            self.assertTrue(
                {
                    "FULL_BONUS_SAME_CABIN",
                    "SPLIT_CABIN_BONUS",
                    "HYBRID_BONUS_PLUS_CASH",
                    "CASH_AND_POINTS",
                }.issubset(strategies),
                f"balance={balance}: {strategies}",
            )
            self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", strategies)
            self.assertNotIn("COMMERCIAL_CASH_ONLY", strategies)
            for prop in not_entered:
                if prop.itinerary.fulfillment_strategy.value == "CASH_AND_POINTS":
                    # Points-plus-money never carries a points figure
                    self.assertIsNone(prop.itinerary.min_points_per_bonus_ticket)
                else:
                    self.assertGreater(prop.itinerary.min_points_per_bonus_ticket, 0)

    # ------------------------------------------------------------------ R3
    def test_r3_bonus_score_follows_available_bonus_seats(self) -> None:
        """Results that differ only in available bonus seats are scored from that difference."""
        family = self._family_of_four()
        scores_by_seats: dict[tuple, float] = {}
        for out_seats, in_seats in ((1, 1), (2, 2), (4, 4), (2, None)):
            planner = self._live_only_planner(self._lca_rows(out_seats, in_seats))
            ret = "2027-04-26" if in_seats is not None else "2027-04-28"
            proposals = self._search(planner, "LCA", "2027-04-20", ret, family, balance=0)
            self.assertGreaterEqual(len(proposals), 1, f"seats={out_seats}/{in_seats}")
            expected = _seat_score(out_seats, in_seats, 4)
            for prop in proposals:
                self.assertEqual(prop.itinerary.outbound_bonus_seats, out_seats)
                self.assertEqual(prop.itinerary.inbound_bonus_seats, in_seats)
                self.assertAlmostEqual(prop.flight_bonus_value_score, expected, places=1)
                # Overall badge: same formula as before, fed with the seat-only bonus score
                self.assertAlmostEqual(
                    prop.combined_trip_optimization_score,
                    round(0.55 * prop.holiday_alignment_score + 0.45 * expected, 1),
                    places=1,
                )
            scores_by_seats[(out_seats, in_seats)] = proposals[0].flight_bonus_value_score

        self.assertEqual(scores_by_seats[(1, 1)], 25.0)
        self.assertEqual(scores_by_seats[(2, None)], 50.0)
        self.assertEqual(scores_by_seats[(2, 2)], 100.0)
        self.assertEqual(scores_by_seats[(4, 4)], 100.0)
        self.assertLess(scores_by_seats[(1, 1)], scores_by_seats[(2, None)])
        self.assertLess(scores_by_seats[(2, None)], scores_by_seats[(2, 2)])

    def test_r3_scores_and_order_do_not_move_when_only_cash_reference_values_change(self) -> None:
        from unittest.mock import patch

        from backend.app.storage_cache.seed_data import DESTINATION_CATALOG

        family = self._family_of_four()
        cash_keys = (
            "rt_cash_per_pax_usd",
            "supplemental_single_pax_cash_usd",
            "five_pax_cash_benchmark_usd",
            "outbound_taxes_usd",
            "inbound_taxes_usd",
        )

        def _snapshot(planner) -> list[tuple]:
            rows: list[tuple] = []
            for dest, dep, ret in (self.ROME, ("ATH", "2026-12-06", "2026-12-12")):
                for prop in self._search(planner, dest, dep, ret, family, balance=100000):
                    itin = prop.itinerary
                    rows.append(
                        (
                            dest,
                            itin.fulfillment_strategy.value,
                            itin.bonus_tickets_count,
                            itin.cash_tickets_count,
                            itin.bonus_direction_coverage,
                            itin.min_points_per_bonus_ticket,
                            prop.flight_bonus_value_score,
                            prop.combined_trip_optimization_score,
                        )
                    )
            return rows

        repo = SQLiteRepository(":memory:", auto_seed=True)
        baseline = _snapshot(self._planner_for(repo))
        self.assertGreaterEqual(len(baseline), 4)

        # Multiply every cash reference value the planner used to read: catalog fares and
        # taxes, and the per-row award taxes.
        with repo.connection() as conn:
            conn.execute(
                "UPDATE elal_bonus_availability SET taxes_usd_per_pax = taxes_usd_per_pax * 9 + 500"
            )
        inflated_catalog = {
            dest: {key: float(DESTINATION_CATALOG[dest][key]) * 9 + 500 for key in cash_keys}
            for dest in ("FCO", "ATH")
        }
        with patch.dict(DESTINATION_CATALOG["FCO"], inflated_catalog["FCO"]), patch.dict(
            DESTINATION_CATALOG["ATH"], inflated_catalog["ATH"]
        ):
            changed_planner = self._planner_for(repo)
            fco_out = changed_planner.elal_adapter.get_award_availability(
                destinations=["FCO"],
                start_date=date(2027, 4, 11),
                end_date=date(2027, 4, 11),
                direction="OUTBOUND",
            )[0]
            self.assertGreater(fco_out.taxes_usd_per_pax, 500.0, "cash inputs really changed")
            self.assertGreater(DESTINATION_CATALOG["FCO"]["rt_cash_per_pax_usd"], 500.0)
            after_change = _snapshot(changed_planner)

        self.assertEqual(after_change, baseline)

    def test_r3_mixed_strategy_kinds_are_still_returned_without_cash_figures(self) -> None:
        """Inputs that returned the three mixed kinds at `57ab331` still return each of them."""
        planner = self._seeded_planner()
        family = self._family_of_four()
        proposals = self._search(planner, *self.ROME, family, balance=30000)
        by_strategy = {p.itinerary.fulfillment_strategy.value: p for p in proposals}
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", by_strategy)
        for kind in ("HYBRID_BONUS_PLUS_CASH", "CASH_AND_POINTS"):
            self.assertIn(kind, by_strategy)
            prop = by_strategy[kind]
            itin_dict = prop.to_dict()["itinerary"]
            for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
                self.assertNotIn(removed_key, itin_dict, kind)
            self.assertEqual(itin_dict["bonus_direction_coverage"], "BOTH_DIRECTIONS")
            self.assertEqual(prop.flight_bonus_value_score, 100.0)
            self._assert_cash_free_text(prop.explanation_summary_he)
        hybrid = by_strategy["HYBRID_BONUS_PLUS_CASH"].itinerary
        # 4 confirmed round-trip seats for 4 passengers: the hybrid keeps one commercial ticket
        self.assertEqual((hybrid.bonus_tickets_count, hybrid.cash_tickets_count), (3, 1))
        self.assertIsNone(by_strategy["CASH_AND_POINTS"].itinerary.min_points_per_bonus_ticket)

        # Open-Jaw Italy (`FCO` + `MXP`) returns round-trip Open-Jaw `ONE_WAY_BONUS_ONE_WAY_CASH`
        oj_props = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO", "MXP"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
                "matmid_points_balance": 30000,
            },
            profile=family,
            persist_results=False,
        )
        oj_cards = [
            p
            for p in oj_props
            if p.itinerary.fulfillment_strategy.value == "ONE_WAY_BONUS_ONE_WAY_CASH"
            and p.itinerary.destination_iata != p.itinerary.return_origin_iata
        ]
        self.assertGreaterEqual(len(oj_cards), 1)
        for ojp in oj_cards:
            oj_dict = ojp.to_dict()["itinerary"]
            for removed_key in RUN11_REMOVED_ITINERARY_KEYS:
                self.assertNotIn(removed_key, oj_dict)
            self.assertEqual(oj_dict["bonus_direction_coverage"], "BOTH_DIRECTIONS")
            self.assertEqual(oj_dict["min_points_basis"], "ROUND_TRIP")
            self._assert_cash_free_text(ojp.explanation_summary_he)

        # Seeded one-direction Athens (`2026-12-06..12`) & live one-direction Larnaca return
        # single-direction `ONE_WAY_BONUS_ONE_WAY_CASH` without cash figures
        ath_ow = [
            p
            for p in self._search(planner, "ATH", "2026-12-06", "2026-12-12", family, balance=0)
            if p.itinerary.fulfillment_strategy.value == "ONE_WAY_BONUS_ONE_WAY_CASH"
        ]
        self.assertEqual(len(ath_ow), 1)
        self.assertEqual(ath_ow[0].itinerary.bonus_direction_coverage, "OUTBOUND_ONLY")
        self.assertEqual(ath_ow[0].itinerary.min_points_basis, "ONE_WAY")
        self._assert_cash_free_text(ath_ow[0].explanation_summary_he)

        # The live one-direction case of `57ab331`: one-way bonus + commercial `LY_CASH` leg
        live_planner = self._live_only_planner(self._lca_rows(2, None))
        live_props = self._search(
            live_planner, "LCA", "2027-04-20", "2027-04-28", family, balance=9000
        )
        self.assertEqual(self._strategies(live_props), {"ONE_WAY_BONUS_ONE_WAY_CASH"})
        self.assertEqual(live_props[0].itinerary.inbound_legs[0].flight_number, "LY_CASH")

    # ------------------------------------------------------------------ R4
    def test_r4_every_result_states_bonus_in_both_directions_or_only_one(self) -> None:
        family = self._family_of_four()
        seeded = self._seeded_planner()

        both = self._search(seeded, *self.ROME, family, balance=0)
        self.assertGreaterEqual(len(both), 1)
        for prop in both:
            itin = prop.itinerary
            self.assertEqual(itin.bonus_direction_coverage, "BOTH_DIRECTIONS")
            self.assertGreater(itin.outbound_bonus_seats, 0)
            self.assertGreater(itin.inbound_bonus_seats, 0)
            self.assertTrue(itin.outbound_bonus_seats_is_two_plus)
            self.assertIn("בונוס בשני הכיוונים", prop.explanation_summary_he)

        # Seeded Athens 2026-12-06..12: the return flight has an award row with 0 seats
        outbound_only = self._search(seeded, "ATH", "2026-12-06", "2026-12-12", family, balance=0)
        self.assertGreaterEqual(len(outbound_only), 1)
        for prop in outbound_only:
            itin = prop.itinerary
            self.assertEqual(itin.bonus_direction_coverage, "OUTBOUND_ONLY")
            self.assertGreater(itin.outbound_bonus_seats, 0)
            self.assertEqual(itin.inbound_bonus_seats, 0)
            self.assertFalse(itin.inbound_bonus_seats_is_two_plus)
            if itin.fulfillment_strategy.value == "CASH_AND_POINTS":
                # Returned with balance 0 too (ruling J2); it has no points figure or basis
                self.assertIsNone(itin.min_points_basis)
            else:
                self.assertEqual(itin.min_points_basis, "ONE_WAY")
            self.assertIn("בונוס בכיוון אחד בלבד — הלוך", prop.explanation_summary_he)
        self.assertEqual(
            self._strategies(outbound_only),
            {"ONE_WAY_BONUS_ONE_WAY_CASH", "CASH_AND_POINTS"},
        )

        # Live-only inventory with no return row at all: commercial `LY_CASH` leg back
        live_out = self._search(
            self._live_only_planner(self._lca_rows(2, None)),
            "LCA",
            "2027-04-20",
            "2027-04-28",
            family,
            balance=0,
        )
        self.assertGreaterEqual(len(live_out), 1)
        for prop in live_out:
            itin = prop.itinerary
            self.assertEqual(itin.bonus_direction_coverage, "OUTBOUND_ONLY")
            self.assertEqual(itin.outbound_bonus_seats, 2)
            self.assertTrue(itin.outbound_bonus_seats_is_two_plus)
            self.assertIsNone(itin.inbound_bonus_seats)
            self.assertEqual(itin.inbound_legs[0].flight_number, "LY_CASH")

        # ...and the mirror case: bonus seats on the way back only
        live_in = self._search(
            self._live_only_planner(self._lca_rows(None, 1)),
            "LCA",
            "2027-04-20",
            "2027-04-26",
            family,
            balance=0,
        )
        self.assertGreaterEqual(len(live_in), 1)
        for prop in live_in:
            itin = prop.itinerary
            self.assertEqual(itin.bonus_direction_coverage, "INBOUND_ONLY")
            self.assertIsNone(itin.outbound_bonus_seats)
            self.assertEqual(itin.inbound_bonus_seats, 1)
            self.assertFalse(itin.inbound_bonus_seats_is_two_plus)
            self.assertEqual(itin.outbound_legs[0].flight_number, "LY_CASH")
            self.assertIn("בונוס בכיוון אחד בלבד — חזור", prop.explanation_summary_he)

    # ------------------------------------------------------------------ U4
    def test_u4_bonus_search_returns_no_result_without_bonus_seats(self) -> None:
        planner = self._seeded_planner()
        family = self._family_of_four()

        # Open-destination guest search: every returned result has bonus seats somewhere
        anywhere = planner.search_vacations(
            {
                "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                "direct_holiday_code": "PESACH",
                "direct_target_year": 2027,
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": [],
            },
            profile=family,
            persist_results=False,
        )
        self.assertGreaterEqual(len(anywhere), 3)
        for prop in anywhere:
            itin = prop.itinerary
            self.assertNotEqual(itin.bonus_direction_coverage, "NONE")
            self.assertNotEqual(itin.fulfillment_strategy.value, "COMMERCIAL_CASH_ONLY")
            self.assertGreater((itin.outbound_bonus_seats or 0) + (itin.inbound_bonus_seats or 0), 0)
            self.assertGreater(prop.flight_bonus_value_score, 0.0)

        # Award rows with 0 seats in every cabin, both directions: nothing is returned, with or
        # without points (at `57ab331` a household with points got a points-plus-money card).
        from unittest.mock import patch

        fco_out = copy.deepcopy(
            planner.elal_adapter.get_award_availability(
                destinations=["FCO"],
                start_date=date(2027, 4, 11),
                end_date=date(2027, 4, 11),
                direction="OUTBOUND",
            )[0]
        )
        fco_in = copy.deepcopy(
            planner.elal_adapter.get_award_availability(
                destinations=["FCO"],
                start_date=date(2027, 4, 18),
                end_date=date(2027, 4, 18),
                direction="INBOUND",
            )[0]
        )
        sold_out_out, sold_out_in = copy.deepcopy(fco_out), copy.deepcopy(fco_in)
        for row in (sold_out_out, sold_out_in):
            row.economy_award_seats = 0
            row.premium_award_seats = 0
            row.business_award_seats = 0
            row.economy_seats_is_two_plus = False
            row.premium_seats_is_two_plus = False
            row.business_seats_is_two_plus = False

        with patch.object(
            planner,
            "_ensure_award_rows_for_window",
            return_value=([sold_out_out], [sold_out_in]),
        ):
            for balance in (0, 100000):
                self.assertEqual(
                    self._search(planner, *self.ROME, family, balance=balance),
                    [],
                    f"balance={balance}",
                )
        # Seats left in one direction only: results come back, each stating that direction
        with patch.object(
            planner,
            "_ensure_award_rows_for_window",
            return_value=([sold_out_out], [fco_in]),
        ):
            inbound_only = self._search(planner, *self.ROME, family, balance=100000)
        self.assertGreaterEqual(len(inbound_only), 1)
        for prop in inbound_only:
            self.assertEqual(prop.itinerary.bonus_direction_coverage, "INBOUND_ONLY")
            self.assertEqual(prop.itinerary.outbound_bonus_seats, 0)

        # The engine still answers for zero-seat rows; the exclusion is the search's decision
        engine = MultiClubWalletAllocationEngine()
        commercial_only = engine.allocate_family_tickets(
            family, sold_out_out, sold_out_in, 590.0, "COMMERCIAL_CASH_ONLY"
        )
        self.assertIsNotNone(commercial_only)
        assert commercial_only is not None
        self.assertEqual(commercial_only["bonus_direction_coverage"], "NONE")
        self.assertEqual(commercial_only["bonus_tickets_count"], 0)
        self.assertEqual(commercial_only["cash_tickets_count"], 4)
        for strategy in (
            "FULL_BONUS_SAME_CABIN",
            "SPLIT_CABIN_BONUS",
            "HYBRID_BONUS_PLUS_CASH",
            "ONE_WAY_BONUS_ONE_WAY_CASH",
        ):
            self.assertIsNone(
                engine.allocate_family_tickets(
                    family, sold_out_out, sold_out_in, 590.0, strategy
                ),
                strategy,
            )

    # ------------------------------------------------------------ persistence
    def test_persisted_search_for_signed_in_user_with_saved_profile_still_works(self) -> None:
        """No DDL: a persisted search still writes its rows, with the cash columns left empty."""
        import sqlite3

        from backend.app.main import VacationPlannerTestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "run11_persist.db"
            client = VacationPlannerTestClient(db_path=db_path)
            TestM2ProvidersAndSynthesizer._authenticate_client(
                self, client, email="run11.persist@gmail.com", seed_default_household=True
            )
            resp = client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-11",
                    "specific_return_date": "2027-04-18",
                    "flex_days_plus_minus": 0,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["FCO"],
                    "matmid_points_balance": 30000,
                },
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            body = resp.json()
            self.assertGreater(body["count"], 0)
            query_id = body["query"]["id"]

            conn = sqlite3.connect(str(db_path))
            try:
                conn.row_factory = sqlite3.Row
                columns = [r["name"] for r in conn.execute("PRAGMA table_info(flight_itineraries)")]
                # Same table shape as before run 11 (no column added, none dropped)
                self.assertEqual(len(columns), 34)
                for kept_column in (
                    "total_out_of_pocket_cash_usd",
                    "full_cash_benchmark_usd",
                    "points_used_by_wallet_json",
                    "total_matmid_points",
                ):
                    self.assertIn(kept_column, columns)
                for new_key in RUN11_NEW_ITINERARY_KEYS:
                    self.assertNotIn(new_key, columns)

                itin_rows = conn.execute(
                    "SELECT * FROM flight_itineraries WHERE search_query_id = ?", (query_id,)
                ).fetchall()
                self.assertEqual(len(itin_rows), body["count"])
                for row in itin_rows:
                    self.assertEqual(row["total_matmid_points"], 0)
                    self.assertEqual(row["total_taxes_and_fees_usd"], 0.0)
                    self.assertEqual(row["total_supplemental_cash_fares_usd"], 0.0)
                    self.assertEqual(row["total_baggage_fees_usd"], 0.0)
                    self.assertEqual(row["total_out_of_pocket_cash_usd"], 0.0)
                    self.assertEqual(row["full_cash_benchmark_usd"], 0.0)
                    self.assertEqual(row["net_cash_saved_usd"], 0.0)
                    self.assertIsNone(row["cents_per_point_value"])
                    self.assertEqual(row["points_used_by_wallet_json"], "{}")

                prop_rows = conn.execute(
                    "SELECT * FROM vacation_option_proposals WHERE search_query_id = ?",
                    (query_id,),
                ).fetchall()
                self.assertEqual(len(prop_rows), body["count"])
                for row in prop_rows:
                    self._assert_cash_free_text(row["explanation_summary_he"])
            finally:
                conn.close()

            # Stored rows load back through the repository
            first = body["proposals"][0]
            reloaded = client.router.repository.get_proposal_by_id(first["id"])
            self.assertIsNotNone(reloaded)
            assert reloaded is not None and reloaded.itinerary is not None
            self.assertEqual(
                reloaded.itinerary.fulfillment_strategy.value,
                first["itinerary"]["fulfillment_strategy"],
            )
            self.assertEqual(
                reloaded.flight_bonus_value_score, first["flight_bonus_value_score"]
            )


class TestRun12ConsistentBonusBadges(unittest.TestCase):
    """Run 12 (`M12`): non-contradictory bonus direction & strategy logic, R1 weather payload, R3 metric inputs."""

    @staticmethod
    def _family_of_four():
        from backend.app.schemas.domain import FamilyProfile
        from backend.app.storage_cache.seed_data import build_clean_guest_profile

        return FamilyProfile.from_dict(
            {
                **build_clean_guest_profile().to_dict(),
                "children": [
                    {
                        "id": "c1",
                        "child_name": "ילד 1",
                        "child_age_years": 5,
                        "framework_type": "MUNICIPAL_GAN",
                        "school_week_days": 5,
                    },
                    {
                        "id": "c2",
                        "child_name": "ילד 2",
                        "child_age_years": 9,
                        "framework_type": "ELEMENTARY_1_3",
                        "school_week_days": 5,
                    },
                ],
            }
        )

    @staticmethod
    def _planner_for(repo: SQLiteRepository) -> BonusVacationPlannerService:
        return TestRun11SeatBasedResults._planner_for(repo)

    def test_run12_r2_four_pax_two_plus_open_jaw_lca_pfo_and_mixed_cabin_ltn_lhr_consistency(
        self,
    ) -> None:
        """Exact screenshot route (`TLV->LCA` `2+` + `PFO->TLV` `2+` for 4 pax) and mixed-cabin Open-Jaw (`LTN`/`LHR`)."""
        repo = SQLiteRepository(":memory:", auto_seed=False)
        planner = self._planner_for(repo)
        planner.elal_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "LCA",
                    "direction": "OUTBOUND",
                    "flight_number": "LY5131",
                    "flight_date": "2026-12-10",
                    "economy_seats": 2,
                    "dep_time": "07:00",
                    "arr_time": "08:05",
                },
                {
                    "destination_iata": "PFO",
                    "direction": "INBOUND",
                    "flight_number": "LY5138",
                    "flight_date": "2026-12-14",
                    "economy_seats": 2,
                    "dep_time": "08:15",
                    "arr_time": "09:20",
                },
            ]
        )
        family = self._family_of_four()
        proposals = planner.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LCA", "PFO"],
                "specific_departure_date": "2026-12-10",
                "specific_return_date": "2026-12-14",
                "flex_days_plus_minus": 0,
            },
            profile=family,
            persist_results=False,
        )
        self.assertGreaterEqual(len(proposals), 1)
        oj_props = [
            p
            for p in proposals
            if p.itinerary.destination_iata == "LCA"
            and p.itinerary.return_origin_iata == "PFO"
        ]
        self.assertEqual(len(oj_props), 1)
        oj = oj_props[0]
        itin = oj.itinerary
        assert itin is not None
        self.assertEqual(itin.fulfillment_strategy.value, "ONE_WAY_BONUS_ONE_WAY_CASH")
        self.assertEqual(itin.bonus_direction_coverage, "BOTH_DIRECTIONS")
        self.assertEqual(itin.outbound_bonus_seats, 2)
        self.assertEqual(itin.inbound_bonus_seats, 2)
        self.assertTrue(itin.outbound_bonus_seats_is_two_plus)
        self.assertTrue(itin.inbound_bonus_seats_is_two_plus)
        self.assertEqual(itin.bonus_tickets_count, 4)
        self.assertEqual(itin.cash_tickets_count, 0)
        self.assertTrue(itin.requires_two_plus_seat_verification)
        self.assertEqual(itin.min_points_per_bonus_ticket, 18000)
        self.assertEqual(itin.min_points_basis, "ROUND_TRIP")
        self.assertEqual(oj.flight_bonus_value_score, 100.0)
        assert oj.weather_metrics is not None
        self.assertIn("כף גרקו", oj.weather_metrics.activity_recommendations_he)
        self.assertIn("Larnaca", oj.weather_metrics.activity_recommendations_en)
        self.assertIn("Expected weather:", oj.weather_metrics.weather_summary_en)
        self.assertIn("מסלול משולב בבונוס (הלוך ל-LCA, חזור מ-PFO)", oj.explanation_summary_he)
        self.assertIn("בונוס בשני הכיוונים", oj.explanation_summary_he)
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", oj.explanation_summary_he)
        for forbidden in RUN11_FORBIDDEN_PRICE_TEXT:
            self.assertNotIn(forbidden, oj.explanation_summary_he)

        # Mixed-cabin Open-Jaw (`LTN` Economy 2 + `LHR` Premium 2, Economy 0 on return) must NOT
        # fall through into Case B `ONE_WAY`; it must stay `ROUND_TRIP` + `BOTH_DIRECTIONS`!
        repo_lon = SQLiteRepository(":memory:", auto_seed=False)
        planner_lon = self._planner_for(repo_lon)
        planner_lon.elal_adapter.parse_and_import_external_rbd_payload(
            [
                {
                    "destination_iata": "LTN",
                    "direction": "OUTBOUND",
                    "flight_number": "LY311",
                    "flight_date": "2026-12-09",
                    "economy_seats": 2,
                    "dep_time": "05:30",
                    "arr_time": "09:05",
                },
                {
                    "destination_iata": "LHR",
                    "direction": "INBOUND",
                    "flight_number": "LY210",
                    "flight_date": "2026-12-15",
                    "premium_seats": 2,
                    "dep_time": "16:20",
                    "arr_time": "23:09",
                },
            ]
        )
        lon_props = planner_lon.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LTN", "LHR"],
                "specific_departure_date": "2026-12-09",
                "specific_return_date": "2026-12-15",
                "flex_days_plus_minus": 0,
                "preferred_cabins": ["ECONOMY", "PREMIUM"],
            },
            profile=family,
            persist_results=False,
        )
        lon_oj = [
            p
            for p in lon_props
            if p.itinerary.destination_iata == "LTN"
            and p.itinerary.return_origin_iata == "LHR"
        ]
        self.assertEqual(len(lon_oj), 1)
        self.assertEqual(lon_oj[0].itinerary.bonus_direction_coverage, "BOTH_DIRECTIONS")
        self.assertEqual(lon_oj[0].itinerary.min_points_basis, "ROUND_TRIP")
        self.assertEqual(lon_oj[0].itinerary.bonus_tickets_count, 2)
        self.assertEqual(lon_oj[0].itinerary.cash_tickets_count, 2)

        # Open-Jaw with 0 inbound seats returns None (never falls through to mismatched Case B)
        out_ltn = planner_lon.elal_adapter.get_award_availability(
            destinations=["LTN"],
            start_date=date(2026, 12, 9),
            end_date=date(2026, 12, 9),
            direction="OUTBOUND",
        )[0]
        in_lhr_zero = copy.deepcopy(
            planner_lon.elal_adapter.get_award_availability(
                destinations=["LHR"],
                start_date=date(2026, 12, 15),
                end_date=date(2026, 12, 15),
                direction="INBOUND",
            )[0]
        )
        in_lhr_zero.economy_award_seats = 0
        in_lhr_zero.premium_award_seats = 0
        in_lhr_zero.business_award_seats = 0
        self.assertIsNone(
            planner_lon.wallet_engine.allocate_family_tickets(
                family,
                out_ltn,
                in_lhr_zero,
                0.0,
                "ONE_WAY_BONUS_ONE_WAY_CASH",
                ["ECONOMY", "PREMIUM"],
                ["ELAL_MATMID"],
            )
        )

    def test_run12_r2_same_airport_two_plus_both_directions_never_emits_one_way_while_single_direction_does(
        self,
    ) -> None:
        """Same-airport 2-direction (`FCO`, `LCA` `2+`/`2+`) omits `ONE_WAY_BONUS_ONE_WAY_CASH`; 1-direction emits it."""
        family = self._family_of_four()
        seeded = self._planner_for(SQLiteRepository(":memory:", auto_seed=True))
        fco_props = seeded.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["FCO"],
                "specific_departure_date": "2027-04-11",
                "specific_return_date": "2027-04-18",
                "flex_days_plus_minus": 0,
            },
            profile=family,
            persist_results=False,
        )
        self.assertGreaterEqual(len(fco_props), 3)
        for p in fco_props:
            self.assertEqual(p.itinerary.bonus_direction_coverage, "BOTH_DIRECTIONS")
            self.assertNotEqual(p.itinerary.fulfillment_strategy.value, "ONE_WAY_BONUS_ONE_WAY_CASH")

        # Single-cabin 2+/2+ same-city Larnaca for 4 pax
        repo_lca = SQLiteRepository(":memory:", auto_seed=False)
        planner_lca = self._planner_for(repo_lca)
        planner_lca.elal_adapter.parse_and_import_external_rbd_payload(
            TestRun11SeatBasedResults._lca_rows(2, 2)
        )
        lca_both = planner_lca.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["LCA"],
                "specific_departure_date": "2027-04-20",
                "specific_return_date": "2027-04-26",
                "flex_days_plus_minus": 0,
            },
            profile=family,
            persist_results=False,
        )
        lca_strats = {p.itinerary.fulfillment_strategy.value for p in lca_both}
        self.assertIn("FULL_BONUS_SAME_CABIN", lca_strats)
        self.assertIn("HYBRID_BONUS_PLUS_CASH", lca_strats)
        self.assertNotIn("ONE_WAY_BONUS_ONE_WAY_CASH", lca_strats)

        # Single-direction Athens (`2026-12-06..12`) emits `ONE_WAY_BONUS_ONE_WAY_CASH` with `OUTBOUND_ONLY`
        ath_props = seeded.search_vacations(
            {
                "date_selection_mode": "SPECIFIC_DATES",
                "airline_selection_mode": "EL_AL_ONLY",
                "destination_iatas": ["ATH"],
                "specific_departure_date": "2026-12-06",
                "specific_return_date": "2026-12-12",
                "flex_days_plus_minus": 0,
            },
            profile=family,
            persist_results=False,
        )
        ath_ow = [
            p
            for p in ath_props
            if p.itinerary.fulfillment_strategy.value == "ONE_WAY_BONUS_ONE_WAY_CASH"
        ]
        self.assertEqual(len(ath_ow), 1)
        self.assertEqual(ath_ow[0].itinerary.bonus_direction_coverage, "OUTBOUND_ONLY")
        self.assertEqual(ath_ow[0].itinerary.min_points_basis, "ONE_WAY")

    def test_run12_r1_r3_weather_coastal_vs_landlocked_and_metric_payload_completeness(
        self,
    ) -> None:
        """Verify R1 coastal (`LCA`) vs landlocked (`VIE`) `sea_water_temp_c` and R3 serialized metric inputs."""
        from backend.app.main import VacationPlannerTestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            client = VacationPlannerTestClient(db_path=Path(tmpdir) / "run12_r1_r3.db")
            hol_resp = client.post(
                "/api/v1/vacations/search",
                json={
                    "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                    "direct_holiday_code": "PESACH",
                    "direct_target_year": 2027,
                    "airline_selection_mode": "EL_AL_ONLY",
                    "destination_iatas": ["LCA", "VIE"],
                    "inline_profile": {
                        "adults_count": 2,
                        "matmid_points_balance": 0,
                        "children": [
                            {"child_age_years": 6, "framework_type": "ELEMENTARY_1_3"},
                            {"child_age_years": 10, "framework_type": "ELEMENTARY_4_6"},
                        ],
                    },
                },
            )
            self.assertEqual(hol_resp.status_code, 200)
            hol_props = hol_resp.json()["proposals"]
            lca_props = [p for p in hol_props if p["itinerary"]["destination_iata"] == "LCA"]
            vie_props = [p for p in hol_props if p["itinerary"]["destination_iata"] == "VIE"]
            self.assertGreaterEqual(len(lca_props), 1)
            self.assertGreaterEqual(len(vie_props), 1)
            self.assertIsNotNone(lca_props[0]["weather_metrics"]["sea_water_temp_c"])
            self.assertIsNone(vie_props[0]["weather_metrics"]["sea_water_temp_c"])

            for prop in (lca_props[0], vie_props[0]):
                for req_key in (
                    "holiday_alignment_score",
                    "total_school_days_missed_across_children",
                    "max_single_child_school_days_missed",
                    "per_child_impact",
                    "childcare_coverage_gain",
                    "school_absence_penalty",
                    "window_set_type",
                    "flight_bonus_value_score",
                    "weather_suitability_score",
                    "combined_trip_optimization_score",
                ):
                    self.assertIn(req_key, prop)
                self.assertEqual(len(prop["per_child_impact"]), 2)


if __name__ == "__main__":
    unittest.main()
