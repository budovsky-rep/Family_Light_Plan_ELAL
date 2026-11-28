"""Comprehensive Milestone 1 (`M1_foundation_db_calendar_maximizer`) unit test suite.

Covers Features `F01` through `F16`, `TEST-CAL-01`, `TEST-CAL-02`, `TEST-CAL-03`,
`TEST-OPT-01`, Worked Examples 1-6, Mode 1 optional frameworks, Mode 2 school-year
maximization, Mode 3 structured 11-holiday & year maximizer, future-year
`MoECalendarAutoUpdaterService` (`2027-2028`..`2034-2035`), 8-table SQLite 3.53
WAL constraints & `ON DELETE CASCADE`, and pre-seeded `2025-2028` flight/award data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backend.app.calendar_engine.moe_calendar_service import (
    HebrewCalendarRuleProjector,
    MoECalendarAutoUpdaterService,
    MoECalendarService,
    normalize_school_year,
)
from backend.app.config_manager.settings import (
    DEFAULT_DB_PATH,
    PROJECT_ROOT,
    get_settings,
    load_settings,
    resolve_db_path,
)
from backend.app.schemas.domain import (
    AirlineSelectionMode,
    ChildFramework,
    DateSelectionMode,
    ElAlBonusAvailability,
    FamilyProfile,
    FlightItinerary,
    FlightLeg,
    FlightSearchQuery,
    FulfillmentStrategy,
    HolidayExtensionMode,
    LoyaltyProgramCode,
    MoEFrameworkType,
    PassengerLoyaltyWallet,
    VacationOptionProposal,
    classify_passenger_type,
    suggest_framework_for_age,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    build_default_family_profile,
    build_seeded_elal_bonus_availability,
    generate_commercial_flights_for_route,
    is_shabbat_blocked_for_elal,
)
from backend.app.vacation_optimizer.maximizer_engine import (
    VacationMaximizerEngine,
    resolve_holiday_direct_intent_school_year,
)


class TestM1FoundationDbCalendarMaximizer(unittest.TestCase):
    """Verifies all Milestone 1 requirements (`F01`-`F16`)."""

    def setUp(self) -> None:
        self.repo = SQLiteRepository(":memory:", auto_seed=True)
        self.repo.save_profile(build_default_family_profile())
        self.calendar_service = MoECalendarService(self.repo)
        self.auto_updater = MoECalendarAutoUpdaterService(self.repo)
        self.maximizer = VacationMaximizerEngine(self.calendar_service)
        self.profile = self.repo.get_profile("default-family-profile")
        self.assertIsNotNone(self.profile)

    def tearDown(self) -> None:
        self.repo.close()

    # ------------------------------------------------------------------
    # Configuration & Domain Schema Tests
    # ------------------------------------------------------------------
    def test_settings_yaml_and_metro_iata_expansion(self) -> None:
        settings = get_settings()
        app_settings = load_settings()
        self.assertEqual(app_settings.default_origin_iata, "TLV")
        self.assertEqual(app_settings.default_currency, "USD")
        self.assertEqual(app_settings.supported_currencies, ["USD", "ILS", "EUR"])

        metro = app_settings.metro_iata_expansion
        self.assertEqual(metro["NYC"], ["JFK", "EWR"])
        self.assertEqual(metro["LON"], ["LHR", "LTN"])
        self.assertEqual(metro["PAR"], ["CDG"])
        self.assertEqual(metro["MIL"], ["MXP"])
        self.assertEqual(metro["ROM"], ["FCO"])
        self.assertEqual(metro["TYO"], ["NRT"])
        self.assertEqual(metro["MIA_AREA"], ["MIA", "FLL"])

        weights = settings["optimization_weights"]
        self.assertNotIn("vus_alpha_per", weights)
        self.assertNotIn("vus_beta_ccg", weights)
        self.assertNotIn("vus_gamma_sap", weights)
        self.assertAlmostEqual(weights["ctos_calendar_weight"], 0.55)
        self.assertAlmostEqual(weights["ctos_flight_weight"], 0.45)

    def test_age_classification_and_framework_suggestion_f12(self) -> None:
        self.assertEqual(classify_passenger_type(0, infant_seat=False), "INFANT_LAP")
        self.assertEqual(classify_passenger_type(1, infant_seat=True), "INFANT_SEAT")
        self.assertEqual(classify_passenger_type(2), "CHILD")
        self.assertEqual(classify_passenger_type(11), "CHILD")
        self.assertEqual(classify_passenger_type(12), "YOUTH")
        self.assertEqual(classify_passenger_type(17), "YOUTH")
        with self.assertRaises(ValueError):
            classify_passenger_type(-1)
        with self.assertRaises(ValueError):
            classify_passenger_type(22)

        self.assertEqual(suggest_framework_for_age(1), "DAYCARE_SUPERVISED")
        self.assertEqual(suggest_framework_for_age(4), "MUNICIPAL_GAN")
        self.assertEqual(suggest_framework_for_age(7), "ELEMENTARY_1_3")
        self.assertEqual(suggest_framework_for_age(10), "ELEMENTARY_4_6")
        self.assertEqual(suggest_framework_for_age(13), "MIDDLE_SCHOOL_7_9")
        self.assertEqual(suggest_framework_for_age(16), "HIGH_SCHOOL_10_12")

    def test_domain_models_roundtrip_serialization(self) -> None:
        prof = build_default_family_profile()
        dumped = prof.model_dump()
        reloaded = FamilyProfile.model_validate(dumped)
        self.assertEqual(reloaded.id, "default-family-profile")
        self.assertEqual(reloaded.profile_name, "משפחת בודובסקי")
        self.assertEqual(len(reloaded.children), 3)
        self.assertEqual(len(reloaded.passenger_loyalty_wallets), 6)

    # ------------------------------------------------------------------
    # SQLite 11-Table Schema, WAL Mode, Indexes & Constraints (`F01`-`F08`, `M5`)
    # ------------------------------------------------------------------
    def test_sqlite_8_tables_4_indexes_and_wal_mode_on_disk(self) -> None:
        # Use an isolated TemporaryDirectory DB so workspace data/vacation_planner.db is never touched
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db = Path(tmpdir) / "wal_disk_check.db"
            disk_repo = SQLiteRepository(db_path=temp_db, auto_seed=True)
            health = disk_repo.get_health_status()
            self.assertEqual(health["status"], "ok")
            self.assertTrue(health["wal_mode"])
            self.assertEqual(health["journal_mode"], "wal")
            self.assertEqual(health["tables_count"], 11)
            self.assertTrue(Path(disk_repo.db_path).exists())

            expected_tables = [
                "auth_sessions",
                "child_frameworks",
                "elal_bonus_availability",
                "family_profiles",
                "flight_itineraries",
                "flight_search_queries",
                "moe_vacation_windows",
                "oauth_login_states",
                "passenger_loyalty_wallets",
                "users",
                "vacation_option_proposals",
            ]
            self.assertEqual(disk_repo.list_tables(), expected_tables)

            indexes = disk_repo.list_indexes()
            for expected_idx in (
                "idx_users_email",
                "idx_auth_sessions_user_id",
                "idx_auth_sessions_expires",
                "idx_family_profiles_user_id",
                "idx_loyalty_wallets_profile_pax",
                "idx_moe_vacation_year_framework",
                "idx_elal_bonus_route_date",
                "idx_proposals_query_rank",
            ):
                self.assertIn(expected_idx, indexes)
            disk_repo.close()

    def test_sqlite_check_constraints_and_foreign_key_cascade_f01_f08(self) -> None:
        with self.repo.connection() as conn:
            # Invalid adults_count (must be BETWEEN 1 AND 6)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO family_profiles (id, adults_count) VALUES ('bad-prof-1', 0)"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO family_profiles (id, adults_count) VALUES ('bad-prof-2', 7)"
                )

            # Invalid LoyaltyProgramCode in passenger_loyalty_wallets
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO passenger_loyalty_wallets (
                        id, family_profile_id, passenger_id, passenger_name, program_code, available_points
                    ) VALUES ('bad-w-1', 'default-family-profile', 'ADULT_1', 'Test', 'INVALID_CLUB', 1000)
                    """
                )

            # Negative available_points
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO passenger_loyalty_wallets (
                        id, family_profile_id, passenger_id, passenger_name, program_code, available_points
                    ) VALUES ('bad-w-2', 'default-family-profile', 'ADULT_1', 'Test', 'ELAL_MATMID', -50)
                    """
                )

            # Invalid child_age_years (> 21)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO child_frameworks (
                        id, family_profile_id, child_name, child_age_years, passenger_Current_type
                    ) VALUES ('bad-c-1', 'default-family-profile', 'Test', 25, 'YOUTH')
                    """
                )

            # Valid NULL framework_type in child_frameworks (`F03`, `F12`)
            conn.execute(
                """
                INSERT INTO child_frameworks (
                    id, family_profile_id, child_name, child_age_years, passenger_Current_type, framework_type
                ) VALUES ('null-fw-child', 'default-family-profile', 'תינוק', 1, 'INFANT_LAP', NULL)
                """
            )

        # Test ON DELETE CASCADE across family_profiles -> children, wallets, queries, itineraries, proposals
        temp_prof = FamilyProfile(
            id="cascade-test-profile",
            profile_name="משפחת בדיקה",
            adults_count=2,
            children=[
                ChildFramework(
                    id="cascade-child-1",
                    family_profile_id="cascade-test-profile",
                    child_name="ילד",
                    child_age_years=7,
                    framework_type=None,
                )
            ],
            passenger_loyalty_wallets=[
                PassengerLoyaltyWallet(
                    id="cascade-wallet-1",
                    family_profile_id="cascade-test-profile",
                    passenger_id="ADULT_1",
                    passenger_name="הורה",
                    program_code=LoyaltyProgramCode.ELAL_MATMID,
                    available_points=50000,
                )
            ],
        )
        self.repo.save_profile(temp_prof)

        query = FlightSearchQuery(
            id="cascade-query-1",
            family_profile_id="cascade-test-profile",
            date_selection_mode=DateSelectionMode.SPECIFIC_DATES,
            airline_selection_mode=AirlineSelectionMode.EL_AL_ONLY,
            destination_iatas=["FCO"],
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
        )
        itin = FlightItinerary(
            id="cascade-itin-1",
            search_query_id="cascade-query-1",
            origin_iata="TLV",
            destination_iata="FCO",
            return_origin_iata="FCO",
            destination_city_he="רומא",
            destination_city_en="Rome",
            departure_date=date(2027, 4, 11),
            return_date=date(2027, 4, 18),
            trip_nights=7,
            primary_carrier_iata="LY",
            is_elal_flight=True,
            utilizes_elal_bonus=True,
            fulfillment_strategy=FulfillmentStrategy.HYBRID_BONUS_PLUS_CASH,
            outbound_legs=[FlightLeg(flight_number="LY381", flight_date=date(2027, 4, 11))],
            inbound_legs=[FlightLeg(flight_number="LY384", flight_date=date(2027, 4, 18))],
            seated_passengers_count=4,
            bonus_tickets_count=4,
            cash_tickets_count=0,
            primary_cabin="ECONOMY",
            total_matmid_points=142000,
            total_taxes_and_fees_usd=390.0,
            total_supplemental_cash_fares_usd=460.0,
            total_out_of_pocket_cash_usd=850.0,
            full_cash_benchmark_usd=2950.0,
            net_cash_saved_usd=2100.0,
            cents_per_point_value=1.48,
        )
        prop = VacationOptionProposal(
            id="cascade-prop-1",
            search_query_id="cascade-query-1",
            itinerary_id="cascade-itin-1",
            associated_holiday_codes=["PESACH"],
            window_set_type="SPECIFIC_USER_WINDOW",
            school_absence_penalty=1.17,
            childcare_coverage_gain=0.75,
            holiday_alignment_score=88.0,
            flight_bonus_value_score=92.0,
            combined_trip_optimization_score=95.0,
            explanation_summary_he="בדיקת מחיקה מדורגת",
            itinerary=itin,
        )
        self.repo.save_search_results(query, [prop])
        self.assertIsNotNone(self.repo.get_proposal_by_id("cascade-prop-1"))

        deleted = self.repo.delete_profile("cascade-test-profile")
        self.assertTrue(deleted)
        self.assertIsNone(self.repo.get_profile("cascade-test-profile"))
        self.assertIsNone(self.repo.get_proposal_by_id("cascade-prop-1"))

    # ------------------------------------------------------------------
    # Canonical Calendar Tests (`TEST-CAL-01`, `TEST-CAL-02`, `TEST-CAL-03`)
    # ------------------------------------------------------------------
    def test_cal_01_isru_chag_sukkot_divergence(self) -> None:
        """TEST-CAL-01: Isru Chag Sukkot (`2025-10-15` & `2026-10-04`) K-9 vs 10-12 divergence."""
        gan_child = ChildFramework(
            child_name="נועה", child_age_years=5, framework_type=MoEFrameworkType.MUNICIPAL_GAN
        )
        elem_child = ChildFramework(
            child_name="עידו", child_age_years=9, framework_type=MoEFrameworkType.ELEMENTARY_4_6
        )
        mid_child = ChildFramework(
            child_name="מאיה", child_age_years=13, framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9
        )
        high_child = ChildFramework(
            child_name="תומר", child_age_years=16, framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12
        )

        for isru_chag_date in (date(2025, 10, 15), date(2026, 10, 4), date(2027, 10, 24)):
            s_gan = self.calendar_service.get_child_day_status(gan_child, isru_chag_date)
            s_elem = self.calendar_service.get_child_day_status(elem_child, isru_chag_date)
            s_mid = self.calendar_service.get_child_day_status(mid_child, isru_chag_date)
            s_high = self.calendar_service.get_child_day_status(high_child, isru_chag_date)

            self.assertEqual(s_gan.status, "SCHOOL_REGULAR")
            self.assertAlmostEqual(s_gan.penalty_psi, 1.0)

            self.assertEqual(s_elem.status, "SCHOOL_REGULAR")
            self.assertAlmostEqual(s_elem.penalty_psi, 1.0)

            # Crucial Middle School Hybrid Rule: follows Elementary on Isru Chag Sukkot!
            self.assertEqual(s_mid.status, "SCHOOL_REGULAR")
            self.assertAlmostEqual(s_mid.penalty_psi, 1.0)

            # High School 10-12 has official vacation on Isru Chag Sukkot
            self.assertEqual(s_high.status, "VACATION")
            self.assertAlmostEqual(s_high.penalty_psi, 0.0)

    def test_cal_02_june_20_to_30_inter_framework_window(self) -> None:
        """TEST-CAL-02: June 20-30 split in 2026 (Sat shift) and 2027 (Sun)."""
        mid_5day = ChildFramework(
            child_name="מאיה",
            child_age_years=13,
            framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9,
            school_week_days=5,
        )
        high_6day = ChildFramework(
            child_name="תומר",
            child_age_years=16,
            framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12,
            school_week_days=6,
        )
        elem_5day = ChildFramework(
            child_name="עידו",
            child_age_years=9,
            framework_type=MoEFrameworkType.ELEMENTARY_4_6,
            school_week_days=5,
        )
        gan_6day = ChildFramework(
            child_name="נועה",
            child_age_years=5,
            framework_type=MoEFrameworkType.MUNICIPAL_GAN,
            school_week_days=6,
        )

        # 2026: June 20, 2026 is Saturday -> 5-day ends Thu Jun 18; 6-day ends Fri Jun 19
        self.assertEqual(
            self.calendar_service.get_child_day_status(mid_5day, date(2026, 6, 18)).status,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(mid_5day, date(2026, 6, 19)).status,
            "VACATION",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(high_6day, date(2026, 6, 19)).status,
            "SCHOOL_FRIDAY",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(high_6day, date(2026, 6, 21)).status,
            "VACATION",
        )

        # 2027: June 20, 2027 is Sunday -> last school day is Sun Jun 20; vacation starts Mon Jun 21
        self.assertEqual(
            self.calendar_service.get_child_day_status(mid_5day, date(2027, 6, 20)).status,
            "SCHOOL_REGULAR",
        )
        for d_day in range(21, 31):
            st_mid = self.calendar_service.get_child_day_status(
                mid_5day, date(2027, 6, d_day)
            )
            self.assertEqual(st_mid.status, "VACATION")
            self.assertAlmostEqual(st_mid.penalty_psi, 0.0)

        # Elementary & Gan study until June 30 with SCHOOL_END_OF_YEAR_WANING (psi=0.50) on Sun-Thu
        for waning_date in (date(2026, 6, 22), date(2027, 6, 21), date(2027, 6, 30)):
            st_elem = self.calendar_service.get_child_day_status(elem_5day, waning_date)
            st_gan = self.calendar_service.get_child_day_status(gan_6day, waning_date)
            self.assertEqual(st_elem.status, "SCHOOL_END_OF_YEAR_WANING")
            self.assertAlmostEqual(st_elem.penalty_psi, 0.50)
            self.assertEqual(st_gan.status, "SCHOOL_END_OF_YEAR_WANING")
            self.assertAlmostEqual(st_gan.penalty_psi, 0.50)

        # On July 1, Elementary & Gan enter summer vacation
        self.assertEqual(
            self.calendar_service.get_child_day_status(elem_5day, date(2027, 7, 1)).status,
            "VACATION",
        )

    def test_lag_baomer_divergence_5786_vs_5787(self) -> None:
        """Lag BaOmer is off ONLY for High School in תשפ"ו (`2026-05-05`) and regular for ALL in תשפ"ז (`2027-05-25`)."""
        mid_child = ChildFramework(
            child_name="מאיה", child_age_years=13, framework_type=MoEFrameworkType.MIDDLE_SCHOOL_7_9
        )
        high_child = ChildFramework(
            child_name="תומר", child_age_years=16, framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12
        )

        # 2026-05-05 (תשפ"ו)
        self.assertEqual(
            self.calendar_service.get_child_day_status(mid_child, date(2026, 5, 5)).status,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(high_child, date(2026, 5, 5)).status,
            "VACATION",
        )

        # 2027-05-25 (תשפ"ז)
        self.assertEqual(
            self.calendar_service.get_child_day_status(mid_child, date(2027, 5, 25)).status,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(high_child, date(2027, 5, 25)).status,
            "SCHOOL_REGULAR",
        )

    def test_cal_03_tlv_yom_kippur_shutdown_blocker(self) -> None:
        """TEST-CAL-03: TLV Yom Kippur total shutdown blocks departures/returns on YK dates."""
        for yk_d in (
            date(2025, 10, 1),
            date(2025, 10, 2),
            date(2026, 9, 20),
            date(2026, 9, 21),
            date(2027, 10, 10),
            date(2027, 10, 11),
        ):
            self.assertTrue(self.calendar_service.is_tlv_airport_closed(yk_d))

        self.assertFalse(self.calendar_service.is_tlv_airport_closed(date(2026, 9, 22)))

        matrix = self.calendar_service.get_daily_status_matrix(
            self.profile, date(2026, 9, 19), date(2026, 9, 25)
        )
        self.assertTrue(matrix.tlv_airport_closed_by_date["2026-09-20"])
        self.assertTrue(matrix.tlv_airport_closed_by_date["2026-09-21"])
        self.assertFalse(matrix.tlv_airport_closed_by_date["2026-09-22"])

        # Candidate window generation for YOM_KIPPUR_SUKKOT 2026 must exclude Sep 20-21 endpoints
        q = FlightSearchQuery(
            date_selection_mode=DateSelectionMode.HOLIDAY_DIRECT_INTENT,
            direct_holiday_code="YOM_KIPPUR_SUKKOT",
            direct_target_year=2026,
            min_trip_nights=5,
            max_trip_nights=12,
        )
        cands = self.maximizer.generate_candidate_windows(q, self.profile)
        self.assertGreater(len(cands), 0)
        for c in cands:
            self.assertNotIn(c.start_date, (date(2026, 9, 20), date(2026, 9, 21)))
            self.assertNotIn(c.end_date, (date(2026, 9, 20), date(2026, 9, 21)))

    # ------------------------------------------------------------------
    # Optimization & Worked Examples Tests (`TEST-OPT-01`, `F12`-`F15`)
    # ------------------------------------------------------------------
    def test_opt_01_pesach_2027_uncovered_vs_nitzanim_week(self) -> None:
        """TEST-OPT-01: Pesach 2027 uncovered week (`HAS=100.0`) vs Nitzanim pre-Pesach week."""
        uncovered = self.maximizer.evaluate_window(
            self.profile, date(2027, 4, 20), date(2027, 4, 28)
        )
        self.assertEqual(uncovered.school_absence_penalty, 0.0)
        self.assertEqual(uncovered.childcare_coverage_gain, 1.0)
        self.assertEqual(uncovered.holiday_alignment_score, 100.0)

        # Pre-Pesach Nitzanim week (`2027-04-13` to `2027-04-19`) with treat_camp_as_vacation=True (psi=0.15)
        nitz_vac = self.maximizer.evaluate_window(
            self.profile, date(2027, 4, 13), date(2027, 4, 19)
        )
        noa_impact_vac = next(
            imp for imp in nitz_vac.per_child_impact if imp.child_name == "נועה"
        )
        self.assertEqual(noa_impact_vac.nitzanim_days_overlapped, 5)

        # Now toggle treat_camp_as_vacation=False (psi=0.75) for Noa
        prof_care = FamilyProfile.from_dict(self.profile.to_dict())
        prof_care.children[0].treat_camp_as_vacation = False
        nitz_care = self.maximizer.evaluate_window(
            prof_care, date(2027, 4, 13), date(2027, 4, 19)
        )

        self.assertGreater(
            nitz_care.school_absence_penalty, nitz_vac.school_absence_penalty
        )
        self.assertLess(
            nitz_care.holiday_alignment_score,
            nitz_vac.holiday_alignment_score,
        )
        self.assertLess(
            nitz_vac.holiday_alignment_score,
            uncovered.holiday_alignment_score,
        )

    def test_worked_examples_1_through_6_exact_math_f15(self) -> None:
        """Verify all 6 Worked Examples PTO-free HAS, SAP, and CCG math."""
        examples = self.maximizer.evaluate_worked_examples(self.profile)

        # Ex 1: Kippur-Sukkot Mega-Bridge (Tue Sep 22 - Sat Oct 3, 2026)
        ex1 = examples["EX1_KIPPUR_SUKKOT_MEGA_BRIDGE"]
        self.assertEqual(ex1.trip_nights, 11)
        self.assertAlmostEqual(ex1.school_absence_penalty, 0.00, places=2)
        self.assertAlmostEqual(ex1.childcare_coverage_gain, 1.00, places=2)
        self.assertAlmostEqual(ex1.holiday_alignment_score, 100.0, places=1)

        # Ex 2: Hanukkah Post-Nitzanim Shift (Thu Dec 10 - Mon Dec 14, 2026)
        ex2 = examples["EX2_HANUKKAH_POST_NITZANIM_SHIFT"]
        self.assertEqual(ex2.trip_nights, 4)
        self.assertAlmostEqual(ex2.school_absence_penalty, 0.68, places=2)
        self.assertAlmostEqual(ex2.childcare_coverage_gain, 0.73, places=2)
        self.assertAlmostEqual(ex2.holiday_alignment_score, 62.5, places=1)

        # Ex 3: Purim Long-Weekend Bridge (Tue Mar 23 - Sat Mar 27, 2027)
        ex3 = examples["EX3_PURIM_LONG_WEEKEND_BRIDGE"]
        self.assertEqual(ex3.trip_nights, 4)
        self.assertAlmostEqual(ex3.school_absence_penalty, 0.69, places=2)
        self.assertAlmostEqual(ex3.childcare_coverage_gain, 0.77, places=2)
        self.assertAlmostEqual(ex3.holiday_alignment_score, 64.8, places=1)

        # Ex 4A: Pesach Pre-Holiday Shoulder Bridge (Sun Apr 11 - Sun Apr 18, 2027)
        ex4a = examples["EX4A_PESACH_PRE_HOLIDAY_SHOULDER"]
        self.assertEqual(ex4a.trip_nights, 7)
        self.assertAlmostEqual(ex4a.school_absence_penalty, 1.17, places=2)
        self.assertAlmostEqual(ex4a.childcare_coverage_gain, 0.75, places=2)
        self.assertAlmostEqual(ex4a.holiday_alignment_score, 68.4, places=1)

        # Ex 4B: Pesach Uncovered Week
        ex4b = examples["EX4B_PESACH_UNCOVERED_WEEK"]
        self.assertAlmostEqual(ex4b.holiday_alignment_score, 100.0, places=1)

        # Ex 5: Shavuot Extended Weekend (Wed Jun 9 - Sat Jun 12, 2027)
        ex5 = examples["EX5_SHAVUOT_EXTENDED_WEEKEND"]
        self.assertEqual(ex5.trip_nights, 3)
        self.assertAlmostEqual(ex5.school_absence_penalty, 0.67, places=2)
        self.assertAlmostEqual(ex5.childcare_coverage_gain, 0.75, places=2)
        self.assertAlmostEqual(ex5.holiday_alignment_score, 67.5, places=1)

        # Ex 6: June 20-30 Inter-Framework Arbitrage (Mon Jun 21 - Mon Jun 28, 2027)
        ex6 = examples["EX6_JUNE_20_30_INTER_FRAMEWORK_ARBITRAGE"]
        self.assertEqual(ex6.trip_nights, 7)
        self.assertAlmostEqual(ex6.school_absence_penalty, 0.83, places=2)
        self.assertAlmostEqual(ex6.childcare_coverage_gain, 0.58, places=2)
        self.assertAlmostEqual(ex6.holiday_alignment_score, 37.5, places=1)

    def test_mode1_specific_dates_with_null_frameworks_f12(self) -> None:
        """Mode 1 (`SPECIFIC_DATES`) works when children have `framework_type=None`."""
        mode1_profile = FamilyProfile(
            id="mode1-null-fw",
            adults_count=2,
            children=[
                ChildFramework(child_name="ילד 1", child_age_years=4, framework_type=None),
                ChildFramework(child_name="ילד 2", child_age_years=10, framework_type=None),
                ChildFramework(child_name="ילד 3", child_age_years=15, framework_type=None),
            ],
        )
        self.assertEqual(mode1_profile.children[0].passenger_Current_type, "CHILD")
        self.assertEqual(mode1_profile.children[2].passenger_Current_type, "YOUTH")

        q = FlightSearchQuery(
            date_selection_mode=DateSelectionMode.SPECIFIC_DATES,
            specific_departure_date=date(2027, 4, 11),
            specific_return_date=date(2027, 4, 18),
            flex_days_plus_minus=2,
        )
        windows = self.maximizer.generate_candidate_windows(q, mode1_profile)
        self.assertGreater(len(windows), 0)
        self.assertEqual(windows[0].start_date, date(2027, 4, 11))
        self.assertEqual(windows[0].end_date, date(2027, 4, 18))
        self.assertEqual(windows[0].school_absence_penalty, 0.0)
        self.assertEqual(windows[0].window_set_type, "SPECIFIC_USER_WINDOW")

    def test_mode3_all_11_holidays_and_future_years_auto_updater_f11_f14(self) -> None:
        """Mode 3 resolves all 11 holidays and auto-projects future years (`2028`, `2029`, `2032`)."""
        all_11_holidays = [
            "PESACH",
            "SUKKOT",
            "YOM_KIPPUR_SUKKOT",
            "HANUKKAH",
            "ROSH_HASHANAH",
            "PURIM",
            "SHAVUOT",
            "YOM_HAATZMAUT",
            "SUMMER_JUNE_20_30",
            "SUMMER_JULY",
            "SUMMER_AUGUST",
        ]
        for h_code in all_11_holidays:
            q = FlightSearchQuery(
                date_selection_mode=DateSelectionMode.HOLIDAY_DIRECT_INTENT,
                direct_holiday_code=h_code,
                direct_target_year=2027,
                min_trip_nights=3,
                max_trip_nights=10,
                max_bridge_days_shift=3,
            )
            wins = self.maximizer.generate_candidate_windows(q, self.profile)
            self.assertGreater(
                len(wins), 0, f"Expected candidate windows for Mode 3 holiday {h_code}"
            )

        # Future-year projection via MoECalendarAutoUpdaterService (`2028-2029` & `2031-2032`)
        sync_28_29 = self.auto_updater.sync_school_year("2028-2029")
        self.assertEqual(sync_28_29.school_year, "2028-2029")
        self.assertEqual(sync_28_29.school_year_hebrew, 'תשפ"ט')
        self.assertEqual(sync_28_29.calendar_sync_source, "HEBREW_RULE_PROJECTED")
        self.assertGreaterEqual(sync_28_29.windows_synced_count, 60)

        # Mode 3 search for Pesach 2029
        q_2029 = FlightSearchQuery(
            date_selection_mode=DateSelectionMode.HOLIDAY_DIRECT_INTENT,
            direct_holiday_code="PESACH",
            direct_target_year=2029,
            min_trip_nights=5,
            max_trip_nights=9,
        )
        wins_2029 = self.maximizer.generate_candidate_windows(q_2029, self.profile)
        self.assertGreater(len(wins_2029), 0)
        self.assertTrue(all(w.start_date.year == 2029 for w in wins_2029))

    def test_seeded_2025_2028_elal_bonus_and_commercial_flights_f16(self) -> None:
        """Verify canonical flagship flights (`LY381`/`LY384`, `LY541`/`LY544`, `LY395`/`LY398`, `LY387`/`LY388`, `LHR` vs `LTN`)."""
        # Option A: Rome LY381 (2027-04-11) & LY384 (2027-04-18)
        fco_rows = {
            r.id: r
            for r in self.repo.get_cached_elal_bonus(
                ["FCO"], "2027-04-11", "2027-04-18"
            )
        }
        self.assertIn("LY381_2027-04-11", fco_rows)
        self.assertIn("LY384_2027-04-18", fco_rows)
        ly381 = fco_rows["LY381_2027-04-11"]
        self.assertEqual(ly381.economy_award_seats, 2)
        self.assertTrue(ly381.economy_seats_is_two_plus)
        self.assertEqual(ly381.premium_award_seats, 2)
        self.assertEqual(ly381.business_award_seats, 0)
        self.assertEqual(ly381.economy_points_per_pax, 15000)
        self.assertEqual(ly381.premium_points_per_pax, 20500)
        self.assertAlmostEqual(ly381.taxes_usd_per_pax, 48.75)

        ly384 = fco_rows["LY384_2027-04-18"]
        self.assertEqual(ly384.economy_award_seats, 2)
        self.assertEqual(ly384.premium_award_seats, 1)
        self.assertEqual(ly384.business_award_seats, 2)

        # Option B: Athens LY541 (2026-12-06) & LY544 (2026-12-11)
        ath_rows = {
            r.id: r
            for r in self.repo.get_cached_elal_bonus(
                ["ATH"], "2026-12-06", "2026-12-12"
            )
        }
        self.assertIn("LY541_2026-12-06", ath_rows)
        self.assertIn("LY544_2026-12-11", ath_rows)
        self.assertEqual(ath_rows["LY541_2026-12-06"].economy_points_per_pax, 8500)
        self.assertEqual(ath_rows["LY541_2026-12-06"].business_points_per_pax, 16000)
        # Peak return 2026-12-12 has 0 seats for Cash & Points demonstration
        self.assertEqual(ath_rows["LY544_2026-12-12"].economy_award_seats, 0)

        # Option C: Madrid LY395 (2027-06-21) & LY398 (2027-06-28)
        mad_rows = {
            r.id: r
            for r in self.repo.get_cached_elal_bonus(
                ["MAD"], "2027-06-21", "2027-06-28"
            )
        }
        self.assertIn("LY395_2027-06-21", mad_rows)
        self.assertIn("LY398_2027-06-28", mad_rows)
        self.assertEqual(mad_rows["LY395_2027-06-21"].economy_points_per_pax, 16250)
        self.assertEqual(mad_rows["LY395_2027-06-21"].premium_points_per_pax, 21250)

        # Open-Jaw Milan LY387 (2027-04-11) & LY388 (2027-04-18)
        mxp_rows = {
            r.id: r
            for r in self.repo.get_cached_elal_bonus(
                ["MXP"], "2027-04-11", "2027-04-18"
            )
        }
        self.assertEqual(mxp_rows["LY387_2027-04-11"].economy_award_seats, 2)
        self.assertEqual(mxp_rows["LY388_2027-04-18"].economy_award_seats, 0)

        # LHR UK APD ($165) vs LTN ($82) inbound taxes
        lon_rows = {
            r.id: r
            for r in self.repo.get_cached_elal_bonus(
                ["LHR", "LTN"], "2027-04-18", "2027-04-18", direction="INBOUND"
            )
        }
        self.assertAlmostEqual(lon_rows["LY316_2027-04-18"].taxes_usd_per_pax, 165.0)
        self.assertAlmostEqual(lon_rows["LY312_2027-04-18"].taxes_usd_per_pax, 82.0)

    def test_all_8_moe_frameworks_and_bagrut_blackouts_f09(self) -> None:
        """Verify DAYCARE_SUPERVISED (Aug 8), SPECIAL_ED (Aug 15), ELEMENTARY_1_3 (Nitzanim), and Bagrut blackouts."""
        daycare_child = ChildFramework(
            child_name="תינוק",
            child_age_years=2,
            framework_type=MoEFrameworkType.DAYCARE_SUPERVISED,
            school_week_days=6,
        )
        special_ed_child = ChildFramework(
            child_name="ילד חנ\"מ",
            child_age_years=8,
            framework_type=MoEFrameworkType.SPECIAL_ED,
            school_week_days=5,
        )
        elem_1_3_child = ChildFramework(
            child_name="אורי",
            child_age_years=7,
            framework_type=MoEFrameworkType.ELEMENTARY_1_3,
            holiday_extension_mode=HolidayExtensionMode.NITZANIM_FULL_WITH_JULY,
            treat_camp_as_vacation=True,
        )
        high_bagrut = ChildFramework(
            child_name="שירה",
            child_age_years=17,
            framework_type=MoEFrameworkType.HIGH_SCHOOL_10_12,
            bagrut_blackout_dates=[date(2027, 6, 23)],
        )

        # Daycare operates Aug 1-8 and starts vacation Aug 9
        self.assertEqual(
            self.calendar_service.get_child_day_status(daycare_child, date(2027, 8, 5)).status,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(daycare_child, date(2027, 8, 9)).status,
            "VACATION",
        )

        # Special Ed operates Aug 1-15 and starts vacation Aug 16
        self.assertEqual(
            self.calendar_service.get_child_day_status(special_ed_child, date(2027, 8, 12)).status,
            "SCHOOL_REGULAR",
        )
        self.assertEqual(
            self.calendar_service.get_child_day_status(special_ed_child, date(2027, 8, 16)).status,
            "VACATION",
        )

        # Elementary 1-3 has CAMP_OPTIONAL in July Nitzanim
        self.assertEqual(
            self.calendar_service.get_child_day_status(elem_1_3_child, date(2027, 7, 11)).status,
            "CAMP_OPTIONAL",
        )

        # High School Bagrut blackout date returns EXAM_BLACKOUT and disqualifies window
        st_bagrut = self.calendar_service.get_child_day_status(
            high_bagrut, date(2027, 6, 23)
        )
        self.assertEqual(st_bagrut.status, "EXAM_BLACKOUT")
        self.assertGreater(st_bagrut.penalty_psi, 1000.0)

        prof_with_bagrut = FamilyProfile(
            id="bagrut-prof",
            adults_count=2,
            children=[high_bagrut],
        )
        eval_bagrut = self.maximizer.evaluate_window(
            prof_with_bagrut, date(2027, 6, 21), date(2027, 6, 25)
        )
        self.assertTrue(eval_bagrut.has_bagrut_blackout)
        self.assertEqual(eval_bagrut.holiday_alignment_score, 0.0)

    def test_mode2_sets_i_icamp_u_and_zero_pto_window_f13_f15(self) -> None:
        """Verify sets I, I_camp, U in June 21-30 and full school break HAS=100.0 on Rosh Hashanah."""
        matrix = self.calendar_service.get_daily_status_matrix(
            self.profile, date(2027, 6, 21), date(2027, 6, 28)
        )
        # During Jun 21-28, Maya (MIDDLE_SCHOOL_7_9) is on summer vacation -> all 8 days are in Set U
        self.assertEqual(len(matrix.framework_delta_union_dates), 8)
        # Only Saturday Jun 26 has all 3 children strictly on VACATION -> Set I has 1 day
        self.assertEqual(matrix.strict_intersection_dates, [date(2027, 6, 26)])

        # Full holiday window: Rosh Hashanah 2026 (Fri Sep 11 - Sun Sep 13, 2026)
        rh_win = self.maximizer.evaluate_window(
            self.profile, date(2026, 9, 11), date(2026, 9, 13)
        )
        self.assertEqual(rh_win.school_absence_penalty, 0.0)
        self.assertEqual(rh_win.holiday_alignment_score, 100.0)

    def test_all_10_loyalty_programs_and_env_db_path_f02_f16(self) -> None:
        """Verify all 10 LoyaltyProgramCode values persist and seeded El Al flights obey Shabbat/YK."""
        wallets = [
            PassengerLoyaltyWallet(
                passenger_id="ADULT_1",
                passenger_name="יוני",
                program_code=code,
                available_points=25000,
                can_pool_with_family=True,
            )
            for code in LoyaltyProgramCode
        ]
        self.assertEqual(len(wallets), 10)
        prof_10 = FamilyProfile(
            id="ten-clubs-prof",
            profile_name="10 מועדונים",
            adults_count=2,
            passenger_loyalty_wallets=wallets,
        )
        saved_10 = self.repo.save_profile(prof_10)
        self.assertEqual(len(saved_10.passenger_loyalty_wallets), 10)

        # Verify zero seeded El Al / Sun d'Or flights violate Shabbat or Yom Kippur
        all_bonus = self.repo.get_cached_elal_bonus()
        self.assertGreater(len(all_bonus), 200)
        for row in all_bonus:
            self.assertFalse(
                self.calendar_service.is_tlv_airport_closed(row.flight_date),
                f"Bonus row {row.id} should not exist on Yom Kippur shutdown date",
            )
            wd = row.flight_date.weekday()
            dep_hour = int(row.departure_time_local.split(":")[0])
            arr_hour = int(row.arrival_time_local.split(":")[0])
            if wd == 4:
                self.assertLess(dep_hour, 14, f"Friday flight {row.id} departs after 14:00")
                self.assertLess(arr_hour, 14, f"Friday flight {row.id} arrives after 14:00")
                self.assertGreaterEqual(
                    arr_hour,
                    dep_hour,
                    f"Friday flight {row.id} rolls overnight into Saturday Shabbat",
                )
            if wd == 5:
                self.assertGreaterEqual(
                    dep_hour, 21, f"Saturday flight {row.id} departs before Motzei Shabbat"
                )

        # Verify VACATION_PLANNER_DB_PATH environment variable override
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_db = str(Path(tmpdir) / "custom_env.db")
            old_env = os.environ.get("VACATION_PLANNER_DB_PATH")
            try:
                os.environ["VACATION_PLANNER_DB_PATH"] = custom_db
                self.assertEqual(resolve_db_path(), custom_db)
                env_repo = SQLiteRepository(auto_seed=True)
                self.assertEqual(env_repo.db_path, custom_db)
                self.assertEqual(env_repo.get_health_status()["tables_count"], 11)
                env_repo.close()
            finally:
                if old_env is None:
                    os.environ.pop("VACATION_PLANNER_DB_PATH", None)
                else:
                    os.environ["VACATION_PLANNER_DB_PATH"] = old_env

    def test_ttl_cache_tier1_4h_and_tier2_6h_freshness_and_expiration_f06_f07(self) -> None:
        """Verify 4h (14,400s) Tier-1 El Al bonus cache and 6h (21,600s) Tier-2 itinerary/proposal cache."""
        cache_repo = SQLiteRepository(":memory:", auto_seed=False)
        try:
            # 1. Tier-1 4h (14,400s) upsert using dict without expires_at
            cache_repo.upsert_elal_bonus(
                [
                    {
                        "id": "LY381_2027-11-15",
                        "origin_iata": "TLV",
                        "destination_iata": "FCO",
                        "direction": "OUTBOUND",
                        "flight_number": "LY381",
                        "flight_date": "2027-11-15",
                        "economy_award_seats": 2,
                    }
                ],
                ttl_seconds=14400,
            )
            self.assertTrue(
                cache_repo.is_elal_bonus_cache_fresh(
                    ["FCO"], date(2027, 11, 15), date(2027, 11, 15)
                )
            )

            # Expire via ttl_seconds=-60
            cache_repo.upsert_elal_bonus(
                [
                    {
                        "id": "LY381_2027-11-15",
                        "origin_iata": "TLV",
                        "destination_iata": "FCO",
                        "direction": "OUTBOUND",
                        "flight_number": "LY381",
                        "flight_date": "2027-11-15",
                        "economy_award_seats": 2,
                    }
                ],
                ttl_seconds=-60,
            )
            self.assertFalse(
                cache_repo.is_elal_bonus_cache_fresh(
                    ["FCO"], date(2027, 11, 15), date(2027, 11, 15)
                )
            )

            # 2. Tier-1 4h upsert using ElAlBonusAvailability instance with default expires_at
            obj_rec = ElAlBonusAvailability(
                id="LY541_2027-11-16",
                origin_iata="TLV",
                destination_iata="ATH",
                direction="OUTBOUND",
                flight_number="LY541",
                flight_date=date(2027, 11, 16),
                economy_award_seats=2,
            )
            self.assertEqual(obj_rec.expires_at, "")
            cache_repo.upsert_elal_bonus([obj_rec], ttl_seconds=14400)
            self.assertTrue(
                cache_repo.is_elal_bonus_cache_fresh(
                    ["ATH"], date(2027, 11, 16), date(2027, 11, 16)
                )
            )
            cache_repo.upsert_elal_bonus([obj_rec], ttl_seconds=-60)
            self.assertFalse(
                cache_repo.is_elal_bonus_cache_fresh(
                    ["ATH"], date(2027, 11, 16), date(2027, 11, 16)
                )
            )

            # 3. Tier-2 6h (21,600s) itinerary & proposal cache freshness and expiration
            cache_repo.save_profile(build_default_family_profile())
            q = FlightSearchQuery(
                id="tier2-cache-q1",
                family_profile_id="default-family-profile",
                date_selection_mode=DateSelectionMode.SPECIFIC_DATES,
                airline_selection_mode=AirlineSelectionMode.EL_AL_ONLY,
                destination_iatas=["FCO"],
                specific_departure_date=date(2027, 4, 11),
                specific_return_date=date(2027, 4, 18),
            )
            itin = FlightItinerary(
                id="tier2-cache-itin1",
                search_query_id="tier2-cache-q1",
                origin_iata="TLV",
                destination_iata="FCO",
                return_origin_iata="FCO",
                destination_city_he="רומא",
                destination_city_en="Rome",
                departure_date=date(2027, 4, 11),
                return_date=date(2027, 4, 18),
                trip_nights=7,
                primary_carrier_iata="LY",
                is_elal_flight=True,
                utilizes_elal_bonus=True,
                fulfillment_strategy=FulfillmentStrategy.FULL_BONUS_SAME_CABIN,
                total_out_of_pocket_cash_usd=487.5,
                full_cash_benchmark_usd=2950.0,
            )
            prop = VacationOptionProposal(
                id="tier2-cache-prop1",
                search_query_id="tier2-cache-q1",
                itinerary_id="tier2-cache-itin1",
                associated_holiday_codes=["PESACH"],
                window_set_type="SPECIFIC_USER_WINDOW",
                school_absence_penalty=1.17,
                childcare_coverage_gain=0.75,
                holiday_alignment_score=85.0,
                flight_bonus_value_score=91.0,
                combined_trip_optimization_score=87.6,
                explanation_summary_he="בדיקת מטמון שכבה 2",
                itinerary=itin,
            )
            cache_repo.save_search_results(q, [prop])
            self.assertTrue(
                cache_repo.is_itinerary_cache_fresh(
                    search_query_id="tier2-cache-q1", ttl_seconds=21600
                )
            )
            self.assertEqual(
                len(
                    cache_repo.get_cached_proposals_for_query(
                        "tier2-cache-q1", ttl_seconds=21600
                    )
                ),
                1,
            )
            self.assertFalse(
                cache_repo.is_itinerary_cache_fresh(
                    search_query_id="tier2-cache-q1", ttl_seconds=-60
                )
            )
            self.assertEqual(
                len(
                    cache_repo.get_cached_proposals_for_query(
                        "tier2-cache-q1", ttl_seconds=-60
                    )
                ),
                0,
            )
        finally:
            cache_repo.close()

    def test_friday_shabbat_arrival_and_overnight_saturday_landing_guard_f16(self) -> None:
        """Verify Friday LY/2U flights never arrive >= 14:00 or roll overnight into Saturday."""
        # Direct unit checks on is_shabbat_blocked_for_elal
        fri = date(2026, 12, 11)
        self.assertEqual(fri.weekday(), 4)
        self.assertTrue(is_shabbat_blocked_for_elal(fri, "13:30", "07:05"))
        self.assertTrue(is_shabbat_blocked_for_elal(fri, "12:30", "18:15"))
        self.assertTrue(is_shabbat_blocked_for_elal(fri, "14:00", "16:30"))
        self.assertFalse(is_shabbat_blocked_for_elal(fri, "06:30", "11:15"))

        # Check all Friday rows in build_seeded_elal_bonus_availability()
        seeded_rows = build_seeded_elal_bonus_availability()
        friday_rows = [r for r in seeded_rows if r.flight_date.weekday() == 4]
        self.assertGreater(len(friday_rows), 20)
        for r in friday_rows:
            dep_h = int(r.departure_time_local.split(":")[0])
            arr_h = int(r.arrival_time_local.split(":")[0])
            self.assertLess(dep_h, 14, f"Friday departure violation on {r.id}")
            self.assertLess(arr_h, 14, f"Friday arrival violation on {r.id}")
            self.assertGreaterEqual(
                arr_h, dep_h, f"Friday overnight Saturday violation on {r.id}"
            )
            self.assertFalse(
                is_shabbat_blocked_for_elal(
                    r.flight_date, r.departure_time_local, r.arrival_time_local
                )
            )

        # Check Friday commercial flights across all destinations
        comm_rows = generate_commercial_flights_for_route(
            origin="TLV",
            destinations=list(DESTINATION_CATALOG.keys()),
            departure_date=date(2026, 12, 4),  # Friday
            return_date=date(2026, 12, 11),    # Friday
            airline_selection_mode="EL_AL_ONLY",
        )
        self.assertGreater(len(comm_rows), 10)
        for row in comm_rows:
            if row["primary_carrier_iata"] in ("LY", "2U"):
                dep_out_h = int(row["departure_time_out"].split(":")[0])
                arr_out_h = int(row["arrival_time_out"].split(":")[0])
                dep_in_h = int(row["departure_time_in"].split(":")[0])
                arr_in_h = int(row["arrival_time_in"].split(":")[0])
                self.assertLess(dep_out_h, 14)
                self.assertLess(arr_out_h, 14)
                self.assertGreaterEqual(arr_out_h, dep_out_h)
                self.assertLess(dep_in_h, 14)
                self.assertLess(arr_in_h, 14)
                self.assertGreaterEqual(arr_in_h, dep_in_h)


