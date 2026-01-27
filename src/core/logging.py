from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from src.utils.helpers import data_app_path

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _log_file_path() -> Path:
    # data_app/log/app.log
    return data_app_path("app.log", folder_name="data_app/log")


def configure_root_logging(*, level: int = logging.INFO) -> None:
    """Configure root logging (idempotent best-effort).

    Safe to call multiple times; it won't add duplicate handlers.
    """

    root = logging.getLogger()
    root.setLevel(level)

    for h in list(root.handlers):
        # If a file handler already exists, assume logging was configured.
        if isinstance(h, RotatingFileHandler):
            return

    try:
        log_path = _log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(handler)

        # Also emit to console during development.
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(console)
    except Exception:
        # Never block app startup due to logging.
        pass


def get_logger(name: str, *, level: int | None = None) -> logging.Logger:
    """Get a module/component logger, ensuring root logging is configured."""

    configure_root_logging()
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger
