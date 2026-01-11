from __future__ import annotations

import csv

import flet as ft

from src.utils.helpers import data_app_path, load_targets_csv
from src.utils.theme import ON_COLOR, PRIMARY, SECONDARY
from src.utils.ui_helpers import is_file_locked_windows, snack


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

        # Load CSV
        fieldnames: list[str] = []
        metrics_order: list[str] = []
        table_values: dict[str, dict[str, str]] = {}
        try:
            if not csv_path.exists():
                # Create empty template in data_app so the editor can still open.
                try:
                    metrics = []
                    if callable(self._get_metrics_rows_cb):
                        rows = self._get_metrics_rows_cb() or []
                        metrics = [
                            str(m).strip() for m, _t, _a in rows if str(m).strip()
                        ]
                except Exception:
                    metrics = []

                # If the table is empty/uninitialized, fall back to the current default metric set.
                if not metrics:
                    metrics = [
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

                _p, _targets, _created, err = load_targets_csv(
                    shift=selected_shift,
                    filename=filename,
                    folder_name=folder_name,
                    metrics=metrics,
                )
                if err:
                    snack(page, f"Failed to create template CSV: {err}", kind="error")
                    return

            with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])

                # Determine metric + shift columns
                metric_col = None
                for candidate in ("Metrics", "Metric", "METRICS", "METRIC"):
                    if candidate in fieldnames:
                        metric_col = candidate
                        break
                if metric_col is None:
                    snack(page, "Column 'Metrics' not found in CSV", kind="error")
                    return

                shift_cols = [
                    c for c in ("Shift 1", "Shift 2", "Shift 3") if c in fieldnames
                ]
                if not shift_cols:
                    snack(page, "Shift columns not found in CSV", kind="error")
                    return

                for row in reader:
                    metric = str(row.get(metric_col, "") or "").strip()
                    if not metric:
                        continue
                    metrics_order.append(metric)
                    table_values[metric] = {
                        sc: str(row.get(sc, "") or "").strip() for sc in shift_cols
                    }

        except Exception as ex:
            snack(page, f"Failed to read CSV: {ex}", kind="error")
            return

        shift_cols = [c for c in ("Shift 1", "Shift 2", "Shift 3") if c in fieldnames]

        # Build editable DataTable: store TextField refs per metric+shift
        cell_refs: dict[str, dict[str, ft.Ref[ft.TextField]]] = {}

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

        dt = ft.DataTable(
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
                    runner(_paste_async())
                    return
            except Exception:
                pass

            try:
                clip = page.get_clipboard()
            except Exception:
                clip = ""
            _apply_matrix(_parse_excel_clipboard(clip))

        def _on_save(_e=None):
            try:
                if csv_path.exists() and is_file_locked_windows(csv_path):
                    snack(
                        page,
                        "Can't save targets because the CSV file is open/locked (e.g., in Excel).\n"
                        f"Close this file first: {csv_path}",
                        kind="warning",
                    )
                    return
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

            try:
                out_fieldnames = (
                    list(fieldnames) if fieldnames else [metric_col] + shift_cols
                )
                if metric_col not in out_fieldnames:
                    out_fieldnames.insert(0, metric_col)
                for sc in shift_cols:
                    if sc not in out_fieldnames:
                        out_fieldnames.append(sc)

                with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=out_fieldnames)
                    writer.writeheader()
                    for r in out_rows:
                        writer.writerow(r)
            except PermissionError:
                snack(
                    page,
                    "Failed to save targets: CSV file is not writable.\n"
                    "It may be open (e.g., in Excel).\n"
                    f"Close this file first: {csv_path}",
                    kind="warning",
                )
                return
            except OSError as ex:
                if getattr(ex, "winerror", None) in (32, 33):
                    snack(
                        page,
                        "Failed to save targets: CSV file is in use by another app (e.g., Excel).\n"
                        f"Close this file first: {csv_path}",
                        kind="warning",
                    )
                    return
                snack(page, f"Failed to save CSV: {ex}", kind="error")
                return
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

            snack(page, f"Targets saved ({link_up})", kind="success")
            _close_dialog()

        self._dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit target"),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Copy a range from Excel, then click Paste.",
                            size=12,
                            italic=True,
                        ),
                        ft.Container(
                            content=dt,
                            expand=True,
                        ),
                    ],
                    expand=True,
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
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
                        ft.ElevatedButton(
                            "Paste",
                            on_click=_on_paste,
                            color=ON_COLOR,
                            bgcolor=SECONDARY,
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
            on_dismiss=lambda _e: _close_dialog(),
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
