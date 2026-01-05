import flet as ft


class MetricsTable(ft.Container):
    """Reusable metrics table component."""

    def __init__(self, width: int = 500):
        # build the DataTable (headers centered for Target/Actual and numeric cells centered)
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Metric", size=12)),
                ft.DataColumn(
                    ft.Text("Target", size=12),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.DataColumn(
                    ft.Text("Actual", size=12),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            rows=[
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("STOP", size=10)),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("3", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("1", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                ),
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("PR", size=10)),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("75", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("77.4", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                ),
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("MTBF", size=10)),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("105", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("224", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                ),
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("UPDT", size=10)),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("4", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("14", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                ),
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("PDT", size=10)),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("8", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("4", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                ),
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("NATR", size=10)),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("5", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                # content=ft.Text("3", size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                ),
            ],
            border=ft.border.all(1, ft.Colors.BLACK12),
            heading_row_color=ft.Colors.BLUE_GREY_50,
            data_row_max_height=25,
            data_row_min_height=25,
            heading_row_height=30,
            vertical_lines=ft.BorderSide(1, ft.Colors.BLACK12),
            horizontal_lines=ft.BorderSide(1, ft.Colors.BLACK12),
        )

        content = ft.Column(
            [
                ft.Text("TARGET VS ACTUAL", size=12, weight=ft.FontWeight.BOLD),
                table,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=10,
        )

        self._table = table

        super().__init__(
            content=content,
            width=width,
            expand=False,
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.all(10),
        )

    def set_rows(self, rows: list[tuple[str, str, str]]):
        """Replace table rows with provided data.

        rows: list of tuples where each tuple is (metric, target, actual)
        """
        dt_rows = []
        for metric, target, actual in rows:
            dt_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(metric, size=10)),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(str(target), size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(str(actual), size=10),
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                )
            )
        # replace the DataTable rows
        try:
            self._table.rows = dt_rows
        except Exception:
            # fallback
            self.content.controls[1].rows = dt_rows
        self.update()

    def _extract_cell_text(self, cell: ft.DataCell) -> str:
        try:
            c = getattr(cell, "content", None)
            if isinstance(c, ft.Text):
                return str(c.value or "").strip()
            if isinstance(c, ft.Container):
                inner = getattr(c, "content", None)
                if isinstance(inner, ft.Text):
                    return str(inner.value or "").strip()
                return str(inner).strip() if inner is not None else ""
            return str(c).strip() if c is not None else ""
        except Exception:
            return ""

    def get_tabulate_data(self) -> tuple[list[str], list[list[str]]]:
        """Return (headers, rows) for printing via tabulate."""
        headers: list[str] = []
        rows: list[list[str]] = []
        try:
            table = getattr(self, "_table", None) or self.content.controls[1]

            for col in list(getattr(table, "columns", None) or []):
                label = getattr(col, "label", None)
                if isinstance(label, ft.Text):
                    headers.append(str(label.value or "").strip())
                else:
                    headers.append(str(label).strip() if label is not None else "")

            for r in list(getattr(table, "rows", None) or []):
                row_cells = []
                for cell in list(getattr(r, "cells", None) or []):
                    row_cells.append(self._extract_cell_text(cell))
                if row_cells:
                    rows.append(row_cells)
        except Exception:
            pass
        return headers, rows

    def get_rows_data(self) -> list[tuple[str, str, str]]:
        """Return the current table as list of (metric, target, actual)."""
        try:
            _headers, rows = self.get_tabulate_data()
            out: list[tuple[str, str, str]] = []
            for r in rows:
                metric = str(r[0]) if len(r) > 0 else ""
                target = str(r[1]) if len(r) > 1 else ""
                actual = str(r[2]) if len(r) > 2 else ""
                out.append((metric, target, actual))
            return out
        except Exception:
            return []

    def set_targets(self, targets: dict[str, str]):
        """Update Target column values by metric name, preserving Actual."""
        try:
            current = self.get_rows_data()
            if not current:
                return

            new_rows: list[tuple[str, str, str]] = []
            for metric, target, actual in current:
                if metric in targets:
                    new_target = str(targets.get(metric, ""))
                else:
                    new_target = target
                new_rows.append((metric, new_target, actual))

            self.set_rows(new_rows)
        except Exception:
            pass

    def print_tabulated(self, tablefmt: str = "psql"):
        """Print the current metrics table to stdout using tabulate."""
        try:
            _, rows = self.get_tabulate_data()
            if not rows:
                return
        except Exception as ex:
            raise ex

    def format_tabulated(self, tablefmt: str = "pretty") -> str:
        """Return the current metrics table as a string using tabulate."""
        try:
            from tabulate import tabulate

            headers, rows = self.get_tabulate_data()
            if not rows:
                return ""
            return str(tabulate(rows, headers=headers, tablefmt=tablefmt)).strip()
        except Exception:
            return ""
