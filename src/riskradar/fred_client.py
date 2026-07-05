"""FRED API 클라이언트.

- 핵심 6개 시리즈를 병렬 fetch (fetch_all).
- 저수준 fetch_fred_series를 노출해 보조지표(2층)도 같은 경로를 재사용한다.
- '.' (결측)은 raw에서 제거한다. ffill 하지 않는다.
- 실패한 시리즈는 예외 대신 결과에 담아 부분 실패 정책이 처리하게 한다.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import time
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


def fetch_fred_series(series_id: str, out_key: str, api_key: str,
                      timeout: float, start: str) -> FetchResult:
    """FRED series 하나를 받아 (date, value_raw) DataFrame으로.

    일시적인 429/5xx·네트워크 오류는 짧게 재시도한다. 한 번의 순간 오류 때문에
    보조지표가 화면에서 사라지는 일을 줄이기 위한 운영 보완이다.
    """
    max_retries = max(0, int(os.environ.get("FRED_MAX_RETRIES", "2")))
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(_BASE, params={
                "series_id": series_id, "api_key": api_key, "file_type": "json",
                "observation_start": start,
            }, timeout=timeout)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                resp.raise_for_status()
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            rows = [(o["date"], o["value"]) for o in obs if o.get("value") not in (".", "", None)]
            if not rows:
                return FetchResult(out_key, False, None, "empty observations")
            df = pd.DataFrame(rows, columns=["date", "value_raw"])
            df["date"] = pd.to_datetime(df["date"])
            df["value_raw"] = df["value_raw"].astype(float)
            return FetchResult(out_key, True, df.sort_values("date").reset_index(drop=True))
        except Exception as e:  # noqa: BLE001 - 부분 실패로 흡수
            last_error = e
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            log.warning("FRED fetch failed for %s after %s attempts: %s",
                        series_id, max_retries + 1, e)
    return FetchResult(out_key, False, None,
                       f"{type(last_error).__name__}: {last_error}")


def _fetch_one(key: str, api_key: str, timeout: float, start: str) -> FetchResult:
    # 기존 인터페이스 유지: 핵심 6개용
    return fetch_fred_series(C.SERIES[key].series_id, key, api_key, timeout, start)


def _resolve_creds(api_key: str | None, timeout: float | None):
    api_key = api_key or os.environ["FRED_API_KEY"]
    timeout = timeout or float(os.environ.get("FRED_REQUEST_TIMEOUT_SECONDS", "8"))
    return api_key, timeout


def fetch_all(api_key: str | None = None, timeout: float | None = None,
              start: str = C.FRED_START_DATE) -> dict[str, FetchResult]:
    api_key, timeout = _resolve_creds(api_key, timeout)
    results: dict[str, FetchResult] = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_fetch_one, k, api_key, timeout, start): k
                for k in C.SERIES_ORDER}
        for fut in cf.as_completed(futs):
            r = fut.result()
            results[r.key] = r
    return results
