"""'오늘의 해석' 마크다운 렌더링.

판정 로직은 interpretation_engine에 있고, 이 모듈은 저장된 결과를 쉬운 말로 보여준다.
"""
from __future__ import annotations

import pandas as pd

from .display_text import (AUX_ROLES, aux_name, axis_name, core_name,
                           plain_language, state_name)
from .formatting import fmt_change as fmt_change_value

_DIR_MARK = {
    "상승": "▲ 오르는 중",
    "하락": "▼ 내리는 중",
    "보합": "· 뚜렷한 변화 없음",
    "판정불가": "— 확인 불가",
}
_FRESHNESS = {
    "normal": "최신",
    "delayed": "업데이트가 조금 늦음",
    "stale": "오래된 자료 · 현재 해석에서 제외",
}

_VOL_CREDIT_LABELS = {
    "A": "큰 변화 없음",
    "B": "주식시장 흔들림이 먼저 움직임",
    "C": "회사채 쪽만 움직임",
    "D": "주식시장과 회사채가 함께 움직임",
    "E": "주식시장은 진정 · 회사채 변화는 이어짐",
}
_VOL_CREDIT_LABEL_TEXT = {
    "뚜렷한 변화 없음": "큰 변화 없음",
    "변동성 선행": "주식시장 흔들림이 먼저 움직임",
    "신용 단독 변화": "회사채 쪽만 움직임",
    "변동성·신용 동반": "주식시장과 회사채가 함께 움직임",
    "변동성 진정·신용 변화 지속": "주식시장은 진정 · 회사채 변화는 이어짐",
}
_RATE_RESULTS = {
    "변화 없음": "큰 변화 없음",
    "상승 방향": "상승 쪽",
    "하락 방향": "하락 쪽",
    "혼합 방향": "서로 다른 방향",
}


def _fmt_change(row) -> str:
    direction = row.get("direction", "")
    if direction in ("보합", "판정불가") or row.get("change_1m") is None or pd.isna(row.get("change_1m")):
        return _DIR_MARK.get(direction, direction)
    return f"{_DIR_MARK.get(direction, direction)} ({fmt_change_value(row.get('change_1m'), row.get('change_unit', ''))})"


