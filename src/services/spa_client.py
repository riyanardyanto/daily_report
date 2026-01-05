
from io import StringIO

import httpx
import pandas as pd
from httpx_ntlm import HttpNtlmAuth


def get_url_spa(
    link_up: str,
    date: str,
    shift: str = "",
    functional_location: str = "PACK",
    base_url: str | None = None,
) -> str:
    from urllib.parse import urlencode

    if base_url is None:
        base_url = "https://ots.spappa.aws.private-pmideep.biz/db.aspx?"

    base_url = (
        str(base_url or "").strip()
        or "https://ots.spappa.aws.private-pmideep.biz/db.aspx?"
    )
    if "?" not in base_url:
        base_url = base_url + "?"
    elif not base_url.endswith("?") and not base_url.endswith("&"):
        base_url = base_url + "&"

    line_prefix = "PMID-SE-CP-L0" if link_up == "17" else "ID01-SE-CP-L0"
    params = {
        "table": "SPA_NormPeriodLossTree",
        "act": "query",
        "submit1": "Search",
        "db_Line": f"{line_prefix}{link_up}",
        "db_FunctionalLocation": f"{line_prefix}{link_up}-{functional_location}",
        "db_SegmentDateMin": date,
        "db_ShiftStart": shift,
        "db_SegmentDateMax": date,
        "db_ShiftEnd": shift,
        "db_Normalize": 0,
        "db_PeriodTime": 10080,
        "s_PeriodTime": "",
        "db_LongStopDetails": 3,
        "db_ReasonCNT": 30,
        "db_ReasonSort": "stop count",
        "db_Language": "OEM",
        "db_LineFailureAnalysis": "x",
    }

    return base_url + urlencode(params, doseq=True)


def fetch_data_from_api(
    url: str,
    username: str,
    password: str,
    *,
    verify_ssl: bool | None = None,
    timeout: int | float | None = None,
) -> pd.DataFrame:
    """Fetch SPA HTML table via NTLM auth and return as DataFrame."""

    auth = HttpNtlmAuth(username, password)

    client_kwargs: dict[str, object] = {"auth": auth}
    if verify_ssl is not None:
        client_kwargs["verify"] = bool(verify_ssl)
    if timeout is not None:
        try:
            client_kwargs["timeout"] = httpx.Timeout(float(timeout))
        except Exception:
            pass

    with httpx.Client(**client_kwargs) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.text

    dfs = pd.read_html(StringIO(data))
    for df in dfs:
        if len(df) > 20:
            return df
    return pd.DataFrame()
