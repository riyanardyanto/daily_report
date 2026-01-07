from __future__ import annotations

import flet as ft


class CardPanel(ft.Container):
    """A lightweight, reusable card wrapper with optional header + actions.

    Use this to keep spacing, borders, and header layout consistent.
    """

    def __init__(
        self,
        *,
        content: ft.Control,
        title: str | None = None,
        actions: list[ft.Control] | None = None,
        width: int | float | None = None,
        height: int | float | None = None,
        expand: bool | int | None = None,
        padding: int = 10,
    ):
        header_controls: list[ft.Control] = []

        if title is not None or actions:
            title_control: ft.Control = ft.Text(
                str(title or ""), size=12, weight=ft.FontWeight.W_600
            )
            actions_row = ft.Row(
                controls=list(actions or []),
                spacing=8,
                alignment=ft.MainAxisAlignment.END,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            header_controls.append(
                ft.Row(
                    controls=[title_control, actions_row],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        body = ft.Column(
            controls=[
                *header_controls,
                content,
            ],
            spacing=10 if header_controls else 0,
            expand=True,
        )

        super().__init__(
            content=body,
            width=width,
            height=height,
            expand=expand,
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.all(padding),
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=10,
        )
