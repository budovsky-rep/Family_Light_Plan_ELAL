"""REST API v1 Endpoints & Dispatcher (`F29`) for family_vacation_planner.

Implements all 8 core REST API endpoints + `.ics` calendar export using Python
3.13 standard library + project domain services, with zero external runtime
dependencies so it operates both in-process (`VacationPlannerTestClient`) and
over live HTTP (`ThreadingHTTPServer`).

Endpoints:
1. `GET  /api/v1/health`
2. `GET  /api/v1/profile`
3. `PUT  /api/v1/profile`
4. `GET  /api/v1/moe-calendar/{school_year}`
5. `POST /api/v1/moe-calendar/sync/{school_year}`
6. `POST /api/v1/elal-bonus/sync`
7. `GET  /api/v1/elal-bonus/availability`
8. `POST /api/v1/vacations/search`
9. `POST /api/v1/vacations/compare`
10. `GET /api/v1/vacations/{proposal_id}/export.ics`
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Optional
import urllib.parse

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
)
from backend.app.schemas.domain import (
    AirlineSelectionMode,
    DIRECT_HOLIDAY_CODES,
    DateSelectionMode,
    FamilyProfile,
    FlightSearchQuery,
    HolidayExtensionMode,
    LoyaltyProgramCode,
    MoEFrameworkType,
    OVERLAP_POLICIES,
)
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.vacation_optimizer.maximizer_engine import VacationMaximizerEngine


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


def _parse_iso_date_strict(val: Any, field_name: str) -> date:
    if isinstance(val, date):
        return val
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO date string YYYY-MM-DD")
    try:
        return date.fromisoformat(val.strip()[:10])
    except Exception as exc:
        raise ValueError(f"Invalid ISO date for {field_name}: {val!r}") from exc


def _validate_school_year_strict(school_year: str) -> str:
    if not isinstance(school_year, str) or not school_year.strip():
        raise ValueError("school_year must be a string in 'YYYY-YYYY' or 'YYYY' format")
    return normalize_school_year(school_year.strip())


def _validate_profile_payload_strict(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Profile payload must be a JSON object")

    adults = payload.get("adults_count", 2)
    if not isinstance(adults, int) or isinstance(adults, bool) or not (1 <= adults <= 6):
        raise ValueError(f"adults_count must be an integer in 1..6, got {adults!r}")

    workweek = payload.get("workweek_type", "SUN_THU")
    if workweek not in ("SUN_THU", "SUN_FRI"):
        raise ValueError(f"Invalid workweek_type: {workweek!r}")

    for weight_key in ("erev_chag_pto_weight", "chol_hamoed_pto_weight"):
        if weight_key in payload and payload[weight_key] is not None:
            w = float(payload[weight_key])
            if w not in (0.0, 0.5, 1.0):
                raise ValueError(f"{weight_key} must be one of (0.0, 0.5, 1.0)")

    for non_neg_key in (
        "annual_pto_budget",
        "max_pto_per_trip",
        "matmid_points_balance",
        "flycard_companion_vouchers",
    ):
        if non_neg_key in payload and payload[non_neg_key] is not None:
            if float(payload[non_neg_key]) < 0:
                raise ValueError(f"{non_neg_key} must be >= 0")

    if "point_valuation_usd" in payload and payload["point_valuation_usd"] is not None:
        if float(payload["point_valuation_usd"]) <= 0:
            raise ValueError("point_valuation_usd must be > 0")

    children = payload.get("children", [])
    if not isinstance(children, list):
        raise ValueError("children must be a list")
    for idx, child in enumerate(children):
        if not isinstance(child, dict):
            raise ValueError(f"children[{idx}] must be an object")
        age = child.get("child_age_years")
        if age is None or isinstance(age, bool) or not isinstance(age, (int, float)):
            raise ValueError(f"children[{idx}].child_age_years is required")
        age_int = int(age)
        if age_int < 0 or age_int > 18:
            raise ValueError(
                f"children[{idx}].child_age_years must be between 0 and 18, got {age!r}"
            )
        fw = child.get("framework_type")
        if fw is not None and fw != "":
            if str(fw) not in _VALID_FRAMEWORKS:
                raise ValueError(
                    f"children[{idx}].framework_type {fw!r} is not a valid MoEFrameworkType"
                )
        sw = child.get("school_week_days", 5)
        if sw is not None and int(sw) not in (5, 6):
            raise ValueError(f"children[{idx}].school_week_days must be 5 or 6")
        ext = child.get("holiday_extension_mode", "NITZANIM_FULL_WITH_JULY")
        if ext is not None and str(ext) not in _VALID_EXTENSION_MODES:
            raise ValueError(
                f"children[{idx}].holiday_extension_mode {ext!r} is invalid"
            )

    wallets = payload.get("passenger_loyalty_wallets", [])
    if not isinstance(wallets, list):
        raise ValueError("passenger_loyalty_wallets must be a list")
    for idx, wallet in enumerate(wallets):
        if not isinstance(wallet, dict):
            raise ValueError(f"passenger_loyalty_wallets[{idx}] must be an object")
        prog = wallet.get("program_code")
        if not prog or str(prog) not in _VALID_PROGRAMS:
            raise ValueError(
                f"passenger_loyalty_wallets[{idx}].program_code {prog!r} is invalid"
            )
        pts = wallet.get("available_points", 0)
        if isinstance(pts, bool) or not isinstance(pts, (int, float)) or int(pts) < 0:
            raise ValueError(
                f"passenger_loyalty_wallets[{idx}].available_points must be >= 0"
            )
        vouchers = wallet.get("companion_vouchers_count", 0)
        if (
            isinstance(vouchers, bool)
            or not isinstance(vouchers, (int, float))
            or int(vouchers) < 0
        ):
            raise ValueError(
                f"passenger_loyalty_wallets[{idx}].companion_vouchers_count must be >= 0"
            )
        val_cents = wallet.get("point_valuation_cents", 1.4)
        if float(val_cents) <= 0:
            raise ValueError(
                f"passenger_loyalty_wallets[{idx}].point_valuation_cents must be > 0"
            )


def _validate_search_payload_strict(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Search payload must be a JSON object")

    d_mode = payload.get("date_selection_mode", "MOE_VACATION_MAXIMIZATION")
    if str(d_mode) not in _VALID_DATE_MODES:
        raise ValueError(f"Invalid date_selection_mode: {d_mode!r}")

    a_mode = payload.get("airline_selection_mode", "EL_AL_ONLY")
    if str(a_mode) not in _VALID_AIRLINE_MODES:
        raise ValueError(f"Invalid airline_selection_mode: {a_mode!r}")

    if "overlap_policy" in payload and payload["overlap_policy"] is not None:
        if str(payload["overlap_policy"]) not in _VALID_OVERLAP_POLICIES:
            raise ValueError(f"Invalid overlap_policy: {payload['overlap_policy']!r}")

    min_nights = int(payload.get("min_trip_nights", 4))
    max_nights = int(payload.get("max_trip_nights", 10))
    if min_nights < 1 or max_nights < 1 or min_nights > max_nights or max_nights > 45:
        raise ValueError(
            f"Invalid trip nights range: min_trip_nights={min_nights}, max_trip_nights={max_nights}"
        )

    flex = int(payload.get("flex_days_plus_minus", 2))
    if flex < 0 or flex > 7:
        raise ValueError(f"flex_days_plus_minus must be in 0..7, got {flex}")

    bridge = int(payload.get("max_bridge_days_shift", 2))
    if bridge < 0 or bridge > 5:
        raise ValueError(f"max_bridge_days_shift must be in 0..5, got {bridge}")

    dep_raw = payload.get("specific_departure_date")
    ret_raw = payload.get("specific_return_date")
    if dep_raw and ret_raw:
        dep_d = _parse_iso_date_strict(dep_raw, "specific_departure_date")
        ret_d = _parse_iso_date_strict(ret_raw, "specific_return_date")
        if ret_d < dep_d:
            raise ValueError(
                f"specific_return_date ({ret_d}) must be >= specific_departure_date ({dep_d})"
            )

    if str(d_mode) == "HOLIDAY_DIRECT_INTENT":
        h_code = payload.get("direct_holiday_code")
        if h_code is not None and str(h_code) not in _VALID_HOLIDAY_CODES:
            raise ValueError(f"Invalid direct_holiday_code: {h_code!r}")
        t_year = payload.get("direct_target_year")
        if t_year is not None and (int(t_year) < 2024 or int(t_year) > 2040):
            raise ValueError(f"Invalid direct_target_year: {t_year!r}")


class VacationPlannerAPIRouter:
    """Dependency-injected REST API v1 dispatcher."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.repository = SQLiteRepository(db_path=db_path, auto_seed=True)
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

    def dispatch(
        self,
        method: str,
        raw_path: str,
        query_params: Optional[dict[str, str]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> tuple[int, dict[str, str], str]:
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
        json_headers = {"Content-Type": "application/json; charset=utf-8"}

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
                    "tables_count": int(health.get("tables_count", 8)),
                    "db_path": str(self.repository.db_path),
                }
                return 200, json_headers, json.dumps(payload, ensure_ascii=False)

            # 2. GET /api/v1/profile
            if method_u == "GET" and path == "/api/v1/profile":
                profile_id = q_params.get("profile_id", "default-family-profile")
                profile = self.repository.get_profile(profile_id)
                if profile is None:
                    return (
                        404,
                        json_headers,
                        json.dumps({"error": f"Profile {profile_id!r} not found"}),
                    )
                return (
                    200,
                    json_headers,
                    json.dumps(profile.to_dict(), ensure_ascii=False),
                )

            # 3. PUT /api/v1/profile
            if method_u == "PUT" and path == "/api/v1/profile":
                body = json_body if isinstance(json_body, dict) else {}
                _validate_profile_payload_strict(body)
                profile = FamilyProfile.from_dict(body)
                saved = self.repository.save_profile(profile)
                return (
                    200,
                    json_headers,
                    json.dumps(saved.to_dict(), ensure_ascii=False),
                )

            # 4. POST /api/v1/moe-calendar/sync/{school_year}
            if method_u == "POST" and path.startswith("/api/v1/moe-calendar/sync/"):
                school_year_raw = path[len("/api/v1/moe-calendar/sync/") :]
                norm_year = _validate_school_year_strict(school_year_raw)
                body = json_body if isinstance(json_body, dict) else {}
                force_remote = bool(body.get("force_remote_check", False))
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

            # 5. GET /api/v1/moe-calendar/{school_year}
            if method_u == "GET" and path.startswith("/api/v1/moe-calendar/"):
                school_year_raw = path[len("/api/v1/moe-calendar/") :]
                norm_year = _validate_school_year_strict(school_year_raw)
                profile_id = q_params.get("profile_id", "default-family-profile")
                profile = self.repository.get_profile(profile_id) or FamilyProfile()
                windows = self.calendar_service.get_calendar_windows(norm_year)
                meta = self.calendar_service.get_calendar_metadata(norm_year)
                y1, y2 = (int(p) for p in norm_year.split("-"))
                matrix = self.calendar_service.get_daily_status_matrix(
                    profile, date(y1, 9, 1), date(y2, 8, 31)
                )
                candidates = self.maximizer_engine.generate_candidate_windows(
                    FlightSearchQuery(
                        date_selection_mode="MOE_VACATION_MAXIMIZATION",
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
                    json_headers,
                    json.dumps(timeline_payload, ensure_ascii=False),
                )

            # 6. POST /api/v1/elal-bonus/sync
            if method_u == "POST" and path == "/api/v1/elal-bonus/sync":
                body = json_body if isinstance(json_body, dict) else {}
                destinations = body.get("destinations") or body.get("destination_iatas") or ["FCO"]
                if isinstance(destinations, str):
                    destinations = [
                        d.strip() for d in destinations.split(",") if d.strip()
                    ]
                if not isinstance(destinations, list) or not destinations:
                    raise ValueError("destinations must be a non-empty list of IATA codes")
                start_d = _parse_iso_date_strict(
                    body.get("start_date", "2027-04-10"), "start_date"
                )
                end_d = _parse_iso_date_strict(
                    body.get("end_date", "2027-04-20"), "end_date"
                )
                if end_d < start_d:
                    raise ValueError(
                        f"end_date ({end_d}) must be >= start_date ({start_d})"
                    )
                origin = str(body.get("origin", "TLV")).upper()
                force_refresh = bool(body.get("force_refresh", False))
                expanded = self.elal_adapter.expand_metro_iatas(destinations)

                # If caller provided an external `rbd_payload` (e.g. from browser/partner sync), import it directly
                if "rbd_payload" in body and body["rbd_payload"]:
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
                        "live_fetch_status": "IMPORTED_LIVE_PAYLOAD" if imported_rows else "NO_FLIGHTS_FETCHED",
                        "availability": [r.to_dict() for r in imported_rows],
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
                dest_list = [d.strip() for d in dest_raw.split(",") if d.strip()]
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
                origin = str(q_params.get("origin", "TLV")).upper()
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
                body = dict(json_body) if isinstance(json_body, dict) else {}
                _validate_search_payload_strict(body)
                if body.get("overlap_policy") == "CAMP_AWARE_ALL_CHILDREN_OFF":
                    body["overlap_policy"] = "CAMP_ADJUSTED_INTERSECTION"
                elif body.get("overlap_policy") == "WEIGHTED_MIN_ABSENCE":
                    body["overlap_policy"] = "MAXIMIZE_EFFICIENCY_SCORE"
                query = FlightSearchQuery.from_dict(body)
                profile_id = str(body.get("profile_id", "default-family-profile"))
                profile = self.repository.get_profile(profile_id)
                expanded_dests = self.elal_adapter.expand_metro_iatas(
                    query.destination_iatas
                )
                proposals = self.planner_service.search_vacations(
                    query_data=query, profile=profile
                )
                live_mode = self.repository.is_live_fetch_mode()
                status_msg_he = None
                status_msg_en = None
                if not proposals and live_mode:
                    status_msg_he = (
                        "אין משיכה של טיסות מהשרת (לא נמצאו טיסות אמיתיות מסונכרנות במסד הנתונים עבור יעד ומועד זה. "
                        "טיסות פיקטיביות מבוטלות במצב פרודקשן כדי למנוע הטעיה)."
                    )
                    status_msg_en = (
                        "No flights fetched from the server (no live flights synced in the database for this route/date. "
                        "Fictitious flights are disabled in production mode)."
                    )
                resp_payload = {
                    "query": query.to_dict(),
                    "expanded_destinations": expanded_dests,
                    "count": len(proposals),
                    "live_fetch_mode": live_mode,
                    "status_message_he": status_msg_he,
                    "status_message_en": status_msg_en,
                    "proposals": [p.to_dict() for p in proposals],
                }
                return 200, json_headers, json.dumps(resp_payload, ensure_ascii=False)

            # 9. POST /api/v1/vacations/compare
            if method_u == "POST" and path == "/api/v1/vacations/compare":
                body = json_body if isinstance(json_body, dict) else {}
                proposal_ids = body.get("proposal_ids", [])
                if not isinstance(proposal_ids, list) or not proposal_ids:
                    return (
                        422,
                        json_headers,
                        json.dumps(
                            {"error": "proposal_ids must be a non-empty list"},
                            ensure_ascii=False,
                        ),
                    )
                matrix = self.planner_service.compare_proposals(
                    [str(pid) for pid in proposal_ids]
                )
                matrix_dict = (
                    matrix.to_dict() if hasattr(matrix, "to_dict") else dict(matrix)
                )
                return (
                    200,
                    json_headers,
                    json.dumps(matrix_dict, ensure_ascii=False),
                )

            # 10. GET /api/v1/vacations/{proposal_id}/export.ics
            if (
                method_u == "GET"
                and path.startswith("/api/v1/vacations/")
                and path.endswith("/export.ics")
            ):
                middle = path[len("/api/v1/vacations/") : -len("/export.ics")].strip("/")
                if not middle:
                    return (
                        400,
                        json_headers,
                        json.dumps({"error": "Missing proposal_id"}),
                    )
                try:
                    ics_text = self.planner_service.export_proposal_ics(middle)
                except (KeyError, ValueError) as exc:
                    return (
                        404,
                        json_headers,
                        json.dumps({"error": str(exc)}, ensure_ascii=False),
                    )
                ics_headers = {
                    "Content-Type": "text/calendar; charset=utf-8",
                    "Content-Disposition": f'attachment; filename="vacation-{middle}.ics"',
                }
                return 200, ics_headers, ics_text

            return (
                404,
                json_headers,
                json.dumps({"error": f"Unknown API endpoint: {method_u} {path}"}),
            )

        except (ValueError, KeyError, sqlite3.IntegrityError) as exc:
            return (
                422,
                json_headers,
                json.dumps({"error": str(exc)}, ensure_ascii=False),
            )
