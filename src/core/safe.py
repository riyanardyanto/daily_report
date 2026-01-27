from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from src.core.logging import get_logger


def safe_event(
    handler: Callable[[Any], Any] | None,
    *,
    label: str,
    page: ft.Page | None = None,
    swallow: bool = True,
) -> Callable[[Any], Any]:
    """Wrap a Flet event handler with consistent exception logging.

    This reduces repetitive try/except pass blocks and makes failures visible.
    """

    logger = get_logger("ui")

    def _wrapped(e: Any) -> Any:
        if handler is None:
            return None
        try:
            return handler(e)
        except Exception:
            try:
                logger.exception("Unhandled exception in %s", label)
            except Exception:
                pass
            if not swallow:
                raise
            return None

    return _wrapped
