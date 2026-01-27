"""
Adapter untuk migrasi dari shared SQLite ke Local+Sync SQLite.

Wrapper yang kompatibel dengan API existing history_db_service
tapi menggunakan LocalSyncDbService di belakang layar.

CARA PAKAI:
1. Ganti import di file yang pakai history DB
2. Tidak perlu ubah code calling

SEBELUM:
    from src.services.history_db_service import (
        append_history_rows,
        read_history_tail,
        ...
    )

SESUDAH:
    from src.services.history_db_adapter import (
        append_history_rows,
        read_history_tail,
        ...
    )
"""

from __future__ import annotations

import csv
import os
import uuid
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from src.services.history_schema import HISTORY_FIELDNAMES, build_history_rows
from src.services.local_sync_db_service import LocalSyncDbService

# Global instance - initialized on first use
_sync_service: LocalSyncDbService | None = None
_auto_sync_enabled = True  # Auto sync setelah write


def _history_storage_mode() -> str:
    """Return active history storage mode.

    Values:
      - "local_sync" (default)
      - "shared_sqlite"
    """

    # Fast path env var (useful for deployments)
    env_mode = str(os.environ.get("DAILY_REPORT_HISTORY_MODE", "") or "").strip()
    if env_mode:
        m = env_mode.strip().lower()
        return m if m in ("local_sync", "shared_sqlite") else "local_sync"

    try:
        from src.services.config_service import get_history_storage_config

        cfg, _err = get_history_storage_config()
        m = str(getattr(cfg, "mode", "local_sync") or "local_sync").strip().lower()
        return m if m in ("local_sync", "shared_sqlite") else "local_sync"
    except Exception:
        return "local_sync"


def _shared_db_path_from_config_or_env() -> str:
    env_path = str(os.environ.get("DAILY_REPORT_SHARED_DB_PATH", "") or "").strip()
    if env_path:
        return env_path
    try:
        from src.services.config_service import get_history_storage_config

        cfg, _err = get_history_storage_config()
        return str(getattr(cfg, "shared_db_path", "") or "").strip()
    except Exception:
        return ""


