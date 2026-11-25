"""REST API v1 Endpoints & Dispatcher (`F29`) for family_vacation_planner.

Implements all core REST API endpoints using Python 3.13 standard library +
project domain services, with zero external runtime dependencies so it operates
both in-process (`VacationPlannerTestClient`) and over live HTTP (`ThreadingHTTPServer`).

Endpoints:
1. `GET  /api/v1/health`
2. `GET  /api/v1/profile`
3. `PUT  /api/v1/profile`
4. `GET  /api/v1/moe-calendar/{school_year}`
5. `POST /api/v1/moe-calendar/sync/{school_year}`
6. `POST /api/v1/elal-bonus/sync`
7. `GET  /api/v1/elal-bonus/availability`
8. `POST /api/v1/vacations/search`
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Optional
import urllib.parse

from backend.app.auth_service import (
    AuthError,
    GoogleOAuthService,
    TokenExchangerFn,
    redact_pii,
    sha256_hex,
)
from backend.app.calendar_engine.moe_calendar_service import (
    MoECalendarAutoUpdaterService,
    MoECalendarService,
    normalize_school_year,
)
from backend.app.planner_synthesizer.bonus_planner_service import (
    BonusVacationPlannerService,
)
from backend.app.providers.commercial_flights import AllAirlinesSearchAdapter
from backend.app.providers.elal_rbd_client import (
    ElAlRbdDataClientAdapter,
    METRO_IATA_EXPANSION,
)
from backend.app.schemas.domain import (
    AirlineSelectionMode,
    CURRENCIES,
    DIRECT_HOLIDAY_CODES,
    DateSelectionMode,
    EDUCATION_STREAMS,
    FLYCARD_TIERS,
    FamilyProfile,
    FlightSearchQuery,
    HolidayExtensionMode,
    LoyaltyProgramCode,
    MoEFrameworkType,
    OVERLAP_POLICIES,
    PASSENGER_FARE_TYPES,
    VACATION_TYPES,
    VACATION_TYPE_ICONS,
    VACATION_TYPE_LABELS_EN,
    VACATION_TYPE_LABELS_HE,
    WEATHER_FILTER_MODES,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    build_clean_guest_profile,
)
from backend.app.vacation_optimizer.maximizer_engine import (
    VacationMaximizerEngine,
    resolve_holiday_direct_intent_school_year,
)


_SCHOOL_YEAR_RE = re.compile(r"^(\d{4})-(\d{4})$")
_VALID_FRAMEWORKS = {e.value for e in MoEFrameworkType}
_VALID_PROGRAMS = {e.value for e in LoyaltyProgramCode}
_VALID_DATE_MODES = {e.value for e in DateSelectionMode}
_VALID_AIRLINE_MODES = {e.value for e in AirlineSelectionMode}
_VALID_HOLIDAY_CODES = set(DIRECT_HOLIDAY_CODES) | {"YOM_KIPPUR_SUKKOT_BRIDGE"}
_VALID_OVERLAP_POLICIES = set(OVERLAP_POLICIES) | {
    "CAMP_AWARE_ALL_CHILDREN_OFF",
    "WEIGHTED_MIN_ABSENCE",
}
_VALID_EXTENSION_MODES = {e.value for e in HolidayExtensionMode}
_VALID_VACATION_TYPES = set(VACATION_TYPES)
_VALID_WEATHER_FILTER_MODES = set(WEATHER_FILTER_MODES)
_VALID_CABINS = {"ECONOMY", "PREMIUM", "BUSINESS"}
_VALID_DEST_SPECIAL_TOKENS = set(METRO_IATA_EXPANSION.keys()) | {"ANYWHERE", "ALL"}
_SQLITE_INT64_MAX = (1 << 63) - 1
_MAX_POINTS_BALANCE = 10**9
_MAX_VOUCHERS_COUNT = 10**6
_MAX_FLOAT_MAGNITUDE = 1e12

_VALID_PROFILE_TOP_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "profile_name",
        "adults_count",
        "matmid_points_balance",
        "has_flycard",
        "flycard_tier",
        "flycard_companion_vouchers",
        "point_valuation_usd",
        "preferred_currency",
        "children",
        "passenger_loyalty_wallets",
        "created_at",
        "updated_at",
        "is_persisted",
        "notifications_enabled",
        "profile_id",
        "user_id",
        "email",
    }
)

_REMOVED_PTO_SEARCH_KEYS: frozenset[str] = frozenset(
    {
        "workweek_type",
        "erev_chag_pto_weight",
        "chol_hamoed_pto_weight",
        "annual_pto_budget",
        "annual_pto_days_budget",
        "max_pto_per_trip",
    }
)


def _validate_optional_str(
    val: Any,
    field_name: str,
    max_len: int = 512,
    non_empty: bool = False,
) -> Optional[str]:
    if val is None:
        if non_empty:
            raise ValueError(f"{field_name} must be a non-empty string")
        return None
    if not isinstance(val, str):
        raise ValueError(
            f"{field_name} must be a string, got {type(val).__name__}"
        )
    if "\x00" in val:
        raise ValueError(f"{field_name} cannot contain null bytes")
    if len(val) > max_len:
        raise ValueError(f"{field_name} exceeds maximum length {max_len}")
    if non_empty and not val.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return val


def _validate_airport_iata_strict(val: Any, field_name: str) -> str:
    if not isinstance(val, str):
        raise ValueError(
            f"{field_name} must be a 3-letter ASCII IATA string, got {val!r}"
        )
    norm = val.strip().upper()
    if len(norm) != 3 or not norm.isalpha() or not norm.isascii():
        raise ValueError(
            f"{field_name} must be a 3-letter ASCII alphabetic IATA code, got {val!r}"
        )
    return norm


def _validate_destination_codes_strict(
    val: Any, field_name: str, allow_csv_str: bool = False
) -> list[str]:
    tokens: list[str] = []
    if allow_csv_str and isinstance(val, str):
        if "\x00" in val or len(val) > 1024:
            raise ValueError(f"Invalid {field_name}")
        tokens = [tok.strip().upper() for tok in val.split(",") if tok.strip()]
    elif isinstance(val, list):
        if len(val) > 200:
            raise ValueError(f"{field_name} exceeds maximum list length")
        for idx, item in enumerate(val):
            if not isinstance(item, str):
                raise ValueError(
                    f"{field_name}[{idx}] must be an IATA string, got {item!r}"
                )
            if "\x00" in item or len(item) > 64:
                raise ValueError(f"Invalid {field_name}[{idx}]")
            parts = (
                [sub.strip().upper() for sub in item.split(",") if sub.strip()]
                if allow_csv_str
                else ([item.strip().upper()] if item.strip() else [])
            )
            if not parts:
                raise ValueError(f"{field_name}[{idx}] cannot be empty")
            tokens.extend(parts)
    else:
        raise ValueError(f"{field_name} must be a non-empty list of IATA codes")

    if not tokens:
        raise ValueError(f"{field_name} must be a non-empty list of IATA codes")

    for tok in tokens:
        if tok in _VALID_DEST_SPECIAL_TOKENS:
            continue
        if len(tok) == 3 and tok.isalpha() and tok.isascii():
            continue
        raise ValueError(
            f"Invalid IATA or metropolitan code in {field_name}: {tok!r}"
        )
    return tokens


def _validate_search_destinations_strict(
    val: Any, field_name: str, allow_csv_str: bool = False
) -> list[str]:
    tokens: list[str] = []
    if allow_csv_str and isinstance(val, str):
        if "\x00" in val or len(val) > 1024:
            raise ValueError(f"Invalid {field_name}")
        if not val.strip():
            return ["ANYWHERE"]
        tokens = [tok.strip().upper() for tok in val.split(",") if tok.strip()]
    elif isinstance(val, list):
        if len(val) > 200:
            raise ValueError(f"{field_name} exceeds maximum list length")
        if not val:
            return ["ANYWHERE"]
        for idx, item in enumerate(val):
            if not isinstance(item, str):
                raise ValueError(
                    f"{field_name}[{idx}] must be an IATA string, got {item!r}"
                )
            if "\x00" in item or len(item) > 64:
                raise ValueError(f"Invalid {field_name}[{idx}]")
            parts = (
                [sub.strip().upper() for sub in item.split(",") if sub.strip()]
                if allow_csv_str
                else ([item.strip().upper()] if item.strip() else [])
            )
            if not parts:
                raise ValueError(f"{field_name}[{idx}] cannot be empty")
            tokens.extend(parts)
    else:
        raise ValueError(f"{field_name} must be a list of IATA codes")

    if not tokens:
        return ["ANYWHERE"]

    valid_search_specials = _VALID_DEST_SPECIAL_TOKENS | {"*"}
    deduped: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        if tok in valid_search_specials:
            if tok in ("ANYWHERE", "ALL", "*"):
                continue
        elif not (len(tok) == 3 and tok.isalpha() and tok.isascii()):
            raise ValueError(
                f"Invalid IATA or metropolitan code in {field_name}: {tok!r}"
            )
        if tok not in seen:
            seen.add(tok)
            deduped.append(tok)

    if any(t in ("ANYWHERE", "ALL", "*") for t in tokens):
        return ["ANYWHERE"]
    return deduped or ["ANYWHERE"]


def _validate_rbd_payload_strict(raw_payload: Any) -> None:
    if isinstance(raw_payload, bool) or not isinstance(
        raw_payload, (dict, list, str)
    ):
        raise ValueError(
            "rbd_payload must be a JSON object, non-empty list of flight objects, or table string"
        )
    if isinstance(raw_payload, str):
        s = raw_payload.strip()
        if not s or "\x00" in raw_payload:
            raise ValueError("rbd_payload string must be non-empty")
        if s.startswith(("{", "[")):
            try:
                parsed = json.loads(s)
            except Exception as exc:
                raise ValueError(f"Invalid JSON in rbd_payload: {exc}") from exc
            _validate_rbd_payload_strict(parsed)
        return
    if isinstance(raw_payload, dict):
        if "AccumulatedOutput" not in raw_payload or not isinstance(
            raw_payload.get("AccumulatedOutput"), dict
        ):
            raise ValueError(
                "rbd_payload object must contain an 'AccumulatedOutput' object"
            )
        return
    if not raw_payload:
        raise ValueError("rbd_payload list must not be empty")
    for idx, item in enumerate(raw_payload):
        if not isinstance(item, dict) or not item:
            raise ValueError(f"rbd_payload[{idx}] must be a non-empty object")
        if "AccumulatedOutput" in item:
            if not isinstance(item.get("AccumulatedOutput"), dict):
                raise ValueError(
                    f"rbd_payload[{idx}].AccumulatedOutput must be an object"
                )
        elif not any(
            k in item for k in ("flight_date", "date", "SegmentDepDate")
        ):
            raise ValueError(
                f"rbd_payload[{idx}] must contain 'AccumulatedOutput' or flight date fields"
            )


def _validate_reconcile_slices_strict(
    raw_slices: Any,
    expand_metro_fn: Any,
) -> list[dict[str, Any]]:
    if not isinstance(raw_slices, list):
        raise ValueError("reconcile_slices must be a list of slice objects")
    if len(raw_slices) > 200:
        raise ValueError("reconcile_slices exceeds maximum list length (200)")
    allowed_cabins = {"E", "A", "I"}
    validated: list[dict[str, Any]] = []
    for idx, sl in enumerate(raw_slices):
        if not isinstance(sl, dict):
            raise ValueError(f"reconcile_slices[{idx}] must be an object")
        dest_codes = _validate_destination_codes_strict(
            sl.get("destinations"),
            f"reconcile_slices[{idx}].destinations",
            allow_csv_str=True,
        )
        expanded_dests = expand_metro_fn(dest_codes)
        s_date = _parse_iso_date_strict(
            sl.get("start_date"), f"reconcile_slices[{idx}].start_date"
        )
        e_date = _parse_iso_date_strict(
            sl.get("end_date"), f"reconcile_slices[{idx}].end_date"
        )
        if e_date < s_date:
            raise ValueError(
                f"reconcile_slices[{idx}].end_date ({e_date}) must be >= start_date ({s_date})"
            )
        raw_cabins = sl.get("cabins", ["E", "A"])
        if not isinstance(raw_cabins, list) or not raw_cabins or len(raw_cabins) > 10:
            raise ValueError(
                f"reconcile_slices[{idx}].cabins must be a non-empty list of cabin codes"
            )
        cabins: list[str] = []
        for c_item in raw_cabins:
            if not isinstance(c_item, str):
                raise ValueError(
                    f"reconcile_slices[{idx}].cabins items must be strings"
                )
            cu = c_item.strip().upper()
            if cu not in allowed_cabins:
                raise ValueError(
                    f"Invalid cabin code in reconcile_slices[{idx}].cabins: {c_item!r}"
                )
            if cu not in cabins:
                cabins.append(cu)
        validated.append(
            {
                "destinations": expanded_dests,
                "start_date": s_date,
                "end_date": e_date,
                "cabins": cabins,
            }
        )
    return validated


def _parse_strict_float(
    val: Any,
    field_name: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> float:
    if val is None or isinstance(val, bool) or not isinstance(val, (int, float, str)):
        raise ValueError(f"{field_name} must be a finite number, got {val!r}")
    if isinstance(val, str):
        s = val.strip()
        if not s or len(s) > 64:
            raise ValueError(f"{field_name} must be a finite number, got {val!r}")
        raw_num: int | float | str = s
    else:
        raw_num = val
    try:
        num = float(raw_num)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a finite number, got {val!r}") from exc
    if not math.isfinite(num) or abs(num) > _MAX_FLOAT_MAGNITUDE:
        raise ValueError(f"{field_name} must be a finite number, got {val!r}")
    if min_val is not None and num < min_val:
        raise ValueError(f"{field_name} must be >= {min_val}, got {num!r}")
    if max_val is not None and num > max_val:
        raise ValueError(f"{field_name} must be <= {max_val}, got {num!r}")
    return num


def _parse_strict_int(
    val: Any,
    field_name: str,
    allow_integral_float: bool = False,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> int:
    if val is None or isinstance(val, bool) or not isinstance(val, (int, float, str)):
        raise ValueError(f"{field_name} must be an integer, got {val!r}")
    if isinstance(val, int):
        res = val
    elif isinstance(val, float):
        if (
            not math.isfinite(val)
            or not val.is_integer()
            or abs(val) > _SQLITE_INT64_MAX
        ):
            raise ValueError(f"{field_name} must be a 64-bit integer, got {val!r}")
        res = int(val)
    else:
        s = val.strip()
        if not s or len(s) > 64:
            raise ValueError(f"{field_name} must be an integer, got {val!r}")
        try:
            res = int(s)
        except ValueError as exc:
            if allow_integral_float:
                f_val = _parse_strict_float(s, field_name)
                if f_val.is_integer() and abs(f_val) <= _SQLITE_INT64_MAX:
                    res = int(f_val)
                else:
                    raise ValueError(
                        f"{field_name} must be an integer, got {val!r}"
                    ) from exc
            else:
                raise ValueError(
                    f"{field_name} must be an integer, got {val!r}"
                ) from exc
    if abs(res) > _SQLITE_INT64_MAX:
        raise ValueError(f"{field_name} exceeds signed 64-bit integer bounds")
    if min_val is not None and res < min_val:
        raise ValueError(f"{field_name} must be >= {min_val}, got {res!r}")
    if max_val is not None and res > max_val:
        raise ValueError(f"{field_name} must be <= {max_val}, got {res!r}")
    return res


def _parse_iso_date_strict(val: Any, field_name: str) -> date:
    if isinstance(val, date) and not isinstance(val, datetime):
        d = val
    else:
        if not isinstance(val, str) or not val.strip():
            raise ValueError(
                f"{field_name} must be a non-empty ISO date string YYYY-MM-DD"
            )
        s = val.strip()
        if len(s) != 10 or not s.isascii():
            raise ValueError(f"Invalid ISO date for {field_name}: {val!r}")
        try:
            d = date.fromisoformat(s)
        except Exception as exc:
            raise ValueError(f"Invalid ISO date for {field_name}: {val!r}") from exc
    if d.year < 1900 or d.year > 2100:
        raise ValueError(
            f"{field_name} year must be between 1900 and 2100, got {d.year}"
        )
    return d


def _validate_school_year_strict(school_year: Any) -> str:
    if (
        not isinstance(school_year, str)
        or not school_year.strip()
        or not school_year.isascii()
    ):
        raise ValueError(
            "school_year must be an ASCII string in 'YYYY-YYYY' or 'YYYY' format"
        )
    norm = normalize_school_year(school_year.strip())
    y1 = int(norm.split("-")[0])
    if y1 < 2020 or y1 > 2100:
        raise ValueError(
            f"school_year out of supported bounds (2020..2100): {norm!r}"
        )
    return norm


def _validate_profile_payload_strict(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Profile payload must be a JSON object")

    unknown_keys = sorted(set(payload.keys()) - _VALID_PROFILE_TOP_KEYS)
    if unknown_keys:
        raise ValueError(f"Unsupported or removed profile fields: {unknown_keys}")

    for str_key, max_l in (
        ("id", 128),
        ("profile_id", 128),
        ("user_id", 128),
        ("email", 256),
        ("profile_name", 256),
        ("created_at", 128),
        ("updated_at", 128),
    ):
        if str_key in payload:
            _validate_optional_str(payload[str_key], str_key, max_len=max_l)

    if "is_persisted" in payload and payload["is_persisted"] is not None:
        if not isinstance(payload["is_persisted"], bool):
            raise ValueError("is_persisted must be a boolean")

    if "notifications_enabled" in payload and payload["notifications_enabled"] is not None:
        if not isinstance(payload["notifications_enabled"], bool):
            raise ValueError("notifications_enabled must be a boolean")

    if "has_flycard" in payload:
        if not isinstance(payload["has_flycard"], bool):
            raise ValueError("has_flycard must be a boolean")

    if "adults_count" in payload:
        adults = _parse_strict_int(
            payload["adults_count"], "adults_count", min_val=1, max_val=6
        )
        payload["adults_count"] = adults

    if "flycard_tier" in payload:
        fc_tier = payload["flycard_tier"]
        if not isinstance(fc_tier, str) or fc_tier not in FLYCARD_TIERS:
            raise ValueError(f"Invalid flycard_tier: {fc_tier!r}")

    if "preferred_currency" in payload:
        curr = payload["preferred_currency"]
        if not isinstance(curr, str) or curr not in CURRENCIES:
            raise ValueError(f"Invalid preferred_currency: {curr!r}")

    if "matmid_points_balance" in payload:
        payload["matmid_points_balance"] = _parse_strict_int(
            payload["matmid_points_balance"],
            "matmid_points_balance",
            allow_integral_float=True,
            min_val=0,
            max_val=_MAX_POINTS_BALANCE,
        )

    if "flycard_companion_vouchers" in payload:
        payload["flycard_companion_vouchers"] = _parse_strict_int(
            payload["flycard_companion_vouchers"],
            "flycard_companion_vouchers",
            allow_integral_float=True,
            min_val=0,
            max_val=_MAX_VOUCHERS_COUNT,
        )

    if "point_valuation_usd" in payload:
        pv_val = _parse_strict_float(
            payload["point_valuation_usd"],
            "point_valuation_usd",
            max_val=1e6,
        )
        if pv_val <= 0.0:
            raise ValueError("point_valuation_usd must be > 0")
        payload["point_valuation_usd"] = pv_val

    children = payload.get("children", [])
    if not isinstance(children, list) or len(children) > 25:
        raise ValueError("children must be a list of at most 25 items")
    norm_children: list[dict[str, Any]] = []
    for idx, raw_child in enumerate(children):
        if not isinstance(raw_child, dict):
            raise ValueError(f"children[{idx}] must be an object")
        child = dict(raw_child)
        for c_str_key in (
            "id",
            "family_profile_id",
            "child_name",
            "child_name_he",
            "name",
            "created_at",
            "updated_at",
        ):
            if c_str_key in child:
                _validate_optional_str(
                    child[c_str_key], f"children[{idx}].{c_str_key}", max_len=256
                )
        if (
            "name" in child
            and "child_name" not in child
            and isinstance(child["name"], str)
        ):
            child["child_name"] = child["name"]

        if "age" in child:
            age_alias = _parse_strict_int(
                child["age"],
                f"children[{idx}].age",
                allow_integral_float=True,
                min_val=0,
                max_val=18,
            )
            child["age"] = age_alias
            if "child_age_years" not in child:
                child["child_age_years"] = age_alias

        age_int = _parse_strict_int(
            child.get("child_age_years"),
            f"children[{idx}].child_age_years",
            allow_integral_float=True,
            min_val=0,
            max_val=18,
        )
        child["child_age_years"] = age_int

        if "birth_date" in child:
            _validate_optional_str(
                child["birth_date"], f"children[{idx}].birth_date", max_len=32
            )
            if child["birth_date"]:
                _parse_iso_date_strict(
                    child["birth_date"], f"children[{idx}].birth_date"
                )

        for pax_key in ("passenger_Current_type", "passenger_current_type"):
            if pax_key in child:
                _validate_optional_str(
                    child[pax_key], f"children[{idx}].{pax_key}", max_len=32
                )
                if child[pax_key] and child[pax_key] not in PASSENGER_FARE_TYPES:
                    raise ValueError(
                        f"children[{idx}].{pax_key} {child[pax_key]!r} is invalid"
                    )

        if "framework_type" in child:
            _validate_optional_str(
                child["framework_type"],
                f"children[{idx}].framework_type",
                max_len=64,
            )
            fw = child["framework_type"]
            if fw is not None and fw != "" and fw not in _VALID_FRAMEWORKS:
                raise ValueError(
                    f"children[{idx}].framework_type {fw!r} is not a valid MoEFrameworkType"
                )

        if "education_stream" in child:
            _validate_optional_str(
                child["education_stream"],
                f"children[{idx}].education_stream",
                max_len=64,
            )
            ed_s = child["education_stream"]
            if ed_s is not None and ed_s != "" and ed_s not in EDUCATION_STREAMS:
                raise ValueError(
                    f"children[{idx}].education_stream {ed_s!r} is invalid"
                )

        if "school_week_days" in child:
            sw_int = _parse_strict_int(
                child["school_week_days"], f"children[{idx}].school_week_days"
            )
            if sw_int not in (5, 6):
                raise ValueError(f"children[{idx}].school_week_days must be 5 or 6")
            child["school_week_days"] = sw_int

        if "holiday_extension_mode" in child:
            ext = child["holiday_extension_mode"]
            if not isinstance(ext, str) or ext not in _VALID_EXTENSION_MODES:
                raise ValueError(
                    f"children[{idx}].holiday_extension_mode {ext!r} is invalid"
                )

        if "treat_camp_as_vacation" in child:
            if not isinstance(child["treat_camp_as_vacation"], bool):
                raise ValueError(
                    f"children[{idx}].treat_camp_as_vacation must be a boolean"
                )

        if "max_school_days_missed" in child:
            child["max_school_days_missed"] = _parse_strict_int(
                child["max_school_days_missed"],
                f"children[{idx}].max_school_days_missed",
                min_val=0,
                max_val=14,
            )

        if "absence_penalty_weight" in child:
            child["absence_penalty_weight"] = _parse_strict_float(
                child["absence_penalty_weight"],
                f"children[{idx}].absence_penalty_weight",
                min_val=0.0,
                max_val=1e6,
            )

        if "bagrut_blackout_dates" in child and child["bagrut_blackout_dates"] is not None:
            bbd = child["bagrut_blackout_dates"]
            if not isinstance(bbd, list) or len(bbd) > 366:
                raise ValueError(
                    f"children[{idx}].bagrut_blackout_dates must be a list of ISO dates"
                )
            for b_idx, bd_item in enumerate(bbd):
                _parse_iso_date_strict(
                    bd_item,
                    f"children[{idx}].bagrut_blackout_dates[{b_idx}]",
                )

        if (
            "bagrut_blackout_dates_json" in child
            and child["bagrut_blackout_dates_json"] is not None
        ):
            bbd_json = child["bagrut_blackout_dates_json"]
            _validate_optional_str(
                bbd_json,
                f"children[{idx}].bagrut_blackout_dates_json",
                max_len=8192,
            )
            if bbd_json.strip():
                try:
                    parsed_bbd = json.loads(bbd_json)
                except Exception as exc:
                    raise ValueError(
                        f"Invalid JSON in children[{idx}].bagrut_blackout_dates_json"
                    ) from exc
                if not isinstance(parsed_bbd, list) or len(parsed_bbd) > 366:
                    raise ValueError(
                        f"children[{idx}].bagrut_blackout_dates_json must decode to a list"
                    )
                for b_idx, bd_item in enumerate(parsed_bbd):
                    _parse_iso_date_strict(
                        bd_item,
                        f"children[{idx}].bagrut_blackout_dates_json[{b_idx}]",
                    )

        norm_children.append(child)
    if "children" in payload:
        payload["children"] = norm_children

    wallets = payload.get("passenger_loyalty_wallets", [])
    if not isinstance(wallets, list) or len(wallets) > 100:
        raise ValueError("passenger_loyalty_wallets must be a list")
    norm_wallets: list[dict[str, Any]] = []
    for idx, raw_wallet in enumerate(wallets):
        if not isinstance(raw_wallet, dict):
            raise ValueError(f"passenger_loyalty_wallets[{idx}] must be an object")
        wallet = dict(raw_wallet)
        for w_str_key in (
            "id",
            "family_profile_id",
            "passenger_id",
            "passenger_name",
            "pool_group_id",
            "created_at",
            "updated_at",
        ):
            if w_str_key in wallet:
                _validate_optional_str(
                    wallet[w_str_key],
                    f"passenger_loyalty_wallets[{idx}].{w_str_key}",
                    max_len=256,
                )

        prog = wallet.get("program_code")
        if not isinstance(prog, str) or not prog or prog not in _VALID_PROGRAMS:
            raise ValueError(
                f"passenger_loyalty_wallets[{idx}].program_code {prog!r} is invalid"
            )

        if "points_balance" in wallet:
            pb_val = _parse_strict_int(
                wallet["points_balance"],
                f"passenger_loyalty_wallets[{idx}].points_balance",
                allow_integral_float=True,
                min_val=0,
                max_val=_MAX_POINTS_BALANCE,
            )
            wallet["points_balance"] = pb_val
            if "available_points" not in wallet:
                wallet["available_points"] = pb_val

        if "available_points" in wallet:
            wallet["available_points"] = _parse_strict_int(
                wallet["available_points"],
                f"passenger_loyalty_wallets[{idx}].available_points",
                allow_integral_float=True,
                min_val=0,
                max_val=_MAX_POINTS_BALANCE,
            )

        for w_bool_key in ("can_pool_with_family", "has_club_credit_card"):
            if w_bool_key in wallet:
                if not isinstance(wallet[w_bool_key], bool):
                    raise ValueError(
                        f"passenger_loyalty_wallets[{idx}].{w_bool_key} must be a boolean"
                    )

        if "companion_vouchers_count" in wallet:
            wallet["companion_vouchers_count"] = _parse_strict_int(
                wallet["companion_vouchers_count"],
                f"passenger_loyalty_wallets[{idx}].companion_vouchers_count",
                allow_integral_float=True,
                min_val=0,
                max_val=_MAX_VOUCHERS_COUNT,
            )

        if "point_valuation_cents" in wallet:
            val_cents = _parse_strict_float(
                wallet["point_valuation_cents"],
                f"passenger_loyalty_wallets[{idx}].point_valuation_cents",
                max_val=1e6,
            )
            if val_cents <= 0.0:
                raise ValueError(
                    f"passenger_loyalty_wallets[{idx}].point_valuation_cents must be > 0"
                )
            wallet["point_valuation_cents"] = val_cents

        if "transfer_ratio_to_airline" in wallet:
            tr_val = _parse_strict_float(
                wallet["transfer_ratio_to_airline"],
                f"passenger_loyalty_wallets[{idx}].transfer_ratio_to_airline",
                max_val=1e6,
            )
            if tr_val <= 0.0:
                raise ValueError(
                    f"passenger_loyalty_wallets[{idx}].transfer_ratio_to_airline must be > 0"
                )
            wallet["transfer_ratio_to_airline"] = tr_val

        norm_wallets.append(wallet)
    if "passenger_loyalty_wallets" in payload:
        payload["passenger_loyalty_wallets"] = norm_wallets


def _validate_enum_str_list_strict(
    val: Any, field_name: str, allowed_values: set[str]
) -> list[str]:
    if not isinstance(val, list) or len(val) > 100:
        raise ValueError(f"{field_name} must be a list of valid string codes")
    cleaned: list[str] = []
    for idx, item in enumerate(val):
        if not isinstance(item, str):
            raise ValueError(
                f"{field_name}[{idx}] must be a string, got {type(item).__name__}"
            )
        norm = item.strip().upper()
        if not norm or norm not in allowed_values:
            raise ValueError(
                f"Invalid {field_name}[{idx}]: {item!r}. Allowed: {sorted(allowed_values)}"
            )
        cleaned.append(norm)
    return cleaned


def _validate_search_payload_strict(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Search payload must be a JSON object")

    bad_pto_keys = sorted(set(payload.keys()) & _REMOVED_PTO_SEARCH_KEYS)
    if bad_pto_keys:
        raise ValueError(
            f"Removed PTO/workweek fields are no longer supported: {bad_pto_keys}"
        )

    for str_key in ("id", "family_profile_id", "profile_id", "created_at"):
        if str_key in payload:
            _validate_optional_str(payload[str_key], str_key, max_len=128)

    if "school_year" in payload:
        _validate_optional_str(payload["school_year"], "school_year", max_len=32)
        if isinstance(payload["school_year"], str):
            if payload["school_year"].strip():
                payload["school_year"] = _validate_school_year_strict(
                    payload["school_year"]
                )
            else:
                payload["school_year"] = None

    if "origin_iata" in payload:
        payload["origin_iata"] = _validate_airport_iata_strict(
            payload["origin_iata"], "origin_iata"
        )

    resolved_search_dests: Optional[list[str]] = None
    if "destination_iatas" in payload:
        resolved_search_dests = _validate_search_destinations_strict(
            payload["destination_iatas"],
            "destination_iatas",
            allow_csv_str=False,
        )
        payload["destination_iatas"] = resolved_search_dests

    if "destinations" in payload:
        validated_dests = _validate_search_destinations_strict(
            payload["destinations"],
            "destinations",
            allow_csv_str=True,
        )
        if resolved_search_dests is None:
            resolved_search_dests = validated_dests
            payload["destination_iatas"] = resolved_search_dests
        payload.pop("destinations", None)

    if "destination" in payload:
        _validate_optional_str(
            payload["destination"], "destination", max_len=1024, non_empty=False
        )
        if payload["destination"] is None:
            raise ValueError("destination must be a string")
        validated_dest = _validate_search_destinations_strict(
            payload["destination"],
            "destination",
            allow_csv_str=True,
        )
        if resolved_search_dests is None:
            resolved_search_dests = validated_dest
            payload["destination_iatas"] = resolved_search_dests
        payload.pop("destination", None)

    if "destination_iatas_json" in payload and payload["destination_iatas_json"] is not None:
        raw_dj = payload["destination_iatas_json"]
        _validate_optional_str(raw_dj, "destination_iatas_json", max_len=4096, non_empty=True)
        try:
            parsed_dj = json.loads(raw_dj)
        except Exception as exc:
            raise ValueError("Invalid JSON in destination_iatas_json") from exc
        validated_dj = _validate_search_destinations_strict(
            parsed_dj, "destination_iatas_json", allow_csv_str=False
        )
        if resolved_search_dests is None:
            payload["destination_iatas"] = validated_dj

    if "enabled_loyalty_programs" in payload and payload["enabled_loyalty_programs"] is not None:
        payload["enabled_loyalty_programs"] = _validate_enum_str_list_strict(
            payload["enabled_loyalty_programs"],
            "enabled_loyalty_programs",
            _VALID_PROGRAMS,
        )

    if (
        "enabled_loyalty_programs_json" in payload
        and payload["enabled_loyalty_programs_json"] is not None
    ):
        raw_pj = payload["enabled_loyalty_programs_json"]
        _validate_optional_str(raw_pj, "enabled_loyalty_programs_json", max_len=4096)
        if raw_pj.strip():
            try:
                parsed_pj = json.loads(raw_pj)
            except Exception as exc:
                raise ValueError("Invalid JSON in enabled_loyalty_programs_json") from exc
            _validate_enum_str_list_strict(
                parsed_pj, "enabled_loyalty_programs_json", _VALID_PROGRAMS
            )

    if "preferred_cabins" in payload and payload["preferred_cabins"] is not None:
        payload["preferred_cabins"] = _validate_enum_str_list_strict(
            payload["preferred_cabins"], "preferred_cabins", _VALID_CABINS
        )

    if "preferred_cabins_json" in payload and payload["preferred_cabins_json"] is not None:
        raw_cj = payload["preferred_cabins_json"]
        _validate_optional_str(raw_cj, "preferred_cabins_json", max_len=2048)
        if raw_cj.strip():
            try:
                parsed_cj = json.loads(raw_cj)
            except Exception as exc:
                raise ValueError("Invalid JSON in preferred_cabins_json") from exc
            _validate_enum_str_list_strict(
                parsed_cj, "preferred_cabins_json", _VALID_CABINS
            )

    if "target_holiday_codes" in payload and payload["target_holiday_codes"] is not None:
        payload["target_holiday_codes"] = _validate_enum_str_list_strict(
            payload["target_holiday_codes"],
            "target_holiday_codes",
            _VALID_HOLIDAY_CODES,
        )

    if (
        "target_holiday_codes_json" in payload
        and payload["target_holiday_codes_json"] is not None
    ):
        raw_hj = payload["target_holiday_codes_json"]
        _validate_optional_str(raw_hj, "target_holiday_codes_json", max_len=4096)
        if raw_hj.strip():
            try:
                parsed_hj = json.loads(raw_hj)
            except Exception as exc:
                raise ValueError("Invalid JSON in target_holiday_codes_json") from exc
            _validate_enum_str_list_strict(
                parsed_hj, "target_holiday_codes_json", _VALID_HOLIDAY_CODES
            )

    for bool_key in (
        "search_elal_bonus_tickets",
        "include_sundor_flights",
        "allow_hybrid_bonus_cash",
        "direct_flights_only",
        "include_open_jaw",
        "allow_school_absences",
    ):
        if bool_key in payload and payload[bool_key] is not None:
            if not isinstance(payload[bool_key], bool):
                raise ValueError(f"{bool_key} must be a boolean")

    if "date_selection_mode" in payload:
        d_mode = payload["date_selection_mode"]
        if not isinstance(d_mode, str) or d_mode not in _VALID_DATE_MODES:
            raise ValueError(f"Invalid date_selection_mode: {d_mode!r}")
    else:
        d_mode = "HOLIDAY_DIRECT_INTENT"

    if "airline_selection_mode" in payload:
        a_mode = payload["airline_selection_mode"]
        if not isinstance(a_mode, str) or a_mode not in _VALID_AIRLINE_MODES:
            raise ValueError(f"Invalid airline_selection_mode: {a_mode!r}")

    if "overlap_policy" in payload:
        ov_pol = payload["overlap_policy"]
        if not isinstance(ov_pol, str) or ov_pol not in _VALID_OVERLAP_POLICIES:
            raise ValueError(f"Invalid overlap_policy: {ov_pol!r}")

    if "flex_days_plus_minus" in payload:
        flex = _parse_strict_int(
            payload["flex_days_plus_minus"],
            "flex_days_plus_minus",
            min_val=0,
            max_val=7,
        )
        payload["flex_days_plus_minus"] = flex
    else:
        flex = 2

    if "max_bridge_days_shift" in payload:
        bridge = _parse_strict_int(
            payload["max_bridge_days_shift"],
            "max_bridge_days_shift",
            min_val=0,
            max_val=5,
        )
        payload["max_bridge_days_shift"] = bridge

    dep_d: Optional[date] = None
    ret_d: Optional[date] = None
    if "specific_departure_date" in payload and payload["specific_departure_date"] != "":
        if d_mode == "SPECIFIC_DATES" or payload["specific_departure_date"] is not None:
            dep_d = _parse_iso_date_strict(
                payload["specific_departure_date"], "specific_departure_date"
            )
    if "specific_return_date" in payload and payload["specific_return_date"] != "":
        if d_mode == "SPECIFIC_DATES" or payload["specific_return_date"] is not None:
            ret_d = _parse_iso_date_strict(
                payload["specific_return_date"], "specific_return_date"
            )

    if dep_d is not None and ret_d is not None:
        if d_mode == "SPECIFIC_DATES":
            if ret_d <= dep_d:
                raise ValueError(
                    f"specific_return_date ({ret_d}) must be > specific_departure_date ({dep_d})"
                )
            if "min_trip_nights" not in payload and "max_trip_nights" not in payload:
                base_nights = (ret_d - dep_d).days
                payload["min_trip_nights"] = max(1, base_nights - 2 * flex)
                payload["max_trip_nights"] = min(45, max(1, base_nights + 2 * flex))
        elif ret_d < dep_d:
            raise ValueError(
                f"specific_return_date ({ret_d}) must be >= specific_departure_date ({dep_d})"
            )

    if "direct_holiday_code" in payload:
        _validate_optional_str(
            payload["direct_holiday_code"], "direct_holiday_code", max_len=64
        )
        if payload["direct_holiday_code"]:
            h_code = payload["direct_holiday_code"]
            if h_code.strip().upper() not in _VALID_HOLIDAY_CODES:
                raise ValueError(f"Invalid direct_holiday_code: {h_code!r}")

    if "direct_target_year" in payload and payload["direct_target_year"] != "":
        t_year = _parse_strict_int(
            payload["direct_target_year"],
            "direct_target_year",
            min_val=2025,
            max_val=2099,
        )
        payload["direct_target_year"] = t_year

    if d_mode == "HOLIDAY_DIRECT_INTENT":
        if "max_trip_nights" in payload and "min_trip_nights" not in payload:
            max_req = _parse_strict_int(payload["max_trip_nights"], "max_trip_nights")
            if max_req >= 1:
                payload["min_trip_nights"] = min(4, max_req)

    if "min_trip_nights" in payload:
        min_nights = _parse_strict_int(payload["min_trip_nights"], "min_trip_nights")
        payload["min_trip_nights"] = min_nights
    else:
        min_nights = 4

    if "max_trip_nights" in payload:
        max_nights = _parse_strict_int(payload["max_trip_nights"], "max_trip_nights")
        payload["max_trip_nights"] = max_nights
    else:
        max_nights = 10

    if min_nights < 1 or max_nights < 1 or min_nights > max_nights or max_nights > 45:
        raise ValueError(
            f"Invalid trip nights range: min_trip_nights={min_nights}, max_trip_nights={max_nights}"
        )

    if "matmid_points_balance" in payload and payload["matmid_points_balance"] != "":
        mpb_val = _parse_strict_int(
            payload["matmid_points_balance"],
            "matmid_points_balance",
            allow_integral_float=True,
            min_val=0,
            max_val=_MAX_POINTS_BALANCE,
        )
        payload["matmid_points_balance"] = mpb_val

    for vt_key in (
        "preferred_vacation_types",
        "vacation_types",
        "preferred_vacation_type",
    ):
        if vt_key in payload and payload[vt_key] is not None:
            raw_vtypes = payload[vt_key]
            if isinstance(raw_vtypes, str):
                _validate_optional_str(raw_vtypes, vt_key, max_len=1024)
                vlist = [v.strip().upper() for v in raw_vtypes.split(",") if v.strip()]
            elif isinstance(raw_vtypes, list):
                if len(raw_vtypes) > 50:
                    raise ValueError(f"{vt_key} exceeds maximum list length")
                for vt_item in raw_vtypes:
                    if not isinstance(vt_item, str):
                        raise ValueError(f"{vt_key} items must be strings")
                vlist = [v.strip().upper() for v in raw_vtypes if v.strip()]
            else:
                raise ValueError(
                    f"{vt_key} must be a list or comma-separated string"
                )
            for vt in vlist:
                if vt not in _VALID_VACATION_TYPES:
                    raise ValueError(
                        f"Invalid vacation_type: {vt!r}. Allowed: {sorted(_VALID_VACATION_TYPES)}"
                    )

    if (
        "preferred_vacation_types_json" in payload
        and payload["preferred_vacation_types_json"] is not None
    ):
        raw_vtj = payload["preferred_vacation_types_json"]
        _validate_optional_str(raw_vtj, "preferred_vacation_types_json", max_len=4096)
        if raw_vtj.strip():
            try:
                parsed_vtj = json.loads(raw_vtj)
            except Exception as exc:
                raise ValueError("Invalid JSON in preferred_vacation_types_json") from exc
            _validate_enum_str_list_strict(
                parsed_vtj, "preferred_vacation_types_json", _VALID_VACATION_TYPES
            )

    for wm_key in ("weather_filter_mode", "vacation_type_filter_mode"):
        if wm_key in payload and payload[wm_key] is not None:
            raw_wmode = payload[wm_key]
            if not isinstance(raw_wmode, str):
                raise ValueError(f"Invalid {wm_key}: {raw_wmode!r}")
            if raw_wmode.strip():
                wmode_str = raw_wmode.strip().upper()
                if wmode_str not in _VALID_WEATHER_FILTER_MODES:
                    raise ValueError(
                        f"Invalid {wm_key}: {raw_wmode!r}. Allowed: {sorted(_VALID_WEATHER_FILTER_MODES)}"
                    )

    if "min_weather_suitability_score" in payload and payload["min_weather_suitability_score"] != "":
        min_wss_val = _parse_strict_float(
            payload["min_weather_suitability_score"],
            "min_weather_suitability_score",
            min_val=0.0,
            max_val=100.0,
        )
        payload["min_weather_suitability_score"] = min_wss_val

    if "inline_profile" in payload and payload["inline_profile"] is not None:
        if not isinstance(payload["inline_profile"], dict):
            raise ValueError("inline_profile must be a JSON object")
        inline_copy = dict(payload["inline_profile"])
        _validate_profile_payload_strict(inline_copy)
        payload["inline_profile"] = inline_copy

    inline_top_keys = (
        "adults_count",
        "has_flycard",
        "flycard_tier",
        "flycard_companion_vouchers",
        "children",
    )
    top_prof_subset = {
        k: payload[k]
        for k in inline_top_keys
        if k in payload and payload[k] is not None
    }
    if top_prof_subset:
        _validate_profile_payload_strict(top_prof_subset)
        for k, v in top_prof_subset.items():
            payload[k] = v


class VacationPlannerAPIRouter:
    """Dependency-injected REST API v1 dispatcher."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        token_exchanger: Optional[TokenExchangerFn] = None,
    ) -> None:
        self.repository = SQLiteRepository(db_path=db_path, auto_seed=True)
        self.auth_service = GoogleOAuthService(
            self.repository, token_exchanger=token_exchanger
        )
        self.calendar_service = MoECalendarService(self.repository)
        self.auto_updater = MoECalendarAutoUpdaterService(self.repository)
        self.maximizer_engine = VacationMaximizerEngine(self.calendar_service)
        self.elal_adapter = ElAlRbdDataClientAdapter(self.repository)
        self.commercial_adapter = AllAirlinesSearchAdapter(self.repository)
        self.planner_service = BonusVacationPlannerService(
            self.repository,
            self.calendar_service,
            self.maximizer_engine,
            self.elal_adapter,
            self.commercial_adapter,
        )

    def _build_effective_request_profile(
        self,
        session: Optional[dict[str, Any]],
        body: Optional[dict[str, Any]] = None,
        frameworks_csv: Optional[str] = None,
    ) -> tuple[FamilyProfile, bool]:
        """Construct the active household profile for search/calendar strictly from verified session or clean guest defaults."""
        if session is not None:
            saved_prof = self.repository.get_profile_for_user(session["user_id"])
            has_persisted = saved_prof is not None
            base_prof = (
                saved_prof if saved_prof is not None else build_clean_guest_profile()
            )
            if not has_persisted:
                base_prof.id = f"user-profile-{session['user_id']}"
        else:
            has_persisted = False
            base_prof = build_clean_guest_profile()

        prof_dict = base_prof.to_dict()
        override_keys = (
            "adults_count",
            "has_flycard",
            "flycard_tier",
            "flycard_companion_vouchers",
            "children",
        )
        explicit_matmid: Optional[int] = None

        if isinstance(body, dict):
            inline_prof = body.get("inline_profile")
            if isinstance(inline_prof, dict):
                for k in override_keys:
                    if k in inline_prof and inline_prof[k] is not None:
                        prof_dict[k] = inline_prof[k]
                if (
                    "matmid_points_balance" in inline_prof
                    and inline_prof["matmid_points_balance"] is not None
                    and inline_prof["matmid_points_balance"] != ""
                ):
                    explicit_matmid = int(inline_prof["matmid_points_balance"])

            for k in override_keys:
                if k in body and body[k] is not None:
                    prof_dict[k] = body[k]
            if (
                "matmid_points_balance" in body
                and body["matmid_points_balance"] is not None
                and body["matmid_points_balance"] != ""
            ):
                explicit_matmid = int(body["matmid_points_balance"])

        if explicit_matmid is not None:
            prof_dict["matmid_points_balance"] = explicit_matmid
            prof_dict["passenger_loyalty_wallets"] = []

        if frameworks_csv is not None and frameworks_csv.strip():
            _validate_optional_str(frameworks_csv, "frameworks", max_len=1024)
            fw_tokens = [
                tok.strip().upper()
                for tok in frameworks_csv.split(",")
                if tok.strip()
            ]
            for fw_tok in fw_tokens:
                if fw_tok not in _VALID_FRAMEWORKS:
                    raise ValueError(
                        f"Invalid framework code in frameworks parameter: {fw_tok!r}"
                    )
            if fw_tokens:
                prof_dict["children"] = [
                    {
                        "id": f"ephemeral-fw-{idx}",
                        "child_name": "ילד/ה",
                        "child_age_years": 6,
                        "framework_type": fw_code,
                    }
                    for idx, fw_code in enumerate(fw_tokens, start=1)
                ]

        # Sanitize inline children in memory (never expose/persist unnecessary PII)
        sanitized_children: list[dict[str, Any]] = []
        for idx, ch in enumerate(prof_dict.get("children") or [], start=1):
            c_dict = ch if isinstance(ch, dict) else ch.to_dict()
            c_copy = dict(c_dict)
            c_copy["id"] = f"{base_prof.id}:ephemeral-child:{idx}"
            c_copy["family_profile_id"] = base_prof.id
            if not c_copy.get("child_name") or not str(c_copy["child_name"]).strip():
                c_copy["child_name"] = "ילד/ה"
            sanitized_children.append(c_copy)
        prof_dict["children"] = sanitized_children
        prof_dict["id"] = base_prof.id

        return FamilyProfile.from_dict(prof_dict), has_persisted

    def dispatch(
        self,
        method: str,
        raw_path: str,
        query_params: Optional[dict[str, str]] = None,
        json_body: Optional[dict[str, Any]] = None,
        request_headers: Optional[dict[str, str]] = None,
    ) -> tuple[int, dict[str, Any], str]:
        """Dispatch an API request and return `(status_code, headers, body_text)`."""
        parsed = urllib.parse.urlsplit(raw_path)
        path = parsed.path.rstrip("/") or "/"
        q_params: dict[str, str] = {}
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            q_params[k] = v
        if query_params:
            for k, v in query_params.items():
                q_params[str(k)] = str(v)

        method_u = method.upper()
        is_private_route = (
            path.startswith("/api/v1/auth")
            or path.startswith("/api/v1/profile")
            or path == "/api/v1/moe-calendar/upcoming"
            or (
                method_u == "GET"
                and path.startswith("/api/v1/moe-calendar/")
            )
            or path.startswith("/api/v1/vacations/")
        )
        json_headers: dict[str, Any] = {"Content-Type": "application/json; charset=utf-8"}
        private_json_headers: dict[str, Any] = {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store, private",
            "Vary": "Cookie",
        }
        active_err_headers = private_json_headers if is_private_route else json_headers

        try:
            # 1. GET /api/v1/health
            if method_u == "GET" and path == "/api/v1/health":
                health = self.repository.get_health_status()
                payload = {
                    "status": "ok",
                    "service": "family_vacation_planner",
                    "version": "1.0.0",
                    "sqlite_version": sqlite3.sqlite_version,
                    "wal_mode": bool(health.get("wal_mode", True)),
                    "tables_count": int(health.get("tables_count", 11)),
                    "db_path": str(self.repository.db_path),
                }
                return 200, json_headers, json.dumps(payload, ensure_ascii=False)

            # 1b. Auth & Session Endpoints (/api/v1/auth/*)
            if method_u == "GET" and path == "/api/v1/auth/session":
                session = self.auth_service.resolve_session(request_headers)
                oauth_cfg = self.auth_service.is_oauth_configured()
                test_mode = self.auth_service.is_test_mode_allowed(request_headers)
                if session is None:
                    sess_payload = {
                        "authenticated": False,
                        "oauth_configured": oauth_cfg,
                        "test_mode": test_mode,
                        "csrf_token": None,
                        "user": None,
                    }
                else:
                    sess_payload = {
                        "authenticated": True,
                        "oauth_configured": oauth_cfg,
                        "test_mode": test_mode,
                        "csrf_token": session["csrf_token"],
                        "user": session["user"],
                    }
                return (
                    200,
                    private_json_headers,
                    json.dumps(sess_payload, ensure_ascii=False),
                )

            if method_u == "GET" and path == "/api/v1/auth/google/login":
                return self.auth_service.start_login(
                    request_headers=request_headers, query_params=q_params
                )

            if method_u == "GET" and path == "/api/v1/auth/google/callback":
                return self.auth_service.handle_callback(
                    request_headers=request_headers, query_params=q_params
                )

            if method_u == "GET" and path == "/api/v1/auth/test-oauth-authorize":
                return self.auth_service.handle_test_oauth_authorize(
                    request_headers=request_headers, query_params=q_params
                )

            if method_u == "POST" and path == "/api/v1/auth/test-login":
                return self.auth_service.handle_test_login_direct(
                    json_body=json_body, request_headers=request_headers
                )

            if method_u == "POST" and path == "/api/v1/auth/logout":
                session = self.auth_service.require_session(request_headers)
                self.auth_service.verify_csrf(session, request_headers)
                raw_tok = self.auth_service.extract_raw_session_token(request_headers)
                if raw_tok:
                    self.repository.revoke_session_by_token_hash(sha256_hex(raw_tok))
                self.planner_service.evict_ephemeral_proposals_for_user(
                    session["user_id"]
                )
                is_https = self.auth_service.is_https_request(request_headers)
                logout_headers: dict[str, Any] = {
                    **private_json_headers,
                    "Set-Cookie": self.auth_service.build_clear_session_cookies(is_https),
                }
                return (
                    200,
                    logout_headers,
                    json.dumps({"status": "logged_out", "authenticated": False}),
                )

            if method_u == "PUT" and path == "/api/v1/auth/notifications":
                session = self.auth_service.require_session(request_headers)
                self.auth_service.verify_csrf(session, request_headers)
                if not isinstance(json_body, dict):
                    raise ValueError("Request body must be a JSON object")
                body = dict(json_body)
                if "notifications_enabled" not in body or not isinstance(
                    body["notifications_enabled"], bool
                ):
                    raise ValueError("notifications_enabled boolean is required")
                if "notification_email" in body and body["notification_email"] is not None:
                    req_email = str(body["notification_email"]).strip().lower()
                    if req_email != str(session["user"]["email"]).strip().lower():
                        raise AuthError(
                            403,
                            "notification_email must match the verified Gmail account address.",
                        )
                prefs = body.get("notification_preferences")
                if prefs is not None:
                    if not isinstance(prefs, dict):
                        raise ValueError("notification_preferences must be an object")
                    for bool_p in ("award_seat_alerts", "holiday_reminders"):
                        if bool_p in prefs and not isinstance(prefs[bool_p], bool):
                            raise ValueError(f"{bool_p} must be a boolean")
                    if "preferred_locale" in prefs and prefs["preferred_locale"] not in (
                        "he",
                        "en",
                    ):
                        raise ValueError("preferred_locale must be 'he' or 'en'")
                updated_user = self.repository.update_user_notifications(
                    user_id=session["user_id"],
                    notifications_enabled=body["notifications_enabled"],
                    preferences=prefs,
                )
                return (
                    200,
                    private_json_headers,
                    json.dumps({"status": "ok", "user": updated_user}, ensure_ascii=False),
                )

            if method_u == "DELETE" and path == "/api/v1/auth/account":
                session = self.auth_service.require_session(request_headers)
                self.auth_service.verify_csrf(session, request_headers)
                self.planner_service.evict_ephemeral_proposals_for_user(
                    session["user_id"]
                )
                self.repository.delete_user_account(session["user_id"])
                is_https = self.auth_service.is_https_request(request_headers)
                del_acct_headers: dict[str, Any] = {
                    **private_json_headers,
                    "Set-Cookie": self.auth_service.build_clear_session_cookies(is_https),
                }
                return (
                    200,
                    del_acct_headers,
                    json.dumps({"status": "account_deleted", "authenticated": False}),
                )

            # 2. GET /api/v1/profile (Strictly authenticated user's own profile; ignores ?profile_id / ?user_id / ?email)
            if method_u == "GET" and path == "/api/v1/profile":
                session = self.auth_service.require_session(request_headers)
                saved_prof = self.repository.get_profile_for_user(session["user_id"])
                if saved_prof is not None:
                    prof_out = saved_prof.to_dict()
                    prof_out["is_persisted"] = True
                else:
                    starter = build_clean_guest_profile()
                    starter.id = f"user-profile-{session['user_id']}"
                    starter.profile_name = ""
                    prof_out = starter.to_dict()
                    prof_out["is_persisted"] = False
                return (
                    200,
                    private_json_headers,
                    json.dumps(prof_out, ensure_ascii=False),
                )

            # 3. PUT /api/v1/profile (Strictly authenticated + CSRF; ignores client id/profile_id/user_id/email)
            if method_u == "PUT" and path == "/api/v1/profile":
                session = self.auth_service.require_session(request_headers)
                self.auth_service.verify_csrf(session, request_headers)
                if not isinstance(json_body, dict):
                    raise ValueError("Request body must be a JSON object")
                body = dict(json_body)
                _validate_profile_payload_strict(body)
                notif_opt_in = (
                    body.pop("notifications_enabled")
                    if "notifications_enabled" in body
                    else None
                )
                for untrusted_key in ("id", "profile_id", "user_id", "email", "is_persisted"):
                    body.pop(untrusted_key, None)

                # Minimize children PII: default generic child_name, default birth_date to None
                if "children" in body and isinstance(body["children"], list):
                    clean_children: list[dict[str, Any]] = []
                    for ch_idx, ch_raw in enumerate(body["children"], start=1):
                        ch_copy = dict(ch_raw)
                        ch_copy["id"] = f"user-profile-{session['user_id']}:child:{ch_idx}"
                        ch_copy["family_profile_id"] = f"user-profile-{session['user_id']}"
                        raw_cname = str(
                            ch_copy.get("child_name") or ch_copy.get("child_name_he") or ""
                        ).strip()
                        ch_copy["child_name"] = raw_cname if raw_cname else "ילד/ה"
                        if not ch_copy.get("birth_date"):
                            ch_copy["birth_date"] = None
                        clean_children.append(ch_copy)
                    body["children"] = clean_children

                if "passenger_loyalty_wallets" in body and isinstance(
                    body["passenger_loyalty_wallets"], list
                ):
                    clean_wallets: list[dict[str, Any]] = []
                    for w_idx, w_raw in enumerate(
                        body["passenger_loyalty_wallets"], start=1
                    ):
                        w_copy = dict(w_raw)
                        w_copy["id"] = f"user-profile-{session['user_id']}:wallet:{w_idx}"
                        w_copy["family_profile_id"] = f"user-profile-{session['user_id']}"
                        clean_wallets.append(w_copy)
                    body["passenger_loyalty_wallets"] = clean_wallets

                saved = self.repository.save_profile_for_user(session["user_id"], body)
                if isinstance(notif_opt_in, bool):
                    self.repository.update_user_notifications(
                        user_id=session["user_id"],
                        notifications_enabled=notif_opt_in,
                    )
                saved_out = saved.to_dict()
                saved_out["is_persisted"] = True
                return (
                    200,
                    private_json_headers,
                    json.dumps(saved_out, ensure_ascii=False),
                )

            # 3b. DELETE /api/v1/profile (Strictly authenticated + CSRF; deletes only session user's profile)
            if method_u == "DELETE" and path == "/api/v1/profile":
                session = self.auth_service.require_session(request_headers)
                self.auth_service.verify_csrf(session, request_headers)
                self.planner_service.evict_ephemeral_proposals_for_user(
                    session["user_id"]
                )
                deleted = self.repository.delete_profile_for_user(session["user_id"])
                return (
                    200,
                    private_json_headers,
                    json.dumps({"status": "deleted", "deleted": deleted}),
                )

            # 4. POST /api/v1/moe-calendar/sync/{school_year}
            if method_u == "POST" and path.startswith("/api/v1/moe-calendar/sync/"):
                school_year_raw = path[len("/api/v1/moe-calendar/sync/") :]
                norm_year = _validate_school_year_strict(school_year_raw)
                if not isinstance(json_body, dict):
                    raise ValueError("Request body must be a JSON object")
                body = dict(json_body)
                if "force_remote_check" in body:
                    if not isinstance(body["force_remote_check"], bool):
                        raise ValueError("force_remote_check must be a boolean")
                    force_remote = body["force_remote_check"]
                else:
                    force_remote = False
                sync_status = self.auto_updater.sync_school_year(
                    norm_year, force_remote_check=force_remote
                )
                # Refresh cache on calendar_service
                self.calendar_service._windows_cache.pop(norm_year, None)
                return (
                    200,
                    json_headers,
                    json.dumps(sync_status.to_dict(), ensure_ascii=False),
                )

            # 4b. GET /api/v1/moe-calendar/upcoming
            if method_u == "GET" and path == "/api/v1/moe-calendar/upcoming":
                if "profile_id" in q_params:
                    _validate_optional_str(q_params["profile_id"], "profile_id", max_len=128)
                session = self.auth_service.resolve_session(request_headers)
                profile, _ = self._build_effective_request_profile(
                    session=session,
                    frameworks_csv=q_params.get("frameworks"),
                )
                as_of_raw = q_params.get("as_of")
                ref_d = (
                    _parse_iso_date_strict(as_of_raw, "as_of")
                    if as_of_raw
                    else datetime.now(UTC).date()
                )
                holidays = self.calendar_service.get_upcoming_holidays_for_rolling_year(
                    as_of_date=ref_d, profile=profile
                )
                try:
                    win_end = ref_d.replace(year=ref_d.year + 1)
                except ValueError:
                    win_end = ref_d + timedelta(days=365)
                upcoming_payload = {
                    "as_of_date": ref_d.isoformat(),
                    "window_end_date": win_end.isoformat(),
                    "count": len(holidays),
                    "holidays": holidays,
                }
                return (
                    200,
                    private_json_headers,
                    json.dumps(upcoming_payload, ensure_ascii=False),
                )

            # 5. GET /api/v1/moe-calendar/{school_year}
            if method_u == "GET" and path.startswith("/api/v1/moe-calendar/"):
                school_year_raw = path[len("/api/v1/moe-calendar/") :]
                norm_year = _validate_school_year_strict(school_year_raw)
                if "profile_id" in q_params:
                    _validate_optional_str(q_params["profile_id"], "profile_id", max_len=128)
                session = self.auth_service.resolve_session(request_headers)
                profile, _ = self._build_effective_request_profile(
                    session=session,
                    frameworks_csv=q_params.get("frameworks"),
                )
                windows = self.calendar_service.get_calendar_windows(norm_year)
                meta = self.calendar_service.get_calendar_metadata(norm_year)
                y1, y2 = (int(p) for p in norm_year.split("-"))
                matrix = self.calendar_service.get_daily_status_matrix(
                    profile, date(y1, 9, 1), date(y2, 8, 31)
                )
                candidates = self.maximizer_engine.generate_candidate_windows(
                    FlightSearchQuery(
                        date_selection_mode="HOLIDAY_DIRECT_INTENT",
                        school_year=norm_year,
                        min_trip_nights=4,
                        max_trip_nights=10,
                        max_bridge_days_shift=2,
                    ),
                    profile=profile,
                )[:12]
                timeline_payload = {
                    "school_year": norm_year,
                    "school_year_hebrew": str(meta.get("school_year_hebrew") or ""),
                    "calendar_sync_source": str(
                        meta.get("calendar_sync_source") or "OFFICIAL_MOE_CIRCULAR"
                    ),
                    "windows": [w.to_dict() for w in windows],
                    "strict_intersection_dates": [
                        d.isoformat() for d in matrix.strict_intersection_dates
                    ],
                    "camp_adjusted_intersection_dates": [
                        d.isoformat() for d in matrix.camp_adjusted_intersection_dates
                    ],
                    "framework_delta_union_dates": [
                        d.isoformat() for d in matrix.framework_delta_union_dates
                    ],
                    "candidate_windows": [c.to_dict() for c in candidates],
                }
                return (
                    200,
                    private_json_headers,
                    json.dumps(timeline_payload, ensure_ascii=False),
                )

            # 6. POST /api/v1/elal-bonus/sync
            if method_u == "POST" and path == "/api/v1/elal-bonus/sync":
                if not isinstance(json_body, dict):
                    raise ValueError("Request body must be a JSON object")
                body = dict(json_body)

                required_token = os.environ.get("ELAL_SYNC_API_TOKEN", "").strip()
                if required_token:
                    hdrs = {
                        str(k).lower(): str(v)
                        for k, v in (request_headers or {}).items()
                    }
                    auth_val = hdrs.get("authorization", "").strip()
                    provided_token = ""
                    if auth_val.lower().startswith("bearer "):
                        provided_token = auth_val[7:].strip()
                    elif isinstance(body.get("sync_token"), str):
                        provided_token = body["sync_token"].strip()
                    if not provided_token or not hmac.compare_digest(
                        provided_token.encode("utf-8"), required_token.encode("utf-8")
                    ):
                        return (
                            401,
                            json_headers,
                            json.dumps({"error": "Unauthorized sync token"}),
                        )
                destinations: Optional[list[str]] = None
                if "destinations" in body:
                    destinations = _validate_destination_codes_strict(
                        body["destinations"], "destinations", allow_csv_str=True
                    )
                if "destination_iatas" in body:
                    dest_alias = _validate_destination_codes_strict(
                        body["destination_iatas"],
                        "destination_iatas",
                        allow_csv_str=True,
                    )
                    if destinations is None:
                        destinations = dest_alias
                if destinations is None:
                    destinations = ["FCO"]

                start_d = (
                    _parse_iso_date_strict(body["start_date"], "start_date")
                    if "start_date" in body
                    else date(2027, 4, 10)
                )
                end_d = (
                    _parse_iso_date_strict(body["end_date"], "end_date")
                    if "end_date" in body
                    else date(2027, 4, 20)
                )
                if end_d < start_d:
                    raise ValueError(
                        f"end_date ({end_d}) must be >= start_date ({start_d})"
                    )

                origin = "TLV"
                if "origin" in body:
                    origin = _validate_airport_iata_strict(body["origin"], "origin")
                if "origin_iata" in body:
                    origin_alias = _validate_airport_iata_strict(
                        body["origin_iata"], "origin_iata"
                    )
                    if "origin" not in body:
                        origin = origin_alias

                if "force_refresh" in body:
                    if not isinstance(body["force_refresh"], bool):
                        raise ValueError("force_refresh must be a boolean")
                    force_refresh = body["force_refresh"]
                else:
                    force_refresh = False

                for m_key in ("months_ahead", "months"):
                    if m_key in body:
                        body[m_key] = _parse_strict_int(
                            body[m_key], m_key, min_val=1, max_val=24
                        )

                expanded = self.elal_adapter.expand_metro_iatas(destinations)

                reconciled_cnt = 0
                has_reconcile_slices = (
                    "reconcile_slices" in body and body["reconcile_slices"] is not None
                )
                if has_reconcile_slices:
                    validated_slices = _validate_reconcile_slices_strict(
                        body["reconcile_slices"],
                        self.elal_adapter.expand_metro_iatas,
                    )
                    reconciled_cnt = self.repository.reconcile_live_bonus_slices(
                        validated_slices
                    )

                # If caller provided an external `rbd_payload` (e.g. from browser/partner sync), validate & import it directly
                if "rbd_payload" in body and body["rbd_payload"] is not None:
                    _validate_rbd_payload_strict(body["rbd_payload"])
                    imported_rows = self.elal_adapter.parse_and_import_external_rbd_payload(
                        raw_payload=body["rbd_payload"],
                        default_origin=origin,
                        default_destination=expanded[0] if expanded else "FCO",
                    )
                    resp_payload = {
                        "status": "ok",
                        "origin": origin,
                        "requested_destination": destinations[0]
                        if len(destinations) == 1
                        else ",".join(destinations),
                        "requested_destinations": destinations,
                        "expanded_destinations": expanded,
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "records_synced": len(imported_rows),
                        "records_reconciled": reconciled_cnt,
                        "live_fetch_status": "IMPORTED_LIVE_PAYLOAD" if imported_rows else "NO_FLIGHTS_FETCHED",
                        "availability": [r.to_dict() for r in imported_rows],
                    }
                    return 200, json_headers, json.dumps(resp_payload, ensure_ascii=False)

                if has_reconcile_slices:
                    resp_payload = {
                        "status": "ok",
                        "origin": origin,
                        "requested_destination": destinations[0]
                        if len(destinations) == 1
                        else ",".join(destinations),
                        "requested_destinations": destinations,
                        "expanded_destinations": expanded,
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "records_synced": 0,
                        "records_reconciled": reconciled_cnt,
                        "live_fetch_status": "RECONCILED_EMPTY_SLICE",
                        "availability": [],
                    }
                    return 200, json_headers, json.dumps(resp_payload, ensure_ascii=False)

                synced_res = self.elal_adapter.sync_award_availability(
                    destinations=destinations,
                    start_date=start_d,
                    end_date=end_d,
                    origin=origin,
                    force_refresh=force_refresh,
                )
                if isinstance(synced_res, dict):
                    rec_cnt = int(synced_res.get("records_synced", 0))
                    resp_payload = {
                        **synced_res,
                        "status": "ok",
                        "origin": origin,
                        "requested_destination": destinations[0]
                        if len(destinations) == 1
                        else ",".join(destinations),
                        "requested_destinations": destinations,
                        "expanded_destinations": expanded,
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "live_fetch_status": "OK" if rec_cnt > 0 else "NO_FLIGHTS_FETCHED_FROM_SERVER",
                    }
                else:
                    resp_payload = {
                        "status": "ok",
                        "origin": origin,
                        "requested_destination": destinations[0]
                        if len(destinations) == 1
                        else ",".join(destinations),
                        "requested_destinations": destinations,
                        "expanded_destinations": expanded,
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "records_synced": len(synced_res),
                        "live_fetch_status": "OK" if len(synced_res) > 0 else "NO_FLIGHTS_FETCHED_FROM_SERVER",
                        "availability": [
                            r.to_dict() if hasattr(r, "to_dict") else r
                            for r in synced_res
                        ],
                    }
                return 200, json_headers, json.dumps(resp_payload, ensure_ascii=False)

            # 7. GET /api/v1/elal-bonus/availability
            if method_u == "GET" and path == "/api/v1/elal-bonus/availability":
                dest_raw = q_params.get("destination") or q_params.get("destinations")
                if not dest_raw:
                    raise ValueError("Missing required query parameter 'destination'")
                dest_list = _validate_destination_codes_strict(
                    dest_raw, "destination", allow_csv_str=True
                )
                start_d = _parse_iso_date_strict(
                    q_params.get("start_date", ""), "start_date"
                )
                end_d = _parse_iso_date_strict(
                    q_params.get("end_date", ""), "end_date"
                )
                if end_d < start_d:
                    raise ValueError(
                        f"end_date ({end_d}) must be >= start_date ({start_d})"
                    )
                origin = (
                    _validate_airport_iata_strict(q_params["origin"], "origin")
                    if q_params.get("origin")
                    else "TLV"
                )
                expanded = self.elal_adapter.expand_metro_iatas(dest_list)
                rows = self.elal_adapter.get_award_availability(
                    destinations=dest_list,
                    start_date=start_d,
                    end_date=end_d,
                    origin=origin,
                )
                resp_payload = {
                    "origin": origin,
                    "requested_destination": dest_raw.strip(),
                    "requested_destinations": dest_list,
                    "expanded_destinations": expanded,
                    "start_date": start_d.isoformat(),
                    "end_date": end_d.isoformat(),
                    "count": len(rows),
                    "availability": [r.to_dict() for r in rows],
                }
                return 200, json_headers, json.dumps(resp_payload, ensure_ascii=False)

            # 8. POST /api/v1/vacations/search
            if method_u == "POST" and path == "/api/v1/vacations/search":
                if not isinstance(json_body, dict):
                    raise ValueError("Request body must be a JSON object")
                body = dict(json_body)
                _validate_search_payload_strict(body)
                if body.get("overlap_policy") in (
                    "CAMP_AWARE_ALL_CHILDREN_OFF",
                    "WEIGHTED_MIN_ABSENCE",
                ):
                    body["overlap_policy"] = "CAMP_ADJUSTED_INTERSECTION"

                resolved_ty: Optional[int] = None
                raw_ty = body.get("direct_target_year")
                if isinstance(raw_ty, int) and not isinstance(raw_ty, bool) and raw_ty > 2035:
                    resolved_ty = raw_ty
                    body["direct_target_year"] = None
                    if str(body.get("date_selection_mode") or "") == "HOLIDAY_DIRECT_INTENT":
                        body["school_year"] = resolve_holiday_direct_intent_school_year(
                            str(body.get("direct_holiday_code") or "PESACH"),
                            resolved_ty,
                        )

                # Ignore client-supplied profile_id / family_profile_id to enforce strict per-user isolation
                body.pop("profile_id", None)
                body.pop("family_profile_id", None)
                query = FlightSearchQuery.from_dict(body)
                if resolved_ty is not None:
                    setattr(query, "_resolved_target_year", resolved_ty)

                session = self.auth_service.resolve_session(request_headers)
                profile, has_persisted_profile = self._build_effective_request_profile(
                    session=session,
                    body=body,
                )
                expanded_dests = self.elal_adapter.expand_metro_iatas(
                    query.destination_iatas
                )
                proposals = self.planner_service.search_vacations(
                    query_data=query,
                    profile=profile,
                    persist_results=has_persisted_profile,
                    owner_user_id=session["user_id"] if session else None,
                )
                live_mode = (
                    self.repository.is_live_fetch_mode()
                    or self.planner_service._has_live_only_inventory()
                )
                weather_fallback_he = getattr(
                    self.planner_service, "last_weather_fallback_message_he", None
                )
                status_msg_he = weather_fallback_he
                status_msg_en = None
                if weather_fallback_he:
                    status_msg_en = (
                        "Strict weather threshold relaxed so you still see the highest-rated weather options."
                    )
                if not proposals and live_mode:
                    status_msg_he = (
                        "אין משיכה של טיסות מהשרת (לא נמצאו טיסות אמיתיות מסונכרנות במסד הנתונים עבור יעד ומועד זה. "
                        "טיסות פיקטיביות מבוטלות במצב פרודקשן כדי למנוע הטעיה)."
                    )
                    status_msg_en = (
                        "No flights fetched from the server (no live flights synced in the database for this route/date. "
                        "Fictitious flights are disabled in production mode)."
                    )
                query_dict = query.to_dict()
                if resolved_ty is not None:
                    query_dict["direct_target_year"] = resolved_ty
                resp_payload = {
                    "query": query_dict,
                    "expanded_destinations": expanded_dests,
                    "count": len(proposals),
                    "live_fetch_mode": live_mode,
                    "status_message_he": status_msg_he,
                    "status_message_en": status_msg_en,
                    "weather_fallback_message_he": weather_fallback_he,
                    "proposals": [p.to_dict() for p in proposals],
                }
                return (
                    200,
                    private_json_headers,
                    json.dumps(resp_payload, ensure_ascii=False),
                )

            # 8b. GET /api/v1/destinations/weather
            if method_u == "GET" and path == "/api/v1/destinations/weather":
                month_param = q_params.get("month")
                start_param = q_params.get("start_date")
                end_param = q_params.get("end_date")
                if start_param or end_param:
                    start_d = _parse_iso_date_strict(start_param or "", "start_date")
                    end_d = _parse_iso_date_strict(end_param or "", "end_date")
                    if end_d < start_d:
                        raise ValueError(
                            f"end_date ({end_d}) must be >= start_date ({start_d})"
                        )
                elif month_param:
                    m_int = _parse_strict_int(
                        month_param, "month", min_val=1, max_val=12
                    )
                    start_d = date(2027, m_int, 10)
                    end_d = date(2027, m_int, 17)
                else:
                    start_d = date(2027, 7, 10)
                    end_d = date(2027, 7, 17)

                vtype_raw = (
                    q_params.get("vacation_type")
                    or q_params.get("vacation_types")
                    or "ANY"
                )
                vtypes = [
                    v.strip().upper()
                    for v in vtype_raw.split(",")
                    if v.strip()
                ]
                if not vtypes:
                    raise ValueError("Invalid empty vacation_type parameter")
                for vt in vtypes:
                    if vt not in _VALID_VACATION_TYPES:
                        raise ValueError(
                            f"Invalid vacation_type: {vt!r}. Allowed: {sorted(_VALID_VACATION_TYPES)}"
                        )

                dest_filter_raw = q_params.get("destination") or q_params.get("destinations")
                allowed_iatas: Optional[set[str]] = None
                if dest_filter_raw:
                    raw_codes = _validate_destination_codes_strict(
                        dest_filter_raw, "destination", allow_csv_str=True
                    )
                    allowed_iatas = set(self.elal_adapter.expand_metro_iatas(raw_codes))

                items: list[dict[str, Any]] = []
                for iata_key, dest_entry in DESTINATION_CATALOG.items():
                    iata = str(dest_entry.get("iata") or iata_key).upper()
                    if allowed_iatas is not None and iata not in allowed_iatas:
                        continue
                    metrics = self.planner_service.weather_engine.evaluate_destination(
                        destination_iata=iata,
                        departure_date=start_d,
                        return_date=end_d,
                        preferred_vacation_types=vtypes,
                    )
                    items.append(
                        {
                            "iata": iata,
                            "metro": dest_entry.get("metro"),
                            "city": dest_entry.get("city"),
                            "city_he": dest_entry.get("city_he"),
                            "country": dest_entry.get("country"),
                            "country_he": dest_entry.get("country_he"),
                            "climate_profile": dest_entry.get("climate_profile"),
                            "weather_suitability_score": metrics.overall_weather_suitability_score,
                            "best_matching_vacation_type": metrics.best_matching_vacation_type,
                            "weather_metrics": metrics.to_dict(),
                        }
                    )

                items.sort(
                    key=lambda x: (
                        -float(x["weather_suitability_score"]),
                        str(x["iata"]),
                    )
                )
                catalog_types = [
                    {
                        "code": code,
                        "label_he": VACATION_TYPE_LABELS_HE.get(code, code),
                        "label_en": VACATION_TYPE_LABELS_EN.get(code, code),
                        "icon": VACATION_TYPE_ICONS.get(code, "🌍"),
                    }
                    for code in VACATION_TYPES
                ]
                resp_payload = {
                    "start_date": start_d.isoformat(),
                    "end_date": end_d.isoformat(),
                    "vacation_types": vtypes,
                    "count": len(items),
                    "vacation_types_catalog": catalog_types,
                    "destinations": items,
                }
                return 200, json_headers, json.dumps(resp_payload, ensure_ascii=False)

            return (
                404,
                active_err_headers,
                json.dumps({"error": f"Unknown API endpoint: {method_u} {path}"}),
            )

        except AuthError as auth_exc:
            return (
                auth_exc.status_code,
                private_json_headers,
                json.dumps({"error": auth_exc.safe_message}, ensure_ascii=False),
            )
        except (
            ValueError,
            TypeError,
            OverflowError,
            KeyError,
            sqlite3.Error,
        ) as exc:
            return (
                422,
                active_err_headers,
                json.dumps({"error": redact_pii(str(exc))}, ensure_ascii=False),
            )
