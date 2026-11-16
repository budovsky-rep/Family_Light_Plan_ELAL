"""Configuration management package."""

from backend.app.config_manager.settings import (
    AppSettings,
    DEFAULT_SETTINGS,
    PROJECT_ROOT,
    get_settings,
    load_settings,
    resolve_db_path,
)

__all__ = [
    "AppSettings",
    "DEFAULT_SETTINGS",
    "PROJECT_ROOT",
    "get_settings",
    "load_settings",
    "resolve_db_path",
]
