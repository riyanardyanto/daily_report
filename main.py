import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Ensure local package imports work in dev and PyInstaller onefile.

    When frozen, PyInstaller extracts bundled modules under `sys._MEIPASS`.
    Adding it to `sys.path` makes absolute imports like `src.entrypoint` reliable.
    """

    try:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            p = str(Path(base))
            if p and p not in sys.path:
                sys.path.insert(0, p)
    except Exception:
        pass

    try:
        here = str(Path(__file__).resolve().parent)
        if here and here not in sys.path:
            sys.path.insert(0, here)
    except Exception:
        pass


_ensure_src_on_path()

from src.entrypoint import run  # noqa: E402

if __name__ == "__main__":
    run()
