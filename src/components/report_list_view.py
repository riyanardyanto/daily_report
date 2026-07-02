import uuid
from collections.abc import Callable
from typing import Any

import flet as ft

from src.utils.theme import (
    DANGER,
    ON_COLOR,
    PRIMARY,
    SUCCESS,
    SURFACE,
    SURFACE_ALT,
    TEXT_MUTED,
    TEXT_SECONDARY,
    WARNING,
)
from src.utils.ui_helpers import open_dialog

# Detail description texts that are fixed / cannot be edited by the user.
# These are PDT-specific template prefixes inserted from the card menu.
# Stored as stripped strings; detection uses .strip() to be space-agnostic.
_DETAIL_READONLY_TEXTS: frozenset[str] = frozenset({"Brand Change", "Follow Up"})


class ReportList(ft.ReorderableListView):
    """Reusable report list component."""

    _last_cleared_state: list[dict[str, Any]] | None
    _on_dirty: Callable[[], None] | None

    def _mark_dirty(self) -> None:
        cb = getattr(self, "_on_dirty", None)
        if not callable(cb):
            return
        try:
            cb()
        except Exception:
            return

    def set_on_dirty(self, cb: Callable[[], None] | None) -> None:
        """Register a callback called after content changes."""
        self._on_dirty = cb

    def _clean_text(self, value) -> str:
        try:
            text = "" if value is None else str(value)
            return text.strip()
        except Exception:
            return ""

    def _get_issue_column(self, issue_card: ft.Control) -> ft.Column | None:
        try:
            container = getattr(issue_card, "content", None)
            column = getattr(container, "content", None)
            return column if isinstance(column, ft.Column) else None
        except Exception:
            return None

    def snapshot_state(self) -> list[dict[str, Any]]:
        """Capture the current list content as plain data."""
        state: list[dict[str, Any]] = []
        try:
            for card in list(getattr(self, "controls", None) or []):
                issue_text = self._extract_issue_text(card)
                details = self._extract_details(card)
                normalized_details: list[dict[str, Any]] = []
                for d in list(details or []):
                    normalized_details.append(
                        {
                            "text": str(d.get("text", "") or ""),
                            "actions": [
                                str(x or "")
                                for x in list(d.get("actions", []) or [])
                                if str(x or "").strip() != ""
                            ],
                        }
                    )
                state.append(
                    {"issue": str(issue_text or ""), "details": normalized_details}
                )
        except Exception:
            return []
        return state

    def can_restore_last(self) -> bool:
        return bool(self._last_cleared_state)

    def discard_last_snapshot(self) -> None:
        self._last_cleared_state = None

    def get_last_snapshot(self) -> list[dict[str, Any]] | None:
        return self._last_cleared_state

    def set_last_snapshot(self, state: list[dict[str, Any]] | None) -> None:
        self._last_cleared_state = list(state) if state else None

    def load_state(
        self, state: list[dict[str, Any]] | None, *, replace_current: bool = True
    ) -> bool:
        """Load a previously captured snapshot into the UI (best-effort)."""
        if not state:
            return False

        try:
            if replace_current:
                self.controls.clear()

            for idx, item in enumerate(list(state)):
                issue_text = str(item.get("issue", "") or "")
                details = list(item.get("details", []) or [])

                issue_tf_ref: ft.Ref[ft.TextField] = ft.Ref()
                card = self._make_issue_card(
                    issue_text,
                    index=idx,
                    key=f"item-{uuid.uuid4()}",
                    issue_textfield_ref=issue_tf_ref,
                )
                self.controls.append(card)

                issue_column = self._get_issue_column(card)
                if issue_column is None:
                    continue

                for detail in details:
                    detail_text = str(detail.get("text", "") or "")
                    action_texts = [
                        str(x or "")
                        for x in list(detail.get("actions", []) or [])
                        if str(x or "").strip() != ""
                    ]

                    if len(issue_column.controls) == 1:
                        issue_column.controls.append(
                            ft.Divider(height=5, color=ft.Colors.TRANSPARENT)
                        )

                    tile = self._make_detail_description_for_card(
                        issue_column,
                        detail_text,
                        initially_expanded=False,
                    )
                    tile.controls = [
                        self._make_action_container(a, detail_tile=tile)
                        for a in action_texts
                    ]
                    issue_column.controls.append(tile)

            self.update()
            self._mark_dirty()
            return True
        except Exception:
            try:
                self.update()
            except Exception:
                pass
            return False

    def clear_all(self, *, backup: bool = True) -> bool:
        """Clear all cards, optionally keeping a restore snapshot."""
        try:
            cards = list(getattr(self, "controls", None) or [])
            if not cards:
                return False

            if backup:
                self._last_cleared_state = self.snapshot_state()

            self.controls.clear()
            self.update()
            self._mark_dirty()
            return True
        except Exception:
            try:
                self.update()
            except Exception:
                pass
            return False

    def restore_last(self, *, replace_current: bool = True) -> bool:
        """Restore the last cleared list (best-effort)."""
        return self.load_state(
            self._last_cleared_state, replace_current=replace_current
        )

    def build_report_text(self) -> str:
        """Build report text for all cards (skips empty/whitespace fields)."""
        try:
            lines: list[str] = []
            for card_index, card in enumerate(list(self.controls), start=1):
                issue_text = self._extract_issue_text(card)
                if issue_text:
                    lines.append(f"*{issue_text}*\n")
                else:
                    lines.append(f"*{card_index}*\n")

                details = self._extract_details(card)
                for detail_index, detail in enumerate(details, start=1):
                    detail_text = detail.get("text", "")
                    actions = detail.get("actions", [])

                    if detail_text:
                        lines.append(f"> {detail_text}\n")
                    elif actions:
                        lines.append(f"> {detail_index}\n")
                    for action_text in actions:
                        if not action_text:
                            continue
                        lines.append(f"- {action_text}\n")

                lines.append("\n")

            return "".join(lines).strip()
        except Exception:
            return ""

    def _extract_issue_text(self, issue_card: ft.Control) -> str:
        try:
            # Card -> content Container -> content Column
            container = getattr(issue_card, "content", None)
            column = getattr(container, "content", None)
            controls = getattr(column, "controls", None) or []
            if not controls:
                return ""

            header = controls[0]
            row = getattr(header, "content", None)
            row_controls = getattr(row, "controls", None) or []
            for c in row_controls:
                if isinstance(c, ft.TextField):
                    return self._clean_text(c.value)
        except Exception:
            pass
        return ""

    def _extract_details(self, issue_card: ft.Control) -> list[dict]:
        details: list[dict] = []
        try:
            container = getattr(issue_card, "content", None)
            column = getattr(container, "content", None)
            controls = getattr(column, "controls", None) or []
            # Skip header (index 0) and optional spacer divider.
            for c in controls[1:]:
                if isinstance(c, ft.Divider):
                    continue
                if isinstance(c, ft.ExpansionTile):
                    detail_text = self._extract_detail_text(c)
                    action_texts = self._extract_actions(c)
                    # Skip printing tiles that contain no non-empty text fields.
                    if not detail_text and not action_texts:
                        continue
                    details.append({"text": detail_text, "actions": action_texts})
        except Exception:
            pass
        return details

    def _extract_detail_text(self, detail_tile: ft.ExpansionTile) -> str:
        try:
            title_row = getattr(detail_tile, "title", None)
            title_controls = getattr(title_row, "controls", None) or []
            if title_controls and isinstance(title_controls[0], ft.TextField):
                return self._clean_text(title_controls[0].value)
        except Exception:
            pass
        return ""

    def _extract_actions(self, detail_tile: ft.ExpansionTile) -> list[str]:
        actions: list[str] = []
        try:
            for c in list(getattr(detail_tile, "controls", None) or []):
                # Action containers are Container(Row(TextField, PopupMenuButton))
                if not isinstance(c, ft.Container):
                    continue
                row = getattr(c, "content", None)
                row_controls = getattr(row, "controls", None) or []
                if row_controls and isinstance(row_controls[0], ft.TextField):
                    cleaned = self._clean_text(row_controls[0].value)
                    if cleaned:
                        actions.append(cleaned)
        except Exception:
            pass
        return actions

    def __init__(self, **kwargs):
        kwargs.setdefault("expand", True)
        self._last_cleared_state = None
        self._on_dirty = None
        self._active_menu_dlg: ft.AlertDialog | None = None
        super().__init__(
            padding=ft.padding.symmetric(vertical=0, horizontal=0),
            on_reorder=self._on_reorder,
            **kwargs,
        )

    def close_active_menu(self) -> None:
        """Programmatically close any open card menu dialog (call on window blur/minimize)."""
        try:
            dlg = getattr(self, "_active_menu_dlg", None)
            if dlg is None:
                return
            page = getattr(self, "page", None)
            if page is None:
                return
            dlg.open = False
            self._active_menu_dlg = None
            try:
                page.update()
            except Exception:
                pass
        except Exception:
            pass

    def _show_card_menu(
        self,
        page: ft.Page | None,
        items: list[tuple[str, ft.Icon, bool, object]],
        title: str | None = None,
    ) -> None:
        """Open a styled AlertDialog acting as a popup menu.

        items is a list of (label, icon, disabled, on_click_callback).
        title is optional text to display at the top of the menu (e.g., issue text).
        """
        if page is None:
            return

        # Close any previously open menu first.
        self.close_active_menu()

        def _close(e=None):
            try:
                dlg.open = False
                self._active_menu_dlg = None
                page.update()
            except Exception:
                pass

        menu_rows: list[ft.Control] = []

        # Add title/header if provided
        if title:
            title_text = ft.Text(
                str(title).strip(),
                size=12,
                weight=ft.FontWeight.BOLD,
                color=TEXT_SECONDARY,
                no_wrap=False,
            )
            menu_rows.append(title_text)
            menu_rows.append(ft.Divider(height=6, color=ft.Colors.BLUE_GREY_100))

        for label, icon, disabled, callback in items:
            cb = callback  # capture

            def _make_handler(c, close_fn):
                def _handler(e=None):
                    close_fn()
                    if callable(c):
                        try:
                            c()
                        except Exception:
                            pass

                return _handler

            row = ft.Container(
                content=ft.Row(
                    [
                        icon,
                        ft.Text(
                            label,
                            size=13,
                            color="#374151" if not disabled else TEXT_MUTED,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                border_radius=8,
                ink=not disabled,
                bgcolor=ft.Colors.TRANSPARENT,
                on_click=None if disabled else _make_handler(cb, _close),
            )
            if disabled:
                row.opacity = 0.4
            menu_rows.append(row)

        dlg = ft.AlertDialog(
            modal=False,
            bgcolor=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=10),
            content_padding=ft.padding.symmetric(horizontal=4, vertical=8),
            content=ft.Column(
                controls=menu_rows,
                spacing=0,
                tight=True,
                width=240,
            ),
            on_dismiss=lambda e: setattr(self, "_active_menu_dlg", None),
        )
        self._active_menu_dlg = dlg
        from src.utils.ui_helpers import open_dialog

        open_dialog(page, dlg)

    def _on_reorder(self, e: ft.OnReorderEvent):
        old_index = e.old_index
        new_index = e.new_index
        if old_index is None or new_index is None:
            return

        # Note: Flet's `new_index` is already the target index for insertion.
        # Decrementing it (like Flutter examples) causes off-by-one behavior.
        if new_index < 0:
            new_index = 0
        if new_index > len(self.controls):
            new_index = len(self.controls)

        try:
            moved = self.controls.pop(old_index)
            self.controls.insert(new_index, moved)
        except Exception:
            return

        self.update()
        self._mark_dirty()

    def append_item_issue(self, text: str = "", *, focus: bool = False):
        """Append a new issue card with a stable key.

        If focus=True, focus its Description field.
        """
        issue_tf_ref: ft.Ref[ft.TextField] = ft.Ref()

        new_prio = self._get_priority(text)

        # Find the first card with priority > new_prio to insert before it.
        insert_idx = len(self.controls)
        for idx, card in enumerate(self.controls):
            if self._get_card_priority(card) > new_prio:
                insert_idx = idx
                break

        new_card = self._make_issue_card(
            str(text),
            index=insert_idx,
            key=f"item-{uuid.uuid4()}",
            issue_textfield_ref=issue_tf_ref,
        )

        self.controls.insert(insert_idx, new_card)
        self.update()
        self._mark_dirty()

        if focus:
            try:
                tf = getattr(issue_tf_ref, "current", None)
                if tf is not None:
                    tf.focus()
            except Exception:
                pass

    def append_item_detail(
        self, issue_column: ft.Column, text: str = "", *, focus: bool = True
    ):
        """Append a new detail (ExpansionTile) into an issue card's Column.

        If focus=True, focus the new Detail Description field.
        Pre-filled details (non-empty text) start expanded so the TextField
        is immediately interactive without the collapsed header intercepting taps.
        """
        try:
            if len(issue_column.controls) == 1:
                issue_column.controls.append(
                    ft.Divider(height=5, color=ft.Colors.TRANSPARENT)
                )

            # Expand immediately when text is pre-filled so the user can
            # click / edit the TextField without the collapsed tile header
            # intercepting the tap event for toggling expansion.
            start_expanded = bool(str(text).strip())

            detail_tf_ref: ft.Ref[ft.TextField] = ft.Ref()
            detail_tile = self._make_detail_description_for_card(
                issue_column,
                str(text),
                initially_expanded=start_expanded,
                detail_textfield_ref=detail_tf_ref,
            )
            issue_column.controls.append(detail_tile)

            issue_column.update()
            self._mark_dirty()

            if focus:
                try:
                    tf = getattr(detail_tf_ref, "current", None)
                    if tf is not None:
                        tf.focus()
                except Exception:
                    pass
        except Exception:
            try:
                self.update()
            except Exception:
                pass

    def append_action(
        self,
        detail_tile: ft.ExpansionTile,
        text: str = "",
        *,
        issue_column: ft.Column | None = None,
        focus: bool = True,
    ):
        """Append a new action into a specific detail ExpansionTile.

        If `issue_column` is provided, the tile will be re-created with
        `initially_expanded=True` to reliably force expansion across Flet versions.
        """
        try:
            if detail_tile.controls is None:
                detail_tile.controls = []

            action_tf_ref: ft.Ref[ft.TextField] = ft.Ref()
            detail_tile.controls.append(
                self._make_action_container(
                    text,
                    detail_tile=detail_tile,
                    action_textfield_ref=action_tf_ref,
                )
            )

            if issue_column is not None:
                try:
                    existing_detail_text = ""
                    try:
                        title_row = getattr(detail_tile, "title", None)
                        title_controls = getattr(title_row, "controls", None) or []
                        if title_controls and isinstance(
                            title_controls[0], ft.TextField
                        ):
                            existing_detail_text = str(title_controls[0].value or "")
                    except Exception:
                        existing_detail_text = ""

                    action_texts: list[str] = []
                    for c in list(detail_tile.controls or []):
                        try:
                            if isinstance(c, ft.Container) and isinstance(
                                c.content, ft.Row
                            ):
                                row_controls = c.content.controls or []
                                if row_controls and isinstance(
                                    row_controls[0], ft.TextField
                                ):
                                    action_texts.append(
                                        str(row_controls[0].value or "")
                                    )
                        except Exception:
                            continue

                    new_tile = self._make_detail_description_for_card(
                        issue_column,
                        existing_detail_text,
                        initially_expanded=True,
                    )

                    rebuilt_controls: list[ft.Control] = []
                    for i, t in enumerate(action_texts):
                        if focus and i == len(action_texts) - 1:
                            rebuilt_controls.append(
                                self._make_action_container(
                                    t,
                                    detail_tile=new_tile,
                                    action_textfield_ref=action_tf_ref,
                                )
                            )
                        else:
                            rebuilt_controls.append(
                                self._make_action_container(t, detail_tile=new_tile)
                            )
                    new_tile.controls = rebuilt_controls

                    for i, c in enumerate(list(issue_column.controls)):
                        if c is detail_tile:
                            issue_column.controls[i] = new_tile
                            break

                    issue_column.update()

                    if focus:
                        try:
                            tf = getattr(action_tf_ref, "current", None)
                            if tf is not None:
                                tf.focus()
                        except Exception:
                            pass
                    return
                except Exception:
                    pass

            try:
                if hasattr(detail_tile, "expanded"):
                    detail_tile.expanded = True
                else:
                    detail_tile.initially_expanded = True
            except Exception:
                pass

            detail_tile.update()
            self._mark_dirty()

            if focus:
                try:
                    tf = getattr(action_tf_ref, "current", None)
                    if tf is not None:
                        tf.focus()
                except Exception:
                    pass
        except Exception:
            try:
                self.update()
            except Exception:
                pass

    def remove_detail(self, issue_column: ft.Column, detail_tile: ft.ExpansionTile):
        """Remove a detail ExpansionTile from a specific issue card's Column."""
        try:
            if issue_column is None or detail_tile is None:
                return

            removed = False
            for i, c in enumerate(list(issue_column.controls)):
                if c is detail_tile:
                    issue_column.controls.pop(i)
                    removed = True
                    break

            if not removed:
                detail_key = getattr(detail_tile, "key", None)
                if detail_key is not None:
                    for i, c in enumerate(list(issue_column.controls)):
                        if getattr(c, "key", None) == detail_key:
                            issue_column.controls.pop(i)
                            break

            if len(issue_column.controls) == 2 and isinstance(
                issue_column.controls[1], ft.Divider
            ):
                issue_column.controls.pop(1)

            issue_column.update()
            self._mark_dirty()
        except Exception:
            try:
                self.update()
            except Exception:
                pass

    def confirm_remove_detail(
        self, page: ft.Page, issue_column: ft.Column, detail_tile: ft.ExpansionTile
    ):
        """Show a confirmation dialog before removing a detail tile."""
        if page is None or issue_column is None or detail_tile is None:
            return

        def _close_dialog(e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(e=None):
            try:
                self.remove_detail(issue_column, detail_tile)
            finally:
                _close_dialog()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Text("Delete this detail?"),
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
                            "Delete",
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
            on_dismiss=lambda e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def remove_action(
        self, detail_tile: ft.ExpansionTile, action_container: ft.Container
    ):
        """Remove an action container from a specific detail ExpansionTile."""
        try:
            if detail_tile is None or action_container is None:
                return
            if detail_tile.controls is None:
                return

            removed = False
            for i, c in enumerate(list(detail_tile.controls)):
                if c is action_container:
                    detail_tile.controls.pop(i)
                    removed = True
                    break

            if not removed:
                action_key = getattr(action_container, "key", None)
                if action_key is not None:
                    for i, c in enumerate(list(detail_tile.controls)):
                        if getattr(c, "key", None) == action_key:
                            detail_tile.controls.pop(i)
                            break

            detail_tile.update()
            self._mark_dirty()
        except Exception:
            try:
                self.update()
            except Exception:
                pass

    def confirm_remove_action(
        self,
        page: ft.Page,
        detail_tile: ft.ExpansionTile,
        action_container: ft.Container,
    ):
        """Show a confirmation dialog before removing an action."""
        if page is None or detail_tile is None or action_container is None:
            return

        def _close_dialog(e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(e=None):
            try:
                self.remove_action(detail_tile, action_container)
            finally:
                _close_dialog()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Text("Delete this action?"),
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
                            "Delete",
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
            on_dismiss=lambda e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def remove_issue(self, issue_card: ft.Card):
        """Remove an issue card from the list."""
        try:
            if issue_card is None:
                return

            removed = False
            for i, c in enumerate(list(self.controls)):
                if c is issue_card:
                    self.controls.pop(i)
                    removed = True
                    break

            if not removed:
                issue_key = getattr(issue_card, "key", None)
                if issue_key is not None:
                    for i, c in enumerate(list(self.controls)):
                        if getattr(c, "key", None) == issue_key:
                            self.controls.pop(i)
                            break

            self.update()
            self._mark_dirty()
        except Exception:
            try:
                self.update()
            except Exception:
                pass

    def confirm_remove_issue(self, page: ft.Page, issue_card: ft.Card):
        """Show a confirmation dialog before removing an issue card."""
        if page is None or issue_card is None:
            return

        def _close_dialog(e=None):
            try:
                dlg.open = False
                page.update()
            except Exception:
                pass

        def _confirm(e=None):
            try:
                self.remove_issue(issue_card)
            finally:
                _close_dialog()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm"),
            content=ft.Container(
                content=ft.Text("Delete this issue?"),
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
                            "Delete",
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
            on_dismiss=lambda e: _close_dialog(),
        )

        open_dialog(page, dlg)

    def _make_issue_card(
        self,
        text: str,
        *,
        index: int,
        key: str,
        issue_textfield_ref: ft.Ref[ft.TextField] | None = None,
    ):
        card_ref: ft.Ref[ft.Card] = ft.Ref()
        column_ref: ft.Ref[ft.Column] = ft.Ref()
        card_column = ft.Column(ref=column_ref, controls=[], spacing=0)
        card_column.controls.append(
            self._make_issue_description_for_card(
                text,
                index,
                column_ref,
                card_ref,
                issue_textfield_ref=issue_textfield_ref,
            )
        )

        return ft.Card(
            ref=card_ref,
            key=key,
            margin=ft.margin.only(top=2, bottom=2, left=0, right=0),
            color=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=12),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            elevation=3,
            shadow_color=f"#40{self._get_color(text, index)[1:]}"
            if self._get_color(text, index).startswith("#")
            else self._get_color(text, index),
            content=ft.Container(
                border=ft.Border(
                    left=ft.BorderSide(5, self._get_color(text, index)),
                    top=ft.BorderSide(1, "#E2E8F0"),
                    right=ft.BorderSide(1, "#E2E8F0"),
                    bottom=ft.BorderSide(1, "#E2E8F0"),
                ),
                border_radius=ft.border_radius.only(
                    top_left=0,
                    bottom_left=0,
                    top_right=12,
                    bottom_right=12,
                ),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                padding=ft.padding.only(left=8, right=24, top=7, bottom=7),
                content=card_column,
            ),
        )

    def _make_issue_description_for_card(
        self,
        text: str,
        index: int,
        column_ref: ft.Ref[ft.Column],
        card_ref: ft.Ref[ft.Card],
        *,
        issue_textfield_ref: ft.Ref[ft.TextField] | None = None,
    ):
        is_read_only = str(text).strip() in {"PDT", "TRL", "PROPOSE NEXT ACTION"}
        _add_detail_disabled = [str(text or "").strip() == ""]

        def _sync_add_detail_enabled(e: ft.ControlEvent | None = None):
            try:
                if e is not None and getattr(e, "control", None) is not None:
                    current_value = getattr(e.control, "value", "")
                elif issue_textfield_ref is not None:
                    tf = getattr(issue_textfield_ref, "current", None)
                    current_value = getattr(tf, "value", "") if tf is not None else ""
                else:
                    current_value = ""
                _add_detail_disabled[0] = str(current_value or "").strip() == ""
            except Exception:
                pass

        def _on_issue_text_change(e: ft.ControlEvent | None = None):
            _sync_add_detail_enabled(e)
            self._mark_dirty()

        def _do_open_issue_menu(e):
            page = getattr(e, "page", None) or getattr(self, "page", None)
            col = getattr(column_ref, "current", None)
            card = getattr(card_ref, "current", None)

            is_pdt = str(text or "").strip().upper() == "PDT"

            if is_pdt:
                self._show_card_menu(
                    page,
                    [
                        (
                            "Brand Change Detail",
                            ft.Icon(
                                ft.Icons.SWAP_HORIZ_ROUNDED, color=SUCCESS, size=14
                            ),
                            False,
                            lambda: (
                                self.append_item_detail(col, text="Brand Change")
                                if col is not None
                                else None
                            ),
                        ),
                        (
                            "Follow Up Detail",
                            ft.Icon(
                                ft.Icons.TRACK_CHANGES_ROUNDED, color=SUCCESS, size=14
                            ),
                            False,
                            lambda: (
                                self.append_item_detail(col, text="Follow Up")
                                if col is not None
                                else None
                            ),
                        ),
                        (
                            "Hapus",
                            ft.Icon(ft.Icons.DELETE_ROUNDED, color=DANGER, size=14),
                            False,
                            lambda: (
                                self.confirm_remove_issue(page, card)
                                if card is not None
                                else None
                            ),
                        ),
                    ],
                    title=text,
                )
            else:
                self._show_card_menu(
                    page,
                    [
                        (
                            "Add detail",
                            ft.Icon(ft.Icons.ADD, color=SUCCESS, size=14),
                            _add_detail_disabled[0],
                            lambda: (
                                self.append_item_detail(col)
                                if col is not None
                                else None
                            ),
                        ),
                        (
                            "Hapus",
                            ft.Icon(ft.Icons.DELETE_ROUNDED, color=DANGER, size=14),
                            False,
                            lambda: (
                                self.confirm_remove_issue(page, card)
                                if card is not None
                                else None
                            ),
                        ),
                    ],
                    title=text,
                )

        return ft.Container(
            content=ft.Row(
                [
                    ft.TextField(
                        ref=issue_textfield_ref,
                        value=str(text),
                        label="Issue",
                        hint_text="Deskripsi issue...",
                        read_only=is_read_only,
                        label_style=ft.TextStyle(
                            size=9,
                            color=TEXT_MUTED,
                        ),
                        text_size=12,
                        text_style=ft.TextStyle(
                            weight=ft.FontWeight.W_500,
                            color="#0F172A",
                        ),
                        text_align=ft.TextAlign.LEFT,
                        multiline=False,
                        border=ft.InputBorder.OUTLINE,
                        border_color="#CBD5E1",
                        focused_border_color=PRIMARY,
                        border_radius=8,
                        bgcolor=SURFACE,
                        fill_color=SURFACE,
                        expand=True,
                        height=36,
                        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
                        on_change=_on_issue_text_change,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.MORE_VERT,
                        icon_color=TEXT_MUTED,
                        icon_size=18,
                        tooltip="Opsi",
                        width=34,
                        height=34,
                        padding=ft.padding.all(0),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                        on_click=_do_open_issue_menu,
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=0, right=0, top=0, bottom=0),
        )

    def _make_detail_description_for_card(
        self,
        issue_column: ft.Column,
        text: str = "",
        *,
        initially_expanded: bool = False,
        detail_textfield_ref: ft.Ref[ft.TextField] | None = None,
    ):
        _detail_tf_ref: ft.Ref[ft.TextField] = (
            detail_textfield_ref if detail_textfield_ref is not None else ft.Ref()
        )

        tile_ref: ft.Ref[ft.ExpansionTile] = ft.Ref()
        _add_action_disabled = [str(text or "").strip() == ""]

        # Detect read-only template texts (e.g. "Brand Change", "Follow Up")
        # Use .strip() so it matches regardless of trailing spaces in stored text.
        is_detail_read_only = str(text).strip() in _DETAIL_READONLY_TEXTS

        def _sync_add_action_enabled(e: ft.ControlEvent | None = None):
            try:
                if e is not None and getattr(e, "control", None) is not None:
                    current_value = getattr(e.control, "value", "")
                else:
                    tf = getattr(_detail_tf_ref, "current", None)
                    current_value = getattr(tf, "value", "") if tf is not None else ""
                _add_action_disabled[0] = str(current_value or "").strip() == ""
            except Exception:
                pass

        def _on_detail_text_change(e: ft.ControlEvent | None = None):
            _sync_add_action_enabled(e)
            self._mark_dirty()

        def _do_open_detail_menu(e):
            page = getattr(e, "page", None) or getattr(self, "page", None)
            tile = getattr(tile_ref, "current", None)
            self._show_card_menu(
                page,
                [
                    (
                        "Add action",
                        ft.Icon(ft.Icons.ADD, color=SUCCESS, size=14),
                        _add_action_disabled[0],
                        lambda: (
                            self.append_action(tile, issue_column=issue_column)
                            if tile is not None
                            else None
                        ),
                    ),
                    (
                        "Hapus",
                        ft.Icon(ft.Icons.DELETE_ROUNDED, color=DANGER, size=14),
                        False,
                        lambda: (
                            self.confirm_remove_detail(page, issue_column, tile)
                            if tile is not None
                            else None
                        ),
                    ),
                ],
                title=text,
            )

        return ft.ExpansionTile(
            ref=tile_ref,
            affinity=ft.TileAffinity.LEADING,
            initially_expanded=initially_expanded,
            maintain_state=True,
            collapsed_text_color="#3B82F6",
            text_color="#60A5FA",
            bgcolor=SURFACE_ALT,
            collapsed_bgcolor=SURFACE_ALT,
            tile_padding=ft.padding.only(left=0, right=4, top=0, bottom=0),
            controls_padding=ft.padding.only(left=0, right=0, top=0, bottom=3),
            shape=ft.RoundedRectangleBorder(radius=8),
            on_change=lambda e, r=tile_ref: self._on_detail_tile_change(e, r),
            title=ft.Row(
                controls=[
                    ft.TextField(
                        ref=_detail_tf_ref,
                        value=str(text),
                        label="Detail deskripsi",
                        read_only=is_detail_read_only,
                        label_style=ft.TextStyle(
                            size=9,
                            color=TEXT_MUTED,
                        ),
                        text_size=11,
                        text_style=ft.TextStyle(
                            color=TEXT_SECONDARY,
                            weight=ft.FontWeight.W_600
                            if is_detail_read_only
                            else ft.FontWeight.NORMAL,
                        ),
                        text_align=ft.TextAlign.LEFT,
                        multiline=False,
                        border=ft.InputBorder.OUTLINE,
                        border_color="#CBD5E1",
                        focused_border_color=PRIMARY,
                        border_radius=8,
                        bgcolor="#F1F5F9" if is_detail_read_only else SURFACE,
                        fill_color="#F1F5F9" if is_detail_read_only else SURFACE,
                        expand=True,
                        height=30,
                        content_padding=ft.padding.only(
                            left=10, right=0, top=0, bottom=20
                        ),
                        on_change=_on_detail_text_change
                        if not is_detail_read_only
                        else None,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.MORE_VERT,
                        icon_color=TEXT_MUTED,
                        icon_size=16,
                        tooltip="Opsi",
                        width=28,
                        height=28,
                        padding=ft.padding.only(left=0, right=0, top=0, bottom=0),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                        on_click=_do_open_detail_menu,
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _on_detail_tile_change(
        self, e: ft.ControlEvent, tile_ref: ft.Ref[ft.ExpansionTile]
    ):
        """Persist expanded/collapsed state across client reconnect/minimize."""
        try:
            tile = getattr(tile_ref, "current", None)
            if tile is None:
                return

            raw = getattr(e, "data", None)
            expanded = None
            if isinstance(raw, str):
                if raw.lower() in ("true", "1", "yes"):
                    expanded = True
                elif raw.lower() in ("false", "0", "no"):
                    expanded = False

            if expanded is None:
                expanded = bool(raw)

            tile.initially_expanded = expanded
            try:
                tile.update()
            except Exception:
                pass
        except Exception:
            pass

    def _make_action_container(
        self,
        text: str = "",
        *,
        detail_tile: ft.ExpansionTile | None = None,
        tile_ref: ft.Ref[ft.ExpansionTile] | None = None,
        action_textfield_ref: ft.Ref[ft.TextField] | None = None,
    ):
        action_ref: ft.Ref[ft.Container] = ft.Ref()

        def _do_open_action_menu(e):
            page = getattr(e, "page", None) or getattr(self, "page", None)
            tile = (
                detail_tile
                if detail_tile is not None
                else getattr(tile_ref, "current", None)
            )
            ac = getattr(action_ref, "current", None)
            self._show_card_menu(
                page,
                [
                    (
                        "Hapus",
                        ft.Icon(ft.Icons.DELETE_ROUNDED, color=DANGER, size=14),
                        False,
                        lambda: (
                            self.confirm_remove_action(page, tile, ac)
                            if tile is not None and ac is not None
                            else None
                        ),
                    ),
                ],
                title=text,
            )

        return ft.Container(
            ref=action_ref,
            padding=ft.padding.only(left=48, right=4, top=2, bottom=2),
            bgcolor=SURFACE,
            border_radius=6,
            content=ft.Row(
                [
                    ft.TextField(
                        ref=action_textfield_ref,
                        value=str(text),
                        label="Action yang dilakukan",
                        label_style=ft.TextStyle(
                            size=9,
                            color=TEXT_MUTED,
                        ),
                        text_size=10,
                        text_style=ft.TextStyle(color=TEXT_SECONDARY),
                        text_align=ft.TextAlign.LEFT,
                        multiline=False,
                        border=ft.InputBorder.OUTLINE,
                        border_color="#CBD5E1",
                        focused_border_color=SUCCESS,
                        border_radius=8,
                        bgcolor=SURFACE,
                        fill_color=SURFACE,
                        expand=True,
                        height=28,
                        content_padding=ft.padding.only(
                            left=10, right=0, top=0, bottom=20
                        ),
                        on_change=lambda _e: self._mark_dirty(),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.MORE_VERT,
                        icon_color=TEXT_MUTED,
                        icon_size=16,
                        tooltip="Opsi",
                        width=28,
                        height=28,
                        padding=ft.padding.all(0),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                        on_click=_do_open_action_menu,
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _get_color(self, text, i):
        """Get card accent color based on its issue text or fallback to DANGER red."""
        try:
            t = str(text or "").strip().upper()
            if t == "PDT":
                return SUCCESS
            elif t == "TRL":
                return WARNING
            elif t in ("PROPOSE NEXT ACTION", "NEXT ACTION"):
                return PRIMARY
            else:
                return DANGER
        except Exception:
            return DANGER

    def _get_priority(self, text: str) -> int:
        """Get card priority level based on text (0=Red, 1=Green, 2=Yellow, 3=Blue)."""
        try:
            t = str(text or "").strip().upper()
            if t == "PDT":
                return 1
            elif t == "TRL":
                return 2
            elif t in ("PROPOSE NEXT ACTION", "NEXT ACTION"):
                return 3
            else:
                return 0
        except Exception:
            return 0

    def _get_card_priority(self, card: ft.Control) -> int:
        """Get priority level of a card control."""
        try:
            txt = self._extract_issue_text(card)
            return self._get_priority(txt)
        except Exception:
            return 0
