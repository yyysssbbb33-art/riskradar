"""'오늘의 해석' 마크다운 렌더링.

판정 로직은 interpretation_engine에 있고, 이 모듈은 저장된 결과를 사용자에게 쉽게 보여준다.
"""
from __future__ import annotations

import pandas as pd

from .display_text import AUX_ROLES, aux_name, core_name
from .state_rules import LABELS

_DIR_MARK = {
    "상승": "▲ 상승",
    "하락": "▼ 하락",
    "보합": "· 뚜렷한 변화 없음",
    "판정불가": "— 판정불가",
}
_FRESHNESS = {
    "normal": "최신",
    "delayed": "업데이트 지연",
    "stale": "오래된 자료 · 해석 집계 제외",
}


def _fmt_change(row) -> str:
    direction = row.get("direction", "")
    if direction in ("보합", "판정불가") or row.get("change_1m") is None or pd.isna(row.get("change_1m")):
        return _DIR_MARK.get(direction, direction)
    unit = row.get("change_unit", "")
    return f"{_DIR_MARK.get(direction, direction)} ({row['change_1m']:+.0f}{unit})"


def _aux_section(aux_df: pd.DataFrame) -> str:
    if aux_df is None or aux_df.empty:
        return "### 원인 확인용 보조지표\n보조지표 데이터가 아직 없습니다.\n"

    lines = [
        "### 원인 확인용 보조지표",
        "핵심 3축에는 넣지 않고, 관찰된 조합의 원인을 구분할 때만 사용합니다.",
        "",
    ]
    for _, row in aux_df.iterrows():
        key = str(row.get("key", ""))
        if not key:
            raw_name = str(row.get("display_name", ""))
            key = {
                "10Y Breakeven": "BREAKEVEN",
                "IG OAS": "IGOAS",
                "10Y Term Premium (KW)": "TERMPREM",
            }.get(raw_name, raw_name)
        fresh_raw = str(row.get("staleness_label", "normal"))
        fresh = _FRESHNESS.get(fresh_raw, fresh_raw)
        date = row.get("latest_date") or "관측일 없음"
        lines.append(f"- **{aux_name(key)}**: {_fmt_change(row)} · {fresh} · 관측일 {date}")
        role = AUX_ROLES.get(key)
        if role:
            lines.append(f"  - 용도: {role}")
    return "\n".join(lines)


def _axes_section(axes: dict) -> str:
    if not axes:
        return "축 조망 데이터가 아직 없습니다. 다음 배치 후 표시됩니다."

    vc = axes["vol_credit"]
    cy = axes["cycle"]
    rt = axes["rate"]
    changed = axes.get("changed_axes") or []
    base = axes.get("base_axes") or []

    members = rt.get("members", {})
    member_text = " · ".join(
        f"{core_name(key, short=True)} {members.get(key, '기본')}"
        for key in ("DGS30", "DGS2", "DFII10")
    )

    lines = [
        "### 현재 복합 조망",
        f"**{axes['summary_line']}**",
        "",
    ]
    if changed:
        lines.append(f"- 기준상 변화 축: **{' · '.join(changed)}**")
    if base:
        lines.append(f"- 기본 상태 축: {' · '.join(base)}")
    lines += [
        "",
        f"#### 변동성·신용 — {vc['label']}",
        f"{vc['note']}",
        f"- VIX 원래 상태: {LABELS.get(vc.get('vix_state'), vc.get('vix_state', '?'))} · "
        f"HY OAS 원래 상태: {LABELS.get(vc.get('hy_state'), vc.get('hy_state', '?'))}",
        "",
        f"#### 경기 사이클 — {cy['label']}",
        "10년-3개월 금리차의 현재 경로 상태입니다. 현재 시장 공포와는 별개의 축입니다.",
        "",
        f"#### 금리 방향 — {rt['result']}",
        member_text,
        "",
        f"> {axes.get('disclaimer', '')}",
    ]
    return "\n".join(lines)


def _explanation_map(reading: dict) -> dict[str, str]:
    return {str(x["id"]): str(x["text"]) for x in reading.get("explanations", [])}


def _reading_block(reading: dict) -> str:
    explanations = _explanation_map(reading)
    supported = set(reading.get("supported_ids") or [])
    weakened = set(reading.get("weakened_ids") or [])

    lines = [
        f"## {reading['label']}",
        "",
        "### 관찰된 사실",
        reading["observed"],
        "",
        "### 일반적으로 가능한 설명",
    ]
    for eid, text in explanations.items():
        if eid in supported:
            tag = "**현재 데이터가 지지**"
        elif eid in weakened:
            tag = "현재 데이터가 약화"
        else:
            tag = "확인 중"
        lines.append(f"- [{tag}] {text}")

    lines += ["", "### 추가 확인 결과"]
    for check in reading.get("checks", []):
        freshness = check.get("freshness", "normal")
        ftxt = ""
        if freshness == "delayed":
            ftxt = " · ⚠️ 업데이트 지연"
        elif freshness == "stale":
            ftxt = " · ⚠️ 오래된 자료, 집계 제외"
        lines.append(
            f"- **{check['label']}** [{check['direction']}]{ftxt}: {check['text']}"
        )

    if supported:
        lines += ["", "### 현재 상대적으로 더 잘 맞는 설명"]
        for eid in supported:
            if eid in explanations:
                lines.append(f"- {explanations[eid]}")
    else:
        lines += [
            "",
            "### 현재 상대적으로 더 잘 맞는 설명",
            "현재 확인지표만으로 한 설명이 뚜렷하게 우세하다고 보기 어렵습니다.",
        ]

    if weakened:
        lines += ["", "### 반대 증거 · 약해지는 설명"]
        for eid in weakened:
            if eid in explanations:
                lines.append(f"- {explanations[eid]}")

    if reading.get("conflict"):
        lines += ["", "### 결과가 엇갈리는 부분", f"⚠️ {reading['conflict']}"]

    lines += ["", "### 아직 결정하기 어려운 부분", reading["uncertainty"]]
    return "\n".join(lines)


def render_today_markdown(dq: dict, aux_df: pd.DataFrame | None) -> str:
    dq = dq or {}
    parts = [
        "# 오늘의 해석",
        "",
        "오늘 데이터에서 **어떤 축과 조합이 움직였는지**, 그리고 보조지표가 여러 가능한 설명 중 무엇을 지지하거나 약화하는지 보여줍니다.",
        "",
        _axes_section(dq.get("axes")),
        "",
        _aux_section(aux_df),
        "",
        "# 오늘 관찰된 주요 조합",
    ]

    readings = dq.get("readings") or []
    if not readings:
        parts.append(
            "현재 정의된 조합 중 뚜렷하게 관찰된 것이 없습니다. 이것은 시장에 변화가 없다는 뜻이 아니라, "
            "현재 조합 규칙에서 별도로 설명할 패턴이 잡히지 않았다는 뜻입니다."
        )
    else:
        for reading in readings:
            parts += ["", _reading_block(reading), "", "---"]

    parts += [
        "",
        "*해석은 규칙 기반 참고 정보입니다. 지표 관계를 설명하지만 매수·매도, 단일 위험점수, 투자행동 판단을 제공하지 않습니다.*",
    ]
    return "\n".join(parts)
