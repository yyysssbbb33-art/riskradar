"""FRED API 클라이언트.

- 6개 시리즈를 병렬 fetch.
- '.' (결측)은 raw에서 제거한다. ffill 하지 않는다.
- 실패한 시리즈는 예외 대신 결과에 담아 부분 실패 정책이 처리하게 한다.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
from dataclasses import dataclass

import pandas as pd
import requests

from . import config as C

log = logging.getLogger(__name__)
_BASE = "https://api.stlouisfed.org/fred/series/observations"


@dataclass
class FetchResult:
    key: str
    ok: bool
    df: pd.DataFrame | None
    error: str | None = None


def _fetch_one(key: str, api_key: str, timeout: float, start: str) -> FetchResult:
    sid = C.SERIES[key].series_id
    try:
        resp = requests.get(_BASE, params={
            "series_id": sid, "api_key": api_key, "file_type": "json",
            "observation_start": start,
        }, timeout=timeout)
        resp.raise_for_status()
        obs = resp.json().get("observations", [])
        rows = [(o["date"], o["value"]) for o in obs if o.get("value") not in (".", "", None)]
        if not rows:
            return FetchResult(key, False, None, "empty observations")
        df = pd.DataFrame(rows, columns=["date", "value_raw"])
        df["date"] = pd.to_datetime(df["date"])
        df["value_raw"] = df["value_raw"].astype(float)
        return FetchResult(key, True, df.sort_values("date").reset_index(drop=True))
    except Exception as e:  # noqa: BLE001 - 부분 실패로 흡수
        log.warning("FRED fetch failed for %s: %s", sid, e)
        return FetchResult(key, False, None, f"{type(e).__name__}: {e}")


def fetch_all(api_key: str | None = None, timeout: float | None = None,
              start: str = C.FRED_START_DATE) -> dict[str, FetchResult]:
    api_key = api_key or os.environ["FRED_API_KEY"]
    timeout = timeout or float(os.environ.get("FRED_REQUEST_TIMEOUT_SECONDS", "8"))
    results: dict[str, FetchResult] = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_fetch_one, k, api_key, timeout, start): k
                for k in C.SERIES_ORDER}
        for fut in cf.as_completed(futs):
            r = fut.result()
            results[r.key] = r
    return results
