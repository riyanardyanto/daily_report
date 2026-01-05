from __future__ import annotations

import csv
from pathlib import Path

import flet as ft

from src.utils.ui_helpers import snack


class HistoryTableDialog:
    def __init__(
        self,
        *,
        page: ft.Page,
        csv_path: Path,
        title: str = "History Table",
        hidden_columns: set[str] | None = None,
        export_default_name: str = "history_export.csv",
    ):
        self.page = page
        self.csv_path = Path(csv_path)
        self.title = title
        self.hidden_columns = set(hidden_columns or set())
        self.export_default_name = export_default_name

        self._dlg: ft.AlertDialog | None = None
        self._prev_on_resize = None

        self._fieldnames: list[str] = []
        self._rows_data: list[dict] = []
        self._filtered_rows_data: list[dict] = []

        self._dt: ft.DataTable | None = None
        self._content_container: ft.Container | None = None
        self._filter_tf: ft.TextField | None = None

        self._file_picker = ft.FilePicker()

    def show(self):
        page = self.page
        if page is None:
            return

        if not self.csv_path.exists():
            snack(page, f"History belum ada: {self.csv_path}", kind="warning")
            return

        try:
            with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                rows_data = list(reader)

            if not fieldnames:
                snack(page, "History CSV tidak memiliki header", kind="warning")
                return

            visible_fields = [c for c in fieldnames if c not in self.hidden_columns]
            if not visible_fields:
                snack(
                    page,
                    "History CSV tidak memiliki kolom yang bisa ditampilkan",
                    kind="warning",
                )
                return

            self._fieldnames = visible_fields
            self._rows_data = list(rows_data)
            self._filtered_rows_data = list(rows_data)

            self._prev_on_resize = getattr(page, "on_resize", None)

            self._file_picker.on_result = self._on_export_result

            self._filter_tf = ft.TextField(
                label="Filter",
                hint_text="Ketik untuk filter data...",
                text_size=12,
                dense=True,
                on_change=self._apply_filter,
            )

            self._dt = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text(name, size=11, weight=ft.FontWeight.W_600))
                    for name in self._fieldnames
                ],
                rows=self._build_rows(self._filtered_rows_data),
                border=ft.border.all(1, ft.Colors.BLACK12),
                heading_row_color=ft.Colors.BLUE_GREY_50,
                data_row_max_height=140,
                data_row_min_height=40,
                heading_row_height=34,
                vertical_lines=ft.BorderSide(1, ft.Colors.BLACK12),
                horizontal_lines=ft.BorderSide(1, ft.Colors.BLACK12),
                column_spacing=10,
                width=900,
            )

            self._content_container = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(str(self.csv_path), size=11, italic=True),
                        self._filter_tf,
                        ft.Container(
                            content=ft.Row(
                                controls=[self._dt],
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                                alignment=ft.MainAxisAlignment.END,
                            ),
                            expand=True,
                        ),
                    ],
                    expand=True,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                ),
                width=1200,
                height=650,
                padding=ft.padding.all(8),
                expand=True,
            )

            self._dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"{self.title} ({len(self._rows_data)} rows)"),
                content=self._content_container,
                actions=[
                    ft.TextButton("Export", on_click=self._on_export_click),
                    ft.TextButton("Close", on_click=self.close),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=self.close,
            )

            try:
                page.on_resize = self._on_resize
            except Exception:
                pass

            self._apply_responsive_size()

            try:
                page.open(self._dlg)
            except Exception:
                page.dialog = self._dlg
                self._dlg.open = True
                page.update()

        except Exception as ex:
            snack(page, f"Gagal membaca history.csv: {ex}", kind="error")

    def close(self, _e=None):
        page = self.page
        try:
            if self._dlg is not None:
                self._dlg.open = False
            try:
                page.on_resize = self._prev_on_resize
            except Exception:
                pass
            page.update()
        except Exception:
            pass

    def _ensure_file_picker_added(self):
        page = self.page
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is None:
                return
            if self._file_picker not in overlay:
                overlay.append(self._file_picker)
                page.update()
        except Exception:
            pass

    def _on_export_click(self, _e=None):
        self._ensure_file_picker_added()
        try:
            self._file_picker.save_file(
                dialog_title="Export history CSV",
                file_name=self.export_default_name,
                allowed_extensions=["csv"],
            )
            self.close()
        except Exception as ex:
            snack(self.page, f"Gagal buka file dialog: {ex}", kind="error")

    def _on_export_result(self, ev: ft.FilePickerResultEvent):
        try:
            export_path = getattr(ev, "path", None)
        except Exception:
            export_path = None
        if export_path:
            self._export_rows_to_path(export_path)

    def _export_rows_to_path(self, export_path: str):
        try:
            p = str(export_path or "").strip()
            if not p:
                return

            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=self._fieldnames)
                writer.writeheader()
                for row_obj in self._filtered_rows_data:
                    out = {
                        c: str((row_obj or {}).get(c, "") or "")
                        for c in self._fieldnames
                    }
                    writer.writerow(out)

            snack(self.page, f"Export berhasil: {p}", kind="success")
        except Exception as ex:
            snack(self.page, f"Gagal export CSV: {ex}", kind="error")

    def _row_matches(self, row_obj: dict, q: str) -> bool:
        if not q:
            return True
        q = q.lower()
        try:
            for col in self._fieldnames:
                v = str((row_obj or {}).get(col, "") or "")
                if q in v.lower():
                    return True
        except Exception:
            return True
        return False

    def _build_rows(self, filtered: list[dict]) -> list[ft.DataRow]:
        out_rows: list[ft.DataRow] = []
        for row_obj in filtered:
            cells: list[ft.DataCell] = []
            for col in self._fieldnames:
                try:
                    value = str((row_obj or {}).get(col, "") or "")
                except Exception:
                    value = ""
                cells.append(ft.DataCell(ft.Text(value, size=11)))
            out_rows.append(ft.DataRow(cells=cells))
        return out_rows

    def _apply_filter(self, _e=None):
        try:
            q = str(getattr(self._filter_tf, "value", "") or "").strip()
            self._filtered_rows_data = [
                r for r in self._rows_data if self._row_matches(r, q)
            ]
            if self._dt is not None:
                self._dt.rows = self._build_rows(self._filtered_rows_data)
                try:
                    self._dt.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_responsive_size(self):
        page = self.page
        if self._content_container is None or self._dt is None:
            return

        try:
            w = getattr(page, "width", None) or 1200
            h = getattr(page, "height", None) or 900

            self._content_container.width = max(800, int(w * 0.90))
            self._content_container.height = max(520, int(h * 0.82))
            self._dt.width = max(760, int(self._content_container.width * 0.98))

            try:
                self._dt.update()
            except Exception:
                pass
            try:
                self._content_container.update()
            except Exception:
                pass
        except Exception:
            pass

    def _on_resize(self, evt=None):
        try:
            if callable(self._prev_on_resize):
                self._prev_on_resize(evt)
        except Exception:
            pass

        try:
            if self._dlg is not None and getattr(self._dlg, "open", False):
                self._apply_responsive_size()
                self.page.update()
        except Exception:
            pass