def _resolve_db_path(db_path: Path) -> Path:
    """Resolve effective db_path based on active mode.

    - local_sync: db_path argument is ignored (kept for compatibility)
    - shared_sqlite: uses env/config shared_db_path if set; otherwise uses passed db_path
    """

    if _history_storage_mode() != "shared_sqlite":
        return Path(db_path)

    raw = _shared_db_path_from_config_or_env()
    if raw:
        try:
            p = Path(raw)
            if not p.is_absolute():
                p = Path.cwd() / p
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    # Fallback to caller-provided db_path for backward compatibility.
    try:
        p = Path(db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        return Path(db_path)


def _user_local_root_dir() -> Path:
    """Per-user local root directory (independent of portable/shared data_app).

    We intentionally mirror src.utils.helpers.get_data_app_dir()'s per-user root
    naming to avoid creating multiple top-level folders under AppData.
    """

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "Daily Report"
    return Path.home() / ".daily_report"


def _migrate_legacy_local_db_if_needed(*, new_db_path: Path) -> None:
    """Best-effort migrate from the legacy 'DailyReport' folder to new location."""

    try:
        if new_db_path.exists():
            return

        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not base:
            return

        legacy_db_path = Path(base) / "DailyReport" / "history.db"
        if not legacy_db_path.exists():
            return

        new_db_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy the main DB.
        try:
            import shutil

            shutil.copy2(legacy_db_path, new_db_path)
        except Exception:
            return

        # Copy WAL sidecars if present (safe to ignore failures).
        for suffix in ("-wal", "-shm"):
            try:
                src = Path(str(legacy_db_path) + suffix)
                dst = Path(str(new_db_path) + suffix)
                if src.exists() and not dst.exists():
                    shutil.copy2(src, dst)
            except Exception:
                pass
    except Exception:
        return


def _resolve_sync_folder() -> Path:
    """Resolve shared sync folder.

    Priority:
      1) Env var DAILY_REPORT_SYNC_DIR
      2) data_app/settings/config.toml: [HISTORY_SYNC].sync_dir or [HISTORY].sync_dir
      3) Fallback: data_app/history/sync (portable/per-user depending on helpers)
    """

    # 1) Env override (recommended for shared deployments)
    env_dir = str(os.environ.get("DAILY_REPORT_SYNC_DIR", "") or "").strip()
    if env_dir:
        try:
            p = Path(env_dir)
            if not p.is_absolute():
                p = Path.cwd() / p
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            # Fall back to config/default
            pass

    # 2) Config setting
    try:
        from src.services.config_service import load_config_toml

        cfg, _cfg_path, err = load_config_toml()
        if not err and isinstance(cfg, dict):
            section = None
            for sect_name in ("HISTORY_SYNC", "HISTORY"):
                v = cfg.get(sect_name)
                if isinstance(v, dict):
                    section = v
                    break
            if isinstance(section, dict):
                raw = section.get("sync_dir")
                sync_dir = str(raw or "").strip()
                if sync_dir:
                    p = Path(sync_dir)
                    if not p.is_absolute():
                        # Relative paths are treated as relative to the data_app dir.
                        from src.utils.helpers import get_data_app_dir

                        p = get_data_app_dir(folder_name="data_app", create=True) / p
                    p.mkdir(parents=True, exist_ok=True)
                    return p
    except Exception:
        pass

    # 3) Default:
    # - When packaged as an .exe and placed in a shared folder, default to a
    #   `sync/` subfolder next to the executable so all PCs share the same
    #   sync location without cluttering the exe directory.
    # - Otherwise (dev runs), fall back to data_app/history/sync.
    try:
        import sys

        if bool(getattr(sys, "frozen", False)):
            exe_dir = Path(str(getattr(sys, "executable", "") or "")).resolve().parent
            p = exe_dir / "sync"
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass

    from src.utils.helpers import data_app_path

    return data_app_path("sync", folder_name="data_app/history")


def _get_sync_service() -> LocalSyncDbService:
    """Get atau initialize global sync service."""
    global _sync_service

    if _sync_service is None:
        # Local SQLite MUST be per-user (never on shared/portable folder).
        # Keep everything under the same AppData root: "Daily Report".
        local_db_dir = _user_local_root_dir() / "local_cache"
        local_db_path = local_db_dir / "history.db"

        # Migrate legacy location if it exists.
        _migrate_legacy_local_db_if_needed(new_db_path=local_db_path)

        # Shared sync folder (env var / config / default)
        sync_folder = _resolve_sync_folder()

        _sync_service = LocalSyncDbService(local_db_path, sync_folder)

        # Auto import saat init (import data dari komputer lain)
        try:
            imported = _sync_service.import_from_sync_folder()
            if imported > 0:
                print(f"[LocalSync] Imported {imported} rows from sync folder")
        except Exception as e:
            print(f"[LocalSync] Import error (ignored): {e}")

    return _sync_service


def manual_sync() -> tuple[int, int]:
    """
    Trigger manual sync (import + export).

    Returns:
        (imported_count, exported_count)
    """
    if _history_storage_mode() == "shared_sqlite":
        return 0, 0

    service = _get_sync_service()
    return service.sync_bidirectional()


def publish_all_history_to_sync() -> tuple[bool, str]:
    """Export a full history snapshot to the shared sync folder.

    Use this when onboarding a new PC that has an empty local DB.
    The new PC will import the produced `fullsync_*.json` on next sync.
    """

    if _history_storage_mode() == "shared_sqlite":
        return False, "Shared SQLite mode: JSON sync is disabled"

    try:
        service = _get_sync_service()
        out = service.export_full_snapshot_to_sync_folder()
        return True, f"Full history exported: {out}"
    except Exception as ex:
        return False, f"Full history export failed: {ex}"


def cleanup_sync_files(
    *,
    retention_days: int = 30,
    keep_latest_fullsync: int = 1,
) -> tuple[bool, str]:
    """Archive old sync JSON files in the shared sync folder.

    Conservative behavior: never deletes; moves old files to `archive/`.
    """

    if _history_storage_mode() == "shared_sqlite":
        return False, "Shared SQLite mode: JSON sync cleanup not applicable"

    try:
        service = _get_sync_service()
        res = service.cleanup_sync_folder(
            retention_days=retention_days,
            keep_latest_fullsync=keep_latest_fullsync,
        )
        return (
            True,
            "Cleanup done: "
            f"scanned {res.get('scanned', 0)}, "
            f"archived {res.get('archived', 0)}, "
            f"skipped {res.get('skipped', 0)}, "
            f"errors {res.get('errors', 0)}",
        )
    except Exception as ex:
        return False, f"Cleanup failed: {ex}"


def _normalize_history_row(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in HISTORY_FIELDNAMES:
        try:
            out[k] = str((row or {}).get(k, "") or "")
        except Exception:
            out[k] = ""
    return out


def _parse_int(v: Any) -> int:
    try:
        return int(str(v or "").strip() or 0)
    except Exception:
        return 0


def _shift_key(shift_value: Any) -> int:
    s = str(shift_value or "").strip().lower()
    if not s:
        return 10000
    if "all" in s and "shift" in s:
        return 9999
    if s.startswith("shift "):
        try:
            return -int(s[6:].strip() or 0)
        except Exception:
            return 0
    return 0


def _date_key(date_field: Any) -> int:
    s = str(date_field or "").strip()
    if not s:
        return 0
    try:
        d = _date.fromisoformat(s)
        return -int(d.toordinal() or 0)
    except Exception:
        return 0


def _sort_rows_for_view(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    normalized = [_normalize_history_row(r) for r in (rows or [])]
    if not normalized:
        return []

    def _key(r: dict[str, str]):
        return (
            _date_key(r.get("date_field", "")),
            _shift_key(r.get("shift", "")),
            str(r.get("shift", "") or "").strip().lower(),
            str(r.get("saved_at", "") or ""),
            str(r.get("save_id", "") or ""),
            _parse_int(r.get("card_index", "")),
            _parse_int(r.get("detail_index", "")),
            _parse_int(r.get("action_index", "")),
        )

    try:
        return sorted(normalized, key=_key)
    except Exception:
        return normalized


# ==================== ADAPTER FUNCTIONS ====================
# Drop-in replacement untuk functions dari history_db_service


def count_history_rows(db_path: Path) -> int:
    """
    Count total rows di history database.

    NOTE: db_path parameter diabaikan (compatibility).
    Sekarang menggunakan local database.
    """
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import count_history_rows as _count

        return _count(_resolve_db_path(db_path))

    service = _get_sync_service()
    return service.count_rows()


def append_history_rows(db_path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """
    Append rows ke history database.

    NOTE: db_path parameter diabaikan (compatibility).
    Sekarang menggunakan local database + auto sync.

    Returns:
        Jumlah rows yang di-insert
    """
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import append_history_rows as _append

        return _append(_resolve_db_path(db_path), rows)

    service = _get_sync_service()
    count = service.append_rows(rows)

    # Auto sync ke shared folder jika enabled
    if _auto_sync_enabled and count > 0:
        try:
            sync_file = service.export_to_sync_folder()
            if sync_file:
                print(f"[LocalSync] Exported to {sync_file.name}")
        except Exception as e:
            print(f"[LocalSync] Export error (ignored): {e}")

    return count


def read_history_tail(
    *,
    db_path: Path,
    limit: int,
) -> tuple[list[str], int, list[dict[str, str]]]:
    """Return (fieldnames, total_rows, tail_rows) like history_db_service."""
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import read_history_tail as _read

        return _read(db_path=_resolve_db_path(db_path), limit=limit)

    service = _get_sync_service()
    total = int(service.count_rows() or 0)
    lim = int(limit or 0) or 500
    if lim <= 0:
        lim = 500

    rows = _sort_rows_for_view(service.get_all_rows())
    return list(HISTORY_FIELDNAMES), total, rows[:lim]


def read_history_filtered_tail(
    *,
    db_path: Path,
    q: str,
    fieldnames: list[str],
    limit: int,
) -> tuple[int, list[dict[str, str]]]:
    """Return (matches_total, last_matches) like history_db_service."""
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import read_history_filtered_tail as _read

        return _read(
            db_path=_resolve_db_path(db_path),
            q=q,
            fieldnames=fieldnames,
            limit=limit,
        )

    q_s = str(q or "").strip().lower()
    if not q_s:
        return 0, []

    fields = [c for c in (fieldnames or []) if c in set(HISTORY_FIELDNAMES)]
    if not fields:
        return 0, []

    service = _get_sync_service()
    lim = int(limit or 0) or 500
    if lim <= 0:
        lim = 500

    all_rows = _sort_rows_for_view(service.get_all_rows())
    matches = [
        r
        for r in all_rows
        if any(q_s in str(r.get(c, "") or "").lower() for c in fields)
    ]
    return len(matches), matches[:lim]


def read_history_filtered_tail_no_count(
    *,
    db_path: Path,
    q: str,
    fieldnames: list[str],
    limit: int,
) -> list[dict[str, str]]:
    """Return last_matches without computing total matches."""
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import (
            read_history_filtered_tail_no_count as _read,
        )

        return _read(
            db_path=_resolve_db_path(db_path),
            q=q,
            fieldnames=fieldnames,
            limit=limit,
        )

    q_s = str(q or "").strip().lower()
    if not q_s:
        return []

    fields = [c for c in (fieldnames or []) if c in set(HISTORY_FIELDNAMES)]
    if not fields:
        return []

    service = _get_sync_service()
    lim = int(limit or 0) or 500
    if lim <= 0:
        lim = 500

    all_rows = _sort_rows_for_view(service.get_all_rows())
    matches = [
        r
        for r in all_rows
        if any(q_s in str(r.get(c, "") or "").lower() for c in fields)
    ]
    return matches[:lim]


def read_last_saved_user_date_shift(
    db_path: Path,
) -> tuple[str, str, str] | None:
    """
    Read last saved user/date/shift.

    NOTE: db_path parameter diabaikan (compatibility).
    """
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import (
            read_last_saved_user_date_shift as _read,
        )

        return _read(_resolve_db_path(db_path))

    service = _get_sync_service()
    rows = service.get_all_rows()
    if not rows:
        return None

    def _meta_key(r: dict[str, Any]):
        saved_at = str((r or {}).get("saved_at", "") or "")
        save_id = str((r or {}).get("save_id", "") or "")
        return (saved_at, save_id)

    try:
        last = max(rows, key=_meta_key)
    except Exception:
        last = rows[-1]

    user = str((last or {}).get("user", "") or "")
    date_field = str((last or {}).get("date_field", "") or "")
    shift = str((last or {}).get("shift", "") or "")
    return user, date_field, shift


def export_history_db_to_csv(
    *,
    db_path: Path,
    export_path: Path,
    visible_fieldnames: list[str],
    q: str | None = None,
) -> tuple[int, int]:
    """Export history to CSV like history_db_service.

    Returns:
        (total_exported, matches_total)
    """
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import export_history_db_to_csv as _export

        return _export(
            db_path=_resolve_db_path(db_path),
            export_path=export_path,
            visible_fieldnames=visible_fieldnames,
            q=q,
        )

    export_path = Path(export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [c for c in (visible_fieldnames or []) if c in set(HISTORY_FIELDNAMES)]
    if not fields:
        fields = list(HISTORY_FIELDNAMES)

    q_s = str(q or "").strip().lower()
    service = _get_sync_service()
    all_rows = _sort_rows_for_view(service.get_all_rows())

    if q_s:
        matches = [
            r
            for r in all_rows
            if any(q_s in str(r.get(c, "") or "").lower() for c in fields)
        ]
    else:
        matches = list(all_rows)

    matches_total = len(matches)
    exported = 0

    with export_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in matches:
            writer.writerow({k: str(r.get(k, "") or "") for k in fields})
            exported += 1

    return exported, matches_total


def save_report_history_sqlite(
    *,
    db_path: Path,
    cards: list[Any],
    extract_issue: Callable[[Any], str],
    extract_details: Callable[[Any], list[dict]],
    shift: str = "Shift 1",
    link_up: str = "LU22",
    func_location: str = "Packer",
    date_field: str = "",
    user: str = "",
) -> tuple[bool, str]:
    """Save report snapshot into the Local+Sync history store.

    Matches the behavior/signature of history_db_service.save_report_history_sqlite.
    """
    if _history_storage_mode() == "shared_sqlite":
        from src.services.history_db_service import save_report_history_sqlite as _save

        return _save(
            db_path=_resolve_db_path(db_path),
            cards=cards,
            extract_issue=extract_issue,
            extract_details=extract_details,
            shift=shift,
            link_up=link_up,
            func_location=func_location,
            date_field=date_field,
            user=user,
        )

    if not cards:
        return False, "No cards to save"

    save_id = str(uuid.uuid4())
    saved_at = datetime.now().isoformat(timespec="seconds")

    rows = build_history_rows(
        cards=cards,
        extract_issue=extract_issue,
        extract_details=extract_details,
        save_id=save_id,
        saved_at=saved_at,
        link_up=str(link_up or "").strip(),
        func_location=str(func_location or "").strip(),
        date_field=str(date_field or "").strip(),
        shift=str(shift or "").strip() or "Shift 1",
        user=str(user or "").strip(),
    )

    try:
        appended = append_history_rows(db_path, rows)
        return True, f"Report saved (local cache) (+{appended} rows)"
    except Exception as ex:
        return False, f"Failed to save report to local history: {ex}"
