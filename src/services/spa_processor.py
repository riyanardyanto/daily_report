from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup

from src.services.spa_client import fetch_data_from_api

SpaTable = list[list[str]]


def scrape_spa_response(html_response: str) -> List[SpaTable]:
    """
    Scrape semua <table> dari HTML string,
    lalu mengubahnya menjadi list of tables (list-of-rows)
    dengan index kolom = 0, 1, 2, 3 ...
    Contoh: kolom pertama → index 0, kolom kedua → index 1, dst.
    """
    # Ambil HTML
    html_content = html_response

    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        return []

    list_tables: list[SpaTable] = []

    for table in tables:
        # Extract data using list comprehension for efficiency
        data = [
            [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
            for row in table.find_all("tr")
        ]
        # Filter out empty rows
        data = [row for row in data if row and not all(c == "" for c in row)]

        if not data:
            continue

        # Determine max columns
        max_cols = max(len(row) for row in data)

        # Normalize rows to same length using list comprehension
        normalized_data = [
            (
                row + [""] * (max_cols - len(row))
                if len(row) < max_cols
                else row[:max_cols]
            )
            for row in data
        ]

        list_tables.append(normalized_data)

    return list_tables


def fetch_data_from_spa_with_retries(
    url: str,
    username: str,
    password: str,
    verify_ssl: bool | None = None,
    timeout: float | None = None,
    max_retries: int = 3,
) -> SpaTable:
    # fetch data dari spa
    response_text = fetch_data_from_api(
        url, username, password, verify_ssl=verify_ssl, timeout=timeout
    )
    # scarpe semua table dari response_text
    tables = scrape_spa_response(html_response=response_text)

    # ambil table yang memiliki jumlah baris > 20
    # jika tidak ada table yang sesuai, coba fetch data dari spa lagi sebanyak max_retries
    for _ in range(max_retries):
        for table in tables:
            if len(table) > 20:
                return table

        response_text = fetch_data_from_api(
            url, username, password, verify_ssl=verify_ssl, timeout=timeout
        )
        tables = scrape_spa_response(html_response=response_text)

    raise ValueError("No suitable table found after multiple attempts.")


def _cell(row: list[str] | None, idx: int) -> str:
    if row is None:
        return ""
    if idx < 0 or idx >= len(row):
        return ""
    try:
        return str(row[idx] or "")
    except Exception:
        return ""


def process_data_spa(spa_df: SpaTable) -> list[SpaTable]:
    def _is_marker(row: list[str]) -> bool:
        for col_i in (6, 7, 8, 9):
            v = _cell(row, col_i).strip()
            if v == "i":
                return True
        return False

    # Remove rows where both col 3 and col 13 are empty,
    # but keep marker rows so splitting still works.
    filtered: SpaTable = []
    for row in spa_df or []:
        c3 = _cell(row, 3).strip()
        c13 = _cell(row, 13).strip()
        if (c3 == "" and c13 == "") and not _is_marker(row):
            continue
        filtered.append(row)

    # Optional: blank out col 0 and col 2 (just index columns)
    for row in filtered:
        if len(row) > 0:
            row[0] = ""
        if len(row) > 2:
            row[2] = ""

    # split table menjadi beberapa table berdasarkan index baris yang memiliki nilai 'i'
    split_indices: list[int] = []
    for i, row in enumerate(filtered):
        if _is_marker(row):
            split_indices.append(i)

    split_tables: list[SpaTable] = []
    prev_index = 0
    for index in split_indices:
        if index == prev_index:
            continue
        split_tables.append(filtered[prev_index:index])
        prev_index = index
    split_tables.append(filtered[prev_index:])

    return split_tables


def get_line_performance_details(
    split_tables: list[SpaTable],
) -> list[tuple[str, str, str, str]]:
    # Find the segment containing the "line performance details" header
    seg: SpaTable | None = None
    for t in split_tables or []:
        if not t:
            continue
        header = _cell(t[0], 1).lower().strip()
        if "line performance details" in header:
            seg = t
            break

    if not seg:
        return []

    # Skip first row (header)
    rows = seg[1:]

    out: list[tuple[str, str, str, str]] = []
    last_line: str = ""
    for r in rows:
        line_raw = _cell(r, 1).strip()
        issue = _cell(r, 13).strip()
        stops = _cell(r, 6).strip()
        downtime = _cell(r, 8).strip()

        # forward fill line
        if line_raw == "":
            line_raw = last_line
        else:
            last_line = line_raw

        # split Line berdasarkan '-' dan ambil bagian index 4
        line_out = line_raw
        try:
            parts = str(line_raw).split("-")
            if len(parts) > 4 and str(parts[4]).strip():
                line_out = str(parts[4]).strip()
        except Exception:
            pass

        out.append((str(line_out), str(issue), str(stops), str(downtime)))

    return out


def _get_cell(split_tables: list[SpaTable], seg_index: int, col: int, row_index: int):
    """Get cell value from segments list (plain Python version)."""
    try:
        if seg_index < 0 or seg_index >= len(split_tables):
            return None
        seg = split_tables[seg_index]
        if not seg:
            return None
        if row_index < 0 or row_index >= len(seg):
            return None
        row = seg[row_index]
        v = _cell(row, int(col))
        return v
    except Exception:
        return None


def get_data_actual(
    split_tables: list[SpaTable],
) -> list[tuple[str, str]]:
    """
    Extract actual metrics data from SPA tables.

    Args:
        split_tables: List of segments (tables)

    Returns:
        List of (Metric, Value)
    """

    # Extraction mapping: metric -> (segment_index, column, row)
    extraction = {
        "STOP": (7, 4, 1),
        "L STOP": (2, 4, 1),
        "PR": (0, 7, 5),
        "UPTIME": (0, 7, 6),
        "MTBF": (0, 9, 5),
        "L MTBF": (2, 8, 1),
        "UPDT": (7, 7, 1),
        "PDT": (6, 7, 1),
        "TRL": (4, 6, 2),
    }

    rows: list[tuple[str, str]] = []
    for metric, (seg_i, col_i, row_i) in extraction.items():
        v = _get_cell(split_tables, seg_i, col_i, row_i)
        # Always include the metric so downstream UI/templates have a stable set.
        rows.append((metric, "" if v is None else str(v).strip()))

    return rows


def get_data_range(split_tables: list[SpaTable]) -> str:
    """
    Extract date range string from SPA tables.

    Args:
        split_tables: List of segments (tables)

    Returns:
        String representing the date range
    """

    try:
        value = _get_cell(split_tables, 0, 11, 1)
        return "" if value is None else str(value).strip()
    except Exception:
        return ""


def main() -> None:
    url = "http://127.0.0.1:5500/src/assets/response1.html"
    password = "password"
    username = "username"

    # fetch data dari spa
    spa_df = fetch_data_from_spa_with_retries(
        url=url,
        username=username,
        password=password,
        max_retries=3,
    )

    # process data spa
    split_tables = process_data_spa(spa_df=spa_df)

    # get line performance details
    stops_rows = get_line_performance_details(split_tables=split_tables)

    # get actual data
    actual_rows = get_data_actual(split_tables=split_tables)

    # get data range
    data_range = get_data_range(split_tables=split_tables)

    with open("x output_debug.txt", "w", encoding="utf-8") as f:
        f.write("=== Line Performance Details ===\n")
        for r in stops_rows:
            f.write("\t".join(map(str, r)) + "\n")
        f.write("\n\n")

        f.write("=== Actual Data ===\n")
        for metric, value in actual_rows:
            f.write(f"{metric}\t{value}\n")
        f.write("\n\n")

        f.write(f"=== Data Range ===\n{data_range}\n")


if __name__ == "__main__":
    main()
