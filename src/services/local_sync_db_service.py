"""
Local SQLite with Sync - Solusi untuk shared folder multi-computer.

Strategi:
1. Setiap komputer menggunakan SQLite lokal (AppData/temp folder)
2. Data disync ke shared folder sebagai JSON/CSV files
3. Komputer lain bisa import dari shared folder
4. Menghindari corruption karena concurrent access
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.services.history_schema import HISTORY_FIELDNAMES


class LocalSyncDbService:
    """Service untuk manage local DB + sync ke shared folder."""

    def __init__(self, local_db_path: Path, sync_folder: Path):
        """
        Args:
            local_db_path: Path ke local SQLite (e.g., AppData/history.db)
            sync_folder: Shared folder untuk sync data antar komputer
        """
        self.local_db_path = Path(local_db_path)
        self.sync_folder = Path(sync_folder)
        self.sync_folder.mkdir(parents=True, exist_ok=True)
        self._ensure_local_db()

    def _ensure_local_db(self) -> None:
        """Initialize local database."""
        self.local_db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.local_db_path)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 3000")

            # Create schema
            cols = ",\n            ".join([f"{c} TEXT" for c in HISTORY_FIELDNAMES])
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS history_rows (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {cols},
                    synced_at TEXT,
                    sync_hash TEXT
                )
                """.strip()
            )

            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_history_row
                ON history_rows(save_id, card_index, detail_index, action_index)
                """.strip()
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_synced_at ON history_rows(synced_at)"
            )
            conn.commit()
        finally:
            conn.close()

    def append_rows(self, rows: Iterable[dict[str, Any]]) -> int:
        """Append rows ke local database."""
        rows_list = list(rows)
        if not rows_list:
            return 0

        conn = sqlite3.connect(self.local_db_path)
        try:
            cols = ",".join(HISTORY_FIELDNAMES)
            placeholders = ",".join(["?"] * len(HISTORY_FIELDNAMES))

            values = []
            for r in rows_list:
                values.append(
                    tuple(str(r.get(c, "") or "") for c in HISTORY_FIELDNAMES)
                )

            conn.executemany(
                f"INSERT OR IGNORE INTO history_rows ({cols}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return len(rows_list)
        finally:
            conn.close()

    def _import_index_path(self) -> Path:
        # Per-machine local marker file for which sync files have been imported.
        return self.local_db_path.parent / "sync_import_index.json"

    def _load_import_index(self) -> dict[str, dict[str, Any]]:
        p = self._import_index_path()
        try:
            if not p.exists():
                return {}
            obj = json.loads(p.read_text(encoding="utf-8") or "{}")
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _save_import_index(self, idx: dict[str, dict[str, Any]]) -> None:
        p = self._import_index_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            return

    def export_to_sync_folder(self) -> Path | None:
        """
        Export unsynced data ke shared folder sebagai JSON file.
        Return path ke exported file.
        """
        import hashlib
        import platform

        conn = sqlite3.connect(self.local_db_path)
        conn.row_factory = sqlite3.Row

        try:
            # Get rows yang belum di-sync atau baru
            cols = ",".join(HISTORY_FIELDNAMES)
            cursor = conn.execute(
                " ".join(
                    [
                        "SELECT row_id,",
                        cols,
                        "FROM history_rows",
                        "WHERE synced_at IS NULL OR synced_at = ''",
                        "ORDER BY row_id",
                    ]
                )
            )

            fetched = [dict(row) for row in cursor.fetchall()]
            unsynced_rows = [
                {k: r.get(k, "") for k in HISTORY_FIELDNAMES} for r in fetched
            ]
            row_ids = [r.get("row_id") for r in fetched if r.get("row_id") is not None]

            if not unsynced_rows:
                return None

            # Create unique filename dengan timestamp dan computer name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            computer_name = platform.node() or "unknown"
            filename = f"sync_{computer_name}_{timestamp}.json"

            sync_file = self.sync_folder / filename

            # Export ke JSON
            with open(sync_file, "w", encoding="utf-8") as f:
                # Compact JSON to keep files small and reduce network write time.
                json.dump(unsynced_rows, f, ensure_ascii=False, separators=(",", ":"))

            # Mark sebagai synced dengan hash
            file_hash = hashlib.md5(sync_file.read_bytes()).hexdigest()
            sync_timestamp = datetime.now().isoformat()

            if row_ids:
                placeholders = ",".join(["?"] * len(row_ids))
                conn.execute(
                    f"""
                    UPDATE history_rows 
                    SET synced_at = ?, sync_hash = ?
                    WHERE row_id IN ({placeholders})
                    """,
                    [sync_timestamp, file_hash] + row_ids,
                )
                conn.commit()

            return sync_file

        finally:
            conn.close()

    def export_full_snapshot_to_sync_folder(self) -> Path:
        """Export a full snapshot (all rows) to the shared sync folder.

        Intended for onboarding a new PC: one existing PC runs this once, then
        the new PC imports the produced file.
        """
        import platform

        conn = sqlite3.connect(self.local_db_path)
        conn.row_factory = sqlite3.Row
        try:
            cols = ",".join(HISTORY_FIELDNAMES)
            cursor = conn.execute(
                f"SELECT {cols} FROM history_rows ORDER BY row_id ASC"
            )
            all_rows = [
                {k: ("" if row[k] is None else str(row[k])) for k in HISTORY_FIELDNAMES}
                for row in cursor.fetchall()
            ]

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            computer_name = platform.node() or "unknown"
            filename = f"fullsync_{computer_name}_{timestamp}.json"
            sync_file = self.sync_folder / filename
            with open(sync_file, "w", encoding="utf-8") as f:
                json.dump(all_rows, f, ensure_ascii=False, separators=(",", ":"))
            return sync_file
        finally:
            conn.close()

    def import_from_sync_folder(self) -> int:
        """
        Import data dari sync files di shared folder.
        Return jumlah rows yang diimport.
        """
        if not self.sync_folder.exists():
            return 0

        imported_count = 0

        idx = self._load_import_index()

        # Process semua JSON files (including full snapshots)
        patterns = ("sync_*.json", "fullsync_*.json")
        files: list[Path] = []
        for pat in patterns:
            try:
                files.extend(list(self.sync_folder.glob(pat)))
            except Exception:
                pass
        files = sorted({p.resolve() for p in files}, key=lambda p: p.name)

        for sync_file in files:
            try:
                # Skip already-imported unchanged files (local-only marker).
                try:
                    st = sync_file.stat()
                    marker = idx.get(sync_file.name) if isinstance(idx, dict) else None
                    if isinstance(marker, dict):
                        if marker.get("size") == st.st_size and marker.get(
                            "mtime"
                        ) == int(st.st_mtime):
                            continue
                except Exception:
                    pass

                with open(sync_file, "r", encoding="utf-8") as f:
                    rows = json.load(f)

                # Import ke local DB
                if rows:
                    # Remove internal fields sebelum import
                    clean_rows = []
                    for r in rows:
                        clean = {k: v for k, v in r.items() if k in HISTORY_FIELDNAMES}
                        clean_rows.append(clean)

                    count = self.append_rows(clean_rows)
                    imported_count += count

                # Mark file as imported (regardless of whether it contained new rows).
                try:
                    st = sync_file.stat()
                    idx[sync_file.name] = {
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                    }
                except Exception:
                    idx[sync_file.name] = {"size": None, "mtime": None}

            except Exception as e:
                # Log error tapi continue
                print(f"Error importing {sync_file.name}: {e}")
                continue

        self._save_import_index(idx)

        return imported_count

    def get_all_rows(self) -> list[dict[str, Any]]:
        """Get all history rows dari local database."""
        conn = sqlite3.connect(self.local_db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.execute(
                f"""
                SELECT {",".join(HISTORY_FIELDNAMES)} 
                FROM history_rows 
                ORDER BY saved_at DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def count_rows(self) -> int:
        """Count total rows di local database."""
        conn = sqlite3.connect(self.local_db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM history_rows")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def sync_bidirectional(self) -> tuple[int, int]:
        """
        Lakukan sync 2-arah:
        1. Import dari shared folder
        2. Export ke shared folder

        Return: (imported_count, exported_count)
        """
        imported = self.import_from_sync_folder()

        exported_file = self.export_to_sync_folder()
        exported = 1 if exported_file else 0

        return (imported, exported)

    def cleanup_sync_folder(
        self,
        *,
        retention_days: int = 30,
        keep_latest_fullsync: int = 1,
        archive_dirname: str = "archive",
    ) -> dict[str, int]:
        """Archive old sync files to keep the shared folder tidy.

        This is intentionally conservative for multi-PC setups:
        - Never deletes files; only moves them into `<sync_folder>/archive/`.
        - Only archives files older than `retention_days`.
        - Keeps the newest `keep_latest_fullsync` full snapshots.

        Returns:
            dict with counts: {"scanned": n, "archived": n, "skipped": n, "errors": n}
        """

        scanned = 0
        archived = 0
        skipped = 0
        errors = 0

        try:
            retention_days_i = int(retention_days or 0)
        except Exception:
            retention_days_i = 30
        if retention_days_i <= 0:
            retention_days_i = 30

        try:
            keep_full = int(keep_latest_fullsync or 0)
        except Exception:
            keep_full = 1
        if keep_full < 0:
            keep_full = 0

        # Determine cutoff timestamp.
        now_ts = datetime.now().timestamp()
        cutoff_ts = now_ts - (retention_days_i * 24 * 60 * 60)

        archive_dir = self.sync_folder / str(archive_dirname or "archive")
        try:
            archive_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If we can't create archive dir, we can't safely clean up.
            return {"scanned": 0, "archived": 0, "skipped": 0, "errors": 1}

        # Collect candidate files.
        patterns = ("sync_*.json", "fullsync_*.json")
        files: list[Path] = []
        for pat in patterns:
            try:
                files.extend(list(self.sync_folder.glob(pat)))
            except Exception:
                pass

        # Keep newest fullsync files (by mtime) regardless of age.
        fullsync_files = [p for p in files if p.name.lower().startswith("fullsync_")]
        try:
            fullsync_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            pass
        keep_fullsync_names = {p.name for p in fullsync_files[:keep_full]}

        for p in files:
            if not p.is_file():
                continue
            scanned += 1

            # Never touch files already inside archive.
            try:
                if archive_dir in p.resolve().parents:
                    skipped += 1
                    continue
            except Exception:
                pass

            name = p.name
            if name in keep_fullsync_names:
                skipped += 1
                continue

            try:
                st = p.stat()
                # Only archive files older than retention window.
                if st.st_mtime > cutoff_ts:
                    skipped += 1
                    continue
            except Exception:
                errors += 1
                continue

            # Move to archive.
            dst = archive_dir / name
            try:
                if dst.exists():
                    # Avoid clobbering if another PC already archived it.
                    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dst = archive_dir / f"{p.stem}_{suffix}{p.suffix}"
                p.replace(dst)
                archived += 1
            except Exception:
                # File might be in use or no permissions; skip safely.
                errors += 1
                continue

        return {
            "scanned": scanned,
            "archived": archived,
            "skipped": skipped,
            "errors": errors,
        }