class TestRun14WorkplaceHolidayCalendarAndCost(unittest.TestCase):
    """Run 14 (M14): Statutory Israeli workplace holiday calendar & 4-bucket workday cost engine."""

    def test_run14_statutory_workplace_holidays_and_knesset_shifts_2025_2029(self) -> None:
        from backend.app.calendar_engine.moe_calendar_service import (
            IsraeliWorkplaceCalendarService,
        )

        expected_codes = [
            "ROSH_HASHANAH",
            "YOM_KIPPUR",
            "SUKKOT_I",
            "CHOL_HAMOED_SUKKOT",
            "SIMCHAT_TORAH",
            "PESACH_I",
            "CHOL_HAMOED_PESACH",
            "PESACH_VII",
            "YOM_HAATZMAUT",
            "SHAVUOT",
        ]

        # Verify 10 chronological statutory periods + exact Knesset Yom HaAtzmaut shifts across 2024-2029
        expected_atzmaut = {
            "2024-2025": "2025-05-01",  # Thu (shifted from Fri 5 Iyar)
            "2025-2026": "2026-04-22",  # Wed
            "2026-2027": "2027-05-12",  # Wed
            "2027-2028": "2028-05-02",  # Tue (shifted from Mon 5 Iyar)
            "2028-2029": "2029-04-19",  # Thu (shifted from Sat 5 Iyar)
        }
        for sy, exp_atz in expected_atzmaut.items():
            periods = IsraeliWorkplaceCalendarService.get_workplace_holidays_for_school_year(sy)
            self.assertEqual([p["holiday_code"] for p in periods], expected_codes)
            by_code = {p["holiday_code"]: p for p in periods}
            self.assertEqual(by_code["YOM_HAATZMAUT"]["start_date"], exp_atz)
            self.assertEqual(by_code["YOM_HAATZMAUT"]["end_date"], exp_atz)
            self.assertEqual(by_code["YOM_HAATZMAUT"]["workplace_status"], "OFFICIAL_HOLIDAY")
            self.assertEqual(by_code["YOM_HAATZMAUT"]["workday_cost_per_day"], 0.0)
            self.assertEqual(by_code["CHOL_HAMOED_SUKKOT"]["calendar_days"], 6)
            self.assertEqual(by_code["CHOL_HAMOED_SUKKOT"]["workplace_status"], "CHOL_HAMOED")
            self.assertEqual(by_code["CHOL_HAMOED_SUKKOT"]["workday_cost_per_day"], 0.5)
            self.assertEqual(by_code["CHOL_HAMOED_PESACH"]["calendar_days"], 5)
            self.assertEqual(by_code["CHOL_HAMOED_PESACH"]["workplace_status"], "CHOL_HAMOED")
            self.assertEqual(by_code["CHOL_HAMOED_PESACH"]["workday_cost_per_day"], 0.5)
            # Chronological ordering & zero "בוגרים" anywhere
            starts = [p["start_date"] for p in periods]
            self.assertEqual(starts, sorted(starts))
            for entry in periods:
                for val in entry.values():
                    self.assertNotIn("בוגרים", str(val))

        # Far-horizon algorithmic support (1900..2100)
        for edge_sy in ("1900-1901", "2099-2100"):
            edge_periods = IsraeliWorkplaceCalendarService.get_workplace_holidays_for_school_year(edge_sy)
            self.assertEqual(len(edge_periods), 10)

        # Statutory independence from MoE school-only break windows:
        # 1) 2028-05-31 (Wed, 6 Sivan) is statutory Shavuot (0.0), whereas 2028-06-01 (Thu, 7 Sivan Isru Chag) is regular workday (1.0)
        self.assertEqual(IsraeliWorkplaceCalendarService.classify_workday_date("2028-05-31"), ("OFFICIAL_HOLIDAY", 0.0))
        self.assertEqual(IsraeliWorkplaceCalendarService.classify_workday_date("2028-06-01"), ("REGULAR_WORKDAY", 1.0))
        # 2) YK-Sukkot MoE bridge days 11-13 Tishrei 5787 (2026-09-22..24 Tue-Thu) are regular 1.0 workdays
        self.assertEqual(
            IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost("2026-09-22", "2026-09-24")[
                "workplace_vacation_days_cost"
            ],
            3.0,
        )
        # 3) Pre-Pesach school break days (e.g. 2027-04-18..21 Sun-Wed before Seder Thu 2027-04-22) are regular 1.0 workdays
        self.assertEqual(
            IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost("2027-04-18", "2027-04-21")[
                "workplace_vacation_days_cost"
            ],
            4.0,
        )
        # 4) Hanukkah & Purim Sun-Thu days are regular 1.0 workdays in the Israeli workplace calendar
        self.assertEqual(IsraeliWorkplaceCalendarService.classify_workday_date("2026-12-07"), ("REGULAR_WORKDAY", 1.0))
        self.assertEqual(IsraeliWorkplaceCalendarService.classify_workday_date("2027-03-23"), ("REGULAR_WORKDAY", 1.0))

    def test_run14_four_bucket_daily_precedence_and_weekend_override(self) -> None:
        from backend.app.calendar_engine.moe_calendar_service import (
            IsraeliWorkplaceCalendarService,
        )

        # Pure Sun-Thu regular workweek: 5 * 1.0 = 5.0
        reg_week = IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost("2026-11-08", "2026-11-12")
        self.assertEqual(reg_week["workplace_vacation_days_cost"], 5.0)
        self.assertEqual(reg_week["regular_workdays_count"], 5)
        self.assertEqual(reg_week["weekend_days_count"], 0)

        # Pure Fri-Sat weekend: 0.0
        wknd = IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost("2026-11-13", "2026-11-14")
        self.assertEqual(wknd["workplace_vacation_days_cost"], 0.0)
        self.assertEqual(wknd["weekend_days_count"], 2)

        # Pesach 2027 (2027-04-22 Thu .. 2027-04-28 Wed, 7 days):
        # Thu 04-22 Pesach I (0.0 official), Fri 04-23 & Sat 04-24 Chol HaMoed on Fri-Sat -> 0.0 WEEKEND override!
        # Sun-Tue 04-25..27 Chol HaMoed (3 * 0.5 = 1.5), Wed 04-28 Pesach VII (0.0 official) -> total 1.5!
        pes_2027 = IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost("2027-04-22", "2027-04-28")
        self.assertEqual(pes_2027["workplace_vacation_days_cost"], 1.5)
        self.assertEqual(pes_2027["regular_workdays_count"], 0)
        self.assertEqual(pes_2027["chol_hamoed_workdays_count"], 3)
        self.assertEqual(pes_2027["official_holiday_workdays_saved_count"], 2)
        self.assertEqual(pes_2027["weekend_days_count"], 2)
        self.assertEqual(pes_2027["holiday_or_weekend_days_count"], 4)

        # Sukkot 2026 (2026-09-26 Sat .. 2026-10-03 Sat, 8 days):
        # Sat 09-26 Sukkot I on Sat (weekend), Sun-Thu 09-27..10-01 Chol HaMoed (5 * 0.5 = 2.5),
        # Fri 10-02 Hoshana Rabbah on Fri (weekend 0.0!), Sat 10-03 Simchat Torah on Sat (weekend) -> 2.5!
        suk_2026 = IsraeliWorkplaceCalendarService.evaluate_trip_workdays_cost("2026-09-26", "2026-10-03")
        self.assertEqual(suk_2026["workplace_vacation_days_cost"], 2.5)
        self.assertEqual(suk_2026["chol_hamoed_workdays_count"], 5)
        self.assertEqual(suk_2026["official_holiday_workdays_saved_count"], 0)
        self.assertEqual(suk_2026["weekend_days_count"], 3)

    def test_run14_proposal_auto_compute_and_sqlite_roundtrip_zero_ddl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = SQLiteRepository(Path(tmpdir) / "run14_roundtrip.db", auto_seed=False)
            try:
                q = FlightSearchQuery(
                    id="run14-q1",
                    family_profile_id=None,
                    date_selection_mode=DateSelectionMode.SPECIFIC_DATES,
                    airline_selection_mode=AirlineSelectionMode.EL_AL_ONLY,
                    destination_iatas=["FCO"],
                    specific_departure_date=date(2027, 4, 22),
                    specific_return_date=date(2027, 4, 28),
                )
                itin = FlightItinerary(
                    id="run14-itin1",
                    search_query_id="run14-q1",
                    origin_iata="TLV",
                    destination_iata="FCO",
                    return_origin_iata="FCO",
                    destination_city_he="רומא",
                    destination_city_en="Rome",
                    departure_date=date(2027, 4, 22),
                    return_date=date(2027, 4, 28),
                    trip_nights=6,
                    primary_carrier_iata="LY",
                    is_elal_flight=True,
                    utilizes_elal_bonus=True,
                    fulfillment_strategy=FulfillmentStrategy.FULL_BONUS_SAME_CABIN,
                )
                prop = VacationOptionProposal(
                    id="run14-prop1",
                    search_query_id="run14-q1",
                    itinerary_id="run14-itin1",
                    associated_holiday_codes=["PESACH"],
                    window_set_type="SPECIFIC_USER_WINDOW",
                    holiday_alignment_score=95.0,
                    flight_bonus_value_score=100.0,
                    combined_trip_optimization_score=97.2,
                    itinerary=itin,
                )
                self.assertEqual(prop.workplace_vacation_days_cost, 1.5)
                self.assertEqual(prop.chol_hamoed_workdays_count, 3)
                self.assertEqual(prop.official_holiday_workdays_saved_count, 2)
                self.assertEqual(prop.weekend_days_count, 2)
                self.assertEqual(prop.holiday_or_weekend_days_count, 4)

                d = prop.to_dict()
                for forbidden in (
                    "total_vacation_days",
                    "parent_pto_days_used",
                    "pto_efficiency_ratio",
                    "vacation_utilization_score",
                ):
                    self.assertNotIn(forbidden, d)

                repo.save_search_results(q, [prop])
                reloaded = repo.get_proposal_by_id("run14-prop1")
                self.assertIsNotNone(reloaded)
                self.assertEqual(reloaded.workplace_vacation_days_cost, 1.5)
                self.assertEqual(reloaded.chol_hamoed_workdays_count, 3)
                self.assertEqual(reloaded.holiday_or_weekend_days_count, 4)

                cached = repo.get_cached_proposals_for_query("run14-q1", ttl_seconds=3600)
                self.assertEqual(len(cached), 1)
                self.assertEqual(cached[0].workplace_vacation_days_cost, 1.5)
            finally:
                repo.close()


