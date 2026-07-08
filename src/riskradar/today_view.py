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
    "확인 불가": "— 확인 불가",
    "판정불가": "— 확인 불가",
}
_FRESHNESS = {
    "normal": "최신",
    "delayed": "업데이트가 조금 늦음",
    "stale": "오래된 자료 · 현재 해석에서 제외",
}

_VOL_CREDIT_LABELS = {
    "A": "큰 변화 없음",
    "B": "주식시장 쪽만 움직임",
    "C": "회사채 쪽만 움직임",
    "D": "주식시장과 회사채가 함께 움직임",
    "E": "주식시장은 진정 · 회사채 변화는 이어짐",
}
_VOL_CREDIT_LABEL_TEXT = {
    "뚜렷한 변화 없음": "큰 변화 없음",
    "변동성 선행": "주식시장 쪽만 움직임",
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
    if direction in ("보합", "확인 불가") or row.get("change_1m") is None or pd.isna(row.get("change_1m")):
        return _DIR_MARK.get(direction, direction)
    return f"{_DIR_MARK.get(direction, direction)} ({fmt_change_value(row.get('change_1m'), row.get('change_unit', ''))})"


_AUX_GROUPS = [
    ("10년 구간 참고 맥락", ("BREAKEVEN", "TERMPREM")),
    ("기업 신용 부담이 어디에서 나타나나", ("BBBOAS", "AOAS")),
    ("단기 자금시장도 영향을 받고 있나", ("CPSPREAD",)),
    ("외부 참고 지표", ("NFCI", "STLFSI")),
]


def _reference_level_text(key: str, row) -> str:
    """외부 참고 지표지표의 현재 수준을 자기 역사에서 쉬운 말로 표시."""
    pct = row.get("level_pct")
    if pct is None or pd.isna(pct):
        return "현재 수준 비교 불가"
    pct = float(pct)
    if 40.0 <= pct <= 60.0:
        return "평소 범위"
    if key == "NFCI":
        return "평소보다 자금 사정이 어려워지는 쪽" if pct > 60.0 else "평소보다 자금 사정이 느슨한 쪽"
    if key == "STLFSI":
        return "평소보다 시장 불안이 높은 쪽" if pct > 60.0 else "평소보다 시장 불안이 낮은 쪽"
    return "평소보다 높은 쪽" if pct > 60.0 else "평소보다 낮은 쪽"


def _aux_row_lines(row, key: str | None = None) -> list[str]:
    key = key or str(row.get("key", ""))
    fresh_raw = str(row.get("staleness_label", "normal"))
    fresh = _FRESHNESS.get(fresh_raw, fresh_raw)
    date = row.get("latest_date")
    fetch_status = str(row.get("fetch_status", "ok"))
    error = row.get("error")

    has_latest_value = "latest_value" in row.index
    if has_latest_value and (row.get("latest_value") is None or pd.isna(row.get("latest_value"))):
        msg = f"- **{aux_name(key)}**: 이번 캐시에서 값을 불러오지 못했습니다."
        if error and str(error) not in ("None", "nan", "missing"):
            msg += " 데이터 상태 탭에서 수집 오류를 확인할 수 있습니다."
        lines = [msg]
        role = AUX_ROLES.get(key)
        if role:
            lines.append(f"  - 이 지표를 쓰는 이유: {role}")
        return lines

    status_note = ""
    if fetch_status == "carried_forward":
        status_note = " · 이번 수집 실패로 직전 성공값 사용"
    elif fetch_status == "failed":
        status_note = " · 이번 수집 실패"

    date_text = f"관측일 {date}" if date else "관측일 확인 불가"
    if key in {"NFCI", "STLFSI"}:
        summary = f"{_reference_level_text(key, row)} · {_fmt_change(row)}"
    else:
        summary = _fmt_change(row)
    lines = [f"- **{aux_name(key)}**: {summary} · {fresh}{status_note} · {date_text}"]
    role = AUX_ROLES.get(key)
    if role:
        lines.append(f"  - 이 지표를 쓰는 이유: {role}")
    return lines


def _aux_section(aux_df: pd.DataFrame) -> str:
    if aux_df is None or aux_df.empty:
        return (
            "### 원인을 구분할 때 쓰는 확인 지표\n"
            "현재 캐시에는 확인 지표 데이터가 없습니다. 핵심 6개 지표는 정상적으로 볼 수 있지만, "
            "세부 원인 구분은 다음 성공 배치에서 보완됩니다.\n"
        )

    lines = [
        "### 함께 보는 참고 지표",
        "함께 볼 지표는 10년 금리 구간의 별도 맥락, 회사채 부담이 나타나는 곳, 단기 자금시장 변화를 구분할 때 씁니다. 외부 참고 지표는 공식 종합 지표가 같은 방향인지 마지막에 확인합니다. 어느 쪽도 핵심 상태에 점수처럼 더하지 않습니다.",
        "",
    ]
    old_name_to_key = {
        "10Y Breakeven": "BREAKEVEN",
        "A OAS": "AOAS",
        "10Y Term Premium (KW)": "TERMPREM",
    }
    by_key = {}
    for _, row in aux_df.iterrows():
        key = str(row.get("key", ""))
        if not key or key == "nan":
            key = old_name_to_key.get(str(row.get("display_name", "")), "")
        if key:
            by_key[key] = row
    for title, keys in _AUX_GROUPS:
        present = [k for k in keys if k in by_key]
        if not present:
            continue
        lines += [f"#### {title}"]
        if title == "기업 신용 부담이 어디에서 나타나나":
            lines.append("핵심 지표인 신용등급이 낮은 기업의 추가 금리(HY OAS)와 함께 봅니다.")
        elif title == "외부 참고 지표":
            lines.append("아래 지표는 RiskRadar 해석 엔진에 넣지 않고, 공식 기관의 종합 지표가 같은 방향을 가리키는지만 참고합니다.")
        for key in present:
            lines.extend(_aux_row_lines(by_key[key], key))
        lines.append("")
    return "\n".join(lines)


def _credit_episode_section(dq: dict) -> str:
    credit = (dq or {}).get("credit_episode") or {}
    current = credit.get("current") or {}
    episode = current.get("episode") or {}
    nodes = current.get("nodes") or {}
    lens = credit.get("lens") or {}
    vix = credit.get("vix_context") or {}
    state = str(episode.get("state", "none"))
    if not current:
        return "### 기업 신용 변화 흐름\n현재 캐시에는 기업 신용 범위·지속 결과가 없습니다."

    lines = [
        "### 기업 신용 변화 흐름",
        "이 부분은 누가 먼저였는지 추정하지 않고, **어느 시장에서 변화가 나타나고 무엇이 계속 이어지는지**를 봅니다.",
        "",
        f"- **변화 흐름 상태:** {episode.get('state_label', '현재 변화 흐름 없음')}",
        f"- **현재 변화 범위:** {current.get('scope_text', '확인 불가')}",
    ]
    if episode.get("started_at"):
        lines.append(f"- **현재 변화 흐름 시작:** {episode.get('started_at')} · 마지막 의미 있는 변화 {episode.get('last_meaningful_activity_at') or '확인 불가'}")
    if state == "dormant":
        lines.append("- **한동안 새 변화 없음의 의미:** 한동안 새 변화는 없지만 이전 변화가 완전히 사라졌다는 뜻은 아닙니다. 다른 시장에서 새 변화가 나타나면 별도의 변화 흐름으로 구분합니다.")
    if episode.get("prior_residual_nodes"):
        lines.append("- **이전 변화의 영향:** 이전 변화가 완전히 사라지기 전에 새 변화가 시작됐습니다.")

    lines += ["", "#### 실제 시장별 현재 상태"]
    for key in ("HY", "BBB", "A", "CP"):
        row = nodes.get(key) or {}
        if not row.get("available"):
            lines.append(f"- **{key}:** 확인 불가")
            continue
        extra = []
        if row.get("confirmed_at"):
            extra.append(f"상승 변화 확인 {row.get('confirmed_at')}")
        if row.get("residual_change") is not None:
            extra.append(f"기준선 대비 {row.get('residual_change') / 100.0:+.2f}%p 남음")
        suffix = " · " + " · ".join(extra) if extra else ""
        lines.append(f"- **{row.get('name', key)}:** {row.get('state_label', '확인 불가')}{suffix}")

    lines += [
        "",
        "#### 저신용 기업 쪽 상대 부담 해석 기준",
        f"- {lens.get('label', '확인 불가')}",
    ]
    if lens.get("latest_value_bp") is not None:
        lines.append(f"- HY-BBB 차이: {lens.get('latest_value_bp') / 100.0:.2f}%p · 약 1개월 {lens.get('change_1m_bp', 0.0) / 100.0:+.2f}%p")
    cp_calendar = current.get("cp_calendar_context") or {}
    if cp_calendar.get("year_end"):
        lines += ["", "#### 단기자금 캘린더 진단", f"- {cp_calendar.get('note')}"]
    if vix.get("available"):
        lines += [
            "",
            "#### 주식시장 맥락",
            f"- {vix.get('onset', '확인 불가')}",
            f"- {vix.get('current', '확인 불가')}",
        ]
    lines += [
        "",
        "> HY-BBB 차이는 별도 시장이 아니라 HY와 BBB의 상대적 차이를 보는 해석 기준입니다. 기업 신용 범위 엔진에서 별도 시장으로 두 번 세지 않습니다.",
    ]
    return "\n".join(lines)



def render_credit_episode_markdown(data_quality: dict | None) -> str:
    """현재 기업 신용 범위·지속 결과만 독립적으로 렌더링한다."""
    return plain_language(_credit_episode_section(data_quality or {}))

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


def render_today_summary_markdown(dq: dict, aux_df: pd.DataFrame | None = None) -> str:
    """오늘의 해석 탭 첫 화면용 핵심 요약.

    전체 확인 근거와 결과별 대안은 기존 ``render_today_markdown``에 남겨 두고,
    첫 화면에는 현재 변화 범위·움직이는 영역·주요 조합만 압축해서 보여준다.
    """
    dq = dq or {}
    lines = [
        "# 오늘의 해석",
        "",
        "지금 무엇이 움직이는지와 가장 중요한 조합만 먼저 보여줍니다.",
    ]

    credit = dq.get("credit_episode") or {}
    current = credit.get("current") or {}
    episode = current.get("episode") or {}
    lens = credit.get("lens") or {}
    if current:
        lines += [
            "",
            "## 기업 신용",
            f"- **변화 흐름:** {episode.get('state_label', '현재 변화 흐름 없음')}",
            f"- **변화 범위:** {current.get('scope_text', '확인 불가')}",
        ]
        lens_label = str(lens.get("label") or "")
        if lens_label and lens_label != "확인 불가":
            lines.append(f"- **저신용 기업 쪽 상대 부담:** {lens_label}")

    axes = dq.get("axes") or {}
    if axes:
        changed = [axis_name(x) for x in (axes.get("changed_axes") or [])]
        base = [axis_name(x) for x in (axes.get("base_axes") or [])]
        changed_count = axes.get("changed_count")
        if changed_count is None:
            changed_count = len(changed)
        lines += [
            "",
            "## 시장 전체",
            f"- **3개 영역 중 {changed_count}개**에서 평소와 다른 움직임이 보입니다.",
        ]
        if changed:
            lines.append(f"- 움직이는 곳: **{' · '.join(changed)}**")
        if base:
            lines.append(f"- 큰 움직임이 없는 곳: {' · '.join(base)}")

    readings = dq.get("readings") or []
    lines += ["", "## 눈에 띄는 조합"]
    if not readings:
        lines.append("현재 정의된 조합 중 따로 설명할 만한 패턴은 잡히지 않았습니다.")
    else:
        for reading in readings[:2]:
            label = plain_language(str(reading.get("label", "확인 불가")))
            observed = plain_language(str(reading.get("observed", "")))
            lines.append(f"- **{label}:** {observed}")
            explanations = _explanation_map(reading)
            supported = set(reading.get("supported_ids") or [])
            best = [text for eid, text in explanations.items() if eid in supported]
            if best:
                lines.append(f"  - 지금 데이터와 더 잘 맞는 설명: {best[0]}")

    lines += [
        "",
        "> 전체 근거, 함께 볼 지표 결과, 결과가 달라질 때의 해석은 아래 아코디언에서 볼 수 있습니다.",
    ]
    return "\n".join(lines)


def render_today_markdown(dq: dict, aux_df: pd.DataFrame | None) -> str:
    dq = dq or {}
    parts = [
        "# 오늘의 해석",
        "",
        "오늘 데이터에서 **어느 부분이 움직였는지**, 그리고 함께 본 지표가 여러 가능한 설명 중 무엇과 더 잘 맞는지 보여줍니다.",
        "",
        _credit_episode_section(dq),
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
