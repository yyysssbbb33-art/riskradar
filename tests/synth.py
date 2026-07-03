"""오프라인 테스트용 합성 시계열 (FRED 형태 흉내).

business-day 인덱스, 결측 없음, raw 단위(FRED 원단위)로 생성한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _bdays(start: str, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def raw(dates: pd.DatetimeIndex, values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"date": dates, "value_raw": values.astype(float)})


def make_raw_by_key(n: int = 1600, seed: int = 7) -> dict[str, pd.DataFrame]:
    """6개 시리즈 raw dict. 단위는 FRED 원단위(퍼센트 등)."""
    rng = np.random.default_rng(seed)
    d = _bdays("2016-01-04", n)
    t = np.arange(n)

    vix = 16 + 4 * np.sin(t / 90) + rng.normal(0, 2, n).cumsum() * 0.02
    vix = np.clip(vix, 9, 80)

    hy = 3.5 + 0.8 * np.sin(t / 120) + rng.normal(0, 0.05, n).cumsum() * 0.01  # percent
    hy = np.clip(hy, 2.5, 12)

    t10y3m = 1.2 - 3.0 * (t / n) + 0.5 * np.sin(t / 70)  # percentage points, 역전 유도
    dgs30 = 3.0 + 1.8 * (t / n) + 0.2 * np.sin(t / 60)   # percent, 상승 추세
    dgs2 = 2.0 + 2.5 * (t / n) + 0.2 * np.sin(t / 50)
    dfii10 = 0.2 + 1.9 * (t / n) + 0.1 * np.sin(t / 55)

    return {
        "VIX": raw(d, vix),
        "HYOAS": raw(d, hy),
        "T10Y3M": raw(d, t10y3m),
        "DGS30": raw(d, dgs30),
        "DGS2": raw(d, dgs2),
        "DFII10": raw(d, dfii10),
    }
