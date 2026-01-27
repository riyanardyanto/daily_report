from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import threading
from collections import OrderedDict

import flet as ft

from src.services.config_service import get_ui_config
from src.utils.theme import DANGER, ON_COLOR
from src.utils.ui_helpers import open_dialog

_QR_CACHE_LOCK = threading.Lock()
_QR_CACHE: "OrderedDict[str, str]" = OrderedDict()
_QR_CACHE_MAX: int | None = None


def _get_qr_cache_max() -> int:
    global _QR_CACHE_MAX
    if _QR_CACHE_MAX is not None:
        return _QR_CACHE_MAX
    try:
        ui_cfg, _err = get_ui_config()
        _QR_CACHE_MAX = int(getattr(ui_cfg, "qr_cache_size", 20) or 0)
    except Exception:
        _QR_CACHE_MAX = 20
    if _QR_CACHE_MAX < 0:
        _QR_CACHE_MAX = 0
    return _QR_CACHE_MAX


def _qr_cache_key(payload: str) -> str:
    p = payload or ""
    h = hashlib.sha256(p.encode("utf-8", errors="ignore")).hexdigest()
    return f"sha256:{h}:len:{len(p)}"


def _qr_cache_get(key: str) -> str | None:
    with _QR_CACHE_LOCK:
        v = _QR_CACHE.get(key)
        if v is None:
            return None
        # Mark as recently used
        _QR_CACHE.move_to_end(key)
        return v


def _qr_cache_put(key: str, png_b64: str) -> None:
    max_size = _get_qr_cache_max()
    if max_size <= 0:
        return
    with _QR_CACHE_LOCK:
        _QR_CACHE[key] = png_b64
        _QR_CACHE.move_to_end(key)
        while len(_QR_CACHE) > max_size:
            _QR_CACHE.popitem(last=False)


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

        # Open a lightweight dialog immediately (prevents perceived "no response").
        img = ft.Image(
            src_base64=None,
            width=self.width,
            height=self.height,
            visible=False,
        )
        progress = ft.ProgressRing(visible=True)
        status = ft.Text("Generating QR…", size=12)

        loading_overlay = ft.Container(
            content=ft.Column(
                controls=[progress, status],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
                spacing=10,
            ),
            alignment=ft.alignment.center,
            expand=True,
            visible=True,
        )

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
            content=ft.Container(
                content=ft.Stack(
                    controls=[
                        ft.Container(content=img, alignment=ft.alignment.center),
                        loading_overlay,
                    ],
                    expand=True,
                ),
                alignment=ft.alignment.center,
                padding=ft.padding.all(12),
                bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10,
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.ElevatedButton(
                            "Close",
                            on_click=_close_dialog,
                            color=ON_COLOR,
                            bgcolor=DANGER,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda _e: _close_dialog(),
        )

        open_dialog(page, dlg)

        # Fast path: if we've generated this payload before, show immediately.
        key = _qr_cache_key(self.payload or "")
        cached = _qr_cache_get(key)
        if cached:
            try:
                progress.visible = False
                status.value = ""
                loading_overlay.visible = False
                img.src_base64 = cached
                img.visible = True
                page.update()
            except Exception:
                pass
            return

        async def _generate_qr_async():
            try:
                # Import here so the rest of the app still works even if qrcode isn't installed.
                import qrcode

                def _build_png_b64(payload: str) -> str:
                    qr = qrcode.QRCode(
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=8,
                        border=2,
                    )
                    qr.add_data(payload or "")
                    qr.make(fit=True)
                    img_pil = qr.make_image(fill_color="black", back_color="white")

                    buf = io.BytesIO()
                    img_pil.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode("ascii")

                png_b64 = await asyncio.to_thread(_build_png_b64, self.payload or "")

                try:
                    _qr_cache_put(key, png_b64)
                except Exception:
                    pass

                # Update UI
                try:
                    progress.visible = False
                    status.value = ""
                    loading_overlay.visible = False
                    img.src_base64 = png_b64
                    img.visible = True
                    page.update()
                except Exception:
                    pass
            except Exception as ex:
                try:
                    progress.visible = False
                    status.value = f"Failed to generate QR: {ex}"
                    loading_overlay.visible = True
                    page.update()
                except Exception:
                    pass

        # Run in background if available; otherwise do best-effort sync (may block).
        try:
            runner = getattr(page, "run_task", None)
            if callable(runner):
                # IMPORTANT: pass coroutine function (not coroutine object)
                runner(_generate_qr_async)
                return
        except Exception:
            pass

        # Fallback: run synchronously (older runtimes)
        try:
            import qrcode

            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(self.payload or "")
            qr.make(fit=True)
            img_pil = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img_pil.save(buf, format="PNG")
            png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            try:
                _qr_cache_put(key, png_b64)
            except Exception:
                pass

            progress.visible = False
            status.value = ""
            loading_overlay.visible = False
            img.src_base64 = png_b64
            img.visible = True
            page.update()
        except Exception as ex:
            try:
                progress.visible = False
                status.value = f"Failed to generate QR: {ex}"
                loading_overlay.visible = True
                page.update()
            except Exception:
                pass
