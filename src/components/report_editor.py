import asyncio
import json
import os
import re
from datetime import datetime

import flet as ft

from src.components.history_table import HistoryTableDialog
from src.components.qr_code_dialog import QrCodeDialog
from src.components.report_list_view import ReportList
from src.components.target_editor import TargetEditorDialog
from src.services.config_service import get_marquee_config
from src.services.history_db_adapter import (
    save_report_history_sqlite,
)
from src.utils.helpers import data_app_path, load_settings_options
from src.utils.theme import (
    DANGER,
    INFO,
    ON_COLOR,
    PRIMARY,
    SUCCESS,
    SURFACE,
    TEXT_MUTED,
    TEXT_SECONDARY,
    WARNING,
)
from src.utils.ui_helpers import open_dialog, resolve_page, snack


class ReportEditor(ft.Container):
    def __init__(
        self,
        get_report_table_text=None,
        get_include_table=None,
        get_stops_line_table_text=None,
        get_include_line_stop=None,
        get_metrics_rows=None,
        set_metrics_targets=None,
        get_selected_shift=None,
        get_link_up=None,
        get_func_location=None,
        get_date_field=None,
        set_selected_shift=None,
        set_link_up=None,
        set_func_location=None,
        set_date_field=None,
        on_history_saved=None,
        **kwargs,
    ):
        # Default to filling available space so the embedded ReportList becomes scrollable.
        kwargs.setdefault("expand", True)
        self._get_report_table_text_cb = get_report_table_text
        self._get_include_table_cb = get_include_table
        self._get_stops_line_table_text_cb = get_stops_line_table_text
        self._get_include_line_stop_cb = get_include_line_stop
        self._get_metrics_rows_cb = get_metrics_rows
        self._set_metrics_targets_cb = set_metrics_targets
        self._get_selected_shift_cb = get_selected_shift
        self._get_link_up_cb = get_link_up
        self._get_func_location_cb = get_func_location
        self._get_date_field_cb = get_date_field
        self._set_selected_shift_cb = set_selected_shift
        self._set_link_up_cb = set_link_up
        self._set_func_location_cb = set_func_location
        self._set_date_field_cb = set_date_field
        self._on_history_saved_cb = on_history_saved

        def _icon_btn(icon, color, tip, handler, *, disabled=False) -> ft.IconButton:
            """Helper to create a styled icon button."""
            return ft.IconButton(
                icon=icon,
                icon_color=ON_COLOR,
                bgcolor=color,
                icon_size=18,
                tooltip=tip,
                on_click=handler,
                disabled=disabled,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    animation_duration=150,
                ),
            )

        header = ft.Container(
            bgcolor=SURFACE,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            margin=ft.margin.only(bottom=8),
            border_radius=12,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=10,
                color="#0000000D",
                offset=ft.Offset(0, 2),
            ),
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            _icon_btn(
                                ft.Icons.QR_CODE_ROUNDED,
                                WARNING,
                                "Show QR code",
                                self._on_show_qr_code,
                            ),
                            _icon_btn(
                                ft.Icons.EDIT_ROUNDED,
                                PRIMARY,
                                "Edit target",
                                self._on_show_target_editor,
                            ),
                            _icon_btn(
                                ft.Icons.SAVE_ROUNDED,
                                SUCCESS,
                                "Save report",
                                self._on_save_report,
                            ),
                            _icon_btn(
                                ft.Icons.TABLE_ROWS_ROUNDED,
                                INFO,
                                "Show history",
                                self._on_show_history_table,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.PopupMenuButton(
                                content=ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.ADD_ROUNDED, color=ON_COLOR, size=18
                                    ),
                                    bgcolor=SUCCESS,
                                    width=40,
                                    height=40,
                                    border_radius=20,
                                    alignment=ft.alignment.center,
                                ),
                                tooltip="Add card",
                                items=[
                                    ft.PopupMenuItem(
                                        content=ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.CANCEL_OUTLINED,
                                                    size=16,
                                                    color=ft.Colors.RED_700,
                                                ),
                                                ft.Text("UPDT card", size=12),
                                            ],
                                            spacing=8,
                                        ),
                                        on_click=lambda e: self._on_add_card(
                                            e, text=""
                                        ),
                                    ),
                                    ft.PopupMenuItem(
                                        content=ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.PAUSE_CIRCLE_OUTLINED,
                                                    size=16,
                                                    color=ft.Colors.GREEN_600,
                                                ),
                                                ft.Text("PDT card", size=12),
                                            ],
                                            spacing=8,
                                        ),
                                        on_click=lambda e: self._on_add_card(
                                            e, text="PDT"
                                        ),
                                    ),
                                    ft.PopupMenuItem(
                                        content=ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.TRENDING_DOWN,
                                                    size=16,
                                                    color=ft.Colors.ORANGE_600,
                                                ),
                                                ft.Text("TRL card", size=12),
                                            ],
                                            spacing=8,
                                        ),
                                        on_click=lambda e: self._on_add_card(
                                            e, text="TRL"
                                        ),
                                    ),
                                    ft.PopupMenuItem(
                                        content=ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.LIGHTBULB_OUTLINED,
                                                    size=16,
                                                    color=ft.Colors.BLUE_600,
                                                ),
                                                ft.Text("PROPOSE NEXT ACTION", size=12),
                                            ],
                                            spacing=8,
                                        ),
                                        on_click=lambda e: self._on_add_card(
                                            e, text="PROPOSE NEXT ACTION"
                                        ),
                                    ),
                                ],
                            ),
                            _icon_btn(
                                ft.Icons.RESTORE_ROUNDED,
                                INFO,
                                "Restore last cleared",
                                self._on_restore_last,
                                disabled=True,
                            ),
                            _icon_btn(
                                ft.Icons.CLEAR_ROUNDED,
                                DANGER,
                                "Clear all",
                                self._on_clear_all,
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                expand=True,
                spacing=10,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        self.report_list = ReportList(expand=True)
        self._pending_draft_task = None

        # Panel: last saved data (with expand/collapse)
        self._last_saved_expanded = False  # default: collapsed
        self._last_saved_cards_col = ft.Column(
            controls=[],
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
            visible=False,  # hidden when collapsed
        )
        self._last_saved_chevron = ft.Icon(
            ft.Icons.EXPAND_MORE,
            size=14,
            color=PRIMARY,
        )
        self._last_saved_meta_text = ft.Text(
            "",
            size=8,
            color=TEXT_MUTED,
            italic=True,
            no_wrap=False,
            expand=True,
        )
        # Navigation state for last saved panel
        self._all_save_ids_list: list[
            tuple[str, str]
        ] = []  # List of (save_id, saved_at)
        self._current_save_index = 0  # Index in _all_save_ids_list
        self._current_filter_link_up: str | None = None
        self._current_filter_func_location: str | None = None
        self._last_saved_nav_text = ft.Text(
            "",
            size=8,
            color=TEXT_MUTED,
            italic=True,
        )
        self._last_saved_prev_btn = ft.IconButton(
            icon=ft.Icons.ARROW_BACK_IOS_ROUNDED,
            icon_size=12,
            icon_color=PRIMARY,
            tooltip="Previous save",
            on_click=self._on_prev_save,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )
        self._last_saved_next_btn = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
            icon_size=12,
            icon_color=PRIMARY,
            tooltip="Next save",
            on_click=self._on_next_save,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )
        # Menu button for last saved panel actions
        self._last_saved_menu_btn = ft.PopupMenuButton(
            items=[
                ft.PopupMenuItem(
                    text="Show QR Code",
                    icon=ft.Icons.QR_CODE_ROUNDED,
                    on_click=self._on_show_last_saved_qr_code,
                ),
                ft.PopupMenuItem(
                    text="Load to Editor",
                    icon=ft.Icons.EDIT_ROUNDED,
                    on_click=self._on_load_last_saved_to_editor,
                ),
            ],
            icon=ft.Icons.MORE_VERT,
            icon_size=16,
            icon_color=PRIMARY,
            tooltip="Actions",
            menu_position=ft.PopupMenuPosition.UNDER,
        )
        _panel_header_row = ft.Row(
            controls=[
                self._last_saved_prev_btn,
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.HISTORY_ROUNDED, size=14, color=PRIMARY),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Data Terakhir Tersimpan",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT_SECONDARY,
                                ),
                                self._last_saved_meta_text,
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self._last_saved_chevron,
                self._last_saved_menu_btn,
                self._last_saved_next_btn,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        self._panel_header_container = ft.Container(
            content=_panel_header_row,
            on_click=self._on_toggle_last_saved,
            border_radius=6,
            ink=True,
            padding=ft.padding.symmetric(horizontal=4, vertical=2),
        )
        self._last_saved_panel = ft.Container(
            content=ft.Column(
                controls=[
                    self._panel_header_container,
                    self._last_saved_cards_col,
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor="#EFF6FF",
            border=ft.border.only(left=ft.BorderSide(3, PRIMARY)),
            border_radius=ft.border_radius.only(top_right=8, bottom_right=8),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            visible=False,
            margin=ft.margin.only(top=6),
        )

        # Running (marquee) text (load from config)
        try:
            mc, _err = get_marquee_config()
            msg = (
                mc.message
                if mc and getattr(mc, "message", None) is not None
                else ("      JANGAN LUPA SAVE REPORT            <===<      ")
            )
            interval_ms = getattr(mc, "interval_ms", 150) if mc is not None else 150
        except Exception:
            msg = "      JANGAN LUPA SAVE REPORT            <===<      "
            interval_ms = 150

        self._running_msg = str(msg or "")
        self._marquee_interval = float(int(interval_ms)) / 1000.0

        self._running_text = ft.Text(
            self._running_msg,
            color="#4338CA",
            size=9,
            expand=True,
            text_align=ft.TextAlign.LEFT,
            weight=ft.FontWeight.W_500,
        )
        self._marquee_task = None

        # Autosave draft (so it survives accidental close/restart)
        try:
            self.report_list.set_on_dirty(self._schedule_persist_draft)
        except Exception:
            pass

        # Keep a handle to the Restore button (header -> Row[1] -> controls[1])
        try:
            self._restore_btn = header.content.controls[1].controls[1]
        except Exception:
            self._restore_btn = None

        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Column(
                        controls=[
                            header,
                            # Marquee / running text (full width)
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        expand=True,
                                        content=self._running_text,
                                        bgcolor="#EEF2FF",
                                        height=22,
                                        padding=ft.padding.symmetric(horizontal=10),
                                        alignment=ft.alignment.center,
                                        border_radius=6,
                                        border=ft.border.only(
                                            left=ft.BorderSide(3, "#6366F1")
                                        ),
                                    )
                                ],
                                expand=False,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            # Panel last saved data
                            self._last_saved_panel,
                        ],
                        spacing=0,
                    ),
                    self.report_list,
                ],
                expand=True,
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
            ),
            **kwargs,
        )

    def did_mount(self):
        # Called when added to the page; page is available here.
        try:
            self._load_draft_from_disk()
        except Exception:
            pass
        try:
            self._sync_restore_enabled(getattr(self, "page", None))
        except Exception:
            pass
        try:
            self._start_marquee()
        except Exception:
            pass
        try:
            self._refresh_last_saved_panel(getattr(self, "page", None))
        except Exception:
            pass

    def _draft_store_path(self):
        # Store in settings (portable-friendly in frozen builds).
        # Draft files are keyed by (functional location, link_up) so they don't
        # overwrite across different areas. We also add a user/pc suffix to avoid
        # collisions when settings folder is shared.

        def _safe_part(v: str, *, max_len: int = 40) -> str:
            try:
                s = str(v or "").strip().lower()
            except Exception:
                s = ""
            if not s:
                return "na"
            s = re.sub(r"\s+", "_", s)
            s = re.sub(r"[^a-z0-9._-]", "_", s)
            s = re.sub(r"_+", "_", s).strip("_")
            if not s:
                return "na"
            if len(s) > max_len:
                s = s[:max_len]
            return s

        link_up = "LU22"
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                link_up = self._get_link_up_cb() or "LU22"
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = self._get_func_location_cb() or "Packer"
        except Exception:
            func_location = "Packer"

        key = "_".join(
            [
                _safe_part(func_location, max_len=30),
                _safe_part(link_up, max_len=20),
            ]
        )

        # Add a per-user / per-PC suffix to avoid collisions in shared folders.
        try:
            username = (
                str(os.environ.get("USERNAME") or os.environ.get("USER") or "")
                .strip()
                .lower()
            )
        except Exception:
            username = ""
        try:
            computername = str(os.environ.get("COMPUTERNAME") or "").strip().lower()
        except Exception:
            computername = ""

        suffix = "__".join(
            [
                f"user-{_safe_part(username, max_len=24)}",
                f"pc-{_safe_part(computername, max_len=24)}",
            ]
        )

        filename = f"draft_report_{key}__{suffix}.json"
        return data_app_path(filename, folder_name="data_app/history/drafts")

    def _persist_draft_now(self) -> None:
        try:
            draft = self.report_list.snapshot_state()
        except Exception:
            draft = []

        try:
            last_cleared = self.report_list.get_last_snapshot() or []
        except Exception:
            last_cleared = []

        store_path = self._draft_store_path()

        # If nothing to persist, delete stale file.
        if not draft and not last_cleared:
            try:
                if store_path.exists():
                    store_path.unlink()
            except Exception:
                pass

            # Also cleanup older drafts for the same context.
            try:
                legacy_keyed = self._draft_store_path_legacy_no_suffix()
                if legacy_keyed is not None and legacy_keyed.exists():
                    legacy_keyed.unlink()
            except Exception:
                pass
            try:
                for p in self._legacy_shift_date_draft_paths_for_context():
                    try:
                        if p.exists():
                            p.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
            return

        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "draft": draft,
            "last_cleared": last_cleared,
        }

        try:
            store_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Never crash UI for draft persistence
            return

        # Cleanup older no-suffix keyed draft for the same context.
        try:
            legacy_keyed = self._draft_store_path_legacy_no_suffix()
            if legacy_keyed is not None and legacy_keyed.exists():
                legacy_keyed.unlink()
        except Exception:
            pass

        # Cleanup older shift/date-based drafts for the same context.
        try:
            for p in self._legacy_shift_date_draft_paths_for_context():
                try:
                    if p != store_path and p.exists():
                        p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def _schedule_persist_draft(self) -> None:
        """Debounced draft save (safe to call very frequently)."""
        try:
            prev = getattr(self, "_pending_draft_task", None)
            if prev is not None and hasattr(prev, "cancel"):
                try:
                    prev.cancel()
                except Exception:
                    pass
        except Exception:
            pass

        page = getattr(self, "page", None)

        async def _runner():
            try:
                await asyncio.sleep(0.4)
            except Exception:
                return
            self._persist_draft_now()
            try:
                self._sync_restore_enabled(page)
            except Exception:
                pass

        try:
            if page is not None and callable(getattr(page, "run_task", None)):
                self._pending_draft_task = page.run_task(_runner)
            else:
                # Fallback: best-effort immediate write
                self._persist_draft_now()
        except Exception:
            self._persist_draft_now()

    def _clear_draft_storage(self) -> None:
        try:
            p = self._draft_store_path()
            if p.exists():
                p.unlink()
        except Exception:
            return

        # Backward-compat: remove older no-suffix keyed draft for the same context.
        try:
            p2 = self._draft_store_path_legacy_no_suffix()
            if p2 is not None and p2.exists():
                p2.unlink()
        except Exception:
            pass

        # Backward-compat: remove older shift/date-based drafts for the same context.
        try:
            for p3 in self._legacy_shift_date_draft_paths_for_context():
                try:
                    if p3.exists():
                        p3.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        # Backward-compat: remove legacy global file if present.
        try:
            legacy = data_app_path("draft_report.json", folder_name="data_app/settings")
            if legacy.exists():
                legacy.unlink()
        except Exception:
            return

    def _load_draft_from_disk(self) -> None:
        page = getattr(self, "page", None)

        target_path = self._draft_store_path()
        store_path = target_path
        loaded_from = target_path

        # Backward-compat: older keyed drafts without user/pc suffix.
        legacy_keyed = self._draft_store_path_legacy_no_suffix()
        if (
            not store_path.exists()
            and legacy_keyed is not None
            and legacy_keyed.exists()
        ):
            store_path = legacy_keyed
            loaded_from = legacy_keyed

        # Backward-compat: older drafts keyed by shift/date (previous versions).
        if not store_path.exists():
            legacy_shift_date = None
            try:
                legacy_paths = self._legacy_shift_date_draft_paths_for_context()
                if legacy_paths:
                    legacy_shift_date = legacy_paths[0]
            except Exception:
                legacy_shift_date = None
            if legacy_shift_date is not None and legacy_shift_date.exists():
                store_path = legacy_shift_date
                loaded_from = legacy_shift_date

        # Backward-compat: if keyed draft doesn't exist, try legacy.
        legacy_path = data_app_path(
            "draft_report.json", folder_name="data_app/settings"
        )
        if not store_path.exists() and legacy_path.exists():
            store_path = legacy_path
            loaded_from = legacy_path

        if not store_path.exists():
            return

        try:
            raw = store_path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
        except Exception:
            return

        draft = data.get("draft")
        last_cleared = data.get("last_cleared")

        try:
            if isinstance(last_cleared, list):
                self.report_list.set_last_snapshot(last_cleared)
        except Exception:
            pass

        # Only auto-restore draft when the editor is empty.
        try:
            has_cards = bool(list(getattr(self.report_list, "controls", None) or []))
        except Exception:
            has_cards = False

        if (not has_cards) and isinstance(draft, list) and draft:
            # Avoid triggering multiple saves while initializing.
            try:
                self.report_list.set_on_dirty(None)
            except Exception:
                pass

            try:
                self.report_list.load_state(draft, replace_current=True)
            except Exception:
                pass
            finally:
                try:
                    self.report_list.set_on_dirty(self._schedule_persist_draft)
                except Exception:
                    pass

            try:
                if page is not None:
                    snack(page, "Restored unsaved draft", kind="warning")
            except Exception:
                pass

        # Always migrate legacy sources (even if draft is empty but last_cleared exists).
        try:
            if loaded_from != target_path:
                self._persist_draft_now()
                try:
                    loaded_from.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def _draft_store_path_legacy_no_suffix(self):
        """Return the previous keyed-draft path (without user/pc suffix)."""
        # Keep the implementation in sync with _draft_store_path(), minus suffix.

        def _safe_part(v: str, *, max_len: int = 40) -> str:
            try:
                s = str(v or "").strip().lower()
            except Exception:
                s = ""
            if not s:
                return "na"
            s = re.sub(r"\s+", "_", s)
            s = re.sub(r"[^a-z0-9._-]", "_", s)
            s = re.sub(r"_+", "_", s).strip("_")
            if not s:
                return "na"
            if len(s) > max_len:
                s = s[:max_len]
            return s

        link_up = "LU22"
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                link_up = self._get_link_up_cb() or "LU22"
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = self._get_func_location_cb() or "Packer"
        except Exception:
            func_location = "Packer"

        key = "_".join(
            [
                _safe_part(func_location, max_len=30),
                _safe_part(link_up, max_len=20),
            ]
        )
        filename = f"draft_report_{key}.json"
        return data_app_path(filename, folder_name="data_app/history/drafts")

    def _legacy_shift_date_draft_paths_for_context(self) -> list:
        """Find older shift/date keyed draft files for the current (fl, link_up) context."""

        def _safe_part(v: str, *, max_len: int = 40) -> str:
            try:
                s = str(v or "").strip().lower()
            except Exception:
                s = ""
            if not s:
                return "na"
            s = re.sub(r"\s+", "_", s)
            s = re.sub(r"[^a-z0-9._-]", "_", s)
            s = re.sub(r"_+", "_", s).strip("_")
            if not s:
                return "na"
            if len(s) > max_len:
                s = s[:max_len]
            return s

        link_up = "LU22"
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                link_up = self._get_link_up_cb() or "LU22"
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = self._get_func_location_cb() or "Packer"
        except Exception:
            func_location = "Packer"

        lu = _safe_part(link_up, max_len=40)
        fl = _safe_part(func_location, max_len=40)

        try:
            drafts_dir = data_app_path(
                "_", folder_name="data_app/history/drafts"
            ).parent
        except Exception:
            return []

        needle = f"__lu-{lu}__fl-{fl}__date-"
        found = []
        try:
            for p in drafts_dir.glob("draft_report__shift-*__lu-*__fl-*__date-*.json"):
                try:
                    name = str(getattr(p, "name", "") or "")
                    if needle in name:
                        found.append(p)
                except Exception:
                    continue
        except Exception:
            return []

        def _mtime(path):
            try:
                return path.stat().st_mtime
            except Exception:
                return 0

        found.sort(key=_mtime, reverse=True)
        return found

    def _notify_history_saved(self, page: ft.Page | None) -> None:
        cb = getattr(self, "_on_history_saved_cb", None)
        if callable(cb):
            try:
                cb(page)
            except Exception:
                pass
        # Refresh the last saved panel after a save
        try:
            self._refresh_last_saved_panel(page)
        except Exception:
            pass

    def _build_last_saved_card_widget(self, card_data: dict, idx: int) -> ft.Container:
        """Build a compact card widget for a single saved card entry."""
        issue_text = str(card_data.get("issue", "") or "").strip()
        details = list(card_data.get("details", []) or [])

        detail_widgets: list[ft.Control] = []
        for d in details:
            detail_text = str(d.get("text", "") or "").strip()
            actions = list(d.get("actions", []) or [])
            if detail_text:
                detail_widgets.append(
                    ft.Text(
                        f"  • {detail_text}",
                        size=9,
                        color=ft.Colors.BLUE_GREY_700,
                        no_wrap=False,
                    )
                )
            for act in actions:
                act_s = str(act or "").strip()
                if act_s:
                    detail_widgets.append(
                        ft.Text(
                            f"      ↳ {act_s}",
                            size=8,
                            color=ft.Colors.BLUE_GREY_500,
                            italic=True,
                            no_wrap=False,
                        )
                    )

        controls: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Text(
                            str(idx),
                            size=8,
                            color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD,
                        ),
                        bgcolor=ft.Colors.BLUE_GREY_400,
                        border_radius=10,
                        width=16,
                        height=16,
                        alignment=ft.alignment.center,
                    ),
                    ft.Text(
                        issue_text or "(no issue)",
                        size=10,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.BLUE_GREY_800,
                        no_wrap=False,
                        expand=True,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        ]
        controls.extend(detail_widgets)

        return ft.Container(
            content=ft.Column(controls=controls, spacing=2, tight=True),
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.BLUE_GREY_100),
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
        )

    def _on_toggle_last_saved(self, e=None) -> None:
        """Toggle expand/collapse of the last saved data panel body."""
        panel = getattr(self, "_last_saved_panel", None)
        col = getattr(self, "_last_saved_cards_col", None)
        chevron = getattr(self, "_last_saved_chevron", None)
        if panel is None or col is None:
            return

        self._last_saved_expanded = not bool(
            getattr(self, "_last_saved_expanded", False)
        )
        expanded = self._last_saved_expanded

        try:
            col.visible = expanded
        except Exception:
            pass

        try:
            if chevron is not None:
                chevron.name = (
                    ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE
                )
        except Exception:
            pass

        page = getattr(self, "page", None)
        try:
            col.update()
        except Exception:
            pass
        try:
            if chevron is not None:
                chevron.update()
        except Exception:
            pass
        try:
            panel.update()
        except Exception:
            pass
        if page is not None:
            try:
                page.update()
            except Exception:
                pass

    def _on_load_last_saved_to_editor(self, e=None) -> None:
        """Load the currently displayed last saved data into the editor."""
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        try:
            current_result = getattr(self, "_last_saved_result", None)
            cards = list((current_result or {}).get("cards", []) or [])
            if not cards:
                snack(page, "No saved data to load", kind="warning")
                return

            def _do_load_saved_to_editor() -> None:
                # Keep current editor state as restore snapshot before replacing.
                prev_state = []
                try:
                    prev_state = self.report_list.snapshot_state()
                except Exception:
                    prev_state = []

                meta = dict((current_result or {}).get("meta", {}) or {})

                editor_state: list[dict[str, object]] = []
                for card in cards:
                    issue = str((card or {}).get("issue", "") or "")
                    details_src = list((card or {}).get("details", []) or [])
                    details: list[dict[str, object]] = []
                    for detail in details_src:
                        detail_text = str((detail or {}).get("text", "") or "")
                        actions = [
                            str(a or "").strip()
                            for a in list((detail or {}).get("actions", []) or [])
                            if str(a or "").strip()
                        ]
                        details.append({"text": detail_text, "actions": actions})

                    editor_state.append({"issue": issue, "details": details})

                ok = self.report_list.load_state(editor_state, replace_current=True)
                if not ok:
                    snack(page, "Could not load saved data", kind="error")
                    return

                # Auto-fill sidebar metadata from the selected saved data.
                summary_shift = ""
                summary_link_up = ""
                summary_func_location = ""
                summary_date_field = ""
                try:
                    shift_v = str(meta.get("shift", "") or "").strip()
                    link_up_v = str(meta.get("link_up", "") or "").strip()
                    func_location_v = str(meta.get("func_location", "") or "").strip()
                    date_field_v = str(meta.get("date_field", "") or "").strip()

                    if shift_v and callable(
                        getattr(self, "_set_selected_shift_cb", None)
                    ):
                        self._set_selected_shift_cb(shift_v)
                    summary_shift = (
                        str(self._get_selected_shift_cb() or "").strip()
                        if callable(getattr(self, "_get_selected_shift_cb", None))
                        else shift_v
                    )

                    if link_up_v and callable(getattr(self, "_set_link_up_cb", None)):
                        self._set_link_up_cb(link_up_v)
                    summary_link_up = (
                        str(self._get_link_up_cb() or "").strip()
                        if callable(getattr(self, "_get_link_up_cb", None))
                        else link_up_v
                    )

                    if func_location_v and callable(
                        getattr(self, "_set_func_location_cb", None)
                    ):
                        self._set_func_location_cb(func_location_v)
                    summary_func_location = (
                        str(self._get_func_location_cb() or "").strip()
                        if callable(getattr(self, "_get_func_location_cb", None))
                        else func_location_v
                    )

                    if date_field_v and callable(
                        getattr(self, "_set_date_field_cb", None)
                    ):
                        self._set_date_field_cb(date_field_v)
                    summary_date_field = (
                        str(self._get_date_field_cb() or "").strip()
                        if callable(getattr(self, "_get_date_field_cb", None))
                        else date_field_v
                    )
                except Exception:
                    pass

                summary_parts = [
                    summary_shift,
                    summary_link_up,
                    summary_func_location,
                    summary_date_field,
                ]
                summary_text = " | ".join(
                    [str(x).strip() for x in summary_parts if str(x).strip()]
                )
                if not summary_text:
                    summary_text = "metadata auto-filled"

                try:
                    if prev_state:
                        self.report_list.set_last_snapshot(prev_state)
                    self._sync_restore_enabled(page)
                except Exception:
                    pass

                try:
                    self._persist_draft_now()
                except Exception:
                    pass

                snack(
                    page,
                    f"Saved data loaded into editor: {summary_text}",
                    kind="success",
                )

            has_editor_cards = bool(
                list(getattr(self.report_list, "controls", None) or [])
            )
            if not has_editor_cards:
                _do_load_saved_to_editor()
                return

            def _close_dialog(_e=None):
                try:
                    dlg.open = False
                    page.update()
                except Exception:
                    pass

            def _confirm(_e=None):
                try:
                    _do_load_saved_to_editor()
                finally:
                    _close_dialog()

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Confirm"),
                content=ft.Container(
                    content=ft.Text(
                        "Replace current editor content with the selected saved data?"
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
                                on_click=_close_dialog,
                                color=ON_COLOR,
                                bgcolor=DANGER,
                            ),
                            ft.ElevatedButton(
                                "Load",
                                on_click=_confirm,
                                color=ON_COLOR,
                                bgcolor=INFO,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=lambda _e: _close_dialog(),
            )
            open_dialog(page, dlg)
        except Exception:
            snack(page, "Could not load saved data", kind="error")

    def _refresh_last_saved_panel(self, page: ft.Page | None) -> None:
        """Load last save data from DB and update the panel widget.

        Uses run_task + asyncio.to_thread if available to avoid blocking the UI thread.
        Falls back to a synchronous read otherwise.
        """
        panel = getattr(self, "_last_saved_panel", None)
        col = getattr(self, "_last_saved_cards_col", None)
        if panel is None or col is None:
            return

        # Try async path (non-blocking DB read)
        runner = getattr(page, "run_task", None) if page is not None else None

        # Snapshot sidebar values on the UI thread before going async
        cur_link_up = ""
        cur_func_location = ""
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                cur_link_up = (self._get_link_up_cb() or "").strip()
        except Exception:
            cur_link_up = ""
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                cur_func_location = (self._get_func_location_cb() or "").strip()
        except Exception:
            cur_func_location = ""

        if callable(runner):

            async def _async_refresh():
                try:
                    db_path = data_app_path(
                        "history.db", folder_name="data_app/history"
                    )
                    from src.services.history_db_adapter import (
                        read_all_save_ids_filtered,
                        read_save_cards_by_id,
                    )

                    # Load all save_ids first
                    all_saves = await asyncio.to_thread(
                        read_all_save_ids_filtered,
                        db_path,
                        link_up=cur_link_up or None,
                        func_location=cur_func_location or None,
                    )
                    self._all_save_ids_list = all_saves
                    self._current_save_index = 0
                    self._current_filter_link_up = cur_link_up or None
                    self._current_filter_func_location = cur_func_location or None
                    self._update_nav_buttons()

                    # Load the first (most recent) save
                    if all_saves:
                        save_id = all_saves[0][0]
                        result = await asyncio.to_thread(
                            read_save_cards_by_id,
                            db_path,
                            save_id,
                        )
                    else:
                        result = None
                except Exception:
                    result = None
                    self._all_save_ids_list = []
                    self._current_save_index = 0
                self._apply_last_saved_result(result)

            try:
                runner(_async_refresh)
                return
            except Exception:
                pass

        # Sync fallback
        try:
            db_path = data_app_path("history.db", folder_name="data_app/history")

            # Load all save_ids first to initialize navigation list
            from src.services.history_db_adapter import (
                read_all_save_ids_filtered,
                read_save_cards_by_id,
            )

            all_saves = read_all_save_ids_filtered(
                db_path,
                link_up=cur_link_up or None,
                func_location=cur_func_location or None,
            )
            self._all_save_ids_list = all_saves
            self._current_save_index = 0
            self._current_filter_link_up = cur_link_up or None
            self._current_filter_func_location = cur_func_location or None
            self._update_nav_buttons()

            # Load the first (most recent) save
            if all_saves:
                save_id = all_saves[0][0]
                result = read_save_cards_by_id(db_path, save_id)
            else:
                result = None
        except Exception:
            result = None
            self._all_save_ids_list = []
            self._current_save_index = 0
        self._apply_last_saved_result(result)

    def _update_nav_buttons(self) -> None:
        """Update prev/next button states and nav text based on current index."""
        prev_btn = getattr(self, "_last_saved_prev_btn", None)
        next_btn = getattr(self, "_last_saved_next_btn", None)
        nav_text = getattr(self, "_last_saved_nav_text", None)
        saves_list = getattr(self, "_all_save_ids_list", [])
        current_idx = getattr(self, "_current_save_index", 0)

        if prev_btn is not None:
            try:
                prev_btn.disabled = current_idx >= len(saves_list) - 1
                prev_btn.update()
            except Exception:
                pass

        if next_btn is not None:
            try:
                next_btn.disabled = current_idx <= 0
                next_btn.update()
            except Exception:
                pass

        if nav_text is not None:
            try:
                if saves_list:
                    display_idx = current_idx + 1  # Display 1-based for users
                    nav_text.value = f"{display_idx}/{len(saves_list)}"
                else:
                    nav_text.value = ""
                nav_text.update()
            except Exception:
                pass

    def _load_and_display_save(self, index: int) -> None:
        """Load and display a specific save by index."""
        saves_list = getattr(self, "_all_save_ids_list", [])
        if not saves_list or index < 0 or index >= len(saves_list):
            return

        self._current_save_index = index
        self._update_nav_buttons()

        try:
            db_path = data_app_path("history.db", folder_name="data_app/history")
            from src.services.history_db_adapter import read_save_cards_by_id

            save_id = saves_list[index][0]
            result = read_save_cards_by_id(db_path, save_id)

            # Store the current saved data for later access (e.g., for QR code)
            self._last_saved_result = result

            # Apply the result to the UI
            self._apply_last_saved_result(result)
        except Exception:
            pass

    def _apply_last_saved_result(self, result) -> None:
        """Apply loaded save result to the panel widget. Extracted from _refresh_last_saved_panel."""
        # Store result for later access (e.g., for QR code display)
        self._last_saved_result = result

        page = getattr(self, "page", None)
        panel = getattr(self, "_last_saved_panel", None)
        col = getattr(self, "_last_saved_cards_col", None)
        if panel is None or col is None:
            return

        meta_text_widget = getattr(self, "_last_saved_meta_text", None)
        chevron = getattr(self, "_last_saved_chevron", None)
        expanded = bool(getattr(self, "_last_saved_expanded", False))

        if result is None:
            try:
                panel.visible = False
                panel.update()
            except Exception:
                pass
            return

        meta = result.get("meta", {})
        cards = result.get("cards", [])

        if not cards:
            try:
                panel.visible = False
                panel.update()
            except Exception:
                pass
            return

        # Build meta line (compact, shown in header even when collapsed)
        user = str(meta.get("user", "") or "").strip() or "—"
        date_field = str(meta.get("date_field", "") or "").strip() or "—"
        shift = str(meta.get("shift", "") or "").strip() or "—"
        link_up = str(meta.get("link_up", "") or "").strip()
        func_loc = str(meta.get("func_location", "") or "").strip()
        saved_at_raw = str(meta.get("saved_at", "") or "").strip()
        saved_at_disp = saved_at_raw
        try:
            from datetime import datetime as _dt

            saved_at_disp = _dt.fromisoformat(saved_at_raw).strftime("%d/%m %H:%M")
        except Exception:
            pass

        meta_parts = []
        if func_loc:
            meta_parts.append(func_loc)
        if link_up:
            meta_parts.append(link_up)
        meta_parts.append(date_field)
        meta_parts.append(shift)
        meta_parts.append(f"by {user}")
        if saved_at_disp:
            meta_parts.append(f"@ {saved_at_disp}")
        meta_line = " | ".join(meta_parts)

        # Update the inline meta text in the header
        try:
            if meta_text_widget is not None:
                meta_text_widget.value = meta_line
        except Exception:
            pass

        # Update chevron to match current expanded state
        try:
            if chevron is not None:
                chevron.name = (
                    ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE
                )
        except Exception:
            pass

        # Rebuild cards column (cards only, no meta text row here)
        new_controls = []
        new_controls.append(ft.Divider(height=4, color=ft.Colors.BLUE_GREY_100))
        for i, card_data in enumerate(cards, start=1):
            new_controls.append(self._build_last_saved_card_widget(card_data, i))

        try:
            col.controls = new_controls
            col.visible = expanded  # respect current state
            panel.visible = True
            try:
                col.update()
            except Exception:
                pass
            try:
                panel.update()
            except Exception:
                pass
            if page is not None:
                try:
                    page.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_prev_save(self, e=None) -> None:
        """Navigate to previous (older) save."""
        current_idx = getattr(self, "_current_save_index", 0)
        saves_list = getattr(self, "_all_save_ids_list", [])

        # Prev means going to older saves (higher index in our descending list)
        next_idx = current_idx + 1
        if next_idx < len(saves_list):
            self._load_and_display_save(next_idx)

    def _on_next_save(self, e=None) -> None:
        """Navigate to next (newer) save."""
        current_idx = getattr(self, "_current_save_index", 0)

        # Next means going to newer saves (lower index in our descending list)
        if current_idx > 0:
            self._load_and_display_save(current_idx - 1)

    def _sync_restore_enabled(self, page: ft.Page | None = None) -> None:
        btn = getattr(self, "_restore_btn", None)
        if btn is None:
            return
        try:
            btn.disabled = not bool(
                getattr(self.report_list, "can_restore_last", lambda: False)()
            )
            try:
                btn.update()
                return
            except Exception:
                pass
            if page is not None:
                page.update()
        except Exception:
            return

    def _on_restore_last(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        if not self.report_list.can_restore_last():
            snack(page, "Nothing to restore", kind="warning")
            self._sync_restore_enabled(page)
            return

        cards = list(getattr(self.report_list, "controls", None) or [])

        def _do_restore():
            ok = self.report_list.restore_last(replace_current=True)
            self._sync_restore_enabled(page)
            try:
                self._persist_draft_now()
            except Exception:
                pass
            snack(
                page,
                "Restored last cleared cards" if ok else "Restore failed",
                kind="success" if ok else "error",
            )

        if cards:

            def _close_dialog(_e=None):
                try:
                    dlg.open = False
                    page.update()
                except Exception:
                    pass

            def _confirm(_e=None):
                try:
                    _do_restore()
                finally:
                    _close_dialog()

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Confirm"),
                content=ft.Container(
                    content=ft.Text(
                        "Replace current cards with the last cleared list?"
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
                                on_click=_close_dialog,
                                color=ON_COLOR,
                                bgcolor=DANGER,
                            ),
                            ft.ElevatedButton(
                                "Restore",
                                on_click=_confirm,
                                color=ON_COLOR,
                                bgcolor=INFO,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=lambda _e: _close_dialog(),
            )
            open_dialog(page, dlg)
            return

        _do_restore()

    def _on_show_history_table(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        csv_path = data_app_path("history.csv", folder_name="data_app/history")
        db_path = data_app_path("history.db", folder_name="data_app/history")
        HistoryTableDialog(
            page=page,
            csv_path=csv_path,
            db_path=db_path,
            hidden_columns={
                "save_id",
                "saved_at",
                "card_index",
                "detail_index",
                "action_index",
            },
        ).show()

    def _on_save_report(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        cards = list(getattr(self.report_list, "controls", None) or [])
        if not cards:
            snack(page, "No cards to save", kind="warning")
            return

        # Load user options (from data_app/settings/user.txt)
        try:
            _p, user_options, _created, _err = load_settings_options(
                filename="user.txt",
                defaults=["Alice", "Bob", "Charlie"],
            )
        except Exception:
            user_options = ["Alice", "Bob", "Charlie"]

        if not user_options:
            user_options = ["Alice", "Bob", "Charlie"]

        user_dd = ft.Dropdown(
            options=[ft.dropdown.Option(opt) for opt in user_options],
            label="User",
            hint_text="Choose your name",
            text_size=12,
            expand=True,
            content_padding=10,
            value=None,
        )

        def _do_save(selected_user: str):
            try:
                # Sidebar metadata (best-effort)
                shift = "Shift 1"
                try:
                    if callable(getattr(self, "_get_selected_shift_cb", None)):
                        shift = (
                            self._get_selected_shift_cb() or "Shift 1"
                        ).strip() or "Shift 1"
                except Exception:
                    shift = "Shift 1"

                link_up = "LU22"
                try:
                    if callable(getattr(self, "_get_link_up_cb", None)):
                        link_up = (self._get_link_up_cb() or "LU22").strip() or "LU22"
                except Exception:
                    link_up = "LU22"

                func_location = "Packer"
                try:
                    if callable(getattr(self, "_get_func_location_cb", None)):
                        func_location = (
                            self._get_func_location_cb() or "Packer"
                        ).strip() or "Packer"
                except Exception:
                    func_location = "Packer"

                date_field = ""
                try:
                    if callable(getattr(self, "_get_date_field_cb", None)):
                        date_field = (self._get_date_field_cb() or "").strip()
                except Exception:
                    date_field = ""

                user = (selected_user or "").strip()

                db_path = data_app_path("history.db", folder_name="data_app/history")

                snack(page, "Saving…", kind="warning")

                async def _run_save():
                    try:

                        def _worker():
                            return save_report_history_sqlite(
                                db_path=db_path,
                                cards=cards,
                                extract_issue=self.report_list._extract_issue_text,
                                extract_details=self.report_list._extract_details,
                                shift=shift,
                                link_up=link_up,
                                func_location=func_location,
                                date_field=date_field,
                                user=user,
                            )

                        ok, msg = await asyncio.to_thread(_worker)
                        msg_l = str(msg or "").lower()
                        if ok:
                            kind = "success"
                        elif any(k in msg_l for k in ("terbuka", "terkunci", "locked")):
                            kind = "warning"
                        else:
                            kind = "error"
                        snack(page, msg, kind=kind)
                        if ok:
                            try:
                                self.report_list.discard_last_snapshot()
                                self._sync_restore_enabled(page)
                                self._clear_draft_storage()
                            except Exception:
                                pass
                            self._notify_history_saved(page)
                    except Exception as ex:
                        snack(page, f"Failed to save report: {ex}", kind="error")

                runner = getattr(page, "run_task", None)
                if callable(runner):
                    runner(_run_save)
                else:
                    # Fallback (blocking) if run_task isn't available
                    ok, msg = save_report_history_sqlite(
                        db_path=db_path,
                        cards=cards,
                        extract_issue=self.report_list._extract_issue_text,
                        extract_details=self.report_list._extract_details,
                        shift=shift,
                        link_up=link_up,
                        func_location=func_location,
                        date_field=date_field,
                        user=user,
                    )
                    msg_l = str(msg or "").lower()
                    if ok:
                        kind = "success"
                    elif any(k in msg_l for k in ("terbuka", "terkunci", "locked")):
                        kind = "warning"
                    else:
                        kind = "error"
                    snack(page, msg, kind=kind)
                    if ok:
                        try:
                            self.report_list.discard_last_snapshot()
                            self._sync_restore_enabled(page)
                            self._clear_draft_storage()
                        except Exception:
                            pass
                        self._notify_history_saved(page)
            except Exception as ex:
                snack(page, f"Failed to save report: {ex}", kind="error")

        def _close_dialog(_e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(_e=None):
            selected_user = str(getattr(user_dd, "value", "") or "").strip()
            if not selected_user:
                snack(page, "Please select a user before saving.", kind="warning")
                return
            try:
                _close_dialog()
            finally:
                _do_save(selected_user)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Select user:"),
                        user_dd,
                        ft.Divider(height=10),
                        ft.Text(f"Save report to history? ({len(cards)} card)"),
                    ],
                    spacing=10,
                ),
                padding=ft.padding.all(12),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10,
                height=150,
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.ElevatedButton(
                            "Cancel",
                            on_click=_close_dialog,
                            color=ON_COLOR,
                            bgcolor=DANGER,
                        ),
                        ft.ElevatedButton(
                            "Save",
                            on_click=_confirm,
                            color=ON_COLOR,
                            bgcolor=SUCCESS,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def _on_add_card(self, e, text: str = ""):
        try:
            self.report_list.append_item_issue(text=text, focus=True)
        except Exception:
            pass

    def _on_clear_all(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        try:
            if not (getattr(self.report_list, "controls", None) or []):
                snack(page, "No cards to clear", kind="warning")
                return
        except Exception:
            pass

        def _close_dialog(_e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(_e=None):
            try:
                self.report_list.clear_all(backup=True)
                self._sync_restore_enabled(page)
                try:
                    self._persist_draft_now()
                except Exception:
                    pass
            finally:
                _close_dialog()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Text("Clear all cards?"),
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
                            on_click=_close_dialog,
                            color=ON_COLOR,
                            bgcolor=DANGER,
                        ),
                        ft.ElevatedButton(
                            "Clear",
                            on_click=_confirm,
                            color=ON_COLOR,
                            bgcolor=DANGER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def _on_show_qr_code(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        # Sidebar metadata (best-effort) to prepend as the first line of QR payload
        shift = "Shift 1"
        try:
            if callable(getattr(self, "_get_selected_shift_cb", None)):
                shift = (
                    self._get_selected_shift_cb() or "Shift 1"
                ).strip() or "Shift 1"
        except Exception:
            shift = "Shift 1"

        link_up = "LU22"
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                link_up = (self._get_link_up_cb() or "LU22").strip() or "LU22"
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = (
                    self._get_func_location_cb() or "Packer"
                ).strip() or "Packer"
        except Exception:
            func_location = "Packer"

        date_field = ""
        try:
            if callable(getattr(self, "_get_date_field_cb", None)):
                date_field = (self._get_date_field_cb() or "").strip()
        except Exception:
            date_field = ""

        report_text = ""
        try:
            report_text = self.report_list.build_report_text()
        except Exception:
            report_text = ""

        payload = report_text
        payload_sections: list[str] = []
        include_table = True
        try:
            if callable(getattr(self, "_get_include_table_cb", None)):
                include_table = bool(self._get_include_table_cb())
        except Exception:
            include_table = True

        if include_table and callable(getattr(self, "_get_report_table_text_cb", None)):
            try:
                table_text: str = self._get_report_table_text_cb()
                replaced_table_text = table_text.replace("\n", "`\n`")
                formatted_table_text = f"`{replaced_table_text}`".strip()
                if table_text:
                    payload_sections.append(
                        f"*=== TARGET vs ACTUAL ===*\n{formatted_table_text}".strip()
                    )
            except Exception:
                pass

        include_line_stop = True
        try:
            if callable(getattr(self, "_get_include_line_stop_cb", None)):
                include_line_stop = bool(self._get_include_line_stop_cb())
        except Exception:
            include_line_stop = True

        if include_line_stop and callable(
            getattr(self, "_get_stops_line_table_text_cb", None)
        ):
            try:
                stops_table_text: str = self._get_stops_line_table_text_cb()
                replaced_stops_text = stops_table_text.replace("\n", "`\n`")
                formatted_stops_text = f"`{replaced_stops_text}`".strip()
                if stops_table_text:
                    payload_sections.append(
                        f"*=== LINE STOP SUMMARY ===*\n{formatted_stops_text}".strip()
                    )
            except Exception:
                pass

        if report_text:
            payload_sections.append(f"*=== DETAIL REPORT ===*\n{report_text}".strip())
        if payload_sections:
            payload = "\n\n".join(payload_sections).strip()

        meta_line = (
            f"*{func_location.upper()} {link_up[-2:]} | {date_field} | {shift}*"
        ).strip()
        payload = f"{meta_line}\n{payload}".strip()

        QrCodeDialog(page=page, payload=payload).show()

    def _on_show_last_saved_qr_code(self, e):
        """Show QR code for the currently displayed last-saved data in _last_saved_cards_col."""
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        # Get the result data that was used to populate _last_saved_cards_col
        result = getattr(self, "_last_saved_result", None)
        if not result:
            snack(page, "No saved data to display", kind="warning")
            return

        meta = result.get("meta", {})
        cards = result.get("cards", [])

        # Verify we have cards to show
        if not cards:
            snack(page, "No cards in saved data", kind="warning")
            return

        # Build report text from saved cards that are displayed in _last_saved_cards_col
        report_sections = []
        for card_data in cards:
            issue_text = str(card_data.get("issue", "") or "").strip()
            details = list(card_data.get("details", []) or [])

            if issue_text:
                report_sections.append(f"*{issue_text}*")

            for detail in details:
                detail_text = str(detail.get("text", "") or "").strip()
                actions = list(detail.get("actions", []) or [])

                if detail_text:
                    report_sections.append(f"> {detail_text}")

                for action in actions:
                    action_text = str(action or "").strip()
                    if action_text:
                        report_sections.append(f"- {action_text}")

            report_sections.append("\n")  # Add a blank line between cards

        report_text = "\n".join(report_sections)

        # Extract metadata from the displayed last saved data
        # user = str(meta.get("user", "") or "").strip() or "—"
        date_field = str(meta.get("date_field", "") or "").strip() or "—"
        shift = str(meta.get("shift", "") or "").strip() or "—"
        link_up = str(meta.get("link_up", "") or "").strip() or "LU22"
        func_location = str(meta.get("func_location", "") or "").strip() or "Packer"

        # Build QR payload with metadata and all displayed cards
        payload_sections = []
        if report_text:
            payload_sections.append(f"*=== SAVED REPORT ===*\n{report_text}".strip())

        payload = (
            "\n\n".join(payload_sections).strip() if payload_sections else report_text
        )

        meta_line = (
            f"*{func_location.upper()} {link_up[-2:]} | {date_field} | {shift}*"
        ).strip()
        payload = f"{meta_line}\n{payload}".strip()

        QrCodeDialog(page=page, payload=payload).show()

    def _on_show_target_editor(self, e):
        page = resolve_page(e, fallback=getattr(self, "page", None))
        if page is None:
            return

        TargetEditorDialog(
            page=page,
            get_selected_shift=getattr(self, "_get_selected_shift_cb", None),
            get_link_up=getattr(self, "_get_link_up_cb", None),
            get_func_location=getattr(self, "_get_func_location_cb", None),
            get_metrics_rows=getattr(self, "_get_metrics_rows_cb", None),
            set_metrics_targets=getattr(self, "_set_metrics_targets_cb", None),
        ).show()

    def _start_marquee(self) -> None:
        """Start a background task that rotates the running text value."""
        page = getattr(self, "page", None)
        if getattr(self, "_marquee_task", None) is not None:
            return

        async def _runner():
            try:
                while True:
                    await asyncio.sleep(0.15)
                    try:
                        s = str(getattr(self, "_running_msg", "") or "")
                        if not s:
                            continue
                        s = s[1:] + s[0]
                        self._running_msg = s
                        try:
                            self._running_text.value = s
                            self._running_text.update()
                        except Exception:
                            # fallback to page update
                            if page is not None:
                                try:
                                    page.update()
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except asyncio.CancelledError:
                return

        runner = getattr(page, "run_task", None)
        if callable(runner):
            try:
                # Pass coroutine function (not coroutine object) as expected by run_task
                self._marquee_task = runner(_runner)
            except Exception:
                self._marquee_task = None
        else:
            try:
                # Fallback: schedule coroutine on default event loop
                self._marquee_task = asyncio.create_task(_runner())
            except Exception:
                self._marquee_task = None

    def _stop_marquee(self) -> None:
        t = getattr(self, "_marquee_task", None)
        if t is None:
            return
        try:
            if hasattr(t, "cancel"):
                t.cancel()
        except Exception:
            pass
        self._marquee_task = None

    def did_unmount(self):
        try:
            self._stop_marquee()
        except Exception:
            pass
