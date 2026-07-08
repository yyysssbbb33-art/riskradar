"""v0.7.1 장기금리 변화의 동일 만기 구성.

핵심 원칙
- DFII30은 core/aux 판정에 넣지 않는 전용 입력이다.
- DGS30과 DFII30의 공통 관측일에서 30년 명목-실질 금리차를 한 번만 계산한다.
- 곡선 설명은 DGS30과 DGS2를 같은 관측창으로 비교한다.
- 10년 Term Premium은 30년 산술 구성에 더하지 않는 별도 맥락이다.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import config as C
from . import fred_client as FC

DFII30_SERIES_ID = "DFII30"
DFII30_KEY = "DFII30"
PROXY_KEY = "INFLCOMP30"


def fetch_dfii30(api_key: str | None = None, timeout: float | None = None,
                 start: str = C.FRED_START_DATE) -> FC.FetchResult:
    """30년 실질금리를 정확히 한 경로에서 수집한다."""
    api_key, timeout = FC._resolve_creds(api_key, timeout)
    return FC.fetch_fred_series(DFII30_SERIES_ID, DFII30_KEY, api_key, timeout, start)


def build_composition_series(dgs30_raw: pd.DataFrame | None,
                             dfii30_raw: pd.DataFrame | None) -> pd.DataFrame:
    """같은 날짜의 30년 명목·실질금리와 명목-실질 금리차를 만든다."""
    columns = ["date", "DGS30", "DFII30", "INFLCOMP30"]
    if dgs30_raw is None or dfii30_raw is None or dgs30_raw.empty or dfii30_raw.empty:
        return pd.DataFrame(columns=columns)

    nominal = dgs30_raw[["date", "value_raw"]].copy()
    real = dfii30_raw[["date", "value_raw"]].copy()
    nominal["date"] = pd.to_datetime(nominal["date"])
    real["date"] = pd.to_datetime(real["date"])
    nominal["value_raw"] = pd.to_numeric(nominal["value_raw"], errors="coerce")
    real["value_raw"] = pd.to_numeric(real["value_raw"], errors="coerce")
    nominal = nominal.dropna().rename(columns={"value_raw": "DGS30"})
    real = real.dropna().rename(columns={"value_raw": "DFII30"})

    merged = nominal.merge(real, on="date", how="inner").sort_values("date")
    if merged.empty:
        return pd.DataFrame(columns=columns)
    merged["INFLCOMP30"] = merged["DGS30"] - merged["DFII30"]
    return merged[columns].drop_duplicates("date", keep="last").reset_index(drop=True)


def _guard_days(lookback_obs: int) -> int:
    if lookback_obs == 20:
        return C.SPAN_GUARD_20OBS_DAYS
    if lookback_obs == 60:
        return C.SPAN_GUARD_60OBS_DAYS
    raise ValueError(f"unsupported rate composition lookback: {lookback_obs}")


def _changes_from_series(series: pd.DataFrame, lookback_obs: int) -> dict[str, Any] | None:
    if series is None or series.empty or len(series) <= lookback_obs:
        return None
    d = series.sort_values("date").reset_index(drop=True)
    latest = d.iloc[-1]
    previous = d.iloc[-1 - lookback_obs]
    if (pd.Timestamp(latest["date"]) - pd.Timestamp(previous["date"])).days > _guard_days(lookback_obs):
        return None

    out: dict[str, Any] = {
        "lookback_obs": lookback_obs,
        "start_date": pd.Timestamp(previous["date"]).date().isoformat(),
        "end_date": pd.Timestamp(latest["date"]).date().isoformat(),
    }
    for key in ("DGS30", "DFII30", "INFLCOMP30"):
        out[f"{key}_change_bp"] = round((float(latest[key]) - float(previous[key])) * 100.0, 6)
    out["identity_residual_bp"] = round(
        out["DGS30_change_bp"] - out["DFII30_change_bp"] - out["INFLCOMP30_change_bp"],
        9,
    )
    return out


def _direction(change_bp: float, material_bp: float) -> str:
    if change_bp > material_bp:
        return "up"
    if change_bp < -material_bp:
        return "down"
    return "flat"


def _curve_summary(dgs30_raw: pd.DataFrame | None,
                   dgs2_raw: pd.DataFrame | None,
                   *, lookback_obs: int = C.RATE_COMPOSITION_LOOKBACK_OBS,
                   material_bp: float = C.RATE_COMPOSITION_MATERIAL_BP) -> dict[str, Any]:
    unavailable = {
        "status": "unavailable",
        "lookback_obs": lookback_obs,
        "material_bp": material_bp,
        "code": "unavailable",
        "text": "장·단기 금리 곡선은 현재 확인할 수 없습니다.",
    }
    if dgs30_raw is None or dgs2_raw is None or dgs30_raw.empty or dgs2_raw.empty:
        return unavailable

    long = dgs30_raw[["date", "value_raw"]].copy().rename(columns={"value_raw": "DGS30"})
    short = dgs2_raw[["date", "value_raw"]].copy().rename(columns={"value_raw": "DGS2"})
    long["date"] = pd.to_datetime(long["date"])
    short["date"] = pd.to_datetime(short["date"])
    frame = long.merge(short, on="date", how="inner").dropna().sort_values("date").reset_index(drop=True)
    if len(frame) <= lookback_obs:
        return unavailable

    latest = frame.iloc[-1]
    previous = frame.iloc[-1 - lookback_obs]
    if (pd.Timestamp(latest["date"]) - pd.Timestamp(previous["date"])).days > _guard_days(lookback_obs):
        return unavailable

    long_change = (float(latest["DGS30"]) - float(previous["DGS30"])) * 100.0
    short_change = (float(latest["DGS2"]) - float(previous["DGS2"])) * 100.0
    slope_change = long_change - short_change
    long_dir = _direction(long_change, material_bp)
    short_dir = _direction(short_change, material_bp)
    slope_dir = _direction(slope_change, material_bp)

    code = "no_clear_curve_move"
    text = "최근 약 1개월 기준 장·단기 금리차에 뚜렷한 변화가 없습니다."
    if slope_dir == "up":
        if long_dir == "up" and short_dir == "up":
            code = "bear_steepening"
            text = "장·단기 금리가 함께 올랐고 장기가 더 올라 곡선이 가팔라졌습니다(bear steepening)."
        elif long_dir == "up" and short_dir == "flat":
            code = "bear_steepening"
            text = "장기금리는 오르고 단기는 큰 변화가 없어 곡선이 가팔라졌습니다(bear steepening)."
        elif long_dir == "up" and short_dir == "down":
            code = "long_up_short_down"
            text = "장기금리는 오르고 단기금리는 내려 곡선이 가팔라졌습니다(장·단기 엇갈림)."
        elif short_dir == "down" and long_dir == "down":
            code = "bull_steepening"
            text = "장·단기 금리가 함께 내렸고 단기가 더 내려 곡선이 가팔라졌습니다(bull steepening)."
        elif short_dir == "down" and long_dir == "flat":
            code = "bull_steepening"
            text = "장기금리는 큰 변화가 없고 단기금리는 내려 곡선이 가팔라졌습니다(bull steepening)."
        else:
            code = "steepening"
            text = "장·단기 금리차가 벌어져 곡선이 가팔라졌습니다."
    elif slope_dir == "down":
        if long_dir == "down" and short_dir == "down":
            code = "bull_flattening"
            text = "장·단기 금리가 함께 내렸고 장기가 더 내려 곡선이 평평해졌습니다(bull flattening)."
        elif long_dir == "down" and short_dir == "flat":
            code = "bull_flattening"
            text = "장기금리는 내리고 단기는 큰 변화가 없어 곡선이 평평해졌습니다(bull flattening)."
        elif long_dir == "down" and short_dir == "up":
            code = "long_down_short_up"
            text = "장기금리는 내리고 단기금리는 올라 곡선이 평평해졌습니다(장·단기 엇갈림)."
        elif short_dir == "up" and long_dir == "up":
            code = "bear_flattening"
            text = "장·단기 금리가 함께 올랐고 단기가 더 올라 곡선이 평평해졌습니다(bear flattening)."
        elif short_dir == "up" and long_dir == "flat":
            code = "bear_flattening"
            text = "장기금리는 큰 변화가 없고 단기금리는 올라 곡선이 평평해졌습니다(bear flattening)."
        else:
            code = "flattening"
            text = "장·단기 금리차가 줄어 곡선이 평평해졌습니다."

    return {
        "status": "ok",
        "lookback_obs": lookback_obs,
        "material_bp": material_bp,
        "start_date": pd.Timestamp(previous["date"]).date().isoformat(),
        "end_date": pd.Timestamp(latest["date"]).date().isoformat(),
        "DGS30_change_bp": round(long_change, 6),
        "DGS2_change_bp": round(short_change, 6),
        "slope_change_bp": round(slope_change, 6),
        "long_direction": long_dir,
        "short_direction": short_dir,
        "slope_direction": slope_dir,
        "code": code,
        "text": text,
    }


def _term_premium_context(aux_df: pd.DataFrame | None) -> dict[str, Any]:
    if aux_df is None or aux_df.empty or "key" not in aux_df.columns:
        return {"status": "unavailable"}
    hit = aux_df.loc[aux_df["key"].astype(str) == "TERMPREM"]
    if hit.empty:
        return {"status": "unavailable"}
    row = hit.iloc[-1]
    value = row.get("latest_value")
    change = row.get("change_1m")
    if value is None or pd.isna(value):
        return {
            "status": "unavailable",
            "fetch_status": str(row.get("fetch_status", "failed")),
            "staleness_label": str(row.get("staleness_label", "unknown")),
        }
    return {
        "status": "ok",
        "latest_value": float(value),
        "value_unit": str(row.get("value_unit", "%")),
        "change_1m_bp": None if change is None or pd.isna(change) else float(change),
        "direction": str(row.get("direction", "판정불가")),
        "latest_date": None if pd.isna(row.get("latest_date")) else str(row.get("latest_date")),
        "fetch_status": str(row.get("fetch_status", "ok")),
        "staleness_label": str(row.get("staleness_label", "unknown")),
    }


def build_summary(series: pd.DataFrame,
                  dgs30_raw: pd.DataFrame | None,
                  dgs2_raw: pd.DataFrame | None,
                  aux_df: pd.DataFrame | None,
                  *, fetch_error: str | None = None,
                  stale_core: set[str] | None = None) -> dict[str, Any]:
    """UI·Telegram·저장이 함께 쓰는 단일 요약을 만든다."""
    stale_core = stale_core or set()
    base: dict[str, Any] = {
        "schema_version": "rate-composition-v1",
        "status": "unavailable",
        "series_id": DFII30_SERIES_ID,
        "lookback_obs": C.RATE_COMPOSITION_LOOKBACK_OBS,
        "context_lookback_obs": C.RATE_COMPOSITION_CONTEXT_LOOKBACK_OBS,
        "pure_inflation_expectation": False,
        "term_premium_is_component": False,
        "fetch_error": fetch_error,
        "source_status": "stale" if "DGS30" in stale_core else "ok",
        "term_premium": _term_premium_context(aux_df),
    }
    if series is None or series.empty:
        base["reason"] = "DFII30 또는 같은 날짜의 30년 명목금리 자료를 확인할 수 없습니다."
        base["curve"] = _curve_summary(dgs30_raw, dgs2_raw)
        return base

    primary = _changes_from_series(series, C.RATE_COMPOSITION_LOOKBACK_OBS)
    context = _changes_from_series(series, C.RATE_COMPOSITION_CONTEXT_LOOKBACK_OBS)
    if primary is None:
        base["reason"] = "약 1개월 동일 만기 변화를 계산할 공통 관측치가 부족합니다."
        base["curve"] = _curve_summary(dgs30_raw, dgs2_raw)
        return base

    latest = series.sort_values("date").iloc[-1]
    base.update({
        "status": "ok",
        "observation_date": pd.Timestamp(latest["date"]).date().isoformat(),
        "latest": {
            "DGS30": float(latest["DGS30"]),
            "DFII30": float(latest["DFII30"]),
            "INFLCOMP30": float(latest["INFLCOMP30"]),
        },
        "primary": primary,
        "context": context,
        "curve": _curve_summary(dgs30_raw, dgs2_raw),
    })
    return base


def _fmt_bp(value: Any) -> str:
    if value is None:
        return "확인 불가"
    try:
        return f"{float(value):+.1f}bp"
    except (TypeError, ValueError):
        return "확인 불가"


def render_markdown(summary: dict | None) -> str:
    """첫 화면용 장기금리 구성 패널."""
    s = summary or {}
    lines = ["## 장기금리 변화의 구성"]
    if s.get("status") != "ok":
        lines.append(s.get("reason") or "30년 동일 만기 구성 자료를 현재 확인할 수 없습니다.")
        lines.append("새 v0.7.1 배치가 정상 완료되면 30년 명목금리와 30년 실질금리를 같은 날짜로 맞춰 보여줍니다.")
        return "\n\n".join(lines)

    primary = s.get("primary") or {}
    context = s.get("context") or {}
    lines += [
        "같은 **30년 만기**끼리 맞춰, 명목금리 변화가 실질금리와 명목−실질 금리차에서 각각 얼마나 나타났는지 봅니다.",
        "",
        "| 구성 | 약 1개월 | 약 3개월 |",
        "|---|---:|---:|",
        f"| 30년 명목금리 | {_fmt_bp(primary.get('DGS30_change_bp'))} | {_fmt_bp(context.get('DGS30_change_bp'))} |",
        f"| 30년 실질금리 | {_fmt_bp(primary.get('DFII30_change_bp'))} | {_fmt_bp(context.get('DFII30_change_bp'))} |",
        f"| 30년 명목−실질 금리차 | {_fmt_bp(primary.get('INFLCOMP30_change_bp'))} | {_fmt_bp(context.get('INFLCOMP30_change_bp'))} |",
        "",
        f"**같은 만기 확인:** {_fmt_bp(primary.get('DGS30_change_bp'))} = "
        f"{_fmt_bp(primary.get('DFII30_change_bp'))} + {_fmt_bp(primary.get('INFLCOMP30_change_bp'))}",
        "",
        "> 30년 명목−실질 금리차는 **물가보상 proxy**입니다. 순수한 기대인플레이션으로 단정하지 않습니다.",
    ]

    curve = s.get("curve") or {}
    lines += ["", "### 곡선 움직임", curve.get("text") or "장·단기 금리 곡선은 현재 확인할 수 없습니다."]

    tp = s.get("term_premium") or {}
    lines += ["", "### 10년 Term Premium은 별도 맥락"]
    if tp.get("status") == "ok":
        change = _fmt_bp(tp.get("change_1m_bp"))
        latest = tp.get("latest_value")
        latest_text = "확인 불가" if latest is None else f"{float(latest):.2f}%"
        lines.append(
            f"현재 {latest_text}, 약 1개월 변화 {change} · {tp.get('direction', '판정불가')}. "
            "이 값은 위 30년 동일 만기 산술 구성에 더하는 항목이 아닙니다."
        )
    else:
        lines.append("현재 자료를 확인할 수 없습니다. 이 값은 위 30년 동일 만기 산술 구성과 별도입니다.")
    return "\n".join(lines)
