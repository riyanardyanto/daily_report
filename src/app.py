import asyncio

import flet as ft
import pandas as pd

from src.components.card_panel import CardPanel
from src.components.metrics_table import MetricsTable
from src.components.report_editor import ReportEditor
from src.components.report_list_view import ReportList
from src.components.sidebar import Sidebar
from src.components.stops_table import StopsTable
from src.core.context import AppContext, build_context
from src.core.errors import capture_traceback, report_exception, report_exception_sync
from src.core.logging import get_logger
from src.core.safe import safe_event
from src.services.config_service import get_ui_config
from src.services.history_db_service import read_last_saved_user_date_shift
from src.services.spa_facade import SpaFacade, SpaRequest
from src.utils.helpers import data_app_path
from src.utils.ui_helpers import snack


class DashboardApp(ft.Container):
    def __init__(self, page: ft.Page | None = None, *, ctx: AppContext | None = None):
        super().__init__()
        if ctx is None and page is not None:
            try:
                ctx = build_context(page, logger_name="daily_report")
            except Exception:
                ctx = None

        self._ctx = ctx
        self._page = page or (ctx.page if ctx is not None else None)
        self._logger = get_logger("dashboard")
        self._is_compact = False

        # Debug logging (avoid noisy/slow prints in production hot paths)
        self._env_lower = "production"
        self._debug_enabled = False
        try:
            if ctx is not None:
                self._env_lower = (
                    str(ctx.app.environment or "production").strip().lower()
                )
                self._debug_enabled = self._env_lower != "production"
        except Exception:
            self._env_lower = "production"
            self._debug_enabled = False

        # Get Data concurrency + caching
        self._getdata_seq = 0
        self._getdata_running = False
        # key -> (timestamp_monotonic, df, rng_str, metrics_rows, stops_rows)
        self._spa_cache: dict[
            tuple[str, str, str, str, str],
            tuple[float, pd.DataFrame, str, list[tuple[str, str, str]], list[list]],
        ] = {}
        self._spa_cache_ttl_s = 15.0
        try:
            if ctx is not None:
                self._spa_cache_ttl_s = float(
                    getattr(ctx.ui, "spa_cache_ttl_seconds", 15) or 0
                )
            else:
                ui_cfg, _ui_err = get_ui_config()
                self._spa_cache_ttl_s = float(
                    getattr(ui_cfg, "spa_cache_ttl_seconds", 15) or 0
                )
        except Exception:
            self._spa_cache_ttl_s = 15.0

        # Move SPA fetch/transform logic behind a facade for maintainability.
        self._spa_facade: SpaFacade | None = None
        try:
            if self._ctx is not None:
                self._spa_facade = SpaFacade(
                    self._ctx,
                    cache_ttl_s=float(self._spa_cache_ttl_s or 0.0),
                    cache=self._spa_cache,
                )
        except Exception:
            self._spa_facade = None

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
            on_history_saved=self._on_history_saved,
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
        self.sidebar.get_data_button.on_click = safe_event(
            self.update_tables,
            label="sidebar.get_data_button.on_click",
        )
        # allow stops_table to push selected row details into report content via callback (already set on construction)
        self.progress_bar = ft.ProgressBar(
            # bar_height=600,
            height=12,
            visible=False,
            expand=True,
        )

        self.last_saved_info = ft.Text(
            "",
            size=8,
            color=ft.Colors.BLUE_GREY_700,
            italic=True,
            text_align=ft.TextAlign.RIGHT,
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
                            ft.Column(
                                controls=[
                                    self.status_bar,
                                    self.last_saved_info,
                                ],
                                spacing=1,
                                tight=True,
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
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
            msg = " ".join(str(a) for a in args)
            self._logger.debug(msg)
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

    def _resolve_page(self, e=None) -> ft.Page | None:
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

        return page

    def _snapshot_sidebar_values(self) -> tuple[str, str, str, str]:
        """Read UI controls safely on the UI thread."""

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

        return link_up, date_value, shift_value, func_location

    def _snapshot_existing_metrics(self) -> list[str]:
        try:
            existing_rows = self.metrics_table.get_rows_data()
            return [
                str(m or "").strip()
                for m, _t, _a in (existing_rows or [])
                if str(m or "").strip()
            ]
        except Exception:
            return []

    def _bump_getdata_seq(self) -> int:
        try:
            self._getdata_seq += 1
        except Exception:
            self._getdata_seq = 1
        return int(getattr(self, "_getdata_seq", 1) or 1)

    def _is_stale_seq(self, my_seq: int) -> bool:
        try:
            return my_seq != int(getattr(self, "_getdata_seq", my_seq) or my_seq)
        except Exception:
            return False

    def _set_loading(self, page: ft.Page | None, *, loading: bool, status: str = ""):
        try:
            if getattr(self, "progress_bar", None) is not None:
                self.progress_bar.visible = bool(loading)
            if getattr(self, "status_bar", None) is not None and status:
                self.status_bar.value = str(status)
            if page is not None:
                page.update()
        except Exception:
            pass

    async def _refresh_last_saved_info_async(self, page: ft.Page | None):
        """Update the header text with the most recent history metadata."""

        try:
            db_path = data_app_path("history.db", folder_name="data_app/history")

            def _read():
                return read_last_saved_user_date_shift(db_path)

            meta = await asyncio.to_thread(_read)
            if meta is None:
                text = "Last data saved: (no history yet)"
            else:
                user, date_field, shift = meta
                user = str(user or "").strip() or "unknown"
                date_field = str(date_field or "").strip() or "unknown date"
                shift = str(shift or "").strip() or "unknown shift"
                text = f"Last data saved: {user} | {date_field} | {shift}"

            if getattr(self, "last_saved_info", None) is not None:
                self.last_saved_info.value = text
                try:
                    self.last_saved_info.update()
                except Exception:
                    pass
            if page is not None:
                try:
                    page.update()
                except Exception:
                    pass
        except Exception:
            # Never block Get Data if history lookup fails.
            return

    def _on_history_saved(self, page: ft.Page | None) -> None:
        """Called by ReportEditor after a successful save."""

        if page is None:
            return

        runner = getattr(page, "run_task", None)
        if callable(runner):

            async def _run():
                await self._refresh_last_saved_info_async(page)

            try:
                runner(_run)
            except Exception:
                pass
            return

        # Sync fallback (best-effort)
        try:
            db_path = data_app_path("history.db", folder_name="data_app/history")
            meta = read_last_saved_user_date_shift(db_path)
            if meta is None:
                self.last_saved_info.value = "Last data saved: (no history yet)"
            else:
                user, date_field, shift = meta
                user = str(user or "").strip() or "unknown"
                date_field = str(date_field or "").strip() or "unknown date"
                shift = str(shift or "").strip() or "unknown shift"
                self.last_saved_info.value = (
                    f"Last data saved by '{user}', at '{date_field}' - '{shift}'"
                )
            try:
                self.last_saved_info.update()
            except Exception:
                pass
            try:
                page.update()
            except Exception:
                pass
        except Exception:
            return

    def _ensure_spa_facade(self, page: ft.Page | None) -> SpaFacade | None:
        facade = getattr(self, "_spa_facade", None)
        if facade is not None:
            return facade

        try:
            if getattr(self, "_ctx", None) is None and page is not None:
                try:
                    self._ctx = build_context(page, logger_name="daily_report")
                except Exception:
                    self._ctx = None

            if getattr(self, "_ctx", None) is None:
                return None

            facade = SpaFacade(
                self._ctx,
                cache_ttl_s=float(getattr(self, "_spa_cache_ttl_s", 0.0) or 0.0),
                cache=getattr(self, "_spa_cache", None),
            )
            self._spa_facade = facade
            return facade
        except Exception:
            return None

    def _apply_spa_response(self, resp, *, page: ft.Page | None):
        try:
            self.spa_df = resp.df
        except Exception:
            pass

        try:
            label = str(resp.rng_str or "")
            if resp.from_cache:
                label = f"{label} (Cached)" if label else "Cached"
            self.status_bar.value = label
        except Exception:
            pass

        try:
            self.metrics_table.set_rows(resp.metrics_rows)
        except Exception:
            pass

        try:
            self.stops_table.set_rows(resp.stops_rows)
        except Exception:
            pass

    def _build_spa_request(
        self,
        *,
        link_up: str,
        date_value: str,
        shift_value: str,
        func_location: str,
        existing_metrics: list[str],
    ) -> SpaRequest:
        """Build a SpaRequest from already-snapshotted UI values."""

        return SpaRequest(
            link_up=str(link_up or ""),
            date_value=str(date_value or ""),
            shift_value=str(shift_value or ""),
            func_location=str(func_location or "PACK"),
            existing_metrics=list(existing_metrics or []),
        )

    def update_tables(self, e=None):
        page = self._resolve_page(e)

        # Avoid spawning multiple concurrent Get Data workers.
        # This prevents piling up background threads if a request is slow/hung.
        try:
            if bool(getattr(self, "_getdata_running", False)):
                if page is not None:
                    snack(page, "Get Data masih berjalan…", kind="warning")
                return
        except Exception:
            pass

        try:
            self._getdata_running = True
        except Exception:
            pass

        # Snapshot sidebar values on UI thread to avoid reading UI controls in worker thread.
        link_up, date_value, shift_value, func_location = (
            self._snapshot_sidebar_values()
        )
        existing_metrics = self._snapshot_existing_metrics()

        # Seq guard: ignore stale results from previous clicks.
        my_seq = self._bump_getdata_seq()

        # Overall timeout (UI-level failsafe) so Loading never runs forever.
        overall_timeout_s = 75.0
        try:
            ctx = getattr(self, "_ctx", None)
            spa_cfg = getattr(ctx, "spa", None) if ctx is not None else None
            base_timeout = float(getattr(spa_cfg, "timeout", 30) or 30)
            if base_timeout <= 0:
                base_timeout = 30.0
            # Add slack for HTML parsing/processing.
            overall_timeout_s = max(20.0, min(240.0, base_timeout + 45.0))
        except Exception:
            overall_timeout_s = 75.0

        async def _run():
            # Show progress immediately.
            self._set_loading(page, loading=True, status="Loading…")

            # Refresh the "last saved" info without blocking Get Data.
            try:
                await self._refresh_last_saved_info_async(page)
            except Exception:
                pass

            try:
                facade = self._ensure_spa_facade(page)

                if facade is None:
                    raise RuntimeError("SPA facade not initialized")

                req = self._build_spa_request(
                    link_up=link_up,
                    date_value=date_value,
                    shift_value=shift_value,
                    func_location=func_location,
                    existing_metrics=existing_metrics,
                )

                try:
                    resp = await asyncio.wait_for(
                        facade.get_data(req), timeout=float(overall_timeout_s)
                    )
                except asyncio.TimeoutError:
                    if page is not None:
                        snack(
                            page,
                            f"Get Data timeout setelah {int(overall_timeout_s)} detik",
                            kind="warning",
                        )
                    return

                # Ignore stale completion if user clicked again.
                if self._is_stale_seq(my_seq):
                    return

                if resp.df is None:
                    try:
                        self._debug_print("No SPA data available.")
                    except Exception:
                        pass
                    if page is not None:
                        snack(
                            page, "Failed to get SPA data (empty data)", kind="warning"
                        )
                    return

                # Apply results to UI (UI thread)
                self._apply_spa_response(resp, page=page)

            except Exception as ex:
                env_lower = (
                    str(getattr(self, "_env_lower", "production") or "production")
                    .strip()
                    .lower()
                )

                await report_exception(
                    ex,
                    where="DashboardApp.update_tables(async)",
                    env_lower=env_lower,
                    logger_name="dashboard",
                    traceback_text=capture_traceback(),
                )

                if page is not None:
                    snack(page, f"Failed to get SPA data: {ex}", kind="error")
            finally:
                self._set_loading(page, loading=False)
                try:
                    self._getdata_running = False
                except Exception:
                    pass

        if page is None or not hasattr(page, "run_task"):
            # Fallback to the old blocking behavior if run_task isn't available.
            self._set_loading(page, loading=True, status="Loading…")
            try:
                try:
                    # Sync best-effort (single-row query); safe to ignore failures.
                    db_path = data_app_path(
                        "history.db", folder_name="data_app/history"
                    )
                    meta = read_last_saved_user_date_shift(db_path)
                    if meta is None:
                        self.last_saved_info.value = "Last data saved: (no history yet)"
                    else:
                        user, date_field, shift = meta
                        user = str(user or "").strip() or "unknown"
                        date_field = str(date_field or "").strip() or "unknown date"
                        shift = str(shift or "").strip() or "unknown shift"
                        self.last_saved_info.value = (
                            f"Last data saved: {user} | {date_field} | {shift}"
                        )
                    try:
                        self.last_saved_info.update()
                    except Exception:
                        pass
                except Exception:
                    pass

                facade = self._ensure_spa_facade(page)

                if facade is None:
                    if page is not None:
                        snack(page, "SPA service is not initialized", kind="error")
                    return

                req = self._build_spa_request(
                    link_up=link_up,
                    date_value=date_value,
                    shift_value=shift_value,
                    func_location=func_location,
                    existing_metrics=existing_metrics,
                )

                resp = facade.get_data_sync(req)

                if resp.df is None:
                    if page is not None:
                        snack(
                            page, "Failed to get SPA data (empty data)", kind="warning"
                        )
                    return

                self._apply_spa_response(resp, page=page)
            except Exception as ex:
                env_lower = (
                    str(getattr(self, "_env_lower", "production") or "production")
                    .strip()
                    .lower()
                )
                try:
                    report_exception_sync(
                        ex,
                        where="DashboardApp.update_tables(sync)",
                        env_lower=env_lower,
                        logger_name="dashboard",
                        traceback_text=capture_traceback(),
                    )
                except Exception:
                    # Last resort: avoid crashing the UI on error reporting.
                    try:
                        self._logger.exception(
                            "DashboardApp.update_tables(sync): %s", ex
                        )
                    except Exception:
                        pass
                if page is not None:
                    snack(page, f"Failed to get SPA data: {ex}", kind="error")
            finally:
                self._set_loading(page, loading=False)
                try:
                    self._getdata_running = False
                except Exception:
                    pass
            return

        # Flet expects a coroutine *function* here, not a coroutine object.
        try:
            page.run_task(_run)
        except Exception:
            try:
                self._getdata_running = False
            except Exception:
                pass
            raise

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