class TestRun18WorkplaceCalendarAndMaximizer(unittest.TestCase):
    """Run 18 F1–F4: Child-free (`0` children) Israeli workplace calendar, workday-efficiency scoring & zero-DDL reload."""

    _FORBIDDEN_SCHOOL_AND_COPY_TOKENS = (
        "בוגרים",
        "חיסכון",
        "$",
        "¢",
        "הערכת",
        "מזומן",
        "Est. Cash",
        "נקודות:",
        "בי״ס",
        'בי"ס',
        "בית ספר",
        "מוסדות החינוך",
        "משרד החינוך",
        "חיסור",
        "ניצנים",
        "יוני",
    )

    def test_run18_rolling_workplace_holidays_and_bridge_expansion_multi_year(self) -> None:
        from backend.app.calendar_engine.moe_calendar_service import (
            IsraeliWorkplaceCalendarService,
        )

        expected_codes = {
            "ROSH_HASHANAH",
            "YOM_KIPPUR_SUKKOT_BRIDGE",
            "SUKKOT",
            "PESACH",
            "YOM_HAATZMAUT",
            "SHAVUOT",
        }
        expected_keys = {
            "holiday_code",
            "name_he",
            "name_en",
            "target_year",
            "school_year",
            "start_date",
            "end_date",
            "holiday_days",
            "recommended_window_start",
            "recommended_window_end",
            "recommended_trip_days",
            "recommended_workdays_cost",
            "recommended_workdays_saved",
            "recommended_efficiency_ratio",
            "workplace_workdays_cost",
            "official_holiday_days",
            "chol_hamoed_days",
            "is_ongoing",
            "calendar_mode",
            "label_he",
            "label_en",
        }

        for as_of in (
            "2026-11-28",
            "2027-04-25",
            "2027-05-12",
            "2027-05-13",
            "2028-02-29",
            "2036-01-01",
        ):
            items = IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
                as_of_date=as_of
            )
            self.assertEqual(len(items), 6, f"Expected 6 workplace holidays for {as_of}")
            self.assertEqual({it["holiday_code"] for it in items}, expected_codes)
            # Strictly chronological
            sort_keys = [
                (it["start_date"], it["end_date"], it["holiday_days"], it["holiday_code"])
                for it in items
            ]
            self.assertEqual(sort_keys, sorted(sort_keys))
            for it in items:
                self.assertEqual(set(it.keys()), expected_keys)
                self.assertEqual(it["calendar_mode"], "WORKPLACE")
                self.assertGreaterEqual(it["end_date"], as_of)
                if it["holiday_code"] in ("ROSH_HASHANAH", "YOM_HAATZMAUT", "SHAVUOT"):
                    self.assertIn(it["recommended_trip_days"], (4, 5), it)
                text_blob = f"{it['name_he']} {it['name_en']} {it['label_he']} {it['label_en']}"
                for bad in self._FORBIDDEN_SCHOOL_AND_COPY_TOKENS:
                    self.assertNotIn(bad, text_blob, f"Forbidden token {bad!r} in {text_blob!r}")

        # Exact Pesach 2027 contract check
        nov_items = {
            it["holiday_code"]: it
            for it in IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
                "2026-11-28"
            )
        }
        pes27 = nov_items["PESACH"]
        self.assertEqual(pes27["target_year"], 2027)
        self.assertEqual(pes27["start_date"], "2027-04-22")
        self.assertEqual(pes27["end_date"], "2027-04-28")
        self.assertEqual(pes27["holiday_days"], 7)
        self.assertEqual(pes27["official_holiday_days"], 2)
        self.assertEqual(pes27["chol_hamoed_days"], 5)
        self.assertEqual(pes27["workplace_workdays_cost"], 1.5)
        self.assertEqual(pes27["recommended_trip_days"], 7)
        self.assertEqual(pes27["recommended_workdays_cost"], 1.5)
        self.assertEqual(pes27["recommended_workdays_saved"], 5.5)
        self.assertEqual(pes27["recommended_efficiency_ratio"], 4.67)
        self.assertFalse(pes27["is_ongoing"])

        # Mid-Pesach & Yom HaAtzmaut ongoing / rollover checks
        mid_pes = {
            it["holiday_code"]: it
            for it in IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
                "2027-04-25"
            )
        }
        self.assertTrue(mid_pes["PESACH"]["is_ongoing"])
        self.assertEqual(mid_pes["PESACH"]["target_year"], 2027)

        on_atz = {
            it["holiday_code"]: it
            for it in IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
                "2027-05-12"
            )
        }
        self.assertTrue(on_atz["YOM_HAATZMAUT"]["is_ongoing"])
        self.assertEqual(on_atz["YOM_HAATZMAUT"]["target_year"], 2027)

        after_atz = {
            it["holiday_code"]: it
            for it in IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
                "2027-05-13"
            )
        }
        self.assertFalse(after_atz["YOM_HAATZMAUT"]["is_ongoing"])
        self.assertEqual(after_atz["YOM_HAATZMAUT"]["target_year"], 2028)

    def test_run18_resolve_workplace_holiday_span_and_erev_chag_preserved(self) -> None:
        from backend.app.calendar_engine.moe_calendar_service import (
            IsraeliWorkplaceCalendarService,
        )

        self.assertEqual(
            IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span("PESACH", 2027),
            (date(2027, 4, 22), date(2027, 4, 28)),
        )
        self.assertEqual(
            IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span("ROSH_HASHANAH", 2026),
            (date(2026, 9, 12), date(2026, 9, 13)),
        )
        self.assertEqual(
            IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span("YOM_HAATZMAUT", 2027),
            (date(2027, 5, 12), date(2027, 5, 12)),
        )
        self.assertEqual(
            IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span("SHAVUOT", 2027),
            (date(2027, 6, 11), date(2027, 6, 11)),
        )
        self.assertEqual(
            IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span("SUKKOT", 2027),
            (date(2027, 10, 16), date(2027, 10, 23)),
        )
        self.assertEqual(
            IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span(
                "YOM_KIPPUR_SUKKOT_BRIDGE", 2027
            ),
            (date(2027, 10, 11), date(2027, 10, 23)),
        )
        for moe_only in ("HANUKKAH", "PURIM", "SUMMER_JULY", "LAG_BAOMER"):
            self.assertIsNone(
                IsraeliWorkplaceCalendarService.resolve_workplace_holiday_span(moe_only, 2027)
            )

        # Erev Chag remains REGULAR_WORKDAY (1.0)
        self.assertEqual(
            IsraeliWorkplaceCalendarService.classify_workday_date(date(2027, 4, 21)),
            ("REGULAR_WORKDAY", 1.0),
        )

        # MoECalendarService delegation matches IsraeliWorkplaceCalendarService
        repo = SQLiteRepository(":memory:", auto_seed=False)
        try:
            cal = MoECalendarService(repo)
            self.assertEqual(
                cal.get_upcoming_workplace_holidays_for_rolling_year("2026-11-28"),
                IsraeliWorkplaceCalendarService.get_upcoming_workplace_holidays_for_rolling_year(
                    "2026-11-28"
                ),
            )
            self.assertEqual(
                cal.resolve_workplace_holiday_span("PESACH", 2027),
                (date(2027, 4, 22), date(2027, 4, 28)),
            )
            occ = cal.resolve_upcoming_workplace_holiday_occurrence(
                "YOM_KIPPUR_SUKKOT", as_of_date="2026-11-28"
            )
            self.assertIsNotNone(occ)
            self.assertEqual(occ["target_year"], 2027)
        finally:
            repo.close()

    def test_run18_workday_efficiency_monotonic_scoring_and_zero_workday_edge(self) -> None:
        repo = SQLiteRepository(":memory:", auto_seed=False)
        try:
            cal = MoECalendarService(repo)
            maximizer = VacationMaximizerEngine(cal)
            p0 = FamilyProfile(id="run18-p0", adults_count=2, children=[])

            w_reg = maximizer.evaluate_window(p0, date(2026, 11, 8), date(2026, 11, 12))
            w_pre_pes = maximizer.evaluate_window(p0, date(2027, 4, 11), date(2027, 4, 18))
            w_atz = maximizer.evaluate_window(p0, date(2027, 5, 12), date(2027, 5, 15))
            w_pes = maximizer.evaluate_window(p0, date(2027, 4, 22), date(2027, 4, 28))
            w_zero = maximizer.evaluate_window(p0, date(2026, 9, 11), date(2026, 9, 13))
            w_yk = maximizer.evaluate_window(p0, date(2027, 10, 11), date(2027, 10, 16))
            w_shift = maximizer.evaluate_window(
                p0,
                date(2027, 4, 22),
                date(2027, 4, 28),
                window_set_type="SPECIFIC_USER_WINDOW",
                mode1_shift_days=2,
            )

            self.assertEqual(w_reg.workday_efficiency_score, 0.0)
            self.assertEqual(w_pre_pes.workday_efficiency_score, 20.0)
            self.assertEqual(w_atz.workday_efficiency_score, 75.0)
            self.assertEqual(w_pes.workday_efficiency_score, 82.5)
            self.assertEqual(w_zero.workday_efficiency_score, 100.0)
            self.assertTrue(w_zero.is_zero_workday_trip)
            self.assertEqual(w_zero.workplace_vacation_days_cost, 0.0)
            self.assertEqual(w_zero.workday_efficiency_ratio, 6.0)
            self.assertEqual(w_yk.workday_efficiency_score, 0.0)
            self.assertEqual(w_yk.holiday_alignment_score, 0.0)
            self.assertEqual(w_shift.workday_efficiency_score, 79.5)
            self.assertEqual(w_shift.holiday_alignment_score, 79.5)

            # Strictly monotonic ordering
            self.assertLess(w_reg.holiday_alignment_score, w_pre_pes.holiday_alignment_score)
            self.assertLess(w_pre_pes.holiday_alignment_score, w_atz.holiday_alignment_score)
            self.assertLess(w_atz.holiday_alignment_score, w_pes.holiday_alignment_score)
            self.assertLess(w_pes.holiday_alignment_score, w_zero.holiday_alignment_score)

            for w in (w_reg, w_pre_pes, w_atz, w_pes, w_zero, w_shift):
                self.assertEqual(w.calendar_mode, "WORKPLACE")
                self.assertEqual(w.holiday_alignment_score, w.workday_efficiency_score)
                for bad in self._FORBIDDEN_SCHOOL_AND_COPY_TOKENS:
                    self.assertNotIn(bad, w.explanation_summary_he)
        finally:
            repo.close()

    def test_run18_zero_moe_db_dependency_for_zero_children(self) -> None:
        repo = SQLiteRepository(":memory:", auto_seed=False)
        try:
            with repo.connection() as conn:
                conn.execute("DELETE FROM moe_vacation_windows")
            cal = MoECalendarService(repo)

            def _forbid(*_args, **_kwargs):
                raise AssertionError("MoE calendar DB/methods must NOT be called for 0 children!")

            cal.get_calendar_windows = _forbid  # type: ignore[method-assign]
            cal.get_child_day_status = _forbid  # type: ignore[method-assign]
            cal.resolve_upcoming_holiday_occurrence = _forbid  # type: ignore[method-assign]

            maximizer = VacationMaximizerEngine(cal)
            p0 = FamilyProfile(id="run18-nodb", adults_count=2, children=[])

            # Mode 1 SPECIFIC_DATES
            m1_wins = maximizer.generate_candidate_windows(
                {
                    "date_selection_mode": "SPECIFIC_DATES",
                    "specific_departure_date": "2027-04-22",
                    "specific_return_date": "2027-04-28",
                    "flex_days_plus_minus": 2,
                },
                p0,
            )
            self.assertGreater(len(m1_wins), 0)
            self.assertTrue(all(w.calendar_mode == "WORKPLACE" for w in m1_wins))

            # Mode 3 across all 6 canonical workplace holidays + legacy MoE codes
            for h_code, yr, min_n, max_n in (
                ("ROSH_HASHANAH", 2027, 2, 5),
                ("YOM_KIPPUR_SUKKOT_BRIDGE", 2027, 4, 14),
                ("SUKKOT", 2027, 4, 9),
                ("PESACH", 2027, 4, 8),
                ("YOM_HAATZMAUT", 2027, 2, 5),
                ("SHAVUOT", 2027, 2, 5),
                ("HANUKKAH", 2026, 3, 7),
                ("PURIM", 2027, 2, 5),
                ("SUMMER_JULY", 2027, 4, 8),
            ):
                wins = maximizer.generate_candidate_windows(
                    {
                        "date_selection_mode": "HOLIDAY_DIRECT_INTENT",
                        "direct_holiday_code": h_code,
                        "direct_target_year": yr,
                        "min_trip_nights": min_n,
                        "max_trip_nights": max_n,
                    },
                    p0,
                )
                self.assertGreater(len(wins), 0, f"No windows for {h_code} {yr}")
                for w in wins[:5]:
                    self.assertEqual(w.calendar_mode, "WORKPLACE")
                    for bad in self._FORBIDDEN_SCHOOL_AND_COPY_TOKENS:
                        self.assertNotIn(bad, w.explanation_summary_he)
        finally:
            repo.close()

    def test_run18_zero_ddl_sqlite_reload_preserves_workplace_fields_and_shift_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = SQLiteRepository(db_path=Path(tmpdir) / "run18_reload.db", auto_seed=False)
            try:
                q = FlightSearchQuery(
                    id="run18-q1",
                    family_profile_id=None,
                    origin_iata="TLV",
                    destination_iatas=["FCO"],
                )
                itin_shift = FlightItinerary(
                    id="run18-itin-shift",
                    search_query_id="run18-q1",
                    destination_iata="FCO",
                    destination_city_he="רומא",
                    departure_date=date(2027, 4, 22),
                    return_date=date(2027, 4, 28),
                    trip_nights=6,
                )
                prop_shift = VacationOptionProposal(
                    id="run18-prop-shift",
                    search_query_id="run18-q1",
                    itinerary_id="run18-itin-shift",
                    associated_holiday_codes=["PESACH"],
                    window_set_type="SPECIFIC_USER_WINDOW",
                    holiday_alignment_score=79.5,
                    flight_bonus_value_score=100.0,
                    combined_trip_optimization_score=88.7,
                    explanation_summary_he="רומא (FCO) | ציונים: יעילות ימי חופש=79.5/100, FBVS=100.0, CTOS=88.7",
                    itinerary=itin_shift,
                    calendar_mode="WORKPLACE",
                    workday_efficiency_score=79.5,
                )

                itin_zero = FlightItinerary(
                    id="run18-itin-zero",
                    search_query_id="run18-q1",
                    destination_iata="ATH",
                    destination_city_he="אתונה",
                    departure_date=date(2026, 9, 11),
                    return_date=date(2026, 9, 13),
                    trip_nights=2,
                )
                prop_zero = VacationOptionProposal(
                    id="run18-prop-zero",
                    search_query_id="run18-q1",
                    itinerary_id="run18-itin-zero",
                    associated_holiday_codes=["ROSH_HASHANAH"],
                    window_set_type="STRICT_INTERSECTION",
                    holiday_alignment_score=100.0,
                    flight_bonus_value_score=90.0,
                    combined_trip_optimization_score=95.5,
                    explanation_summary_he="אתונה (ATH) | ציונים: יעילות ימי חופש=100.0/100, FBVS=90.0, CTOS=95.5",
                    itinerary=itin_zero,
                    calendar_mode="WORKPLACE",
                    workday_efficiency_score=100.0,
                )

                repo.save_search_results(q, [prop_shift, prop_zero])
                reloaded_shift = repo.get_proposal_by_id("run18-prop-shift")
                reloaded_zero = repo.get_proposal_by_id("run18-prop-zero")
                self.assertIsNotNone(reloaded_shift)
                self.assertIsNotNone(reloaded_zero)

                self.assertEqual(reloaded_shift.calendar_mode, "WORKPLACE")
                self.assertEqual(reloaded_shift.trip_calendar_days, 7)
                self.assertEqual(reloaded_shift.workdays_saved_count, 5.5)
                self.assertEqual(reloaded_shift.workday_efficiency_ratio, 4.67)
                self.assertEqual(reloaded_shift.workday_efficiency_score, 79.5)
                self.assertFalse(reloaded_shift.is_zero_workday_trip)

                self.assertEqual(reloaded_zero.calendar_mode, "WORKPLACE")
                self.assertEqual(reloaded_zero.trip_calendar_days, 3)
                self.assertEqual(reloaded_zero.workdays_saved_count, 3.0)
                self.assertEqual(reloaded_zero.workday_efficiency_ratio, 6.0)
                self.assertEqual(reloaded_zero.workday_efficiency_score, 100.0)
                self.assertTrue(reloaded_zero.is_zero_workday_trip)

                for d in (reloaded_shift.to_dict(), reloaded_zero.to_dict()):
                    for forbidden in (
                        "total_vacation_days",
                        "parent_pto_days_used",
                        "pto_efficiency_ratio",
                        "vacation_utilization_score",
                    ):
                        self.assertNotIn(forbidden, d)
            finally:
                repo.close()

    def test_run18_one_or_more_children_preserves_moe_regression(self) -> None:
        repo = SQLiteRepository(":memory:", auto_seed=True)
        try:
            cal = MoECalendarService(repo)
            maximizer = VacationMaximizerEngine(cal)

            p_null_fw = FamilyProfile(
                id="run18-null-fw",
                adults_count=2,
                children=[ChildFramework(id="c1", child_age_years=6, framework_type=None)],
            )
            w_null = maximizer.evaluate_window(p_null_fw, date(2027, 4, 11), date(2027, 4, 18))
            self.assertEqual(w_null.calendar_mode, "MOE")
            self.assertEqual(w_null.holiday_alignment_score, 80.0)

            examples = maximizer.evaluate_worked_examples()
            for key, win in examples.items():
                self.assertEqual(win.calendar_mode, "MOE", key)
            self.assertEqual(examples["EX1_KIPPUR_SUKKOT_MEGA_BRIDGE"].holiday_alignment_score, 100.0)
            self.assertEqual(examples["EX4B_PESACH_UNCOVERED_WEEK"].holiday_alignment_score, 100.0)
        finally:
            repo.close()


if __name__ == "__main__":
    unittest.main()
