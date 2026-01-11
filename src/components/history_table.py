from __future__ import annotations

import csv
from collections import deque
from pathlib import Path

import flet as ft

from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY
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
        max_rows: int = 1000,
    ):
        self.page = page
        self.csv_path = Path(csv_path)
        self.title = title
        self.hidden_columns = set(hidden_columns or set())
        self.export_default_name = export_default_name
        self.max_rows = int(max_rows or 0) if max_rows is not None else 1000

        self._dlg: ft.AlertDialog | None = None
        self._prev_on_resize = None

        self._fieldnames: list[str] = []
        self._rows_data: list[dict] = []
        self._filtered_rows_data: list[dict] = []

        self._dt: ft.DataTable | None = None
        self._content_container: ft.Container | None = None
        self._filter_tf: ft.TextField | None = None

        self._file_picker = ft.FilePicker()

        self._total_rows: int = 0
        self._base_rows_data: list[dict] = []
        self._title_text: ft.Text | None = None

        # Column sizing rules:
        # - issue/detail/action: stretch equally to fill remaining width
        # - everything else: fixed width
        self._stretch_columns = {"issue", "detail", "action"}
        self._fixed_col_widths: dict[str, int] = {
            "save_id": 160,
            "saved_at": 150,
            "link_up": 45,
            "func_location": 40,
            "date_field": 70,
            "shift": 40,
            "user": 55,
            "card_index": 70,
            "detail_index": 85,
            "action_index": 90,
        }
        self._default_fixed_width_px = 120
        self._stretch_width_px = 260
        self._min_stretch_width_px = 200
        self._width_padding_px = 48

    def show(self):
        page = self.page
        if page is None:
            return

        if not self.csv_path.exists():
            snack(page, f"History not found: {self.csv_path}", kind="warning")
            return

        try:
            with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                # Stream rows so memory doesn't grow with the file size.
                max_rows = self.max_rows if self.max_rows > 0 else 1000
                tail = deque(maxlen=max_rows)
                total_rows = 0
                for row in reader:
                    total_rows += 1
                    tail.append(row)
                rows_data = list(tail)

            self._total_rows = int(total_rows)
            self._base_rows_data = list(rows_data)

            if not fieldnames:
                snack(page, "History CSV has no header", kind="warning")
                return

            visible_fields = [c for c in fieldnames if c not in self.hidden_columns]
            if not visible_fields:
                snack(
                    page,
                    "History CSV has no columns to display",
                    kind="warning",
                )
                return

            self._fieldnames = visible_fields
            self._rows_data = list(rows_data)
            self._filtered_rows_data = list(rows_data)

            self._prev_on_resize = getattr(page, "on_resize", None)

            self._file_picker.on_result = self._on_export_result

            self._filter_tf = ft.TextField(
                label="Search",
                hint_text="Type to search, then press Enter...",
                text_size=12,
                dense=True,
                on_submit=self._apply_filter,
                expand=True,
            )

            self._dt = ft.DataTable(
                columns=[
                    ft.DataColumn(
                        ft.Container(
                            content=ft.Text(
                                (
                                    {
                                        "link_up": "lu",
                                        "func_location": "fl",
                                        "date_field": "date",
                                        "shift": "shift",
                                    }.get(name, name)
                                ).upper(),
                                size=11,
                                weight=ft.FontWeight.W_600,
                            ),
                            width=self._get_column_width(name),
                        )
                    )
                    for name in self._fieldnames
                ],
                rows=self._build_rows(self._filtered_rows_data),
                border=ft.border.all(1, ft.Colors.BLACK12),
                heading_row_color=ft.Colors.BLUE_GREY_50,
                data_row_max_height=100,
                data_row_min_height=40,
                heading_row_height=34,
                vertical_lines=ft.BorderSide(1, ft.Colors.BLACK12),
                horizontal_lines=ft.BorderSide(1, ft.Colors.BLACK12),
                column_spacing=15,
                width=900,
            )

            self._content_container = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            [
                                self._filter_tf,
                                ft.Text(str(self.csv_path), size=11, italic=True),
                            ],
                        ),
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[self._dt],
                                        scroll=ft.ScrollMode.AUTO,
                                        alignment=ft.MainAxisAlignment.END,
                                    )
                                ],
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                            expand=True,
                        ),
                    ],
                    expand=True,
                    spacing=8,
                    scroll=None,
                    alignment=ft.MainAxisAlignment.START,
                ),
                width=1200,
                height=650,
                padding=ft.padding.all(12),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10,
                expand=True,
            )

            self._title_text = ft.Text(
                f"{self.title} (showing {len(self._rows_data)} of {total_rows} rows)"
            )

            self._dlg = ft.AlertDialog(
                modal=True,
                title=self._title_text,
                content=self._content_container,
                actions=[
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                "Close",
                                on_click=self.close,
                                style=ft.ButtonStyle(color=SECONDARY),
                            ),
                            ft.ElevatedButton(
                                "Export",
                                on_click=self._on_export_click,
                                color=ON_COLOR,
                                bgcolor=PRIMARY,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=self.close,
            )

            try:
                page.on_resize = self._on_resize
            except Exception:
                pass

            self._apply_responsive_size()
            self._apply_column_widths()

            try:
                page.open(self._dlg)
            except Exception:
                page.dialog = self._dlg
                self._dlg.open = True
                page.update()

        except Exception as ex:
            snack(page, f"Failed to read history.csv: {ex}", kind="error")

    def _read_filtered_rows(self, q: str) -> tuple[int, list[dict]]:
        """Stream-read the full CSV and return (matches_total, last_matches)."""
        q = str(q or "").strip()
        if not q:
            return 0, []

        max_rows = self.max_rows if self.max_rows > 0 else 1000
        tail = deque(maxlen=max_rows)
        matches_total = 0

        with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if self._row_matches(row, q):
                    matches_total += 1
                    tail.append(row)

        return matches_total, list(tail)

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
            snack(self.page, f"Failed to open file dialog: {ex}", kind="error")

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

            snack(self.page, f"Export successful: {p}", kind="success")
        except Exception as ex:
            snack(self.page, f"Failed to export CSV: {ex}", kind="error")

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
                cells.append(
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(value, size=11),
                            width=self._get_column_width(col),
                        )
                    )
                )
            out_rows.append(ft.DataRow(cells=cells))
        return out_rows

    def _apply_filter(self, _e=None):
        try:
            q = str(getattr(self._filter_tf, "value", "") or "").strip()

            # Empty query: restore the initial tail view.
            if not q:
                self._rows_data = list(self._base_rows_data)
                self._filtered_rows_data = list(self._base_rows_data)
                if self._title_text is not None:
                    self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {self._total_rows} rows)"
                if self._dlg is not None:
                    try:
                        self._dlg.update()
                    except Exception:
                        pass
            else:
                # Option A: stream-read the full CSV and filter across the entire file.
                matches_total, matches_tail = self._read_filtered_rows(q)
                self._filtered_rows_data = list(matches_tail)
                if self._title_text is not None:
                    self._title_text.value = f"{self.title} (showing {len(self._filtered_rows_data)} of {matches_total} matches)"
                if self._dlg is not None:
                    try:
                        self._dlg.update()
                    except Exception:
                        pass

            if self._dt is not None:
                self._dt.rows = self._build_rows(self._filtered_rows_data)
                self._apply_column_widths()
                try:
                    self._dt.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _get_column_width(self, col_name: str) -> int:
        name = str(col_name or "")
        if name in self._stretch_columns:
            return int(self._stretch_width_px)
        return int(self._fixed_col_widths.get(name, self._default_fixed_width_px))

    def _recompute_stretch_width(self):
        if not self._fieldnames:
            return

        stretch_cols = [c for c in self._fieldnames if c in self._stretch_columns]
        if not stretch_cols:
            return

        dt_width = 900
        try:
            if self._dt is not None and getattr(self._dt, "width", None):
                dt_width = int(getattr(self._dt, "width") or 900)
        except Exception:
            dt_width = 900

        fixed_cols = [c for c in self._fieldnames if c not in self._stretch_columns]
        fixed_sum = 0
        for c in fixed_cols:
            fixed_sum += int(
                self._fixed_col_widths.get(c, self._default_fixed_width_px)
            )

        spacing = 0
        try:
            if self._dt is not None:
                spacing = int(getattr(self._dt, "column_spacing", 0) or 0)
        except Exception:
            spacing = 0

        total_spacing = max(0, (len(self._fieldnames) - 1) * spacing)
        remaining = dt_width - fixed_sum - total_spacing - int(self._width_padding_px)
        per = int(remaining / max(1, len(stretch_cols)))
        self._stretch_width_px = max(int(self._min_stretch_width_px), per)

    def _apply_column_widths(self):
        if self._dt is None:
            return

        self._recompute_stretch_width()

        try:
            for i, col_name in enumerate(self._fieldnames):
                try:
                    col_obj = self._dt.columns[i]
                    label = getattr(col_obj, "label", None)
                    if isinstance(label, ft.Container):
                        label.width = self._get_column_width(col_name)
                except Exception:
                    pass

            for row in self._dt.rows or []:
                try:
                    for i, col_name in enumerate(self._fieldnames):
                        cell = row.cells[i]
                        content = getattr(cell, "content", None)
                        if isinstance(content, ft.Container):
                            content.width = self._get_column_width(col_name)
                except Exception:
                    pass

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

            self._apply_column_widths()

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
