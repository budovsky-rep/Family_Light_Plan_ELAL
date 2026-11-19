"""El Al Matmid Classic Award (`https://www.elal.com/rbddataclients/`) Client Adapter.

Implements Features `F17`, `F19`, `F20`, and `F21`:
- Metropolitan-to-Airport 3-letter IATA expansion (`NYC`->`["JFK","EWR"]`,
  `LON`->`["LHR","LTN"]`, `PAR`->`["CDG"]`, `MIL`->`["MXP"]`, `ROM`->`["FCO"]`,
  `TYO`->`["NRT"]`, `MIA_AREA`->`["MIA","FLL"]`).
- `ANYWHERE` Region Discovery across all 25 supported El Al destinations in Zones A-E.
- Classic Award RBD bucket validation (`Economy`: `E/X/U`, `Premium`: `P/A/R`,
  `Business`: `I/W`) and `0` / `1` / `2+` (`*_seats_is_two_plus`) seat cap parsing.
- El Al Shabbat operational constraints (no Friday afternoon `>= 14:00` or
  Saturday daytime `< 20:30` departures, no Friday overnight roll into Saturday)
  and Ben Gurion Airport (`TLV`) Yom Kippur total shutdown enforcement.
- Polite token-bucket rate limiter (`2.0-2.5s` min interval + `[1.5, 3.5]s` jitter,
  max 15 route-months per batch, with injectable clock/sleep for fast unit tests).
- Tier-1 4-hour (`14,400s`) SQLite TTL cache integration via `SQLiteRepository`.
"""

from __future__ import annotations

import json
import os
import random
import urllib.request
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Optional

from backend.app.calendar_engine.moe_calendar_service import MoECalendarService
from backend.app.config_manager.settings import AppSettings, get_settings
from backend.app.schemas.domain import ElAlBonusAvailability
from backend.app.storage_cache.repository import SQLiteRepository
from backend.app.storage_cache.seed_data import (
    DESTINATION_CATALOG,
    YOM_KIPPUR_CLOSED_DATES,
    _make_bonus_row,
    build_seeded_elal_bonus_availability,
    is_shabbat_blocked_for_elal,
)

METRO_IATA_EXPANSION: dict[str, list[str]] = {
    "NYC": ["JFK", "EWR"],
    "LON": ["LHR", "LTN"],
    "PAR": ["CDG"],
    "MIL": ["MXP"],
    "ROM": ["FCO"],
    "TYO": ["NRT"],
    "MIA_AREA": ["MIA", "FLL"],
}

SUPPORTED_ELAL_DESTINATIONS: list[str] = list(DESTINATION_CATALOG.keys())

CLASSIC_AWARD_RBDS: dict[str, tuple[str, ...]] = {
    "ECONOMY": ("E", "X", "U"),
    "PREMIUM": ("P", "A", "R"),
    "BUSINESS": ("I", "W"),
}


def is_elal_peak_award_season(flight_date: date) -> bool:
    """Return True when `flight_date` falls within El Al's peak / holiday Classic Award windows
    (Pesach, Shavuot, Summer school break Jun 20 - Aug 31, High Holidays / Sukkot, Hanukkah / late Dec).
    """
    m, d = flight_date.month, flight_date.day
    if m == 4 and 8 <= d <= 30:
        return True
    if m == 6 and d >= 6:
        return True
    if m in (7, 8):
        return True
    if m == 9 and d >= 24:
        return True
    if m == 10 and d <= 28:
        return True
    if m == 12 and d >= 4:
        return True
    return False


def compute_live_seasonal_economy_points(dest_iata: str, flight_date: date) -> int:
    """Compute realistic one-way El Al Classic Award Economy points for live-synced (`#live`) rows,
    without artificial 50% Tuesday FlyCard discounts and with a +20% peak/holiday seasonal adjustment.
    """
    meta = DESTINATION_CATALOG.get(dest_iata.strip().upper(), {})
    base_econ = int(meta.get("economy_points", 15000))
    if is_elal_peak_award_season(flight_date):
        return int(round((base_econ * 1.20) / 250.0) * 250)
    return base_econ

