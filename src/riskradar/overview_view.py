"""v0.7.1 변화 중심 첫 화면과 모바일 카드 렌더링.

판정은 만들지 않는다. v0.6.2가 저장한 권위 있는 decision snapshot/diff와
현재 데이터 산출물을 사용자에게 빠르게 읽히는 형태로만 바꾼다.
"""
from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd

from . import aux_config as AC
from . import config as C
from .display_text import aux_name, axis_name, core_name, plain_language, state_name
from .formatting import fmt_change, fmt_value


_STATE_SYMBOLS = {
    "early_change": "◌",
    "newly_rising": "↑",
    "rising_persistent": "●",
    "retracing": "↘",
    "normalized": "✓",
    "normal": "○",
    "watch": "↑",
    "stress": "●",
    "rise_watch": "↑",
    "rate_shock": "●",
}

_CREDIT_NAMES = {
    "HY": "신용등급이 낮은 기업(HY)",
    "BBB": "투자등급 경계 기업(BBB)",
    "A": "A등급 기업(A)",
    "CP": "단기 기업자금시장(CP)",
}


def _text(value: Any, default: str = "확인 불가") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text in {"", "None", "nan"} else text


def _core_noteworthy(row: pd.Series) -> bool:
    key = str(row.get("key", ""))
    code = str(row.get("state_code", ""))
    if bool(row.get("drop_flag", False)):
        return True
    if key == "VIX":
        return code in {"watch", "stress"}
    if key == "HYOAS":
        return code in {"watch", "stress"}
    if key == "T10Y3M":
        return code not in {"", "normal"}
    if key in {"DGS30", "DGS2", "DFII10"}:
        return code in {"rise_watch", "rate_shock"}
    return False


def _sparkline(values: list[float]) -> str:
    vals = [float(v) for v in values if pd.notna(v)]
    if not vals:
        return ""
    vals = vals[-24:]
    if len(vals) == 1 or max(vals) == min(vals):
        return "▅" * min(12, len(vals))
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(vals), max(vals)
    return "".join(blocks[round((v - lo) / (hi - lo) * (len(blocks) - 1))] for v in vals)


def _state_symbol(key: str, state_code: str, drop_flag: bool = False) -> str:
    if drop_flag:
        return "↓"
    if state_code in _STATE_SYMBOLS:
        return _STATE_SYMBOLS[state_code]
    if key == "VIX" and state_code in {"calm", "normal"}:
        return "○"
    if key == "HYOAS" and state_code in {"calm", "neutral"}:
        return "○"
    if state_code in {"stable", "base"}:
        return "○"
    return "·"


def render_core_cards_html(matrix: pd.DataFrame, chart_data: pd.DataFrame, *, changes_only: bool) -> str:
    if matrix is None or matrix.empty:
        return '<div class="rr-empty">핵심 지표 데이터를 읽을 수 없습니다.</div>'
    chart_data = chart_data if isinstance(chart_data, pd.DataFrame) else pd.DataFrame()
    cards: list[str] = []
    hidden_count = 0
    for _, row in matrix.iterrows():
        if changes_only and not _core_noteworthy(row):
            hidden_count += 1
            continue
        key = str(row.get("key", ""))
        code = str(row.get("state_code", ""))
        drop = bool(row.get("drop_flag", False))
        label = state_name(code, str(row.get("state_label", "")), drop=drop, key=key)
        symbol = _state_symbol(key, code, drop)
        vals: list[float] = []
        if not chart_data.empty and {"key", "date", "value"}.issubset(chart_data.columns):
            d = chart_data.loc[chart_data["key"].astype(str) == key].sort_values("date")
            vals = pd.to_numeric(d["value"], errors="coerce").dropna().tail(24).tolist()
        spark = _sparkline(vals)
        cards.append(
            '<article class="rr-card">'
            f'<div class="rr-card-name">{escape(core_name(key))}</div>'
            f'<div class="rr-card-state"><span>{escape(symbol)}</span> {escape(label)}</div>'
            '<div class="rr-card-grid">'
            f'<div><small>현재</small><strong>{escape(fmt_value(row.get("latest_value"), row.get("value_unit", "")))}</strong></div>'
            f'<div><small>약 1개월</small><strong>{escape(fmt_change(row.get("change_20obs"), row.get("change_unit", "")))}</strong></div>'
            f'<div><small>약 3개월</small><strong>{escape(fmt_change(row.get("change_60obs"), row.get("change_unit", "")))}</strong></div>'
            '</div>'
            f'<div class="rr-spark" aria-label="최근 흐름">{escape(spark or "최근 흐름 확인 불가")}</div>'
            f'<div class="rr-observed">관측일 {escape(_text(row.get("latest_observed_date"), "확인 불가"))}</div>'
            '</article>'
        )
    if not cards:
        return (
            '<div class="rr-empty"><strong>새로 눈에 띄는 핵심 지표 변화가 없습니다.</strong><br>'
            '아래의 전체 보기로 바꾸면 모든 핵심 지표를 확인할 수 있습니다.</div>'
        )
    tail = ""
    if changes_only and hidden_count:
        tail = f'<div class="rr-muted">나머지 {hidden_count}개 핵심 지표에서는 현재 새로 눈에 띄는 변화가 없습니다.</div>'
    return '<div class="rr-card-grid-wrap">' + "".join(cards) + '</div>' + tail


