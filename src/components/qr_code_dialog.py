from __future__ import annotations

import base64
import io

import flet as ft


class QrCodeDialog:
    def __init__(
        self,
        *,
        page: ft.Page,
        payload: str,
        title: str = "QR Code",
        width: int = 500,
        height: int = 500,
    ):
        self.page = page
        self.payload = payload
        self.title = title
        self.width = width
        self.height = height

    def show(self):
        page = self.page
        if page is None:
            return

        def _open_dialog(dlg: ft.AlertDialog):
            try:
                page.open(dlg)
                return
            except Exception:
                pass
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except Exception:
                pass

        try:
            # Import here so the rest of the app still works
            # even if qrcode isn't installed.
            import qrcode

            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(self.payload or "")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            dlg: ft.AlertDialog | None = None

            def _close_dialog(_e=None):
                try:
                    if dlg is not None:
                        dlg.open = False
                        page.update()
                except Exception:
                    pass

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(self.title),
                content=ft.Image(
                    src_base64=png_b64,
                    width=self.width,
                    height=self.height,
                ),
                actions=[ft.TextButton("Close", on_click=_close_dialog)],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=lambda _e: _close_dialog(),
            )

            _open_dialog(dlg)

        except Exception as ex:
            # Best-effort error dialog (same UX as before)
            dlg: ft.AlertDialog | None = None

            def _close_dialog(_e=None):
                try:
                    if dlg is not None:
                        dlg.open = False
                        page.update()
                except Exception:
                    pass

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(self.title),
                content=ft.Text(f"Gagal membuat QR: {ex}"),
                actions=[ft.TextButton("Close", on_click=_close_dialog)],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=lambda _e: _close_dialog(),
            )
            _open_dialog(dlg)
