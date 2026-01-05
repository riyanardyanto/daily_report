from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.utils.ui_helpers import is_file_locked_windows

HISTORY_FIELDNAMES: list[str] = [
    "save_id",
    "saved_at",
    "link_up",
    "func_location",
    "date_field",
    "shift",
    "user",
    "card_index",
    "issue",
    "detail_index",
    "detail",
    "action_index",
    "action",
]


def _build_history_rows(
    *,
    cards: list[Any],
    extract_issue: Callable[[Any], str],
    extract_details: Callable[[Any], list[dict]],
    save_id: str,
    saved_at: str,
    link_up: str,
    func_location: str,
    date_field: str,
    shift: str,
    user: str,
) -> list[dict[str, str]]:
    new_rows: list[dict[str, str]] = []

    for card_index, card in enumerate(cards, start=1):
        try:
            issue = str(extract_issue(card) or "")
        except Exception:
            issue = ""

        try:
            details = extract_details(card) or []
        except Exception:
            details = []

        base = {
            "save_id": save_id,
            "saved_at": saved_at,
            "link_up": link_up,
            "func_location": func_location,
            "date_field": date_field,
            "shift": shift,
            "user": user,
            "card_index": str(card_index),
            "issue": issue,
        }

        if not details:
            new_rows.append(
                {
                    **base,
                    "detail_index": "",
                    "detail": "",
                    "action_index": "",
                    "action": "",
                }
            )
            continue

        for detail_index, detail_obj in enumerate(details, start=1):
            detail_text = str((detail_obj or {}).get("text", "") or "")
            actions = list((detail_obj or {}).get("actions", []) or [])

            if not actions:
                new_rows.append(
                    {
                        **base,
                        "detail_index": str(detail_index),
                        "detail": detail_text,
                        "action_index": "",
                        "action": "",
                    }
                )
                continue

            for action_index, action_text in enumerate(actions, start=1):
                new_rows.append(
                    {
                        **base,
                        "detail_index": str(detail_index),
                        "detail": detail_text,
                        "action_index": str(action_index),
                        "action": str(action_text or ""),
                    }
                )

    return new_rows


def _upgrade_header_if_needed(
    csv_path: Path, fieldnames: list[str]
) -> tuple[bool, str | None]:
    if not csv_path.exists():
        return True, None

    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as src:
            reader = csv.DictReader(src)
            existing_fields = list(reader.fieldnames or [])

        missing_cols = [c for c in fieldnames if c not in existing_fields]
        if existing_fields and missing_cols:
            tmp_path = csv_path.with_suffix(".csv.tmp")
            with csv_path.open("r", newline="", encoding="utf-8-sig") as src:
                src_reader = csv.DictReader(src)
                with tmp_path.open("w", newline="", encoding="utf-8-sig") as dst:
                    dst_writer = csv.DictWriter(dst, fieldnames=fieldnames)
                    dst_writer.writeheader()
                    for row in src_reader:
                        out = {k: (row.get(k, "") if row else "") for k in fieldnames}
                        dst_writer.writerow(out)
            tmp_path.replace(csv_path)

        return True, None

    except PermissionError as ex:
        msg = (
            "Gagal upgrade format history.csv. Kemungkinan file sedang terbuka (mis. Excel).\n"
            f"Tutup file ini dulu: {csv_path} ({type(ex).__name__})"
        )
        return False, msg

    except OSError as ex:
        if getattr(ex, "winerror", None) in (32, 33):
            msg = (
                "Gagal upgrade format history.csv karena file sedang dipakai aplikasi lain (mis. Excel).\n"
                f"Tutup file ini dulu: {csv_path} ({type(ex).__name__})"
            )
            return False, msg
        raise


def save_report_history_csv(
    *,
    csv_path: Path,
    cards: list[Any],
    extract_issue: Callable[[Any], str],
    extract_details: Callable[[Any], list[dict]],
    shift: str = "Shift 1",
    link_up: str = "LU22",
    func_location: str = "Packer",
    date_field: str = "",
    user: str = "",
) -> tuple[bool, str]:
    """Append report snapshot rows to history.csv.

    Returns:
        (ok, message)
    """

    if not cards:
        return False, "Tidak ada card untuk disimpan"

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Proactively detect Excel lock (so we can warn even if Windows sharing might allow writes).
    if csv_path.exists() and is_file_locked_windows(csv_path):
        msg = (
            "Tidak bisa simpan karena history.csv sedang terbuka/terkunci (mis. di Excel).\n"
            f"Tutup file ini dulu: {csv_path}"
        )
        return False, msg

    save_id = str(uuid.uuid4())
    saved_at = datetime.now().isoformat(timespec="seconds")

    new_rows = _build_history_rows(
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

    ok, err = _upgrade_header_if_needed(csv_path, HISTORY_FIELDNAMES)
    if not ok:
        return False, str(err or "Gagal upgrade format history.csv")

    try:
        write_header = not csv_path.exists()
        with csv_path.open("a", newline="", encoding="utf-8-sig") as dst:
            writer = csv.DictWriter(dst, fieldnames=HISTORY_FIELDNAMES)
            if write_header:
                writer.writeheader()
            for row in new_rows:
                out = {k: (row.get(k, "") if row else "") for k in HISTORY_FIELDNAMES}
                writer.writerow(out)

    except PermissionError as ex:
        msg = (
            "Gagal simpan report: history.csv tidak bisa ditulis.\n"
            "Kemungkinan file sedang terbuka (mis. di Excel).\n"
            f"Tutup file ini dulu: {csv_path} ({type(ex).__name__})"
        )
        return False, msg

    except OSError as ex:
        if getattr(ex, "winerror", None) in (32, 33):
            msg = (
                "Gagal simpan report: history.csv sedang dipakai aplikasi lain (mis. Excel).\n"
                f"Tutup file ini dulu: {csv_path} ({type(ex).__name__})"
            )
            return False, msg
        raise

    return True, f"Report tersimpan: {csv_path}"
