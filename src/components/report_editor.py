import asyncio

import flet as ft

from src.components.history_table import HistoryTableDialog
from src.components.qr_code_dialog import QrCodeDialog
from src.components.report_list_view import ReportList
from src.components.target_editor import TargetEditorDialog
from src.services.history_db_service import save_report_history_sqlite
from src.utils.helpers import data_app_path, load_settings_options
from src.utils.theme import DANGER, INFO, ON_COLOR, PRIMARY, SECONDARY, SUCCESS, WARNING
from src.utils.ui_helpers import open_dialog, resolve_page, snack


class ReportEditor(ft.Container):
    def __init__(
        self,
        get_report_table_text=None,
        get_include_table=None,
        get_metrics_rows=None,
        set_metrics_targets=None,
        get_selected_shift=None,
        get_link_up=None,
        get_func_location=None,
        get_date_field=None,
        on_history_saved=None,
        **kwargs,
    ):
        # Default to filling available space so the embedded ReportList becomes scrollable.
        kwargs.setdefault("expand", True)
        self._get_report_table_text_cb = get_report_table_text
        self._get_include_table_cb = get_include_table
        self._get_metrics_rows_cb = get_metrics_rows
        self._set_metrics_targets_cb = set_metrics_targets
        self._get_selected_shift_cb = get_selected_shift
        self._get_link_up_cb = get_link_up
        self._get_func_location_cb = get_func_location
        self._get_date_field_cb = get_date_field
        self._on_history_saved_cb = on_history_saved

        header = ft.Container(
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            margin=ft.margin.only(bottom=10),
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=10,
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.QR_CODE,
                                icon_color=ON_COLOR,
                                bgcolor=WARNING,
                                icon_size=18,
                                tooltip="Show QR code",
                                on_click=self._on_show_qr_code,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                icon_color=ON_COLOR,
                                bgcolor=PRIMARY,
                                icon_size=18,
                                tooltip="Edit target",
                                on_click=self._on_show_target_editor,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SAVE,
                                icon_color=ON_COLOR,
                                bgcolor=SUCCESS,
                                icon_size=18,
                                tooltip="Save report",
                                on_click=self._on_save_report,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.TABLE_ROWS,
                                icon_color=ON_COLOR,
                                bgcolor=INFO,
                                icon_size=18,
                                tooltip="Show history",
                                on_click=self._on_show_history_table,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ADD_ROUNDED,
                                icon_color=ON_COLOR,
                                bgcolor=SUCCESS,
                                icon_size=18,
                                tooltip="Add card",
                                on_click=self._on_add_card,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLEAR,
                                icon_color=ON_COLOR,
                                bgcolor=DANGER,
                                icon_size=18,
                                tooltip="Clear all",
                                on_click=self._on_clear_all,
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                expand=True,
                spacing=10,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self.report_list = ReportList(expand=True)

        super().__init__(
            content=ft.Column(
                controls=[
                    header,
                    self.report_list,
                ],
                expand=True,
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
            ),
            **kwargs,
        )

    def _notify_history_saved(self, page: ft.Page | None) -> None:
        cb = getattr(self, "_on_history_saved_cb", None)
        if not callable(cb):
            return
        try:
            cb(page)
        except Exception:
            return

    def _on_show_history_table(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        csv_path = data_app_path("history.csv", folder_name="data_app/history")
        db_path = data_app_path("history.db", folder_name="data_app/history")
        HistoryTableDialog(
            page=page,
            csv_path=csv_path,
            db_path=db_path,
            hidden_columns={
                "save_id",
                "saved_at",
                "card_index",
                "detail_index",
                "action_index",
            },
        ).show()

    def _on_save_report(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        cards = list(getattr(self.report_list, "controls", None) or [])
        if not cards:
            snack(page, "No cards to save", kind="warning")
            return

        # Load user options (from data_app/settings/user.txt)
        try:
            _p, user_options, _created, _err = load_settings_options(
                filename="user.txt",
                defaults=["Alice", "Bob", "Charlie"],
            )
        except Exception:
            user_options = ["Alice", "Bob", "Charlie"]

        if not user_options:
            user_options = ["Alice", "Bob", "Charlie"]

        user_dd = ft.Dropdown(
            options=[ft.dropdown.Option(opt) for opt in user_options],
            label="User",
            hint_text="Choose your name",
            text_size=12,
            expand=True,
            content_padding=10,
            value=None,
        )

        def _do_save(selected_user: str):
            try:
                # Sidebar metadata (best-effort)
                shift = "Shift 1"
                try:
                    if callable(getattr(self, "_get_selected_shift_cb", None)):
                        shift = (
                            str(self._get_selected_shift_cb() or "Shift 1").strip()
                            or "Shift 1"
                        )
                except Exception:
                    shift = "Shift 1"

                link_up = "LU22"
                try:
                    if callable(getattr(self, "_get_link_up_cb", None)):
                        link_up = (
                            str(self._get_link_up_cb() or "LU22").strip() or "LU22"
                        )
                except Exception:
                    link_up = "LU22"

                func_location = "Packer"
                try:
                    if callable(getattr(self, "_get_func_location_cb", None)):
                        func_location = (
                            str(self._get_func_location_cb() or "Packer").strip()
                            or "Packer"
                        )
                except Exception:
                    func_location = "Packer"

                date_field = ""
                try:
                    if callable(getattr(self, "_get_date_field_cb", None)):
                        date_field = str(self._get_date_field_cb() or "").strip()
                except Exception:
                    date_field = ""

                user = str(selected_user or "").strip()

                db_path = data_app_path("history.db", folder_name="data_app/history")

                snack(page, "Saving…", kind="warning")

                async def _run_save():
                    try:

                        def _worker():
                            return save_report_history_sqlite(
                                db_path=db_path,
                                cards=cards,
                                extract_issue=self.report_list._extract_issue_text,
                                extract_details=self.report_list._extract_details,
                                shift=shift,
                                link_up=link_up,
                                func_location=func_location,
                                date_field=date_field,
                                user=user,
                            )

                        ok, msg = await asyncio.to_thread(_worker)
                        msg_l = str(msg or "").lower()
                        if ok:
                            kind = "success"
                        elif any(k in msg_l for k in ("terbuka", "terkunci", "locked")):
                            kind = "warning"
                        else:
                            kind = "error"
                        snack(page, msg, kind=kind)
                        if ok:
                            self._notify_history_saved(page)
                    except Exception as ex:
                        snack(page, f"Failed to save report: {ex}", kind="error")

                runner = getattr(page, "run_task", None)
                if callable(runner):
                    runner(_run_save)
                else:
                    # Fallback (blocking) if run_task isn't available
                    ok, msg = save_report_history_sqlite(
                        db_path=db_path,
                        cards=cards,
                        extract_issue=self.report_list._extract_issue_text,
                        extract_details=self.report_list._extract_details,
                        shift=shift,
                        link_up=link_up,
                        func_location=func_location,
                        date_field=date_field,
                        user=user,
                    )
                    msg_l = str(msg or "").lower()
                    if ok:
                        kind = "success"
                    elif any(k in msg_l for k in ("terbuka", "terkunci", "locked")):
                        kind = "warning"
                    else:
                        kind = "error"
                    snack(page, msg, kind=kind)
                    if ok:
                        self._notify_history_saved(page)
            except Exception as ex:
                snack(page, f"Failed to save report: {ex}", kind="error")

        def _close_dialog(_e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(_e=None):
            selected_user = str(getattr(user_dd, "value", "") or "").strip()
            if not selected_user:
                snack(page, "Please select a user before saving.", kind="warning")
                return
            try:
                _close_dialog()
            finally:
                _do_save(selected_user)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Select user:"),
                        user_dd,
                        ft.Divider(height=10),
                        ft.Text(f"Save report to history? ({len(cards)} card)"),
                    ],
                    spacing=10,
                ),
                padding=ft.padding.all(12),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10,
                height=150,
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Cancel",
                            on_click=_close_dialog,
                            style=ft.ButtonStyle(color=SECONDARY),
                        ),
                        ft.ElevatedButton(
                            "Save",
                            on_click=_confirm,
                            color=ON_COLOR,
                            bgcolor=SUCCESS,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def _on_add_card(self, e):
        try:
            self.report_list.append_item_issue(focus=True)
        except Exception:
            pass

    def _on_clear_all(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        try:
            if not (getattr(self.report_list, "controls", None) or []):
                snack(page, "No cards to clear", kind="warning")
                return
        except Exception:
            pass

        def _close_dialog(_e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(_e=None):
            try:
                self.report_list.controls.clear()
                self.report_list.update()
            finally:
                _close_dialog()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Text("Clear all cards?"),
                padding=ft.padding.all(12),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10,
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Cancel",
                            on_click=_close_dialog,
                            style=ft.ButtonStyle(color=SECONDARY),
                        ),
                        ft.ElevatedButton(
                            "Clear",
                            on_click=_confirm,
                            color=ON_COLOR,
                            bgcolor=DANGER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def _on_show_qr_code(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        # Sidebar metadata (best-effort) to prepend as the first line of QR payload
        shift = "Shift 1"
        try:
            if callable(getattr(self, "_get_selected_shift_cb", None)):
                shift = (
                    str(self._get_selected_shift_cb() or "Shift 1").strip() or "Shift 1"
                )
        except Exception:
            shift = "Shift 1"

        link_up = "LU22"
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                link_up = str(self._get_link_up_cb() or "LU22").strip() or "LU22"
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = (
                    str(self._get_func_location_cb() or "Packer").strip() or "Packer"
                )
        except Exception:
            func_location = "Packer"

        date_field = ""
        try:
            if callable(getattr(self, "_get_date_field_cb", None)):
                date_field = str(self._get_date_field_cb() or "").strip()
        except Exception:
            date_field = ""

        report_text = ""
        try:
            report_text = self.report_list.build_report_text()
        except Exception:
            report_text = ""

        payload = report_text
        include_table = True
        try:
            if callable(getattr(self, "_get_include_table_cb", None)):
                include_table = bool(self._get_include_table_cb())
        except Exception:
            include_table = True

        if include_table and callable(getattr(self, "_get_report_table_text_cb", None)):
            try:
                table_text: str = self._get_report_table_text_cb()
                replaced_table_text = table_text.replace("\n", "`\n`")
                formatted_table_text = f"`{replaced_table_text}`".strip()
                if table_text:
                    payload = f"{formatted_table_text}\n\n{report_text}".strip()
            except Exception:
                pass

        meta_line = (
            f"*{func_location.upper()} {link_up[-2:]} | {date_field} | {shift}*"
        ).strip()
        payload = f"{meta_line}\n{payload}".strip()

        QrCodeDialog(page=page, payload=payload).show()

    def _on_show_target_editor(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        TargetEditorDialog(
            page=page,
            get_selected_shift=getattr(self, "_get_selected_shift_cb", None),
            get_link_up=getattr(self, "_get_link_up_cb", None),
            get_func_location=getattr(self, "_get_func_location_cb", None),
            get_metrics_rows=getattr(self, "_get_metrics_rows_cb", None),
            set_metrics_targets=getattr(self, "_set_metrics_targets_cb", None),
        ).show()
