from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import flet as ft


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

    # Close existing dialog if present to reduce "sometimes doesn't show" cases.
    try:
        existing = getattr(page, "dialog", None)
        if existing is not None and getattr(existing, "open", False):
            existing.open = False
            try:
                page.update()
            except Exception:
                pass
    except Exception:
        pass

    try:
        page.open(dlg)
        return True
    except Exception as ex_open:
        # Fall back to the older API style.
        try:
            page.dialog = dlg
            dlg.open = True
            page.update()
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


def is_file_locked_windows(path: str | Path) -> bool:
    """Return True if the file is locked by another process (Windows only, best-effort).

    Detects classic Excel locks by attempting to open the file with share mode = 0.
    On non-Windows platforms this returns False.
    """
    try:
        if sys.platform != "win32":
            return False

        p = Path(path)
        if not p.exists():
            return False

        import ctypes

        GENERIC_READ = 0x80000000
        FILE_SHARE_NONE = 0
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        CreateFileW = ctypes.windll.kernel32.CreateFileW
        CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        CreateFileW.restype = ctypes.c_void_p

        handle = CreateFileW(
            str(p),
            GENERIC_READ,
            FILE_SHARE_NONE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )

        if handle == INVALID_HANDLE_VALUE or handle is None:
            err = ctypes.windll.kernel32.GetLastError()
            # 32=sharing violation, 33=lock violation
            return err in (32, 33)

        try:
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass

        return False
    except Exception:
        return False
