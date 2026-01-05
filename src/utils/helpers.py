import csv
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

    The directory is created next to the executable when running as a
    PyInstaller bundle, otherwise next to the entry script.

    Args:
        folder_name: Name of the data folder to use.
        create: Whether to create the folder if it does not exist.

    Returns:
        Path: Absolute path to the data directory.
    """
    data_dir = get_script_folder() / folder_name
    if create:
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def data_app_path(*parts: str, folder_name: str = "data_app") -> Path:
    """Convenience helper: build a path inside the data directory."""
    return get_data_app_dir(folder_name=folder_name, create=True).joinpath(*parts)


def load_targets_csv(
    *,
    shift: str,
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
            return csv_path, {}, True, None
        except Exception as ex:
            return csv_path, {}, False, str(ex)

    targets: dict[str, str] = {}
    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])

            if shift not in fieldnames:
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

            for row in reader:
                metric = str(row.get(metric_col, "") or "").strip()
                value = str(row.get(shift, "") or "").strip()
                if metric:
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

    settings_path = data_app_path("settings", filename)
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

    settings_path = data_app_path("settings", filename)
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned = [str(x).strip() for x in (options or []) if str(x).strip()]
        with settings_path.open("w", encoding="utf-8") as f:
            for item in cleaned:
                f.write(f"{item}\n")
        return settings_path, True, None
    except Exception as ex:
        return settings_path, False, str(ex)
