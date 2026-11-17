#!/usr/bin/env python3
"""Admin Sync Script (`scripts/sync_elal_to_server.py`).

Runs on your Mac (which has a residential IP not blocked by El Al's cloud WAF),
fetches live Classic Award seat availability across all 25 El Al destinations
and 3 cabin classes (`E` Economy, `P` Premium, `I` Business) for both OUTBOUND
and INBOUND directions over the next 350 days, and pushes the real flight
inventory directly to the production server (`http://34.165.250.15:8080`).

Usage on your Mac:
    python3 scripts/sync_elal_to_server.py --server http://34.165.250.15:8080
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import subprocess
import sys
import time
import urllib.request

DEFAULT_SERVER_URL = "http://34.165.250.15:8080"
ELAL_RBD_PAGE_URL = "https://www.elal.com/rbddataclients/"
ELAL_RBD_API_URL = (
    "https://www.elal.com/generalproxy/proxy/dpel/449/GeneralRestServices-GetRbdAvailability"
)

ALL_ELAL_DESTINATIONS: list[str] = [
    "ATH", "LCA", "RHO", "PFO", "TBS",
    "FCO", "MXP", "VIE", "BUD", "PRG", "BER", "MUC", "ZRH",
    "LHR", "LTN", "CDG", "MAD", "BCN", "AMS",
    "BKK", "HKT", "NRT",
    "JFK", "EWR", "MIA", "FLL",
]

CABIN_RBDS: tuple[str, ...] = ("E", "P", "I")


def push_records_to_server(
    server_url: str,
    dest_iata: str,
    start_d: date,
    end_d: date,
    accumulated_payloads: list[dict],
) -> int:
    """POST collected `AccumulatedOutput` payloads for `dest_iata` to `/api/v1/elal-bonus/sync`."""
    if not accumulated_payloads:
        return 0
    endpoint = f"{server_url.rstrip('/')}/api/v1/elal-bonus/sync"
    body = {
        "origin": "TLV",
        "destinations": [dest_iata],
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "force_refresh": True,
        "rbd_payload": accumulated_payloads,
    }
    data_bytes = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        res_json = json.loads(resp.read().decode("utf-8"))
        return int(res_json.get("records_synced", 0))


def run_sync(
    server_url: str,
    destinations: list[str],
    days_ahead: int = 345,
    headless: bool = False,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not found on Mac — installing playwright and chromium automatically...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright

    start_d = date.today()
    end_d = start_d + timedelta(days=days_ahead)
    start_iso = f"{start_d.isoformat()}T21:00:00.000Z"
    end_iso = f"{end_d.isoformat()}T21:00:00.000Z"

    print(
        f"Starting El Al RBD live sync for {len(destinations)} destinations "
        f"({start_d.isoformat()} -> {end_d.isoformat()}) -> {server_url}"
    )

    total_synced = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        print(f"Opening {ELAL_RBD_PAGE_URL} to initialize session...")
        page.goto(ELAL_RBD_PAGE_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3000)

        for idx, dest in enumerate(destinations, start=1):
            dest_payloads: list[dict] = []
            for direction_seg in (
                [{"org": "TLV", "dest": dest}],
                [{"org": dest, "dest": "TLV"}],
            ):
                for rbd in CABIN_RBDS:
                    js_fetch = """async ({apiUrl, rbd, startIso, endIso, seg}) => {
                        const r = await fetch(apiUrl, {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                                "Accept": "application/json, text/plain, */*"
                            },
                            body: JSON.stringify({
                                input: {
                                    rbd: rbd,
                                    startDate: startIso,
                                    endDate: endIso,
                                    seg: seg
                                }
                            })
                        });
                        if (!r.ok) return null;
                        const txt = await r.text();
                        try { return JSON.parse(txt); } catch (e) { return null; }
                    }"""
                    data = page.evaluate(
                        js_fetch,
                        {
                            "apiUrl": ELAL_RBD_API_URL,
                            "rbd": rbd,
                            "startIso": start_iso,
                            "endIso": end_iso,
                            "seg": direction_seg,
                        },
                    )
                    if isinstance(data, dict) and "AccumulatedOutput" in data:
                        dest_payloads.append(data)
                    time.sleep(0.35)

            synced_cnt = push_records_to_server(
                server_url=server_url,
                dest_iata=dest,
                start_d=start_d,
                end_d=end_d,
                accumulated_payloads=dest_payloads,
            )
            total_synced += synced_cnt
            print(
                f"[{idx}/{len(destinations)}] {dest}: synced {synced_cnt} real award flights to server"
            )

        browser.close()

    print(f"\nDone! Total real El Al award flight records synced to {server_url}: {total_synced}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync live El Al rbddataclients availability from your Mac to the production server"
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER_URL,
        help=f"Production server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--destinations",
        default=",".join(ALL_ELAL_DESTINATIONS),
        help="Comma-separated destination IATA codes (default: all 26 El Al destinations)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=345,
        help="Number of days ahead to scan (default: 345)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    args = parser.parse_args()
    dests = [d.strip().upper() for d in args.destinations.split(",") if d.strip()]
    run_sync(
        server_url=args.server,
        destinations=dests,
        days_ahead=args.days,
        headless=args.headless,
    )


if __name__ == "__main__":
    main()
