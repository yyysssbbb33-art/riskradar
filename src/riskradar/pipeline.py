"""raw -> 분석 산출물 파이프라인.

compute_all()은 refresh와 anti-lookahead 테스트가 공유하는 유일한 진입점이다.
입력은 raw 관측값만(ffill 없음), 출력은 결정론적이다.
"""
from __future__ import annotations

import pandas as pd

from . import config as C
from . import state_rules as SR
from . import transforms as T


def compute_frames(raw_by_key: dict[str, pd.DataFrame],
                   th: C.Thresholds = C.THRESHOLDS) -> dict[str, pd.DataFrame]:
    """key -> [date, value_raw] raw dict을 분석 프레임 dict으로."""
    frames = {}
    for key in C.SERIES_ORDER:
        if key not in raw_by_key:
            continue
        df = T.build_series_frame(key, raw_by_key[key])
        df = SR.attach_states(key, df, th)
        frames[key] = df
    return frames


def signal_matrix(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for key in C.SERIES_ORDER:
        if key not in frames:
            continue
        s = C.SERIES[key]
        r = frames[key].iloc[-1]
        rows.append({
            "series_id": s.series_id,
            "key": key,
            "display_name": s.display_name,
            "axis": s.axis,
            "latest_observed_date": pd.to_datetime(r["date"]).strftime("%Y-%m-%d"),
            "latest_value": float(r["value"]),
            "value_unit": s.value_unit,
            "change_20obs": _n(r["change_20obs"]),
            "change_60obs": _n(r["change_60obs"]),
            "change_unit": s.change_unit,
            "percentile_3y": _n(r["percentile_3y"]),
            "percentile_5y": _n(r["percentile_5y"]),
            "percentile_10y": _n(r["percentile_10y"]),
            "state_code": r["state_code"],
            "state_label": r["state_label"],
            "state_reason": SR.state_reason(key, r),
            "drop_flag": bool(r["drop_flag"]),
        })
    return pd.DataFrame(rows)


def chart_data(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for key, df in frames.items():
        p = df[["date", "value", "change_20obs", "change_60obs",
                "percentile_3y", "percentile_5y", "percentile_10y", "state_code",
                "state_label", "drop_flag"]].copy()
        p.insert(0, "series_id", C.SERIES[key].series_id)
        p.insert(1, "key", key)
        parts.append(p)
    return pd.concat(parts, ignore_index=True)


def compute_all(raw_by_key: dict[str, pd.DataFrame],
                th: C.Thresholds = C.THRESHOLDS) -> dict:
    frames = compute_frames(raw_by_key, th)
    snap = T.synced_snapshot(frames)
    return {
        "frames": frames,
        "signal_matrix": signal_matrix(frames),
        "chart_data": chart_data(frames),
        "synced": snap,
    }


def _n(x):
    return None if pd.isna(x) else float(x)
