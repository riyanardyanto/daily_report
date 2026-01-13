from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.services.history_db_service import (
        count_history_rows,
        migrate_history_csv_to_sqlite,
    )

    parser = argparse.ArgumentParser(
        description="Import history.csv rows into history.db (SQLite). Duplicates are ignored."
    )
    parser.add_argument(
        "csv_path",
        help="Path to the source CSV (history.csv)",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=str(project_root / "data_app" / "history" / "history.db"),
        help="Path to the destination SQLite DB (default: data_app/history/history.db)",
    )

    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    db_path = Path(args.db_path)

    before = count_history_rows(db_path)
    ok, msg = migrate_history_csv_to_sqlite(csv_path=csv_path, db_path=db_path)
    after = count_history_rows(db_path)

    print(msg)
    print(f"DB rows: {before} -> {after} (+{after - before})")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
