import asyncio
import time
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
    get_ui_config,
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

        # Debug logging (avoid noisy/slow prints in production hot paths)
        self._env_lower = "production"
        self._debug_enabled = False
        try:
            app_cfg, _app_err = get_application_config()
            self._env_lower = (
                str(getattr(app_cfg, "environment", "production") or "production")
                .strip()
                .lower()
            )
            self._debug_enabled = self._env_lower != "production"
        except Exception:
            self._env_lower = "production"
            self._debug_enabled = False

        # Get Data concurrency + caching
        self._getdata_seq = 0
        # key -> (timestamp_monotonic, df, rng_str, metrics_rows, stops_rows)
        self._spa_cache: dict[
            tuple[str, str, str, str, str],
            tuple[float, pd.DataFrame, str, list[tuple[str, str, str]], list[list]],
        ] = {}
        self._spa_cache_ttl_s = 15.0
        try:
            ui_cfg, _ui_err = get_ui_config()
            self._spa_cache_ttl_s = float(
                getattr(ui_cfg, "spa_cache_ttl_seconds", 15) or 0
            )
        except Exception:
            self._spa_cache_ttl_s = 15.0

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
                spacing=10,
            ),
            expand=False,
            padding=10,
        )

        # use reusable ReportEditor component (keeps server-side order and stable keys)
        # make it expand so the embedded ReportList gets a constrained height and can scroll
        self.report_editor = ReportEditor(
            expand=True,
            get_report_table_text=self._get_metrics_table_text,
            get_include_table=self._get_include_table,
            get_metrics_rows=self._get_metrics_rows,
            set_metrics_targets=self._set_metrics_targets,
            get_selected_shift=self._get_selected_shift,
            get_link_up=self._get_link_up,
            get_func_location=self._get_func_location,
            get_date_field=self._get_date_field,
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

    def _debug_print(self, *args, **kwargs) -> None:
        if not bool(getattr(self, "_debug_enabled", False)):
            return
        try:
            print(*args, **kwargs)
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

        if page is None:
            try:
                page = getattr(getattr(self, "sidebar", None), "page", None)
            except Exception:
                page = None

        # Snapshot sidebar values on UI thread to avoid reading UI controls in worker thread.
        link_up = ""
        date_value = ""
        shift_value = ""
        func_location = "PACK"
        try:
            link_up = str(
                getattr(getattr(self, "sidebar", None), "link_up", None).value or ""
            )
        except Exception:
            link_up = ""
        try:
            date_value = str(
                getattr(getattr(self, "sidebar", None), "date_field", None).value or ""
            )
        except Exception:
            date_value = ""
        try:
            shift_value = str(
                getattr(getattr(self, "sidebar", None), "shift", None).value or ""
            )
        except Exception:
            shift_value = ""
        try:
            func_location = (
                str(
                    getattr(getattr(self, "sidebar", None), "func_location", None).value
                    or "PACK"
                )
                .strip()
                .upper()[:4]
                or "PACK"
            )
        except Exception:
            func_location = "PACK"

        existing_metrics: list[str] = []
        try:
            existing_rows = self.metrics_table.get_rows_data()
            existing_metrics = [
                str(m or "").strip()
                for m, _t, _a in (existing_rows or [])
                if str(m or "").strip()
            ]
        except Exception:
            existing_metrics = []

        # Seq guard: ignore stale results from previous clicks.
        try:
            self._getdata_seq += 1
        except Exception:
            self._getdata_seq = 1
        my_seq = int(getattr(self, "_getdata_seq", 1) or 1)

        async def _run():
            # Show progress immediately.
            try:
                if getattr(self, "progress_bar", None) is not None:
                    self.progress_bar.visible = True
                if getattr(self, "status_bar", None) is not None:
                    self.status_bar.value = "Loading…"
                if page is not None:
                    page.update()
            except Exception:
                pass

            try:
                # Load config once (UI thread) to decide logging behavior.
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

                # Fast-path cache for repeated clicks with same inputs (short TTL).
                cache_key = (
                    str(env_lower or ""),
                    str(link_up or ""),
                    str(date_value or ""),
                    str(shift_value or ""),
                    str(func_location or ""),
                )
                try:
                    ttl = float(getattr(self, "_spa_cache_ttl_s", 0.0) or 0.0)
                except Exception:
                    ttl = 0.0

                if ttl > 0:
                    try:
                        cached = self._spa_cache.get(cache_key)
                    except Exception:
                        cached = None
                    if cached is not None:
                        ts, df, rng_str, metrics_rows, stops_rows = cached
                        try:
                            fresh = (time.monotonic() - float(ts)) <= ttl
                        except Exception:
                            fresh = False

                        if fresh:
                            # Ignore stale completion if user clicked again.
                            if my_seq != int(
                                getattr(self, "_getdata_seq", my_seq) or my_seq
                            ):
                                return

                            try:
                                self.spa_df = df
                            except Exception:
                                pass
                            try:
                                cached_label = (
                                    f"{rng_str} (Cached)" if rng_str else "Cached"
                                )
                                self.status_bar.value = cached_label
                            except Exception:
                                pass
                            try:
                                self.metrics_table.set_rows(metrics_rows)
                            except Exception:
                                pass
                            try:
                                self.stops_table.set_rows(stops_rows)
                            except Exception:
                                pass

                            return

                # Also snapshot SPA config + credentials on UI thread.
                spa_cfg, spa_err = get_spa_service_config()
                if spa_err:
                    try:
                        self._debug_print(f"Config read warning: {spa_err}")
                    except Exception:
                        pass

                username, password, cfg_err = get_spa_credentials(
                    default_username="DOMAIN\\username",
                    default_password="password",
                )
                if cfg_err:
                    try:
                        self._debug_print(f"Config read warning: {cfg_err}")
                    except Exception:
                        pass

                def _worker():
                    # Build URL inside worker (pure string ops, safe).
                    local_url = (
                        "http://127.0.0.1:5500/src/assets/response2.html"
                        if link_up == "LU21"
                        else "http://127.0.0.1:5500/src/assets/response.html"
                    )
                    spa_url = get_url_spa(
                        link_up=(link_up[-2:] if link_up else ""),
                        date=date_value,
                        shift=(
                            shift_value[-1]
                            if shift_value and shift_value[-1].isnumeric()
                            else ""
                        ),
                        functional_location=func_location or "PACK",
                        base_url=getattr(spa_cfg, "base_url", None) or None,
                    )
                    url = local_url if env_lower == "development" else spa_url

                    df = fetch_data_from_api(
                        url,
                        username,
                        password,
                        verify_ssl=getattr(spa_cfg, "verify_ssl", None),
                        timeout=getattr(spa_cfg, "timeout", None),
                    )

                    if df is None or getattr(df, "empty", False):
                        return None, "", [], []

                    df_processed = process_data(df)

                    # Status bar range (best-effort)
                    rng_str = ""
                    try:
                        rng = get_data_range(df_processed)
                        rng_str = str(rng) if rng is not None else ""
                    except Exception:
                        rng_str = ""

                    # Build metrics rows (targets + actuals) in worker.
                    metrics_rows: list[tuple[str, str, str]] = []
                    try:
                        actual_df = get_data_actual(df_processed)
                        actuals: dict[str, str] = {}
                        actual_metric_order: list[str] = []
                        if hasattr(actual_df, "iterrows"):
                            for _idx, row in actual_df.iterrows():
                                try:
                                    metric = str(row.get("Metric", "") or "").strip()
                                    value = row.get("Value", "")
                                    if metric:
                                        if metric not in actual_metric_order:
                                            actual_metric_order.append(metric)
                                        actuals[metric] = str(
                                            value if value is not None else ""
                                        ).strip()
                                except Exception:
                                    pass

                        lu = link_up[-2:].lower() if link_up else ""
                        fl = func_location[:4].lower() if func_location else ""
                        filename = f"target_{fl}_{lu}.csv"

                        shift_for_targets = ""
                        try:
                            shift_for_targets = shift_value.strip()
                            if "all" in shift_for_targets.lower():
                                shift_for_targets = ""
                        except Exception:
                            shift_for_targets = ""

                        # Metric list for template creation/order.
                        metrics_for_template: list[str] = []
                        for m in list(actual_metric_order) + list(existing_metrics):
                            m = str(m or "").strip()
                            if m and m not in metrics_for_template:
                                metrics_for_template.append(m)

                        _csv_path, targets, _created_template, _err = load_targets_csv(
                            shift=shift_for_targets,
                            filename=filename,
                            folder_name="data_app/targets",
                            metrics=metrics_for_template,
                        )

                        metrics_display: list[str] = []
                        for m in list(actual_metric_order):
                            m = str(m or "").strip()
                            if m and m not in metrics_display:
                                metrics_display.append(m)
                        if not metrics_display:
                            for m in list(existing_metrics):
                                m = str(m or "").strip()
                                if m and m not in metrics_display:
                                    metrics_display.append(m)

                        for metric in metrics_display:
                            target = str((targets or {}).get(metric, "") or "").strip()
                            actual = str(actuals.get(metric, "") or "").strip()
                            metrics_rows.append((metric, target, actual))
                    except Exception:
                        metrics_rows = []

                    # Build stops rows in worker.
                    stops_rows: list[list] = []
                    try:
                        line_df = get_line_performance_details(df_processed)
                        if line_df:
                            first_seg = line_df[0]
                            if hasattr(first_seg, "values"):
                                stops_rows = first_seg.values.tolist()
                    except Exception:
                        stops_rows = []

                    return df, rng_str, metrics_rows, stops_rows

                df, rng_str, metrics_rows, stops_rows = await asyncio.to_thread(_worker)

                # Ignore stale completion if user clicked again.
                if my_seq != int(getattr(self, "_getdata_seq", my_seq) or my_seq):
                    return

                if df is None:
                    try:
                        self._debug_print("No SPA data available.")
                    except Exception:
                        pass
                    if page is not None:
                        snack(
                            page, "Failed to get SPA data (empty data)", kind="warning"
                        )
                    return

                # Update cache on success (UI thread)
                if ttl > 0:
                    try:
                        self._spa_cache[cache_key] = (
                            time.monotonic(),
                            df,
                            str(rng_str or ""),
                            list(metrics_rows or []),
                            list(stops_rows or []),
                        )
                        # Keep cache bounded.
                        if len(self._spa_cache) > 12:
                            items = sorted(
                                self._spa_cache.items(), key=lambda kv: kv[1][0]
                            )
                            for k, _v in items[: max(0, len(items) - 12)]:
                                self._spa_cache.pop(k, None)
                    except Exception:
                        pass

                # Apply results to UI (UI thread)
                try:
                    self.spa_df = df
                except Exception:
                    pass

                try:
                    self.status_bar.value = str(rng_str or "")
                except Exception:
                    pass

                try:
                    self.metrics_table.set_rows(metrics_rows)
                except Exception:
                    pass

                try:
                    self.stops_table.set_rows(stops_rows)
                except Exception:
                    pass

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
                        tb = ""
                        try:
                            tb = traceback.format_exc()
                        except Exception:
                            tb = ""

                        def _write_log():
                            log_path.parent.mkdir(parents=True, exist_ok=True)
                            with log_path.open("a", encoding="utf-8") as f:
                                f.write(tb)
                                f.write("\n\n")

                        await asyncio.to_thread(_write_log)
                    except Exception:
                        pass
                else:
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass

                if page is not None:
                    snack(page, f"Failed to get SPA data: {ex}", kind="error")
            finally:
                # Always hide progress bar at the end, and batch update.
                try:
                    if getattr(self, "progress_bar", None) is not None:
                        self.progress_bar.visible = False
                    if page is not None:
                        page.update()
                except Exception:
                    pass

        if page is None or not hasattr(page, "run_task"):
            # Fallback to the old blocking behavior if run_task isn't available.
            try:
                self.get_spa_dataframe()
                if self.spa_df is not None:
                    self.update_metrics_tables(self.spa_df, e)
                    self.update_stops_tables(self.spa_df, e)
            finally:
                try:
                    if getattr(self, "progress_bar", None) is not None:
                        self.progress_bar.visible = False
                        if page is not None:
                            page.update()
                except Exception:
                    pass
            return

        # Flet expects a coroutine *function* here, not a coroutine object.
        page.run_task(_run)

    def update_metrics_tables(self, df, e=None):
        # Load targets based on selected shift from CSV and update MetricsTable.

        lu = self.sidebar.link_up.value[-2:].lower()  # last 2 chars
        fl = self.sidebar.func_location.value[:4].lower()  # first 4 chars
        filename = f"target_{fl}_{lu}.csv"

        shift = None

        try:
            shift = (
                self.sidebar.shift.value
                if "All" not in self.sidebar.shift.value
                else ""
            ).strip()
        except Exception:
            shift = ""

        # Compute actual metrics first so the table rows can follow get_data_actual() output.
        actuals: dict[str, str] = {}
        actual_metric_order: list[str] = []
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
                            if metric not in actual_metric_order:
                                actual_metric_order.append(metric)
                            actuals[metric] = str(
                                value if value is not None else ""
                            ).strip()
                    except Exception:
                        pass
            elif isinstance(actual_df, dict):
                # Fallback if service returns dict
                for k, v in actual_df.items():
                    try:
                        metric = str(k).strip()
                        if metric:
                            if metric not in actual_metric_order:
                                actual_metric_order.append(metric)
                            actuals[metric] = str(v if v is not None else "").strip()
                    except Exception:
                        pass
        except Exception as ex:
            self._debug_print(f"Failed computing actual metrics: {ex}")
            actuals = {}
            actual_metric_order = []

        try:
            existing_rows = self.metrics_table.get_rows_data()
            metrics = [m for m, _t, _a in existing_rows if str(m).strip()]
        except Exception:
            metrics = []

        # Build metric list for target template creation (preserve order, avoid duplicates)
        metrics_for_template: list[str] = []
        for m in list(actual_metric_order) + list(metrics):
            m = str(m or "").strip()
            if m and m not in metrics_for_template:
                metrics_for_template.append(m)

        csv_path, targets, created_template, err = load_targets_csv(
            shift=shift,
            filename=filename,
            folder_name="data_app/targets",
            metrics=metrics_for_template,
        )
        if err:
            self._debug_print(f"Failed reading targets from CSV: {err}")
            return
        if created_template:
            self._debug_print(
                f"Target CSV not found; created empty template: {csv_path}"
            )
            # Continue updating the UI (targets will be empty)

        if not targets:
            # No targets is still a valid state; we can still show Actual metrics.
            self._debug_print(f"No targets loaded from {csv_path.name} for {shift}.")

        # Update rows to follow get_data_actual() output order.
        try:
            # Start from actual order, then add any target-only metrics (e.g., legacy metrics like NATR)
            metrics_display: list[str] = []
            for m in list(actual_metric_order):
                m = str(m or "").strip()
                if m and m not in metrics_display:
                    metrics_display.append(m)

            for m in list((targets or {}).keys()):
                m = str(m or "").strip()
                if m and m not in metrics_display:
                    metrics_display.append(m)

            # Fall back to existing table metrics if both are empty
            if not metrics_display:
                for m in list(metrics):
                    m = str(m or "").strip()
                    if m and m not in metrics_display:
                        metrics_display.append(m)

            new_rows: list[tuple[str, str, str]] = []
            for metric in metrics_display:
                target = str((targets or {}).get(metric, "") or "").strip()
                actual = str(actuals.get(metric, "") or "").strip()
                new_rows.append((metric, target, actual))

            self.metrics_table.set_rows(new_rows)
        except Exception as ex:
            self._debug_print(f"Failed rebuilding MetricsTable rows: {ex}")

        self._debug_print(
            f"Metrics targets updated for {shift if shift else 'Average of all shifts'} from {csv_path.name}."
        )

    def update_stops_tables(self, df, e=None):
        df = process_data(df)
        line_df = get_line_performance_details(df)

        if not line_df:
            # nothing to show — clear table and return
            self.stops_table.set_rows([])
            self._debug_print("No line performance segments found.")
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
            self._debug_print(f"Config read warning: {app_err}")

        spa_cfg, spa_err = get_spa_service_config()
        if spa_err:
            self._debug_print(f"Config read warning: {spa_err}")

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
            shift=self.sidebar.shift.value[-1]
            if self.sidebar.shift.value[-1].isnumeric()
            else "",
            functional_location=self.sidebar.func_location.value[:4].upper() or "PACK",
            base_url=spa_cfg.base_url or None,
        )

        url = local_url if env == "development" else spa_url

        username, password, cfg_err = get_spa_credentials(
            default_username="DOMAIN\\username",
            default_password="password",
        )
        if cfg_err:
            self._debug_print(f"Config read warning: {cfg_err}")

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
