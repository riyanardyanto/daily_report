import flet as ft


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
        # build the DataTable (headers centered for Target/Actual and numeric cells centered)
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Line", size=12, weight=ft.FontWeight.W_600)),
                ft.DataColumn(
                    ft.Text("Issue", size=12, weight=ft.FontWeight.W_600),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.DataColumn(
                    ft.Text("Stops", size=12, weight=ft.FontWeight.W_600),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.DataColumn(
                    ft.Text("Dt[min]", size=12, weight=ft.FontWeight.W_600),
                    heading_row_alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            border=ft.border.all(1, ft.Colors.BLACK12),
            heading_row_color=ft.Colors.BLUE_GREY_50,
            data_row_max_height=50,
            data_row_min_height=28,
            heading_row_height=34,
            vertical_lines=ft.BorderSide(1, ft.Colors.BLACK12),
            horizontal_lines=ft.BorderSide(1, ft.Colors.BLACK12),
        )

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
                ft.Text("Stop Details", size=12, weight=ft.FontWeight.W_600),
                table_container,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=10,
        )

        super().__init__(
            content=content,
            width=width,
            expand=True,
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.all(10),
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=10,
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
