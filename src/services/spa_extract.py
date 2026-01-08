import pandas as pd


def process_data(df: pd.DataFrame) -> pd.DataFrame:
    # remove rows with value in column 1 == value in column 1 previous row and column 2 == nan
    df = df.drop(
        df[(df.iloc[:, 1].shift() == df.iloc[:, 1]) & (df.iloc[:, 2].isna())].index
    )
    return df


def get_line_performance_details(df: pd.DataFrame):
    """Split DataFrame into "Line performance Details" segments (best-effort)."""
    if df.empty:
        return []

    col_idx = 14
    if df.shape[1] <= col_idx:
        raise IndexError(
            f"DataFrame has only {df.shape[1]} columns; cannot access column index {col_idx}"
        )

    required_cols = [1, 9, 2, 4]
    if df.shape[1] <= max(required_cols):
        raise IndexError(
            f"DataFrame has only {df.shape[1]} columns; requires column indexes {required_cols}"
        )

    mask = df.iloc[:, col_idx].astype(str).str.contains("i", na=False, case=False)
    positions = [i for i, v in enumerate(mask) if v]

    if not positions:
        return [df.copy()]

    segments = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(df)
        seg = df.iloc[start:end].copy()

        col1 = seg.iloc[:, 1].fillna("").astype(str)
        col1 = (
            col1.str.replace("&nbsp;", " ", regex=False)
            .str.replace("&nbsp", " ", regex=False)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )
        col1 = col1.replace("", None)

        def _take_left(v):
            if pd.isna(v) or v is None:
                return None
            s = str(v).strip()
            if not s:
                return None
            return s.split(" - ", 1)[0].split("-")[-1].strip()

        col1 = col1.apply(_take_left)
        col1 = col1.ffill()
        seg.iloc[:, 1] = col1

        seg = seg.dropna(how="all")
        if not seg.empty:
            segments.append(seg)

    filtered: list[pd.DataFrame] = []
    for seg in segments:
        try:
            val = seg.iat[0, 1]
            if pd.isna(val) or val is None:
                first_col1 = ""
            else:
                first_col1 = str(val).strip().lower()
        except Exception:
            first_col1 = ""
        if "line performance details" in first_col1:
            filtered.append(seg)

    final_segments = []
    for seg in filtered:
        sel: pd.DataFrame = seg.iloc[:, required_cols].copy()
        sel = sel.dropna(subset=[1, 2, 4], how="all")
        if not sel.empty:
            sel = sel.reset_index(drop=True)
            if len(sel) > 0:
                sel = sel.iloc[1:].reset_index(drop=True)
            sel.columns = ["Line", "Issue", "Stops", "Downtime"]
            sel = sel.dropna(subset=["Issue", "Stops", "Downtime"], how="all")
            if not sel.empty:
                final_segments.append(sel)

    return final_segments


def _split_segments_by_marker(
    df: pd.DataFrame, *, marker_col_idx: int = 14
) -> list[pd.DataFrame]:
    if df is None or df.empty:
        return []
    if df.shape[1] <= marker_col_idx:
        return []

    try:
        mask = (
            df.iloc[:, marker_col_idx]
            .astype(str)
            .str.contains("i", na=False, case=False)
        )
        positions = [i for i, v in enumerate(mask) if v]
    except Exception:
        return []

    if not positions:
        return []

    segments: list[pd.DataFrame] = []
    try:
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(df)
            seg = df.iloc[start:end].copy().reset_index(drop=True)
            segments.append(seg)
    except Exception:
        return []

    return segments


def _get_cell(segments: list[pd.DataFrame], seg_index: int, col: int, row_index: int):
    """Best-effort cell getter (tries label-based then position-based)."""
    try:
        if seg_index < 0 or seg_index >= len(segments):
            return None
        seg = segments[seg_index]
        if seg is None or getattr(seg, "empty", False):
            return None

        series = None
        try:
            if col in list(getattr(seg, "columns", [])):
                series = seg[col]
        except Exception:
            series = None

        if series is None:
            if not isinstance(col, int) or seg.shape[1] <= col:
                return None
            series = seg.iloc[:, col]

        if series is None:
            return None
        if row_index < 0 or len(series) <= row_index:
            return None
        value = series.iloc[row_index]
        if pd.isna(value):
            return None
        return value
    except Exception:
        return None


def get_data_actual(df: pd.DataFrame) -> pd.DataFrame:
    def _empty() -> pd.DataFrame:
        return pd.DataFrame(columns=["Metric", "Value"])

    if df is None or df.empty:
        return _empty()

    segments = _split_segments_by_marker(df)
    if not segments:
        return _empty()

    extraction = {
        "STOP": (7, 2, 1),
        "L STOP": (2, 2, 1),
        "PR": (0, 5, 5),
        "UPTIME": (0, 5, 6),
        "MTBF": (0, 7, 5),
        "L MTBF": (2, 7, 1),
        "UPDT": (7, 5, 1),
        "PDT": (6, 5, 1),
        "TRL": (4, 5, 2),
    }

    rows: list[dict[str, object]] = []
    for metric, (seg_i, col_i, row_i) in extraction.items():
        v = _get_cell(segments, seg_i, col_i, row_i)
        # Always include the metric so downstream UI/templates have a stable set.
        rows.append({"Metric": metric, "Value": "" if v is None else v})

    return pd.DataFrame(rows, columns=["Metric", "Value"])


def get_data_range(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""

    segments = _split_segments_by_marker(df)
    if not segments:
        return ""

    try:
        value = _get_cell(segments, 0, 9, 1)
        return "" if value is None else str(value).strip()
    except Exception:
        return ""
