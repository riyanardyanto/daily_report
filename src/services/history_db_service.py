from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable

from src.services.history_schema import HISTORY_FIELDNAMES, build_history_rows


def ensure_history_db(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA busy_timeout = 3000")

        cols = ",\n            ".join([f"{c} TEXT" for c in HISTORY_FIELDNAMES])
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS history_rows (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                {cols}
            )
            """.strip()
        )

        # Prevent duplicate inserts during migration.
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_history_row
            ON history_rows(save_id, card_index, detail_index, action_index)
            """.strip()
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_history_saved_at ON history_rows(saved_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_history_link_up ON history_rows(link_up)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_history_shift ON history_rows(shift)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_history_date_field ON history_rows(date_field)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_history_user ON history_rows(user)")


def count_history_rows(db_path: Path) -> int:
    ensure_history_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM history_rows")
        row = cur.fetchone()
        return int(row[0] if row and row[0] is not None else 0)


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in HISTORY_FIELDNAMES:
        try:
            out[k] = str((row or {}).get(k, "") or "")
        except Exception:
            out[k] = ""
    return out


def append_history_rows(db_path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_history_db(db_path)

    normalized = [_normalize_row(r) for r in rows]
    if not normalized:
        return 0

    cols = ",".join(HISTORY_FIELDNAMES)
    placeholders = ",".join(["?"] * len(HISTORY_FIELDNAMES))
    values = [tuple(r[c] for c in HISTORY_FIELDNAMES) for r in normalized]

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA busy_timeout = 3000")
        conn.execute("BEGIN")
        try:
            conn.executemany(
                f"INSERT OR IGNORE INTO history_rows ({cols}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return len(normalized)


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
    """Save report snapshot into SQLite.

    Returns:
        (ok, message)
    """

    # Reuse the existing CSV builder logic for consistent row shape.
    import uuid
    from datetime import datetime

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
        return True, f"Report saved: {db_path} (+{appended} rows)"
    except Exception as ex:
        return False, f"Failed to save report to SQLite: {ex}"


def migrate_history_csv_to_sqlite(
    *,
    csv_path: Path,
    db_path: Path,
) -> tuple[bool, str]:
    """One-time migration from history.csv to history.db.

    Idempotent: uses a UNIQUE index and INSERT OR IGNORE to avoid duplicates.
    """

    csv_path = Path(csv_path)
    db_path = Path(db_path)

    if not csv_path.exists():
        # Nothing to migrate.
        ensure_history_db(db_path)
        return True, "No CSV to migrate"

    ensure_history_db(db_path)

    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            if not fieldnames:
                return False, f"CSV has no header: {csv_path}"

            rows: list[dict[str, Any]] = []
            for row in reader:
                rows.append(row or {})

        inserted = append_history_rows(db_path, rows)
        return (
            True,
            f"Migrated CSV -> SQLite: {csv_path} -> {db_path} ({inserted} rows processed)",
        )
    except Exception as ex:
        return False, f"Migration failed: {ex}"


def read_history_tail(
    *,
    db_path: Path,
    limit: int,
) -> tuple[list[str], int, list[dict[str, str]]]:
    """Return (fieldnames, total_rows, tail_rows) in the same shape as CSV reader."""

    ensure_history_db(db_path)

    lim = int(limit or 0)
    if lim <= 0:
        lim = 500

    with sqlite3.connect(db_path) as conn:
        # COUNT(*) can be slow on large tables; MAX(row_id) is fast via the PK index.
        cur = conn.execute("SELECT COALESCE(MAX(row_id), 0) FROM history_rows")
        total = int((cur.fetchone() or [0])[0] or 0)

        # Sorting is pushed to SQLite to avoid Python sorting large row sets.
        date_expr = "COALESCE(date_field, '')"
        shift_expr = "LOWER(TRIM(COALESCE(shift, '')))"
        shift_sort_key = (
            "CASE "
            f"WHEN {shift_expr} = '' THEN 10000 "
            f"WHEN {shift_expr} LIKE '%all%shift%' THEN 9999 "
            f"WHEN {shift_expr} LIKE 'shift %' THEN -CAST(SUBSTR({shift_expr}, 7) AS INT) "
            "ELSE 0 END"
        )

        card_i = "CAST(COALESCE(card_index, '0') AS INT)"
        detail_i = "CAST(COALESCE(detail_index, '0') AS INT)"
        action_i = "CAST(COALESCE(action_index, '0') AS INT)"

        cols = ",".join(HISTORY_FIELDNAMES)
        cur = conn.execute(
            " ".join(
                [
                    f"SELECT {cols} FROM history_rows",
                    "ORDER BY",
                    f"{date_expr} DESC,",
                    f"{shift_sort_key} ASC,",
                    f"{shift_expr} ASC,",
                    "COALESCE(saved_at, '') ASC,",
                    "COALESCE(save_id, '') ASC,",
                    f"{card_i} ASC,",
                    f"{detail_i} ASC,",
                    f"{action_i} ASC",
                    "LIMIT ?",
                ]
            ),
            (lim,),
        )
        rows = [dict(zip(HISTORY_FIELDNAMES, r)) for r in cur.fetchall()]

    return list(HISTORY_FIELDNAMES), total, rows


def read_last_saved_user_date_shift(db_path: Path) -> tuple[str, str, str] | None:
    """Return the most recent saved (user, date_field, shift).

    Uses the latest `saved_at` value (descending). This is intended for quick UI
    status display and avoids any COUNT(*) or large scans.
    """

    db_path = Path(db_path)
    if not db_path.exists():
        return None

    ensure_history_db(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA busy_timeout = 1000")
        cur = conn.execute(
            " ".join(
                [
                    "SELECT",
                    "COALESCE(user, ''),",
                    "COALESCE(date_field, ''),",
                    "COALESCE(shift, '')",
                    "FROM history_rows",
                    "ORDER BY COALESCE(saved_at, '') DESC, COALESCE(save_id, '') DESC",
                    "LIMIT 1",
                ]
            )
        )
        row = cur.fetchone()
        if not row:
            return None

    try:
        user, date_field, shift = row
        return str(user or ""), str(date_field or ""), str(shift or "")
    except Exception:
        return None


def read_history_filtered_tail(
    *,
    db_path: Path,
    q: str,
    fieldnames: list[str],
    limit: int,
) -> tuple[int, list[dict[str, str]]]:
    """Return (matches_total, last_matches) similar to CSV streaming filter.

    Searches only within the provided fieldnames.
    """

    ensure_history_db(db_path)

    q = str(q or "").strip()
    if not q:
        return 0, []

    lim = int(limit or 0)
    if lim <= 0:
        lim = 500

    fields = [c for c in (fieldnames or []) if c in set(HISTORY_FIELDNAMES)]
    if not fields:
        return 0, []

    # Build a SQL WHERE clause: lower(col) LIKE ? OR ...
    q_l = q.lower()
    like = f"%{q_l}%"

    where = " OR ".join([f"LOWER(COALESCE({c}, '')) LIKE ?" for c in fields])
    params = [like] * len(fields)

    date_expr = "COALESCE(date_field, '')"
    shift_expr = "LOWER(TRIM(COALESCE(shift, '')))"
    shift_sort_key = (
        "CASE "
        f"WHEN {shift_expr} = '' THEN 10000 "
        f"WHEN {shift_expr} LIKE '%all%shift%' THEN 9999 "
        f"WHEN {shift_expr} LIKE 'shift %' THEN -CAST(SUBSTR({shift_expr}, 7) AS INT) "
        "ELSE 0 END"
    )
    card_i = "CAST(COALESCE(card_index, '0') AS INT)"
    detail_i = "CAST(COALESCE(detail_index, '0') AS INT)"
    action_i = "CAST(COALESCE(action_index, '0') AS INT)"

    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(f"SELECT COUNT(*) FROM history_rows WHERE {where}", params)
        matches_total = int((cur.fetchone() or [0])[0] or 0)

        cols = ",".join(HISTORY_FIELDNAMES)
        cur = conn.execute(
            " ".join(
                [
                    f"SELECT {cols} FROM history_rows WHERE {where}",
                    "ORDER BY",
                    f"{date_expr} DESC,",
                    f"{shift_sort_key} ASC,",
                    f"{shift_expr} ASC,",
                    "COALESCE(saved_at, '') ASC,",
                    "COALESCE(save_id, '') ASC,",
                    f"{card_i} ASC,",
                    f"{detail_i} ASC,",
                    f"{action_i} ASC",
                    "LIMIT ?",
                ]
            ),
            [*params, lim],
        )
        rows = [dict(zip(HISTORY_FIELDNAMES, r)) for r in cur.fetchall()]

    return matches_total, rows


def read_history_filtered_tail_no_count(
    *,
    db_path: Path,
    q: str,
    fieldnames: list[str],
    limit: int,
) -> list[dict[str, str]]:
    """Return last_matches without computing total matches.

    This avoids COUNT(*) which can be slow on large tables.
    Searches only within the provided fieldnames.
    """

    ensure_history_db(db_path)

    q = str(q or "").strip()
    if not q:
        return []

    lim = int(limit or 0)
    if lim <= 0:
        lim = 500

    fields = [c for c in (fieldnames or []) if c in set(HISTORY_FIELDNAMES)]
    if not fields:
        return []

    q_l = q.lower()
    like = f"%{q_l}%"

    where = " OR ".join([f"LOWER(COALESCE({c}, '')) LIKE ?" for c in fields])
    params = [like] * len(fields)

    date_expr = "COALESCE(date_field, '')"
    shift_expr = "LOWER(TRIM(COALESCE(shift, '')))"
    shift_sort_key = (
        "CASE "
        f"WHEN {shift_expr} = '' THEN 10000 "
        f"WHEN {shift_expr} LIKE '%all%shift%' THEN 9999 "
        f"WHEN {shift_expr} LIKE 'shift %' THEN -CAST(SUBSTR({shift_expr}, 7) AS INT) "
        "ELSE 0 END"
    )
    card_i = "CAST(COALESCE(card_index, '0') AS INT)"
    detail_i = "CAST(COALESCE(detail_index, '0') AS INT)"
    action_i = "CAST(COALESCE(action_index, '0') AS INT)"

    with sqlite3.connect(db_path) as conn:
        cols = ",".join(HISTORY_FIELDNAMES)
        cur = conn.execute(
            " ".join(
                [
                    f"SELECT {cols} FROM history_rows WHERE {where}",
                    "ORDER BY",
                    f"{date_expr} DESC,",
                    f"{shift_sort_key} ASC,",
                    f"{shift_expr} ASC,",
                    "COALESCE(saved_at, '') ASC,",
                    "COALESCE(save_id, '') ASC,",
                    f"{card_i} ASC,",
                    f"{detail_i} ASC,",
                    f"{action_i} ASC",
                    "LIMIT ?",
                ]
            ),
            [*params, lim],
        )
        return [dict(zip(HISTORY_FIELDNAMES, r)) for r in cur.fetchall()]


def export_history_db_to_csv(
    *,
    db_path: Path,
    export_path: Path,
    visible_fieldnames: list[str],
    q: str | None = None,
) -> tuple[int, int]:
    """Export history from SQLite to CSV.

    Args:
        db_path: history.db path
        export_path: destination csv path
        visible_fieldnames: columns to export (order preserved)
        q: optional search query; when provided, exports only matches

    Returns:
        (total_exported, matches_total)
        - matches_total equals total rows when q is empty
    """

    ensure_history_db(db_path)
    export_path = Path(export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [c for c in (visible_fieldnames or []) if c in set(HISTORY_FIELDNAMES)]
    if not fields:
        fields = list(HISTORY_FIELDNAMES)

    q = str(q or "").strip()

    where = ""
    params: list[str] = []
    if q:
        q_l = q.lower()
        like = f"%{q_l}%"
        where = " WHERE " + " OR ".join(
            [f"LOWER(COALESCE({c}, '')) LIKE ?" for c in fields]
        )
        params = [like] * len(fields)

    select_cols = ",".join(fields)

    with sqlite3.connect(db_path) as conn:
        if where:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM history_rows{where}",
                params,
            )
            matches_total = int((cur.fetchone() or [0])[0] or 0)
        else:
            cur = conn.execute("SELECT COUNT(*) FROM history_rows")
            matches_total = int((cur.fetchone() or [0])[0] or 0)

        cur = conn.execute(
            f"SELECT {select_cols} FROM history_rows{where} ORDER BY row_id ASC",
            params,
        )

        exported = 0
        with export_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            while True:
                batch = cur.fetchmany(2000)
                if not batch:
                    break
                for row in batch:
                    out = {
                        fields[i]: ("" if row[i] is None else str(row[i]))
                        for i in range(len(fields))
                    }
                    writer.writerow(out)
                    exported += 1

    return exported, matches_total
