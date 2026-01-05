from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

from src.app import DashboardApp
from src.utils.helpers import get_data_app_dir, resource_path


def _main(page: ft.Page) -> None:


    page.title = "Daily Report Dashboard"
    page.window.icon = "icon_windows.ico"
    page.padding = 0
    page.theme = ft.Theme(font_family="Verdana")
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme.page_transitions.windows = "cupertino"
    page.fonts = {"Pacifico": "Pacifico-Regular.ttf"}
    page.bgcolor = ft.Colors.BLUE_GREY_200

    dashboard = DashboardApp()
    page.add(dashboard)
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

    # Ensure app-data folder exists next to script/exe.
    try:
        get_data_app_dir()
    except Exception:
        pass

    ft.app(target=_main, assets_dir=_get_assets_dir())
