from __future__ import annotations

import asyncio

import flet as ft

from src.utils.helpers import load_settings_options, save_settings_options
from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY
from src.utils.ui_helpers import open_dialog, snack


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

        status = ft.Text("Loading…", size=12, italic=True)
        progress = ft.ProgressRing(width=18, height=18, stroke_width=2)

        loading_overlay = ft.Container(
            content=ft.Column(
                controls=[progress, status],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
                spacing=10,
            ),
            alignment=ft.alignment.center,
            expand=True,
            visible=True,
        )

        lu_text = ft.TextField(
            label="Link Up (one per line)",
            value="",
            multiline=True,
            min_lines=6,
            max_lines=10,
            text_size=12,
            disabled=True,
        )
        user_text = ft.TextField(
            label="User (one per line)",
            value="",
            multiline=True,
            min_lines=6,
            max_lines=10,
            text_size=12,
            disabled=True,
        )

        save_btn = ft.ElevatedButton(
            "Save",
            on_click=None,
            color=ON_COLOR,
            bgcolor=PRIMARY,
            disabled=True,
        )

        def _on_save(_e=None):
            lu_items = _parse_lines(str(getattr(lu_text, "value", "") or ""))
            user_items = _parse_lines(str(getattr(user_text, "value", "") or ""))

            if not lu_items:
                lu_items = list(self.link_up_defaults)

            lu_items = sorted(lu_items, key=_sort_key_link_up)
            user_items = sorted(user_items, key=lambda s: str(s or "").strip().lower())

            try:
                save_btn.disabled = True
                status.value = "Saving…"
                progress.visible = True
                loading_overlay.visible = True
                page.update()
            except Exception:
                pass

            async def _save_async():
                try:

                    def _worker_save():
                        p1, ok1, err1 = save_settings_options(
                            filename=self.link_up_filename,
                            options=lu_items,
                        )
                        p2, ok2, err2 = save_settings_options(
                            filename=self.user_filename,
                            options=user_items,
                        )
                        return (p1, ok1, err1, p2, ok2, err2)

                    p1, ok1, err1, p2, ok2, err2 = await asyncio.to_thread(_worker_save)

                    if not ok1:
                        snack(
                            page,
                            f"Failed to save Link Up: {err1} ({p1})",
                            kind="error",
                        )
                        return
                    if not ok2:
                        snack(
                            page,
                            f"Failed to save User: {err2} ({p2})",
                            kind="error",
                        )
                        return

                    try:
                        if callable(self.on_saved):
                            self.on_saved()
                    except Exception:
                        pass

                    snack(page, "Settings saved", kind="success")
                    _close()
                finally:
                    try:
                        progress.visible = False
                        status.value = ""
                        loading_overlay.visible = False
                        save_btn.disabled = False
                        page.update()
                    except Exception:
                        pass

            runner = getattr(page, "run_task", None)
            if callable(runner):
                runner(_save_async)
            else:
                # Fallback: blocking save
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

        # Wire the handler after definition so Save actually works.
        try:
            save_btn.on_click = _on_save
        except Exception:
            pass

        self._dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.title),
            content=ft.Container(
                content=ft.Stack(
                    controls=[
                        ft.Column(
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
                        loading_overlay,
                    ],
                    expand=True,
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
                        save_btn,
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=_close,
        )

        open_dialog(page, self._dlg)

        async def _load_async():
            try:

                def _worker_load():
                    return (
                        load_settings_options(
                            filename=self.link_up_filename,
                            defaults=list(self.link_up_defaults),
                        ),
                        load_settings_options(
                            filename=self.user_filename,
                            defaults=list(self.user_defaults),
                        ),
                    )

                (
                    (p_lu, lu_opts, _c_lu, e_lu),
                    (p_u, user_opts, _c_u, e_u),
                ) = await asyncio.to_thread(_worker_load)

                if e_lu:
                    snack(
                        page,
                        f"Link Up options read warning: {e_lu} ({p_lu})",
                        kind="warning",
                    )
                if e_u:
                    snack(
                        page,
                        f"User options read warning: {e_u} ({p_u})",
                        kind="warning",
                    )

                lu_text.value = "\n".join(lu_opts or [])
                user_text.value = "\n".join(user_opts or [])
                lu_text.disabled = False
                user_text.disabled = False
                save_btn.disabled = False

                progress.visible = False
                status.value = ""
                loading_overlay.visible = False
                page.update()
            except Exception as ex:
                progress.visible = False
                status.value = f"Failed to load: {ex}"
                loading_overlay.visible = True
                try:
                    page.update()
                except Exception:
                    pass

        runner = getattr(page, "run_task", None)
        if callable(runner):
            runner(_load_async)
        else:
            # Fallback: blocking load
            _p_lu, lu_opts, _c_lu, _e_lu = load_settings_options(
                filename=self.link_up_filename,
                defaults=list(self.link_up_defaults),
            )
            _p_u, user_opts, _c_u, _e_u = load_settings_options(
                filename=self.user_filename,
                defaults=list(self.user_defaults),
            )
            lu_text.value = "\n".join(lu_opts or [])
            user_text.value = "\n".join(user_opts or [])
            lu_text.disabled = False
            user_text.disabled = False
            save_btn.disabled = False
            progress.visible = False
            status.value = ""
            loading_overlay.visible = False
            try:
                page.update()
            except Exception:
                pass
