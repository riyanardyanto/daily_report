import csv
import os
import shutil
import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """
    Get the absolute path to a resource, compatible with PyInstaller.

    Args:
        relative_path (str): The relative path to the resource.

    Returns:
        str: The absolute path to the resource.
    """
    base_path = getattr(sys, "_MEIPASS", str(Path(".").resolve()))
    return Path(base_path) / relative_path


def get_script_folder() -> Path:
    """
    Get the absolute path to the script folder, compatible with PyInstaller.

    Returns:
        Path: The absolute path to the script folder.
    """
    if getattr(sys, "frozen", False):
        # When frozen by PyInstaller, prefer the folder containing the
        # original executable (sys.argv[0]) if available. In some
        # PyInstaller modes `sys.executable` points to a temporary
        # extracted binary; writing logs there means they disappear when
        # the temp dir is cleaned. Using argv[0] keeps logs next to the
        # original exe which is what users expect.
        try:
            exe_path = Path(sys.argv[0]).resolve()
            if exe_path.exists():
                return exe_path.parent
        except Exception:
            # Fall back to sys.executable parent if anything goes wrong
            return Path(sys.executable).parent

    return Path(sys.modules["__main__"].__file__).resolve().parent


def get_data_app_dir(folder_name: str = "data_app", create: bool = True) -> Path:
    """Return the directory used to store app data.

    When running as a PyInstaller bundle, writing next to the executable can be
    unsafe (Program Files permissions, OneDrive/network sync, shared folders).
    We therefore prefer a per-user local data directory by default, but keep a
    "portable" layout when the data folder already exists next to the exe.

    Override:
        Set env var DAILY_REPORT_DATA_DIR to force a specific root directory.

    Args:
        folder_name: Name of the data folder to use.
        create: Whether to create the folder if it does not exist.

    Returns:
        Path: Absolute path to the data directory.
    """

    def _user_data_root() -> Path:
        # Per-user data root (no folder_name appended yet).
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if base:
                return Path(base) / "Daily Report"
        return Path.home() / ".daily_report"

    # Allow forcing a custom root directory (e.g. portable deployments).
    override_root = str(os.environ.get("DAILY_REPORT_DATA_DIR", "") or "").strip()
    if override_root:
        data_dir = Path(override_root) / folder_name
    else:
        portable_dir = get_script_folder() / folder_name

        # In frozen deployments, keep non-DB operational folders next to the exe.
        # This matches user expectations for a “portable” layout:
        #   <exe_dir>/data_app/log
        #   <exe_dir>/data_app/settings
        #   <exe_dir>/data_app/targets
        try:
            folder_key = str(folder_name or "").replace("\\", "/").strip().lower()
        except Exception:
            folder_key = str(folder_name or "").strip().lower()

        portable_prefixes = (
            "data_app/log",
            "data_app/settings",
            "data_app/targets",
        )

        if getattr(sys, "frozen", False):
            if any(folder_key.startswith(p) for p in portable_prefixes):
                data_dir = portable_dir
            else:
                # Backward compatibility: if a portable folder already exists next
                # to the exe (and has any contents), keep using it.
                try:
                    if portable_dir.exists() and any(portable_dir.iterdir()):
                        data_dir = portable_dir
                    else:
                        data_dir = _user_data_root() / folder_name
                except Exception:
                    data_dir = _user_data_root() / folder_name
        else:
            data_dir = portable_dir

    if create:
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def data_app_path(*parts: str, folder_name: str = "data_app") -> Path:
    """Convenience helper: build a path inside the data directory."""
    return get_data_app_dir(folder_name=folder_name, create=True).joinpath(*parts)


def ensure_portable_targets_seeded() -> None:
    """Ensure data_app/targets exists next to the exe and seed CSVs if available.

    For one-file PyInstaller builds, bundled data lives under sys._MEIPASS.
    We copy target CSVs to the portable folder only if they don't exist yet.
    """

    if not getattr(sys, "frozen", False):
        return

    try:
        dst_dir = get_script_folder() / "data_app" / "targets"
        dst_dir.mkdir(parents=True, exist_ok=True)

        src_dir = resource_path("data_app/targets")
        if not src_dir.exists() or not src_dir.is_dir():
            return

        for src_file in src_dir.glob("*.csv"):
            dst_file = dst_dir / src_file.name
            if dst_file.exists():
                continue
            try:
                shutil.copy2(src_file, dst_file)
            except Exception:
                pass
    except Exception:
        pass


