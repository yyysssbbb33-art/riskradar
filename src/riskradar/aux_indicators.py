"""함께 볼 지표·외부참고 수집과 방향 판정.

v0.6.0에서는 최신 요약뿐 아니라 raw history도 함께 반환할 수 있다.
신용 범위·지속 엔진은 BBB/A/CP의 실제 과거 경로가 필요하기 때문이다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import pandas as pd

from . import aux_config as AC
from . import fred_client as FC

DIRECTION_UP = "상승"
DIRECTION_DOWN = "하락"
DIRECTION_FLAT = "보합"
DIRECTION_NA = "판정불가"


@dataclass
class AuxDirection:
    key: str
    display_name: str
    ok: bool
    latest_value: float | None
    latest_date: str | None
    change_1m: float | None
    direction: str
    pct_in_history: float | None
    n_obs: int
    error: str | None = None
    level_pct: float | None = None
    history_start: str | None = None
    history_end: str | None = None
    history_years: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuxCollection:
    directions: dict[str, AuxDirection]
    raw_frames: dict[str, pd.DataFrame]


def _cfg_for_spec(spec: AC.AuxSeries,
                  cfg: AC.AuxDirectionCfg = AC.AUX_DIRECTION) -> AC.AuxDirectionCfg:
    return replace(
        cfg,
        lookback_obs=spec.lookback_obs if spec.lookback_obs is not None else cfg.lookback_obs,
        span_guard_days=(spec.span_guard_days
                         if spec.span_guard_days is not None else cfg.span_guard_days),
        flat_abs_pct=spec.flat_abs_pct if spec.flat_abs_pct is not None else cfg.flat_abs_pct,
        min_obs=spec.min_obs if spec.min_obs is not None else cfg.min_obs,
    )


def _history_meta(df: pd.DataFrame) -> tuple[str | None, str | None, float | None]:
    if df is None or df.empty:
        return None, None, None
    dates = pd.to_datetime(df["date"])
    start = dates.min()
    end = dates.max()
    return start.date().isoformat(), end.date().isoformat(), round((end - start).days / 365.25, 2)


def compute_direction(df: pd.DataFrame, spec: AC.AuxSeries,
                      cfg: AC.AuxDirectionCfg = AC.AUX_DIRECTION) -> AuxDirection:
    cfg = _cfg_for_spec(spec, cfg)
    if df is None or df.empty:
        return AuxDirection(spec.key, spec.display_name, False, None, None,
                            None, DIRECTION_NA, None, 0, "empty df")

    d = df.sort_values("date").reset_index(drop=True).copy()
    d["date"] = pd.to_datetime(d["date"])
    d["value"] = d["value_raw"] * spec.raw_to_value
    h_start, h_end, h_years = _history_meta(d)

    lb = cfg.lookback_obs
    prev_val = d["value"].shift(lb)
    prev_date = d["date"].shift(lb)
    gap_days = (d["date"] - prev_date).dt.days
    raw_change = d["value"] - prev_val
    d["change"] = raw_change.where(gap_days <= cfg.span_guard_days)

    valid = d["change"].dropna()
    latest_value = float(d["value"].iloc[-1])
    latest_date = d["date"].iloc[-1].date().isoformat()
    level_pct = round(float((d["value"] <= latest_value).mean() * 100.0), 1)

    if valid.empty:
        return AuxDirection(spec.key, spec.display_name, True, latest_value,
                            latest_date, None, DIRECTION_NA, None, 0,
                            "no valid change (span guard)", level_pct,
                            h_start, h_end, h_years)

    latest_change = d["change"].iloc[-1]
    change_disp = (float(latest_change) * spec.change_to_disp
                   if pd.notna(latest_change) else None)
    n = int(valid.shape[0])

    if pd.isna(latest_change) or n < cfg.min_obs:
        return AuxDirection(spec.key, spec.display_name, True, latest_value,
                            latest_date, change_disp, DIRECTION_NA, None, n,
                            "insufficient history" if n < cfg.min_obs else "latest change NaN",
                            level_pct, h_start, h_end, h_years)

    abs_pct = float((valid.abs() <= abs(float(latest_change))).mean() * 100.0)
    if abs_pct < cfg.flat_abs_pct:
        direction = DIRECTION_FLAT
    elif latest_change > 0:
        direction = DIRECTION_UP
    else:
        direction = DIRECTION_DOWN

    return AuxDirection(spec.key, spec.display_name, True, latest_value,
                        latest_date, change_disp, direction, round(abs_pct, 1), n,
                        level_pct=level_pct, history_start=h_start,
                        history_end=h_end, history_years=h_years)


def _fetch_with_attempts(series_id: str, out_key: str, api_key: str,
                         timeout: float, start: str, max_attempts: int):
    last_error = None
    res = None
    for _attempt in range(1, max_attempts + 1):
        res = FC.fetch_fred_series(series_id, out_key, api_key, timeout, start)
        if res.ok:
            break
        last_error = res.error
    return res, last_error


def _fetch_spread(spec: AC.AuxSeries, api_key: str, timeout: float,
                  start: str, max_attempts: int):
    if len(spec.component_series_ids) != 2:
        return None, "spread indicator requires exactly two component series"

    frames = []
    errors = []
    for idx, series_id in enumerate(spec.component_series_ids):
        res, last_error = _fetch_with_attempts(
            series_id, f"{spec.key}_{idx}", api_key, timeout, start, max_attempts
        )
        if res is None or not res.ok:
            errors.append(last_error or getattr(res, "error", None) or "fetch failed")
            continue
        frames.append(res.df.rename(columns={"value_raw": f"value_{idx}"}))

    if errors or len(frames) != 2:
        return None, "; ".join(str(x) for x in errors) or "component fetch failed"

    merged = frames[0].merge(frames[1], on="date", how="inner").sort_values("date")
    if merged.empty:
        return None, "no overlapping observations between spread components"
    merged["value_raw"] = merged["value_0"] - merged["value_1"]
    return merged[["date", "value_raw"]].reset_index(drop=True), None


def collect_aux_bundle(api_key: str | None = None, timeout: float | None = None,
                       start: str | None = None, max_attempts: int = 2) -> AuxCollection:
    """모든 확인·외부·호환 지표를 수집하고 최신 방향 + raw history를 반환한다."""
    from . import config as C

    api_key, timeout = FC._resolve_creds(api_key, timeout)
    start = start or C.FRED_START_DATE
    max_attempts = max(1, int(max_attempts))

    directions: dict[str, AuxDirection] = {}
    raw_frames: dict[str, pd.DataFrame] = {}
    for key in AC.AUX_ORDER:
        spec = AC.AUX_SERIES[key]

        if spec.fetch_kind == "spread":
            df, error = _fetch_spread(spec, api_key, timeout, start, max_attempts)
            if df is None:
                directions[key] = AuxDirection(key, spec.display_name, False, None, None,
                                               None, DIRECTION_NA, None, 0, error)
                continue
            raw_frames[key] = df.copy()
            directions[key] = compute_direction(df, spec)
            continue

        res, last_error = _fetch_with_attempts(
            spec.series_id, key, api_key, timeout, start, max_attempts
        )
        if res is None or not res.ok:
            error = last_error or (getattr(res, "error", None)
                                   if res is not None else "fetch failed")
            directions[key] = AuxDirection(key, spec.display_name, False, None, None,
                                           None, DIRECTION_NA, None, 0, error)
            continue
        raw_frames[key] = res.df.copy()
        directions[key] = compute_direction(res.df, spec)
    return AuxCollection(directions, raw_frames)


def collect_aux(api_key: str | None = None, timeout: float | None = None,
                start: str | None = None, max_attempts: int = 2) -> dict[str, AuxDirection]:
    """v0.5.x 호환 인터페이스. 최신 방향 dict만 반환한다."""
    return collect_aux_bundle(api_key, timeout, start, max_attempts).directions