def _event_name(section: str, key: str) -> str:
    if section == "core":
        return core_name(key)
    if section == "aux":
        return aux_name(key)
    if section == "credit_nodes":
        return _CREDIT_NAMES.get(key, key)
    if section == "credit_lens":
        return "HY-BBB 등급 차이"
    if section == "credit_episode":
        return "기업 신용 변화 흐름"
    return key


def _friendly_event(event: dict) -> str:
    section = str(event.get("section", ""))
    key = str(event.get("key", ""))
    name = _event_name(section, key)
    previous = event.get("previous")
    current = event.get("current")
    transition_type = str(event.get("transition_type", ""))
    if section in {"core", "aux", "credit_nodes", "credit_lens"} and previous is not None and current is not None:
        return f"**{name}**: {plain_language(str(previous))} → {plain_language(str(current))}"
    if section == "credit_episode":
        if transition_type == "observation_clock_transition":
            return "관측 기간이 지나면서 **기업 신용 변화 흐름**이 휴면 또는 종료 상태로 바뀌었습니다."
        return "**기업 신용 변화 흐름**의 상태 또는 변화 범위가 바뀌었습니다."
    return plain_language(str(event.get("message", "변화가 기록됐습니다.")))


def _is_change_center_event(event: dict) -> bool:
    """일반 사용자 변화센터에 노출할 사건인지 판정한다.

    권위 있는 decision diff와 운영 진단은 모든 aux를 보존한다. 여기서는
    일반 사용자에게 먼저 밀어줄 변화만 별도 표면 정책으로 거른다.
    """
    if str(event.get("section", "")) != "aux":
        return True
    return str(event.get("key", "")) in AC.AUX_CHANGE_CENTER_KEYS


