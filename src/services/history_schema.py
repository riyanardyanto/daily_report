from __future__ import annotations

from typing import Any, Callable

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


def build_history_rows(
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
