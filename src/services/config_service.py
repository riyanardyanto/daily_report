from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.helpers import data_app_path

DEFAULT_CONFIG_TOML = """[APPLICATION]
environment = "production"

[UI]
# Performance-related UI settings
# - history_max_rows: limits how many latest history rows are rendered in the History dialog
# - qr_cache_size: number of QR payloads cached in memory to speed up repeated opens
# - spa_cache_ttl_seconds: cache TTL for Get Data results (same inputs) to speed repeated clicks
history_max_rows = 500
qr_cache_size = 20
spa_cache_ttl_seconds = 15

[SPA_SERVICE]
username = ""
password = ""
base_url = "https://ots.spappa.aws.private-pmideep.biz/db.aspx?"
verify_ssl = false
timeout = 30

[HISTORY_SYNC]
# Optional: force sync JSON folder (shared path for all PCs).
# If left empty, the packaged .exe defaults to using `<exe_dir>/sync`.
# Recommended for multi-PC deployments. Example (UNC):
# sync_dir = "\\\\SERVER\\Share\\DailyReportSync"
sync_dir = ""

# Cleanup/retention for sync JSON files in the shared folder.
# - retention_days: archive (move) files older than N days into `archive/`.
# - keep_latest_fullsync: keep N newest fullsync_*.json files for onboarding.
retention_days = 30
keep_latest_fullsync = 1

[HISTORY_STORAGE]
# Storage mode for history DB:
# - "local_sync" (default): per-PC local SQLite + JSON sync folder (recommended for shared folders)
# - "shared_sqlite": directly read/write a single SQLite file in a shared folder (NOT recommended)
#
# If you choose shared_sqlite, set shared_db_path to a UNC or shared path.
# Example:
# shared_db_path = "\\\\SERVER\\Share\\DailyReport\\history.db"
mode = "local_sync"
shared_db_path = ""
"""


def get_config_path() -> Path:
    # Stored under: data_app/settings/config.toml
    return data_app_path("config.toml", folder_name="data_app/settings")


def ensure_default_config() -> tuple[Path, bool, str | None]:
    """Ensure config.toml exists; create with defaults if missing.

    Returns:
        (path, created_template, error_message)
    """
    path = get_config_path()
    if path.exists():
        return path, False, None

    # Migration: older versions stored config under per-user AppData.
    # If the new portable config (next to exe) is missing but the legacy one exists,
    # copy it once to preserve user settings.
    try:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            legacy = (
                Path(base) / "Daily Report" / "data_app" / "settings" / "config.toml"
            )
            if legacy.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy, path)
                return path, True, None
    except Exception:
        pass

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
        return path, True, None
    except Exception as ex:
        return path, False, str(ex)


def _toml_loads(text: str) -> dict[str, Any]:
    """Parse TOML into a python dict.

    Uses stdlib `tomllib` when available; falls back to `tomli`.
    """
    try:
        import tomllib  # py>=3.11

        return tomllib.loads(text)
    except ModuleNotFoundError:
        import tomli  # type: ignore

        return tomli.loads(text)


def load_config_toml() -> tuple[dict[str, Any], Path, str | None]:
    """Load the application config TOML from data_app/settings/config.toml.

    Returns:
        (config_dict, path, error_message)
    """
    path, _created, err = ensure_default_config()
    if err:
        return {}, path, err

    try:
        raw = path.read_text(encoding="utf-8-sig")
        return _toml_loads(raw or ""), path, None
    except Exception as ex:
        return {}, path, str(ex)


@dataclass(frozen=True)
class SpaServiceConfig:
    username: str = ""
    password: str = ""
    base_url: str = ""
    verify_ssl: bool = False
    timeout: int = 30


@dataclass(frozen=True)
class ApplicationConfig:
    environment: str = "production"


@dataclass(frozen=True)
class UiConfig:
    history_max_rows: int = 500
    qr_cache_size: int = 20
    spa_cache_ttl_seconds: int = 15


@dataclass(frozen=True)
class HistorySyncConfig:
    sync_dir: str = ""
    retention_days: int = 30
    keep_latest_fullsync: int = 1


@dataclass(frozen=True)
class HistoryStorageConfig:
    mode: str = "local_sync"
    shared_db_path: str = ""


def get_history_storage_config() -> tuple[HistoryStorageConfig, str | None]:
    """Read history storage selection from [HISTORY_STORAGE].

    Env overrides (recommended for deployment):
    - DAILY_REPORT_HISTORY_MODE: "local_sync" or "shared_sqlite"
    - DAILY_REPORT_SHARED_DB_PATH: absolute path/UNC to history.db
    """

    # Env overrides first
    env_mode = str(os.environ.get("DAILY_REPORT_HISTORY_MODE", "") or "").strip()
    env_shared = str(os.environ.get("DAILY_REPORT_SHARED_DB_PATH", "") or "").strip()

    cfg, _path, err = load_config_toml()
    if err:
        # Even if config fails, honor env overrides.
        return (
            HistoryStorageConfig(
                mode=(env_mode or "local_sync"),
                shared_db_path=env_shared,
            ),
            err,
        )

    sec = cfg.get("HISTORY_STORAGE") if isinstance(cfg, dict) else None
    if not isinstance(sec, dict):
        sec = {}

    def _s(key: str, default: str = "") -> str:
        try:
            return str(sec.get(key, default) or "").strip()
        except Exception:
            return default

    mode = (env_mode or _s("mode", "local_sync") or "local_sync").strip().lower()
    if mode not in ("local_sync", "shared_sqlite"):
        mode = "local_sync"

    shared_db_path = (env_shared or _s("shared_db_path", "")).strip()

    return HistoryStorageConfig(mode=mode, shared_db_path=shared_db_path), None


