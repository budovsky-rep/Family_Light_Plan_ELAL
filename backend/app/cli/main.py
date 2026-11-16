"""CLI Companion (`F30` — `plan-vacation` / `backend.app.cli.main`).

Supports 5 subcommands:
- `profile`: Display family profile, children frameworks, and multi-club loyalty wallets.
- `calendar`: Inspect or sync (`--sync`) Ministry of Education (`משרד החינוך`) school-year calendars.
- `bonus-availability`: Query or sync (`--sync`) El Al `rbddataclients` bonus seat availability with metro IATA expansion (`ROM` -> `FCO`, `NYC` -> `JFK,EWR`).
- `search`: Run vacation maximization & flight synthesis across all 3 Date Selection Modes (`specific-dates`, `moe-maximize`, `holiday-direct`) and export `.json` / `.ics`.
- `serve`: Launch the local web & API server (`0.0.0.0:8000`).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional

from backend.app.main import VacationPlannerTestClient, run_server


_MODE_MAP: dict[str, str] = {
    "specific-dates": "SPECIFIC_DATES",
    "specific_dates": "SPECIFIC_DATES",
    "SPECIFIC_DATES": "SPECIFIC_DATES",
    "moe-maximize": "MOE_VACATION_MAXIMIZATION",
    "moe_maximize": "MOE_VACATION_MAXIMIZATION",
    "moe-vacation-maximization": "MOE_VACATION_MAXIMIZATION",
    "MOE_VACATION_MAXIMIZATION": "MOE_VACATION_MAXIMIZATION",
    "holiday-direct": "HOLIDAY_DIRECT_INTENT",
    "holiday_direct": "HOLIDAY_DIRECT_INTENT",
    "holiday-direct-intent": "HOLIDAY_DIRECT_INTENT",
    "HOLIDAY_DIRECT_INTENT": "HOLIDAY_DIRECT_INTENT",
}

_AIRLINE_MAP: dict[str, str] = {
    "elal-only": "EL_AL_ONLY",
    "elal_only": "EL_AL_ONLY",
    "EL_AL_ONLY": "EL_AL_ONLY",
    "all-airlines": "ALL_AIRLINES",
    "all_airlines": "ALL_AIRLINES",
    "ALL_AIRLINES": "ALL_AIRLINES",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plan-vacation",
        description=(
            "Family Vacation Planner CLI Companion — Israeli MoE Holiday Maximizer "
            "& El Al Bonus Ticket Synthesizer (profile, calendar, bonus-availability, search, serve)"
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database (defaults to VACATION_PLANNER_DB_PATH or data/vacation_planner.db)",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. profile
    p_prof = subparsers.add_parser(
        "profile",
        help="Show family profile, children frameworks, and loyalty wallets",
    )
    p_prof.add_argument(
        "--profile-id",
        default="default-family-profile",
        help="Family profile ID",
    )
    p_prof.add_argument(
        "--json", action="store_true", help="Output raw JSON"
    )

    # 2. calendar
    p_cal = subparsers.add_parser(
        "calendar",
        help="Inspect or sync Ministry of Education (MoE) school-year vacation windows",
    )
    p_cal.add_argument(
        "--school-year",
        default="2026-2027",
        help="Target school year in YYYY-YYYY format (e.g. 2026-2027, 2027-2028)",
    )
    p_cal.add_argument(
        "--sync",
        action="store_true",
        help="Sync or project the school year via MoECalendarAutoUpdaterService first",
    )
    p_cal.add_argument(
        "--json", action="store_true", help="Output raw JSON"
    )

    # 3. bonus-availability
    p_bon = subparsers.add_parser(
        "bonus-availability",
        help="Query or sync El Al rbddataclients bonus seat availability",
    )
    p_bon.add_argument(
        "--destination",
        required=True,
        help="Destination IATA or metro code(s), comma-separated (e.g. ROM, NYC, FCO, ATH, ANYWHERE)",
    )
    p_bon.add_argument(
        "--start-date",
        required=True,
        help="Start date in YYYY-MM-DD format",
    )
    p_bon.add_argument(
        "--end-date",
        required=True,
        help="End date in YYYY-MM-DD format",
    )
    p_bon.add_argument(
        "--origin",
        default="TLV",
        help="Origin airport IATA code (default: TLV)",
    )
    p_bon.add_argument(
        "--sync",
        action="store_true",
        help="Force sync with El Al rbddataclients adapter before querying",
    )
    p_bon.add_argument(
        "--json", action="store_true", help="Output raw JSON"
    )

    # 4. search
    p_srch = subparsers.add_parser(
        "search",
        help="Search & rank family vacation proposals across Modes 1/2/3 and export .json / .ics",
    )
    p_srch.add_argument(
        "--mode",
        default="holiday-direct",
        help="Date selection mode: specific-dates | moe-maximize | holiday-direct",
    )
    p_srch.add_argument(
        "--airline",
        default="elal-only",
        help="Airline selection mode: elal-only | all-airlines",
    )
    p_srch.add_argument(
        "--destination",
        default="FCO",
        help="Destination IATA/metro code(s), comma-separated (e.g. FCO, ROM, ATH, ANYWHERE)",
    )
    p_srch.add_argument(
        "--holiday",
        default="PESACH",
        help="Holiday code for holiday-direct mode (e.g. PESACH, SUKKOT, HANUKKAH, SUMMER_AUGUST)",
    )
    p_srch.add_argument(
        "--year",
        type=int,
        default=2027,
        help="Target calendar year for holiday-direct mode (e.g. 2026, 2027, 2028)",
    )
    p_srch.add_argument(
        "--school-year",
        default="2026-2027",
        help="School year for moe-maximize mode (e.g. 2026-2027)",
    )
    p_srch.add_argument(
        "--departure-date",
        default=None,
        help="Specific departure date YYYY-MM-DD for specific-dates mode",
    )
    p_srch.add_argument(
        "--return-date",
        default=None,
        help="Specific return date YYYY-MM-DD for specific-dates mode",
    )
    p_srch.add_argument(
        "--flex-days",
        type=int,
        default=2,
        help="Flexibility +/- days for specific-dates mode (0..7)",
    )
    p_srch.add_argument(
        "--max-bridge-days",
        type=int,
        default=2,
        help="Maximum bridge days shift (0..5)",
    )
    p_srch.add_argument(
        "--min-nights",
        type=int,
        default=4,
        help="Minimum trip nights (default: 4)",
    )
    p_srch.add_argument(
        "--max-nights",
        type=int,
        default=10,
        help="Maximum trip nights (default: 10)",
    )
    p_srch.add_argument(
        "--export-json",
        default=None,
        help="Optional file path to export proposals JSON",
    )
    p_srch.add_argument(
        "--export-ics",
        default=None,
        help="Optional file path to export the top proposal RFC 5545 .ics calendar",
    )
    p_srch.add_argument(
        "--json", action="store_true", help="Output raw JSON"
    )

    # 5. serve
    p_srv = subparsers.add_parser(
        "serve",
        help="Start the local Family Vacation Planner web & REST API server",
    )
    p_srv.add_argument(
        "--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)"
    )
    p_srv.add_argument(
        "--port", type=int, default=8000, help="Bind port (default: 8000)"
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    db_path = args.db_path or os.environ.get("VACATION_PLANNER_DB_PATH")
    client = VacationPlannerTestClient(db_path=db_path)

    if args.subcommand == "profile":
        resp = client.get(
            "/api/v1/profile", params={"profile_id": args.profile_id}
        )
        if resp.status_code != 200:
            print(resp.text, file=sys.stderr)
            return 1
        data = resp.json()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(
                f"Profile: {data['profile_name']} (id={data['id']}, adults={data['adults_count']}, "
                f"children={len(data['children'])}, wallets={len(data['passenger_loyalty_wallets'])})"
            )
        return 0

    if args.subcommand == "calendar":
        if args.sync:
            s_resp = client.post(
                f"/api/v1/moe-calendar/sync/{args.school_year}",
                json={"force_remote_check": False},
            )
            if s_resp.status_code != 200:
                print(s_resp.text, file=sys.stderr)
                return 1
        resp = client.get(f"/api/v1/moe-calendar/{args.school_year}")
        if resp.status_code != 200:
            print(resp.text, file=sys.stderr)
            return 1
        data = resp.json()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(
                f"School Year {data['school_year']} ({data['calendar_sync_source']}): "
                f"{len(data['windows'])} framework windows, "
                f"{len(data['candidate_windows'])} top candidate vacation windows."
            )
        return 0

    if args.subcommand == "bonus-availability":
        dest_list = [
            d.strip() for d in str(args.destination).split(",") if d.strip()
        ]
        if args.sync:
            s_resp = client.post(
                "/api/v1/elal-bonus/sync",
                json={
                    "destinations": dest_list,
                    "start_date": args.start_date,
                    "end_date": args.end_date,
                    "origin": args.origin,
                    "force_refresh": False,
                },
            )
            if s_resp.status_code != 200:
                print(s_resp.text, file=sys.stderr)
                return 1
        resp = client.get(
            "/api/v1/elal-bonus/availability",
            params={
                "destination": ",".join(dest_list),
                "start_date": args.start_date,
                "end_date": args.end_date,
                "origin": args.origin,
            },
        )
        if resp.status_code != 200:
            print(resp.text, file=sys.stderr)
            return 1
        data = resp.json()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(
                f"El Al Bonus Availability ({data['origin']} -> {data['expanded_destinations']}): "
                f"{data['count']} flights found."
            )
        return 0

    if args.subcommand == "search":
        if args.mode not in _MODE_MAP:
            print(f"Error: invalid --mode {args.mode!r}", file=sys.stderr)
            return 2
        if args.airline not in _AIRLINE_MAP:
            print(f"Error: invalid --airline {args.airline!r}", file=sys.stderr)
            return 2
        if args.flex_days < 0 or args.flex_days > 7:
            print(
                f"Error: --flex-days must be between 0 and 7, got {args.flex_days}",
                file=sys.stderr,
            )
            return 2
        if args.max_bridge_days < 0 or args.max_bridge_days > 5:
            print(
                f"Error: --max-bridge-days must be between 0 and 5, got {args.max_bridge_days}",
                file=sys.stderr,
            )
            return 2

        dest_list = [
            d.strip() for d in str(args.destination).split(",") if d.strip()
        ]
        search_payload: dict[str, Any] = {
            "date_selection_mode": _MODE_MAP[args.mode],
            "airline_selection_mode": _AIRLINE_MAP[args.airline],
            "destination_iatas": dest_list,
            "school_year": args.school_year,
            "direct_holiday_code": str(args.holiday).upper(),
            "direct_target_year": int(args.year),
            "specific_departure_date": args.departure_date or "2027-04-11",
            "specific_return_date": args.return_date or "2027-04-18",
            "flex_days_plus_minus": int(args.flex_days),
            "max_bridge_days_shift": int(args.max_bridge_days),
            "min_trip_nights": int(args.min_nights),
            "max_trip_nights": int(args.max_nights),
        }
        resp = client.post("/api/v1/vacations/search", json=search_payload)
        if resp.status_code != 200:
            print(resp.text, file=sys.stderr)
            return 1
        data = resp.json()

        if args.export_json:
            out_json_path = Path(args.export_json)
            out_json_path.parent.mkdir(parents=True, exist_ok=True)
            out_json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        if args.export_ics and data.get("proposals"):
            top_id = data["proposals"][0]["id"]
            ics_resp = client.get(f"/api/v1/vacations/{top_id}/export.ics")
            if ics_resp.status_code == 200:
                out_ics_path = Path(args.export_ics)
                out_ics_path.parent.mkdir(parents=True, exist_ok=True)
                out_ics_path.write_text(ics_resp.text, encoding="utf-8")

        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            proposals = data.get("proposals", [])
            print(f"Found {len(proposals)} ranked family vacation proposals:")
            for idx, p in enumerate(proposals[:5], start=1):
                it = p.get("itinerary") or {}
                rank_val = p.get("rank") or p.get("rank_order") or idx
                tier_val = p.get("recommendation_tier") or "RECOMMENDED"
                city_val = (
                    it.get("destination_city_he")
                    or it.get("destination_city")
                    or it.get("destination_iata")
                    or ""
                )
                print(
                    f"  #{rank_val} [{tier_val}] "
                    f"{city_val} ({it.get('destination_iata', '')}) "
                    f"{it.get('departure_date', '')} -> {it.get('return_date', '')} | "
                    f"Strategy={it.get('fulfillment_strategy', '')} | "
                    f"CTOS={float(p.get('combined_trip_optimization_score', 0.0)):.2f}"
                )
        return 0

    if args.subcommand == "serve":
        run_server(host=args.host, port=args.port, db_path=db_path)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
