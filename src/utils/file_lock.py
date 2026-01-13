from __future__ import annotations

import sys
from pathlib import Path


def is_file_locked_windows(path: str | Path) -> bool:
    """Return True if file is locked by another process (Windows only, best-effort)."""

    try:
        if sys.platform != "win32":
            return False

        p = Path(path)
        if not p.exists():
            return False

        import ctypes

        GENERIC_READ = 0x80000000
        FILE_SHARE_NONE = 0
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        CreateFileW = ctypes.windll.kernel32.CreateFileW
        CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        CreateFileW.restype = ctypes.c_void_p

        handle = CreateFileW(
            str(p),
            GENERIC_READ,
            FILE_SHARE_NONE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )

        if handle == INVALID_HANDLE_VALUE:
            return True

        try:
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass

        return False
    except Exception:
        return False