def _aux_section(aux_df: pd.DataFrame) -> str:
    if aux_df is None or aux_df.empty:
        return (
            "### 원인을 구분할 때 쓰는 확인 지표\n"
            "현재 캐시에는 확인 지표 데이터가 없습니다. 핵심 6개 지표는 정상적으로 볼 수 있지만, "
            "세부 원인 구분은 다음 성공 배치에서 보완됩니다.\n"
        )

    lines = [
        "### 원인을 구분할 때 같이 보는 지표",
        "아래 3개는 시장 상태를 점수에 더하지 않습니다. 여러 가능한 원인 중 무엇이 현재 데이터와 더 잘 맞는지 구분할 때만 씁니다.",
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
        date = row.get("latest_date")
        fetch_status = str(row.get("fetch_status", "ok"))
        error = row.get("error")

        if row.get("latest_value") is None or pd.isna(row.get("latest_value")):
            msg = f"- **{aux_name(key)}**: 이번 캐시에서 값을 불러오지 못했습니다."
            if error and str(error) not in ("None", "nan", "missing"):
                msg += " 데이터 상태 탭에서 수집 오류를 확인할 수 있습니다."
            lines.append(msg)
            role = AUX_ROLES.get(key)
            if role:
                lines.append(f"  - 이 지표를 쓰는 이유: {role}")
            continue

        status_note = ""
        if fetch_status == "carried_forward":
            status_note = " · 이번 수집 실패로 직전 성공값 사용"
        elif fetch_status == "failed":
            status_note = " · 이번 수집 실패"

        date_text = f"관측일 {date}" if date else "관측일 확인 불가"
        lines.append(f"- **{aux_name(key)}**: {_fmt_change(row)} · {fresh}{status_note} · {date_text}")
        role = AUX_ROLES.get(key)
        if role:
            lines.append(f"  - 이 지표를 쓰는 이유: {role}")
    return "\n".join(lines)


def _axes_section(axes: dict) -> str:
    if not axes:
        return "현재 저장된 데이터로는 여러 지표를 같이 본 결과를 계산할 수 없습니다."

    vc = axes["vol_credit"]
    cy = axes["cycle"]
    rt = axes["rate"]
    changed = [axis_name(x) for x in (axes.get("changed_axes") or [])]
    base = [axis_name(x) for x in (axes.get("base_axes") or [])]

    members = rt.get("members", {})
    direction_text = {"상승": "오르는 중", "하락": "내리는 중", "기본": "큰 움직임 없음"}
    member_text = " · ".join(
        f"{core_name(key, short=True)} {direction_text.get(members.get(key, '기본'), members.get(key, '기본'))}"
        for key in ("DGS30", "DGS2", "DFII10")
    )

    vc_label = _VOL_CREDIT_LABELS.get(vc.get("state"), _VOL_CREDIT_LABEL_TEXT.get(vc.get("label"), plain_language(vc.get("label", ""))))
    rate_result = _RATE_RESULTS.get(rt.get("result"), rt.get("result"))
    changed_count = axes.get("changed_count")
    if changed_count is None:
        changed_count = len(axes.get("changed_axes") or [])

    lines = [
        "### 여러 지표를 같이 보면",
        f"**현재 3개 영역 중 {changed_count}개에서 평소와 다른 움직임이 보입니다.**",
        "",
    ]
    if changed:
        lines.append(f"- 평소와 다른 움직임이 보이는 곳: **{' · '.join(changed)}**")
    if base:
        lines.append(f"- 큰 움직임이 없는 곳: {' · '.join(base)}")
    lines += [
        "",
        f"#### {axis_name('변동성·신용')} — {vc_label}",
        plain_language(vc.get("note", "")),
        f"- {core_name('VIX', short=True)}: {state_name(vc.get('vix_state'), key='VIX')} · "
        f"{core_name('HYOAS', short=True)}: {state_name(vc.get('hy_state'), key='HYOAS')}",
        "",
        f"#### 경기 흐름 — {state_name(cy.get('state'), plain_language(cy.get('label', '확인 불가')), key='T10Y3M')}",
        "10년 금리와 3개월 금리의 현재 관계입니다. 지금 주식시장이 불안한지와는 따로 봅니다.",
        "",
        f"#### 금리 움직임 — {rate_result}",
        member_text,
        "",
        "> 이 세 영역은 여러 지표를 보기 쉽게 묶은 내부 참고 방식입니다. 위험확률이나 투자 신호가 아닙니다.",
    ]
    return "\n".join(lines)


def _explanation_map(reading: dict) -> dict[str, str]:
    return {str(x["id"]): plain_language(str(x["text"])) for x in reading.get("explanations", [])}


def _reading_block(reading: dict) -> str:
    explanations = _explanation_map(reading)
    supported = set(reading.get("supported_ids") or [])
    weakened = set(reading.get("weakened_ids") or [])

    lines = [
        f"## {plain_language(reading['label'])}",
        "",
        "### 지금 보이는 모습",
        plain_language(reading["observed"]),
        "",
        "### 이렇게 볼 수 있습니다",
    ]
    for eid, text in explanations.items():
        if eid in supported:
            tag = "**지금 데이터와 잘 맞음**"
        elif eid in weakened:
            tag = "지금 데이터와 덜 맞음"
        else:
            tag = "추가 확인 중"
        lines.append(f"- [{tag}] {text}")

    lines += ["", "### 같이 본 지표는 지금 어떤가"]
    for check in reading.get("checks", []):
        freshness = check.get("freshness", "normal")
        ftxt = ""
        if freshness == "delayed":
            ftxt = " · ⚠️ 업데이트가 조금 늦음"
        elif freshness == "stale":
            ftxt = " · ⚠️ 오래된 자료, 현재 판단에서 제외"
        lines.append(
            f"- **{plain_language(check['label'])}** [{_DIR_MARK.get(check['direction'], check['direction'])}]{ftxt}: {plain_language(check['text'])}"
        )
        branches = check.get("branches") or {}
        alternatives = [
            (direction, text)
            for direction, text in branches.items()
            if direction != check.get("direction")
        ]
        if alternatives:
            lines.append("  - **결과가 달라지면**")
            for direction, text in alternatives:
                lines.append(f"    - **{_DIR_MARK.get(direction, direction)}:** {plain_language(text)}")

    if supported:
        lines += ["", "### 지금 데이터와 더 잘 맞는 설명"]
        for eid in supported:
            if eid in explanations:
                lines.append(f"- {explanations[eid]}")
    else:
        lines += [
            "",
            "### 지금 데이터와 더 잘 맞는 설명",
            "현재 확인 지표만으로 한 설명이 뚜렷하게 앞선다고 보기 어렵습니다.",
        ]

    if weakened:
        lines += ["", "### 지금 데이터와 덜 맞는 설명"]
        for eid in weakened:
            if eid in explanations:
                lines.append(f"- {explanations[eid]}")

    if reading.get("conflict"):
        lines += ["", "### 서로 다른 설명을 가리키는 부분", f"⚠️ {plain_language(reading['conflict'])}"]

    lines += ["", "### 아직 정하기 어려운 부분", plain_language(reading["uncertainty"])]
    return "\n".join(lines)


def render_today_markdown(dq: dict, aux_df: pd.DataFrame | None) -> str:
    dq = dq or {}
    parts = [
        "# 오늘의 해석",
        "",
        "오늘 데이터에서 **어느 부분이 움직였는지**, 그리고 함께 본 지표가 여러 가능한 설명 중 무엇과 더 잘 맞는지 보여줍니다.",
        "",
        _axes_section(dq.get("axes")),
        "",
        _aux_section(aux_df),
        "",
        "# 오늘 눈에 띄는 지표 조합",
    ]

    readings = dq.get("readings") or []
    if not readings:
        parts.append(
            "현재 정의된 조합 중 따로 설명할 만한 패턴이 잡히지 않았습니다. 시장에 변화가 전혀 없다는 뜻은 아닙니다."
        )
    else:
        for reading in readings:
            parts += ["", _reading_block(reading), "", "---"]

    parts += [
        "",
        "*이 해석은 지표를 같이 읽기 위한 참고 정보입니다. 매수·매도나 단일 위험점수를 제시하지 않습니다.*",
    ]
    return "\n".join(parts)