def load_targets_csv(
    *,
    shift: str = "",
    filename: str = "",
    folder_name: str = "data_app",
    metrics: list[str] | None = None,
) -> tuple[Path, dict[str, str], bool, str | None]:
    """Load targets for a given shift from a CSV stored in the data folder.

    If the CSV does not exist it will be created with empty target values.

    Returns:
        (csv_path, targets, created_template, error_message)
    """

    csv_path = data_app_path(filename, folder_name=folder_name)

    def _parse_float(value: str) -> float | None:
        s = str(value or "").strip()
        if not s:
            return None
        s = s.replace("%", "").strip()
        # Be lenient with common formats: "1,234.5" or "1.234,5".
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s and "." not in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None

    def _fmt_number(n: float) -> str:
        try:
            s = f"{float(n):.2f}"
            s = s.rstrip("0").rstrip(".")
            return s
        except Exception:
            return "N/A"

    if not csv_path.exists():
        try:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = ["Metrics", "Shift 1", "Shift 2", "Shift 3"]
            metrics_list = [m for m in (metrics or []) if str(m).strip()]
            if not metrics_list:
                metrics_list = ["STOP", "PR", "MTBF", "UPDT", "PDT", "NATR"]

            with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for metric in metrics_list:
                    writer.writerow(
                        {
                            "Metrics": str(metric),
                            "Shift 1": "",
                            "Shift 2": "",
                            "Shift 3": "",
                        }
                    )
            if str(shift or "").strip() == "":
                # No shift selected: template contains no numbers yet → N/A.
                return csv_path, {str(m): "N/A" for m in metrics_list}, True, None
            return csv_path, {}, True, None
        except Exception as ex:
            return csv_path, {}, False, str(ex)

    targets: dict[str, str] = {}
    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])

            # If shift == "", return per-metric average across Shift 1/2/3.
            shift_key = str(shift or "").strip()
            if shift_key != "" and shift_key not in fieldnames:
                return (
                    csv_path,
                    {},
                    False,
                    f"Shift column '{shift}' not found. Available: {fieldnames}",
                )

            metric_col = None
            for candidate in ("Metrics", "Metric", "METRICS", "METRIC"):
                if candidate in fieldnames:
                    metric_col = candidate
                    break

            if metric_col is None:
                return (
                    csv_path,
                    {},
                    False,
                    f"Metric column not found. Expected 'Metrics'. Available: {fieldnames}",
                )

            # Try to locate the standard shift columns (be tolerant to casing).
            shift_cols: dict[str, str] = {}
            for want in ("Shift 1", "Shift 2", "Shift 3"):
                for actual in fieldnames:
                    if str(actual).strip().lower() == want.lower():
                        shift_cols[want] = actual
                        break

            for row in reader:
                metric = str(row.get(metric_col, "") or "").strip()
                if metric:
                    if shift_key == "":
                        try:
                            nums: list[float] = []
                            for want in ("Shift 1", "Shift 2", "Shift 3"):
                                col_name = shift_cols.get(want)
                                if not col_name:
                                    continue
                                parsed = _parse_float(str(row.get(col_name, "") or ""))
                                if parsed is not None:
                                    nums.append(parsed)

                            if nums:
                                avg = sum(nums) / float(len(nums))
                                targets[metric] = _fmt_number(avg)
                            else:
                                targets[metric] = "N/A"
                        except Exception:
                            targets[metric] = "N/A"
                    else:
                        value = str(row.get(shift, "") or "").strip()
                        targets[metric] = value

        return csv_path, targets, False, None
    except Exception as ex:
        return csv_path, {}, False, str(ex)


def load_settings_options(
    *,
    filename: str,
    defaults: list[str] | None = None,
) -> tuple[Path, list[str], bool, str | None]:
    """Load dropdown options from data_app/settings/<filename>.

    Format supported:
    - One value per line
    - Comma-separated values per line

    If file does not exist, it will be created from `defaults`.

    Returns:
        (settings_path, options, created_template, error_message)
    """

    # Store settings next to the exe under data_app/settings (portable layout).
    settings_path = data_app_path(filename, folder_name="data_app/settings")
    defaults_list = [str(x).strip() for x in (defaults or []) if str(x).strip()]

    if not settings_path.exists():
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            with settings_path.open("w", encoding="utf-8") as f:
                for item in defaults_list:
                    f.write(f"{item}\n")
            return settings_path, defaults_list, True, None
        except Exception as ex:
            return settings_path, defaults_list, False, str(ex)

    try:
        raw = settings_path.read_text(encoding="utf-8-sig")
    except Exception as ex:
        return settings_path, defaults_list, False, str(ex)

    seen: set[str] = set()
    options: list[str] = []
    try:
        for line in (raw or "").splitlines():
            for part in str(line).split(","):
                value = str(part or "").strip()
                if not value:
                    continue
                key = value.lower()
                if key in seen:
                    continue
                seen.add(key)
                options.append(value)
    except Exception:
        options = []

    if not options and defaults_list:
        return settings_path, defaults_list, False, None

    return settings_path, options, False, None


def save_settings_options(
    *,
    filename: str,
    options: list[str],
) -> tuple[Path, bool, str | None]:
    """Save dropdown options to data_app/settings/<filename>.

    Writes one option per line (UTF-8).

    Returns:
        (settings_path, ok, error_message)
    """

    # Store settings next to the exe under data_app/settings (portable layout).
    settings_path = data_app_path(filename, folder_name="data_app/settings")
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned = [str(x).strip() for x in (options or []) if str(x).strip()]
        with settings_path.open("w", encoding="utf-8") as f:
            for item in cleaned:
                f.write(f"{item}\n")
        return settings_path, True, None
    except Exception as ex:
        return settings_path, False, str(ex)
