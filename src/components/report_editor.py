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
from src.services.history_db_adapter import save_report_history_sqlite
from src.utils.helpers import data_app_path, load_settings_options
from src.utils.theme import DANGER, INFO, ON_COLOR, PRIMARY, SUCCESS, WARNING
from src.utils.ui_helpers import open_dialog, resolve_page, snack


class ReportEditor(ft.Container):
    def __init__(
        self,
        get_report_table_text=None,
        get_include_table=None,
        get_metrics_rows=None,
        set_metrics_targets=None,
        get_selected_shift=None,
        get_link_up=None,
        get_func_location=None,
        get_date_field=None,
        on_history_saved=None,
        **kwargs,
    ):
        # Default to filling available space so the embedded ReportList becomes scrollable.
        kwargs.setdefault("expand", True)
        self._get_report_table_text_cb = get_report_table_text
        self._get_include_table_cb = get_include_table
        self._get_metrics_rows_cb = get_metrics_rows
        self._set_metrics_targets_cb = set_metrics_targets
        self._get_selected_shift_cb = get_selected_shift
        self._get_link_up_cb = get_link_up
        self._get_func_location_cb = get_func_location
        self._get_date_field_cb = get_date_field
        self._on_history_saved_cb = on_history_saved

        header = ft.Container(
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            margin=ft.margin.only(bottom=10),
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=10,
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.QR_CODE,
                                icon_color=ON_COLOR,
                                bgcolor=WARNING,
                                icon_size=18,
                                tooltip="Show QR code",
                                on_click=self._on_show_qr_code,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                icon_color=ON_COLOR,
                                bgcolor=PRIMARY,
                                icon_size=18,
                                tooltip="Edit target",
                                on_click=self._on_show_target_editor,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SAVE,
                                icon_color=ON_COLOR,
                                bgcolor=SUCCESS,
                                icon_size=18,
                                tooltip="Save report",
                                on_click=self._on_save_report,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.TABLE_ROWS,
                                icon_color=ON_COLOR,
                                bgcolor=INFO,
                                icon_size=18,
                                tooltip="Show history",
                                on_click=self._on_show_history_table,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ADD_ROUNDED,
                                icon_color=ON_COLOR,
                                bgcolor=SUCCESS,
                                icon_size=18,
                                tooltip="Add card",
                                on_click=self._on_add_card,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.RESTORE,
                                icon_color=ON_COLOR,
                                bgcolor=INFO,
                                icon_size=18,
                                tooltip="Restore last cleared",
                                on_click=self._on_restore_last,
                                disabled=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLEAR,
                                icon_color=ON_COLOR,
                                bgcolor=DANGER,
                                icon_size=18,
                                tooltip="Clear all",
                                on_click=self._on_clear_all,
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
                    header,
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
                link_up = str(self._get_link_up_cb() or "LU22")
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = str(self._get_func_location_cb() or "Packer")
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
                link_up = str(self._get_link_up_cb() or "LU22")
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = str(self._get_func_location_cb() or "Packer")
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
                link_up = str(self._get_link_up_cb() or "LU22")
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = str(self._get_func_location_cb() or "Packer")
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
        if not callable(cb):
            return
        try:
            cb(page)
        except Exception:
            return

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
                            str(self._get_selected_shift_cb() or "Shift 1").strip()
                            or "Shift 1"
                        )
                except Exception:
                    shift = "Shift 1"

                link_up = "LU22"
                try:
                    if callable(getattr(self, "_get_link_up_cb", None)):
                        link_up = (
                            str(self._get_link_up_cb() or "LU22").strip() or "LU22"
                        )
                except Exception:
                    link_up = "LU22"

                func_location = "Packer"
                try:
                    if callable(getattr(self, "_get_func_location_cb", None)):
                        func_location = (
                            str(self._get_func_location_cb() or "Packer").strip()
                            or "Packer"
                        )
                except Exception:
                    func_location = "Packer"

                date_field = ""
                try:
                    if callable(getattr(self, "_get_date_field_cb", None)):
                        date_field = str(self._get_date_field_cb() or "").strip()
                except Exception:
                    date_field = ""

                user = str(selected_user or "").strip()

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

    def _on_add_card(self, e):
        try:
            self.report_list.append_item_issue(focus=True)
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
                    str(self._get_selected_shift_cb() or "Shift 1").strip() or "Shift 1"
                )
        except Exception:
            shift = "Shift 1"

        link_up = "LU22"
        try:
            if callable(getattr(self, "_get_link_up_cb", None)):
                link_up = str(self._get_link_up_cb() or "LU22").strip() or "LU22"
        except Exception:
            link_up = "LU22"

        func_location = "Packer"
        try:
            if callable(getattr(self, "_get_func_location_cb", None)):
                func_location = (
                    str(self._get_func_location_cb() or "Packer").strip() or "Packer"
                )
        except Exception:
            func_location = "Packer"

        date_field = ""
        try:
            if callable(getattr(self, "_get_date_field_cb", None)):
                date_field = str(self._get_date_field_cb() or "").strip()
        except Exception:
            date_field = ""

        report_text = ""
        try:
            report_text = self.report_list.build_report_text()
        except Exception:
            report_text = ""

        payload = report_text
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
                    payload = f"{formatted_table_text}\n\n{report_text}".strip()
            except Exception:
                pass

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
