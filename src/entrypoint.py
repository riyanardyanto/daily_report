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
    page.padding = 8
    page.theme = ft.Theme(font_family="Verdana")
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme.page_transitions.windows = "cupertino"
    page.fonts = {"Pacifico": "Pacifico-Regular.ttf"}
    # Softer neutral background improves contrast and reduces visual noise.
    page.bgcolor = ft.Colors.BLUE_GREY_50

    ctx = build_context(page, logger_name="daily_report")
    dashboard = DashboardApp(page, ctx=ctx)
    page.add(dashboard)

    def _on_resize(_e=None):
        try:
            dashboard.apply_responsive_layout(getattr(page, "width", None))
        except Exception:
            pass

    # Keep the dashboard responsive.
    page.on_resize = safe_event(_on_resize, label="page.on_resize")

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
