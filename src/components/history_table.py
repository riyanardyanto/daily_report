from __future__ import annotations

import asyncio
import csv
import re
from collections import deque
from datetime import date as _date
from pathlib import Path

import flet as ft

from src.services.config_service import get_history_sync_config, get_ui_config
from src.services.history_db_adapter import (
    cleanup_sync_files,
    export_history_db_to_csv,
    manual_sync,
    publish_all_history_to_sync,
    read_history_filtered_tail,
    read_history_filtered_tail_no_count,
    read_history_tail,
)
from src.utils.theme import DANGER, ON_COLOR, PRIMARY
from src.utils.ui_helpers import open_dialog, snack


class HistoryTableDialog:
    def __init__(
        self,
        *,
        page: ft.Page,
        csv_path: Path,
        db_path: Path | None = None,
        title: str = "History Table",
        hidden_columns: set[str] | None = None,
        export_default_name: str = "history_export.csv",
        max_rows: int | None = None,
        filter_no_count: bool | None = None,
    ):
        self.page = page
        self.csv_path = Path(csv_path)
        self.db_path = Path(db_path) if db_path is not None else None
        self.title = title
        self.hidden_columns = set(hidden_columns or set())
        self.export_default_name = export_default_name

        # Prefer SQLite when available.
        self._use_sqlite: bool = bool(self.db_path is not None)

        ui_cfg, _err = get_ui_config()
        if max_rows is None:
            max_rows = getattr(ui_cfg, "history_max_rows", 500)

        if filter_no_count is None:
            filter_no_count = getattr(ui_cfg, "history_filter_no_count", None)
        if filter_no_count is None:
            filter_no_count = self._use_sqlite

        self._filter_no_count: bool = bool(filter_no_count)

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

        # Export behavior
        # - view: export only what's currently displayed (fast)
        # - all: export all rows (or all matches if a filter query exists)
        self._export_mode: str = "view"

        # Wire file picker callbacks once.
        self._file_picker.on_result = self._on_export_result

    def _sort_rows(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []

        def _parse_int(v) -> int:
            try:
                s = str(v or "").strip()
                if not s:
                    return 0
                return int(float(s))
            except Exception:
                return 0

        def _parse_date(v) -> _date:
            try:
                s = str(v or "").strip()
                if not s:
                    return _date.min
                return _date.fromisoformat(s)
            except Exception:
                return _date.min

        def _shift_key(v) -> tuple[int, str]:
            s = str(v or "").strip()
            s_l = s.lower()
            if not s_l:
                # Empty shift goes last.
                return (10000, "")
            if "all" in s_l and "shift" in s_l:
                # Keep "All Shifts" after numbered shifts.
                return (9999, s_l)
            parts = [p for p in s_l.replace("-", " ").split() if p]
            for p in parts:
                try:
                    # Descending shift number: Shift 3 before Shift 2 before Shift 1
                    return (-int(p), s_l)
                except Exception:
                    continue
            # Non-numeric shift labels: place after numbered shifts.
            return (0, s_l)

        def _key(row: dict) -> tuple:
            r = row or {}
            d = _parse_date(r.get("date_field", ""))
            # Sort date descending (newest first). Missing/invalid dates go last.
            date_key = -int(getattr(d, "toordinal", lambda: 0)() or 0)
            sh = _shift_key(r.get("shift", ""))
            saved_at = str(r.get("saved_at", "") or "")
            save_id = str(r.get("save_id", "") or "")
            card_i = _parse_int(r.get("card_index", ""))
            detail_i = _parse_int(r.get("detail_index", ""))
            action_i = _parse_int(r.get("action_index", ""))
            return (date_key, sh, saved_at, save_id, card_i, detail_i, action_i)

        try:
            return sorted(list(rows), key=_key)
        except Exception:
            return list(rows)

    def _on_publish_all_history_click(self, _e=None):
        page = self.page
        if page is None:
            return

        def _close(_ev=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(_ev=None):
            _close()
            snack(page, "Publishing full history…", kind="warning")

            async def _run_publish():
                try:

                    def _worker():
                        return publish_all_history_to_sync()

                    ok, msg = await asyncio.to_thread(_worker)
                    snack(page, msg, kind="success" if ok else "error")
                except Exception as ex:
                    snack(page, f"Publish failed: {ex}", kind="error")

            runner = getattr(page, "run_task", None)
            if callable(runner):
                try:
                    runner(_run_publish)
                    return
                except Exception:
                    pass

            try:
                ok, msg = publish_all_history_to_sync()
                snack(page, msg, kind="success" if ok else "error")
            except Exception as ex:
                snack(page, f"Publish failed: {ex}", kind="error")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Publish full history"),
            content=ft.Text(
                "This will export ALL local history to the shared sync folder as a single file. "
                "Use this once when onboarding a new PC. Continue?"
            ),
            actions=[
                ft.ElevatedButton(
                    "Cancel",
                    on_click=_close,
                    color=ON_COLOR,
                    bgcolor=DANGER,
                ),
                ft.ElevatedButton(
                    "Publish",
                    on_click=_confirm,
                    bgcolor=ft.Colors.INDIGO_600,
                    color=ON_COLOR,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=_close,
        )

        open_dialog(page, dlg)

    def _on_cleanup_sync_files_click(self, _e=None):
        page = self.page
        if page is None:
            return

        sync_cfg, _cfg_err = get_history_sync_config()
        retention_days = int(getattr(sync_cfg, "retention_days", 30) or 30)
        keep_latest_fullsync = int(getattr(sync_cfg, "keep_latest_fullsync", 1) or 1)

        def _close(_ev=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(_ev=None):
            _close()
            snack(page, "Cleaning up sync files…", kind="warning")

            async def _run_cleanup():
                try:

                    def _worker():
                        return cleanup_sync_files(
                            retention_days=retention_days,
                            keep_latest_fullsync=keep_latest_fullsync,
                        )

                    ok, msg = await asyncio.to_thread(_worker)
                    snack(page, msg, kind="success" if ok else "error")
                except Exception as ex:
                    snack(page, f"Cleanup failed: {ex}", kind="error")

            runner = getattr(page, "run_task", None)
            if callable(runner):
                try:
                    runner(_run_cleanup)
                    return
                except Exception:
                    pass

            try:
                ok, msg = cleanup_sync_files(
                    retention_days=retention_days,
                    keep_latest_fullsync=keep_latest_fullsync,
                )
                snack(page, msg, kind="success" if ok else "error")
            except Exception as ex:
                snack(page, f"Cleanup failed: {ex}", kind="error")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Clean up sync files"),
            content=ft.Text(
                "This will move old sync_*.json/fullsync_*.json into an 'archive' subfolder (no deletion). "
                f"Archive files older than {retention_days} days and keep {keep_latest_fullsync} newest fullsync file(s). Continue?"
            ),
            actions=[
                ft.ElevatedButton(
                    "Cancel",
                    on_click=_close,
                    color=ON_COLOR,
                    bgcolor=DANGER,
                ),
                ft.ElevatedButton(
                    "Clean up",
                    on_click=_confirm,
                    bgcolor=ft.Colors.DEEP_ORANGE_600,
                    color=ON_COLOR,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=_close,
        )

        open_dialog(page, dlg)

    def show(self):
        page = self.page
        if page is None:
            return

        if self._use_sqlite and self.db_path is not None:
            if not self.db_path.exists():
                # When running in Local+Sync mode, the adapter uses a local DB and
                # the legacy shared-file path may not exist. Allow opening anyway.
                snack(
                    page,
                    f"History DB not found: {self.db_path} (using local cache)",
                    kind="warning",
                )
        else:
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
            # Final size is set by _apply_responsive_size().
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
                        ft.ElevatedButton(
                            "Publish all history",
                            on_click=self._on_publish_all_history_click,
                            color=ON_COLOR,
                            bgcolor=ft.Colors.INDIGO_600,
                        )
                        if (self._use_sqlite and self.db_path is not None)
                        else ft.Container(),
                        ft.ElevatedButton(
                            "Clean up sync files",
                            on_click=self._on_cleanup_sync_files_click,
                            color=ON_COLOR,
                            bgcolor=ft.Colors.DEEP_ORANGE_600,
                        )
                        if (self._use_sqlite and self.db_path is not None)
                        else ft.Container(),
                        ft.TextButton(
                            "Close",
                            on_click=self.close,
                            style=ft.ButtonStyle(color=ON_COLOR, bgcolor=DANGER),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                    wrap=True,
                    run_spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=self.close,
        )

        open_dialog(page, self._dlg)

        # Apply responsive sizing immediately (even while loading) so actions
        # don't get pushed off-screen on small windows.
        try:
            self._apply_responsive_size()
        except Exception:
            pass

        # Some runtimes don't have correct page dimensions until after the
        # first UI frame; schedule a second layout pass shortly after opening.
        try:
            runner = getattr(page, "run_task", None)
            if callable(runner):

                async def _post_open_layout():
                    try:
                        await asyncio.sleep(0.05)
                        self._apply_responsive_size()
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
                    except Exception:
                        pass

                runner(_post_open_layout)
        except Exception:
            pass

        async def _load_async():
            try:
                # Start sync in the background so opening the dialog is fast.
                # We'll refresh the table after sync completes.
                sync_task: asyncio.Task | None = None
                if self._use_sqlite and self.db_path is not None:
                    try:
                        try:
                            loading_text.value = (
                                "Loading history… (syncing in background)"
                            )
                            loading_text.update()
                        except Exception:
                            pass

                        sync_task = asyncio.create_task(asyncio.to_thread(manual_sync))
                    except Exception:
                        sync_task = None

                def _read_source():
                    max_rows = self.max_rows if self.max_rows > 0 else 1000
                    if self._use_sqlite and self.db_path is not None:
                        return read_history_tail(db_path=self.db_path, limit=max_rows)

                    with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        fieldnames = list(reader.fieldnames or [])
                        tail = deque(maxlen=max_rows)
                        total_rows = 0
                        for row in reader:
                            total_rows += 1
                            tail.append(row)
                        rows_data = list(tail)
                    return fieldnames, total_rows, rows_data

                fieldnames, total_rows, rows_data = await asyncio.to_thread(
                    _read_source
                )

                self._total_rows = int(total_rows)
                if self._use_sqlite and self.db_path is not None:
                    sorted_rows = list(rows_data)
                else:
                    sorted_rows = self._sort_rows(list(rows_data))
                self._base_rows_data = list(sorted_rows)

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
                self._rows_data = list(sorted_rows)
                self._filtered_rows_data = list(sorted_rows)

                self._prev_on_resize = getattr(page, "on_resize", None)

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
                                ft.Text(
                                    str(
                                        self.db_path
                                        if self._use_sqlite
                                        else self.csv_path
                                    ),
                                    size=11,
                                    italic=True,
                                ),
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
                    self._content_container.expand = True

                # Update existing dialog instead of creating a new one.
                if self._title_text is not None:
                    self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {total_rows} rows)"

                if self._dlg is not None:
                    controls: list[ft.Control] = [
                        ft.ElevatedButton(
                            "Publish all history",
                            on_click=self._on_publish_all_history_click,
                            color=ON_COLOR,
                            bgcolor=ft.Colors.INDIGO_600,
                        )
                    ]
                    if self._use_sqlite and self.db_path is not None:
                        controls.append(
                            ft.ElevatedButton(
                                "Clean up sync files",
                                on_click=self._on_cleanup_sync_files_click,
                                color=ON_COLOR,
                                bgcolor=ft.Colors.DEEP_ORANGE_600,
                            )
                        )
                    controls.append(
                        ft.ElevatedButton(
                            "Export",
                            on_click=self._on_export_click,
                            color=ON_COLOR,
                            bgcolor=PRIMARY,
                        )
                    )
                    controls.append(
                        ft.ElevatedButton(
                            "Close",
                            on_click=self.close,
                            color=ON_COLOR,
                            bgcolor=DANGER,
                        )
                    )
                    self._dlg.actions = [
                        ft.Row(
                            controls=controls,
                            alignment=ft.MainAxisAlignment.END,
                            spacing=8,
                            wrap=True,
                            run_spacing=8,
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

                # After initial render, wait for background sync and refresh.
                if sync_task is not None:

                    async def _after_sync_refresh():
                        try:
                            imported, exported = await sync_task

                            # If dialog closed, do nothing.
                            try:
                                if self._dlg is None or not bool(
                                    getattr(self._dlg, "open", False)
                                ):
                                    return
                            except Exception:
                                return

                            # If user is actively filtering, avoid rewriting rows.
                            q_now = ""
                            try:
                                q_now = str(
                                    getattr(self._filter_tf, "value", "") or ""
                                ).strip()
                            except Exception:
                                q_now = ""

                            if imported > 0 and not q_now:
                                try:
                                    max_rows = (
                                        self.max_rows if self.max_rows > 0 else 1000
                                    )
                                    fn2, total2, rows2 = await asyncio.to_thread(
                                        read_history_tail,
                                        db_path=self.db_path,
                                        limit=max_rows,
                                    )
                                    self._total_rows = int(total2)
                                    self._base_rows_data = list(rows2)
                                    self._rows_data = list(rows2)
                                    self._filtered_rows_data = list(rows2)
                                    if fn2:
                                        self._fieldnames = [
                                            c
                                            for c in fn2
                                            if c not in self.hidden_columns
                                        ]

                                    if self._dt is not None:
                                        # Rebuild columns if needed, otherwise refresh rows.
                                        if len(self._dt.columns or []) != len(
                                            self._fieldnames
                                        ):
                                            self._dt.columns = [
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
                                                        width=self._get_column_width(
                                                            name
                                                        ),
                                                    )
                                                )
                                                for name in self._fieldnames
                                            ]

                                        widths = self._get_column_widths_snapshot()
                                        self._dt.rows = self._build_rows(
                                            self._filtered_rows_data,
                                            widths,
                                        )
                                        try:
                                            self._dt.update()
                                        except Exception:
                                            pass

                                    if self._title_text is not None:
                                        self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {self._total_rows} rows)"
                                except Exception:
                                    pass
                            else:
                                # Still update the title line to reflect sync completion.
                                try:
                                    if self._title_text is not None:
                                        self._title_text.value = f"{self.title} (showing {len(self._filtered_rows_data)} of {self._total_rows} rows)"
                                except Exception:
                                    pass

                            # Friendly message (non-blocking).
                            try:
                                if imported or exported:
                                    snack(
                                        page,
                                        f"Sync done: imported {imported}, exported {exported}",
                                        kind="success",
                                    )
                            except Exception:
                                pass

                            try:
                                self._apply_responsive_size()
                            except Exception:
                                pass
                            try:
                                page.update()
                            except Exception:
                                pass
                        except Exception:
                            # Sync failures should never block viewing history.
                            return

                    try:
                        runner2 = getattr(page, "run_task", None)
                        if callable(runner2):
                            runner2(_after_sync_refresh)
                        else:
                            asyncio.create_task(_after_sync_refresh())
                    except Exception:
                        pass

            except Exception as ex:
                snack(page, f"Failed to read history: {ex}", kind="error")

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
            max_rows = self.max_rows if self.max_rows > 0 else 1000
            if self._use_sqlite and self.db_path is not None:
                # Avoid running sync here (blocking) to prevent long UI hangs.
                fieldnames, total_rows, rows_data = read_history_tail(
                    db_path=self.db_path,
                    limit=max_rows,
                )
            else:
                with self.csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    fieldnames = list(reader.fieldnames or [])
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
            sorted_rows = self._sort_rows(list(rows_data))
            self._base_rows_data = list(sorted_rows)

            if not fieldnames:
                snack(page, "History CSV has no header", kind="warning")
                return

            visible_fields = [c for c in fieldnames if c not in self.hidden_columns]
            if not visible_fields:
                snack(page, "History CSV has no columns to display", kind="warning")
                return

            self._fieldnames = visible_fields
            self._rows_data = list(sorted_rows)
            self._filtered_rows_data = list(sorted_rows)

            self._prev_on_resize = getattr(page, "on_resize", None)

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
                            ft.Text(
                                str(
                                    self.db_path if self._use_sqlite else self.csv_path
                                ),
                                size=11,
                                italic=True,
                            ),
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
                self._content_container.expand = True

            if self._title_text is not None:
                self._title_text.value = f"{self.title} (showing {len(self._rows_data)} of {total_rows} rows)"

            if self._dlg is not None:
                controls: list[ft.Control] = [
                    ft.ElevatedButton(
                        "Close",
                        on_click=self.close,
                        color=ON_COLOR,
                        bgcolor=DANGER,
                    )
                ]
                if self._use_sqlite and self.db_path is not None:
                    pass
                controls.append(
                    ft.ElevatedButton(
                        "Export",
                        on_click=self._on_export_click,
                        color=ON_COLOR,
                        bgcolor=PRIMARY,
                    )
                )
                self._dlg.actions = [
                    ft.Row(
                        controls=controls,
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                        wrap=True,
                        run_spacing=8,
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
            snack(page, f"Failed to read history: {ex}", kind="error")

    def _read_filtered_rows(self, q: str) -> tuple[int | None, list[dict]]:
        """Stream-read the full CSV and return (matches_total, last_matches)."""
        q = str(q or "").strip()
        if not q:
            return 0, []

        if self._use_sqlite and self.db_path is not None:
            fields = list(self._fieldnames or [])
            max_rows = self.max_rows if self.max_rows > 0 else 1000
            if self._filter_no_count:
                return (
                    None,
                    read_history_filtered_tail_no_count(
                        db_path=self.db_path,
                        q=q,
                        fieldnames=fields,
                        limit=max_rows,
                    ),
                )
            return read_history_filtered_tail(
                db_path=self.db_path,
                q=q,
                fieldnames=fields,
                limit=max_rows,
            )

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
    ) -> tuple[int | None, list[dict]]:
        """Thread-friendly variant: uses provided fieldnames snapshot."""
        q = str(q or "").strip()
        if not q:
            return 0, []

        if self._use_sqlite and self.db_path is not None:
            max_rows = self.max_rows if self.max_rows > 0 else 1000
            if self._filter_no_count:
                return (
                    None,
                    read_history_filtered_tail_no_count(
                        db_path=self.db_path,
                        q=q,
                        fieldnames=list(fieldnames or []),
                        limit=max_rows,
                    ),
                )
            return read_history_filtered_tail(
                db_path=self.db_path,
                q=q,
                fieldnames=list(fieldnames or []),
                limit=max_rows,
            )

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
        page = self.page
        self._ensure_file_picker_added()

        # For SQLite, let the user choose export scope.
        if self._use_sqlite and self.db_path is not None:

            def _close_choice(_e=None):
                try:
                    if dlg is not None:
                        dlg.open = False
                    page.update()
                except Exception:
                    pass

            def _pick(mode: str):
                try:
                    self._export_mode = str(mode or "view")
                except Exception:
                    self._export_mode = "view"
                try:
                    _close_choice()
                finally:
                    try:
                        self._file_picker.save_file(
                            dialog_title="Export history CSV",
                            file_name=self.export_default_name,
                            allowed_extensions=["csv"],
                        )
                        self.close()
                    except Exception as ex:
                        snack(
                            self.page, f"Failed to open file dialog: {ex}", kind="error"
                        )

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Export"),
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Choose what to export:",
                                size=12,
                            ),
                            ft.Text(
                                "- Current view exports only the rows shown (fast).\n"
                                "- All rows exports from SQLite (may take longer).",
                                size=11,
                                italic=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=ft.padding.all(12),
                    bgcolor=ft.Colors.WHITE,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=10,
                ),
                actions=[
                    ft.Row(
                        controls=[
                            ft.ElevatedButton(
                                "Cancel",
                                on_click=_close_choice,
                                color=ON_COLOR,
                                bgcolor=DANGER,
                            ),
                            ft.ElevatedButton(
                                "Current view",
                                on_click=lambda _e: _pick("view"),
                                color=ON_COLOR,
                                bgcolor=PRIMARY,
                            ),
                            ft.ElevatedButton(
                                "All rows",
                                on_click=lambda _e: _pick("all"),
                                color=ON_COLOR,
                                bgcolor=PRIMARY,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=_close_choice,
            )

            open_dialog(page, dlg)
            return

        # CSV mode: keep current behavior (exports current view snapshot).
        try:
            self._export_mode = "view"
        except Exception:
            pass
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

            export_mode = str(getattr(self, "_export_mode", "view") or "view").strip()
            use_sqlite = bool(self._use_sqlite and self.db_path is not None)
            q_snapshot = ""
            try:
                q_snapshot = str(getattr(self._filter_tf, "value", "") or "").strip()
            except Exception:
                q_snapshot = ""

            try:
                snack(page, "Exporting…", kind="warning")
            except Exception:
                pass

            async def _export_async():
                try:

                    def _worker_write():
                        # If using SQLite and user asked for full export, stream from DB.
                        if (
                            use_sqlite
                            and export_mode == "all"
                            and self.db_path is not None
                        ):
                            exported, matches_total = export_history_db_to_csv(
                                db_path=self.db_path,
                                export_path=Path(p),
                                visible_fieldnames=fieldnames,
                                q=q_snapshot,
                            )
                            return exported, matches_total

                        # Default: export current view snapshot.
                        with open(p, "w", newline="", encoding="utf-8-sig") as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writeheader()
                            for row_obj in rows_data:
                                out = {
                                    c: str((row_obj or {}).get(c, "") or "")
                                    for c in fieldnames
                                }
                                writer.writerow(out)
                        return len(rows_data), len(rows_data)

                    exported, matches_total = await asyncio.to_thread(_worker_write)

                    if use_sqlite and export_mode == "all":
                        snack(
                            page,
                            f"Export successful: {p} ({exported} of {matches_total} rows)",
                            kind="success",
                        )
                    else:
                        snack(page, f"Export successful: {p}", kind="success")
                except Exception as ex:
                    snack(page, f"Failed to export CSV: {ex}", kind="error")

            runner = getattr(page, "run_task", None)
            if callable(runner):
                runner(_export_async)
            else:
                # Fallback: blocking export
                if use_sqlite and export_mode == "all" and self.db_path is not None:
                    exported, matches_total = export_history_db_to_csv(
                        db_path=self.db_path,
                        export_path=Path(p),
                        visible_fieldnames=fieldnames,
                        q=q_snapshot,
                    )
                    snack(
                        page,
                        f"Export successful: {p} ({exported} of {matches_total} rows)",
                        kind="success",
                    )
                else:
                    with open(p, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        for row_obj in rows_data:
                            out = {
                                c: str((row_obj or {}).get(c, "") or "")
                                for c in fieldnames
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
            row_color = None
            try:
                shift_v = str((row_obj or {}).get("shift", "") or "").strip()
                shift_l = shift_v.lower()
                if shift_l:
                    if "all" in shift_l and "shift" in shift_l:
                        row_color = ft.Colors.INDIGO_50
                    else:
                        m = re.search(r"\d+", shift_l)
                        n = int(m.group(0)) if m else None
                        if n == 1:
                            row_color = ft.Colors.RED_50
                        elif n == 2:
                            row_color = ft.Colors.GREEN_50
                        elif n == 3:
                            row_color = ft.Colors.YELLOW_50
                        else:
                            row_color = ft.Colors.BLUE_GREY_50
            except Exception:
                row_color = None

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
            if row_color is None:
                out_rows.append(ft.DataRow(cells=cells))
            else:
                out_rows.append(ft.DataRow(cells=cells, color=row_color))
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

                    if self._use_sqlite and self.db_path is not None:
                        self._filtered_rows_data = list(matches_tail)
                    else:
                        self._filtered_rows_data = self._sort_rows(list(matches_tail))

                    if self._title_text is not None:
                        if matches_total is None:
                            self._title_text.value = f"{self.title} (showing {len(self._filtered_rows_data)} rows)"
                        else:
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
            if self._use_sqlite and self.db_path is not None:
                self._filtered_rows_data = list(matches_tail)
            else:
                self._filtered_rows_data = self._sort_rows(list(matches_tail))
            if self._title_text is not None:
                if matches_total is None:
                    self._title_text.value = (
                        f"{self.title} (showing {len(self._filtered_rows_data)} rows)"
                    )
                else:
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

    def _get_page_window_size(self) -> tuple[int, int]:
        page = self.page
        w = None
        h = None
        try:
            win = getattr(page, "window", None)
            if win is not None:
                w = getattr(win, "width", None)
                h = getattr(win, "height", None)
        except Exception:
            w = None
            h = None

        if not w:
            try:
                w = getattr(page, "width", None)
            except Exception:
                w = None
        if not h:
            try:
                h = getattr(page, "height", None)
            except Exception:
                h = None

        return int(w or 1200), int(h or 900)

    def _apply_responsive_size(self):
        page = self.page
        if self._content_container is None:
            return

        try:
            w, h = self._get_page_window_size()

            # Clamp sizes to the current window so the dialog (and its action
            # buttons) never overflow off-screen.
            # Leave room for title + actions + outer padding.
            max_w = max(280, w - 40)
            max_h = max(220, h - 220)
            target_w = int(w * 0.92)
            target_h = int(h * 0.78)

            self._content_container.width = min(max_w, max(320, target_w))
            self._content_container.height = min(max_h, max(280, target_h))

            if self._dt is not None:
                self._dt.width = max(240, int(self._content_container.width * 0.98))
                self._apply_column_widths()
                try:
                    self._dt.update()
                except Exception:
                    pass
            try:
                self._content_container.update()
            except Exception:
                pass

            # When the dialog is first opened, explicit updates help apply the
            # size change before the user resizes the window.
            try:
                if self._dlg is not None:
                    self._dlg.update()
            except Exception:
                pass
            try:
                if page is not None:
                    page.update()
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
