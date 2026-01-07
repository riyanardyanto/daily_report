import traceback

import flet as ft
import pandas as pd

from src.components.card_panel import CardPanel
from src.components.metrics_table import MetricsTable
from src.components.report_editor import ReportEditor
from src.components.report_list_view import ReportList
from src.components.sidebar import Sidebar
from src.components.stops_table import StopsTable
from src.services.config_service import (
    get_application_config,
    get_spa_credentials,
    get_spa_service_config,
)
from src.services.spa_service import (
    fetch_data_from_api,
    get_data_actual,
    get_data_range,
    get_line_performance_details,
    get_url_spa,
    process_data,
)
from src.utils.helpers import data_app_path, load_targets_csv
from src.utils.ui_helpers import snack


class DashboardApp(ft.Container):
    def __init__(self, page: ft.Page | None = None):
        super().__init__()
        self._page = page
        self._is_compact = False

        self.spa_df: pd.DataFrame | None = None
        self.sidebar = Sidebar()
        self.metrics_table = MetricsTable(width=550)
        # wire up stops_table so parent can react to row double-tap
        self.stops_table = StopsTable(
            width=550, on_row_double_tap=self.on_stop_row_double
        )
        self.table_container = CardPanel(
            content=ft.Column(
                controls=[
                    self.metrics_table,
                    self.stops_table,
                ],
                expand=True,
                spacing=12,
            ),
            expand=True,
            padding=10,
        )

        # use reusable ReportEditor component (keeps server-side order and stable keys)
        # make it expand so the embedded ReportList gets a constrained height and can scroll
        self.report_editor = ReportEditor(
            expand=True,
            on_report_table=self._print_metrics_table,
            get_report_table_text=self._get_metrics_table_text,
            get_include_table=self._get_include_table,
            get_metrics_rows=self._get_metrics_rows,
            set_metrics_targets=self._set_metrics_targets,
            get_selected_shift=self._get_selected_shift,
            get_link_up=self._get_link_up,
            get_func_location=self._get_func_location,
            get_date_field=self._get_date_field,
            get_user=self._get_user,
        )

        # use reusable ReportList component (keeps server-side order and stable keys)
        self.report_list = ReportList(expand=True)
        self.report_label = ft.Text("", size=12)
        self.report_content = CardPanel(
            content=ft.Column(
                controls=[self.report_editor],
                expand=True,
                spacing=0,
            ),
            expand=True,
            padding=10,
        )
        # create if button get data is clicked in sidebar, then update the report content
        self.sidebar.get_data_button.on_click = self.update_tables
        # allow stops_table to push selected row details into report content via callback (already set on construction)
        self.progress_bar = ft.ProgressBar(
            # bar_height=600,
            height=12,
            visible=False,
            expand=True,
        )

        self.status_bar = ft.Text("", size=11, color=ft.Colors.BLUE_GREY_700)

        header = ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=10),
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=10,
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.DASHBOARD_CUSTOMIZE, size=26),
                            ft.Text(
                                "Daily Report Dashboard",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=8,
                        expand=False,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=self.progress_bar,
                                width=220,
                            ),
                            self.status_bar,
                        ],
                        expand=True,
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                ],
                expand=True,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self._main_panel = ft.Container(
            content=ft.Column(
                spacing=12,
                controls=[
                    header,
                    ft.Row(
                        [
                            self.table_container,
                            self.report_content,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        expand=True,
                        spacing=12,
                    ),
                ],
                expand=True,
            ),
            padding=ft.padding.only(left=0, right=0, top=0, bottom=0),
            expand=True,
        )

        # Host container; we can swap its content on resize to become responsive.
        self._layout_host = ft.Container(expand=True)
        self.content = self._layout_host
        self.expand = True

        # Apply initial layout (best-effort).
        try:
            w = None
            if page is not None:
                w = getattr(page, "width", None)
            self.apply_responsive_layout(w)
        except Exception:
            self.apply_responsive_layout(None)

    def apply_responsive_layout(self, page_width: int | float | None):
        """Switch layout based on window width.

        - Wide: sidebar on the left, content on the right.
        - Narrow: sidebar stacked on top.
        """

        try:
            w = float(page_width) if page_width is not None else None
        except Exception:
            w = None

        compact = bool(w is not None and w < 980)
        if (
            compact == self._is_compact
            and getattr(self._layout_host, "content", None) is not None
        ):
            return

        self._is_compact = compact

        # Sidebar sizing: fixed width on wide layouts, full-width on compact.
        try:
            if compact:
                self.sidebar.width = None
                self.sidebar.expand = True
            else:
                self.sidebar.width = 220
                self.sidebar.expand = False
        except Exception:
            pass

        if compact:
            layout = ft.Column(
                controls=[
                    self.sidebar,
                    self._main_panel,
                ],
                spacing=12,
                expand=True,
            )
        else:
            layout = ft.Row(
                controls=[
                    self.sidebar,
                    self._main_panel,
                ],
                spacing=12,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )

        self._layout_host.content = layout

        try:
            self.update()
        except Exception:
            pass

    def _get_selected_shift(self) -> str:
        try:
            return str(self.sidebar.shift.value or "Shift 1")
        except Exception:
            return "Shift 1"

    def _get_link_up(self) -> str:
        try:
            return str(self.sidebar.link_up.value or "LU22")
        except Exception:
            return "LU22"

    def _get_func_location(self) -> str:
        try:
            return str(self.sidebar.func_location.value or "Packer")
        except Exception:
            return "Packer"

    def _get_date_field(self) -> str:
        try:
            return str(getattr(self.sidebar.date_field, "value", "") or "")
        except Exception:
            return ""

    def _get_user(self) -> str:
        try:
            return str(getattr(self.sidebar.user, "value", "") or "")
        except Exception:
            return ""

    def _print_metrics_table(self):
        """Print MetricsTable to console using tabulate."""
        try:
            self.metrics_table.print_tabulated()
        except Exception:
            pass

    def _get_metrics_table_text(self) -> str:
        """Return MetricsTable as tabulate text (for QR payload)."""
        try:
            return self.metrics_table.format_tabulated(tablefmt="pretty")
        except Exception:
            return ""

    def _get_include_table(self) -> bool:
        try:
            sw = getattr(
                getattr(self, "metrics_table", None), "include_table_switch", None
            )
            return bool(getattr(sw, "value", True))
        except Exception:
            return True

    def _get_metrics_rows(self) -> list[tuple[str, str, str]]:
        try:
            return self.metrics_table.get_rows_data()
        except Exception:
            return []

    def _set_metrics_targets(self, targets: dict[str, str]):
        try:
            self.metrics_table.set_targets(targets)
        except Exception:
            pass

    def update_report_content(self, e):
        # Update the report content based on sidebar inputs
        link_up = self.sidebar.link_up.value
        func_location = self.sidebar.func_location.value
        date = self.sidebar.date_picker.value
        shift = self.sidebar.shift.value

        self.sidebar.date_picker.value = date  # Ensure date picker shows selected date

        # date format to string YYYY-MM-DD
        report_text = f"Report for Link Up: {link_up}, Function Location: {func_location}, Date: {date.strftime('%Y-%m-%d')}, Shift: {shift}"
        # set the report label above the list
        try:
            self.report_label.value = report_text
            self.report_label.update()
        except Exception:
            pass

    def update_tables(self, e=None):
        page = None
        try:
            page = getattr(e, "page", None) if e is not None else None
        except Exception:
            page = None

        if page is None:
            try:
                page = getattr(self, "page", None)
            except Exception:
                page = None

        # Show progress while fetching/updating
        try:
            if getattr(self, "progress_bar", None) is not None:
                self.progress_bar.visible = True
                try:
                    self.progress_bar.update()
                except Exception:
                    pass
            if page is None:
                page = getattr(getattr(self, "progress_bar", None), "page", None)
            if page is not None:
                page.update()
        except Exception:
            pass

        try:
            try:
                self.get_spa_dataframe()
            except Exception as ex:
                # Environment-aware error handling
                env_lower = "production"
                try:
                    app_cfg, _app_err = get_application_config()
                    env_lower = (
                        str(
                            getattr(app_cfg, "environment", "production")
                            or "production"
                        )
                        .strip()
                        .lower()
                    )
                except Exception:
                    env_lower = "production"

                if env_lower == "production":
                    try:
                        log_path = data_app_path(
                            "error.log", folder_name="data_app/log"
                        )
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        with log_path.open("a", encoding="utf-8") as f:
                            f.write(traceback.format_exc())
                            f.write("\n\n")
                    except Exception:
                        # best-effort; don't crash UI thread
                        pass
                else:
                    # development: print traceback to terminal
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass

                try:
                    if page is None:
                        page = getattr(getattr(self, "sidebar", None), "page", None)
                except Exception:
                    pass
                if page is not None:
                    snack(page, f"Failed to get SPA data: {ex}", kind="error")
                return
            if self.spa_df is None:
                print("No SPA data available.")
                try:
                    if page is None:
                        page = getattr(getattr(self, "sidebar", None), "page", None)
                except Exception:
                    pass
                if page is not None:
                    snack(page, "Failed to get SPA data (empty data)", kind="warning")
                return

            # Update status bar with SPA range (best-effort)
            try:
                rng = get_data_range(process_data(self.spa_df))
                self.status_bar.value = str(rng) if rng is not None else ""
                self.status_bar.update()
            except Exception:
                pass

            self.update_metrics_tables(self.spa_df, e)
            self.update_stops_tables(self.spa_df, e)
        finally:
            # Always hide progress bar at the end
            try:
                if getattr(self, "progress_bar", None) is not None:
                    self.progress_bar.visible = False
                    try:
                        self.progress_bar.update()
                    except Exception:
                        pass
                if page is None:
                    page = getattr(getattr(self, "progress_bar", None), "page", None)
                if page is not None:
                    page.update()
            except Exception:
                pass

    def update_metrics_tables(self, df, e=None):
        # Load targets based on selected shift from CSV and update MetricsTable.

        lu = self.sidebar.link_up.value[-2:].lower()  # last 2 chars
        fl = self.sidebar.func_location.value[:4].lower()  # first 4 chars
        filename = f"target_{fl}_{lu}.csv"

        shift = None

        try:
            shift = (self.sidebar.shift.value or "").strip()
        except Exception:
            shift = ""
        if not shift:
            shift = "Shift 1"

        try:
            existing_rows = self.metrics_table.get_rows_data()
            metrics = [m for m, _t, _a in existing_rows if str(m).strip()]
        except Exception:
            metrics = []

        csv_path, targets, created_template, err = load_targets_csv(
            shift=shift,
            filename=filename,
            folder_name="data_app/targets",
            metrics=metrics,
        )
        if err:
            print(f"Failed reading targets from CSV: {err}")
            return
        if created_template:
            print(f"Target CSV not found; created empty template: {csv_path}")
            return

        if not targets:
            print(f"No targets loaded from {csv_path.name} for {shift}.")
            return

        try:
            self.metrics_table.set_targets(targets)
        except Exception as ex:
            print(f"Failed updating MetricsTable targets: {ex}")
            return

        # Update Actual column using SPA df
        actuals: dict[str, str] = {}
        try:
            df_actual = process_data(df)
            actual_df = get_data_actual(df_actual)

            # Expected shape: DataFrame with columns Metric, Value
            if hasattr(actual_df, "iterrows"):
                for _idx, row in actual_df.iterrows():
                    try:
                        metric = str(row.get("Metric", "") or "").strip()
                        value = row.get("Value", "")
                        if metric:
                            actuals[metric] = str(
                                value if value is not None else ""
                            ).strip()
                    except Exception:
                        pass
            elif isinstance(actual_df, dict):
                # Fallback if service returns dict
                for k, v in actual_df.items():
                    try:
                        actuals[str(k).strip()] = str(
                            v if v is not None else ""
                        ).strip()
                    except Exception:
                        pass
        except Exception as ex:
            print(f"Failed computing actual metrics: {ex}")
            actuals = {}

        if actuals:
            try:
                current_rows = self.metrics_table.get_rows_data()
                if current_rows:
                    new_rows: list[tuple[str, str, str]] = []
                    for metric, target, actual in current_rows:
                        if metric in actuals:
                            actual = actuals.get(metric, actual)
                        new_rows.append((metric, target, actual))
                    self.metrics_table.set_rows(new_rows)
            except Exception as ex:
                print(f"Failed updating MetricsTable actuals: {ex}")

        print(f"Metrics targets updated for {shift} from {csv_path.name}.")

    def update_stops_tables(self, df, e=None):
        df = process_data(df)
        line_df = get_line_performance_details(df)

        if not line_df:
            # nothing to show — clear table and return
            self.stops_table.set_rows([])
            print("No line performance segments found.")
            return

        # take first segment and ensure it's a DataFrame
        first_seg = line_df[0]
        if hasattr(first_seg, "values"):
            row_values = first_seg.values.tolist()
        else:
            row_values = []

        self.stops_table.set_rows(row_values)

    def get_spa_dataframe(self):
        app_cfg, app_err = get_application_config()
        if app_err:
            print(f"Config read warning: {app_err}")

        spa_cfg, spa_err = get_spa_service_config()
        if spa_err:
            print(f"Config read warning: {spa_err}")

        env = (
            str(getattr(app_cfg, "environment", "production") or "production")
            .strip()
            .lower()
        )

        # Local test sources (used for development)
        local_url = (
            "http://127.0.0.1:5500/src/assets/response2.html"
            if self.sidebar.link_up.value == "LU21"
            else "http://127.0.0.1:5500/src/assets/response.html"
        )

        # Real SPA URL (used for production)
        spa_url = get_url_spa(
            link_up=self.sidebar.link_up.value[-2:],
            date=self.sidebar.date_field.value,
            shift=self.sidebar.shift.value[-1] or "",
            functional_location=self.sidebar.func_location.value[:4].upper() or "PACK",
            base_url=spa_cfg.base_url or None,
        )

        url = local_url if env == "development" else spa_url

        username, password, cfg_err = get_spa_credentials(
            default_username="DOMAIN\\username",
            default_password="password",
        )
        if cfg_err:
            print(f"Config read warning: {cfg_err}")

        self.spa_df = fetch_data_from_api(
            url,
            username,
            password,
            verify_ssl=getattr(spa_cfg, "verify_ssl", None),
            timeout=getattr(spa_cfg, "timeout", None),
        )

    def on_stop_row_double(self, row: list):
        """Callback invoked when a stops-table row is double-clicked.

        Sets the `report_content` to a summary text of the clicked row.
        """
        try:
            line, issue, stops, downtime = row
            text = (
                f"Line: {line} — Issue: {issue} — Stops: {stops} — Downtime: {downtime}"
            )
        except Exception:
            text = str(row)
        # set the report label (do not replace the list)
        try:
            self.report_label.value = text
            self.report_label.update()
        except Exception:
            pass

        # Append the clicked row's issue (row[1]) as a new card into the report list shown in the UI.
        try:
            issue_value = (
                row[1] if isinstance(row, (list, tuple)) and len(row) > 1 else None
            )
            if issue_value is None:
                return

            # Prefer the ReportEditor-embedded list (this is what is actually mounted in report_content).
            report_list = None
            if (
                hasattr(self, "report_editor")
                and getattr(self.report_editor, "report_list", None) is not None
            ):
                report_list = self.report_editor.report_list
            elif hasattr(self, "report_list"):
                # Backward-compatible fallback (older layout used self.report_list directly)
                report_list = self.report_list

            if report_list is None or not isinstance(
                report_list, ft.ReorderableListView
            ):
                return

            # append a new item via the reusable ReportList component
            try:
                report_list.append_item_issue(issue_value)
            except Exception:
                # fallback: append raw container if something goes wrong
                item = ft.Container(
                    content=ft.Text(str(issue_value), color=ft.Colors.BLACK),
                    margin=ft.margin.symmetric(horizontal=0, vertical=5),
                    expand=True,
                )
                report_list.controls.append(item)
                try:
                    report_list.update()
                except Exception:
                    pass
        except Exception:
            pass
