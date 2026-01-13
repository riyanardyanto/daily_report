from __future__ import annotations

import asyncio
import csv

import flet as ft

from src.utils.file_lock import is_file_locked_windows
from src.utils.helpers import data_app_path, load_targets_csv
from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY
from src.utils.ui_helpers import open_dialog, snack


class TargetEditorDialog:
    def __init__(
        self,
        *,
        page: ft.Page,
        get_selected_shift=None,
        get_link_up=None,
        get_func_location=None,
        get_metrics_rows=None,
        set_metrics_targets=None,
    ):
        self.page = page
        self._get_selected_shift_cb = get_selected_shift
        self._get_link_up_cb = get_link_up
        self._get_func_location_cb = get_func_location
        self._get_metrics_rows_cb = get_metrics_rows
        self._set_metrics_targets_cb = set_metrics_targets

        self._dlg: ft.AlertDialog | None = None

    def show(self):
        page = self.page
        if page is None:
            return

        selected_shift = "Shift 1"
        try:
            if callable(self._get_selected_shift_cb):
                selected_shift = str(self._get_selected_shift_cb()).strip() or "Shift 1"
        except Exception:
            selected_shift = "Shift 1"

        link_up = "LU21"
        try:
            if callable(self._get_link_up_cb):
                link_up = str(self._get_link_up_cb() or "LU21").strip() or "LU21"
        except Exception:
            link_up = "LU21"

        func_location = "Packer"
        try:
            if callable(self._get_func_location_cb):
                func_location = (
                    str(self._get_func_location_cb() or "Packer").strip() or "Packer"
                )
        except Exception:
            func_location = "Packer"

        lu = (link_up[-2:] if len(link_up) >= 2 else link_up).lower()
        fl = (func_location[:4] if func_location else "").lower()
        filename = f"target_{fl}_{lu}.csv"
        folder_name = "data_app/targets"

        csv_path = data_app_path(filename, folder_name=folder_name)

        def _close_dialog(_e=None):
            try:
                if self._dlg is not None:
                    self._dlg.open = False
                    page.update()
            except Exception:
                pass

        # Snapshot metrics (used to create template if missing) on UI thread.
        metrics_for_template: list[str] = []
        try:
            if callable(self._get_metrics_rows_cb):
                rows = self._get_metrics_rows_cb() or []
                metrics_for_template = [
                    str(m).strip() for m, _t, _a in rows if str(m).strip()
                ]
        except Exception:
            metrics_for_template = []

        if not metrics_for_template:
            metrics_for_template = [
                "STOP",
                "L STOP",
                "PR",
                "UPTIME",
                "MTBF",
                "L MTBF",
                "UPDT",
                "PDT",
                "TRL",
            ]

        # Data loaded from CSV (populated asynchronously)
        fieldnames: list[str] = []
        metrics_order: list[str] = []
        table_values: dict[str, dict[str, str]] = {}
        shift_cols: list[str] = []

        # Build editable DataTable: store TextField refs per metric+shift
        cell_refs: dict[str, dict[str, ft.Ref[ft.TextField]]] = {}
        dt: ft.DataTable | None = None

        # Create dialog immediately with a loading UI.
        loading_ring = ft.ProgressRing(width=18, height=18, stroke_width=2)
        loading_text = ft.Text("Loading targets…", size=12)

        base_content = ft.Container(expand=True)
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

        content_host = ft.Stack(
            controls=[base_content, loading_overlay],
            expand=True,
        )

        paste_btn = ft.ElevatedButton(
            "Paste",
            on_click=lambda _e: None,
            color=ON_COLOR,
            bgcolor=SECONDARY,
            disabled=True,
        )
        save_btn = ft.ElevatedButton(
            "Save",
            on_click=lambda _e: None,
            color=ON_COLOR,
            bgcolor=PRIMARY,
            disabled=True,
        )

        self._dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit target"),
            content=ft.Container(
                content=content_host,
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
                            on_click=_close_dialog,
                            style=ft.ButtonStyle(color=SECONDARY),
                        ),
                        paste_btn,
                        save_btn,
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        open_dialog(page, self._dlg)

        def _make_cell(metric: str, shift: str, value: str) -> ft.DataCell:
            tf_ref: ft.Ref[ft.TextField] = ft.Ref()
            cell_refs.setdefault(metric, {})[shift] = tf_ref
            return ft.DataCell(
                ft.Container(
                    content=ft.TextField(
                        ref=tf_ref,
                        value=str(value or ""),
                        dense=True,
                        text_size=12,
                        text_align=ft.TextAlign.CENTER,
                        border=ft.InputBorder.NONE,
                        content_padding=ft.padding.symmetric(
                            horizontal=10, vertical=10
                        ),
                    ),
                    alignment=ft.alignment.center,
                    padding=ft.padding.symmetric(horizontal=0, vertical=0),
                    margin=ft.margin.only(left=0, right=0, top=0, bottom=0),
                    width=80,
                    height=32,
                )
            )

        def _build_datatable() -> ft.DataTable:
            cell_refs.clear()
            rows: list[ft.DataRow] = []
            for metric in metrics_order:
                cells: list[ft.DataCell] = [
                    ft.DataCell(ft.Text(metric, size=12, weight=ft.FontWeight.W_600))
                ]
                for sc in shift_cols:
                    cells.append(
                        _make_cell(metric, sc, table_values.get(metric, {}).get(sc, ""))
                    )
                rows.append(ft.DataRow(cells=cells))

            return ft.DataTable(
                columns=[ft.DataColumn(ft.Text("Metrics", size=12))]
                + [
                    ft.DataColumn(
                        ft.Text(sc, size=12),
                        heading_row_alignment=ft.MainAxisAlignment.CENTER,
                    )
                    for sc in shift_cols
                ],
                rows=rows,
                border=ft.border.all(1, ft.Colors.BLACK12),
                heading_row_color=ft.Colors.BLUE_GREY_50,
                data_row_max_height=40,
                data_row_min_height=40,
                heading_row_height=34,
                vertical_lines=ft.BorderSide(1, ft.Colors.BLACK12),
                horizontal_lines=ft.BorderSide(1, ft.Colors.BLACK12),
            )

        def _apply_matrix(matrix: list[list[str]]):
            if not matrix:
                snack(page, "Clipboard kosong", kind="warning")
                return

            matrix = [r for r in matrix if any((c or "").strip() for c in r)]
            if not matrix:
                snack(page, "Clipboard kosong", kind="warning")
                return

            try:
                first = [str(c or "").strip() for c in matrix[0]]
                if first and first[0].lower() in ("metrics", "metric"):
                    matrix = matrix[1:]
            except Exception:
                pass

            # Decide selected shift (used for 1-col pastes)
            paste_shift = selected_shift
            if paste_shift not in shift_cols:
                paste_shift = shift_cols[0] if shift_cols else "Shift 1"

            updated = 0

            def _set(metric: str, shift: str, value: str):
                nonlocal updated
                try:
                    ref = cell_refs.get(metric, {}).get(shift)
                    tf = getattr(ref, "current", None) if ref is not None else None
                    if tf is not None:
                        tf.value = str(value or "")
                        updated += 1
                except Exception:
                    pass

            # Case A: rows are (Metric, v) or (Metric, v1, v2, v3)
            if matrix and len(matrix[0]) >= 2:
                known = {m.strip().lower(): m for m in metrics_order}
                likely_metric_rows = 0
                for r in matrix[: min(5, len(matrix))]:
                    if r and str(r[0] or "").strip().lower() in known:
                        likely_metric_rows += 1
                if likely_metric_rows >= 1:
                    for r in matrix:
                        if not r:
                            continue
                        m_key = str(r[0] or "").strip().lower()
                        metric = known.get(m_key)
                        if not metric:
                            continue

                        values = [str(c or "").strip() for c in r[1:]]
                        if len(values) >= 3:
                            for i, sc in enumerate(shift_cols[:3]):
                                _set(metric, sc, values[i] if i < len(values) else "")
                        else:
                            _set(metric, paste_shift, values[0] if values else "")

                    try:
                        dt.update()
                    except Exception:
                        pass
                    snack(page, f"Paste successful ({updated} cell)", kind="success")
                    return

            # Case B: matrix is pure values without metric names
            height = len(matrix)
            width = max((len(r) for r in matrix), default=0)
            if height == len(metrics_order) and width >= 3:
                for row_idx, metric in enumerate(metrics_order):
                    r = matrix[row_idx]
                    for col_idx, sc in enumerate(shift_cols[:3]):
                        if col_idx < len(r):
                            _set(metric, sc, str(r[col_idx] or "").strip())
                try:
                    dt.update()
                except Exception:
                    pass
                snack(page, f"Paste successful ({updated} cell)", kind="success")
                return

            if height == len(metrics_order) and width == 1:
                for row_idx, metric in enumerate(metrics_order):
                    r = matrix[row_idx]
                    _set(metric, paste_shift, str(r[0] or "").strip() if r else "")
                try:
                    dt.update()
                except Exception:
                    pass
                snack(page, f"Paste successful ({updated} cell)", kind="success")
                return

            snack(
                page,
                "Paste format not recognized. Copy from Excel as: (Metrics + values) or a value matrix.",
                kind="warning",
            )

        def _parse_excel_clipboard(text: str) -> list[list[str]]:
            try:
                raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
                raw = raw.strip("\n")
                if not raw.strip():
                    return []
                lines = [ln for ln in raw.split("\n") if ln.strip() != ""]
                matrix: list[list[str]] = []
                for ln in lines:
                    matrix.append([c.strip() for c in ln.split("\t")])
                return matrix
            except Exception:
                return []

        def _on_paste(_e=None):
            if dt is None:
                return

            async def _paste_async():
                try:
                    clip = ""
                    try:
                        clip = await page.get_clipboard()
                    except Exception:
                        try:
                            clip = page.get_clipboard()
                        except Exception:
                            clip = ""
                    matrix = _parse_excel_clipboard(clip)
                    _apply_matrix(matrix)
                except Exception as ex:
                    snack(page, f"Paste failed: {ex}", kind="error")

            try:
                runner = getattr(page, "run_task", None)
                if callable(runner):
                    runner(_paste_async)
                    return
            except Exception:
                pass

            try:
                clip = page.get_clipboard()
            except Exception:
                clip = ""
            _apply_matrix(_parse_excel_clipboard(clip))

        def _on_save(_e=None):
            if dt is None:
                return

            try:
                snack(page, "Saving…", kind="warning")
            except Exception:
                pass

            out_rows: list[dict[str, str]] = []

            metric_col = None
            for candidate in ("Metrics", "Metric", "METRICS", "METRIC"):
                if candidate in fieldnames:
                    metric_col = candidate
                    break
            if metric_col is None:
                metric_col = "Metrics"

            for metric in metrics_order:
                row: dict[str, str] = {metric_col: metric}
                for sc in shift_cols:
                    try:
                        ref = cell_refs.get(metric, {}).get(sc)
                        tf = getattr(ref, "current", None) if ref is not None else None
                        raw_val = (
                            str(getattr(tf, "value", "") or "")
                            if tf is not None
                            else ""
                        )
                        # Normalize user input before saving (e.g. "75%" -> "75").
                        row[sc] = raw_val.replace("%", "").strip()
                    except Exception:
                        row[sc] = ""
                out_rows.append(row)

            out_fieldnames = (
                list(fieldnames) if fieldnames else [metric_col] + shift_cols
            )
            if metric_col not in out_fieldnames:
                out_fieldnames.insert(0, metric_col)
            for sc in shift_cols:
                if sc not in out_fieldnames:
                    out_fieldnames.append(sc)

            async def _save_async():
                try:

                    def _worker_write():
                        if csv_path.exists() and is_file_locked_windows(csv_path):
                            return (
                                False,
                                "Can't save targets because the CSV file is open/locked (e.g., in Excel).\n"
                                f"Close this file first: {csv_path}",
                                "warning",
                            )

                        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
                            writer = csv.DictWriter(f, fieldnames=out_fieldnames)
                            writer.writeheader()
                            for r in out_rows:
                                writer.writerow(r)
                        return (True, "Targets saved", "success")

                    ok, msg, kind = await asyncio.to_thread(_worker_write)
                    snack(page, msg if ok else msg, kind=kind)
                    if ok:
                        _close_dialog()
                except PermissionError:
                    snack(
                        page,
                        "Failed to save targets: CSV file is not writable.\n"
                        "It may be open (e.g., in Excel).\n"
                        f"Close this file first: {csv_path}",
                        kind="warning",
                    )
                except OSError as ex:
                    if getattr(ex, "winerror", None) in (32, 33):
                        snack(
                            page,
                            "Failed to save targets: CSV file is in use by another app (e.g., Excel).\n"
                            f"Close this file first: {csv_path}",
                            kind="warning",
                        )
                    else:
                        snack(page, f"Failed to save CSV: {ex}", kind="error")
                except Exception as ex:
                    snack(page, f"Failed to save CSV: {ex}", kind="error")

            runner = getattr(page, "run_task", None)
            if callable(runner):
                runner(_save_async)
            else:
                # Fallback: blocking save
                try:
                    if csv_path.exists() and is_file_locked_windows(csv_path):
                        snack(
                            page,
                            "Can't save targets because the CSV file is open/locked (e.g., in Excel).\n"
                            f"Close this file first: {csv_path}",
                            kind="warning",
                        )
                        return

                    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
                        writer.writeheader()
                        for r in out_rows:
                            writer.writerow(r)

                    snack(page, f"Targets saved ({link_up})", kind="success")
                    _close_dialog()
                except Exception as ex:
                    snack(page, f"Failed to save CSV: {ex}", kind="error")
                return

            # try:
            #     _p, targets, _created, err = load_targets_csv(
            #         shift=selected_shift,
            #         filename=filename,
            #         folder_name=folder_name,
            #         metrics=metrics_order,
            #     )
            #     if err:
            #         snack(page, f"Failed to refresh targets: {err}", kind="error")
            #         return

            #     if targets and callable(self._set_metrics_targets_cb):
            #         self._set_metrics_targets_cb(targets)
            # except Exception as ex:
            #     snack(page, f"Failed to refresh targets: {ex}", kind="error")
            #     return

            # Snack + close handled in async save.

        async def _load_async():
            try:

                def _worker_load():
                    # Ensure template exists.
                    if not csv_path.exists():
                        _p, _targets, _created, err = load_targets_csv(
                            shift=selected_shift,
                            filename=filename,
                            folder_name=folder_name,
                            metrics=metrics_for_template,
                        )
                        if err:
                            return (False, f"Failed to create template CSV: {err}")

                    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        fns = list(reader.fieldnames or [])

                        metric_col = None
                        for candidate in ("Metrics", "Metric", "METRICS", "METRIC"):
                            if candidate in fns:
                                metric_col = candidate
                                break
                        if metric_col is None:
                            return (False, "Column 'Metrics' not found in CSV")

                        scols = [
                            c for c in ("Shift 1", "Shift 2", "Shift 3") if c in fns
                        ]
                        if not scols:
                            return (False, "Shift columns not found in CSV")

                        order: list[str] = []
                        values: dict[str, dict[str, str]] = {}
                        for row in reader:
                            metric = str(row.get(metric_col, "") or "").strip()
                            if not metric:
                                continue
                            order.append(metric)
                            values[metric] = {
                                sc: str(row.get(sc, "") or "").strip() for sc in scols
                            }

                    return (
                        True,
                        {
                            "fieldnames": fns,
                            "metrics_order": order,
                            "table_values": values,
                            "shift_cols": scols,
                        },
                    )

                ok, payload = await asyncio.to_thread(_worker_load)
                if not ok:
                    base_content.content = ft.Text(str(payload), size=12)
                    loading_overlay.visible = False
                    try:
                        base_content.update()
                        loading_overlay.update()
                    except Exception:
                        pass
                    return

                # Populate loaded data
                nonlocal dt
                fieldnames[:] = list(payload.get("fieldnames") or [])
                metrics_order[:] = list(payload.get("metrics_order") or [])
                table_values.clear()
                table_values.update(payload.get("table_values") or {})
                shift_cols[:] = list(payload.get("shift_cols") or [])

                dt = _build_datatable()

                # Wire handlers now that data table exists
                paste_btn.disabled = False
                paste_btn.on_click = _on_paste
                save_btn.disabled = False
                save_btn.on_click = _on_save

                base_content.content = ft.Column(
                    controls=[
                        ft.Text(
                            "Copy a range from Excel, then click Paste.",
                            size=12,
                            italic=True,
                        ),
                        ft.Container(content=dt, expand=True),
                    ],
                    expand=True,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                )
                loading_overlay.visible = False

                try:
                    base_content.update()
                    loading_overlay.update()
                    paste_btn.update()
                    save_btn.update()
                except Exception:
                    pass
            except Exception as ex:
                base_content.content = ft.Text(f"Failed to read CSV: {ex}", size=12)
                loading_overlay.visible = False
                try:
                    base_content.update()
                    loading_overlay.update()
                except Exception:
                    pass

        runner = getattr(page, "run_task", None)
        if callable(runner):
            runner(_load_async)
        else:
            # If run_task isn't available, fall back to current (blocking) behavior.
            snack(
                page,
                "run_task not available; Target editor may be slow",
                kind="warning",
            )
