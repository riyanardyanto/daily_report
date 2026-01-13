from __future__ import annotations

import asyncio
from typing import Any

import flet as ft

from src.utils.file_lock import is_file_locked_windows


def resolve_page(e: Any | None = None, fallback: Any | None = None) -> Any | None:
    """Best-effort resolver untuk mendapatkan `page` dari event Flet.

    Urutan pencarian:
    - e.page
    - e.control.page
    - fallback

    Return:
        page atau None
    """

    try:
        page = getattr(e, "page", None)
        if page is not None:
            return page
    except Exception:
        pass

    try:
        page = getattr(getattr(e, "control", None), "page", None)
        if page is not None:
            return page
    except Exception:
        pass

    return fallback


def open_dialog(page: Any, dlg: ft.AlertDialog) -> bool:
    """Open an AlertDialog in a best-effort, non-silent way.

    Why this exists:
    - In some edge cases `page.open()` may throw (page not ready / disposed /
      a previous dialog still open).
    - Some callers previously swallowed exceptions, making the UI appear to do
      nothing.

    Behavior:
    - Closes any currently-open `page.dialog` (best-effort).
    - Tries `page.open(dlg)` first, then falls back to setting `page.dialog`.
    - If both fail, it emits a SnackBar (when possible) and prints the error.

    Returns:
        True if a dialog open attempt was made successfully, else False.
    """

    if page is None or dlg is None:
        return False

    def _mount_dialog_on_page() -> None:
        # Prefer mounting on overlay to ensure the control gets a UID.
        try:
            overlay = getattr(page, "overlay", None)
            if isinstance(overlay, list) and dlg not in overlay:
                overlay.append(dlg)
        except Exception:
            pass

        # Keep compatibility with older patterns.
        try:
            page.dialog = dlg
        except Exception:
            pass

    def _close_existing_dialogs() -> None:
        # Best-effort: close current dialog + any open AlertDialog in overlay.
        try:
            existing = getattr(page, "dialog", None)
            if (
                existing is not None
                and existing is not dlg
                and getattr(existing, "open", False)
            ):
                existing.open = False
        except Exception:
            pass

        try:
            overlay = getattr(page, "overlay", None)
            if isinstance(overlay, list):
                for c in list(overlay):
                    if c is None or c is dlg:
                        continue
                    try:
                        if isinstance(c, ft.AlertDialog) and getattr(c, "open", False):
                            c.open = False
                    except Exception:
                        pass
        except Exception:
            pass

    def _try_open_now() -> None:
        _close_existing_dialogs()
        _mount_dialog_on_page()
        try:
            dlg.open = True
        except Exception:
            pass

        # Update page (not dlg) so Flet can assign UIDs.
        page.update()

    try:
        _try_open_now()
        return True
    except Exception as ex_open:
        # Flet can throw AssertionError when a control has not been mounted yet
        # (e.g., called during early startup). Do a one-shot retry on the next loop tick.
        try:
            run_task = getattr(page, "run_task", None)
            if callable(run_task):

                async def _retry_once():
                    try:
                        await asyncio.sleep(0)
                        _try_open_now()
                    except Exception:
                        pass

                run_task(_retry_once())
                return True
        except Exception:
            pass

        # Last resort: try the native API.
        try:
            page.open(dlg)
            return True
        except Exception as ex_fallback:
            msg = (
                "Failed to open dialog "
                f"(open={type(ex_open).__name__}: {ex_open!r}; "
                f"fallback={type(ex_fallback).__name__}: {ex_fallback!r})"
            )
            try:
                snack(page, msg, kind="error")
            except Exception:
                pass
            try:
                import traceback

                print(msg)
                traceback.print_exc()
            except Exception:
                pass
            return False


def _snack_style(message: Any, kind: str | None) -> tuple[str, str]:
    """Return (bgcolor, text_color) for a snackbar."""
    try:
        normalized_kind = str(kind or "").strip().lower()
    except Exception:
        normalized_kind = ""

    if normalized_kind in ("success", "ok", "green"):
        return ft.Colors.GREEN_600, ft.Colors.WHITE
    if normalized_kind in ("error", "err", "fail", "failed", "red"):
        return ft.Colors.RED_600, ft.Colors.WHITE
    if normalized_kind in ("warning", "warn", "yellow"):
        return ft.Colors.AMBER_400, ft.Colors.BLACK

    # Backwards-compatible auto-detection from message
    msg = ""
    try:
        msg = str(message or "")
    except Exception:
        msg = ""

    msg_l = msg.lower()
    if any(k in msg_l for k in ("gagal", "error", "failed", "exception", "traceback")):
        return ft.Colors.RED_600, ft.Colors.WHITE
    if any(
        k in msg_l for k in ("warning", "peringatan", "locked", "dibuka", "tidak ada")
    ):
        return ft.Colors.AMBER_400, ft.Colors.BLACK
    return ft.Colors.GREEN_600, ft.Colors.WHITE


def snack(page: Any, message: str, kind: str | None = None) -> None:
    """Show a SnackBar message (best-effort).

    Uses page.overlay to increase the chance the SnackBar is rendered.
    """
    try:
        bgcolor, text_color = _snack_style(message, kind)
        sb = ft.SnackBar(
            ft.Text(str(message), color=text_color),
            bgcolor=bgcolor,
        )
        try:
            page.snack_bar = sb
        except Exception:
            pass

        try:
            overlay = getattr(page, "overlay", None)
            if isinstance(overlay, list) and sb not in overlay:
                overlay.append(sb)
        except Exception:
            pass

        try:
            sb.open = True
        except Exception:
            try:
                page.snack_bar.open = True
            except Exception:
                pass

        try:
            page.update()
        except Exception:
            pass
    except Exception:
        # Never crash UI thread for a toast
        pass


__all__ = [
    "resolve_page",
    "open_dialog",
    "snack",
    "is_file_locked_windows",
]
