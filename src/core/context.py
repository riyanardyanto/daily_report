from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from src.core.logging import get_logger
from src.services.config_service import (
    ApplicationConfig,
    SpaServiceConfig,
    UiConfig,
    get_application_config,
    get_spa_service_config,
    get_ui_config,
)
from src.utils.ui_helpers import open_dialog, snack


@dataclass(slots=True)
class AppContext:
    """Shared application context.

    Keeping this small helps avoid hard coupling across components.
    """

    page: ft.Page
    ui: UiConfig
    app: ApplicationConfig
    spa: SpaServiceConfig
    logger_name: str = "daily_report"

    @property
    def logger(self):
        return get_logger(self.logger_name)

    def toast(self, message: str, *, kind: str | None = None) -> None:
        snack(self.page, message, kind=kind)

    def dialog(self, dlg: ft.AlertDialog) -> bool:
        return open_dialog(self.page, dlg)


def build_context(page: ft.Page, *, logger_name: str = "daily_report") -> AppContext:
    ui_cfg, _ui_err = get_ui_config()
    app_cfg, _app_err = get_application_config()
    spa_cfg, _spa_err = get_spa_service_config()
    return AppContext(
        page=page, ui=ui_cfg, app=app_cfg, spa=spa_cfg, logger_name=logger_name
    )
