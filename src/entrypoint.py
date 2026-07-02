from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

from src.app import DashboardApp
from src.core.context import build_context
from src.core.safe import safe_event
from src.utils.helpers import (
    ensure_portable_targets_seeded,
    get_data_app_dir,
    resource_path,
)


def _main(page: ft.Page) -> None:
    page.title = "Daily Report Dashboard"
    page.window.icon = "icon_windows.ico"
    # Use a small global padding so content doesn't hug the window edges.
    page.padding = 10
    # Inter is a modern, highly readable UI font. Falls back to Segoe UI on Windows.
    page.fonts = {
        "Pacifico": "Pacifico-Regular.ttf",
        "Inter": "https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuLyfAZ9hiJ-Ek-_EeA.woff2",
    }
    page.theme = ft.Theme(font_family="Inter")
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme.page_transitions.windows = "cupertino"
    # Slate-100 background — softer than white, less eye strain.
    page.bgcolor = "#F1F5F9"

    ctx = build_context(page, logger_name="daily_report")
    dashboard = DashboardApp(page, ctx=ctx)
    page.add(dashboard)

    def _on_resize(_e=None):
        try:
            if getattr(page.window, "minimized", False):
                return
            if page.width == 0 or page.height == 0:
                return
            dashboard.apply_responsive_layout(getattr(page, "width", None))
        except Exception:
            pass

    # Keep the dashboard responsive.
    page.on_resize = safe_event(_on_resize, label="page.on_resize")

    def _on_window_event(e):
        try:
            event_type = str(getattr(e, "data", "") or "").lower()
            # Close any active card menu dialog before the window loses its render surface.
            # This prevents the Flutter overlay route from hanging mid-animation,
            # which causes the blank/white screen on Windows desktop.
            if event_type in ("blur", "minimize"):
                try:
                    report_list = dashboard.report_editor.report_list
                    report_list.close_active_menu()
                except Exception:
                    pass
            # Force a repaint when the window comes back into focus or is restored.
            if event_type in ("restore", "focus"):
                page.update()
        except Exception:
            pass

    try:
        page.window.on_event = safe_event(_on_window_event, label="page.window.on_event")
    except Exception:
        pass

    def _on_disconnect(_e=None):
        try:
            if hasattr(dashboard, "report_editor"):
                dashboard.report_editor._stop_marquee()
        except Exception:
            pass

    # Best-effort: stop background UI tasks when the client disconnects.
    try:
        if hasattr(page, "on_disconnect"):
            page.on_disconnect = safe_event(_on_disconnect, label="page.on_disconnect")
    except Exception:
        pass

    _on_resize()
    page.update()


def _get_assets_dir() -> str:
    # When frozen by PyInstaller and built with:
    #   --add-data "src\assets;src\assets"
    # assets will be available under sys._MEIPASS/src/assets.
    if getattr(sys, "frozen", False):
        return str(resource_path("src/assets"))
    return str(Path(__file__).resolve().parent / "assets")


def run() -> None:
    import flet as ft

    # Ensure portable folders exist next to the exe.
    try:
        get_data_app_dir(folder_name="data_app/log")
        get_data_app_dir(folder_name="data_app/settings")
        get_data_app_dir(folder_name="data_app/targets")
        ensure_portable_targets_seeded()
    except Exception:
        pass

    ft.app(target=_main, assets_dir=_get_assets_dir())