def render_recent_changes_markdown(diff: dict | None) -> str:
    diff = diff or {}
    status = str(diff.get("status", ""))
    # 숨은 aux 사건이 표시 슬롯을 먹지 않도록 반드시 slice 전에 필터한다.
    market = [
        event for event in (diff.get("market_transitions") or [])
        if _is_change_center_event(event)
    ]
    data_events = [
        event for event in (diff.get("data_quality_transitions") or [])
        if _is_change_center_event(event)
    ]
    recovery = [
        event for event in (diff.get("recovery_gap_events") or [])
        if _is_change_center_event(event)
    ]
    boundaries = diff.get("schema_boundaries") or []

    lines = ["## 새로 달라진 점"]
    if not diff:
        lines.append("아직 이전 정상 데이터와 비교할 기록이 없습니다. 정상 데이터가 두 번 쌓이면 새로 달라진 점을 보여줍니다.")
        return "\n\n".join(lines)
    if status == "cold_start":
        lines.append("이번 데이터가 첫 기준 기록입니다. 다음 정상 데이터부터 새로 달라진 점을 비교합니다.")
        return "\n\n".join(lines)

    if market:
        lines += ["", "### 시장에서 새로 보이는 변화"]
        for event in market[:5]:
            lines.append(f"- {_friendly_event(event)}")
    else:
        lines += ["", "**새로 확인된 시장 변화는 없습니다.**"]

    if recovery:
        lines += ["", "### 자료 복구 뒤 확인된 변화"]
        for event in recovery[:3]:
            name = _event_name(str(event.get("section", "")), str(event.get("key", "")))
            lines.append(
                f"- **{name}** 자료가 다시 들어왔고 공백 이전과 상태가 달라졌습니다. "
                "자료가 비어 있던 기간 중 정확히 언제 달라졌는지는 확인할 수 없습니다."
            )
    if data_events:
        lines += ["", "### 데이터 확인 필요"]
        for event in data_events[:4]:
            name = _event_name(str(event.get("section", "")), str(event.get("key", "")))
            lines.append(f"- **{name}**의 데이터 상태가 바뀌었습니다. 시장 변화와 구분해서 봅니다.")
    if boundaries:
        lines += ["", "> 일부 기준이나 저장 형식이 바뀐 영역은 이번 비교에서 시장 변화로 보지 않았습니다."]
    return "\n".join(lines)


def _changed_axis_text(axes: dict) -> str:
    changed = [axis_name(x) for x in (axes.get("changed_axes") or [])]
    if not changed:
        return "세 영역에서 새로 두드러지는 움직임이 크지 않습니다."
    if len(changed) == 1:
        return f"시장 전체로는 **{changed[0]}**에서 평소와 다른 움직임이 보입니다."
    return f"시장 전체로는 **{' · '.join(changed)}**에서 평소와 다른 움직임이 보입니다."


def render_today_one_line_markdown(data_quality: dict | None) -> str:
    dq = data_quality or {}
    credit = dq.get("credit_episode") or {}
    current = credit.get("current") or {}
    episode = current.get("episode") or {}
    axes = dq.get("axes") or {}
    scope = _text(current.get("scope_text"), "")
    state = str(episode.get("state", "none"))
    if current and state not in {"none", "ended"} and scope:
        scope_clean = scope.rstrip(".。 ")
        first = f"기업 신용에서는 **{scope_clean}**."
    elif current:
        first = "기업 신용에서는 현재 뚜렷한 변화가 크지 않습니다."
    else:
        first = "기업 신용 상태는 현재 확인할 수 없습니다."
    second = _changed_axis_text(axes) if axes else "시장 전체 영역 비교는 현재 확인할 수 없습니다."
    return "# 현재 상황\n\n" + first + " " + second


def render_remaining_changes_markdown(decision_snapshot: dict | None, data_quality: dict | None) -> str:
    snap = decision_snapshot or {}
    credit_nodes = (((snap.get("credit") or {}).get("nodes")) or {})
    core = snap.get("core") or {}
    items: list[str] = []
    for node in ("HY", "BBB", "A", "CP"):
        row = credit_nodes.get(node) or {}
        if str(row.get("source_status", "unavailable")) != "ok":
            continue
        state = str(row.get("state", ""))
        if state in {"newly_rising", "rising_persistent", "retracing"} or bool(row.get("participant", False)):
            items.append(f"**{_CREDIT_NAMES[node]}**: {_text(row.get('state_label'))}")
    for key, row in core.items():
        if len(items) >= 4:
            break
        if key == "HYOAS" and any(node in credit_nodes for node in ("HY", "BBB", "A", "CP")):
            continue
        code = str(row.get("state_code", ""))
        drop = bool(row.get("drop_flag", False))
        fake = pd.Series({"key": key, "state_code": code, "drop_flag": drop})
        if _core_noteworthy(fake):
            items.append(f"**{core_name(key)}**: {_text(row.get('state_label'))}")
    lines = ["## 계속 이어지는 변화"]
    if items:
        lines.extend(f"- {x}" for x in items[:4])
    else:
        lines.append("현재 계속 이어진다고 볼 만한 뚜렷한 변화는 많지 않습니다.")
    return "\n".join(lines)