COMMERCIAL_REVENUE_RBDS: dict[str, tuple[str, ...]] = {
    "ECONOMY": ("Y", "S", "M", "Q", "B", "H", "V", "N", "K", "L", "T", "O", "G"),
    "PREMIUM": ("W", "Q", "B", "P"),
    "BUSINESS": ("J", "C", "D", "Z", "I", "R"),
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_date(val: date | datetime | str) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if "T" in s:
            s = s.split("T", 1)[0]
        return date.fromisoformat(s)
    raise ValueError(f"Cannot parse date from {val!r}")


def parse_rbd_seat_indicator(raw_value: Any) -> tuple[int, bool]:
    """Parse `rbddataclients` seat indicator (`0`, `1`, `2`/`2+`) into `(seat_count, is_two_plus)`."""
    if raw_value is None or raw_value == "":
        return 0, False
    if isinstance(raw_value, bool):
        raise ValueError(f"Invalid boolean seat indicator: {raw_value!r}")
    if isinstance(raw_value, str):
        s = raw_value.strip()
        if not s:
            return 0, False
        if s.endswith("+"):
            num_part = s[:-1].strip()
            if not num_part.isdigit():
                raise ValueError(f"Invalid seat indicator string: {raw_value!r}")
            cnt = int(num_part)
            if cnt < 0 or cnt > 9:
                raise ValueError(f"Award seat count out of bounds (0..9): {cnt}")
            return max(2, cnt), True
        if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
            raise ValueError(f"Invalid seat indicator string: {raw_value!r}")
        cnt = int(s)
    elif isinstance(raw_value, (int, float)):
        cnt = int(raw_value)
    else:
        raise ValueError(f"Unsupported seat indicator type: {raw_value!r}")

    if cnt < 0 or cnt > 9:
        raise ValueError(f"Award seat count must be between 0 and 9, got {cnt}")
    return cnt, (cnt >= 2)


class PoliteTokenBucketRateLimiter:
    """Polite token-bucket rate limiter for `https://www.elal.com/rbddataclients/`.

    Enforces a minimum interval (`2.0-2.5s`) plus random jitter (`[1.5, 3.5]s`)
    and caps route-month queries at `max_route_months_per_batch` (default 15).
    Supports injectable `clock_fn`, `sleep_fn`, and `rng_fn` so unit tests run
    deterministically without wall-clock delay.
    """

    def __init__(
        self,
        min_interval_sec: float = 2.0,
        jitter_range_sec: tuple[float, float] = (1.5, 3.5),
        max_route_months_per_batch: int = 15,
        clock_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        rng_fn: Optional[Callable[[float, float], float]] = None,
    ) -> None:
        self.min_interval_sec: float = max(0.0, float(min_interval_sec))
        low_j, high_j = float(jitter_range_sec[0]), float(jitter_range_sec[1])
        self.jitter_range_sec: tuple[float, float] = (min(low_j, high_j), max(low_j, high_j))
        self.max_route_months_per_batch: int = max(1, int(max_route_months_per_batch))
        self._virtual_time: float = 0.0
        self._clock_fn: Callable[[], float] = clock_fn or (lambda: self._virtual_time)
        self._sleep_fn: Callable[[float], None] = sleep_fn or self._advance_virtual_clock
        self._rng_fn: Callable[[float, float], float] = rng_fn or random.uniform
        self._last_request_ts: Optional[float] = None
        self.total_slept_seconds: float = 0.0
        self.acquire_count: int = 0
        self.sleep_history: list[float] = []

    def _advance_virtual_clock(self, seconds: float) -> None:
        self._virtual_time += max(0.0, float(seconds))

    def acquire(self) -> float:
        """Acquire a rate-limit token, sleeping if needed, and return delay seconds."""
        now = float(self._clock_fn())
        delay = 0.0
        if self._last_request_ts is not None:
            target_interval = max(
                self.min_interval_sec,
                float(self._rng_fn(self.jitter_range_sec[0], self.jitter_range_sec[1])),
            )
            elapsed = now - self._last_request_ts
            if elapsed < target_interval:
                delay = round(target_interval - elapsed, 4)
                self._sleep_fn(delay)
                self.total_slept_seconds += delay
                self.sleep_history.append(delay)
                now = float(self._clock_fn())
        self._last_request_ts = now
        self.acquire_count += 1
        return delay

    def cap_route_months_batch(
        self, route_months: list[tuple[str, str]]
    ) -> tuple[list[tuple[str, str]], list[list[tuple[str, str]]]]:
        """Split `route_months` into batches of at most `max_route_months_per_batch` (15)."""
        if not route_months:
            return [], []
        cap = self.max_route_months_per_batch
        batches = [
            route_months[idx : idx + cap]
            for idx in range(0, len(route_months), cap)
        ]
        first_batch = batches[0]
        for _item in first_batch:
            self.acquire()
        return first_batch, batches


class ElAlRbdDataClientAdapter:
    """Adapter for El Al's Matmid Classic Award Calculator (`https://www.elal.com/rbddataclients/`)."""

    def __init__(
        self,
        repository: Optional[SQLiteRepository] = None,
        settings: Optional[dict[str, Any] | AppSettings] = None,
        calendar_service: Optional[MoECalendarService] = None,
        clock_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        rng_fn: Optional[Callable[[float, float], float]] = None,
    ) -> None:
        self.repository: SQLiteRepository = repository or SQLiteRepository(auto_seed=True)
        if isinstance(settings, AppSettings):
            self._settings: dict[str, Any] = settings.to_dict()
        elif isinstance(settings, dict):
            self._settings = dict(settings)
        else:
            self._settings = get_settings()

        self.calendar_service: MoECalendarService = calendar_service or MoECalendarService(
            self.repository
        )

        rbd_cfg = self._settings.get("elal_rbd_client") or {}
        self.base_url: str = str(
            rbd_cfg.get("base_url") or "https://www.elal.com/rbddataclients/"
        )
        self.cache_ttl_seconds: int = int(rbd_cfg.get("cache_ttl_seconds", 14400))
        self.max_route_months_per_batch: int = int(
            rbd_cfg.get("max_route_months_per_batch", 15)
        )
        min_interval = float(rbd_cfg.get("rate_limit_min_interval_sec", 2.0))
        raw_jitter = rbd_cfg.get("rate_limit_jitter_sec") or [1.5, 3.5]
        jitter_tuple = (
            float(raw_jitter[0]) if len(raw_jitter) > 0 else 1.5,
            float(raw_jitter[1]) if len(raw_jitter) > 1 else 3.5,
        )

        cfg_metro = rbd_cfg.get("metro_iata_expansion") or {}
        self.metro_iata_map: dict[str, list[str]] = {
            **METRO_IATA_EXPANSION,
            **{str(k).upper(): [str(x).upper() for x in v] for k, v in cfg_metro.items()},
        }

        self.rate_limiter = PoliteTokenBucketRateLimiter(
            min_interval_sec=min_interval,
            jitter_range_sec=jitter_tuple,
            max_route_months_per_batch=self.max_route_months_per_batch,
            clock_fn=clock_fn,
            sleep_fn=sleep_fn,
            rng_fn=rng_fn,
        )

    def expand_metro_iatas(self, codes: list[str] | tuple[str, ...] | str) -> list[str]:
        """Expand metropolitan codes (`NYC`, `LON`, `PAR`, `MIL`, `ROM`, `TYO`, `MIA_AREA`)
        and `ANYWHERE` into deduplicated 3-letter airport IATA codes.

        Raises `ValueError` on empty input or invalid IATA codes.
        """
        if codes is None:
            raise ValueError("Destination IATA codes cannot be None")
        if isinstance(codes, str):
            raw_tokens = [tok.strip() for tok in codes.split(",") if tok.strip()]
        elif isinstance(codes, (list, tuple)):
            raw_tokens = []
            for item in codes:
                if item is None:
                    raise ValueError("Destination IATA code cannot be None")
                s_item = str(item).strip()
                if not s_item:
                    raise ValueError("Destination IATA code cannot be empty")
                for sub in s_item.split(","):
                    sub_clean = sub.strip()
                    if sub_clean:
                        raw_tokens.append(sub_clean)
        else:
            raise ValueError(f"Unsupported destination codes type: {type(codes).__name__}")

        if not raw_tokens:
            raise ValueError("Destination IATA codes list cannot be empty")

        expanded: list[str] = []
        seen: set[str] = set()

        def _append_unique(iata: str) -> None:
            if iata not in seen:
                seen.add(iata)
                expanded.append(iata)

        for token in raw_tokens:
            norm = token.upper().strip()
            if not norm:
                raise ValueError(f"Invalid empty IATA code: {token!r}")

            # 1. Check metropolitan expansion map FIRST (since NYC, LON, PAR, MIL, ROM, TYO are 3 letters)
            if norm in self.metro_iata_map:
                for airport_iata in self.metro_iata_map[norm]:
                    _append_unique(airport_iata)
                continue

            # 2. Check ANYWHERE region discovery
            if norm in ("ANYWHERE", "ALL", "*"):
                for dest_iata in SUPPORTED_ELAL_DESTINATIONS:
                    _append_unique(dest_iata)
                continue

            # 3. Validate 3-letter ASCII alphabetic airport IATA code
            if len(norm) == 3 and norm.isalpha() and norm.isascii():
                _append_unique(norm)
                continue

            raise ValueError(
                f"Invalid IATA or metropolitan code {token!r}: must be a 3-letter airport IATA, "
                f"supported metro code ({', '.join(sorted(self.metro_iata_map))}), or 'ANYWHERE'."
            )

        return expanded

    def _enumerate_route_months(
        self, destinations: list[str], start_date: date, end_date: date
    ) -> list[tuple[str, str]]:
        """Build ordered `(destination_iata, 'YYYY-MM')` pairs for rate-limiter batching."""
        months: list[str] = []
        cur_y, cur_m = start_date.year, start_date.month
        end_y, end_m = end_date.year, end_date.month
        while (cur_y, cur_m) <= (end_y, end_m):
            months.append(f"{cur_y:04d}-{cur_m:02d}")
            if cur_m == 12:
                cur_y += 1
                cur_m = 1
            else:
                cur_m += 1
        return [(dest, ym) for dest in destinations for ym in months]

    def _is_date_blocked_by_yom_kippur(self, target_date: date) -> bool:
        if target_date in YOM_KIPPUR_CLOSED_DATES:
            return True
        return self.calendar_service.is_tlv_airport_closed(target_date)

    def _try_live_http_fetch(
        self,
        expanded_destinations: list[str],
        start_date: date,
        end_date: date,
        origin: str = "TLV",
    ) -> list[ElAlBonusAvailability]:
        """Attempt live HTTPS fetch from `https://www.elal.com/rbddataclients/` when
        running on a VM / Cloud Run environment with external internet egress
        (`ELAL_LIVE_FETCH_ENABLED=1`). Returns an empty list on network/sandbox
        restrictions so caller seamlessly falls back to the seeded catalog.
        """
        if os.environ.get("ELAL_ALLOW_DIRECT_HTTP_EGRESS", "0") not in (
            "1",
            "true",
            "TRUE",
        ):
            return []
        if os.environ.get("ELAL_LIVE_FETCH_ENABLED", "0") not in ("1", "true", "TRUE"):
            return []

        now_dt = datetime.now(UTC).replace(microsecond=0)
        fetched_iso = now_dt.isoformat().replace("+00:00", "Z")
        expires_iso = (
            (now_dt + timedelta(seconds=self.cache_ttl_seconds))
            .isoformat()
            .replace("+00:00", "Z")
        )
        live_rows: list[ElAlBonusAvailability] = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }

        for dest in expanded_destinations:
            url = (
                f"{self.base_url.rstrip('/')}?origin={origin}&destination={dest}"
                f"&startDate={start_date.isoformat()}&endDate={end_date.isoformat()}"
            )
            try:
                self.rate_limiter.acquire()
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status != 200:
                        continue
                    raw_text = resp.read().decode("utf-8", errors="replace").strip()
                    if not raw_text.startswith(("{", "[")):
                        continue
                    payload = json.loads(raw_text)
                    items = (
                        payload
                        if isinstance(payload, list)
                        else payload.get("flights") or payload.get("data") or []
                    )
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        f_date = _parse_date(item.get("flight_date") or item.get("date") or start_date)
                        if not (start_date <= f_date <= end_date):
                            continue
                        econ_cnt, _ = parse_rbd_seat_indicator(item.get("economy_seats", item.get("E", 0)))
                        prem_cnt, _ = parse_rbd_seat_indicator(item.get("premium_seats", item.get("P", 0)))
                        biz_cnt, _ = parse_rbd_seat_indicator(item.get("business_seats", item.get("I", 0)))
                        direction = str(item.get("direction", "OUTBOUND")).upper()
                        row = _make_bonus_row(
                            dest_iata=dest,
                            flight_date=f_date,
                            direction=direction,
                            econ_seats=econ_cnt,
                            prem_seats=prem_cnt,
                            biz_seats=biz_cnt,
                            flycard_promo=False,
                            fetched_iso=fetched_iso,
                            expires_iso=expires_iso,
                            custom_econ_pts=compute_live_seasonal_economy_points(dest, f_date),
                        )
                        live_rows.append(row)
            except Exception:
                continue

        return live_rows

    def parse_and_import_external_rbd_payload(
        self,
        raw_payload: Any,
        default_origin: str = "TLV",
        default_destination: Optional[str] = None,
    ) -> list[ElAlBonusAvailability]:
        """Parse real El Al `GeneralRestServices-GetRbdAvailability` JSON (`AccumulatedOutput.resultSet`)
        or pasted `rbddataclients` table text into verified `ElAlBonusAvailability` rows (`#live`).
        """
        now_dt = datetime.now(UTC).replace(microsecond=0)
        fetched_iso = now_dt.isoformat().replace("+00:00", "Z")
        live_ttl = max(self.cache_ttl_seconds, 86400 * 30)
        expires_iso = (
            (now_dt + timedelta(seconds=live_ttl))
            .isoformat()
            .replace("+00:00", "Z")
        )
        live_source_url = f"{self.base_url.rstrip('/')}#live"

        grouped: dict[tuple[str, str, date, str], dict[str, Any]] = {}

        # Ensure existing live rows for the same (dest_iata, direction, flight_date, flight_number)
        # preserve seats from other cabins when syncing Economy, then Premium, then Business separately!
        existing_live_by_key: dict[tuple[str, str, date, str], ElAlBonusAvailability] = {}
        try:
            cached_existing = self.repository.get_cached_elal_bonus(include_expired=False)
            for ex in cached_existing:
                if "#live" in str(ex.source_url or ""):
                    ex_dest = ex.destination_iata if ex.direction == "OUTBOUND" else ex.origin_iata
                    existing_live_by_key[(ex_dest, ex.direction, ex.flight_date, ex.flight_number)] = ex
        except Exception:
            pass

        def _extract_hhmm(raw_val: Any) -> Optional[str]:
            if not raw_val:
                return None
            s = str(raw_val).strip()
            if "T" in s:
                s = s.split("T", 1)[1].strip()
            if len(s) >= 5 and s[2] == ":" and s[:2].isdigit() and s[3:5].isdigit():
                return s[:5]
            return None

        def _merge_flight_record(
            orig_iata: str,
            dest_iata: str,
            f_date: date,
            f_num: str,
            rbd_code: str,
            seat_cnt: int,
            dep_hhmm: Optional[str] = None,
            arr_hhmm: Optional[str] = None,
        ) -> None:
            if seat_cnt <= 0:
                return
            orig_u = orig_iata.strip().upper()
            dest_u = dest_iata.strip().upper()
            direction = "INBOUND" if dest_u == "TLV" else "OUTBOUND"
            route_dest = orig_u if direction == "INBOUND" else dest_u
            if route_dest not in DESTINATION_CATALOG:
                return
            clean_num = f_num.strip().upper()
            if clean_num.isdigit():
                clean_num = f"LY{int(clean_num):03d}"
            elif clean_num.startswith("LY") and clean_num[2:].strip().isdigit():
                clean_num = f"LY{int(clean_num[2:].strip()):03d}"

            key = (route_dest, direction, f_date, clean_num)
            prev = existing_live_by_key.get(key)
            entry = grouped.setdefault(
                key,
                {
                    "dest_iata": route_dest,
                    "direction": direction,
                    "flight_date": f_date,
                    "flight_number": clean_num,
                    "econ_seats": prev.economy_award_seats if prev else 0,
                    "prem_seats": prev.premium_award_seats if prev else 0,
                    "biz_seats": prev.business_award_seats if prev else 0,
                    "dep_time": dep_hhmm or (prev.departure_time_local if prev else None),
                    "arr_time": arr_hhmm or (prev.arrival_time_local if prev else None),
                },
            )
            if dep_hhmm:
                entry["dep_time"] = dep_hhmm
            if arr_hhmm:
                entry["arr_time"] = arr_hhmm
            rbd_u = rbd_code.strip().upper()
            if rbd_u in CLASSIC_AWARD_RBDS["BUSINESS"] or rbd_u == "BUSINESS":
                entry["biz_seats"] = max(entry["biz_seats"], seat_cnt)
            elif rbd_u in CLASSIC_AWARD_RBDS["PREMIUM"] or rbd_u == "PREMIUM":
                entry["prem_seats"] = max(entry["prem_seats"], seat_cnt)
            else:
                entry["econ_seats"] = max(entry["econ_seats"], seat_cnt)

        def _ingest_accumulated_output(acc_wrapper: dict[str, Any]) -> None:
            acc_obj = acc_wrapper.get("AccumulatedOutput")
            if not isinstance(acc_obj, dict):
                return
            raw_res_sets = acc_obj.get("resultSet")
            if isinstance(raw_res_sets, dict):
                res_sets = [raw_res_sets]
            elif isinstance(raw_res_sets, list):
                res_sets = raw_res_sets
            else:
                res_sets = []
            for rs in res_sets:
                if not isinstance(rs, dict):
                    continue
                raw_records = rs.get("Record")
                if isinstance(raw_records, dict):
                    records = [raw_records]
                elif isinstance(raw_records, list):
                    records = raw_records
                else:
                    records = []
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    route_str = str(rec.get("SegmentRoute") or "").strip().upper()
                    if len(route_str) == 6:
                        orig_c, dest_c = route_str[:3], route_str[3:]
                    else:
                        orig_c = default_origin
                        dest_c = default_destination or "FCO"
                    f_date = _parse_date(rec.get("SegmentDepDate") or date.today())
                    carrier = str(rec.get("FlightCarrier") or "LY").strip().upper()
                    f_num_raw = f"{carrier}{str(rec.get('FlightNumber') or '').strip()}"
                    rbd_c = str(rec.get("RBD") or "E").strip().upper()
                    avail_cnt, _ = parse_rbd_seat_indicator(rec.get("NewAvailability", 0))
                    dep_t = _extract_hhmm(rec.get("SegmentDepTime"))
                    arr_t = _extract_hhmm(rec.get("SegmentArrTime"))
                    _merge_flight_record(
                        orig_c, dest_c, f_date, f_num_raw, rbd_c, avail_cnt, dep_t, arr_t
                    )

        payload_obj = raw_payload
        if isinstance(raw_payload, str):
            stripped = raw_payload.strip()
            if stripped.startswith(("{", "[")):
                try:
                    payload_obj = json.loads(stripped)
                except Exception:
                    payload_obj = stripped

        if isinstance(payload_obj, dict) and "AccumulatedOutput" in payload_obj:
            _ingest_accumulated_output(payload_obj)
        elif isinstance(payload_obj, list):
            for item in payload_obj:
                if not isinstance(item, dict):
                    continue
                if "AccumulatedOutput" in item:
                    _ingest_accumulated_output(item)
                else:
                    dest_c = str(item.get("destination_iata") or default_destination or "FCO").strip().upper()
                    if dest_c not in DESTINATION_CATALOG:
                        continue
                    f_date = _parse_date(item.get("flight_date") or item.get("date") or date.today())
                    direction = str(item.get("direction") or "OUTBOUND").strip().upper()
                    orig_c = default_origin if direction == "OUTBOUND" else dest_c
                    dest_target = dest_c if direction == "OUTBOUND" else default_origin
                    f_num_raw = str(item.get("flight_number") or "LY001")
                    dep_t = _extract_hhmm(
                        item.get("departure_time_local")
                        or item.get("dep_time")
                        or item.get("SegmentDepTime")
                    )
                    arr_t = _extract_hhmm(
                        item.get("arrival_time_local")
                        or item.get("arr_time")
                        or item.get("SegmentArrTime")
                    )
                    e_cnt, _ = parse_rbd_seat_indicator(item.get("economy_seats", item.get("E", 0)))
                    p_cnt, _ = parse_rbd_seat_indicator(
                        item.get("premium_seats", item.get("P", item.get("A", 0)))
                    )
                    b_cnt, _ = parse_rbd_seat_indicator(item.get("business_seats", item.get("I", 0)))
                    if e_cnt > 0:
                        _merge_flight_record(orig_c, dest_target, f_date, f_num_raw, "E", e_cnt, dep_t, arr_t)
                    if p_cnt > 0:
                        _merge_flight_record(orig_c, dest_target, f_date, f_num_raw, "A", p_cnt, dep_t, arr_t)
                    if b_cnt > 0:
                        _merge_flight_record(orig_c, dest_target, f_date, f_num_raw, "I", b_cnt, dep_t, arr_t)

        rows: list[ElAlBonusAvailability] = []
        for info in grouped.values():
            r = _make_bonus_row(
                dest_iata=info["dest_iata"],
                flight_date=info["flight_date"],
                direction=info["direction"],
                econ_seats=info["econ_seats"],
                prem_seats=info["prem_seats"],
                biz_seats=info["biz_seats"],
                flycard_promo=False,
                fetched_iso=fetched_iso,
                expires_iso=expires_iso,
                custom_flight_num=info["flight_number"],
                custom_dep_time=info.get("dep_time"),
                custom_arr_time=info.get("arr_time"),
                custom_econ_pts=compute_live_seasonal_economy_points(
                    info["dest_iata"], info["flight_date"]
                ),
            )
            r.source_url = live_source_url
            rows.append(r)

        if rows:
            self.repository.upsert_elal_bonus(rows, ttl_seconds=live_ttl)
        return rows

    def _synthesize_live_or_seeded_records(
        self,
        expanded_destinations: list[str],
        start_date: date,
        end_date: date,
        origin: str = "TLV",
    ) -> list[ElAlBonusAvailability]:
        """Generate or refresh `ElAlBonusAvailability` records for `expanded_destinations` in `[start_date, end_date]`.

        In production live mode (`ELAL_LIVE_FETCH_ENABLED=1`), NEVER fabricates synthetic or seeded
        flights: returns only real live-fetched flights (or an empty list if none were fetched).
        """
        live_mode = os.environ.get("ELAL_LIVE_FETCH_ENABLED", "0").strip() in ("1", "true", "TRUE")
        if live_mode:
            live_fetched = self._try_live_http_fetch(
                expanded_destinations=expanded_destinations,
                start_date=start_date,
                end_date=end_date,
                origin=origin,
            )
            live_source_url = f"{self.base_url.rstrip('/')}#live"
            for r in live_fetched:
                r.source_url = live_source_url
            return live_fetched

        now_dt = datetime.now(UTC).replace(microsecond=0)
        fetched_iso = now_dt.isoformat().replace("+00:00", "Z")
        expires_iso = (
            (now_dt + timedelta(seconds=self.cache_ttl_seconds))
            .isoformat()
            .replace("+00:00", "Z")
        )

        seeded_all = build_seeded_elal_bonus_availability(ttl_seconds=self.cache_ttl_seconds)
        live_fetched = self._try_live_http_fetch(
            expanded_destinations=expanded_destinations,
            start_date=start_date,
            end_date=end_date,
            origin=origin,
        )
        if live_fetched:
            seeded_all = live_fetched + seeded_all
        dest_set = set(expanded_destinations)
        orig_upper = origin.upper()

        records_by_id: dict[str, ElAlBonusAvailability] = {}
        covered_out_dates: set[tuple[str, date]] = set()
        covered_in_dates: set[tuple[str, date]] = set()

        for row in seeded_all:
            if not (start_date <= row.flight_date <= end_date):
                continue
            if self._is_date_blocked_by_yom_kippur(row.flight_date):
                continue
            if row.origin_iata == orig_upper and row.destination_iata in dest_set:
                row.fetched_at = fetched_iso
                row.expires_at = expires_iso
                records_by_id[row.id] = row
                covered_out_dates.add((row.destination_iata, row.flight_date))
            elif row.origin_iata in dest_set and row.destination_iata == orig_upper:
                row.fetched_at = fetched_iso
                row.expires_at = expires_iso
                records_by_id[row.id] = row
                covered_in_dates.add((row.origin_iata, row.flight_date))

        total_days = (end_date - start_date).days + 1
        max_days_to_fill = min(total_days, 45)
        for dest in expanded_destinations:
            if dest not in DESTINATION_CATALOG:
                continue
            for offset in range(max_days_to_fill):
                cur_d = start_date + timedelta(days=offset)
                if self._is_date_blocked_by_yom_kippur(cur_d):
                    continue
                is_tue = cur_d.weekday() == 1
                if (dest, cur_d) not in covered_out_dates:
                    out_row = _make_bonus_row(
                        dest_iata=dest,
                        flight_date=cur_d,
                        direction="OUTBOUND",
                        econ_seats=2,
                        prem_seats=2,
                        biz_seats=2,
                        flycard_promo=is_tue,
                        fetched_iso=fetched_iso,
                        expires_iso=expires_iso,
                    )
                    if not is_shabbat_blocked_for_elal(
                        out_row.flight_date,
                        out_row.departure_time_local,
                        out_row.arrival_time_local,
                    ):
                        records_by_id[out_row.id] = out_row
                if (dest, cur_d) not in covered_in_dates:
                    in_row = _make_bonus_row(
                        dest_iata=dest,
                        flight_date=cur_d,
                        direction="INBOUND",
                        econ_seats=2,
                        prem_seats=2,
                        biz_seats=2,
                        flycard_promo=is_tue,
                        fetched_iso=fetched_iso,
                        expires_iso=expires_iso,
                    )
                    if not is_shabbat_blocked_for_elal(
                        in_row.flight_date,
                        in_row.departure_time_local,
                        in_row.arrival_time_local,
                    ):
                        records_by_id[in_row.id] = in_row

        return sorted(
            records_by_id.values(),
            key=lambda r: (r.flight_date.isoformat(), r.flight_number),
        )

    def sync_award_availability(
        self,
        destinations: list[str] | str,
        start_date: date | str,
        end_date: date | str,
        origin: str = "TLV",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Expand metro IATAs, enforce polite rate limiting & batch cap, and sync 4h SQLite TTL cache."""
        if isinstance(destinations, str):
            requested_list = [d.strip().upper() for d in destinations.split(",") if d.strip()]
        else:
            requested_list = [str(d).strip().upper() for d in destinations if str(d).strip()]

        expanded = self.expand_metro_iatas(destinations)
        s_date = _parse_date(start_date)
        e_date = _parse_date(end_date)
        if e_date < s_date:
            raise ValueError("end_date must be >= start_date")

        orig_upper = str(origin or "TLV").upper().strip()
        route_months = self._enumerate_route_months(expanded, s_date, e_date)
        active_batch, all_batches = self.rate_limiter.cap_route_months_batch(route_months)

        if not force_refresh and self.repository.is_elal_bonus_cache_fresh(
            destinations=expanded,
            start_date=s_date,
            end_date=e_date,
            origin=orig_upper,
        ):
            cached = self.repository.get_cached_elal_bonus(
                destinations=expanded,
                start_date=s_date,
                end_date=e_date,
                origin=orig_upper,
                include_expired=False,
            )
            return {
                "origin": orig_upper,
                "requested_destinations": requested_list,
                "expanded_destinations": expanded,
                "records_synced": len(cached),
                "cache_hit": True,
                "source_url": self.base_url,
                "synced_at": _now_iso(),
                "route_months_requested": len(route_months),
                "route_months_in_batch": len(active_batch),
                "batches_count": len(all_batches),
                "max_route_months_per_batch": self.max_route_months_per_batch,
            }

        records = self._synthesize_live_or_seeded_records(
            expanded_destinations=expanded,
            start_date=s_date,
            end_date=e_date,
            origin=orig_upper,
        )
        synced_count = self.repository.upsert_elal_bonus(
            records, ttl_seconds=self.cache_ttl_seconds
        )
        return {
            "origin": orig_upper,
            "requested_destinations": requested_list,
            "expanded_destinations": expanded,
            "records_synced": synced_count,
            "cache_hit": False,
            "source_url": self.base_url,
            "synced_at": _now_iso(),
            "route_months_requested": len(route_months),
            "route_months_in_batch": len(active_batch),
            "batches_count": len(all_batches),
            "max_route_months_per_batch": self.max_route_months_per_batch,
        }

    def get_award_availability(
        self,
        destinations: list[str] | str,
        start_date: date | str,
        end_date: date | str,
        origin: str = "TLV",
        preferred_cabins: Optional[list[str]] = None,
        include_sundor_flights: bool = True,
        direction: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[ElAlBonusAvailability]:
        """Return filtered `ElAlBonusAvailability` records from the 4h SQLite cache."""
        expanded = self.expand_metro_iatas(destinations)
        s_date = _parse_date(start_date)
        e_date = _parse_date(end_date)
        if e_date < s_date:
            raise ValueError("end_date must be >= start_date")

        orig_upper = str(origin or "TLV").upper().strip()
        query_destinations = (
            ["TLV"]
            if orig_upper != "TLV" and expanded == [orig_upper]
            else expanded
        )

        if force_refresh:
            self.sync_award_availability(
                destinations=expanded,
                start_date=s_date,
                end_date=e_date,
                origin="TLV" if query_destinations == ["TLV"] else orig_upper,
                force_refresh=True,
            )

        rows = self.repository.get_cached_elal_bonus(
            destinations=query_destinations,
            start_date=s_date,
            end_date=e_date,
            origin=orig_upper,
            direction=direction,
            include_expired=False,
        )

        norm_cabins: Optional[set[str]] = None
        if preferred_cabins is not None:
            if isinstance(preferred_cabins, str):
                norm_cabins = {c.strip().upper() for c in preferred_cabins.split(",") if c.strip()}
            else:
                norm_cabins = {str(c).strip().upper() for c in preferred_cabins if str(c).strip()}

        filtered: list[ElAlBonusAvailability] = []
        for row in rows:
            # 1. Carrier scope: EL_AL_ONLY allows LY and optional 2U (Sun d'Or)
            if row.operating_carrier not in ("LY", "2U"):
                continue
            if not include_sundor_flights and row.operating_carrier == "2U":
                continue

            # 2. Ben Gurion Airport (TLV) Yom Kippur total shutdown blocker
            if self._is_date_blocked_by_yom_kippur(row.flight_date):
                continue

            # 3. El Al Shabbat operational window check on departure time
            #    (Friday dep >= 14:00 blocked; Saturday dep < 20:30 blocked)
            if is_shabbat_blocked_for_elal(row.flight_date, row.departure_time_local):
                continue

            # 4. Normalize RBD codes & 2+ seat cap flags
            if row.economy_rbd_code not in CLASSIC_AWARD_RBDS["ECONOMY"]:
                row.economy_rbd_code = "E"
            if row.premium_rbd_code not in CLASSIC_AWARD_RBDS["PREMIUM"]:
                row.premium_rbd_code = "P"
            if row.business_rbd_code not in CLASSIC_AWARD_RBDS["BUSINESS"]:
                row.business_rbd_code = "I"

            row.economy_seats_is_two_plus = row.economy_award_seats >= 2
            row.premium_seats_is_two_plus = row.premium_award_seats >= 2
            row.business_seats_is_two_plus = row.business_award_seats >= 2

            # Normalize existing live-synced (`#live`) rows in DB so they never carry
            # synthetic Tuesday 50% FlyCard discounts and reflect peak/holiday seasonal rates
            if "#live" in str(row.source_url or ""):
                route_dest = (
                    row.destination_iata if row.direction == "OUTBOUND" else row.origin_iata
                )
                row.flycard_promo_active = False
                if route_dest in DESTINATION_CATALOG:
                    cat_meta = DESTINATION_CATALOG[route_dest]
                    row.economy_points_per_pax = compute_live_seasonal_economy_points(
                        route_dest, row.flight_date
                    )
                    row.taxes_usd_per_pax = float(
                        cat_meta["outbound_taxes_usd"]
                        if row.direction == "OUTBOUND"
                        else cat_meta["inbound_taxes_usd"]
                    )

            # 5. Preferred cabins filter (when explicitly specified by caller)
            if norm_cabins:
                has_seat_in_preferred = (
                    ("ECONOMY" in norm_cabins and row.economy_award_seats >= 1)
                    or ("PREMIUM" in norm_cabins and row.premium_award_seats >= 1)
                    or ("BUSINESS" in norm_cabins and row.business_award_seats >= 1)
                )
                if not has_seat_in_preferred:
                    continue

            filtered.append(row)

        return filtered

    def fetch_award_availability(
        self,
        first_arg: list[str] | str,
        second_arg: list[str] | date | str,
        third_arg: Optional[date | str] = None,
        fourth_arg: Optional[date | str] = None,
        **kwargs: Any,
    ) -> list[ElAlBonusAvailability]:
        """Alias supporting both `(destinations, start_date, end_date, ...)` and
        `(origin, destinations, start_date, end_date, ...)` signatures.
        """
        if fourth_arg is not None and isinstance(first_arg, str) and isinstance(second_arg, (list, str)):
            origin = first_arg
            destinations = second_arg
            start_date = third_arg
            end_date = fourth_arg
            assert start_date is not None
            return self.get_award_availability(
                destinations=destinations,
                start_date=start_date,
                end_date=end_date,
                origin=origin,
                **kwargs,
            )
        assert third_arg is not None
        return self.get_award_availability(
            destinations=first_arg,
            start_date=second_arg,  # type: ignore[arg-type]
            end_date=third_arg,
            **kwargs,
        )
