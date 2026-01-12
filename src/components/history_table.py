from __future__ import annotations

import asyncio
import csv
from collections import deque
from pathlib import Path

import flet as ft

from src.services.config_service import get_ui_config
from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY
from src.utils.ui_helpers import open_dialog, snack


class HistoryTableDialog:
    def __init__(
        self,
        *,
        page: ft.Page,
        csv_path: Path,
        title: str = "History Table",
        hidden_columns: set[str] | None = None,
        export_default_name: str = "history_export.csv",
        max_rows: int | None = None,
    ):
        self.page = page
        self.csv_path = Path(csv_path)
        self.title = title
        self.hidden_columns = set(hidden_columns or set())
        self.export_default_name = export_default_name

        if max_rows is None:
            ui_cfg, _err = get_ui_config()
            max_rows = getattr(ui_cfg, "history_max_rows", 500)

        self.max_rows = int(max_rows or 0) if max_rows is not None else 500

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

        # Cache for computed column widths to avoid repeated per-cell work.
        self._last_column_widths: dict[str, int] | None = None

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

        # Used to ignore stale async filter results.
        self._filter_seq: int = 0

    def show(self):
        page = self.page
        if page is None:
            return

        if not self.csv_path.exists():
            snack(page, f"History not found: {self.csv_path}", kind="warning")
            return

        # Open a lightweight dialog immediately (prevents perceived "hang").
        self._title_text = ft.Text(f"{self.title} (loading…)")
        loading_ring = ft.ProgressRing()
        loading_text = ft.Text("Loading history…", size=12)

        loading_overlay = ft.Container(
            content=ft.Column(
                controls=[loading_ring, loading_text],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
                spacing=10,
            ),
            alignment=ft.alignment.center,
            expand=True,
            visible=True,
        )

        self._content_container = ft.Container(
            content=ft.Stack(
                controls=[
                    ft.Container(expand=True),
                    loading_overlay,
                ],
                expand=True,
            ),
            width=900,
            height=500,
            padding=ft.padding.all(12),
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=10,
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
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=self.close,
        )

        open_dialog(page, self._dlg)

        async def _load_async():
            try:

                def _read_csv():
                    with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        fieldnames = list(reader.fieldnames or [])
                        max_rows = self.max_rows if self.max_rows > 0 else 1000
                        tail = deque(maxlen=max_rows)
                        total_rows = 0
                        for row in reader:
                            total_rows += 1
                            tail.append(row)
                        rows_data = list(tail)
                    return fieldnames, total_rows, rows_data

                fieldnames, total_rows, rows_data = await asyncio.to_thread(_read_csv)

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
                    rows=self._build_rows(
                        self._filtered_rows_data,
                        self._get_column_widths_snapshot(),
                    ),
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

                new_content = ft.Column(
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
                )

                # Keep the same container instance to avoid UID/assert issues.
                if self._content_container is not None:
                    self._content_container.content = new_content
                    self._content_container.width = 1200
                    self._content_container.height = 650
                    self._content_container.expand = True

                # Update existing dialog instead of creating a new one.
                if self._title_text is not None:
                    self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {total_rows} rows)"

                if self._dlg is not None:
                    self._dlg.actions = [
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
                    ]

                try:
                    page.on_resize = self._on_resize
                except Exception:
                    pass

                self._apply_responsive_size()
                self._apply_column_widths()

                try:
                    if self._content_container is not None:
                        self._content_container.update()
                except Exception:
                    pass

                try:
                    if self._dlg is not None:
                        self._dlg.update()
                except Exception:
                    pass

                try:
                    page.update()
                except Exception:
                    pass

            except Exception as ex:
                snack(page, f"Failed to read history.csv: {ex}", kind="error")

        # Run in background if available; otherwise run synchronously (may block).
        try:
            runner = getattr(page, "run_task", None)
            if callable(runner):
                # IMPORTANT: pass coroutine function (not coroutine object)
                runner(_load_async)
                return
        except Exception:
            pass

        # Fallback: synchronous load
        try:
            with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                max_rows = self.max_rows if self.max_rows > 0 else 1000
                tail = deque(maxlen=max_rows)
                total_rows = 0
                for row in reader:
                    total_rows += 1
                    tail.append(row)
                rows_data = list(tail)

            # Re-run the same setup path on the current thread by invoking the async logic body.
            # This keeps behavior consistent for older runtimes.
            # Note: no asyncio loop here; just perform the same steps inline.
            self._total_rows = int(total_rows)
            self._base_rows_data = list(rows_data)

            if not fieldnames:
                snack(page, "History CSV has no header", kind="warning")
                return

            visible_fields = [c for c in fieldnames if c not in self.hidden_columns]
            if not visible_fields:
                snack(page, "History CSV has no columns to display", kind="warning")
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
                rows=self._build_rows(
                    self._filtered_rows_data,
                    self._get_column_widths_snapshot(),
                ),
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

            new_content = ft.Column(
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
            )

            if self._content_container is not None:
                self._content_container.content = new_content
                self._content_container.width = 1200
                self._content_container.height = 650
                self._content_container.expand = True

            if self._title_text is not None:
                self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {total_rows} rows)"

            if self._dlg is not None:
                self._dlg.actions = [
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
                ]

            try:
                page.on_resize = self._on_resize
            except Exception:
                pass

            self._apply_responsive_size()
            self._apply_column_widths()

            try:
                if self._content_container is not None:
                    self._content_container.update()
            except Exception:
                pass

            try:
                if self._dlg is not None:
                    self._dlg.update()
            except Exception:
                pass
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

    def _read_filtered_rows_for_fields(
        self, q: str, fieldnames: list[str]
    ) -> tuple[int, list[dict]]:
        """Thread-friendly variant: uses provided fieldnames snapshot."""
        q = str(q or "").strip()
        if not q:
            return 0, []

        max_rows = self.max_rows if self.max_rows > 0 else 1000
        tail = deque(maxlen=max_rows)
        matches_total = 0

        q_l = q.lower()

        def _row_matches_fields(row_obj: dict) -> bool:
            try:
                for col in fieldnames:
                    v = str((row_obj or {}).get(col, "") or "")
                    if q_l in v.lower():
                        return True
            except Exception:
                return True
            return False

        with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if _row_matches_fields(row):
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
        page = self.page
        try:
            p = str(export_path or "").strip()
            if not p:
                return

            # Snapshot data on UI thread
            fieldnames = list(self._fieldnames or [])
            rows_data = list(self._filtered_rows_data or [])

            try:
                snack(page, "Exporting…", kind="warning")
            except Exception:
                pass

            async def _export_async():
                try:

                    def _worker_write():
                        with open(p, "w", newline="", encoding="utf-8-sig") as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writeheader()
                            for row_obj in rows_data:
                                out = {
                                    c: str((row_obj or {}).get(c, "") or "")
                                    for c in fieldnames
                                }
                                writer.writerow(out)

                    await asyncio.to_thread(_worker_write)
                    snack(page, f"Export successful: {p}", kind="success")
                except Exception as ex:
                    snack(page, f"Failed to export CSV: {ex}", kind="error")

            runner = getattr(page, "run_task", None)
            if callable(runner):
                runner(_export_async)
            else:
                # Fallback: blocking export
                with open(p, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row_obj in rows_data:
                        out = {
                            c: str((row_obj or {}).get(c, "") or "") for c in fieldnames
                        }
                        writer.writerow(out)
                snack(page, f"Export successful: {p}", kind="success")
        except Exception as ex:
            snack(page, f"Failed to export CSV: {ex}", kind="error")

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

    def _get_column_widths_snapshot(self) -> dict[str, int]:
        """Return a dict of column widths for current fieldnames."""
        widths: dict[str, int] = {}
        for col in self._fieldnames:
            try:
                widths[col] = int(self._get_column_width(col))
            except Exception:
                widths[col] = int(self._default_fixed_width_px)
        return widths

    def _build_rows(
        self, filtered: list[dict], widths: dict[str, int] | None = None
    ) -> list[ft.DataRow]:
        out_rows: list[ft.DataRow] = []
        if widths is None:
            widths = self._get_column_widths_snapshot()
        for row_obj in filtered:
            cells: list[ft.DataCell] = []
            for col in self._fieldnames:
                try:
                    value = str((row_obj or {}).get(col, "") or "")
                except Exception:
                    value = ""
                w = int(widths.get(col, self._default_fixed_width_px))
                cells.append(
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(value, size=11),
                            width=w,
                        )
                    )
                )
            out_rows.append(ft.DataRow(cells=cells))
        return out_rows

    def _apply_filter(self, _e=None):
        page = self.page
        try:
            q = str(getattr(self._filter_tf, "value", "") or "").strip()

            # Empty query: restore the initial tail view immediately.
            if not q:
                self._rows_data = list(self._base_rows_data)
                self._filtered_rows_data = list(self._base_rows_data)
                if self._title_text is not None:
                    self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {self._total_rows} rows)"
                if self._dt is not None:
                    widths = self._get_column_widths_snapshot()
                    self._dt.rows = self._build_rows(self._filtered_rows_data, widths)
                    try:
                        self._dt.update()
                    except Exception:
                        pass
                try:
                    if self._filter_tf is not None:
                        self._filter_tf.disabled = False
                        self._filter_tf.update()
                except Exception:
                    pass
                return

            # Non-empty query: run full-file filtering off the UI thread.
            self._filter_seq += 1
            seq = int(self._filter_seq)

            # Update title + disable input to signal work in progress.
            try:
                if self._title_text is not None:
                    self._title_text.value = f"{self.title} (filtering…)"
                if self._filter_tf is not None:
                    self._filter_tf.disabled = True
                if self._dlg is not None:
                    self._dlg.update()
            except Exception:
                pass

            fields_snapshot = list(self._fieldnames or [])
            q_snapshot = str(q)

            async def _filter_async():
                try:
                    matches_total, matches_tail = await asyncio.to_thread(
                        self._read_filtered_rows_for_fields, q_snapshot, fields_snapshot
                    )

                    # Ignore stale results.
                    if seq != self._filter_seq:
                        return

                    self._filtered_rows_data = list(matches_tail)

                    if self._title_text is not None:
                        self._title_text.value = f"{self.title} (showing {len(self._filtered_rows_data)} of {matches_total} matches)"

                    if self._dt is not None:
                        widths = self._get_column_widths_snapshot()
                        self._dt.rows = self._build_rows(
                            self._filtered_rows_data, widths
                        )
                        try:
                            self._dt.update()
                        except Exception:
                            pass

                    try:
                        if self._filter_tf is not None:
                            self._filter_tf.disabled = False
                            self._filter_tf.update()
                    except Exception:
                        pass

                    try:
                        if page is not None:
                            page.update()
                    except Exception:
                        pass
                except Exception as ex:
                    if seq != self._filter_seq:
                        return
                    try:
                        if self._title_text is not None:
                            self._title_text.value = f"{self.title} (filter failed)"
                        if self._filter_tf is not None:
                            self._filter_tf.disabled = False
                            self._filter_tf.update()
                    except Exception:
                        pass
                    try:
                        if page is not None:
                            snack(page, f"Filter failed: {ex}", kind="error")
                    except Exception:
                        pass

            # Use run_task if available; otherwise fall back to sync filtering.
            try:
                runner = getattr(page, "run_task", None)
                if callable(runner):
                    # IMPORTANT: pass coroutine function (not coroutine object)
                    runner(_filter_async)
                    return
            except Exception:
                pass

            # Sync fallback
            matches_total, matches_tail = self._read_filtered_rows(q_snapshot)
            if seq != self._filter_seq:
                return
            self._filtered_rows_data = list(matches_tail)
            if self._title_text is not None:
                self._title_text.value = f"{self.title} (showing {len(self._filtered_rows_data)} of {matches_total} matches)"
            if self._dt is not None:
                widths = self._get_column_widths_snapshot()
                self._dt.rows = self._build_rows(self._filtered_rows_data, widths)
                try:
                    self._dt.update()
                except Exception:
                    pass
            try:
                if self._filter_tf is not None:
                    self._filter_tf.disabled = False
                    self._filter_tf.update()
            except Exception:
                pass
        except Exception:
            try:
                if self._filter_tf is not None:
                    self._filter_tf.disabled = False
                    self._filter_tf.update()
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

        # Compute new widths and short-circuit if nothing changed.
        widths = self._get_column_widths_snapshot()
        if self._last_column_widths == widths:
            return
        self._last_column_widths = dict(widths)

        try:
            for i, col_name in enumerate(self._fieldnames):
                try:
                    col_obj = self._dt.columns[i]
                    label = getattr(col_obj, "label", None)
                    if isinstance(label, ft.Container):
                        label.width = int(
                            widths.get(col_name, self._default_fixed_width_px)
                        )
                except Exception:
                    pass

            for row in self._dt.rows or []:
                try:
                    for i, col_name in enumerate(self._fieldnames):
                        cell = row.cells[i]
                        content = getattr(cell, "content", None)
                        if isinstance(content, ft.Container):
                            content.width = int(
                                widths.get(col_name, self._default_fixed_width_px)
                            )
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
