from __future__ import annotations

import flet as ft

from src.utils.helpers import load_settings_options, save_settings_options
from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY
from src.utils.ui_helpers import snack


class SettingsDialog:
    """Reusable dialog to edit Link Up and User dropdown options.

    Stores values in:
    - data_app/settings/link_up.txt
    - data_app/settings/user.txt
    """

    def __init__(
        self,
        *,
        page: ft.Page,
        on_saved=None,
        link_up_filename: str = "link_up.txt",
        user_filename: str = "user.txt",
        link_up_defaults: list[str] | None = None,
        user_defaults: list[str] | None = None,
        title: str = "Settings",
    ):
        self.page = page
        self.on_saved = on_saved
        self.link_up_filename = link_up_filename
        self.user_filename = user_filename
        self.link_up_defaults = link_up_defaults or ["LU21", "LU22"]
        self.user_defaults = user_defaults or ["Alice", "Bob", "Charlie"]
        self.title = title

        self._dlg: ft.AlertDialog | None = None

    def show(self):
        page = self.page
        if page is None:
            return

        def _parse_lines(text: str) -> list[str]:
            seen: set[str] = set()
            items: list[str] = []
            for line in (text or "").splitlines():
                for part in str(line).split(","):
                    value = str(part or "").strip()
                    if not value:
                        continue
                    key = value.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(value)
            return items

        def _sort_key_link_up(value: str):
            v = str(value or "").strip()
            prefix = ""
            digits = ""
            for ch in v:
                if ch.isdigit():
                    digits += ch
                else:
                    prefix += ch
            if digits:
                try:
                    return (prefix.lower(), int(digits), v.lower())
                except Exception:
                    return (prefix.lower(), float("inf"), v.lower())
            return (prefix.lower(), float("inf"), v.lower())

        def _close(_e=None):
            try:
                if self._dlg is not None:
                    self._dlg.open = False
                page.update()
            except Exception:
                pass

        # Prefill from current file contents
        _p_lu, lu_opts, _c_lu, _e_lu = load_settings_options(
            filename=self.link_up_filename,
            defaults=list(self.link_up_defaults),
        )
        _p_u, user_opts, _c_u, _e_u = load_settings_options(
            filename=self.user_filename,
            defaults=list(self.user_defaults),
        )

        lu_text = ft.TextField(
            label="Link Up (one per line)",
            value="\n".join(lu_opts or []),
            multiline=True,
            min_lines=6,
            max_lines=10,
            text_size=12,
        )
        user_text = ft.TextField(
            label="User (one per line)",
            value="\n".join(user_opts or []),
            multiline=True,
            min_lines=6,
            max_lines=10,
            text_size=12,
        )

        def _on_save(_e=None):
            lu_items = _parse_lines(str(getattr(lu_text, "value", "") or ""))
            user_items = _parse_lines(str(getattr(user_text, "value", "") or ""))

            if not lu_items:
                lu_items = list(self.link_up_defaults)

            lu_items = sorted(lu_items, key=_sort_key_link_up)
            user_items = sorted(user_items, key=lambda s: str(s or "").strip().lower())

            p1, ok1, err1 = save_settings_options(
                filename=self.link_up_filename,
                options=lu_items,
            )
            p2, ok2, err2 = save_settings_options(
                filename=self.user_filename,
                options=user_items,
            )

            if not ok1:
                snack(page, f"Failed to save Link Up: {err1} ({p1})", kind="error")
                return
            if not ok2:
                snack(page, f"Failed to save User: {err2} ({p2})", kind="error")
                return

            try:
                if callable(self.on_saved):
                    self.on_saved()
            except Exception:
                pass

            snack(page, "Settings saved", kind="success")
            _close()

        self._dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.title),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Edit the options list for the Link Up & User dropdowns.",
                            size=12,
                        ),
                        ft.Divider(height=10),
                        lu_text,
                        ft.Divider(height=10),
                        user_text,
                    ],
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=520,
                padding=ft.padding.all(12),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10,
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Close",
                            on_click=_close,
                            style=ft.ButtonStyle(color=SECONDARY),
                        ),
                        ft.ElevatedButton(
                            "Save",
                            on_click=_on_save,
                            color=ON_COLOR,
                            bgcolor=PRIMARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=_close,
        )

        try:
            page.open(self._dlg)
        except Exception:
            try:
                page.dialog = self._dlg
                self._dlg.open = True
                page.update()
            except Exception:
                pass
