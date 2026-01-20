from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pandas as pd

from src.core.context import AppContext
from src.core.logging import get_logger
from src.services.spa_service import (
    fetch_data_from_api,
    get_data_actual,
    get_data_range,
    get_line_performance_details,
    get_url_spa,
    process_data,
)
from src.utils.helpers import load_targets_csv


@dataclass(frozen=True, slots=True)
class SpaRequest:
    link_up: str
    date_value: str
    shift_value: str
    func_location: str
    existing_metrics: list[str]


@dataclass(frozen=True, slots=True)
class SpaResponse:
    df: pd.DataFrame | None
    rng_str: str
    metrics_rows: list[tuple[str, str, str]]
    stops_rows: list[list]
    from_cache: bool = False


class SpaFacade:
    """Facade for SPA data fetch + transformation.

    Keeps UI code (DashboardApp) thin by moving:
    - URL selection (dev vs prod)
    - fetch + processing
    - metrics/stops shaping
    - short-lived caching
    """

    def __init__(
        self,
        ctx: AppContext,
        *,
        cache_ttl_s: float = 15.0,
        cache: dict[
            tuple[str, str, str, str, str],
            tuple[float, pd.DataFrame, str, list[tuple[str, str, str]], list[list]],
        ]
        | None = None,
        max_cache_items: int = 12,
    ):
        self._ctx = ctx
        self._ttl = float(cache_ttl_s or 0.0)
        self._cache = cache if cache is not None else {}
        self._max_cache_items = int(max_cache_items or 0) if max_cache_items else 0
        self._logger = get_logger("spa")

    @property
    def env_lower(self) -> str:
        try:
            return str(self._ctx.app.environment or "production").strip().lower()
        except Exception:
            return "production"

    def _cache_key(self, req: SpaRequest) -> tuple[str, str, str, str, str]:
        return (
            self.env_lower,
            str(req.link_up or ""),
            str(req.date_value or ""),
            str(req.shift_value or ""),
            str(req.func_location or ""),
        )

    def _get_cached(self, key: tuple[str, str, str, str, str]) -> SpaResponse | None:
        if self._ttl <= 0:
            return None
        try:
            cached = self._cache.get(key)
        except Exception:
            return None
        if cached is None:
            return None

        ts, df, rng_str, metrics_rows, stops_rows = cached
        try:
            if (time.monotonic() - float(ts)) > self._ttl:
                return None
        except Exception:
            return None

        return SpaResponse(
            df=df,
            rng_str=str(rng_str or ""),
            metrics_rows=list(metrics_rows or []),
            stops_rows=list(stops_rows or []),
            from_cache=True,
        )

    def _put_cache(
        self, key: tuple[str, str, str, str, str], resp: SpaResponse
    ) -> None:
        if self._ttl <= 0 or resp.df is None:
            return
        try:
            self._cache[key] = (
                time.monotonic(),
                resp.df,
                str(resp.rng_str or ""),
                list(resp.metrics_rows or []),
                list(resp.stops_rows or []),
            )

            if self._max_cache_items > 0 and len(self._cache) > self._max_cache_items:
                items = sorted(self._cache.items(), key=lambda kv: kv[1][0])
                for k, _v in items[: max(0, len(items) - self._max_cache_items)]:
                    self._cache.pop(k, None)
        except Exception:
            pass

    def _resolve_credentials(self) -> tuple[str, str]:
        spa_cfg = self._ctx.spa
        username = str(getattr(spa_cfg, "username", "") or "").strip()
        password = str(getattr(spa_cfg, "password", "") or "").strip()

        # Backward compatible defaults (also used in old code).
        if not username:
            username = "DOMAIN\\username"
        if not password:
            password = "password"
        return username, password

    def _fetch_and_process(
        self, req: SpaRequest, *, username: str, password: str
    ) -> SpaResponse:
        """Run SPA fetch + transform synchronously.

        Intended to be executed in a worker thread (or in a blocking fallback).
        """

        env = self.env_lower
        spa_cfg = self._ctx.spa

        # Dev URL (local HTML) vs prod URL (real SPA).
        local_url = (
            "http://127.0.0.1:5500/src/assets/response2.html"
            if req.link_up == "LU21"
            else "http://127.0.0.1:5500/src/assets/response.html"
        )

        spa_url = get_url_spa(
            link_up=(req.link_up[-2:] if req.link_up else ""),
            date=req.date_value,
            shift=(
                req.shift_value[-1]
                if req.shift_value and req.shift_value[-1].isnumeric()
                else ""
            ),
            functional_location=req.func_location or "PACK",
            base_url=getattr(spa_cfg, "base_url", None) or None,
        )
        url = local_url if env == "development" else spa_url

        df = fetch_data_from_api(
            url,
            username,
            password,
            verify_ssl=getattr(spa_cfg, "verify_ssl", None),
            timeout=getattr(spa_cfg, "timeout", None),
        )

        if df is None or getattr(df, "empty", False):
            return SpaResponse(df=None, rng_str="", metrics_rows=[], stops_rows=[])

        df_processed = process_data(df)

        rng_str = ""
        try:
            rng = get_data_range(df_processed)
            rng_str = str(rng) if rng is not None else ""
        except Exception:
            rng_str = ""

        # Metrics rows (target + actual)
        metrics_rows: list[tuple[str, str, str]] = []
        try:
            actual_df = get_data_actual(df_processed)
            actuals: dict[str, str] = {}
            actual_metric_order: list[str] = []
            if hasattr(actual_df, "iterrows"):
                for _idx, row in actual_df.iterrows():
                    try:
                        metric = str(row.get("Metric", "") or "").strip()
                        value = row.get("Value", "")
                        if metric:
                            if metric not in actual_metric_order:
                                actual_metric_order.append(metric)
                            actuals[metric] = str(
                                value if value is not None else ""
                            ).strip()
                    except Exception:
                        pass

            lu = req.link_up[-2:].lower() if req.link_up else ""
            fl = req.func_location[:4].lower() if req.func_location else ""
            filename = f"target_{fl}_{lu}.csv"

            shift_for_targets = ""
            try:
                shift_for_targets = str(req.shift_value or "").strip()
                if "all" in shift_for_targets.lower():
                    shift_for_targets = ""
            except Exception:
                shift_for_targets = ""

            metrics_for_template: list[str] = []
            for m in list(actual_metric_order) + list(req.existing_metrics or []):
                m = str(m or "").strip()
                if m and m not in metrics_for_template:
                    metrics_for_template.append(m)

            _csv_path, targets, _created_template, _err = load_targets_csv(
                shift=shift_for_targets,
                filename=filename,
                folder_name="data_app/targets",
                metrics=metrics_for_template,
            )

            metrics_display: list[str] = []
            for m in list(actual_metric_order):
                m = str(m or "").strip()
                if m and m not in metrics_display:
                    metrics_display.append(m)
            if not metrics_display:
                for m in list(req.existing_metrics or []):
                    m = str(m or "").strip()
                    if m and m not in metrics_display:
                        metrics_display.append(m)

            for metric in metrics_display:
                target = str((targets or {}).get(metric, "") or "").strip()
                actual = str(actuals.get(metric, "") or "").strip()
                metrics_rows.append((metric, target, actual))
        except Exception:
            metrics_rows = []

        # Stops rows
        stops_rows: list[list] = []
        try:
            line_df = get_line_performance_details(df_processed)
            if line_df:
                first_seg = line_df[0]
                if hasattr(first_seg, "values"):
                    stops_rows = first_seg.values.tolist()
        except Exception:
            stops_rows = []

        return SpaResponse(
            df=df,
            rng_str=rng_str,
            metrics_rows=metrics_rows,
            stops_rows=stops_rows,
            from_cache=False,
        )

    def get_data_sync(self, req: SpaRequest) -> SpaResponse:
        """Blocking SPA fetch + transform.

        This is used for fallbacks where async scheduling isn't available.
        """

        key = self._cache_key(req)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        username, password = self._resolve_credentials()
        try:
            resp = self._fetch_and_process(req, username=username, password=password)
            self._put_cache(key, resp)
            return resp
        except Exception:
            try:
                self._logger.exception("Failed to fetch/process SPA data")
            except Exception:
                pass
            return SpaResponse(df=None, rng_str="", metrics_rows=[], stops_rows=[])

    async def get_data(self, req: SpaRequest) -> SpaResponse:
        try:
            # Run the blocking implementation in a worker thread.
            return await asyncio.to_thread(self.get_data_sync, req)
        except asyncio.CancelledError:
            # Important: do not swallow cancellation. This allows UI-level
            # timeouts (asyncio.wait_for) to work predictably.
            raise
        except Exception:
            try:
                self._logger.exception("Failed to fetch/process SPA data")
            except Exception:
                pass
            return SpaResponse(df=None, rng_str="", metrics_rows=[], stops_rows=[])
