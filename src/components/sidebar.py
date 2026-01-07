from __future__ import annotations

import datetime

import flet as ft

from src.components.settings_dialog import SettingsDialog
from src.services.config_service import get_application_config
from src.utils.helpers import load_settings_options
from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY


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

        # Logo
        self.logo = ft.Image(
            src="icon_windows.ico",
            width=70,
            height=70,
            fit=ft.ImageFit.CONTAIN,
        )

        title_block = ft.Column(
            controls=[
                self.logo,
                ft.Text(
                    "Daily Report",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

        # Dropdown Link Up
        self.link_up = ft.Dropdown(
            options=[ft.dropdown.Option(opt) for opt in link_up_options],
            value=link_up_options[0] if link_up_options else None,
            label="Link Up",
            label_style=ft.TextStyle(size=12),
            text_size=12,
            expand=True,
            content_padding=10,
        )

        # Dropdown Function Location
        self.func_location = ft.Dropdown(
            options=[
                ft.dropdown.Option("Maker"),
                ft.dropdown.Option("Packer"),
            ],
            value="Packer",
            label="Function Location",
            text_size=12,
            text_align=ft.TextAlign.START,
            label_style=ft.TextStyle(size=12),
            expand=True,
            content_padding=10,
        )

        # Date display TextField
        self.date_field = ft.TextField(
            label="Date",
            label_style=ft.TextStyle(size=12),
            hint_text="yyyy-mm-dd",
            read_only=True,
            expand=True,
            text_size=12,
            content_padding=10,
            value=datetime.datetime.now().strftime("%Y-%m-%d"),
        )

        # DatePicker
        self.date_picker = ft.DatePicker(
            first_date=datetime.datetime(2020, 1, 1),
            last_date=datetime.datetime(2050, 12, 31),
            value=datetime.datetime.now(),
            on_change=self.on_date_picker_change,
        )

        # Calendar icon to open picker
        calendar_icon = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_size=20,
            tooltip="Choose date",
            on_click=lambda e: self.page.open(self.date_picker),
        )

        # Shift dropdown (Shift 1/2/3)
        self.shift = ft.Dropdown(
            options=[
                ft.dropdown.Option("Shift 1"),
                ft.dropdown.Option("Shift 2"),
                ft.dropdown.Option("Shift 3"),
            ],
            value="Shift 1",
            label="Shift",
            label_style=ft.TextStyle(size=12),
            text_size=12,
            expand=True,
            content_padding=10,
        )

        # Get data button
        self.get_data_button = ft.ElevatedButton(
            text="Get Data",
            width=140,
            color=ON_COLOR,
            bgcolor=PRIMARY,
        )

        # Entry user
        self.user = ft.Dropdown(
            options=[ft.dropdown.Option(opt) for opt in user_options],
            label="User",
            label_style=ft.TextStyle(size=12),
            hint_text="Choose your name",
            text_size=12,
            expand=True,
            content_padding=10,
        )

        # Setting Button
        self.settings_button = ft.ElevatedButton(
            text="Settings",
            width=140,
            color=ON_COLOR,
            bgcolor=SECONDARY,
            on_click=self.on_settings_click,
        )

        # Content utama sidebar
        self.content = ft.Column(
            [
                ft.Column(
                    [
                        title_block,
                        ft.Divider(height=16, color=ft.Colors.BLACK12),
                        ft.Text("Filters", size=11, weight=ft.FontWeight.W_600),
                        self.link_up,
                        self.func_location,
                        ft.Row(
                            [
                                self.date_field,
                                calendar_icon,
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=6,
                        ),
                        self.shift,
                        self.get_data_button,
                        ft.Divider(height=12, color=ft.Colors.BLACK12),
                        ft.Text("User", size=11, weight=ft.FontWeight.W_600),
                        self.user,
                        ft.Divider(height=16, color=ft.Colors.BLACK12),
                        self.settings_button,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    expand=False,
                    spacing=10,
                ),
                ft.Column(
                    [
                        ft.Text("© 2026 rardyant", size=8, italic=False),
                        ft.Text(
                            f"env: {env_value}",
                            size=8,
                            italic=False,
                            visible=False if env_value == "production" else True,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=False,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            spacing=10,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Properti Container sidebar
        self.width = 220
        self.bgcolor = ft.Colors.WHITE
        self.border = ft.border.all(1, ft.Colors.BLACK12)
        self.border_radius = 10
        self.padding = ft.padding.symmetric(horizontal=12, vertical=14)
        self.expand = False

    def on_date_picker_change(self, e: ft.ControlEvent):
        selected_date: datetime.datetime = e.control.value
        self.date_field.value = selected_date.strftime("%Y-%m-%d")
        self.date_field.update()

    def on_settings_click(self, e: ft.ControlEvent):
        page = getattr(e, "page", None)
        if page is None:
            return

        def _reload_dropdowns():
            current_lu = str(getattr(self.link_up, "value", "") or "")
            current_user = str(getattr(self.user, "value", "") or "")

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

            self.link_up.options = [ft.dropdown.Option(opt) for opt in lu_opts]
            self.link_up.value = (
                current_lu
                if current_lu in lu_opts
                else (lu_opts[0] if lu_opts else None)
            )

            self.user.options = [ft.dropdown.Option(opt) for opt in user_opts]
            self.user.value = current_user if current_user in user_opts else None

            try:
                self.link_up.update()
            except Exception:
                pass
            try:
                self.user.update()
            except Exception:
                pass

        SettingsDialog(page=page, on_saved=_reload_dropdowns).show()
