from __future__ import annotations

import datetime

import flet as ft

from src.components.settings_dialog import SettingsDialog
from src.services.config_service import get_application_config
from src.utils.helpers import load_settings_options
from src.utils.theme import (
    ON_COLOR,
    PRIMARY,
    SIDEBAR_ACCENT,
    SIDEBAR_BG,
    SIDEBAR_BORDER,
    SIDEBAR_MUTED,
    SIDEBAR_SURFACE,
    SIDEBAR_TEXT,
)
from src.utils.ui_helpers import resolve_page


class Sidebar(ft.Container):
    def __init__(self):  # Terima page sebagai parameter
        super().__init__()

        env_value = "production"
        try:
            app_cfg, _err = get_application_config()
            env_value = (
                str(
                    getattr(app_cfg, "environment", "production") or "production"
                ).strip()
                or "production"
            )
        except Exception:
            env_value = "production"

        # Load dropdown options from data_app/settings (auto-create if missing)
        _link_up_path, link_up_options, _lu_created, _lu_err = load_settings_options(
            filename="link_up.txt",
            defaults=["LU21", "LU22"],
        )
        if not link_up_options:
            link_up_options = ["LU21", "LU22"]

        _user_path, user_options, _u_created, _u_err = load_settings_options(
            filename="user.txt",
            defaults=["Alice", "Bob", "Charlie"],
        )
        if not user_options:
            user_options = ["Alice", "Bob", "Charlie"]

        # ─── Logo & App Identity ───────────────────────────────────────────
        self.logo = ft.Image(
            src="icon_windows.ico",
            width=56,
            height=56,
            fit=ft.ImageFit.CONTAIN,
        )

        # App name below logo
        title_block = ft.Column(
            controls=[
                ft.Container(
                    content=self.logo,
                    width=64,
                    height=64,
                    bgcolor=SIDEBAR_SURFACE,
                    border_radius=16,
                    alignment=ft.alignment.center,
                    padding=ft.padding.all(4),
                ),
                ft.Text(
                    "Daily Report",
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                    color=SIDEBAR_TEXT,
                ),
                ft.Text(
                    "Dashboard",
                    size=10,
                    text_align=ft.TextAlign.CENTER,
                    color=SIDEBAR_MUTED,
                    italic=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

        # ─── Helpers for dark-themed form controls ─────────────────────────
        label_style = ft.TextStyle(size=11, color=SIDEBAR_MUTED)
        text_style_input = ft.TextStyle(size=12, color=ft.Colors.WHITE)

        def _dd_style() -> dict:
            """Common style kwargs for Dropdowns inside dark sidebar."""
            return dict(
                label_style=label_style,
                text_size=12,
                text_style=text_style_input,
                color=ft.Colors.WHITE,
                expand=True,
                content_padding=ft.padding.symmetric(horizontal=10, vertical=10),
                border_color=SIDEBAR_BORDER,
                focused_border_color=SIDEBAR_ACCENT,
                bgcolor=SIDEBAR_SURFACE,
                fill_color=SIDEBAR_SURFACE,
                trailing_icon=ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=ft.Colors.WHITE),
                selected_trailing_icon=ft.Icon(
                    ft.Icons.ARROW_DROP_UP, color=ft.Colors.WHITE
                ),
            )

        # ─── Dropdown Link Up ──────────────────────────────────────────────
        self.link_up = ft.Dropdown(
            options=[
                ft.dropdown.Option(opt, style=ft.TextStyle(color=ft.Colors.WHITE))
                for opt in link_up_options
            ],
            value=link_up_options[0] if link_up_options else None,
            label="Link Up",
            **_dd_style(),
        )

        # ─── Dropdown Function Location ────────────────────────────────────
        self.func_location = ft.Dropdown(
            options=[
                ft.dropdown.Option("Maker", style=ft.TextStyle(color=ft.Colors.WHITE)),
                ft.dropdown.Option("Packer", style=ft.TextStyle(color=ft.Colors.WHITE)),
            ],
            value="Packer",
            label="Function Location",
            **_dd_style(),
        )

        # ─── Date field (read-only) ────────────────────────────────────────
        self.date_field = ft.TextField(
            label="Date",
            label_style=label_style,
            text_style=text_style_input,
            hint_text="yyyy-mm-dd",
            expand=True,
            content_padding=ft.padding.only(top=10, bottom=10, left=10, right=16),
            value=datetime.datetime.now().strftime("%Y-%m-%d"),
            border_color=SIDEBAR_BORDER,
            suffix=ft.Icon(
                ft.Icons.CALENDAR_MONTH_ROUNDED, color=ft.Colors.WHITE, size=14
            ),
            on_click=self._on_open_date_picker,
            read_only=True,
        )

        # ─── DatePicker ────────────────────────────────────────────────────
        self.date_picker = ft.DatePicker(
            first_date=datetime.datetime(2020, 1, 1),
            last_date=datetime.datetime(2050, 12, 31),
            value=datetime.datetime.now(),
            on_change=self.on_date_picker_change,
        )

        # ─── Shift Dropdown ────────────────────────────────────────────────
        self.shift = ft.Dropdown(
            options=[
                ft.dropdown.Option(
                    "Shift 1", style=ft.TextStyle(color=ft.Colors.WHITE)
                ),
                ft.dropdown.Option(
                    "Shift 2", style=ft.TextStyle(color=ft.Colors.WHITE)
                ),
                ft.dropdown.Option(
                    "Shift 3", style=ft.TextStyle(color=ft.Colors.WHITE)
                ),
                ft.dropdown.Option(
                    "All Shifts", style=ft.TextStyle(color=ft.Colors.WHITE)
                ),
            ],
            value="Shift 1",
            label="Shift",
            **_dd_style(),
        )

        # ─── Get Data Button (CTA — most prominent) ────────────────────────
        _inner_get_data_btn = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CLOUD_DOWNLOAD_ROUNDED, size=16, color=ON_COLOR),
                    ft.Text(
                        "Get Data", size=13, weight=ft.FontWeight.W_600, color=ON_COLOR
                    ),
                ],
                spacing=8,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(
                bgcolor={"hovered": "#1D4ED8"},
                color=ON_COLOR,
                elevation={"hovered": 6},
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=14),
                animation_duration=150,
            ),
            bgcolor=PRIMARY,
            expand=True,
        )
        # Keep a reference for app.py to wire on_click
        self._get_data_inner_btn = _inner_get_data_btn

        self.get_data_button = ft.Container(
            content=_inner_get_data_btn,
            expand=True,
        )

        # ─── Settings Button (secondary) ──────────────────────────────────
        self.settings_button = ft.Container(
            content=ft.OutlinedButton(
                content=ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.SETTINGS_ROUNDED, size=15, color=SIDEBAR_MUTED
                        ),
                        ft.Text("Settings", size=12, color=SIDEBAR_MUTED),
                    ],
                    spacing=8,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                style=ft.ButtonStyle(
                    side=ft.BorderSide(1, SIDEBAR_BORDER),
                    shape=ft.RoundedRectangleBorder(radius=10),
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
                    overlay_color={"hovered": "#FFFFFF14"},
                    animation_duration=150,
                ),
                expand=True,
                on_click=self.on_settings_click,
            ),
            expand=True,
        )

        # ─── Section label helper ──────────────────────────────────────────
        def _section_label(text: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(
                    text.upper(),
                    size=9,
                    weight=ft.FontWeight.W_700,
                    color=SIDEBAR_MUTED,
                ),
                padding=ft.padding.only(top=4, bottom=2),
            )

        def _divider() -> ft.Divider:
            return ft.Divider(height=1, color=SIDEBAR_BORDER, thickness=1)

        # ─── Sidebar Content ───────────────────────────────────────────────
        self.content = ft.Column(
            [
                ft.Column(
                    [
                        title_block,
                        _divider(),
                        _section_label("Filters"),
                        self.link_up,
                        self.func_location,
                        self.date_field,
                        self.shift,
                        _divider(),
                        self.get_data_button,
                        self.settings_button,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    expand=False,
                    spacing=8,
                ),
                ft.Column(
                    [
                        _divider(),
                        ft.Text(
                            "© 2026 rardyant",
                            size=9,
                            italic=False,
                            color=SIDEBAR_MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            f"env: {env_value}",
                            size=9,
                            italic=True,
                            color=SIDEBAR_MUTED,
                            text_align=ft.TextAlign.CENTER,
                            visible=False if env_value == "production" else True,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=False,
                    spacing=4,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            spacing=10,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ─── Container props ───────────────────────────────────────────────
        self.width = 220
        self.bgcolor = SIDEBAR_BG
        self.border_radius = 12
        self.padding = ft.padding.symmetric(horizontal=14, vertical=16)
        self.expand = False
        self.shadow = ft.BoxShadow(
            spread_radius=0,
            blur_radius=16,
            color="#0000001A",
            offset=ft.Offset(2, 0),
        )

    def on_date_picker_change(self, e: ft.ControlEvent):
        selected_date: datetime.datetime = e.control.value
        self.date_field.value = selected_date.strftime("%Y-%m-%d")
        self.date_field.update()

    def on_settings_click(self, e: ft.ControlEvent):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        def _reload_dropdowns():
            current_lu = str(getattr(self.link_up, "value", "") or "")

            _p1, lu_opts, _c1, _e1 = load_settings_options(
                filename="link_up.txt",
                defaults=["LU21", "LU22"],
            )
            if not lu_opts:
                lu_opts = ["LU21", "LU22"]

            _p2, user_opts, _c2, _e2 = load_settings_options(
                filename="user.txt",
                defaults=["Alice", "Bob", "Charlie"],
            )
            if not user_opts:
                user_opts = ["Alice", "Bob", "Charlie"]

            self.link_up.options = [
                ft.dropdown.Option(opt, style=ft.TextStyle(color=ft.Colors.WHITE))
                for opt in lu_opts
            ]
            self.link_up.value = (
                current_lu
                if current_lu in lu_opts
                else (lu_opts[0] if lu_opts else None)
            )

            try:
                self.link_up.update()
            except Exception:
                pass

        SettingsDialog(page=page, on_saved=_reload_dropdowns).show()

    def _on_open_date_picker(self, e: ft.ControlEvent):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        try:
            page.open(self.date_picker)
        except Exception:
            # DatePicker isn't an AlertDialog, so keep this best-effort.
            try:
                overlay = getattr(page, "overlay", None)
                if isinstance(overlay, list) and self.date_picker not in overlay:
                    overlay.append(self.date_picker)
            except Exception:
                pass
            try:
                self.date_picker.open = True
            except Exception:
                pass
            try:
                page.update()
            except Exception:
                pass
