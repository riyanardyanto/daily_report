from __future__ import annotations

import asyncio
import traceback
from typing import Optional

from src.core.logging import get_logger
from src.utils.helpers import data_app_path


def capture_traceback() -> str:
    """Best-effort capture of the current exception traceback."""

    try:
        return traceback.format_exc()
    except Exception:
        return ""


def write_error_log_sync(
    text: str, *, log_filename: str = "error.log", folder_name: str = "data_app/log"
) -> None:
    """Append text to the application's error log."""

    if not text:
        return

    log_path = data_app_path(log_filename, folder_name=folder_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")
        f.write("\n")


async def write_error_log(
    text: str, *, log_filename: str = "error.log", folder_name: str = "data_app/log"
) -> None:
    """Async wrapper around write_error_log_sync."""

    await asyncio.to_thread(
        write_error_log_sync,
        text,
        log_filename=log_filename,
        folder_name=folder_name,
    )


async def report_exception(
    exc: Exception,
    *,
    where: str,
    env_lower: str,
    logger_name: str = "errors",
    traceback_text: Optional[str] = None,
) -> None:
    """Log exception to structured logs and (optionally) persist to error.log.

    - Always logs to the configured logger.
    - In production, also appends full traceback to data_app/log/error.log.
    - In non-production, prints traceback to stderr (best-effort) to aid dev.
    """

    logger = get_logger(logger_name)

    try:
        logger.exception("%s: %s", where, exc)
    except Exception:
        pass

    tb = traceback_text if traceback_text is not None else capture_traceback()

    if str(env_lower or "production").strip().lower() == "production":
        try:
            await write_error_log(tb)
        except Exception:
            pass
    else:
        try:
            # Keep dev experience similar to previous behavior.
            traceback.print_exc()
        except Exception:
            pass


def report_exception_sync(
    exc: Exception,
    *,
    where: str,
    env_lower: str,
    logger_name: str = "errors",
    traceback_text: Optional[str] = None,
) -> None:
    """Synchronous variant of report_exception().

    Use this from non-async code paths (e.g., blocking fallbacks) to avoid
    creating/running event loops.
    """

    logger = get_logger(logger_name)

    try:
        logger.exception("%s: %s", where, exc)
    except Exception:
        pass

    tb = traceback_text if traceback_text is not None else capture_traceback()

    if str(env_lower or "production").strip().lower() == "production":
        try:
            write_error_log_sync(tb)
        except Exception:
            pass
    else:
        try:
            traceback.print_exc()
        except Exception:
            pass
