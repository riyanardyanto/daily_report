import flet as ft

from src.components.history_table import HistoryTableDialog
from src.components.qr_code_dialog import QrCodeDialog
from src.components.report_list_view import ReportList
from src.components.target_editor import TargetEditorDialog
from src.services.history_service import save_report_history_csv
from src.utils.helpers import data_app_path
from src.utils.ui_helpers import resolve_page, snack


class ReportEditor(ft.Container):
    def __init__(
        self,
        on_report_table=None,
        get_report_table_text=None,
        get_metrics_rows=None,
        set_metrics_targets=None,
        get_selected_shift=None,
        get_link_up=None,
        get_func_location=None,
        get_date_field=None,
        get_user=None,
        **kwargs,
    ):
        # Default to filling available space so the embedded ReportList becomes scrollable.
        kwargs.setdefault("expand", True)
        self._report_table_cb = on_report_table
        self._get_report_table_text_cb = get_report_table_text
        self._get_metrics_rows_cb = get_metrics_rows
        self._set_metrics_targets_cb = set_metrics_targets
        self._get_selected_shift_cb = get_selected_shift
        self._get_link_up_cb = get_link_up
        self._get_func_location_cb = get_func_location
        self._get_date_field_cb = get_date_field
        self._get_user_cb = get_user

        self.include_table_switch = ft.Switch(
            label="Include Table",
            label_style=ft.TextStyle(size=20, italic=True),
            label_position=ft.LabelPosition.RIGHT,
            width=100,
            height=20,
            value=True,
            active_track_color=ft.Colors.GREEN,
        )

        header = ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            margin=ft.margin.only(bottom=10),
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                icon_color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.BLUE_GREY,
                                icon_size=20,
                                tooltip="Edit Target",
                                on_click=self._on_show_target_editor,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.TABLE_ROWS,
                                icon_color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.PURPLE,
                                icon_size=20,
                                tooltip="Show History Table",
                                on_click=self._on_show_history_table,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.QR_CODE,
                                icon_color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.ORANGE,
                                icon_size=20,
                                tooltip="Show QR Code",
                                on_click=self._on_show_qr_code,
                            ),
                            self.include_table_switch,
                        ],
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ADD_ROUNDED,
                                icon_color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.LIGHT_GREEN,
                                icon_size=20,
                                tooltip="Add Card",
                                on_click=self._on_add_card,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLEAR,
                                icon_color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.RED,
                                icon_size=20,
                                tooltip="Clear All",
                                on_click=self._on_clear_all,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SAVE,
                                icon_color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.BLUE,
                                icon_size=20,
                                tooltip="Save Report",
                                on_click=self._on_save_report,
                            ),
                        ],
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

    def _on_show_history_table(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        csv_path = data_app_path("history.csv", folder_name="data_app/history")
        HistoryTableDialog(
            page=page,
            csv_path=csv_path,
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

        try:
            cards = list(getattr(self.report_list, "controls", None) or [])
            if not cards:
                snack(page, "Tidak ada card untuk disimpan", kind="warning")
                return

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
                    link_up = str(self._get_link_up_cb() or "LU22").strip() or "LU22"
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

            user = ""
            try:
                if callable(getattr(self, "_get_user_cb", None)):
                    user = str(self._get_user_cb() or "").strip()
            except Exception:
                user = ""

            csv_path = data_app_path("history.csv", folder_name="data_app/history")

            ok, msg = save_report_history_csv(
                csv_path=csv_path,
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
        except Exception as ex:
            snack(page, f"Gagal simpan report: {ex}", kind="error")

    def _on_add_card(self, e):
        try:
            self.report_list.append_item_issue(focus=True)
        except Exception:
            pass

    def _on_report_table(self, e):
        try:
            if callable(getattr(self, "_report_table_cb", None)):
                self._report_table_cb()
            else:
                print("(no report table callback)")
        except Exception:
            pass

    def _on_clear_all(self, e):
        page = resolve_page(e)
        if page is None:
            return

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
            title=ft.Text("Confirm delete"),
            content=ft.Text("Hapus semua card?"),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.TextButton("Delete", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        try:
            page.open(dlg)
        except Exception:
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except Exception:
                pass

    def _on_show_qr_code(self, e):
        page = resolve_page(e)
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
        try:
            include_table = bool(
                getattr(getattr(self, "include_table_switch", None), "value", False)
            )
        except Exception:
            include_table = False

        if include_table and callable(getattr(self, "_get_report_table_text_cb", None)):
            try:
                table_text: str = self._get_report_table_text_cb()
                replaced_table_text = table_text.replace("\n", "`\n`")
                formatted_table_text = f"`{replaced_table_text}`".strip()
                if table_text:
                    payload = f"{formatted_table_text}\n\n{report_text}".strip()
            except Exception:
                pass

        meta_line = (f"*{func_location.upper()} {link_up[-2:]} | {date_field} | {shift}*").strip()
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
