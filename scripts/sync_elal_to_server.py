#!/usr/bin/env python3
"""Automated El Al Classic Award Bonus Sync Script (`scripts/sync_elal_to_server.py`).

Fetches real live El Al Matmid bonus availability (`Economy` RBD `"E"` and `Premium` RBD `"A"`)
from `https://www.elal.com/rbddataclients/` (`GeneralRestServices-GetRbdAvailability`) across all
16×14-day Israeli Holiday & Ministry of Education school vacation windows for all 25 supported
`DESTINATION_CATALOG` destinations (`50` directional segments per request), and syncs them directly
into both the local SQLite database (`data/vacation_planner.db`) and the GCP Production server
(`https://breezyflights.com/api/v1/elal-bonus/sync`).

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
from datetime import date, timedelta
import json
import os
from pathlib import Path
import random
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
from typing import Any, Optional
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SERVER_URL = "https://breezyflights.com"
DEFAULT_LOCAL_DB_PATH = str(REPO_ROOT / "data" / "vacation_planner.db")
DEFAULT_SYNC_PROFILE_DIR = str(
    Path.home() / ".local" / "share" / "fvp-chrome-sync-profile"
)
ELAL_RBD_PAGE_URL = "https://www.elal.com/rbddataclients/"
ELAL_RBD_API_URL = (
    "https://www.elal.com/generalproxy/proxy/dpel/449/GeneralRestServices-GetRbdAvailability"
)

try:
    from backend.app.storage_cache.seed_data import DESTINATION_CATALOG as _CATALOG
    ALL_ELAL_DESTINATIONS: list[str] = list(_CATALOG.keys())
except Exception:
    # Standalone fallback when run outside the repo checkout (all 60 supported destinations)
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
        "SZG", "TIA", "ZRH", "BSL", "NAP", "VRN", "LYS", "OPO",
        "JMK", "PVK", "DBV", "ZAG", "LJU", "RMO", "SEZ",
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


def build_rolling_14d_windows(
    days_ahead: int = 350,
    ref_date: Optional[date] = None,
) -> list[dict[str, str]]:
    """Build contiguous 14-day windows covering the entire rolling year ahead (`[anchor .. anchor + days_ahead]`),
    including both holidays and regular non-holiday weeks.

    El Al's `GetRbdAvailability` endpoint accepts `endDate - startDate == 14 days` formatted as
    `YYYY-MM-DDT21:00:00.000Z` (midnight local Israel time for `YYYY-MM-DD + 1 day`, returning
    flights from `start_utc_day + 1` through `end_utc_day + 1` inclusive).
    """
    anchor = ref_date or date.today()
    horizon = max(14, min(364, int(days_ahead or 350)))
    num_windows = (horizon + 13) // 14
    windows: list[dict[str, str]] = []
    for idx in range(num_windows):
        start_utc_day = anchor - timedelta(days=1) + timedelta(days=14 * idx)
        end_utc_day = start_utc_day + timedelta(days=14)
        local_start = start_utc_day + timedelta(days=1)
        local_end = end_utc_day + timedelta(days=1)
        windows.append(
            {
                "label": f"Full-Year Window {idx + 1:02d}/{num_windows:02d} ({local_start.isoformat()} .. {local_end.isoformat()})",
                "start_iso": f"{start_utc_day.isoformat()}T21:00:00.000Z",
                "end_iso": f"{end_utc_day.isoformat()}T21:00:00.000Z",
                "local_start": local_start.isoformat(),
                "local_end": local_end.isoformat(),
            }
        )
    return windows


def build_sharded_rolling_windows(
    days_ahead: int = 350,
    shard_count: int = 5,
    shard_index: Optional[int] = None,
    today_override: Optional[date] = None,
    cycle_anchor_override: Optional[date] = None,
) -> tuple[list[dict[str, str]], int, int]:
    """Select one uniform shard of the 350-day rolling schedule anchored to the cycle start date.

    Anchoring `ref_date` guarantees zero window-boundary drift across all consecutive runs in the
    cycle, refreshing every single date across the 350-day horizon once per cycle (default: 5 shards).
    """
    today_d = today_override or date.today()
    n_shards = max(1, min(25, int(shard_count or 5)))
    if n_shards == 1:
        all_w = build_rolling_14d_windows(days_ahead=days_ahead, ref_date=today_d)
        return all_w, 0, 1

    cycle_anchor = (
        cycle_anchor_override
        if cycle_anchor_override is not None
        else date.fromordinal((today_d.toordinal() // n_shards) * n_shards)
    )
    resolved_idx = (
        (today_d.toordinal() % n_shards)
        if shard_index is None
        else (int(shard_index) % n_shards)
    )
    all_windows = build_rolling_14d_windows(days_ahead=days_ahead, ref_date=cycle_anchor)
    total_w = len(all_windows)
    start_pos = (resolved_idx * total_w) // n_shards
    end_pos = ((resolved_idx + 1) * total_w) // n_shards
    selected = all_windows[start_pos:end_pos]
    # Clamp any window start earlier than today so past days inside a cycle aren't queried unnecessarily
    min_utc_start = today_d - timedelta(days=1)
    clamped: list[dict[str, str]] = []
    for win in selected:
        w_start_utc = date.fromisoformat(win["start_iso"][:10])
        w_end_utc = date.fromisoformat(win["end_iso"][:10])
        if w_end_utc <= min_utc_start:
            continue
        if w_start_utc < min_utc_start:
            new_start_utc = min_utc_start
            new_end_utc = new_start_utc + timedelta(days=14)
            loc_s = new_start_utc + timedelta(days=1)
            loc_e = new_end_utc + timedelta(days=1)
            clamped.append(
                {
                    "label": f"{win['label'].split('(')[0].strip()} ({loc_s.isoformat()} .. {loc_e.isoformat()})",
                    "start_iso": f"{new_start_utc.isoformat()}T21:00:00.000Z",
                    "end_iso": f"{new_end_utc.isoformat()}T21:00:00.000Z",
                    "local_start": loc_s.isoformat(),
                    "local_end": loc_e.isoformat(),
                }
            )
        else:
            clamped.append(win)
    return clamped, resolved_idx, n_shards


def _shard_state_file(profile_dir: str | Path) -> Path:
    return Path(profile_dir or DEFAULT_SYNC_PROFILE_DIR).expanduser().resolve() / "shard_state.json"


def _load_shard_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_shard_state(
    state_path: Path,
    cycle_anchor: date,
    shard_count: int,
    completed_shard: int,
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    prev = _load_shard_state(state_path)
    history = prev.get("completed_at") if isinstance(prev.get("completed_at"), dict) else {}
    history[str(completed_shard)] = date.today().isoformat()
    payload = {
        "cycle_anchor": cycle_anchor.isoformat(),
        "shard_count": int(shard_count),
        "last_completed_shard": int(completed_shard),
        "completed_at": history,
    }
    tmp_p = state_path.with_suffix(".tmp")
    tmp_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_p.replace(state_path)


def resolve_sharded_plan(
    state_path: Optional[Path],
    days_ahead: int = 350,
    shard_count: int = 5,
    shard_index: Optional[int] = None,
    today_override: Optional[date] = None,
) -> tuple[list[dict[str, str]], int, int, date]:
    """Resolve the shard to execute next, resuming seamlessly from where the last completed run stopped.

    When `shard_index` is `None` (`auto`), persists progress across outages/sleep: if Cloudtop
    was shut down for days, the next wake resumes at `(last_completed_shard + 1) % shard_count`
    using the active cycle anchor rather than skipping shards or bursting missed days all at once.
    """
    today_d = today_override or date.today()
    n_shards = max(1, min(25, int(shard_count or 5)))
    if n_shards == 1:
        wins, _, _ = build_sharded_rolling_windows(
            days_ahead=days_ahead, shard_count=1, shard_index=0, today_override=today_d
        )
        return wins, 0, 1, today_d

    state = _load_shard_state(state_path) if state_path else {}
    same_count = int(state.get("shard_count") or 0) == n_shards
    raw_last = state.get("last_completed_shard")
    raw_anchor = state.get("cycle_anchor")

    saved_anchor: Optional[date] = None
    if isinstance(raw_anchor, str) and raw_anchor.strip():
        try:
            saved_anchor = date.fromisoformat(raw_anchor.strip()[:10])
        except ValueError:
            saved_anchor = None

    if shard_index is not None:
        chosen_idx = int(shard_index) % n_shards
        chosen_anchor = (
            saved_anchor
            if (same_count and saved_anchor is not None and 0 <= (today_d - saved_anchor).days <= 14)
            else today_d
        )
    elif same_count and isinstance(raw_last, int) and 0 <= raw_last < n_shards:
        chosen_idx = (raw_last + 1) % n_shards
        if (
            chosen_idx == 0
            or saved_anchor is None
            or (today_d - saved_anchor).days > 14
            or (today_d - saved_anchor).days < 0
        ):
            chosen_anchor = today_d
            if saved_anchor is None or (today_d - saved_anchor).days > 14:
                chosen_idx = 0
        else:
            chosen_anchor = saved_anchor
    else:
        chosen_idx = 0
        chosen_anchor = today_d

    wins, resolved_idx, resolved_tot = build_sharded_rolling_windows(
        days_ahead=days_ahead,
        shard_count=n_shards,
        shard_index=chosen_idx,
        today_override=today_d,
        cycle_anchor_override=chosen_anchor,
    )
    return wins, resolved_idx, resolved_tot, chosen_anchor


def build_single_target_date_window(target_date_iso: str) -> list[dict[str, str]]:
    """Build a single ultra-lightweight 14-day window starting on `target_date_iso` (`YYYY-MM-DD`)."""
    t_day = date.fromisoformat(target_date_iso.strip()[:10])
    start_utc_day = t_day - timedelta(days=1)
    end_utc_day = start_utc_day + timedelta(days=14)
    local_start = start_utc_day + timedelta(days=1)
    local_end = end_utc_day + timedelta(days=1)
    return [
        {
            "label": f"Targeted 14d Window ({local_start.isoformat()} .. {local_end.isoformat()})",
            "start_iso": f"{start_utc_day.isoformat()}T21:00:00.000Z",
            "end_iso": f"{end_utc_day.isoformat()}T21:00:00.000Z",
            "local_start": local_start.isoformat(),
            "local_end": local_end.isoformat(),
        }
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


def _build_https_ssl_context() -> ssl.SSLContext:
    """Build a verifying TLS context that handles macOS Python.framework missing OpenSSL cert bundles."""
    ctx = ssl.create_default_context()
    verify_paths = ssl.get_default_verify_paths()
    has_default_ca = bool(
        (verify_paths.cafile and Path(verify_paths.cafile).exists())
        or (verify_paths.capath and Path(verify_paths.capath).exists())
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("SSL_CERT_DIR")
    )
    if has_default_ca:
        return ctx

    try:
        import certifi  # type: ignore[import-not-found]

        ca_bundle = certifi.where()
        if ca_bundle and Path(ca_bundle).exists():
            return ssl.create_default_context(cafile=ca_bundle)
    except Exception:
        pass

    for candidate in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if Path(candidate).exists():
            return ssl.create_default_context(cafile=candidate)

    if sys.platform == "darwin":
        try:
            pem_out = subprocess.check_output(
                [
                    "/usr/bin/security",
                    "find-certificate",
                    "-a",
                    "-p",
                    "/System/Library/Keychains/SystemRootCertificates.keychain",
                ],
                text=True,
                timeout=10,
            )
            if "BEGIN CERTIFICATE" in pem_out:
                return ssl.create_default_context(cadata=pem_out)
        except Exception:
            pass

    return ctx


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
    reconcile_slices: Optional[list[dict[str, Any]]] = None,
    sync_token: str = "",
) -> int:
    """POST collected `AccumulatedOutput` payloads to `{server_url}/api/v1/elal-bonus/sync` in safe chunks."""
    if not accumulated_payloads and not reconcile_slices:
        return 0
    endpoint = f"{server_url.rstrip('/')}/api/v1/elal-bonus/sync"
    destinations_list = [dest_iata] if isinstance(dest_iata, str) else list(dest_iata)
    start_str = start_d.isoformat() if isinstance(start_d, date) else str(start_d)
    end_str = end_d.isoformat() if isinstance(end_d, date) else str(end_d)
    resolved_token = (sync_token or os.environ.get("ELAL_SYNC_API_TOKEN") or "").strip()
    ssl_ctx = _build_https_ssl_context() if endpoint.lower().startswith("https://") else None

    def _post_chunk(chunk_payload: Any, include_reconcile: bool = False) -> int:
        body: dict[str, Any] = {
            "origin": "TLV",
            "destinations": destinations_list,
            "start_date": start_str,
            "end_date": end_str,
            "force_refresh": True,
        }
        if chunk_payload is not None:
            body["rbd_payload"] = chunk_payload
        if include_reconcile and reconcile_slices:
            body["reconcile_slices"] = reconcile_slices
        headers = {"Content-Type": "application/json"}
        if resolved_token:
            headers["Authorization"] = f"Bearer {resolved_token}"
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_ctx) as resp:
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

        if not all_recs:
            return _post_chunk(
                {"AccumulatedOutput": {"resultSet": []}},
                include_reconcile=True,
            )

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
                synced = _post_chunk(chunk_payload, include_reconcile=(b_idx == 0))
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
            synced = _post_chunk(chunk, include_reconcile=(b_idx == 0))
            total_synced += synced
            print(
                f"  -> Remote sync batch {b_idx + 1}/{total_batches} "
                f"({len(chunk)} items -> {synced} rows synced)"
            )
        return total_synced

    return _post_chunk(accumulated_payloads, include_reconcile=True)


def sync_payload_to_local_db(
    local_db_path: str,
    destinations_list: list[str],
    start_str: str,
    end_str: str,
    rbd_payload: Any,
    reconcile_slices: Optional[list[dict[str, Any]]] = None,
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

    req_body: dict[str, Any] = {
        "origin": "TLV",
        "destinations": destinations_list,
        "start_date": start_str,
        "end_date": end_str,
        "force_refresh": True,
        "rbd_payload": rbd_payload,
    }
    if reconcile_slices:
        req_body["reconcile_slices"] = reconcile_slices
    hdrs: dict[str, str] = {}
    env_tok = os.environ.get("ELAL_SYNC_API_TOKEN", "").strip()
    if env_tok:
        hdrs["authorization"] = f"Bearer {env_tok}"
    status, _, raw_body = client.router.dispatch(
        "POST",
        "/api/v1/elal-bonus/sync",
        json_body=req_body,
        request_headers=hdrs,
    )
    if status != 200:
        raise RuntimeError(f"Local DB sync failed (HTTP {status}): {raw_body}")
    res_json = json.loads(raw_body)
    return int(res_json.get("records_synced", 0))


def fetch_live_holiday_payloads_via_cdp(
    destinations: list[str],
    windows: Optional[list[dict[str, str]]] = None,
    profile_dir: str = DEFAULT_SYNC_PROFILE_DIR,
    headed: Optional[bool] = None,
    min_delay_sec: float = 2.5,
    max_delay_sec: float = 4.5,
    return_reconcile_slices: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Launch stock Google Chrome via CDP with honest native headers, persistent profile,
    polite human-paced spacing (`2.5s..4.5s`), and strict fail-fast abort on any error.
    """
    chrome_bin = _find_chrome_binary()
    port = _find_free_port()
    active_windows, _, _ = (
        (windows, 0, 1)
        if windows is not None
        else build_sharded_rolling_windows(days_ahead=350, shard_count=5, shard_index=None)
    )
    valid_dests = [d for d in destinations if d in ALL_ELAL_DESTINATIONS] or list(ALL_ELAL_DESTINATIONS)

    dest_batches: list[list[str]] = [
        valid_dests[i : i + MAX_DESTINATIONS_PER_AJAX_BATCH]
        for i in range(0, len(valid_dests), MAX_DESTINATIONS_PER_AJAX_BATCH)
    ]
    total_segments = len(valid_dests) * 2

    resolved_profile = Path(profile_dir or DEFAULT_SYNC_PROFILE_DIR).expanduser().resolve()
    resolved_profile.mkdir(parents=True, exist_ok=True)

    # Default to visible desktop Chrome on macOS/Windows (personal computers), headless on headless Linux
    use_headed = (
        (sys.platform in ("darwin", "win32"))
        if headed is None
        else bool(headed)
    )

    cmd = [chrome_bin]
    if not use_headed:
        cmd.append("--headless=new")
        if sys.platform.startswith("linux"):
            cmd.append("--no-sandbox")
    cmd.extend(
        [
            f"--user-data-dir={resolved_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            ELAL_RBD_PAGE_URL,
        ]
    )

    mode_str = "visible desktop" if use_headed else "headless"
    print(
        f"Launching {mode_str} Chrome ({chrome_bin}) on CDP port {port} "
        f"[persistent profile: {resolved_profile}] for {len(valid_dests)} destinations "
        f"across {len(active_windows)} window(s)..."
    )
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp: Optional[_StdlibCdpWebSocket] = None
    collected_payloads: list[dict[str, Any]] = []
    verified_slices_map: dict[tuple[tuple[str, ...], str, str], set[str]] = {}

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
                f"Fail-fast abort: {ELAL_RBD_PAGE_URL} did not initialize cleanly within 45s "
                f"(last seen page: {last_seen_page or 'CDP not reachable'}). "
                "Stopping immediately without retrying so any active rate-limit cooldown is not extended."
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
            raise RuntimeError("Fail-fast abort: jQuery $.ajax not initialized on rbddataclients page.")

        print("El Al rbddataclients ready. Checking active calculator airports & running polite sharded scan...")

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

        def _query_batch_once(
            batch_dests: list[str],
            start_iso: str,
            end_iso: str,
            rbd: str,
        ) -> tuple[Optional[dict[str, Any]], int, str]:
            if not batch_dests:
                return None, 0, "empty_batch"
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
                        resolve({{ ok: true, status: 200, data: res }});
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
                    return data_obj, 200, ""
            st_code = int(val.get("status") or 0) if isinstance(val, dict) else 0
            err_msg = str(val.get("error") or "unexpected_response") if isinstance(val, dict) else "invalid_eval"
            return None, st_code, err_msg

        current_batches = [
            active_dests[i : i + MAX_DESTINATIONS_PER_AJAX_BATCH]
            for i in range(0, len(active_dests), MAX_DESTINATIONS_PER_AJAX_BATCH)
        ]

        aborted_early = False
        for w_idx, win in enumerate(active_windows, start=1):
            if aborted_early:
                break
            label = win["label"]
            start_iso = win["start_iso"]
            end_iso = win["end_iso"]
            loc_start = win.get("local_start") or (
                date.fromisoformat(start_iso[:10]) + timedelta(days=1)
            ).isoformat()
            loc_end = win.get("local_end") or (
                date.fromisoformat(end_iso[:10]) + timedelta(days=1)
            ).isoformat()

            for rbd in CABIN_RBDS:
                if aborted_early:
                    break
                cabin_label = "Economy" if rbd == "E" else "Premium"
                window_cabin_cnt = 0
                for b_dests in current_batches:
                    data_obj, http_status, err_msg = _query_batch_once(
                        b_dests, start_iso, end_iso, rbd
                    )
                    if data_obj is None:
                        print(
                            f"  ! Fail-fast stop on window [{w_idx:02d}/{len(active_windows):02d}] "
                            f"{cabin_label} ({rbd}) [status={http_status} error={err_msg}]. "
                            "Aborting remaining requests immediately to avoid rate-limit escalation."
                        )
                        aborted_early = True
                        break
                    collected_payloads.append(data_obj)
                    slice_key = (tuple(b_dests), loc_start, loc_end)
                    verified_slices_map.setdefault(slice_key, set()).add(rbd)
                    _, _, _, _, rec_cnt = normalize_accumulated_payloads([data_obj])
                    window_cabin_cnt += rec_cnt
                    delay = random.uniform(
                        max(0.5, float(min_delay_sec)),
                        max(float(min_delay_sec), float(max_delay_sec)),
                    )
                    time.sleep(delay)

                if not aborted_early:
                    print(
                        f"  [{w_idx:02d}/{len(active_windows):02d}] {label} | "
                        f"{cabin_label} ({rbd}): {window_cabin_cnt} available flight records"
                    )

        reconcile_slices: list[dict[str, Any]] = [
            {
                "destinations": list(b_tuple),
                "start_date": s_d,
                "end_date": e_d,
                "cabins": sorted(c_set),
            }
            for (b_tuple, s_d, e_d), c_set in verified_slices_map.items()
        ]
        if return_reconcile_slices:
            return collected_payloads, reconcile_slices
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
              AND expires_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
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
    days_ahead: int = 350,
    local_db_path: str = DEFAULT_LOCAL_DB_PATH,
    also_local: bool = True,
    skip_remote: bool = False,
    save_json_path: str = "",
    holidays_only: bool = False,
    shard_count: int = 5,
    shard_index: Optional[int] = None,
    target_date: str = "",
    profile_dir: str = DEFAULT_SYNC_PROFILE_DIR,
    headed: Optional[bool] = None,
    sync_token: str = "",
) -> dict[str, int]:
    """Fetch live El Al Economy (`E`) & Premium (`A`) availability via stock Chrome CDP and sync."""
    state_path: Optional[Path] = None
    active_cycle_anchor: Optional[date] = None
    resolved_idx = 0
    resolved_total = max(1, int(shard_count or 5))

    if target_date.strip():
        target_windows = build_single_target_date_window(target_date.strip())
        print(f"Selected single targeted 14-day window starting {target_date.strip()} (4 polite requests).")
    elif holidays_only:
        target_windows = HOLIDAY_14D_WINDOWS
        print(f"Selected {len(target_windows)} holiday windows.")
    else:
        state_path = _shard_state_file(profile_dir)
        target_windows, resolved_idx, resolved_total, active_cycle_anchor = resolve_sharded_plan(
            state_path=state_path,
            days_ahead=days_ahead,
            shard_count=shard_count,
            shard_index=shard_index,
        )
        print(
            f"Selected uniform 5-day rotation shard {resolved_idx + 1}/{resolved_total}: "
            f"{len(target_windows)} window(s) ({target_windows[0]['local_start']} .. {target_windows[-1]['local_end']}, "
            f"cycle anchor {active_cycle_anchor.isoformat()})."
        )

    fetched_res = fetch_live_holiday_payloads_via_cdp(
        destinations=destinations,
        windows=target_windows,
        profile_dir=profile_dir,
        headed=headed,
        return_reconcile_slices=True,
    )
    assert isinstance(fetched_res, tuple)
    raw_payloads, reconcile_slices = fetched_res
    consolidated, dests, min_d, max_d, raw_rec_cnt = normalize_accumulated_payloads(raw_payloads)

    print(
        f"\nFetched {raw_rec_cnt} raw cabin-flight availability records across "
        f"{len(reconcile_slices)} verified batch slice(s) ({min_d} .. {max_d})."
    )

    if save_json_path and (raw_rec_cnt > 0 or reconcile_slices):
        out_p = Path(save_json_path).expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(consolidated, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved normalized AccumulatedOutput snapshot to {out_p}")

    # Always keep a local recovery backup so fetched flights are never lost if upload hits a network/TLS error
    backup_snap_path = (
        Path(profile_dir or DEFAULT_SYNC_PROFILE_DIR).expanduser().resolve()
        / "last_fetched_snapshot.json"
    )
    if raw_rec_cnt > 0:
        try:
            backup_snap_path.parent.mkdir(parents=True, exist_ok=True)
            backup_snap_path.write_text(
                json.dumps(consolidated, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    result_counts = {"raw_records": raw_rec_cnt, "local_synced": 0, "remote_synced": 0}
    if raw_rec_cnt == 0 and not reconcile_slices:
        print("No slices completed; keeping resume cursor unchanged.")
        return result_counts

    # Automatically skip local SQLite sync when run standalone outside a repository checkout
    has_repo_backend = (REPO_ROOT / "backend" / "app" / "main.py").exists()
    if also_local and local_db_path and has_repo_backend:
        local_cnt = sync_payload_to_local_db(
            local_db_path,
            dests,
            min_d,
            max_d,
            consolidated,
            reconcile_slices=reconcile_slices,
        )
        result_counts["local_synced"] = local_cnt
        print(
            f"Synced {local_cnt} merged #live flight rows (reconciled {len(reconcile_slices)} slice(s)) "
            f"to local SQLite DB ({local_db_path})."
        )

    if not skip_remote and server_url:
        try:
            remote_cnt = push_records_to_server(
                server_url,
                dests,
                min_d,
                max_d,
                consolidated,
                reconcile_slices=reconcile_slices,
                sync_token=sync_token,
            )
        except Exception as exc:
            if raw_rec_cnt > 0 and backup_snap_path.exists():
                print(
                    f"\nRemote upload failed ({exc}). Your {raw_rec_cnt} fetched flight records were saved safely!\n"
                    f"Retry uploading without touching elal.com by running:\n"
                    f"  python3 sync_elal_to_server.py --no-local --from-file {backup_snap_path}",
                    file=sys.stderr,
                )
            raise
        result_counts["remote_synced"] = remote_cnt
        print(
            f"Synced {remote_cnt} merged #live flight rows (reconciled {len(reconcile_slices)} slice(s)) "
            f"to remote server ({server_url})."
        )

    if state_path is not None and active_cycle_anchor is not None and resolved_total > 1:
        unique_batches = {tuple(s.get("destinations") or []) for s in reconcile_slices}
        shard_completed = (
            bool(reconcile_slices)
            and len(reconcile_slices) == len(unique_batches) * len(target_windows)
            and all(set(s.get("cabins") or []) >= set(CABIN_RBDS) for s in reconcile_slices)
        )
        if shard_completed:
            _save_shard_state(state_path, active_cycle_anchor, resolved_total, resolved_idx)
            next_shard = (resolved_idx + 1) % resolved_total
            print(
                f"Saved resume state ({state_path}): shard {resolved_idx + 1}/{resolved_total} complete; "
                f"next run will resume at shard {next_shard + 1}/{resolved_total}."
            )
        else:
            print(
                f"Partial run only ({len(reconcile_slices)} slice(s)); resume cursor stays at shard "
                f"{resolved_idx + 1}/{resolved_total} so next run retries it cleanly."
            )

    return result_counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe sharded El Al Matmid award availability sync (5-day uniform rotation + manual targeted sync)"
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
        help="Also sync directly into local SQLite database when inside repo checkout (default: True)",
    )
    parser.add_argument(
        "--no-local",
        action="store_true",
        default=False,
        help="Skip syncing to local SQLite database (recommended when running standalone on personal laptop)",
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
        help="Upload non-expired #live rows from local SQLite DB to remote server without launching Chrome",
    )
    parser.add_argument(
        "--save-json",
        default="",
        help="Optional path to save the normalized AccumulatedOutput JSON snapshot",
    )
    parser.add_argument(
        "--destinations",
        default=",".join(ALL_ELAL_DESTINATIONS),
        help="Comma-separated destination IATA codes (default: all 60 catalog destinations)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=350,
        help="Continuous rolling full-year horizon in days ahead (default: 350)",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=5,
        help="Number of daily shards in uniform rotation cycle (default: 5 -> 5 windows / 20 polite requests per day)",
    )
    parser.add_argument(
        "--shard-index",
        default="auto",
        help="Shard index 0..(shard_count-1), or 'auto' for today's cycle shard (default: auto)",
    )
    parser.add_argument(
        "--all-windows",
        action="store_true",
        default=False,
        help="Scan all 25 windows in a single run instead of 5-day sharding (not recommended; higher ban risk)",
    )
    parser.add_argument(
        "--target-date",
        default="",
        help="Ultra-safe manual mode: scan ONLY one 14-day window starting on YYYY-MM-DD (just 4 requests total)",
    )
    parser.add_argument(
        "--holidays-only",
        action="store_true",
        default=False,
        help="Scan only the 16 holiday windows",
    )
    parser.add_argument(
        "--profile-dir",
        default=DEFAULT_SYNC_PROFILE_DIR,
        help=f"Persistent dedicated Chrome sync profile directory (default: {DEFAULT_SYNC_PROFILE_DIR})",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        default=False,
        help="Force visible desktop Chrome window (default automatically on macOS/Windows)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Force headless Chrome mode (default automatically on Linux/Cloudtop)",
    )
    parser.add_argument(
        "--not-before",
        default=os.environ.get("FVP_NOT_BEFORE_DATE", ""),
        help="Optional cooldown guard date YYYY-MM-DD: politely skip execution before this date",
    )
    parser.add_argument(
        "--sync-token",
        default=os.environ.get("ELAL_SYNC_API_TOKEN", ""),
        help="Optional Bearer token for POST /api/v1/elal-bonus/sync",
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

    if args.not_before.strip():
        guard_date = date.fromisoformat(args.not_before.strip()[:10])
        if date.today() < guard_date:
            print(
                f"Cooldown guard active: today ({date.today().isoformat()}) is before "
                f"--not-before {guard_date.isoformat()}. Exiting cleanly with zero network traffic."
            )
            return

    headed_opt: Optional[bool] = (
        True if args.headed else (False if args.headless else None)
    )
    eff_shard_count = 1 if args.all_windows else max(1, int(args.shard_count))
    raw_sidx = str(args.shard_index).strip().lower()
    eff_shard_idx: Optional[int] = (
        None if raw_sidx in ("", "auto") else int(raw_sidx)
    )

    dests = [d.strip().upper() for d in args.destinations.split(",") if d.strip()]
    run_sync_with_system_chrome(
        server_url=args.server,
        destinations=dests,
        days_ahead=args.days,
        local_db_path=args.local_db,
        also_local=also_local,
        skip_remote=args.skip_remote,
        save_json_path=args.save_json,
        holidays_only=args.holidays_only,
        shard_count=eff_shard_count,
        shard_index=eff_shard_idx,
        target_date=args.target_date,
        profile_dir=args.profile_dir,
        headed=headed_opt,
        sync_token=args.sync_token,
    )


if __name__ == "__main__":
    main()
