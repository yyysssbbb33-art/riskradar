"""분석 계층: 변화량, 백분위, synced snapshot.

원칙
- raw 관측값만 입력으로 쓴다 (ffill 금지).
- 모든 계산은 point-in-time. 날짜 t의 값은 t 이전 데이터만 쓴다.
- 긴 공백을 가로지른 변화량은 NaN (calendar-span guard).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def to_internal_value(key: str, raw: pd.Series) -> pd.Series:
    """FRED raw 값을 내부 저장 단위로 변환한다."""
    return raw.astype(float) * C.SERIES[key].raw_to_value


def change_nobs(values: pd.Series, dates: pd.Series, n: int, guard_days: int,
                to_bp: float) -> pd.Series:
    """n번째 이전 '실제 관측값' 대비 변화량. 관측일 개수 기준.

    values, dates: 관측 순서로 정렬된 raw 시계열 (결측 없음).
    guard_days 초과 span이면 NaN.
    """
    v = values.to_numpy(dtype=float)
    d = pd.to_datetime(dates.to_numpy())
    out = np.full(len(v), np.nan)
    for i in range(n, len(v)):
        span = (d[i] - d[i - n]).days
        if span > guard_days:
            continue
        out[i] = (v[i] - v[i - n]) * to_bp
    return pd.Series(out, index=values.index)


def point_in_time_percentile(values: pd.Series, dates: pd.Series, years: int,
                             min_obs: int, min_coverage_ratio: float = C.PERCENTILE_MIN_COVERAGE_RATIO) -> pd.Series:
    """각 관측일 t에서 [t-years, t] 창 안 value_t의 백분위(0~100).

    미래 데이터 누수 없음. 창 내 관측치가 min_obs 미만이면 NaN.
    weak rank: (창 안에서 <= value_t 비율) * 100.
    """
    v = values.to_numpy(dtype=float)
    d = np.array([np.datetime64(x, "D") for x in pd.to_datetime(dates)])
    out = np.full(len(v), np.nan)
    win = np.timedelta64(365 * years, "D")
    lo = 0
    for i in range(len(v)):
        # 창 하한을 두 포인터로 전진 (dates는 오름차순)
        while d[i] - d[lo] > win:
            lo += 1
        window = v[lo:i + 1]
        if len(window) < min_obs:
            continue
        # 관측치 개수만 많고 실제 달력 범위가 짧은 경우를 장기 위치로 오인하지 않는다.
        # ICE BofA 계열처럼 공식 제공 범위가 잘린 경우 3년 자료를 5년 위치로 표시하는 버그를 막는다.
        coverage_days = int((d[i] - d[lo]) / np.timedelta64(1, "D"))
        if coverage_days < int(365 * years * min_coverage_ratio):
            continue
        out[i] = float(np.mean(window <= v[i]) * 100.0)
    return pd.Series(out, index=values.index)


def build_series_frame(key: str, raw_df: pd.DataFrame) -> pd.DataFrame:
    """단일 시리즈의 raw -> 분석 프레임.

    raw_df: columns [date, value_raw]  (실제 관측만, 오름차순, 결측 없음)
    반환: date, value, change_20obs, change_60obs, percentile_3y/5y/10y
    """
    s = C.SERIES[key]
    df = raw_df.sort_values("date").reset_index(drop=True).copy()
    df["value"] = to_internal_value(key, df["value_raw"])

    for n, guard in ((20, C.SPAN_GUARD_20OBS_DAYS), (60, C.SPAN_GUARD_60OBS_DAYS)):
        df[f"change_{n}obs"] = change_nobs(df["value"], df["date"], n, guard,
                                           s.change_to_bp)

    df["percentile_3y"] = np.nan
    df["percentile_5y"] = np.nan
    df["percentile_10y"] = np.nan
    if s.percentile_applicable:
        if 3 in s.position_years:
            df["percentile_3y"] = point_in_time_percentile(
                df["value"], df["date"], 3, C.MIN_OBS_3Y)
        if 5 in s.position_years:
            df["percentile_5y"] = point_in_time_percentile(
                df["value"], df["date"], 5, C.MIN_OBS_5Y)
        if 10 in s.position_years:
            df["percentile_10y"] = point_in_time_percentile(
                df["value"], df["date"], 10, C.MIN_OBS_10Y)
    return df


def synced_snapshot(frames: dict[str, pd.DataFrame]) -> dict:
    """모든 시리즈에 raw 관측이 실제로 존재하는 가장 최근 날짜 기준 스냅샷.

    ffill 사용 금지. 교집합이 비면 date=None.
    staleness = (전 시리즈 최신 관측일의 최댓값) - synced_date, calendar days.
    """
    date_sets = [set(pd.to_datetime(f["date"])) for f in frames.values()]
    inter = set.intersection(*date_sets) if date_sets else set()
    latest_obs = max(pd.to_datetime(f["date"]).max() for f in frames.values())

    if not inter:
        return {"synced_date": None, "synced_staleness_days": None, "rows": {}}

    synced = max(inter)
    rows = {}
    for key, f in frames.items():
        r = f.loc[pd.to_datetime(f["date"]) == synced].iloc[-1]
        rows[key] = {
            "value": float(r["value"]),
            "change_20obs": _nan_to_none(r["change_20obs"]),
            "change_60obs": _nan_to_none(r["change_60obs"]),
        }
    return {
        "synced_date": synced.strftime("%Y-%m-%d"),
        "synced_staleness_days": int((latest_obs - synced).days),
        "rows": rows,
    }


def staleness_label(days: int | None) -> str | None:
    if days is None:
        return None
    for bound, label in C.STALENESS_BANDS:
        if days <= bound:
            return label
    return "stale"


def _nan_to_none(x):
    return None if pd.isna(x) else float(x)
