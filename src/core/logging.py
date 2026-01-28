from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from src.utils.helpers import data_app_path

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _SuppressAsyncioSocketSendWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.name == "asyncio":
                msg = record.getMessage()
                if "socket.send() raised exception" in msg:
                    return False

                # Flet/asyncio shutdown noise on Windows (harmless but confusing).
                if "Exception in callback BaseEventLoop.run_in_executor" in msg:
                    exc = None
                    if getattr(record, "exc_info", None):
                        exc = record.exc_info[1]
                    if isinstance(
                        exc, RuntimeError
                    ) and "cannot schedule new futures after shutdown" in str(exc):
                        return False
        except Exception:
            # Never break logging due to filter errors.
            return True
        return True


def _ensure_filters(logger: logging.Logger) -> None:
    """Attach global filters to all handlers (idempotent best-effort)."""

    for h in list(logger.handlers):
        try:
            if any(
                isinstance(f, _SuppressAsyncioSocketSendWarning)
                for f in getattr(h, "filters", [])
            ):
                continue
            h.addFilter(_SuppressAsyncioSocketSendWarning())
        except Exception:
            pass


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
            _ensure_filters(root)
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

        _ensure_filters(root)
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
