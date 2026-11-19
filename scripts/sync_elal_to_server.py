#!/usr/bin/env python3
"""Automated El Al Classic Award Bonus Sync Script (`scripts/sync_elal_to_server.py`).

Fetches real live El Al Matmid bonus availability (`Economy` RBD `"E"` and `Premium` RBD `"A"`)
from `https://www.elal.com/rbddataclients/` (`GeneralRestServices-GetRbdAvailability`) across all
16×14-day Israeli Holiday & Ministry of Education school vacation windows for all 25 supported
`DESTINATION_CATALOG` destinations (`50` directional segments per request), and syncs them directly
into both the local SQLite database (`data/vacation_planner.db`) and the GCP Production server
(`https://family-trip-planner.duckdns.org/api/v1/elal-bonus/sync`).

Supports two modes:
1. Live Headless Chrome CDP mode (default): Launches system Google Chrome (`--headless=new`)
   with a pure-Python stdlib CDP WebSocket client (zero external dependencies), passes El Al's
   Reblaze WAAP challenge on `https://www.elal.com/rbddataclients/`, and executes `$.ajax`
   50-segment batch queries across all 16 holiday windows × 2 cabins (`E`, `A`).
2. `--from-file <path>`: Pure Python upload of a saved JSON snapshot to the remote server
   and/or local SQLite database without launching a browser.
"""

from __future__ import annotations

import argparse
import base64
from datetime import date
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Optional
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SERVER_URL = "https://family-trip-planner.duckdns.org"
DEFAULT_LOCAL_DB_PATH = str(REPO_ROOT / "data" / "vacation_planner.db")
ELAL_RBD_PAGE_URL = "https://www.elal.com/rbddataclients/"
ELAL_RBD_API_URL = (
    "https://www.elal.com/generalproxy/proxy/dpel/449/GeneralRestServices-GetRbdAvailability"
)

try:
    from backend.app.storage_cache.seed_data import DESTINATION_CATALOG as _CATALOG
    ALL_ELAL_DESTINATIONS: list[str] = list(_CATALOG.keys())
except Exception:
    # Standalone fallback when run outside the repo checkout (all 45 supported destinations)
    ALL_ELAL_DESTINATIONS = [
        "ATH", "LCA", "RHO", "PFO", "TBS",
        "FCO", "MXP", "VIE", "BUD", "PRG", "BER", "MUC",
        "LHR", "LTN", "CDG", "MAD", "BCN", "AMS",
        "BKK", "HKT", "NRT",
        "JFK", "EWR", "MIA", "FLL",
        "HER", "SKG", "CFU", "EFL", "JTR", "BUS", "TIV", "BEG",
        "OTP", "SOF", "WAW", "KRK",
        "VCE", "GVA", "FRA", "LIS", "NCE",
        "DXB", "LAX", "BOS",
    ]

# El Al GetRbdAvailability supports at most 50 directional segments (25 round-trip destinations) per request
MAX_DESTINATIONS_PER_AJAX_BATCH = 25

# El Al calculator RBD codes: "E" = Economy, "A" = Premium
CABIN_RBDS: tuple[str, ...] = ("E", "A")

# 16×14-day Israeli Holiday & MoE School Vacation windows (endDate - startDate == 14 days)
HOLIDAY_14D_WINDOWS: list[dict[str, str]] = [
    {
        "label": "Hanukkah 2026 A",
        "start_iso": "2026-12-01T21:00:00.000Z",
        "end_iso": "2026-12-15T21:00:00.000Z",
    },
    {
        "label": "Hanukkah 2026 B",
        "start_iso": "2026-12-06T21:00:00.000Z",
        "end_iso": "2026-12-20T21:00:00.000Z",
    },
    {
        "label": "Purim 2027",
        "start_iso": "2027-03-16T21:00:00.000Z",
        "end_iso": "2027-03-30T21:00:00.000Z",
    },
    {
        "label": "Pesach 2027 A (Pre-Holiday & Nitzanim Week)",
        "start_iso": "2027-04-07T21:00:00.000Z",
        "end_iso": "2027-04-21T21:00:00.000Z",
    },
    {
        "label": "Pesach 2027 B (Chol HaMoed, Chag Sheni & Return)",
        "start_iso": "2027-04-19T21:00:00.000Z",
        "end_iso": "2027-05-03T21:00:00.000Z",
    },
    {
        "label": "Yom HaAtzmaut 2027",
        "start_iso": "2027-05-05T21:00:00.000Z",
        "end_iso": "2027-05-19T21:00:00.000Z",
    },
    {
        "label": "Shavuot 2027",
        "start_iso": "2027-06-04T21:00:00.000Z",
        "end_iso": "2027-06-18T21:00:00.000Z",
    },
    {
        "label": "Summer Late June (Grades 7-12 Arbitrage) 2027",
        "start_iso": "2027-06-18T21:00:00.000Z",
        "end_iso": "2027-07-02T21:00:00.000Z",
    },
    {
        "label": "Summer July 2027 A",
        "start_iso": "2027-07-02T21:00:00.000Z",
        "end_iso": "2027-07-16T21:00:00.000Z",
    },
    {
        "label": "Summer July 2027 B",
        "start_iso": "2027-07-16T21:00:00.000Z",
        "end_iso": "2027-07-30T21:00:00.000Z",
    },
    {
        "label": "Summer August 2027 A",
        "start_iso": "2027-07-30T21:00:00.000Z",
        "end_iso": "2027-08-13T21:00:00.000Z",
    },
    {
        "label": "Summer August 2027 B",
        "start_iso": "2027-08-13T21:00:00.000Z",
        "end_iso": "2027-08-27T21:00:00.000Z",
    },
    {
        "label": "Summer End of August 2027",
        "start_iso": "2027-08-20T21:00:00.000Z",
        "end_iso": "2027-09-03T21:00:00.000Z",
    },
    {
        "label": "Rosh Hashanah & Yom Kippur 2027",
        "start_iso": "2027-09-26T21:00:00.000Z",
        "end_iso": "2027-10-10T21:00:00.000Z",
    },
    {
        "label": "Sukkot 2027 A",
        "start_iso": "2027-10-08T21:00:00.000Z",
        "end_iso": "2027-10-22T21:00:00.000Z",
    },
    {
        "label": "Sukkot 2027 B",
        "start_iso": "2027-10-15T21:00:00.000Z",
        "end_iso": "2027-10-29T21:00:00.000Z",
    },
]


