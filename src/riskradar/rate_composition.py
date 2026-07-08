"""v0.7.1 장기금리 변화의 동일 만기 구성.

핵심 원칙
- DFII30은 core/aux 판정에 넣지 않는 전용 입력이다.
- DGS30과 DFII30의 공통 관측일에서 30년 명목-실질 금리차를 한 번만 계산한다.
- 곡선 설명은 DGS30과 DGS2를 같은 관측창으로 비교한다.
- 10년 장기채 추가 보상은 30년 금리 변화 계산과 분리해 참고 정보로만 보여준다.
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
        base["reason"] = "물가 영향을 뺀 30년 금리 또는 같은 날짜의 30년 미국 국채금리 자료를 확인할 수 없습니다."
        base["curve"] = _curve_summary(dgs30_raw, dgs2_raw)
        return base

    primary = _changes_from_series(series, C.RATE_COMPOSITION_LOOKBACK_OBS)
    context = _changes_from_series(series, C.RATE_COMPOSITION_CONTEXT_LOOKBACK_OBS)
    if primary is None:
        base["reason"] = "최근 약 1개월 변화를 나눠 볼 공통 관측치가 부족합니다."
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


def _fmt_change(value: Any) -> str:
    """내부 bp 변화를 사용자 화면의 %p로 보여준다."""
    if value is None:
        return "확인 불가"
    try:
        return f"{float(value) / 100.0:+.2f}%p"
    except (TypeError, ValueError):
        return "확인 불가"


def describe_rate_change(value: Any, *, gap: bool = False) -> str:
    """금리 변화량을 수식이 아니라 읽기 쉬운 말로 바꾼다."""
    if value is None:
        return "확인 불가"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "확인 불가"
    amount = f"{abs(x) / 100.0:.2f}%p"
    if abs(x) < 0.05:
        return "거의 변화 없음"
    if gap:
        return f"{amount} 확대" if x > 0 else f"{amount} 축소"
    return f"{amount} 상승" if x > 0 else f"{amount} 하락"


def describe_total_sentence(value: Any) -> str:
    if value is None:
        return "전체 금리 변화는 확인할 수 없습니다."
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "전체 금리 변화는 확인할 수 없습니다."
    amount = f"{abs(x) / 100.0:.2f}%p"
    if abs(x) < 0.05:
        return "전체 금리는 거의 변하지 않았습니다."
    return f"전체 금리는 {amount} 올랐습니다." if x > 0 else f"전체 금리는 {amount} 내렸습니다."


def render_markdown(summary: dict | None) -> str:
    """금리 탭용 30년 미국 국채금리 변화 설명."""
    s = summary or {}
    lines = ["## 30년 미국 국채금리 변화 나눠보기"]
    if s.get("status") != "ok":
        lines.append(s.get("reason") or "30년 미국 국채금리 변화를 나눠 볼 자료를 현재 확인할 수 없습니다.")
        lines.append("새 데이터 업데이트가 정상 완료되면 30년 미국 국채금리와 물가 영향을 뺀 30년 금리를 같은 날짜로 맞춰 보여줍니다.")
        return "\n\n".join(lines)

    primary = s.get("primary") or {}
    context = s.get("context") or {}
    lines += [
        "최근 약 1개월과 3개월 동안 30년 미국 국채금리가 얼마나 움직였는지 두 부분으로 나눠 봅니다. 둘 다 **30년짜리 금리**를 사용합니다.",
        "",
        "| 무엇이 움직였나 | 약 1개월 | 약 3개월 |",
        "|---|---:|---:|",
        f"| 전체 30년 국채금리 | {_fmt_change(primary.get('DGS30_change_bp'))} | {_fmt_change(context.get('DGS30_change_bp'))} |",
        f"| 물가 영향을 뺀 30년 금리 | {_fmt_change(primary.get('DFII30_change_bp'))} | {_fmt_change(context.get('DFII30_change_bp'))} |",
        f"| 일반 국채와 물가연동국채의 금리 차이 | {_fmt_change(primary.get('INFLCOMP30_change_bp'))} | {_fmt_change(context.get('INFLCOMP30_change_bp'))} |",
        "",
        "### 최근 약 1개월을 쉽게 읽으면",
        f"- **전체 금리:** {describe_rate_change(primary.get('DGS30_change_bp'))}",
        f"- **물가 영향을 뺀 금리:** {describe_rate_change(primary.get('DFII30_change_bp'))}",
        f"- **일반 국채와 물가연동국채의 금리 차이:** {describe_rate_change(primary.get('INFLCOMP30_change_bp'), gap=True)}",
        f"- **정리:** {describe_total_sentence(primary.get('DGS30_change_bp'))} 위 두 변화가 합쳐진 결과입니다.",
        "",
        "> 물가연동국채는 물가 변화가 반영되는 국채입니다. 일반 국채와 물가연동국채의 금리 차이에는 시장의 물가 기대뿐 아니라 물가 위험과 채권 수요·공급 영향도 섞일 수 있습니다.",
    ]

    curve = s.get("curve") or {}
    lines += ["", "### 장·단기 금리 움직임", curve.get("text") or "장·단기 금리 관계는 현재 확인할 수 없습니다."]

    tp = s.get("term_premium") or {}
    lines += ["", "### 참고: 10년 국채를 오래 보유할 때 요구되는 추가 보상"]
    if tp.get("status") == "ok":
        change = describe_rate_change(tp.get("change_1m_bp"))
        latest = tp.get("latest_value")
        latest_text = "확인 불가" if latest is None else f"{float(latest):.2f}%"
        if change == "거의 변화 없음":
            change_sentence = "최근 약 1개월 동안 거의 변하지 않았습니다."
        else:
            change_sentence = f"최근 약 1개월 동안 {change}했습니다."
        lines.append(
            f"현재 추정치는 {latest_text}이고, {change_sentence} "
            "10년 국채를 오래 보유할 때 시장이 요구하는 추가 보상을 모형으로 추정한 값입니다. "
            "위 30년 금리 변화를 나눈 두 항목에 더하는 값은 아닙니다."
        )
    else:
        lines.append("현재 자료를 확인할 수 없습니다. 이 값은 30년 금리 변화를 나눈 두 항목과는 따로 보는 참고 지표입니다.")
    return "\n".join(lines)


def _scan_direction(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "·"
    if x > 0.05:
        return "↑"
    if x < -0.05:
        return "↓"
    return "→"


def _scan_summary(real_bp: Any, gap_bp: Any) -> str:
    try:
        real = float(real_bp)
        gap = float(gap_bp)
    except (TypeError, ValueError):
        return "두 움직임의 방향은 현재 확인할 수 없습니다."
    if abs(real) < 0.05 or abs(gap) < 0.05:
        return "한쪽 움직임이 작아 전체 금리 변화는 다른 쪽의 영향을 더 크게 받았습니다."
    if real * gap > 0:
        return "두 움직임이 같은 방향이었습니다."
    return "두 움직임이 서로 일부 상쇄했습니다."


def render_scan_html(summary: dict | None) -> str:
    """30년 금리 탭용 시각 브리핑.

    산술 항등식을 인과적 기여도로 오해시키지 않도록 `기여`, `합계`라는 표현을 쓰지 않는다.
    같은 방향일 때만 막대로 비교하고, 반대 방향이면 숫자와 화살표만 보여준다.
    """
    from html import escape

    s = summary or {}
    if s.get("status") != "ok":
        reason = escape(str(s.get("reason") or "30년 금리 움직임을 현재 확인할 수 없습니다."))
        return (
            '<section class="rr-rate-panel">'
            '<div class="rr-section-title"><h2>30년 금리</h2></div>'
            f'<div class="rr-empty">{reason}</div>'
            '</section>'
        )

    primary = s.get("primary") or {}
    latest = s.get("latest") or {}
    latest_level = latest.get("DGS30")
    total = primary.get("DGS30_change_bp")
    real = primary.get("DFII30_change_bp")
    gap = primary.get("INFLCOMP30_change_bp")

    def fmt(value: Any) -> str:
        return _fmt_change(value)

    def numeric(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    real_n, gap_n = numeric(real), numeric(gap)
    same_direction = (
        real_n is None or gap_n is None
        or abs(real_n) < 0.05 or abs(gap_n) < 0.05
        or real_n * gap_n > 0
    )

    if same_direction:
        values = [abs(x) for x in (real_n, gap_n) if x is not None]
        scale = max(values or [1.0])

        def row(label: str, value: Any) -> str:
            x = numeric(value)
            width = 4.0 if x is None or abs(x) < 0.05 else min(100.0, max(7.0, abs(x) / scale * 100.0))
            direction = _scan_direction(value)
            tone = "up" if direction == "↑" else ("down" if direction == "↓" else "flat")
            return (
                '<div class="rr-rate-row">'
                f'<div class="rr-rate-label"><span>{label}</span><strong>{fmt(value)} {direction}</strong></div>'
                '<div class="rr-rate-track">'
                f'<span class="rr-rate-fill rr-rate-{tone}" style="width:{width:.1f}%"></span>'
                '</div>'
                '</div>'
            )
        movement_html = row("물가 영향 제외", real) + row("국채 금리 차이", gap)
    else:
        movement_html = (
            '<div class="rr-rate-opposite">'
            f'<div><span>물가 영향 제외</span><strong>{fmt(real)} {_scan_direction(real)}</strong></div>'
            f'<div><span>국채 금리 차이</span><strong>{fmt(gap)} {_scan_direction(gap)}</strong></div>'
            '</div>'
        )

    curve = s.get("curve") or {}
    curve_text = escape(str(curve.get("text") or "장·단기 금리 관계는 현재 확인할 수 없습니다."))
    level_text = "-" if latest_level is None else f"{float(latest_level):.2f}%"
    return (
        '<section class="rr-rate-panel">'
        '<div class="rr-rate-head">'
        '<div><span>30Y</span><strong>' + escape(level_text) + '</strong></div>'
        '<div><span>최근 1개월</span><strong class="rr-rate-total">' + escape(f'{_scan_direction(total)} {fmt(total)}') + '</strong></div>'
        '</div>'
        '<div class="rr-rate-kicker">같은 만기의 두 움직임</div>'
        + movement_html
        + f'<div class="rr-rate-conclusion">{escape(_scan_summary(real, gap))}</div>'
        + '</section>'
    )