def render_next_checks_markdown(data_quality: dict | None, decision_snapshot: dict | None) -> str:
    dq = data_quality or {}
    snap = decision_snapshot or {}
    nodes = (((snap.get("credit") or {}).get("nodes")) or {})
    checks: list[tuple[str, str, str]] = []

    def good(node: str) -> bool:
        return str((nodes.get(node) or {}).get("source_status", "unavailable")) == "ok"

    def participant(node: str) -> bool:
        return bool((nodes.get(node) or {}).get("participant", False))

    if participant("HY") and not participant("BBB") and good("BBB"):
        checks.append(("투자등급 경계 기업", "뚜렷한 변화 없음", "여기에서도 변화가 나타나면 회사채 부담이 투자등급 경계 기업까지 이어지는지 봅니다."))
    elif participant("BBB") and not participant("A") and good("A"):
        checks.append(("A등급 기업", "뚜렷한 변화 없음", "여기에서도 변화가 나타나면 회사채 부담이 A등급 기업까지 이어지는지 봅니다."))
    elif participant("A"):
        checks.append(("A등급 기업", _text((nodes.get("A") or {}).get("state_label")), "되돌림이 시작되는지, 기존 변화가 더 이어지는지 봅니다."))

    if any(participant(x) for x in ("HY", "BBB", "A")) and not participant("CP") and good("CP"):
        checks.append(("단기 기업자금", "뚜렷한 변화 없음", "여기에서도 변화가 나타나면 회사채의 변화가 단기 기업자금시장까지 함께 나타나는지 봅니다."))

    for node in ("HY", "BBB", "A", "CP"):
        row = nodes.get(node) or {}
        state = str(row.get("state", ""))
        if participant(node) and state in {"newly_rising", "rising_persistent"}:
            checks.append((_CREDIT_NAMES[node], _text(row.get("state_label")), "되돌림이 시작되는지, 아니면 부담이 다시 커지는지 봅니다."))
            break

    if not checks:
        axes = dq.get("axes") or {}
        changed = [axis_name(x) for x in (axes.get("changed_axes") or [])]
        if changed:
            checks.append((changed[0], "현재 변화 있음", "현재 움직임이 다음 데이터에서도 이어지는지, 다른 영역에서도 변화가 나타나는지 봅니다."))
        else:
            checks.append(("HY OAS와 VIX", "현재 큰 변화 적음", "어느 쪽이 먼저 움직였는지보다, 새 변화가 이어지는지와 다른 시장에서도 변화가 나타나는지를 봅니다."))

    lines = ["## 다음에 볼 것"]
    for title, current, meaning in checks[:3]:
        lines += ["", f"### {title}", f"현재: **{current}**", meaning]
    return "\n".join(lines)


