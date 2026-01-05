import uuid

import flet as ft


class ReportList(ft.ReorderableListView):
    """Reusable report list component."""

    def _clean_text(self, value) -> str:
        try:
            text = "" if value is None else str(value)
            return text.strip()
        except Exception:
            return ""

    def print_all_cards(self):
        """Print all cards (issue, details, actions) to stdout."""
        try:
            text = self.build_report_text()
            print(text if text else "(no cards)")
        except Exception:
            # best-effort; don't crash UI thread
            try:
                print("(failed to print cards)")
            except Exception:
                pass

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

                    action_no = 0
                    for action_text in actions:
                        if not action_text:
                            continue
                        action_no += 1
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
            if row_controls and isinstance(row_controls[0], ft.TextField):
                return self._clean_text(row_controls[0].value)
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
        super().__init__(
            padding=ft.padding.symmetric(vertical=0, horizontal=10),
            on_reorder=self._on_reorder,
            **kwargs,
        )

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

    def append_item_issue(self, text: str = "", *, focus: bool = False):
        """Append a new issue card with a stable key.

        If focus=True, focus its Description field.
        """
        idx = len(self.controls)
        issue_tf_ref: ft.Ref[ft.TextField] = ft.Ref()

        self.controls.append(
            self._make_issue_card(
                str(text),
                index=idx,
                key=f"item-{uuid.uuid4()}",
                issue_textfield_ref=issue_tf_ref,
            )
        )
        self.update()

        if focus:
            try:
                tf = getattr(issue_tf_ref, "current", None)
                if tf is not None:
                    tf.focus()
            except Exception:
                pass

    # Backwards-compatible alias (used elsewhere in the app)
    def append_item(self, text: str):
        self.append_item_issue(text)

    def append_item_detail(
        self, issue_column: ft.Column, text: str = "", *, focus: bool = True
    ):
        """Append a new detail (ExpansionTile) into an issue card's Column.

        If focus=True, focus the new Detail Description field.
        """
        try:
            if len(issue_column.controls) == 1:
                issue_column.controls.append(
                    ft.Divider(height=5, color=ft.Colors.TRANSPARENT)
                )

            detail_tf_ref: ft.Ref[ft.TextField] = ft.Ref()
            detail_tile = self._make_detail_description_for_card(
                issue_column,
                str(text),
                initially_expanded=False,
                detail_textfield_ref=detail_tf_ref,
            )
            issue_column.controls.append(detail_tile)

            issue_column.update()

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
                        if title_controls and isinstance(title_controls[0], ft.TextField):
                            existing_detail_text = str(title_controls[0].value or "")
                    except Exception:
                        existing_detail_text = ""

                    action_texts: list[str] = []
                    for c in list(detail_tile.controls or []):
                        try:
                            if isinstance(c, ft.Container) and isinstance(c.content, ft.Row):
                                row_controls = c.content.controls or []
                                if row_controls and isinstance(row_controls[0], ft.TextField):
                                    action_texts.append(str(row_controls[0].value or ""))
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

            if len(issue_column.controls) == 2 and isinstance(issue_column.controls[1], ft.Divider):
                issue_column.controls.pop(1)

            issue_column.update()
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
            title=ft.Text("Confirm delete"),
            content=ft.Text("Hapus detail ini?"),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.TextButton("Delete", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: _close_dialog(),
        )

        try:
            page.open(dlg)
        except Exception:
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except Exception:
                pass

    def remove_action(self, detail_tile: ft.ExpansionTile, action_container: ft.Container):
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
            title=ft.Text("Confirm delete"),
            content=ft.Text("Hapus action ini?"),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.TextButton("Delete", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: _close_dialog(),
        )

        try:
            page.open(dlg)
        except Exception:
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except Exception:
                pass

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
            title=ft.Text("Confirm delete"),
            content=ft.Text("Hapus issue ini?"),
            actions=[
                ft.TextButton("Cancel", on_click=_close_dialog),
                ft.TextButton("Delete", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: _close_dialog(),
        )

        try:
            page.open(dlg)
        except Exception:
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except Exception:
                pass

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
                column_ref,
                card_ref,
                issue_textfield_ref=issue_textfield_ref,
            )
        )

        return ft.Card(
            ref=card_ref,
            key=key,
            margin=ft.margin.only(top=5, bottom=5, left=0, right=0),
            color=self._get_color(index),
            elevation=5,
            content=ft.Container(
                padding=ft.padding.only(left=10, right=30, top=8, bottom=8),
                content=card_column,
            ),
        )

    def _make_issue_description_for_card(
        self,
        text: str,
        column_ref: ft.Ref[ft.Column],
        card_ref: ft.Ref[ft.Card],
        *,
        issue_textfield_ref: ft.Ref[ft.TextField] | None = None,
    ):
        add_detail_item = ft.PopupMenuItem(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD, color=ft.Colors.GREEN),
                    ft.Text("Add Detail"),
                ]
            ),
            disabled=(str(text or "").strip() == ""),
            on_click=lambda e, r=column_ref: (
                self.append_item_detail(r.current)
                if getattr(r, "current", None) is not None
                else None
            ),
        )

        def _sync_add_detail_enabled(e: ft.ControlEvent | None = None):
            try:
                if e is not None and getattr(e, "control", None) is not None:
                    current_value = getattr(e.control, "value", "")
                elif issue_textfield_ref is not None:
                    tf = getattr(issue_textfield_ref, "current", None)
                    current_value = getattr(tf, "value", "") if tf is not None else ""
                else:
                    current_value = ""

                add_detail_item.disabled = str(current_value or "").strip() == ""
                try:
                    add_detail_item.update()
                except Exception:
                    pass
            except Exception:
                pass

        return ft.Container(
            content=ft.Row(
                [
                    ft.TextField(
                        ref=issue_textfield_ref,
                        value=str(text),
                        label="Description",
                        label_style=ft.TextStyle(
                            size=11,
                            bgcolor=ft.Colors.WHITE,
                        ),
                        text_size=11,
                        text_align=ft.TextAlign.LEFT,
                        multiline=False,
                        border=ft.InputBorder.OUTLINE,
                        border_color=ft.Colors.WHITE,
                        border_radius=8,
                        bgcolor=ft.Colors.WHITE,
                        expand=True,
                        height=30,
                        content_padding=ft.padding.only(
                            left=10, right=0, top=0, bottom=20
                        ),
                        on_change=_sync_add_detail_enabled,
                        on_blur=_sync_add_detail_enabled,
                    ),
                    ft.PopupMenuButton(
                        width=30,
                        height=30,
                        icon=ft.Icon(ft.Icons.MORE_VERT, size=20),
                        padding=ft.padding.only(left=3, right=15, top=3, bottom=15),
                        items=[
                            add_detail_item,
                            ft.PopupMenuItem(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.REMOVE, color=ft.Colors.RED),
                                        ft.Text("Remove"),
                                    ]
                                ),
                                on_click=lambda e, r=card_ref: (
                                    self.confirm_remove_issue(e.control.page, r.current)
                                    if getattr(r, "current", None) is not None
                                    else None
                                ),
                            ),
                        ],
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.SPACE_AROUND,
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

        add_action_item = ft.PopupMenuItem(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD, color=ft.Colors.GREEN),
                    ft.Text("Add action"),
                ]
            ),
            disabled=(str(text or "").strip() == ""),
            on_click=lambda e, r=tile_ref, col=issue_column: (
                self.append_action(r.current, issue_column=col)
                if getattr(r, "current", None) is not None
                else None
            ),
        )

        def _sync_add_action_enabled(e: ft.ControlEvent | None = None):
            try:
                if e is not None and getattr(e, "control", None) is not None:
                    current_value = getattr(e.control, "value", "")
                else:
                    tf = getattr(_detail_tf_ref, "current", None)
                    current_value = getattr(tf, "value", "") if tf is not None else ""

                add_action_item.disabled = str(current_value or "").strip() == ""
                try:
                    add_action_item.update()
                except Exception:
                    pass
            except Exception:
                pass

        return ft.ExpansionTile(
            ref=tile_ref,
            affinity=ft.TileAffinity.LEADING,
            initially_expanded=initially_expanded,
            maintain_state=True,
            collapsed_text_color=ft.Colors.BLUE_800,
            text_color=ft.Colors.BLUE_200,
            tile_padding=ft.padding.only(left=0, right=0, top=0, bottom=0),
            controls_padding=ft.padding.only(left=0, right=0, top=0, bottom=5),
            on_change=lambda e, r=tile_ref: self._on_detail_tile_change(e, r),
            title=ft.Row(
                controls=[
                    ft.TextField(
                        ref=_detail_tf_ref,
                        value=str(text),
                        label="Detail Description",
                        label_style=ft.TextStyle(
                            size=11,
                            bgcolor=ft.Colors.WHITE,
                        ),
                        text_size=11,
                        text_align=ft.TextAlign.LEFT,
                        multiline=False,
                        border=ft.InputBorder.OUTLINE,
                        border_color=ft.Colors.WHITE,
                        border_radius=8,
                        bgcolor=ft.Colors.WHITE,
                        expand=True,
                        height=30,
                        content_padding=ft.padding.only(
                            left=10, right=0, top=0, bottom=20
                        ),
                        on_change=_sync_add_action_enabled,
                        on_blur=_sync_add_action_enabled,
                    ),
                    ft.PopupMenuButton(
                        width=30,
                        height=30,
                        icon=ft.Icon(ft.Icons.MORE_VERT, size=20),
                        padding=ft.padding.only(left=3, right=15, top=3, bottom=15),
                        items=[
                            add_action_item,
                            ft.PopupMenuItem(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.REMOVE, color=ft.Colors.RED),
                                        ft.Text("Remove"),
                                    ]
                                ),
                                on_click=lambda e, r=tile_ref, col=issue_column: (
                                    self.confirm_remove_detail(
                                        e.control.page, col, r.current
                                    )
                                    if getattr(r, "current", None) is not None
                                    else None
                                ),
                            ),
                        ],
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.SPACE_AROUND,
            ),
        )

    def _on_detail_tile_change(self, e: ft.ControlEvent, tile_ref: ft.Ref[ft.ExpansionTile]):
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
        return ft.Container(
            ref=action_ref,
            padding=ft.padding.only(left=60, right=0, top=2, bottom=2),
            content=ft.Row(
                [
                    ft.TextField(
                        ref=action_textfield_ref,
                        value=str(text),
                        label="Action Description",
                        label_style=ft.TextStyle(
                            size=11,
                            bgcolor=ft.Colors.WHITE,
                        ),
                        text_size=11,
                        text_align=ft.TextAlign.LEFT,
                        multiline=False,
                        border=ft.InputBorder.OUTLINE,
                        border_color=ft.Colors.WHITE,
                        border_radius=8,
                        bgcolor=ft.Colors.WHITE,
                        expand=True,
                        height=30,
                        content_padding=ft.padding.only(
                            left=10, right=0, top=0, bottom=20
                        ),
                    ),
                    ft.PopupMenuButton(
                        width=30,
                        height=30,
                        icon=ft.Icon(ft.Icons.MORE_VERT, size=20),
                        padding=ft.padding.only(left=3, right=15, top=3, bottom=15),
                        items=[
                            ft.PopupMenuItem(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.REMOVE, color=ft.Colors.RED),
                                        ft.Text("Remove"),
                                    ]
                                ),
                                on_click=lambda e, ar=action_ref, t=detail_tile, tr=tile_ref: (
                                    self.confirm_remove_action(
                                        e.control.page,
                                        (t if t is not None else getattr(tr, "current", None)),
                                        ar.current,
                                    )
                                    if ar.current is not None
                                    and (t is not None or getattr(tr, "current", None) is not None)
                                    else None
                                ),
                            ),
                        ],
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.SPACE_AROUND,
            ),
        )

    def _get_color(self, i):
        return ft.Colors.RED_200 if i % 2 == 0 else ft.Colors.BLUE_200
