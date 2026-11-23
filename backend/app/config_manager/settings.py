"""Application settings loader for family_vacation_planner.

Loads `config/settings.yaml` and merges optional environment variables
(`VACATION_PLANNER_DB_PATH`, `SERPAPI_API_KEY`, `DUFFEL_ACCESS_TOKEN`).
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "vacation_planner.db"

DEFAULT_SETTINGS: dict[str, Any] = {
    "app": {
        "default_origin_iata": "TLV",
        "default_currency": "USD",
        "supported_currencies": ["USD", "ILS", "EUR"],
        "locale_default": "he-IL",
        "default_db_path": "data/vacation_planner.db",
    },
    "elal_rbd_client": {
        "base_url": "https://www.elal.com/rbddataclients/",
        "cache_ttl_seconds": 14400,
        "itinerary_cache_ttl_seconds": 21600,
        "rate_limit_min_interval_sec": 2.0,
        "rate_limit_jitter_sec": [1.5, 3.5],
        "max_route_months_per_batch": 15,
        "metro_iata_expansion": {
            "NYC": ["JFK", "EWR"],
            "LON": ["LHR", "LTN"],
            "PAR": ["CDG"],
            "MIL": ["MXP"],
            "ROM": ["FCO"],
            "TYO": ["NRT"],
            "MIA_AREA": ["MIA", "FLL"],
        },
    },
    "optimization_weights": {
        "ctos_calendar_weight": 0.55,
        "ctos_flight_weight": 0.45,
        "ctos_filtered_weather_weight": 0.35,
        "ctos_filtered_calendar_weight": 0.35,
        "ctos_filtered_flight_weight": 0.30,
        "ctos_sub_threshold_penalty_factor": 0.50,
        "default_min_weather_suitability_score": 55.0,
    },
    "framework_criticality_weights": {
        "DAYCARE_SUPERVISED": 0.25,
        "MUNICIPAL_GAN": 0.25,
        "ELEMENTARY_1_3": 0.50,
        "ELEMENTARY_4_6": 0.75,
        "MIDDLE_SCHOOL_7_9": 1.00,
        "HIGH_SCHOOL_10_12": 1.35,
        "SPECIAL_ED": 0.50,
        "RELIGIOUS_HAREDI": 1.00,
    },
    "daily_state_penalties": {
        "VACATION": 0.00,
        "WEEKEND": 0.00,
        "CAMP_OPTIONAL_AS_VACATION": 0.15,
        "CAMP_OPTIONAL_AS_CHILDCARE": 0.75,
        "SCHOOL_FRIDAY": 0.35,
        "SCHOOL_END_OF_YEAR_WANING": 0.50,
        "SCHOOL_REGULAR": 1.00,
        "EXAM_BLACKOUT": 999999.0,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = copy.deepcopy(val)
    return merged


def resolve_db_path(explicit_db_path: Optional[str | Path] = None) -> str:
    """Resolve SQLite database path from explicit arg, env var, or default."""
    if explicit_db_path is not None:
        raw = str(explicit_db_path)
        if raw == ":memory:":
            return raw
        return str(Path(raw).expanduser().resolve())
    env_path = os.environ.get("VACATION_PLANNER_DB_PATH")
    if env_path:
        if env_path == ":memory:":
            return env_path
        return str(Path(env_path).expanduser().resolve())
    return str(DEFAULT_DB_PATH.resolve())


def get_settings(config_path: Optional[str | Path] = None) -> dict[str, Any]:
    """Load application settings from `config/settings.yaml` with fallback defaults."""
    target_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if target_path.exists():
        with target_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                settings = _deep_merge(settings, loaded)

    settings["resolved_db_path"] = resolve_db_path()
    settings["env"] = {
        "SERPAPI_API_KEY": os.environ.get("SERPAPI_API_KEY", ""),
        "DUFFEL_ACCESS_TOKEN": os.environ.get("DUFFEL_ACCESS_TOKEN", ""),
        "VACATION_PLANNER_DB_PATH": os.environ.get("VACATION_PLANNER_DB_PATH", ""),
        "PUBLIC_BASE_URL": os.environ.get("PUBLIC_BASE_URL", ""),
        "GOOGLE_OAUTH_CLIENT_ID": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        "GOOGLE_OAUTH_CLIENT_SECRET": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "GOOGLE_OAUTH_REDIRECT_URI": os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", ""),
        "GOOGLE_OAUTH_ALLOWED_DOMAINS": os.environ.get(
            "GOOGLE_OAUTH_ALLOWED_DOMAINS", "gmail.com,googlemail.com"
        ),
        "SESSION_TTL_SECONDS": os.environ.get("SESSION_TTL_SECONDS", "1209600"),
    }
    return settings


@dataclass
class AppSettings:
    """Structured wrapper around application configuration."""

    raw: dict[str, Any] = field(default_factory=get_settings)

    @property
    def default_origin_iata(self) -> str:
        return str(self.raw.get("app", {}).get("default_origin_iata", "TLV"))

    @property
    def default_currency(self) -> str:
        return str(self.raw.get("app", {}).get("default_currency", "USD"))

    @property
    def supported_currencies(self) -> list[str]:
        return list(self.raw.get("app", {}).get("supported_currencies", ["USD", "ILS", "EUR"]))

    @property
    def db_path(self) -> str:
        return resolve_db_path()

    @property
    def metro_iata_expansion(self) -> dict[str, list[str]]:
        return dict(self.raw.get("elal_rbd_client", {}).get("metro_iata_expansion", {}))

    @property
    def cache_ttl_seconds(self) -> int:
        return int(self.raw.get("elal_rbd_client", {}).get("cache_ttl_seconds", 14400))

    @property
    def itinerary_cache_ttl_seconds(self) -> int:
        return int(self.raw.get("elal_rbd_client", {}).get("itinerary_cache_ttl_seconds", 21600))

    @property
    def optimization_weights(self) -> dict[str, float]:
        return dict(self.raw.get("optimization_weights", DEFAULT_SETTINGS["optimization_weights"]))

    @property
    def framework_criticality_weights(self) -> dict[str, float]:
        return dict(
            self.raw.get(
                "framework_criticality_weights",
                DEFAULT_SETTINGS["framework_criticality_weights"],
            )
        )

    @property
    def daily_state_penalties(self) -> dict[str, float]:
        return dict(self.raw.get("daily_state_penalties", DEFAULT_SETTINGS["daily_state_penalties"]))

    @property
    def public_base_url(self) -> str:
        return str(os.environ.get("PUBLIC_BASE_URL") or self.raw.get("env", {}).get("PUBLIC_BASE_URL", "")).strip()

    @property
    def google_oauth_client_id(self) -> str:
        return str(os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or self.raw.get("env", {}).get("GOOGLE_OAUTH_CLIENT_ID", "")).strip()

    @property
    def google_oauth_client_secret(self) -> str:
        return str(os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or self.raw.get("env", {}).get("GOOGLE_OAUTH_CLIENT_SECRET", "")).strip()

    @property
    def google_oauth_redirect_uri(self) -> str:
        return str(os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or self.raw.get("env", {}).get("GOOGLE_OAUTH_REDIRECT_URI", "")).strip()

    @property
    def session_ttl_seconds(self) -> int:
        raw_val = os.environ.get("SESSION_TTL_SECONDS") or self.raw.get("env", {}).get("SESSION_TTL_SECONDS", "1209600")
        try:
            return max(60, int(str(raw_val).strip()))
        except ValueError:
            return 1209600

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.raw)


def load_settings(config_path: Optional[str | Path] = None) -> AppSettings:
    """Return an `AppSettings` instance loaded from `config_path`."""
    return AppSettings(raw=get_settings(config_path))
