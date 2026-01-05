from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.helpers import data_app_path

DEFAULT_CONFIG_TOML = """[APPLICATION]
environment = "production"

[SPA_SERVICE]
username = ""
password = ""
base_url = "https://ots.spappa.aws.private-pmideep.biz/db.aspx?"
verify_ssl = false
timeout = 30
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


def get_spa_credentials(
    *,
    default_username: str = "",
    default_password: str = "",
) -> tuple[str, str, str | None]:
    """Convenience helper for SPA auth credentials.

    Returns:
        (username, password, error_message)
    """
    spa_cfg, err = get_spa_service_config()
    username = spa_cfg.username or str(default_username or "")
    password = spa_cfg.password or str(default_password or "")
    return username, password, err
