"""v0.8.0 금리 전용 탭의 읽기 전용 시각화.

판정은 새로 만들지 않는다. signal_matrix, aux_signal_matrix,
rate_composition 요약을 카드·표로 다시 배치한다.
"""
from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd

from .display_text import core_name, state_name
from .formatting import fmt_change, fmt_value

RATE_OVERVIEW_KEYS = ("DGS30", "DGS2", "DFII10", "T10Y3M")
RATE_SUBTITLES = {
    "DGS30": "미국 30년 국채금리",
    "DGS2": "미국 2년 국채금리",
    "DFII10": "물가 영향을 뺀 10년 금리",
    "T10Y3M": "10년·3개월 국채금리 차이",
}


def _row(df: pd.DataFrame | None, key: str) -> pd.Series | None:
    if df is None or df.empty or "key" not in df.columns:
        return None
    hit = df.loc[df["key"].astype(str) == key]
    return None if hit.empty else hit.iloc[-1]


def _direction(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "·"
    if x > 0:
        return "↑"
    if x < 0:
        return "↓"
    return "→"


def _pct_change_from_bp(value: Any) -> str:
    try:
        return f"{float(value) / 100.0:+.2f}%p"
    except (TypeError, ValueError):
        return "-"



def _visual_state_class(key: str, code: str, drop: bool = False) -> str:
    if drop:
        return "rr-state-easing"
    if key in {"DGS30", "DGS2", "DFII10"}:
        return {"stable": "rr-state-quiet", "rise_watch": "rr-state-watch", "rate_shock": "rr-state-hot"}.get(code, "rr-state-quiet")
    if key == "T10Y3M":
        return {
            "normal": "rr-state-quiet", "watch": "rr-state-watch",
            "inverted": "rr-state-hot", "long_inverted": "rr-state-hot",
            "re_normalizing": "rr-state-easing", "re_normalized": "rr-state-done",
        }.get(code, "rr-state-quiet")
    return "rr-state-quiet"

def render_rate_overview_cards_html(matrix: pd.DataFrame | None) -> str:
    """금리 핵심 4개를 2×2 숫자 카드로 보여준다."""
    cards: list[str] = []
    for key in RATE_OVERVIEW_KEYS:
        row = _row(matrix, key)
        if row is None:
            cards.append(
                '<article class="rr-metric-card rr-metric-card-quiet">'
                f'<div class="rr-metric-name">{escape(core_name(key, short=True))}</div>'
                f'<div class="rr-metric-subtitle">{escape(RATE_SUBTITLES.get(key, ""))}</div>'
                '<div class="rr-metric-value">-</div>'
                '<div class="rr-metric-state">확인 불가</div>'
                '<div class="rr-metric-change">· - <span>최근 약 1개월</span></div>'
                '</article>'
            )
            continue
        state = state_name(
            str(row.get("state_code", "")), str(row.get("state_label", "")),
            drop=bool(row.get("drop_flag", False)), key=key,
        )
        change_raw = row.get("change_20obs")
        change = fmt_change(change_raw, str(row.get("change_unit", "")))
        code = str(row.get("state_code", ""))
        drop = bool(row.get("drop_flag", False))
        hot = code in {"rise_watch", "rate_shock", "watch", "inverted", "long_inverted", "re_normalizing", "re_normalized"} or drop
        visual = _visual_state_class(key, code, drop)
        cls = f"rr-metric-card {visual}" + (" rr-metric-card-hot" if hot else " rr-metric-card-quiet")
        cards.append(
            f'<article class="{cls}">'
            f'<div class="rr-metric-name">{escape(core_name(key, short=True))}</div>'
            f'<div class="rr-metric-subtitle">{escape(RATE_SUBTITLES.get(key, ""))}</div>'
            f'<div class="rr-metric-value">{escape(fmt_value(row.get("latest_value"), str(row.get("value_unit", ""))))}</div>'
            f'<div class="rr-metric-state">{escape(state)}</div>'
            f'<div class="rr-metric-change">{escape(_direction(change_raw))} {escape(change)} <span>최근 약 1개월</span></div>'
            '</article>'
        )
    return '<div class="rr-metric-grid rr-rate-overview-grid">' + ''.join(cards) + '</div>'


def render_rate_curve_html(summary: dict | None) -> str:
    """2년·30년 금리의 같은 기간 움직임을 숫자 중심으로 보여준다."""
    curve = (summary or {}).get("curve") or {}
    if curve.get("status") != "ok":
        return '<section class="rr-panel"><div class="rr-section-title"><h2>단기·장기 금리 관계</h2></div><div class="rr-empty">현재 장·단기 금리 움직임을 확인할 수 없습니다.</div></section>'

    short = curve.get("DGS2_change_bp")
    long = curve.get("DGS30_change_bp")
    code = str(curve.get("code") or "")
    technical = {
        "bear_steepening": "bear steepening",
        "bull_steepening": "bull steepening",
        "bear_flattening": "bear flattening",
        "bull_flattening": "bull flattening",
    }.get(code, "")

    summary_text = {
        "bear_steepening": "둘 다 상승 · 30Y 상승폭이 더 큼",
        "bull_steepening": "둘 다 하락 · 2Y 하락폭이 더 큼",
        "bear_flattening": "둘 다 상승 · 2Y 상승폭이 더 큼",
        "bull_flattening": "둘 다 하락 · 30Y 하락폭이 더 큼",
        "long_up_short_down": "30Y 상승 · 2Y 하락",
        "long_down_short_up": "30Y 하락 · 2Y 상승",
        "steepening": "장·단기 금리차 확대",
        "flattening": "장·단기 금리차 축소",
        "no_clear_curve_move": "장·단기 금리차 변화 작음",
    }.get(code, str(curve.get("text") or "현재 움직임 확인"))

    return (
        '<section class="rr-panel">'
        '<div class="rr-section-title"><h2>단기·장기 금리 관계</h2><span>최근 약 1개월</span></div>'
        '<div class="rr-curve-pair">'
        f'<div><span>2Y</span><strong>{escape(_direction(short))} {escape(_pct_change_from_bp(short))}</strong></div>'
        f'<div><span>30Y</span><strong>{escape(_direction(long))} {escape(_pct_change_from_bp(long))}</strong></div>'
        '</div>'
        f'<div class="rr-curve-summary"><strong>{escape(summary_text)}</strong></div>'
        '</section>'
    )


def render_rate_reference_cards_html(matrix: pd.DataFrame | None,
                                     aux_df: pd.DataFrame | None) -> str:
    """장기금리 해석에서 함께 보는 두 지표를 줄글 대신 카드로 보여준다."""
    cards: list[str] = []

    be = _row(aux_df, "BREAKEVEN")
    if be is not None:
        change_raw = be.get("change_1m")
        cards.append(
            '<article class="rr-metric-card rr-domain-rate">'
            '<div class="rr-metric-name">10Y Breakeven</div>'
            '<div class="rr-metric-subtitle">일반·물가연동 국채금리 차이</div>'
            f'<div class="rr-metric-value">{escape(fmt_value(be.get("latest_value"), str(be.get("value_unit", ""))))}</div>'
            f'<div class="rr-metric-change">{escape(_direction(change_raw))} {escape(fmt_change(change_raw, str(be.get("change_unit", ""))))} <span>최근 약 1개월</span></div>'
            '</article>'
        )

    term = _row(aux_df, "TERMPREM")
    if term is not None:
        change_raw = term.get("change_1m")
        cards.append(
            '<article class="rr-metric-card rr-domain-rate">'
            '<div class="rr-metric-name">10Y Term Premium</div>'
            '<div class="rr-metric-subtitle">장기채 추가 보상 추정치</div>'
            f'<div class="rr-metric-value">{escape(fmt_value(term.get("latest_value"), str(term.get("value_unit", ""))))}</div>'
            f'<div class="rr-metric-change">{escape(_direction(change_raw))} {escape(fmt_change(change_raw, str(term.get("change_unit", ""))))} <span>최근 약 1개월</span></div>'
            '</article>'
        )

    if not cards:
        return '<div class="rr-empty">장기금리 참고 지표를 확인할 수 없습니다.</div>'
    return '<div class="rr-metric-grid rr-reference-grid">' + ''.join(cards) + '</div>'


def render_rate_change_table_html(summary: dict | None) -> str:
    """30년 금리 구성의 1개월·3개월 숫자를 모바일 3열 표로 보여준다."""
    s = summary or {}
    if s.get("status") != "ok":
        return '<div class="rr-empty">30년 금리 비교표를 만들 자료가 없습니다.</div>'
    primary = s.get("primary") or {}
    context = s.get("context") or {}
    rows = [
        ("30Y", primary.get("DGS30_change_bp"), context.get("DGS30_change_bp")),
        ("실질 30Y", primary.get("DFII30_change_bp"), context.get("DFII30_change_bp")),
        ("30Y 국채 금리 차이", primary.get("INFLCOMP30_change_bp"), context.get("INFLCOMP30_change_bp")),
    ]
    body = ''.join(
        '<tr>'
        f'<th>{escape(name)}</th>'
        f'<td>{escape(_pct_change_from_bp(one))}</td>'
        f'<td>{escape(_pct_change_from_bp(three))}</td>'
        '</tr>'
        for name, one, three in rows
    )
    return (
        '<div class="rr-table-wrap"><table class="rr-compact-table">'
        '<thead><tr><th>항목</th><th>1개월</th><th>3개월</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
    )


def render_rate_notes_html(summary: dict | None) -> str:
    """금리 탭의 오해 방지 설명만 짧은 정보 박스로 남긴다."""
    s = summary or {}
    if s.get("status") != "ok":
        return '<div class="rr-info-box">30년 금리 구성 자료가 정상 수집되면 같은 만기의 일반·물가연동 국채를 비교합니다.</div>'
    return (
        '<div class="rr-info-box">'
        '<strong>읽는 법</strong><br>'
        '30Y와 실질 30Y는 같은 만기입니다. 국채 금리 차이에는 물가 기대뿐 아니라 물가 위험과 채권 수요·공급 영향도 섞일 수 있습니다. '
        'Term Premium은 별도 참고 지표이며 30년 금리 구성에 더하는 항목이 아닙니다.'
        '</div>'
    )