class _StdlibCdpWebSocket:
    """Minimal RFC 6455 WebSocket client using only Python's standard library."""

    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        self._sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(handshake.encode("ascii"))
        resp_buf = b""
        while b"\r\n\r\n" not in resp_buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise RuntimeError("WebSocket handshake closed unexpectedly")
            resp_buf += chunk
        header_part, self._leftover = resp_buf.split(b"\r\n\r\n", 1)
        if b"101" not in header_part.splitlines()[0]:
            raise RuntimeError(f"WebSocket handshake failed: {header_part.decode('utf-8', 'replace')}")
        self._next_id = 0

    def _read_exact(self, n: int) -> bytes:
        while len(self._leftover) < n:
            chunk = self._sock.recv(max(65536, n - len(self._leftover)))
            if not chunk:
                raise RuntimeError("WebSocket connection closed while reading frame")
            self._leftover += chunk
        out = self._leftover[:n]
        self._leftover = self._leftover[n:]
        return out

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask_key = os.urandom(4)
        header = bytearray([0x81])  # FIN + text frame
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        fragments: list[bytes] = []
        while True:
            b1, b2 = self._read_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask_key = self._read_exact(4) if masked else b""
            data = self._read_exact(length) if length > 0 else b""
            if masked:
                data = bytes(b ^ mask_key[i & 3] for i, b in enumerate(data))
            if opcode == 0x8:  # Close
                raise RuntimeError("WebSocket closed by peer")
            if opcode == 0x9:  # Ping -> send Pong
                pong_hdr = bytearray([0x8A, 0x80 | len(data)])
                m_key = os.urandom(4)
                pong_hdr.extend(m_key)
                pong_data = bytes(b ^ m_key[i & 3] for i, b in enumerate(data))
                self._sock.sendall(bytes(pong_hdr) + pong_data)
                continue
            if opcode in (0x0, 0x1, 0x2):
                fragments.append(data)
                if fin:
                    return b"".join(fragments).decode("utf-8", errors="replace")

    def call(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._next_id += 1
        req_id = self._next_id
        self.send_text(json.dumps({"id": req_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.recv_text())
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error calling {method}: {msg['error']}")
                return msg.get("result") or {}

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


def _find_chrome_binary() -> str:
    candidates = [
        os.environ.get("CHROME_BIN", ""),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise RuntimeError("Google Chrome binary not found on this machine.")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _normalize_time_field(raw_time: Any, dep_date_iso: str) -> str:
    if not raw_time:
        return ""
    s = str(raw_time).strip()
    if "T" in s:
        return s
    date_part = dep_date_iso.split("T", 1)[0] if dep_date_iso else "2027-04-14"
    if len(s) >= 5 and s[2] == ":" and s[:2].isdigit() and s[3:5].isdigit():
        hhmm = s[:5]
        return f"{date_part}T{hhmm}:00"
    return s


def normalize_accumulated_payloads(
    raw_payloads: list[dict[str, Any]],
    allowed_destinations: Optional[set[str]] = None,
) -> tuple[dict[str, Any], list[str], str, str, int]:
    """Consolidate and normalize raw `AccumulatedOutput` responses into a single payload dict.

    - Wraps any single-dict `Record` into `[rec]`.
    - Filters `SegmentRoute` strictly to the 25 `DESTINATION_CATALOG` IATA codes.
    - Preserves `SegmentRoute`, `SegmentDepDate`, `SegmentDepTime`, `SegmentArrTime`,
      `FlightCarrier`, `FlightNumber`, `RBD`, and `NewAvailability`.
    """
    valid_dests = allowed_destinations or set(ALL_ELAL_DESTINATIONS)
    normalized_records: list[dict[str, Any]] = []
    seen_destinations: set[str] = set()
    all_dates: list[str] = []

    for payload in raw_payloads:
        if not isinstance(payload, dict):
            continue
        acc = payload.get("AccumulatedOutput")
        if not isinstance(acc, dict):
            continue
        raw_rs = acc.get("resultSet")
        if isinstance(raw_rs, dict):
            rs_list = [raw_rs]
        elif isinstance(raw_rs, list):
            rs_list = raw_rs
        else:
            continue

        for rs in rs_list:
            if not isinstance(rs, dict):
                continue
            raw_rec = rs.get("Record")
            if isinstance(raw_rec, dict):
                rec_list = [raw_rec]
            elif isinstance(raw_rec, list):
                rec_list = raw_rec
            else:
                continue

            for rec in rec_list:
                if not isinstance(rec, dict):
                    continue
                route = str(rec.get("SegmentRoute") or "").strip().upper()
                if len(route) != 6:
                    continue
                orig_c, dest_c = route[:3], route[3:]
                route_dest = orig_c if dest_c == "TLV" else dest_c
                if route_dest not in valid_dests:
                    continue

                avail_str = str(rec.get("NewAvailability") or "0").strip()
                avail_num_str = avail_str[:-1].strip() if avail_str.endswith("+") else avail_str
                if not avail_num_str.isdigit() or int(avail_num_str) <= 0:
                    continue

                dep_date_raw = str(rec.get("SegmentDepDate") or "").strip()
                if not dep_date_raw:
                    continue
                date_only = dep_date_raw.split("T", 1)[0]
                all_dates.append(date_only)
                seen_destinations.add(route_dest)

                norm_rec = dict(rec)
                norm_rec["SegmentRoute"] = route
                norm_rec["SegmentDepDate"] = dep_date_raw
                if "SegmentDepTime" in norm_rec and norm_rec["SegmentDepTime"]:
                    norm_rec["SegmentDepTime"] = _normalize_time_field(
                        norm_rec["SegmentDepTime"], dep_date_raw
                    )
                if "SegmentArrTime" in norm_rec and norm_rec["SegmentArrTime"]:
                    norm_rec["SegmentArrTime"] = _normalize_time_field(
                        norm_rec["SegmentArrTime"], dep_date_raw
                    )
                normalized_records.append(norm_rec)

    consolidated = {
        "AccumulatedOutput": {
            "resultSet": [{"Record": normalized_records}] if normalized_records else []
        }
    }
    sorted_dests = sorted(seen_destinations) if seen_destinations else list(ALL_ELAL_DESTINATIONS)
    min_date = min(all_dates) if all_dates else date.today().isoformat()
    max_date = max(all_dates) if all_dates else "2027-10-30"
    return consolidated, sorted_dests, min_date, max_date, len(normalized_records)


def push_records_to_server(
    server_url: str,
    dest_iata: str | list[str],
    start_d: date | str,
    end_d: date | str,
    accumulated_payloads: list[dict[str, Any]] | dict[str, Any],
    batch_size: int = 800,
    timeout_seconds: float = 180.0,
) -> int:
    """POST collected `AccumulatedOutput` payloads to `{server_url}/api/v1/elal-bonus/sync` in safe chunks."""
    if not accumulated_payloads:
        return 0
    endpoint = f"{server_url.rstrip('/')}/api/v1/elal-bonus/sync"
    destinations_list = [dest_iata] if isinstance(dest_iata, str) else list(dest_iata)
    start_str = start_d.isoformat() if isinstance(start_d, date) else str(start_d)
    end_str = end_d.isoformat() if isinstance(end_d, date) else str(end_d)

    def _post_chunk(chunk_payload: Any) -> int:
        body = {
            "origin": "TLV",
            "destinations": destinations_list,
            "start_date": start_str,
            "end_date": end_str,
            "force_refresh": True,
            "rbd_payload": chunk_payload,
        }
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return int(res_json.get("records_synced", 0))

    # Split consolidated `AccumulatedOutput` records into batches so slow VMs never hit HTTP timeouts
    if (
        isinstance(accumulated_payloads, dict)
        and isinstance(accumulated_payloads.get("AccumulatedOutput"), dict)
    ):
        rs_list = accumulated_payloads["AccumulatedOutput"].get("resultSet") or []
        all_recs: list[dict[str, Any]] = []
        for rs in rs_list if isinstance(rs_list, list) else [rs_list]:
            if isinstance(rs, dict):
                recs = rs.get("Record") or []
                if isinstance(recs, dict):
                    all_recs.append(recs)
                elif isinstance(recs, list):
                    all_recs.extend(r for r in recs if isinstance(r, dict))

        if len(all_recs) > batch_size:
            all_recs.sort(
                key=lambda r: (
                    str(r.get("SegmentRoute") or ""),
                    str(r.get("SegmentDepDate") or ""),
                    str(r.get("FlightNumber") or ""),
                )
            )
            total_synced = 0
            total_batches = (len(all_recs) + batch_size - 1) // batch_size
            for b_idx in range(total_batches):
                chunk = all_recs[b_idx * batch_size : (b_idx + 1) * batch_size]
                chunk_payload = {"AccumulatedOutput": {"resultSet": [{"Record": chunk}]}}
                synced = _post_chunk(chunk_payload)
                total_synced += synced
                print(
                    f"  -> Remote sync batch {b_idx + 1}/{total_batches} "
                    f"({len(chunk)} raw -> {synced} rows synced)"
                )
            return total_synced

    if isinstance(accumulated_payloads, list) and len(accumulated_payloads) > batch_size:
        total_synced = 0
        total_batches = (len(accumulated_payloads) + batch_size - 1) // batch_size
        for b_idx in range(total_batches):
            chunk = accumulated_payloads[b_idx * batch_size : (b_idx + 1) * batch_size]
            synced = _post_chunk(chunk)
            total_synced += synced
            print(
                f"  -> Remote sync batch {b_idx + 1}/{total_batches} "
                f"({len(chunk)} items -> {synced} rows synced)"
            )
        return total_synced

    return _post_chunk(accumulated_payloads)


def sync_payload_to_local_db(
    local_db_path: str,
    destinations_list: list[str],
    start_str: str,
    end_str: str,
    rbd_payload: Any,
) -> int:
    """Purge synthetic non-`#live` rows and sync `rbd_payload` into `local_db_path` via `/api/v1/elal-bonus/sync`."""
    os.environ["ELAL_LIVE_FETCH_ENABLED"] = "1"
    from backend.app.main import VacationPlannerTestClient

    client = VacationPlannerTestClient(db_path=local_db_path)
    # Explicitly ensure non-#live rows and dependent proposals/itineraries are purged
    with client.router.repository.connection() as conn:
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
        conn.execute("DELETE FROM elal_bonus_availability WHERE source_url NOT LIKE '%#live%'")

    resp = client.post(
        "/api/v1/elal-bonus/sync",
        json={
            "origin": "TLV",
            "destinations": destinations_list,
            "start_date": start_str,
            "end_date": end_str,
            "force_refresh": True,
            "rbd_payload": rbd_payload,
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Local DB sync failed (HTTP {resp.status_code}): {resp.text}")
    res_json = resp.json()
    return int(res_json.get("records_synced", 0))


def fetch_live_holiday_payloads_via_cdp(
    destinations: list[str],
    windows: Optional[list[dict[str, str]]] = None,
) -> list[dict[str, Any]]:
    """Launch headless Google Chrome via CDP, pass Reblaze WAAP on `elal.com/rbddataclients/`,
    and fetch all 16×14-day holiday windows × `CABIN_RBDS = ('E', 'A')` using 50-segment `$.ajax`.
    """
    chrome_bin = _find_chrome_binary()
    port = _find_free_port()
    active_windows = windows or HOLIDAY_14D_WINDOWS
    valid_dests = [d for d in destinations if d in ALL_ELAL_DESTINATIONS] or list(ALL_ELAL_DESTINATIONS)

    dest_batches: list[list[str]] = [
        valid_dests[i : i + MAX_DESTINATIONS_PER_AJAX_BATCH]
        for i in range(0, len(valid_dests), MAX_DESTINATIONS_PER_AJAX_BATCH)
    ]
    total_segments = len(valid_dests) * 2
    temp_profile_dir = tempfile.mkdtemp(prefix="fvp_elal_sync_")

    cmd = [
        chrome_bin,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--user-data-dir={temp_profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        (
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        ELAL_RBD_PAGE_URL,
    ]

    print(
        f"Launching headless Chrome ({chrome_bin}) on CDP port {port} for "
        f"{len(valid_dests)} destinations ({total_segments} directional segments across "
        f"{len(dest_batches)} batch(es) of <={MAX_DESTINATIONS_PER_AJAX_BATCH * 2} segments)..."
    )
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp: Optional[_StdlibCdpWebSocket] = None
    collected_payloads: list[dict[str, Any]] = []

    try:
        # Wait for page initialization ("Search for Classic award - EL AL") BEFORE attaching CDP
        ws_url: Optional[str] = None
        last_seen_page: str = ""
        deadline = time.time() + 45.0
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3.0) as r:
                    targets = json.loads(r.read().decode("utf-8"))
                    for t in targets:
                        if t.get("type") == "page":
                            t_url = str(t.get("url") or "")
                            t_title = str(t.get("title") or "")
                            last_seen_page = f"title={t_title!r} url={t_url!r}"
                            if (
                                "elal.com/rbddataclients" in t_url
                                and "Search for Classic award" in t_title
                                and t.get("webSocketDebuggerUrl")
                            ):
                                ws_url = str(t["webSocketDebuggerUrl"])
                                break
                if ws_url:
                    break
            except Exception:
                pass

        if not ws_url:
            raise RuntimeError(
                f"Timed out waiting for {ELAL_RBD_PAGE_URL} initialization "
                f"(last seen page: {last_seen_page or 'CDP not reachable'}). "
                "If you just ran a large scan, El Al may apply a ~10-15 minute rate-limit cooldown "
                "before allowing another automated session (or use the Chrome extension in a regular browser)."
            )

        cdp = _StdlibCdpWebSocket(ws_url, timeout=40.0)

        ready = False
        ready_deadline = time.time() + 15.0
        while time.time() < ready_deadline:
            res = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": (
                        "Boolean(window.$ && typeof window.$.ajax === 'function' "
                        "&& document.querySelectorAll('select').length >= 2)"
                    ),
                    "returnByValue": True,
                },
            )
            if res.get("result", {}).get("value") is True:
                ready = True
                break
            time.sleep(0.5)

        if not ready:
            raise RuntimeError("jQuery $.ajax not initialized on https://www.elal.com/rbddataclients/.")

        print("El Al rbddataclients SPA & Reblaze session ready. Checking active calculator airports & executing <=50-segment $.ajax batch queries...")

        # Inspect El Al's live <select> options so any seasonal airport currently inactive in El Al's calculator is filtered cleanly
        opt_res = cdp.call(
            "Runtime.evaluate",
            {
                "expression": """
                (() => {
                    const codes = new Set();
                    document.querySelectorAll('select option').forEach((opt) => {
                        const raw = `${opt.value || ''} ${opt.textContent || ''}`.toUpperCase();
                        const matches = raw.match(/\\b[A-Z]{3}\\b/g) || [];
                        matches.forEach((m) => codes.add(m));
                    });
                    return Array.from(codes);
                })()
                """,
                "returnByValue": True,
            },
        )
        page_codes = set(opt_res.get("result", {}).get("value") or [])
        active_dests = list(valid_dests)
        if len(page_codes) >= 15:
            filtered = [d for d in active_dests if d in page_codes]
            skipped = [d for d in active_dests if d not in page_codes]
            if filtered:
                active_dests = filtered
                if skipped:
                    print(
                        f"  Note: {len(skipped)} seasonal destination(s) not listed in El Al's calculator dropdown today "
                        f"(skipping {','.join(skipped)}; syncing {len(active_dests)} active destinations)."
                    )

        def _wait_ajax_ready(timeout_sec: float = 15.0) -> bool:
            dl = time.time() + timeout_sec
            while time.time() < dl:
                r = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": (
                            "Boolean(window.$ && typeof window.$.ajax === 'function' "
                            "&& document.querySelectorAll('select').length >= 2)"
                        ),
                        "returnByValue": True,
                    },
                )
                if r.get("result", {}).get("value") is True:
                    return True
                time.sleep(0.5)
            return False

        def _refresh_reblaze_session() -> bool:
            print("  -> Refreshing El Al Reblaze session after transient throttle...")
            time.sleep(3.0)
            cdp.call("Page.reload", {"ignoreCache": False})
            time.sleep(3.0)
            return _wait_ajax_ready(20.0)

        def _query_batch(
            batch_dests: list[str],
            start_iso: str,
            end_iso: str,
            rbd: str,
        ) -> Optional[dict[str, Any]]:
            if not batch_dests:
                return None
            segs: list[dict[str, str]] = []
            for d in batch_dests:
                segs.append({"org": "TLV", "dest": d})
                segs.append({"org": d, "dest": "TLV"})
            seg_json = json.dumps(segs)
            js_expr = f"""
            new Promise((resolve) => {{
                window.$.ajax({{
                    url: {json.dumps(ELAL_RBD_API_URL)},
                    type: "POST",
                    contentType: "application/json",
                    data: JSON.stringify({{
                        input: {{
                            startDate: {json.dumps(start_iso)},
                            endDate: {json.dumps(end_iso)},
                            rbd: {json.dumps(rbd)},
                            seg: {seg_json}
                        }}
                    }}),
                    timeout: 25000,
                    success: function(res) {{
                        resolve({{ ok: true, data: res }});
                    }},
                    error: function(xhr, status, err) {{
                        resolve({{
                            ok: false,
                            status: xhr ? xhr.status : 0,
                            error: String(err || status || "ajax_error")
                        }});
                    }}
                }});
            }})
            """
            for attempt in range(2):
                eval_res = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": js_expr,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                )
                val = eval_res.get("result", {}).get("value") or {}
                if isinstance(val, dict) and val.get("ok") and isinstance(val.get("data"), dict):
                    data_obj = val["data"]
                    if "AccumulatedOutput" in data_obj:
                        return data_obj
                if attempt == 0:
                    _refresh_reblaze_session()
            return None

        current_batches = [
            active_dests[i : i + MAX_DESTINATIONS_PER_AJAX_BATCH]
            for i in range(0, len(active_dests), MAX_DESTINATIONS_PER_AJAX_BATCH)
        ]

        for w_idx, win in enumerate(active_windows, start=1):
            label = win["label"]
            start_iso = win["start_iso"]
            end_iso = win["end_iso"]
            for rbd in CABIN_RBDS:
                cabin_label = "Economy" if rbd == "E" else "Premium"
                window_cabin_cnt = 0
                for b_dests in current_batches:
                    data_obj = _query_batch(b_dests, start_iso, end_iso, rbd)
                    if data_obj is not None:
                        collected_payloads.append(data_obj)
                        _, _, _, _, rec_cnt = normalize_accumulated_payloads([data_obj])
                        window_cabin_cnt += rec_cnt
                    time.sleep(0.55)
                print(
                    f"  [{w_idx:02d}/{len(active_windows):02d}] {label} | "
                    f"{cabin_label} ({rbd}): {window_cabin_cnt} available flight records"
                )

        return collected_payloads
    finally:
        if cdp is not None:
            cdp.close()
        try:
            proc.terminate()
            proc.wait(timeout=5.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(temp_profile_dir, ignore_errors=True)


def push_existing_local_db_to_server(
    server_url: str,
    local_db_path: str = DEFAULT_LOCAL_DB_PATH,
) -> int:
    """Push already-synced `#live` rows from `local_db_path` directly to `server_url` without re-scraping El Al."""
    import sqlite3

    db_file = Path(local_db_path).expanduser().resolve()
    if not db_file.exists():
        raise RuntimeError(f"Local SQLite DB not found: {db_file}")

    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT origin_iata, destination_iata, direction, flight_date, flight_number,
                   departure_time_local, arrival_time_local,
                   economy_award_seats, economy_seats_is_two_plus,
                   premium_award_seats, premium_seats_is_two_plus,
                   business_award_seats, business_seats_is_two_plus
            FROM elal_bonus_availability
            WHERE source_url LIKE '%#live%'
            ORDER BY flight_date, flight_number
            """
        ).fetchall()
    finally:
        conn.close()

    records: list[dict[str, Any]] = []
    dests_seen: set[str] = set()
    dates_seen: list[str] = []

    for r in rows:
        orig = str(r["origin_iata"] or "").strip().upper()
        dest = str(r["destination_iata"] or "").strip().upper()
        route = f"{orig}{dest}"
        fdate = str(r["flight_date"] or "").strip()
        fnum = str(r["flight_number"] or "").strip().upper()
        carrier = "LY"
        num_digits = fnum[2:] if fnum.startswith("LY") else fnum
        dep_t = _normalize_time_field(r["departure_time_local"], fdate) if r["departure_time_local"] else ""
        arr_t = _normalize_time_field(r["arrival_time_local"], fdate) if r["arrival_time_local"] else ""

        route_dest = orig if dest == "TLV" else dest
        dests_seen.add(route_dest)
        dates_seen.append(fdate)

        for rbd_code, seats_col, two_plus_col in (
            ("E", "economy_award_seats", "economy_seats_is_two_plus"),
            ("A", "premium_award_seats", "premium_seats_is_two_plus"),
            ("I", "business_award_seats", "business_seats_is_two_plus"),
        ):
            cnt = int(r[seats_col] or 0)
            if cnt <= 0:
                continue
            avail_str = "2+" if (cnt >= 2 and bool(r[two_plus_col])) else str(cnt)
            rec: dict[str, Any] = {
                "SegmentRoute": route,
                "SegmentDepDate": f"{fdate}T00:00:00",
                "FlightCarrier": carrier,
                "FlightNumber": num_digits,
                "RBD": rbd_code,
                "NewAvailability": avail_str,
            }
            if dep_t:
                rec["SegmentDepTime"] = dep_t
            if arr_t:
                rec["SegmentArrTime"] = arr_t
            records.append(rec)

    if not records:
        print(f"No #live rows found in {db_file}.")
        return 0

    consolidated = {"AccumulatedOutput": {"resultSet": [{"Record": records}]}}
    sorted_dests = sorted(dests_seen)
    min_d, max_d = min(dates_seen), max(dates_seen)
    print(
        f"Loaded {len(rows)} local #live flight rows ({len(records)} cabin records) across "
        f"{len(sorted_dests)} destinations ({min_d} .. {max_d}) from {db_file}."
    )
    remote_cnt = push_records_to_server(server_url, sorted_dests, min_d, max_d, consolidated)
    print(f"Synced {remote_cnt} merged #live flight rows to remote server ({server_url}).")
    return remote_cnt


def sync_from_exported_file(
    server_url: str,
    file_path: str,
    local_db_path: str = DEFAULT_LOCAL_DB_PATH,
    also_local: bool = True,
    skip_remote: bool = False,
) -> None:
    """Upload a saved JSON file of El Al RBD responses to the production server and/or local SQLite DB."""
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        print(f"File not found: {p}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(p.read_text(encoding="utf-8"))
    raw_list: list[dict[str, Any]] = []
    if isinstance(raw, dict) and "by_destination" in raw:
        for payloads in raw["by_destination"].values():
            if isinstance(payloads, list):
                raw_list.extend(x for x in payloads if isinstance(x, dict))
    elif isinstance(raw, dict) and "AccumulatedOutput" in raw:
        raw_list.append(raw)
    elif isinstance(raw, list):
        raw_list.extend(x for x in raw if isinstance(x, dict))

    if raw_list and any("AccumulatedOutput" in x for x in raw_list):
        consolidated, dests, min_d, max_d, raw_rec_cnt = normalize_accumulated_payloads(raw_list)
        payload_to_send: Any = consolidated
    else:
        payload_to_send = raw
        dests = list(ALL_ELAL_DESTINATIONS)
        min_d = date.today().isoformat()
        max_d = "2027-10-30"
        raw_rec_cnt = len(raw_list)

    print(f"Loaded {raw_rec_cnt} normalized RBD records across {len(dests)} destinations ({min_d}..{max_d}).")

    if also_local and local_db_path:
        local_cnt = sync_payload_to_local_db(local_db_path, dests, min_d, max_d, payload_to_send)
        print(f"Synced {local_cnt} real #live flight rows to local SQLite DB ({local_db_path}).")

    if not skip_remote and server_url:
        remote_cnt = push_records_to_server(server_url, dests, min_d, max_d, payload_to_send)
        print(f"Synced {remote_cnt} real #live flight rows to remote server ({server_url}).")


def run_sync_with_system_chrome(
    server_url: str,
    destinations: list[str],
    days_ahead: int = 345,
    local_db_path: str = DEFAULT_LOCAL_DB_PATH,
    also_local: bool = True,
    skip_remote: bool = False,
    save_json_path: str = "",
) -> dict[str, int]:
    """Fetch live El Al Economy (`E`) & Premium (`A`) availability via headless Chrome CDP and sync."""
    _ = days_ahead
    raw_payloads = fetch_live_holiday_payloads_via_cdp(destinations=destinations)
    consolidated, dests, min_d, max_d, raw_rec_cnt = normalize_accumulated_payloads(raw_payloads)

    print(
        f"\nFetched {raw_rec_cnt} raw cabin-flight availability records across "
        f"{len(dests)} destinations ({min_d} .. {max_d})."
    )

    if save_json_path:
        out_p = Path(save_json_path).expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(consolidated, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved normalized AccumulatedOutput snapshot to {out_p}")

    result_counts = {"raw_records": raw_rec_cnt, "local_synced": 0, "remote_synced": 0}

    if also_local and local_db_path:
        local_cnt = sync_payload_to_local_db(local_db_path, dests, min_d, max_d, consolidated)
        result_counts["local_synced"] = local_cnt
        print(f"Synced {local_cnt} merged #live flight rows to local SQLite DB ({local_db_path}).")

    if not skip_remote and server_url:
        remote_cnt = push_records_to_server(server_url, dests, min_d, max_d, consolidated)
        result_counts["remote_synced"] = remote_cnt
        print(f"Synced {remote_cnt} merged #live flight rows to remote server ({server_url}).")

    return result_counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and sync live El Al rbddataclients bonus availability to local SQLite and GCP production"
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER_URL,
        help=f"Production server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--local-db",
        default=DEFAULT_LOCAL_DB_PATH,
        help=f"Local SQLite DB path (default: {DEFAULT_LOCAL_DB_PATH})",
    )
    parser.add_argument(
        "--also-local",
        action="store_true",
        default=True,
        help="Also sync directly into local SQLite database (default: True)",
    )
    parser.add_argument(
        "--no-local",
        action="store_true",
        default=False,
        help="Skip syncing to local SQLite database",
    )
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        default=False,
        help="Skip syncing to remote production server",
    )
    parser.add_argument(
        "--from-file",
        default="",
        help="Path to exported JSON file (pure Python upload, zero browser binaries)",
    )
    parser.add_argument(
        "--push-local-db",
        action="store_true",
        default=False,
        help="Upload already-synced #live rows from local SQLite DB to remote server without re-running Chrome",
    )
    parser.add_argument(
        "--save-json",
        default="",
        help="Optional path to save the normalized AccumulatedOutput JSON snapshot",
    )
    parser.add_argument(
        "--destinations",
        default=",".join(ALL_ELAL_DESTINATIONS),
        help="Comma-separated destination IATA codes (default: all 25 catalog destinations)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=345,
        help="Horizon in days ahead (default: 345)",
    )
    args = parser.parse_args()
    also_local = bool(args.also_local and not args.no_local)

    if args.push_local_db:
        push_existing_local_db_to_server(server_url=args.server, local_db_path=args.local_db)
        return

    if args.from_file:
        sync_from_exported_file(
            server_url=args.server,
            file_path=args.from_file,
            local_db_path=args.local_db,
            also_local=also_local,
            skip_remote=args.skip_remote,
        )
        return

    dests = [d.strip().upper() for d in args.destinations.split(",") if d.strip()]
    run_sync_with_system_chrome(
        server_url=args.server,
        destinations=dests,
        days_ahead=args.days,
        local_db_path=args.local_db,
        also_local=also_local,
        skip_remote=args.skip_remote,
        save_json_path=args.save_json,
    )


if __name__ == "__main__":
    main()