def render_evidence_balance_markdown(data_quality: dict | None, aux_df: pd.DataFrame | None) -> str:
    dq = data_quality or {}
    readings = dq.get("readings") or []
    lines = ["## 현재 상황을 이렇게 봅니다"]
    if readings:
        reading = readings[0]
        label = plain_language(str(reading.get("label", "현재 가장 잘 맞는 설명")))
        observed = plain_language(str(reading.get("observed", "")))
        lines += ["", f"### {label}", observed]
        explanations = {str(x.get("id")): plain_language(str(x.get("text", ""))) for x in reading.get("explanations", [])}
        supported = [explanations[x] for x in (reading.get("supported_ids") or []) if x in explanations][:2]
        weakened = [explanations[x] for x in (reading.get("weakened_ids") or []) if x in explanations][:1]
        if supported:
            lines += ["", "### 가장 중요한 근거"] + [f"- {x}" for x in supported]
        if weakened:
            lines += ["", "### 아직 단정하기 어려운 점"] + [f"- {x}" for x in weakened]
    else:
        credit = dq.get("credit_episode") or {}
        current = credit.get("current") or {}
        if current:
            lines += ["", "### 현재 가장 먼저 볼 설명", _text(current.get("scope_text"))]
        else:
            lines += ["", "현재 정의된 조합 중 앞에 내세울 설명이 뚜렷하지 않습니다."]

    missing: list[str] = []
    if aux_df is not None and not aux_df.empty:
        for _, row in aux_df.iterrows():
            if len(missing) >= 2:
                break
            if str(row.get("staleness_label", "normal")) == "stale" or str(row.get("fetch_status", "ok")) in {"failed", "carried_forward"}:
                missing.append(aux_name(str(row.get("key", ""))))
    if missing:
        lines += ["", "### 현재 확인이 어려운 부분"] + [f"- {name}: 자료 상태 때문에 현재 해석에서는 조심해서 봅니다." for name in missing]
    lines += ["", "> 근거 개수를 점수처럼 세지 않습니다. 가장 중요한 근거와 반대로 볼 만한 점만 압축해서 보여줍니다."]
    return "\n".join(lines)


def render_credit_range_map_html(data_quality: dict | None) -> str:
    credit = (data_quality or {}).get("credit_episode") or {}
    current = credit.get("current") or {}
    nodes = current.get("nodes") or {}
    episode = current.get("episode") or {}
    participants = {str(x) for x in (episode.get("participants") or [])}
    lens = credit.get("lens") or {}
    if not current:
        return '<div class="rr-empty">기업 신용 상태를 읽을 수 없습니다.</div>'

    def node_card(node: str) -> str:
        row = nodes.get(node) or {}
        available = bool(row.get("available", False))
        state = str(row.get("state", "unavailable"))
        label = _text(row.get("state_label"), "확인 불가") if available else "확인 불가"
        symbol = _STATE_SYMBOLS.get(state, "○" if state in {"normal", "normalized"} else "?")
        participant = "변화 나타남" if node in participants else "뚜렷한 변화 없음"
        return (
            '<div class="rr-credit-node">'
            f'<strong>{escape(node)}</strong>'
            f'<span class="rr-credit-state">{escape(symbol)} {escape(label)}</span>'
            f'<small>{escape(participant)}</small>'
            '</div>'
        )

    scope = _text(current.get("scope_text"))
    episode_label = _text(episode.get("state_label"), "현재 변화 흐름 없음")
    lens_label = _text(lens.get("label"), "확인 불가")
    return (
        '<div class="rr-credit-map">'
        f'<div class="rr-credit-summary"><strong>현재 변화 범위</strong><span>{escape(scope)}</span>'
        f'<small>현재 흐름: {escape(episode_label)}</small></div>'
        '<div class="rr-credit-group"><div class="rr-group-title">회사채</div><div class="rr-credit-row">'
        + node_card("HY") + node_card("BBB") + node_card("A") +
        '</div></div>'
        '<div class="rr-credit-group"><div class="rr-group-title">단기 기업자금시장</div><div class="rr-credit-row rr-credit-row-single">'
        + node_card("CP") +
        '</div></div>'
        f'<div class="rr-credit-lens"><strong>저신용 기업 쪽 상대 부담(HY−BBB)</strong><span>{escape(lens_label)}</span></div>'
        '</div>'
    )


def render_data_health_badge(status: dict | None, data_quality: dict | None, decision_diff: dict | None, load_errors: list[str] | None) -> str:
    status = status or {}
    diff = decision_diff or {}
    summary = diff.get("summary") or {}
    issues = int(summary.get("data_quality", 0) or 0) + int(summary.get("recovery_gap", 0) or 0) + len(load_errors or [])
    active = _text(status.get("active_cache_version"), "확인 불가")
    if issues:
        return f"⚠ **데이터 확인 필요 {issues}건** · 활성 데이터 `{active}`"
    return f"✓ **데이터 정상** · 활성 데이터 `{active}`"
