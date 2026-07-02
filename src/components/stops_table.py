import flet as ft

from src.utils.theme import (
    SURFACE,
    SWITCH_ACTIVE,
    TABLE_HEADER_BG,
    TABLE_HEADER_TEXT,
    TEXT_SECONDARY,
)


class StopsTable(ft.Container):
    """Reusable stops table component."""

    def __init__(self, width: int = 500, on_row_double_tap=None):
        """Create a StopsTable.

        Args:
            width (int): control width
            on_row_double_tap (callable or None): optional callback that will be called
                with the row list when a row is double-clicked/tapped.
        """
        self.on_row_double_tap = on_row_double_tap
        self.include_line_stop_switch = ft.Switch(
            label="Include line stop",
            label_style=ft.TextStyle(size=18),
            label_position=ft.LabelPosition.LEFT,
            height=18,
            value=True,
            active_track_color=SWITCH_ACTIVE,
        )

        # build the DataTable (headers centered for Target/Actual and numeric cells centered)
        table = ft.DataTable(
            columns=[
                ft.DataColumn(
                    ft.Text("Line", size=12, weight=ft.FontWeight.W_600, color=TABLE_HEADER_TEXT)
                ),
                ft.DataColumn(
                    ft.Text("Issue", size=12, weight=ft.FontWeight.W_600, color=TABLE_HEADER_TEXT),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.DataColumn(
                    ft.Text("Stops", size=12, weight=ft.FontWeight.W_600, color=TABLE_HEADER_TEXT),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.DataColumn(
                    ft.Text("Dt[min]", size=12, weight=ft.FontWeight.W_600, color=TABLE_HEADER_TEXT),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            border=ft.border.all(1, "#E2E8F0"),
            heading_row_color=TABLE_HEADER_BG,
            data_row_max_height=40,
            data_row_min_height=22,
            heading_row_height=34,
            vertical_lines=ft.BorderSide(1, "#E2E8F0"),
            horizontal_lines=ft.BorderSide(1, "#E2E8F0"),
        )
        self._table = table

        # wrap the DataTable into a scrollable container so large datasets can scroll
        # Use a scrolling container (supported across flet versions) with fixed height
        # Use a ListView to enable scrolling across flet versions
        table_container = ft.Container(
            content=ft.ListView(
                [table],
                expand=True,
                spacing=0,
            ),
            height=300,
            expand=True,
        )

        content = ft.Column(
            [
                ft.Row(
                    controls=[
                        ft.Text(
                            "Stop Details",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_SECONDARY,
                        ),
                        self.include_line_stop_switch,
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                table_container,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=10,
        )

        super().__init__(
            content=content,
            width=width,
            expand=True,
            bgcolor=SURFACE,
            padding=ft.padding.all(12),
            border_radius=12,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color="#0000000D",
                offset=ft.Offset(0, 2),
            ),
        )

    def set_rows(self, rows: list[tuple[str, str, str, str]]):
        """Replace table rows with provided data.

        rows: list of tuples where each tuple is (line, issue, stops, downtime)
        """
        # Color rows by "Line" group so identical Line values share the same background.
        # Keep the palette subtle and based on existing theme primitives.
        group_palette = [
            ft.Colors.BLUE_50,
            ft.Colors.INDIGO_50,
            ft.Colors.TEAL_50,
            ft.Colors.GREEN_50,
            ft.Colors.AMBER_50,
            ft.Colors.ORANGE_50,
            ft.Colors.RED_50,
        ]

        dt_rows = []
        for line, issue, stops, downtime in rows:
            line_key = str(line).strip() if line is not None else ""
            palette_index = (
                sum(ord(ch) for ch in line_key) % len(group_palette) if line_key else 0
            )
            row_color = group_palette[palette_index]

            # preserve the full row as a list and pass it to the double-tap handler
            row_list = [line, issue, stops, downtime]
            dt_rows.append(
                ft.DataRow(
                    color=row_color,
                    cells=[
                        ft.DataCell(
                            ft.GestureDetector(
                                content=ft.Container(
                                    content=ft.Text(line, size=11),
                                    alignment=ft.alignment.center_left,
                                    padding=ft.padding.only(left=4),
                                ),
                                on_double_tap=lambda e,
                                r=row_list: self._on_cell_double_tap(e, r),
                            )
                        ),
                        ft.DataCell(
                            ft.GestureDetector(
                                content=ft.Container(
                                    content=ft.Text(str(issue), size=11),
                                    alignment=ft.alignment.center_left,
                                    padding=ft.padding.only(left=0),
                                ),
                                on_double_tap=lambda e,
                                r=row_list: self._on_cell_double_tap(e, r),
                            )
                        ),
                        ft.DataCell(
                            ft.GestureDetector(
                                content=ft.Container(
                                    content=ft.Text(str(stops), size=11),
                                    alignment=ft.alignment.center,
                                    padding=ft.padding.only(left=0),
                                ),
                                on_double_tap=lambda e,
                                r=row_list: self._on_cell_double_tap(e, r),
                            )
                        ),
                        ft.DataCell(
                            ft.GestureDetector(
                                content=ft.Container(
                                    content=ft.Text(str(downtime), size=11),
                                    alignment=ft.alignment.center,
                                    padding=ft.padding.only(left=0),
                                ),
                                on_double_tap=lambda e,
                                r=row_list: self._on_cell_double_tap(e, r),
                            )
                        ),
                    ],
                )
            )
        # find the DataTable regardless of wrapper (Container/ListView) and replace its rows
        data_table = None
        container = self.content.controls[1]
        # Container -> ListView -> DataTable
        if isinstance(container, ft.Container) and hasattr(container, "content"):
            inner = container.content
            if (
                hasattr(inner, "controls")
                and inner.controls
                and isinstance(inner.controls[0], ft.DataTable)
            ):
                data_table = inner.controls[0]
            elif isinstance(inner, ft.DataTable):
                data_table = inner
        elif isinstance(container, ft.DataTable):
            data_table = container

        if data_table is not None:
            data_table.rows = dt_rows
            self.update()
        else:
            # fallback: try assigning to the old location (best-effort)
            try:
                self.content.controls[1].rows = dt_rows
                self.update()
            except Exception:
                pass

    def _extract_cell_text(self, cell: ft.DataCell) -> str:
        try:
            c = getattr(cell, "content", None)
            if isinstance(c, ft.Text):
                return str(c.value or "").strip()
            if isinstance(c, ft.Container):
                inner = getattr(c, "content", None)
                if isinstance(inner, ft.Text):
                    return str(inner.value or "").strip()
                if isinstance(inner, ft.GestureDetector):
                    nested = getattr(inner, "content", None)
                    if isinstance(nested, ft.Container):
                        nested_text = getattr(nested, "content", None)
                        if isinstance(nested_text, ft.Text):
                            return str(nested_text.value or "").strip()
                    if isinstance(nested, ft.Text):
                        return str(nested.value or "").strip()
                return str(inner).strip() if inner is not None else ""
            if isinstance(c, ft.GestureDetector):
                inner = getattr(c, "content", None)
                if isinstance(inner, ft.Container):
                    nested_text = getattr(inner, "content", None)
                    if isinstance(nested_text, ft.Text):
                        return str(nested_text.value or "").strip()
                if isinstance(inner, ft.Text):
                    return str(inner.value or "").strip()
                return str(inner).strip() if inner is not None else ""
            return str(c).strip() if c is not None else ""
        except Exception:
            return ""

    def get_rows_data(self) -> list[tuple[str, str, str, str]]:
        """Return current table rows as (line, issue, stops, downtime)."""
        out: list[tuple[str, str, str, str]] = []
        try:
            table = getattr(self, "_table", None)
            if table is None:
                return out

            for r in list(getattr(table, "rows", None) or []):
                row_cells = []
                for cell in list(getattr(r, "cells", None) or []):
                    row_cells.append(self._extract_cell_text(cell))
                if row_cells:
                    line = str(row_cells[0]) if len(row_cells) > 0 else ""
                    issue = str(row_cells[1]) if len(row_cells) > 1 else ""
                    stops = str(row_cells[2]) if len(row_cells) > 2 else ""
                    downtime = str(row_cells[3]) if len(row_cells) > 3 else ""
                    out.append((line, issue, stops, downtime))
        except Exception:
            return []
        return out

    def format_line_stops_tabulated(self, tablefmt: str = "pretty") -> str:
        """Return tabulate text for aggregated stop count per line."""
        try:
            from tabulate import tabulate

            rows = self.get_rows_data()
            if not rows:
                return ""

            by_line: dict[str, float] = {}
            for line, _issue, stops, _downtime in rows:
                line_key = str(line or "").strip() or "-"
                try:
                    num = float(str(stops).replace(",", "").strip() or "0")
                except Exception:
                    num = 0.0
                by_line[line_key] = float(by_line.get(line_key, 0.0) + num)

            table_rows: list[list[str]] = []
            # Show highest stop counts first to make the summary easier to scan.
            sorted_items = sorted(by_line.items(), key=lambda item: (-item[1], item[0]))
            for line_key, total in sorted_items:
                total_str = str(int(total)) if float(total).is_integer() else f"{total:.2f}"
                table_rows.append([line_key, total_str])

            return str(
                tabulate(
                    table_rows,
                    headers=["Line", "Stops"],
                    tablefmt=tablefmt,
                    numalign="left",
                    stralign="left",
                )
            ).strip()
        except Exception:
            return ""

    def _on_cell_double_tap(self, e, row: list):
        # call user-provided callback if set
        try:
            if callable(self.on_row_double_tap):
                # allow the callback to return something; ignore result here
                self.on_row_double_tap(row)
        except Exception:
            # swallow errors from user callback to avoid crashing the UI
            pass

        return row