def get_history_sync_config() -> tuple[HistorySyncConfig, str | None]:
    """Read sync/cleanup settings from [HISTORY_SYNC] section."""
    cfg, _path, err = load_config_toml()
    if err:
        return HistorySyncConfig(), err

    sec = cfg.get("HISTORY_SYNC") if isinstance(cfg, dict) else None
    if not isinstance(sec, dict):
        sec = {}

    def _s(key: str, default: str = "") -> str:
        try:
            return str(sec.get(key, default) or "").strip()
        except Exception:
            return default

    def _i(key: str, default: int) -> int:
        try:
            v = sec.get(key, default)
            return int(v)
        except Exception:
            return default

    retention_days = _i("retention_days", 30)
    keep_latest_fullsync = _i("keep_latest_fullsync", 1)

    # Clamp to safe ranges
    if retention_days <= 0:
        retention_days = 30
    if retention_days > 3650:
        retention_days = 3650

    if keep_latest_fullsync < 0:
        keep_latest_fullsync = 0
    if keep_latest_fullsync > 20:
        keep_latest_fullsync = 20

    return (
        HistorySyncConfig(
            sync_dir=_s("sync_dir", ""),
            retention_days=retention_days,
            keep_latest_fullsync=keep_latest_fullsync,
        ),
        None,
    )


def get_ui_config() -> tuple[UiConfig, str | None]:
    """Read UI-related config values from [UI] section in config.toml."""
    cfg, _path, err = load_config_toml()
    if err:
        return UiConfig(), err

    ui = cfg.get("UI") if isinstance(cfg, dict) else None
    if not isinstance(ui, dict):
        ui = {}

    def _i(key: str, default: int) -> int:
        try:
            v = ui.get(key, default)
            return int(v)
        except Exception:
            return default

    history_max_rows = _i("history_max_rows", 500)
    qr_cache_size = _i("qr_cache_size", 20)
    spa_cache_ttl_seconds = _i("spa_cache_ttl_seconds", 15)

    # Clamp to sensible ranges (prevents accidental huge values)
    if history_max_rows <= 0:
        history_max_rows = 500
    if history_max_rows > 20000:
        history_max_rows = 20000

    if qr_cache_size < 0:
        qr_cache_size = 0
    if qr_cache_size > 200:
        qr_cache_size = 200

    if spa_cache_ttl_seconds < 0:
        spa_cache_ttl_seconds = 0
    if spa_cache_ttl_seconds > 600:
        spa_cache_ttl_seconds = 600

    return UiConfig(
        history_max_rows=history_max_rows,
        qr_cache_size=qr_cache_size,
        spa_cache_ttl_seconds=spa_cache_ttl_seconds,
    ), None


def get_application_config() -> tuple[ApplicationConfig, str | None]:
    cfg, _path, err = load_config_toml()
    if err:
        return ApplicationConfig(), err

    app = cfg.get("APPLICATION") if isinstance(cfg, dict) else None
    if not isinstance(app, dict):
        app = {}

    try:
        env = str(app.get("environment", "production") or "production").strip()
    except Exception:
        env = "production"

    return ApplicationConfig(environment=env or "production"), None


def get_spa_service_config() -> tuple[SpaServiceConfig, str | None]:
    cfg, _path, err = load_config_toml()
    if err:
        return SpaServiceConfig(), err

    spa = cfg.get("SPA_SERVICE") if isinstance(cfg, dict) else None
    if not isinstance(spa, dict):
        spa = {}

    def _s(key: str) -> str:
        try:
            return str(spa.get(key, "") or "").strip()
        except Exception:
            return ""

    def _b(key: str, default: bool = False) -> bool:
        try:
            v = spa.get(key, default)
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            s = str(v or "").strip().lower()
            if s in ("true", "1", "yes", "y", "on"):
                return True
            if s in ("false", "0", "no", "n", "off"):
                return False
            return default
        except Exception:
            return default

    def _i(key: str, default: int = 30) -> int:
        try:
            v = spa.get(key, default)
            return int(v)
        except Exception:
            return default

    return (
        SpaServiceConfig(
            username=_s("username"),
            password=_s("password"),
            base_url=_s("base_url"),
            verify_ssl=_b("verify_ssl", False),
            timeout=_i("timeout", 30),
        ),
        None,
    )
