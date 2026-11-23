"""SQLite 3.53 WAL repository and two-tier TTL cache for family_vacation_planner.

Enforces `PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;` on every
connection, initializes all 11 normalized tables and indexes from
`schema.sql`, runs idempotent M5/M6 schema migrations, and seeds
MoE vacation calendars (`2025-2028`) and El Al `rbddataclients` Classic Award
inventory (`2025-2028`).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from backend.app.config_manager.settings import resolve_db_path
from backend.app.schemas.domain import (
    ChildFramework,
    ElAlBonusAvailability,
    FamilyProfile,
    FlightItinerary,
    FlightSearchQuery,
    MoEFrameworkType,
    MoEVacationWindow,
    PassengerLoyaltyWallet,
    VacationOptionProposal,
)
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    build_clean_guest_profile,
    build_seeded_elal_bonus_availability,
    generate_commercial_flights_for_route,
    load_bundled_moe_windows,
)

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "schema.sql"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    s = str(ts_str).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    elif " " in s and "T" not in s:
        s = s.replace(" ", "T") + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def _is_timestamp_fresh(
    ts_str: Optional[str],
    ttl_seconds: int,
    now_dt: Optional[datetime] = None,
) -> bool:
    if ttl_seconds <= 0:
        return False
    created_dt = _parse_iso_utc(ts_str)
    if created_dt is None:
        return False
    ref_now = now_dt or datetime.now(UTC).replace(microsecond=0)
    return (created_dt + timedelta(seconds=ttl_seconds)) > ref_now


def _to_date_str(val: Optional[date | datetime | str]) -> Optional[str]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val)[:10]


class SQLiteRepository:
    """Relational storage and two-tier TTL cache backed by SQLite 3.53 WAL mode."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        auto_seed: bool = True,
    ) -> None:
        self.db_path: str = resolve_db_path(db_path)
        self._is_memory: bool = self.db_path == ":memory:"
        self._memory_conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

        if not self._is_memory:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.init_schema()
        if auto_seed:
            self.seed_initial_data()

    def _configure_connection(self, conn: sqlite3.Connection) -> sqlite3.Connection:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _open_raw_connection(self) -> sqlite3.Connection:
        if self._is_memory:
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(
                    ":memory:", check_same_thread=False
                )
            return self._configure_connection(self._memory_conn)
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        return self._configure_connection(conn)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured SQLite connection with WAL and foreign_keys ON."""
        with self._lock:
            conn = self._open_raw_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                if not self._is_memory:
                    conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Return a configured connection (caller manages commit/close if file-backed)."""
        with self._lock:
            return self._open_raw_connection()

    def close(self) -> None:
        with self._lock:
            if self._memory_conn is not None:
                self._memory_conn.close()
                self._memory_conn = None

    def _initialize_database(self) -> None:
        """Execute the 11-table DDL, indexes, and idempotent migrations for existing SQLite DBs."""
        ddl = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        with self.connection() as conn:
            existing_tables = {
                str(r["name"])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            if "family_profiles" in existing_tables:
                fp_cols = {
                    str(r["name"])
                    for r in conn.execute("PRAGMA table_info(family_profiles)").fetchall()
                }
                if "user_id" not in fp_cols:
                    conn.execute(
                        "ALTER TABLE family_profiles ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE CASCADE"
                    )
                if "is_legacy_quarantined" not in fp_cols:
                    conn.execute(
                        "ALTER TABLE family_profiles ADD COLUMN is_legacy_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (is_legacy_quarantined IN (0, 1))"
                    )

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
            existing_indexes = {
                str(r["name"])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            expected_indexes = {
                "idx_users_email",
                "idx_auth_sessions_user_id",
                "idx_auth_sessions_expires",
                "idx_family_profiles_user_id",
            }
            if not expected_tables.issubset(existing_tables) or not expected_indexes.issubset(
                existing_indexes
            ):
                conn.executescript(ddl)

            # Ensure columns & partial index exist on family_profiles and quarantine pre-existing unowned rows
            fp_cols_after = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(family_profiles)").fetchall()
            }
            if "user_id" not in fp_cols_after:
                conn.execute(
                    "ALTER TABLE family_profiles ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE CASCADE"
                )
            if "is_legacy_quarantined" not in fp_cols_after:
                conn.execute(
                    "ALTER TABLE family_profiles ADD COLUMN is_legacy_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (is_legacy_quarantined IN (0, 1))"
                )
            if "idx_family_profiles_user_id" not in existing_indexes:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_family_profiles_user_id ON family_profiles(user_id) WHERE user_id IS NOT NULL;"
                )
            has_unquarantined_unowned = conn.execute(
                "SELECT 1 FROM family_profiles WHERE user_id IS NULL AND is_legacy_quarantined = 0 LIMIT 1"
            ).fetchone()
            if has_unquarantined_unowned is not None:
                conn.execute(
                    "UPDATE family_profiles SET is_legacy_quarantined = 1 WHERE user_id IS NULL AND is_legacy_quarantined = 0"
                )

            # Drop removed R2 parent PTO / workweek columns from family_profiles & moe_vacation_windows
            fp_cols_cur = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(family_profiles)").fetchall()
            }
            for legacy_fp_col in (
                "workweek_type",
                "erev_chag_pto_weight",
                "chol_hamoed_pto_weight",
                "annual_pto_budget",
                "max_pto_per_trip",
            ):
                if legacy_fp_col in fp_cols_cur:
                    conn.execute(
                        f"ALTER TABLE family_profiles DROP COLUMN {legacy_fp_col}"
                    )

            moe_cols_cur = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(moe_vacation_windows)").fetchall()
            }
            if "parent_workday_status" in moe_cols_cur:
                conn.execute(
                    "ALTER TABLE moe_vacation_windows DROP COLUMN parent_workday_status"
                )

            # Idempotent column & CHECK enum migration for flight_search_queries
            q_info = conn.execute("PRAGMA table_info(flight_search_queries)").fetchall()
            q_cols = {str(r["name"]) for r in q_info}
            if "preferred_vacation_types_json" not in q_cols:
                conn.execute(
                    "ALTER TABLE flight_search_queries ADD COLUMN preferred_vacation_types_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "weather_filter_mode" not in q_cols:
                conn.execute(
                    "ALTER TABLE flight_search_queries ADD COLUMN weather_filter_mode TEXT NOT NULL DEFAULT 'SOFT_PRIORITIZE'"
                )
            if "min_weather_suitability_score" not in q_cols:
                conn.execute(
                    "ALTER TABLE flight_search_queries ADD COLUMN min_weather_suitability_score REAL"
                )

            q_info_refreshed = conn.execute("PRAGMA table_info(flight_search_queries)").fetchall()
            fp_fk_notnull = any(
                str(r["name"]) == "family_profile_id" and int(r["notnull"]) == 1
                for r in q_info_refreshed
            )
            fsq_master_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'flight_search_queries'"
            ).fetchone()
            fsq_sql = str(fsq_master_row["sql"] or "") if fsq_master_row is not None else ""
            if (
                fp_fk_notnull
                or "MOE_VACATION_MAXIMIZATION" in fsq_sql
                or "MAXIMIZE_EFFICIENCY_SCORE" in fsq_sql
            ):
                conn.commit()
                conn.execute("PRAGMA foreign_keys = OFF;")
                conn.executescript(
                    """
                    DROP TABLE IF EXISTS flight_search_queries__m6_mig;
                    CREATE TABLE flight_search_queries__m6_mig (
                        id TEXT PRIMARY KEY,
                        family_profile_id TEXT REFERENCES family_profiles(id) ON DELETE CASCADE,
                        date_selection_mode TEXT NOT NULL CHECK (date_selection_mode IN (
                            'SPECIFIC_DATES',
                            'HOLIDAY_DIRECT_INTENT'
                        )),
                        airline_selection_mode TEXT NOT NULL CHECK (airline_selection_mode IN (
                            'EL_AL_ONLY',
                            'ALL_AIRLINES'
                        )),
                        search_elal_bonus_tickets INTEGER NOT NULL DEFAULT 1 CHECK (search_elal_bonus_tickets IN (0, 1)),
                        include_sundor_flights INTEGER NOT NULL DEFAULT 1 CHECK (include_sundor_flights IN (0, 1)),
                        origin_iata TEXT NOT NULL DEFAULT 'TLV',
                        destination_iatas_json TEXT NOT NULL,
                        specific_departure_date TEXT,
                        specific_return_date TEXT,
                        flex_days_plus_minus INTEGER NOT NULL DEFAULT 0 CHECK (flex_days_plus_minus BETWEEN 0 AND 7),
                        school_year TEXT,
                        target_holiday_codes_json TEXT,
                        direct_holiday_code TEXT,
                        direct_target_year INTEGER CHECK (direct_target_year IS NULL OR direct_target_year BETWEEN 2025 AND 2035),
                        min_trip_nights INTEGER NOT NULL DEFAULT 4 CHECK (min_trip_nights >= 1),
                        max_trip_nights INTEGER NOT NULL DEFAULT 10 CHECK (max_trip_nights >= min_trip_nights),
                        max_bridge_days_shift INTEGER NOT NULL DEFAULT 3 CHECK (max_bridge_days_shift BETWEEN 0 AND 5),
                        overlap_policy TEXT NOT NULL DEFAULT 'CAMP_ADJUSTED_INTERSECTION' CHECK (overlap_policy IN (
                            'STRICT_ALL_CHILDREN_OFF',
                            'CAMP_ADJUSTED_INTERSECTION'
                        )),
                        preferred_cabins_json TEXT NOT NULL DEFAULT '["ECONOMY","PREMIUM","BUSINESS"]',
                        enabled_loyalty_programs_json TEXT NOT NULL DEFAULT '["ELAL_MATMID"]',
                        preferred_vacation_types_json TEXT NOT NULL DEFAULT '[]',
                        weather_filter_mode TEXT NOT NULL DEFAULT 'SOFT_PRIORITIZE' CHECK (weather_filter_mode IN ('SOFT_PRIORITIZE', 'HARD_THRESHOLD')),
                        min_weather_suitability_score REAL CHECK (min_weather_suitability_score IS NULL OR (min_weather_suitability_score BETWEEN 0.0 AND 100.0)),
                        allow_hybrid_bonus_cash INTEGER NOT NULL DEFAULT 1 CHECK (allow_hybrid_bonus_cash IN (0, 1)),
                        direct_flights_only INTEGER NOT NULL DEFAULT 1 CHECK (direct_flights_only IN (0, 1)),
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    INSERT INTO flight_search_queries__m6_mig (
                        id, family_profile_id, date_selection_mode, airline_selection_mode,
                        search_elal_bonus_tickets, include_sundor_flights, origin_iata,
                        destination_iatas_json, specific_departure_date, specific_return_date,
                        flex_days_plus_minus, school_year, target_holiday_codes_json,
                        direct_holiday_code, direct_target_year, min_trip_nights,
                        max_trip_nights, max_bridge_days_shift, overlap_policy,
                        preferred_cabins_json, enabled_loyalty_programs_json,
                        preferred_vacation_types_json, weather_filter_mode,
                        min_weather_suitability_score, allow_hybrid_bonus_cash,
                        direct_flights_only, created_at
                    )
                    SELECT
                        id,
                        family_profile_id,
                        CASE WHEN date_selection_mode = 'SPECIFIC_DATES' THEN 'SPECIFIC_DATES' ELSE 'HOLIDAY_DIRECT_INTENT' END,
                        airline_selection_mode,
                        search_elal_bonus_tickets, include_sundor_flights, origin_iata,
                        destination_iatas_json, specific_departure_date, specific_return_date,
                        flex_days_plus_minus, school_year, target_holiday_codes_json,
                        direct_holiday_code, direct_target_year, min_trip_nights,
                        max_trip_nights, max_bridge_days_shift,
                        CASE WHEN overlap_policy = 'STRICT_ALL_CHILDREN_OFF' THEN 'STRICT_ALL_CHILDREN_OFF' ELSE 'CAMP_ADJUSTED_INTERSECTION' END,
                        preferred_cabins_json, enabled_loyalty_programs_json,
                        preferred_vacation_types_json, weather_filter_mode,
                        min_weather_suitability_score, allow_hybrid_bonus_cash,
                        direct_flights_only, created_at
                    FROM flight_search_queries;
                    DROP TABLE flight_search_queries;
                    ALTER TABLE flight_search_queries__m6_mig RENAME TO flight_search_queries;
                    """
                )
                conn.execute("PRAGMA foreign_keys = ON;")

            # R1 migration on flight_itineraries: add aggregate household columns, backfill, drop per-passenger JSON
            i_cols = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(flight_itineraries)").fetchall()
            }
            if "seated_passengers_count" not in i_cols:
                conn.execute(
                    "ALTER TABLE flight_itineraries ADD COLUMN seated_passengers_count INTEGER NOT NULL DEFAULT 1 CHECK (seated_passengers_count >= 1)"
                )
            if "bonus_tickets_count" not in i_cols:
                conn.execute(
                    "ALTER TABLE flight_itineraries ADD COLUMN bonus_tickets_count INTEGER NOT NULL DEFAULT 0 CHECK (bonus_tickets_count >= 0)"
                )
            if "cash_tickets_count" not in i_cols:
                conn.execute(
                    "ALTER TABLE flight_itineraries ADD COLUMN cash_tickets_count INTEGER NOT NULL DEFAULT 0 CHECK (cash_tickets_count >= 0)"
                )
            if "primary_cabin" not in i_cols:
                conn.execute(
                    "ALTER TABLE flight_itineraries ADD COLUMN primary_cabin TEXT NOT NULL DEFAULT 'ECONOMY' CHECK (primary_cabin IN ('ECONOMY', 'PREMIUM', 'BUSINESS'))"
                )
            if "family_ticket_allocation_json" in i_cols:
                legacy_i_rows = conn.execute(
                    "SELECT id, family_ticket_allocation_json FROM flight_itineraries"
                ).fetchall()
                for i_row in legacy_i_rows:
                    raw_alloc_json = i_row["family_ticket_allocation_json"]
                    try:
                        alloc_items = json.loads(raw_alloc_json) if raw_alloc_json else []
                    except Exception:
                        alloc_items = []
                    if not isinstance(alloc_items, list):
                        alloc_items = []
                    seated_items = [
                        a
                        for a in alloc_items
                        if isinstance(a, dict)
                        and str(a.get("rbd_code") or "").upper() != "INF"
                    ]
                    seated_cnt = max(1, len(seated_items))
                    bonus_cnt = sum(
                        1
                        for a in seated_items
                        if "BONUS" in str(a.get("ticket_mode") or "").upper()
                        or "POINTS" in str(a.get("ticket_mode") or "").upper()
                        or int(a.get("points_used") or 0) > 0
                    )
                    cash_cnt = max(0, seated_cnt - bonus_cnt)
                    cabins_set = {
                        str(a.get("cabin_class") or "ECONOMY").upper()
                        for a in seated_items
                        if str(a.get("cabin_class") or "ECONOMY").upper()
                        in ("ECONOMY", "PREMIUM", "BUSINESS")
                    }
                    prim_cabin = (
                        next(iter(cabins_set)) if len(cabins_set) == 1 else "ECONOMY"
                    )
                    conn.execute(
                        "UPDATE flight_itineraries SET seated_passengers_count = ?, bonus_tickets_count = ?, cash_tickets_count = ?, primary_cabin = ? WHERE id = ?",
                        (seated_cnt, bonus_cnt, cash_cnt, prim_cabin, str(i_row["id"])),
                    )
                conn.execute(
                    "ALTER TABLE flight_itineraries DROP COLUMN family_ticket_allocation_json"
                )

            # R2 + weather migration on vacation_option_proposals
            p_cols = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(vacation_option_proposals)").fetchall()
            }
            if "weather_suitability_score" not in p_cols:
                conn.execute(
                    "ALTER TABLE vacation_option_proposals ADD COLUMN weather_suitability_score REAL NOT NULL DEFAULT 0.0"
                )
            if "vacation_type_scores_json" not in p_cols:
                conn.execute(
                    "ALTER TABLE vacation_option_proposals ADD COLUMN vacation_type_scores_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "weather_metrics_json" not in p_cols:
                conn.execute(
                    "ALTER TABLE vacation_option_proposals ADD COLUMN weather_metrics_json TEXT"
                )
            if "holiday_alignment_score" not in p_cols:
                conn.execute(
                    "ALTER TABLE vacation_option_proposals ADD COLUMN holiday_alignment_score REAL NOT NULL DEFAULT 0.0 CHECK (holiday_alignment_score >= 0.0 AND holiday_alignment_score <= 100.0)"
                )
            if "vacation_utilization_score" in p_cols:
                conn.execute(
                    "UPDATE vacation_option_proposals SET holiday_alignment_score = MIN(100.0, MAX(0.0, COALESCE(vacation_utilization_score, 0.0)))"
                )
            for legacy_p_col in (
                "total_vacation_days",
                "parent_pto_days_used",
                "pto_efficiency_ratio",
                "vacation_utilization_score",
            ):
                if legacy_p_col in p_cols:
                    conn.execute(
                        f"ALTER TABLE vacation_option_proposals DROP COLUMN {legacy_p_col}"
                    )

            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")

    def init_schema(self) -> None:
        """Initialize the 11-table schema and run idempotent migrations."""
        self._initialize_database()

    def list_tables(self) -> list[str]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [str(r["name"]) for r in rows]

    def list_indexes(self) -> list[str]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [str(r["name"]) for r in rows]

    def get_health_status(self) -> dict[str, Any]:
        """Return SQLite version, WAL mode status, and table count."""
        with self.connection() as conn:
            ver_row = conn.execute("SELECT sqlite_version() AS v").fetchone()
            mode_row = conn.execute("PRAGMA journal_mode;").fetchone()
            fk_row = conn.execute("PRAGMA foreign_keys;").fetchone()
            tables = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
        mode_val = str(mode_row[0]).lower() if mode_row else ""
        return {
            "status": "ok",
            "sqlite_version": str(ver_row["v"]) if ver_row else sqlite3.sqlite_version,
            "wal_mode": mode_val in ("wal", "memory"),
            "journal_mode": mode_val,
            "foreign_keys": bool(fk_row[0]) if fk_row else True,
            "tables_count": int(tables["cnt"]) if tables else 0,
        }

    @staticmethod
    def is_live_fetch_mode() -> bool:
        """Return True when running in production live-fetch mode (`ELAL_LIVE_FETCH_ENABLED=1`),
        where synthetic/seeded flight inventory must NEVER be fabricated.
        """
        return os.environ.get("ELAL_LIVE_FETCH_ENABLED", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    def seed_initial_data(self) -> None:
        """Idempotently seed MoE calendars and (only in offline/test mode) El Al award inventory.

        Never seeds any personal `family_profiles` rows (zero shared profile exposure).
        """
        live_mode = self.is_live_fetch_mode()
        with self.connection() as conn:
            moe_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM moe_vacation_windows"
            ).fetchone()
            has_moe_windows = bool(moe_row and int(moe_row["cnt"]) > 0)

            if live_mode:
                # Purge any pre-seeded fictitious rows (which lack `#live` in source_url)
                # First remove dependent proposals & itineraries referencing non-live bonus rows
                conn.execute(
                    """
                    DELETE FROM vacation_option_proposals
                    WHERE itinerary_id IN (
                        SELECT id FROM flight_itineraries
                        WHERE outbound_bonus_id IN (
                            SELECT id FROM elal_bonus_availability WHERE source_url NOT LIKE '%#live%'
                        )
                        OR inbound_bonus_id IN (
                            SELECT id FROM elal_bonus_availability WHERE source_url NOT LIKE '%#live%'
                        )
                    )
                    """
                )
                conn.execute(
                    """
                    DELETE FROM flight_itineraries
                    WHERE outbound_bonus_id IN (
                        SELECT id FROM elal_bonus_availability WHERE source_url NOT LIKE '%#live%'
                    )
                    OR inbound_bonus_id IN (
                        SELECT id FROM elal_bonus_availability WHERE source_url NOT LIKE '%#live%'
                    )
                    """
                )
                conn.execute(
                    "DELETE FROM elal_bonus_availability WHERE source_url NOT LIKE '%#live%'"
                )
                has_bonus_rows = True
            else:
                bonus_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM elal_bonus_availability"
                ).fetchone()
                has_bonus_rows = bool(bonus_row and int(bonus_row["cnt"]) > 0)

        if not has_moe_windows:
            self.upsert_moe_windows(load_bundled_moe_windows())

        if not has_bonus_rows and not live_mode:
            self.upsert_elal_bonus(build_seeded_elal_bonus_availability())

    def get_profile(
        self, profile_id: Optional[str] = None
    ) -> Optional[FamilyProfile]:
        """Load a non-quarantined `FamilyProfile` by explicit ID (never falls back to arbitrary user rows)."""
        target_id = profile_id if profile_id is not None else "default-family-profile"
        if not target_id:
            return None
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM family_profiles WHERE id = ? AND is_legacy_quarantined = 0",
                (target_id,),
            ).fetchone()
            if row is None:
                return None

            pid = str(row["id"])
            child_rows = conn.execute(
                "SELECT * FROM child_frameworks WHERE family_profile_id = ? ORDER BY child_age_years ASC, id ASC",
                (pid,),
            ).fetchall()
            wallet_rows = conn.execute(
                "SELECT * FROM passenger_loyalty_wallets WHERE family_profile_id = ? ORDER BY passenger_id ASC, program_code ASC",
                (pid,),
            ).fetchall()

        children = [ChildFramework.from_dict(dict(r)) for r in child_rows]
        wallets = [PassengerLoyaltyWallet.from_dict(dict(r)) for r in wallet_rows]
        prof_dict = dict(row)
        prof_dict["children"] = children
        prof_dict["passenger_loyalty_wallets"] = wallets
        return FamilyProfile.from_dict(prof_dict)

    def get_profile_for_user(self, user_id: str) -> Optional[FamilyProfile]:
        """Load the non-quarantined `FamilyProfile` owned strictly by `user_id`."""
        if not user_id or not str(user_id).strip():
            return None
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM family_profiles WHERE user_id = ? AND is_legacy_quarantined = 0 LIMIT 1",
                (str(user_id).strip(),),
            ).fetchone()
        if row is None:
            return None
        return self.get_profile(str(row["id"]))

    def save_profile_for_user(
        self, user_id: str, profile: FamilyProfile | dict[str, Any]
    ) -> FamilyProfile:
        """Atomically save a `FamilyProfile` scoped strictly to `user_id` with namespaced child/wallet PKs."""
        clean_uid = str(user_id or "").strip()
        if not clean_uid:
            raise ValueError("user_id is required to save a user profile")
        prof_id = f"user-profile-{clean_uid}"
        if isinstance(profile, FamilyProfile):
            raw_dict = profile.to_dict()
        else:
            raw_dict = dict(profile)
        raw_dict["id"] = prof_id
        prof = FamilyProfile.from_dict(raw_dict)
        prof.id = prof_id
        for idx, child in enumerate(prof.children, start=1):
            child.id = f"{prof_id}:child:{idx}"
            child.family_profile_id = prof_id
            if not child.child_name or not child.child_name.strip():
                child.child_name = "ילד/ה"
        for idx, wallet in enumerate(prof.passenger_loyalty_wallets, start=1):
            wallet.id = f"{prof_id}:wallet:{idx}"
            wallet.family_profile_id = prof_id
        return self._persist_profile_row(prof, user_id=clean_uid, namespace_all=True)

    def save_profile(
        self,
        profile: FamilyProfile | dict[str, Any],
        user_id: Optional[str] = None,
    ) -> FamilyProfile:
        """Atomically validate and upsert `family_profiles`, `child_frameworks`, and `passenger_loyalty_wallets`."""
        if user_id is not None:
            return self.save_profile_for_user(user_id, profile)
        prof = (
            profile
            if isinstance(profile, FamilyProfile)
            else FamilyProfile.from_dict(profile)
        )
        return self._persist_profile_row(prof, user_id=None, namespace_all=False)

    def _persist_profile_row(
        self,
        prof: FamilyProfile,
        user_id: Optional[str],
        namespace_all: bool,
    ) -> FamilyProfile:
        now = _now_iso()
        prof.updated_at = now
        if not prof.created_at:
            prof.created_at = now

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO family_profiles (
                    id, user_id, is_legacy_quarantined, profile_name, adults_count,
                    matmid_points_balance, has_flycard, flycard_tier,
                    flycard_companion_vouchers, point_valuation_usd,
                    preferred_currency, created_at, updated_at
                ) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id = COALESCE(excluded.user_id, family_profiles.user_id),
                    is_legacy_quarantined = 0,
                    profile_name = excluded.profile_name,
                    adults_count = excluded.adults_count,
                    matmid_points_balance = excluded.matmid_points_balance,
                    has_flycard = excluded.has_flycard,
                    flycard_tier = excluded.flycard_tier,
                    flycard_companion_vouchers = excluded.flycard_companion_vouchers,
                    point_valuation_usd = excluded.point_valuation_usd,
                    preferred_currency = excluded.preferred_currency,
                    updated_at = excluded.updated_at
                """,
                (
                    prof.id,
                    user_id,
                    prof.profile_name,
                    prof.adults_count,
                    prof.matmid_points_balance,
                    1 if prof.has_flycard else 0,
                    prof.flycard_tier,
                    prof.flycard_companion_vouchers,
                    prof.point_valuation_usd,
                    prof.preferred_currency,
                    prof.created_at,
                    prof.updated_at,
                ),
            )

            conn.execute(
                "DELETE FROM child_frameworks WHERE family_profile_id = ?",
                (prof.id,),
            )
            seen_child_ids: set[str] = set()
            for idx, child in enumerate(prof.children, start=1):
                cid = f"{prof.id}:child:{idx}" if namespace_all else (child.id or f"{prof.id}:child:{idx}")
                if not namespace_all:
                    existing_c = conn.execute(
                        "SELECT family_profile_id FROM child_frameworks WHERE id = ?",
                        (cid,),
                    ).fetchone()
                    if existing_c is not None or cid in seen_child_ids:
                        cid = f"{prof.id}:child:{idx}"
                seen_child_ids.add(cid)
                child.id = cid
                child.family_profile_id = prof.id
                child_dict = child.to_dict()
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
                        cid,
                        prof.id,
                        child.child_name,
                        child.child_age_years,
                        child_dict["birth_date"],
                        child.passenger_Current_type,
                        child_dict["framework_type"],
                        child.education_stream,
                        child.school_week_days,
                        child_dict["holiday_extension_mode"],
                        1 if child.treat_camp_as_vacation else 0,
                        child.max_school_days_missed,
                        child.absence_penalty_weight,
                        child_dict["bagrut_blackout_dates_json"],
                    ),
                )

            conn.execute(
                "DELETE FROM passenger_loyalty_wallets WHERE family_profile_id = ?",
                (prof.id,),
            )
            seen_wallet_ids: set[str] = set()
            for idx, wallet in enumerate(prof.passenger_loyalty_wallets, start=1):
                wid = f"{prof.id}:wallet:{idx}" if namespace_all else (wallet.id or f"{prof.id}:wallet:{idx}")
                if not namespace_all:
                    existing_w = conn.execute(
                        "SELECT family_profile_id FROM passenger_loyalty_wallets WHERE id = ?",
                        (wid,),
                    ).fetchone()
                    if existing_w is not None or wid in seen_wallet_ids:
                        wid = f"{prof.id}:wallet:{idx}"
                seen_wallet_ids.add(wid)
                wallet.id = wid
                wallet.family_profile_id = prof.id
                wallet_dict = wallet.to_dict()
                conn.execute(
                    """
                    INSERT INTO passenger_loyalty_wallets (
                        id, family_profile_id, passenger_id, passenger_name,
                        program_code, available_points, can_pool_with_family,
                        pool_group_id, transfer_ratio_to_airline,
                        has_club_credit_card, companion_vouchers_count,
                        point_valuation_cents, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        wid,
                        prof.id,
                        wallet.passenger_id,
                        wallet.passenger_name,
                        wallet_dict["program_code"],
                        wallet.available_points,
                        1 if wallet.can_pool_with_family else 0,
                        wallet.pool_group_id,
                        wallet.transfer_ratio_to_airline,
                        1 if wallet.has_club_credit_card else 0,
                        wallet.companion_vouchers_count,
                        wallet.point_valuation_cents,
                        wallet_dict["updated_at"],
                    ),
                )

        reloaded = (
            self.get_profile_for_user(user_id)
            if user_id is not None
            else self.get_profile(prof.id)
        )
        if reloaded is None:
            raise RuntimeError(f"Failed to reload saved profile {prof.id}")
        return reloaded

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a family profile (cascading to children, wallets, and queries)."""
        with self.connection() as conn:
            cur = conn.execute(
                "DELETE FROM family_profiles WHERE id = ?", (profile_id,)
            )
            return cur.rowcount > 0

    def delete_profile_for_user(self, user_id: str) -> bool:
        """Delete only the family profile owned by `user_id`."""
        if not user_id or not str(user_id).strip():
            return False
        with self.connection() as conn:
            cur = conn.execute(
                "DELETE FROM family_profiles WHERE user_id = ?",
                (str(user_id).strip(),),
            )
            return cur.rowcount > 0

    def get_moe_windows(
        self, school_year: str, framework_type: Optional[str] = None
    ) -> list[MoEVacationWindow]:
        """Query `moe_vacation_windows` for a school year and optional framework."""
        with self.connection() as conn:
            if framework_type:
                fw_val = (
                    framework_type.value
                    if isinstance(framework_type, MoEFrameworkType)
                    else str(framework_type)
                )
                rows = conn.execute(
                    """
                    SELECT * FROM moe_vacation_windows
                    WHERE school_year = ? AND framework_type = ?
                    ORDER BY start_date ASC, holiday_code ASC
                    """,
                    (school_year, fw_val),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM moe_vacation_windows
                    WHERE school_year = ?
                    ORDER BY start_date ASC, framework_type ASC
                    """,
                    (school_year,),
                ).fetchall()
        return [MoEVacationWindow.from_dict(dict(r)) for r in rows]

    def upsert_moe_windows(
        self, windows: list[MoEVacationWindow | dict[str, Any]]
    ) -> int:
        """Atomically insert or replace `moe_vacation_windows` rows."""
        parsed = [
            w if isinstance(w, MoEVacationWindow) else MoEVacationWindow.from_dict(w)
            for w in windows
        ]
        if not parsed:
            return 0
        with self.connection() as conn:
            for w in parsed:
                wd = w.to_dict()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO moe_vacation_windows (
                        id, school_year, circular_id, holiday_code,
                        holiday_name_he, holiday_name_en, framework_type,
                        start_date, end_date, resumes_on_date,
                        is_covered_by_nitzanim, nitzanim_start_date, nitzanim_end_date,
                        tlv_airport_closed,
                        calendar_sync_source, last_synced_at, source_reference
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        wd["id"],
                        wd["school_year"],
                        wd["circular_id"],
                        wd["holiday_code"],
                        wd["holiday_name_he"],
                        wd["holiday_name_en"],
                        wd["framework_type"],
                        wd["start_date"],
                        wd["end_date"],
                        wd["resumes_on_date"],
                        1 if w.is_covered_by_nitzanim else 0,
                        wd["nitzanim_start_date"],
                        wd["nitzanim_end_date"],
                        1 if w.tlv_airport_closed else 0,
                        wd["calendar_sync_source"],
                        wd["last_synced_at"],
                        wd["source_reference"],
                    ),
                )
        return len(parsed)

    def get_cached_elal_bonus(
        self,
        destinations: Optional[list[str]] = None,
        start_date: Optional[date | str] = None,
        end_date: Optional[date | str] = None,
        origin: str = "TLV",
        direction: Optional[str] = None,
        include_expired: bool = True,
    ) -> list[ElAlBonusAvailability]:
        """Query `elal_bonus_availability` matching route and date range."""
        clauses: list[str] = []
        params: list[Any] = []

        orig = origin.upper()
        norm_dests = (
            [d.upper() for d in destinations if d and d.upper() != "ANYWHERE"]
            if destinations
            else []
        )
        if norm_dests:
            placeholders = ",".join("?" for _ in norm_dests)
            clauses.append(
                f"((origin_iata = ? AND destination_iata IN ({placeholders})) "
                f"OR (origin_iata IN ({placeholders}) AND destination_iata = ?))"
            )
            params.extend([orig, *norm_dests, *norm_dests, orig])

        if direction:
            clauses.append("direction = ?")
            params.append(direction.upper())

        s_str = _to_date_str(start_date)
        e_str = _to_date_str(end_date)
        if s_str:
            clauses.append("flight_date >= ?")
            params.append(s_str)
        if e_str:
            clauses.append("flight_date <= ?")
            params.append(e_str)
        if not include_expired:
            clauses.append("expires_at > ?")
            params.append(_now_iso())

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM elal_bonus_availability {where_sql} ORDER BY flight_date ASC, flight_number ASC"
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [ElAlBonusAvailability.from_dict(dict(r)) for r in rows]

    def is_elal_bonus_cache_fresh(
        self,
        destinations: list[str],
        start_date: date | str,
        end_date: date | str,
        origin: str = "TLV",
    ) -> bool:
        """Check whether non-expired Tier-1 cache records exist for the route/dates."""
        fresh_rows = self.get_cached_elal_bonus(
            destinations=destinations,
            start_date=start_date,
            end_date=end_date,
            origin=origin,
            include_expired=False,
        )
        return len(fresh_rows) > 0

    def upsert_elal_bonus(
        self,
        records: list[ElAlBonusAvailability | dict[str, Any]],
        ttl_seconds: int = 14400,
    ) -> int:
        """Insert or replace `elal_bonus_availability` rows with a 4-hour default TTL."""
        now_dt = datetime.now(UTC).replace(microsecond=0)
        fetched_iso = now_dt.isoformat().replace("+00:00", "Z")
        expires_iso = (
            (now_dt + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        )

        parsed = [
            r
            if isinstance(r, ElAlBonusAvailability)
            else ElAlBonusAvailability.from_dict(r)
            for r in records
        ]
        if not parsed:
            return 0

        with self.connection() as conn:
            for rec in parsed:
                rd = rec.to_dict()
                f_at = rd.get("fetched_at") or fetched_iso
                raw_exp = str(rd.get("expires_at") or "").strip()
                if not raw_exp or raw_exp == f_at or ttl_seconds != 14400:
                    e_at = expires_iso
                else:
                    e_at = raw_exp
                rec.fetched_at = f_at
                rec.expires_at = e_at
                conn.execute(
                    """
                    INSERT OR REPLACE INTO elal_bonus_availability (
                        id, origin_iata, destination_iata, direction,
                        flight_number, operating_carrier, flight_date,
                        departure_time_local, arrival_time_local, aircraft_type,
                        economy_award_seats, economy_seats_is_two_plus, economy_rbd_code,
                        premium_award_seats, premium_seats_is_two_plus, premium_rbd_code,
                        business_award_seats, business_seats_is_two_plus, business_rbd_code,
                        award_zone, economy_points_per_pax, premium_points_per_pax,
                        business_points_per_pax, flycard_promo_active,
                        taxes_usd_per_pax, source_url, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rd["id"],
                        rd["origin_iata"],
                        rd["destination_iata"],
                        rd["direction"],
                        rd["flight_number"],
                        rd["operating_carrier"],
                        rd["flight_date"],
                        rd["departure_time_local"],
                        rd["arrival_time_local"],
                        rd["aircraft_type"],
                        rec.economy_award_seats,
                        1 if rec.economy_seats_is_two_plus else 0,
                        rd["economy_rbd_code"],
                        rec.premium_award_seats,
                        1 if rec.premium_seats_is_two_plus else 0,
                        rd["premium_rbd_code"],
                        rec.business_award_seats,
                        1 if rec.business_seats_is_two_plus else 0,
                        rd["business_rbd_code"],
                        rd["award_zone"],
                        rec.economy_points_per_pax,
                        rec.premium_points_per_pax,
                        rec.business_points_per_pax,
                        1 if rec.flycard_promo_active else 0,
                        rec.taxes_usd_per_pax,
                        rd["source_url"],
                        f_at,
                        e_at,
                    ),
                )
        return len(parsed)

    def reconcile_live_bonus_slices(
        self,
        slices: list[dict[str, Any]],
    ) -> int:
        """Zero out or delete stale `#live` bonus rows within verified scanned slices before re-importing.

        Each slice in `slices` contains:
        - `destinations`: list of 3-letter airport IATA codes actually scanned in this batch
        - `start_date`: `date` or `'YYYY-MM-DD'` inclusive start of scanned window
        - `end_date`: `date` or `'YYYY-MM-DD'` inclusive end of scanned window
        - `cabins`: list of queried RBD cabin buckets (`'E'`, `'A'`, `'I'`)
        """
        if not slices:
            return 0

        reconciled_total = 0
        with self.connection() as conn:
            for sl in slices:
                dests = [
                    str(d).strip().upper()
                    for d in (sl.get("destinations") or [])
                    if str(d).strip()
                ]
                if not dests:
                    continue
                s_raw = sl.get("start_date")
                e_raw = sl.get("end_date")
                start_iso = (
                    s_raw.isoformat()
                    if isinstance(s_raw, date)
                    else str(s_raw)[:10]
                )
                end_iso = (
                    e_raw.isoformat()
                    if isinstance(e_raw, date)
                    else str(e_raw)[:10]
                )
                cabins = {
                    str(c).strip().upper()
                    for c in (sl.get("cabins") or ["E", "A"])
                    if str(c).strip()
                }
                if not cabins:
                    continue

                placeholders = ",".join("?" for _ in dests)
                params: list[Any] = [start_iso, end_iso, *dests, *dests]
                rows = conn.execute(
                    f"""
                    SELECT id,
                           economy_award_seats, economy_seats_is_two_plus,
                           premium_award_seats, premium_seats_is_two_plus,
                           business_award_seats, business_seats_is_two_plus
                    FROM elal_bonus_availability
                    WHERE source_url LIKE '%#live%'
                      AND flight_date >= ?
                      AND flight_date <= ?
                      AND (
                          (direction = 'OUTBOUND' AND destination_iata IN ({placeholders}))
                          OR (direction = 'INBOUND' AND origin_iata IN ({placeholders}))
                      )
                    """,
                    params,
                ).fetchall()

                if not rows:
                    continue

                delete_ids: list[str] = []
                updates: list[tuple[int, int, int, int, int, int, str]] = []
                touched_ids: list[str] = []

                for r in rows:
                    rid = str(r["id"])
                    e_seats = 0 if "E" in cabins else int(r["economy_award_seats"] or 0)
                    e_two = 0 if "E" in cabins else int(r["economy_seats_is_two_plus"] or 0)
                    p_seats = 0 if "A" in cabins else int(r["premium_award_seats"] or 0)
                    p_two = 0 if "A" in cabins else int(r["premium_seats_is_two_plus"] or 0)
                    b_seats = 0 if "I" in cabins else int(r["business_award_seats"] or 0)
                    b_two = 0 if "I" in cabins else int(r["business_seats_is_two_plus"] or 0)

                    touched_ids.append(rid)
                    if e_seats <= 0 and p_seats <= 0 and b_seats <= 0:
                        delete_ids.append(rid)
                    else:
                        updates.append((e_seats, e_two, p_seats, p_two, b_seats, b_two, rid))

                # Remove any cached itineraries/proposals referencing modified/sold-out bonus rows
                for chunk_start in range(0, len(touched_ids), 400):
                    id_chunk = touched_ids[chunk_start : chunk_start + 400]
                    id_ph = ",".join("?" for _ in id_chunk)
                    conn.execute(
                        f"""
                        DELETE FROM vacation_option_proposals
                        WHERE itinerary_id IN (
                            SELECT id FROM flight_itineraries
                            WHERE outbound_bonus_id IN ({id_ph})
                               OR inbound_bonus_id IN ({id_ph})
                        )
                        """,
                        [*id_chunk, *id_chunk],
                    )
                    conn.execute(
                        f"""
                        DELETE FROM flight_itineraries
                        WHERE outbound_bonus_id IN ({id_ph})
                           OR inbound_bonus_id IN ({id_ph})
                        """,
                        [*id_chunk, *id_chunk],
                    )

                for upd in updates:
                    conn.execute(
                        """
                        UPDATE elal_bonus_availability
                        SET economy_award_seats = ?,
                            economy_seats_is_two_plus = ?,
                            premium_award_seats = ?,
                            premium_seats_is_two_plus = ?,
                            business_award_seats = ?,
                            business_seats_is_two_plus = ?
                        WHERE id = ?
                        """,
                        upd,
                    )

                for chunk_start in range(0, len(delete_ids), 400):
                    del_chunk = delete_ids[chunk_start : chunk_start + 400]
                    del_ph = ",".join("?" for _ in del_chunk)
                    conn.execute(
                        f"DELETE FROM elal_bonus_availability WHERE id IN ({del_ph})",
                        del_chunk,
                    )

                reconciled_total += len(touched_ids)

        return reconciled_total

    def get_commercial_flights(
        self,
        origin: str,
        destinations: list[str],
        departure_date: date | str,
        return_date: date | str,
        airline_selection_mode: str = "ALL_AIRLINES",
        include_sundor: bool = True,
        direct_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return commercial flight offerings for a route and date pair."""
        if self.is_live_fetch_mode():
            return []
        dep = (
            departure_date
            if isinstance(departure_date, date)
            else date.fromisoformat(str(departure_date)[:10])
        )
        ret = (
            return_date
            if isinstance(return_date, date)
            else date.fromisoformat(str(return_date)[:10])
        )
        return generate_commercial_flights_for_route(
            origin=origin,
            destinations=destinations,
            departure_date=dep,
            return_date=ret,
            airline_selection_mode=airline_selection_mode,
            include_sundor=include_sundor,
            direct_only=direct_only,
        )

    @staticmethod
    def _write_search_query_on_conn(
        conn: sqlite3.Connection,
        query: FlightSearchQuery | dict[str, Any],
    ) -> FlightSearchQuery:
        explicit_null_profile = (
            isinstance(query, dict)
            and "family_profile_id" in query
            and query["family_profile_id"] is None
        )
        q = (
            query
            if isinstance(query, FlightSearchQuery)
            else FlightSearchQuery.from_dict(query)
        )
        if explicit_null_profile:
            q.family_profile_id = None  # type: ignore[assignment]
        qd = q.to_dict()
        conn.execute(
            """
            INSERT OR REPLACE INTO flight_search_queries (
                id, family_profile_id, date_selection_mode, airline_selection_mode,
                search_elal_bonus_tickets, include_sundor_flights, origin_iata,
                destination_iatas_json, specific_departure_date, specific_return_date,
                flex_days_plus_minus, school_year, target_holiday_codes_json,
                direct_holiday_code, direct_target_year, min_trip_nights,
                max_trip_nights, max_bridge_days_shift, overlap_policy,
                preferred_cabins_json, enabled_loyalty_programs_json,
                preferred_vacation_types_json, weather_filter_mode,
                min_weather_suitability_score,
                allow_hybrid_bonus_cash, direct_flights_only, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qd["id"],
                qd["family_profile_id"],
                qd["date_selection_mode"],
                qd["airline_selection_mode"],
                1 if q.search_elal_bonus_tickets else 0,
                1 if q.include_sundor_flights else 0,
                qd["origin_iata"],
                qd["destination_iatas_json"],
                qd["specific_departure_date"],
                qd["specific_return_date"],
                q.flex_days_plus_minus,
                qd["school_year"],
                qd["target_holiday_codes_json"],
                qd["direct_holiday_code"],
                qd["direct_target_year"],
                q.min_trip_nights,
                q.max_trip_nights,
                q.max_bridge_days_shift,
                qd["overlap_policy"],
                qd["preferred_cabins_json"],
                qd["enabled_loyalty_programs_json"],
                qd["preferred_vacation_types_json"],
                qd["weather_filter_mode"],
                qd["min_weather_suitability_score"],
                1 if q.allow_hybrid_bonus_cash else 0,
                1 if q.direct_flights_only else 0,
                qd["created_at"],
            ),
        )
        return q

    def save_search_query(
        self, query: FlightSearchQuery | dict[str, Any]
    ) -> FlightSearchQuery:
        """Persist a `FlightSearchQuery` row in `flight_search_queries`."""
        with self.connection() as conn:
            return self._write_search_query_on_conn(conn, query)

    @staticmethod
    def _write_itinerary_on_conn(
        conn: sqlite3.Connection,
        itinerary: FlightItinerary | dict[str, Any],
    ) -> FlightItinerary:
        itin = (
            itinerary
            if isinstance(itinerary, FlightItinerary)
            else FlightItinerary.from_dict(itinerary)
        )
        it_dict = itin.to_dict()
        conn.execute(
            """
            INSERT OR REPLACE INTO flight_itineraries (
                id, search_query_id, origin_iata, destination_iata, return_origin_iata,
                destination_city_he, destination_city_en, departure_date, return_date,
                trip_nights, primary_carrier_iata, is_elal_flight, utilizes_elal_bonus,
                fulfillment_strategy, outbound_legs_json, inbound_legs_json,
                outbound_bonus_id, inbound_bonus_id,
                seated_passengers_count, bonus_tickets_count, cash_tickets_count, primary_cabin,
                points_used_by_wallet_json, requires_two_plus_seat_verification,
                total_matmid_points, total_taxes_and_fees_usd,
                total_supplemental_cash_fares_usd, total_baggage_fees_usd,
                total_out_of_pocket_cash_usd, full_cash_benchmark_usd,
                net_cash_saved_usd, cents_per_point_value,
                rbddataclients_verify_url, booking_deep_link_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                it_dict["id"],
                it_dict["search_query_id"],
                it_dict["origin_iata"],
                it_dict["destination_iata"],
                it_dict["return_origin_iata"],
                it_dict["destination_city_he"],
                it_dict["destination_city_en"],
                it_dict["departure_date"],
                it_dict["return_date"],
                itin.trip_nights,
                it_dict["primary_carrier_iata"],
                1 if itin.is_elal_flight else 0,
                1 if itin.utilizes_elal_bonus else 0,
                it_dict["fulfillment_strategy"],
                it_dict["outbound_legs_json"],
                it_dict["inbound_legs_json"],
                it_dict["outbound_bonus_id"],
                it_dict["inbound_bonus_id"],
                itin.seated_passengers_count,
                itin.bonus_tickets_count,
                itin.cash_tickets_count,
                itin.primary_cabin,
                it_dict["points_used_by_wallet_json"],
                1 if itin.requires_two_plus_seat_verification else 0,
                itin.total_matmid_points,
                itin.total_taxes_and_fees_usd,
                itin.total_supplemental_cash_fares_usd,
                itin.total_baggage_fees_usd,
                itin.total_out_of_pocket_cash_usd,
                itin.full_cash_benchmark_usd,
                itin.net_cash_saved_usd,
                itin.cents_per_point_value,
                it_dict["rbddataclients_verify_url"],
                it_dict["booking_deep_link_url"],
            ),
        )
        return itin

    def save_itinerary(
        self, itinerary: FlightItinerary | dict[str, Any]
    ) -> FlightItinerary:
        """Persist a `FlightItinerary` row in `flight_itineraries`."""
        with self.connection() as conn:
            return self._write_itinerary_on_conn(conn, itinerary)

    def _write_proposal_on_conn(
        self,
        conn: sqlite3.Connection,
        proposal: VacationOptionProposal | dict[str, Any],
    ) -> VacationOptionProposal:
        prop = (
            proposal
            if isinstance(proposal, VacationOptionProposal)
            else VacationOptionProposal.from_dict(proposal)
        )
        if prop.itinerary is not None:
            if not prop.itinerary.search_query_id and prop.search_query_id:
                prop.itinerary.search_query_id = prop.search_query_id
            self._write_itinerary_on_conn(conn, prop.itinerary)
            prop.itinerary_id = prop.itinerary.id

        pd = prop.to_dict()
        conn.execute(
            """
            INSERT OR REPLACE INTO vacation_option_proposals (
                id, search_query_id, itinerary_id, associated_holiday_codes_json,
                window_set_type, school_absence_penalty, childcare_coverage_gain,
                per_child_impact_json, total_school_days_missed_across_children,
                max_single_child_school_days_missed, holiday_alignment_score,
                flight_bonus_value_score, weather_suitability_score,
                vacation_type_scores_json, weather_metrics_json,
                combined_trip_optimization_score,
                explanation_summary_he, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pd["id"],
                pd["search_query_id"],
                pd["itinerary_id"],
                pd["associated_holiday_codes_json"],
                pd["window_set_type"],
                prop.school_absence_penalty,
                prop.childcare_coverage_gain,
                pd["per_child_impact_json"],
                prop.total_school_days_missed_across_children,
                prop.max_single_child_school_days_missed,
                prop.holiday_alignment_score,
                prop.flight_bonus_value_score,
                prop.weather_suitability_score,
                pd["vacation_type_scores_json"],
                pd["weather_metrics_json"],
                prop.combined_trip_optimization_score,
                pd["explanation_summary_he"],
                pd["created_at"],
            ),
        )
        return prop

    def save_proposal(
        self, proposal: VacationOptionProposal | dict[str, Any]
    ) -> VacationOptionProposal:
        """Persist a `VacationOptionProposal` (and its embedded `itinerary` if present)."""
        with self.connection() as conn:
            return self._write_proposal_on_conn(conn, proposal)

    def save_search_results(
        self,
        query: FlightSearchQuery | dict[str, Any],
        proposals: list[VacationOptionProposal],
    ) -> list[VacationOptionProposal]:
        """Atomically persist `flight_search_queries`, `flight_itineraries`, and `vacation_option_proposals` in one transaction."""
        with self.connection() as conn:
            q = self._write_search_query_on_conn(conn, query)
            saved: list[VacationOptionProposal] = []
            for prop in proposals:
                prop.search_query_id = q.id
                if prop.itinerary is not None:
                    prop.itinerary.search_query_id = q.id
                saved.append(self._write_proposal_on_conn(conn, prop))
            return saved

    def get_proposal_by_id(
        self, proposal_id: str
    ) -> Optional[VacationOptionProposal]:
        """Load a single `VacationOptionProposal` joined with its `FlightItinerary`."""
        with self.connection() as conn:
            p_row = conn.execute(
                "SELECT * FROM vacation_option_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if p_row is None:
                return None
            i_row = conn.execute(
                "SELECT * FROM flight_itineraries WHERE id = ?",
                (p_row["itinerary_id"],),
            ).fetchone()

        p_dict = dict(p_row)
        if i_row is not None:
            p_dict["itinerary"] = FlightItinerary.from_dict(dict(i_row))
        return VacationOptionProposal.from_dict(p_dict)

    def get_proposals_by_ids(
        self, proposal_ids: list[str]
    ) -> list[VacationOptionProposal]:
        """Load multiple `VacationOptionProposal` records by ID."""
        if not proposal_ids:
            return []
        result: list[VacationOptionProposal] = []
        for pid in proposal_ids:
            prop = self.get_proposal_by_id(pid)
            if prop is not None:
                result.append(prop)
        return result

    def get_cached_itineraries(
        self,
        search_query_id: Optional[str] = None,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        departure_date: Optional[date | str] = None,
        return_date: Optional[date | str] = None,
        ttl_seconds: int = 21600,
        include_expired: bool = False,
    ) -> list[FlightItinerary]:
        """Query Tier-2 cached `flight_itineraries` with 6-hour (`21,600s`) default TTL."""
        clauses: list[str] = []
        params: list[Any] = []
        if search_query_id:
            clauses.append("i.search_query_id = ?")
            params.append(search_query_id)
        if origin:
            clauses.append("i.origin_iata = ?")
            params.append(origin.upper())
        if destination:
            clauses.append("i.destination_iata = ?")
            params.append(destination.upper())
        dep_str = _to_date_str(departure_date)
        ret_str = _to_date_str(return_date)
        if dep_str:
            clauses.append("i.departure_date = ?")
            params.append(dep_str)
        if ret_str:
            clauses.append("i.return_date = ?")
            params.append(ret_str)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT i.*, q.created_at AS query_created_at
            FROM flight_itineraries i
            LEFT JOIN flight_search_queries q ON i.search_query_id = q.id
            {where_sql}
            ORDER BY i.departure_date ASC, i.id ASC
        """
        now_dt = datetime.now(UTC).replace(microsecond=0)
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        results: list[FlightItinerary] = []
        for r in rows:
            row_dict = dict(r)
            q_created = row_dict.pop("query_created_at", None)
            if not include_expired and not _is_timestamp_fresh(
                q_created, ttl_seconds, now_dt=now_dt
            ):
                continue
            results.append(FlightItinerary.from_dict(row_dict))
        return results

    def is_itinerary_cache_fresh(
        self,
        search_query_id: Optional[str] = None,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        departure_date: Optional[date | str] = None,
        return_date: Optional[date | str] = None,
        ttl_seconds: int = 21600,
    ) -> bool:
        """Check whether non-expired Tier-2 (6-hour default TTL) cached itineraries exist."""
        fresh = self.get_cached_itineraries(
            search_query_id=search_query_id,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            ttl_seconds=ttl_seconds,
            include_expired=False,
        )
        return len(fresh) > 0

    def get_cached_proposals_for_query(
        self,
        search_query_id: str,
        ttl_seconds: int = 21600,
        include_expired: bool = False,
    ) -> list[VacationOptionProposal]:
        """Load cached `VacationOptionProposal` records for a search query within the 6h Tier-2 TTL."""
        now_dt = datetime.now(UTC).replace(microsecond=0)
        with self.connection() as conn:
            p_rows = conn.execute(
                """
                SELECT p.*, q.created_at AS query_created_at
                FROM vacation_option_proposals p
                LEFT JOIN flight_search_queries q ON p.search_query_id = q.id
                WHERE p.search_query_id = ?
                ORDER BY p.combined_trip_optimization_score DESC, p.id ASC
                """,
                (search_query_id,),
            ).fetchall()

            results: list[VacationOptionProposal] = []
            for p_row in p_rows:
                p_dict = dict(p_row)
                q_created = p_dict.pop("query_created_at", None)
                ts_to_check = p_dict.get("created_at") or q_created
                if not include_expired and not _is_timestamp_fresh(
                    ts_to_check, ttl_seconds, now_dt=now_dt
                ):
                    continue
                i_row = conn.execute(
                    "SELECT * FROM flight_itineraries WHERE id = ?",
                    (p_dict["itinerary_id"],),
                ).fetchone()
                if i_row is not None:
                    p_dict["itinerary"] = FlightItinerary.from_dict(dict(i_row))
                results.append(VacationOptionProposal.from_dict(p_dict))
        return results

    # ------------------------------------------------------------------
    # Gmail OIDC Users, Auth Sessions, PKCE Login States & Owner Scoping
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_user_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        d = dict(row)
        raw_prefs = d.get("notification_preferences_json") or "{}"
        try:
            prefs = json.loads(raw_prefs) if isinstance(raw_prefs, str) else dict(raw_prefs)
            if not isinstance(prefs, dict):
                prefs = {}
        except Exception:
            prefs = {}
        email_verified = bool(int(d.get("email_verified", 1)))
        notif_email = str(d.get("notification_email") or d.get("email") or "")
        return {
            "id": str(d["id"]),
            "google_sub": str(d["google_sub"]),
            "email": str(d["email"]),
            "email_verified": email_verified,
            "display_name": str(d.get("display_name") or ""),
            "notification_email": notif_email,
            "notifications_enabled": bool(int(d.get("notifications_enabled", 0))),
            "notification_preferences": {
                "award_seat_alerts": bool(prefs.get("award_seat_alerts", False)),
                "holiday_reminders": bool(prefs.get("holiday_reminders", False)),
                "preferred_locale": str(prefs.get("preferred_locale") or "he"),
            },
            "notification_consent_updated_at": d.get("notification_consent_updated_at"),
            "notification_channel_ready": bool(email_verified and notif_email),
            "created_at": str(d.get("created_at") or ""),
            "updated_at": str(d.get("updated_at") or ""),
            "last_login_at": str(d.get("last_login_at") or ""),
        }

    def upsert_google_user(
        self,
        google_sub: str,
        email: str,
        email_verified: bool = True,
        display_name: str = "",
    ) -> dict[str, Any]:
        """Atomically upsert a verified Google/Gmail user record keyed by immutable `google_sub`."""
        norm_sub = str(google_sub or "").strip()
        norm_email = str(email or "").strip().lower()
        if not norm_sub or not norm_email:
            raise ValueError("google_sub and email are required")
        clean_name = str(display_name or "").strip()[:120]
        now = _now_iso()
        ev_int = 1 if email_verified else 0

        with self._lock:
            with self.connection() as conn:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                conflict_row = conn.execute(
                    "SELECT id FROM users WHERE email = ? AND google_sub != ?",
                    (norm_email, norm_sub),
                ).fetchone()
                if conflict_row is not None:
                    raise ValueError("Email already bound to a different Google subject")

                candidate_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO users (
                        id, google_sub, email, email_verified, display_name,
                        notification_email, notifications_enabled,
                        notification_preferences_json, notification_consent_updated_at,
                        created_at, updated_at, last_login_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, ?, ?, ?)
                    ON CONFLICT(google_sub) DO UPDATE SET
                        email = excluded.email,
                        email_verified = excluded.email_verified,
                        display_name = CASE
                            WHEN excluded.display_name != '' THEN excluded.display_name
                            ELSE users.display_name
                        END,
                        notification_email = excluded.notification_email,
                        updated_at = excluded.updated_at,
                        last_login_at = excluded.last_login_at
                    """,
                    (
                        candidate_id,
                        norm_sub,
                        norm_email,
                        ev_int,
                        clean_name,
                        norm_email,
                        '{"award_seat_alerts":false,"holiday_reminders":false,"preferred_locale":"he"}',
                        now,
                        now,
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM users WHERE google_sub = ?", (norm_sub,)
                ).fetchone()
        if row is None:
            raise RuntimeError("Failed to load upserted user")
        return self._row_to_user_dict(row)

    def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        """Fetch a user record by internal UUID."""
        if not user_id:
            return None
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        return self._row_to_user_dict(row) if row is not None else None

    def update_user_notifications(
        self,
        user_id: str,
        notifications_enabled: bool,
        preferences: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Update explicit opt-in notification consent and preferences for `user_id`."""
        now = _now_iso()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
            if row is None:
                return None
            existing_user = self._row_to_user_dict(row)
            merged_prefs = dict(existing_user["notification_preferences"])
            if isinstance(preferences, dict):
                if "award_seat_alerts" in preferences:
                    merged_prefs["award_seat_alerts"] = bool(preferences["award_seat_alerts"])
                if "holiday_reminders" in preferences:
                    merged_prefs["holiday_reminders"] = bool(preferences["holiday_reminders"])
                if "preferred_locale" in preferences and preferences["preferred_locale"] in ("he", "en"):
                    merged_prefs["preferred_locale"] = str(preferences["preferred_locale"])
            elif notifications_enabled:
                merged_prefs["award_seat_alerts"] = True

            conn.execute(
                """
                UPDATE users
                SET notifications_enabled = ?,
                    notification_email = email,
                    notification_preferences_json = ?,
                    notification_consent_updated_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    1 if notifications_enabled else 0,
                    json.dumps(merged_prefs, separators=(",", ":")),
                    now,
                    now,
                    str(user_id),
                ),
            )
            updated_row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (str(user_id),)
            ).fetchone()
        return self._row_to_user_dict(updated_row) if updated_row is not None else None

    def delete_user_account(self, user_id: str) -> bool:
        """Delete a user account (cascading to sessions, family_profiles, children, wallets, queries, proposals)."""
        if not user_id:
            return False
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (str(user_id),))
            return cur.rowcount > 0

    def create_oauth_login_state(
        self,
        state_sha256: str,
        code_verifier: str,
        nonce: str,
        browser_binding_sha256: str,
        return_to: str,
        expires_at: str,
    ) -> None:
        """Persist a single-use PKCE + Login-CSRF state record and purge expired rows."""
        now = _now_iso()
        with self.connection() as conn:
            conn.execute("DELETE FROM oauth_login_states WHERE expires_at <= ?", (now,))
            conn.execute(
                """
                INSERT OR REPLACE INTO oauth_login_states (
                    state_sha256, code_verifier, nonce,
                    browser_binding_sha256, return_to, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state_sha256,
                    code_verifier,
                    nonce,
                    browser_binding_sha256,
                    return_to or "/",
                    now,
                    expires_at,
                ),
            )

    def consume_oauth_login_state(self, state_sha256: str) -> Optional[dict[str, Any]]:
        """Atomically fetch and delete a single-use OAuth login state by SHA-256 hash."""
        if not state_sha256:
            return None
        with self._lock:
            with self.connection() as conn:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute(
                    """
                    DELETE FROM oauth_login_states
                    WHERE state_sha256 = ?
                    RETURNING state_sha256, code_verifier, nonce,
                              browser_binding_sha256, return_to, created_at, expires_at
                    """,
                    (state_sha256,),
                ).fetchall()
                if not rows:
                    return None
                return dict(rows[0])

    def create_auth_session(
        self,
        user_id: str,
        token_sha256: str,
        csrf_token: str,
        expires_at: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        """Insert a hashed session record into `auth_sessions` (raw token is never stored)."""
        now_dt = datetime.now(UTC)
        now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        resolved_expires = expires_at
        if not resolved_expires:
            secs = max(60, int(ttl_seconds or 1209600))
            resolved_expires = (now_dt + timedelta(seconds=secs)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        session_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL",
                (now,),
            )
            conn.execute(
                """
                INSERT INTO auth_sessions (
                    id, user_id, token_sha256, csrf_token,
                    created_at, last_seen_at, expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (session_id, user_id, token_sha256, csrf_token, now, now, resolved_expires),
            )
        return {
            "id": session_id,
            "user_id": user_id,
            "csrf_token": csrf_token,
            "created_at": now,
            "expires_at": resolved_expires,
        }

    def get_active_session_by_token_hash(
        self, token_sha256: str
    ) -> Optional[dict[str, Any]]:
        """Resolve an active, unrevoked, non-expired session joined with its `users` record."""
        if not token_sha256:
            return None
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now_str = now_dt.isoformat().replace("+00:00", "Z")
        with self.connection() as conn:
            s_row = conn.execute(
                """
                SELECT id AS session_id, user_id, csrf_token, created_at, last_seen_at, expires_at, revoked_at
                FROM auth_sessions
                WHERE token_sha256 = ?
                """,
                (token_sha256,),
            ).fetchone()
            if s_row is None or s_row["revoked_at"] is not None:
                return None
            exp_dt = _parse_iso_utc(str(s_row["expires_at"]))
            if exp_dt is None or exp_dt <= now_dt:
                return None
            u_row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (str(s_row["user_id"]),),
            ).fetchone()
            if u_row is None:
                return None
            conn.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
                (now_str, str(s_row["session_id"])),
            )
        return {
            "session_id": str(s_row["session_id"]),
            "user_id": str(s_row["user_id"]),
            "csrf_token": str(s_row["csrf_token"]),
            "expires_at": str(s_row["expires_at"]),
            "user": self._row_to_user_dict(u_row),
        }

    def revoke_session_by_token_hash(self, token_sha256: str) -> bool:
        """Immediately revoke an `auth_sessions` record by SHA-256 token digest."""
        if not token_sha256:
            return False
        now = _now_iso()
        with self.connection() as conn:
            cur = conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE token_sha256 = ? AND revoked_at IS NULL",
                (now, token_sha256),
            )
            return cur.rowcount > 0

    def get_proposal_owner_info(self, proposal_id: str) -> Optional[dict[str, Any]]:
        """Return ownership metadata for a SQLite-persisted `VacationOptionProposal`."""
        if not proposal_id:
            return None
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT p.id AS proposal_id,
                       q.family_profile_id AS family_profile_id,
                       fp.user_id AS user_id,
                       COALESCE(fp.is_legacy_quarantined, 0) AS is_legacy_quarantined
                FROM vacation_option_proposals p
                JOIN flight_search_queries q ON p.search_query_id = q.id
                LEFT JOIN family_profiles fp ON q.family_profile_id = fp.id
                WHERE p.id = ?
                """,
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "proposal_id": str(row["proposal_id"]),
            "family_profile_id": row["family_profile_id"],
            "user_id": row["user_id"],
            "is_legacy_quarantined": bool(int(row["is_legacy_quarantined"] or 0)),
        }
