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


def _direction_symbol(value: Any) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "·"
    if x > 0:
        return "↑"
    if x < 0:
        return "↓"
    return "→"


def render_core_cards_html(matrix: pd.DataFrame, chart_data: pd.DataFrame, *, changes_only: bool = False) -> str:
    """핵심 6개를 모바일 2×3 스캔 카드로 보여준다.

    v0.7.4부터 전체 6개가 기본이다. ``changes_only``는 구버전 호출 호환만 유지한다.
    평소 지표도 숨기지 않고, 눈에 띄는 카드만 시각적 강도를 높인다.
    """
    if matrix is None or matrix.empty:
        return '<div class="rr-empty">핵심 지표 데이터를 읽을 수 없습니다.</div>'
    chart_data = chart_data if isinstance(chart_data, pd.DataFrame) else pd.DataFrame()
    cards: list[str] = []
    hidden_count = 0
    for _, row in matrix.iterrows():
        noteworthy = _core_noteworthy(row)
        if changes_only and not noteworthy:
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
        change = row.get("change_20obs")
        change_text = fmt_change(change, row.get("change_unit", ""))
        direction = _direction_symbol(change)
        card_class = "rr-core-card rr-core-card-hot" if noteworthy else "rr-core-card rr-core-card-quiet"
        cards.append(
            f'<article class="{card_class}">'
            '<div class="rr-core-head">'
            f'<strong>{escape(core_name(key, short=True))}</strong>'
            f'<span class="rr-core-state">{escape(symbol)} {escape(label)}</span>'
            '</div>'
            f'<div class="rr-core-value">{escape(fmt_value(row.get("latest_value"), row.get("value_unit", "")))}</div>'
            f'<div class="rr-core-change"><span>{escape(direction)}</span> {escape(change_text)} <small>약 1개월</small></div>'
            f'<div class="rr-core-spark" aria-label="최근 흐름">{escape(spark or "────────")}</div>'
            '</article>'
        )
    if not cards:
        return '<div class="rr-empty">현재 표시할 핵심 지표가 없습니다.</div>'
    tail = ""
    if changes_only and hidden_count:
        tail = f'<div class="rr-muted">나머지 {hidden_count}개 핵심 지표는 평소 수준입니다.</div>'
    return '<div class="rr-core-grid">' + "".join(cards) + '</div>' + tail


def render_domain_strip_html(data_quality: dict | None, matrix: pd.DataFrame) -> str:
    """종합점수 없이 신용·금리·변동성 세 영역의 현재 사실만 크게 보여준다."""
    dq = data_quality or {}
    credit = dq.get("credit_episode") or {}
    current = credit.get("current") or {}
    episode = current.get("episode") or {}
    participants = [str(x) for x in (episode.get("participants") or [])]
    nodes = current.get("nodes") or {}

    if participants:
        credit_main = "·".join(participants) + " 변화"
        credit_sub = " / ".join(_text((nodes.get(x) or {}).get("state_label"), "확인") for x in participants[:2])
    elif current:
        early = [x for x in ("HY", "BBB", "A", "CP") if str((nodes.get(x) or {}).get("state")) == "early_change"]
        credit_main = ("·".join(early) + " 관찰") if early else "평소"
        credit_sub = "기업 신용"
    else:
        credit_main = "확인 불가"
        credit_sub = "기업 신용"

    def hit(key: str) -> pd.Series | None:
        if matrix is None or matrix.empty:
            return None
        rows = matrix.loc[matrix["key"].astype(str) == key]
        return None if rows.empty else rows.iloc[-1]

    rate = hit("DGS30")
    vix = hit("VIX")
    if rate is None:
        rate_main, rate_sub, rate_symbol = "확인 불가", "30년 금리", "·"
    else:
        rate_symbol = _direction_symbol(rate.get("change_20obs"))
        rate_main = f"30Y {rate_symbol}"
        rate_sub = state_name(str(rate.get("state_code", "")), str(rate.get("state_label", "")), drop=bool(rate.get("drop_flag", False)), key="DGS30")
    if vix is None:
        vix_main, vix_sub, vix_symbol = "확인 불가", "변동성", "·"
    else:
        vix_symbol = _state_symbol("VIX", str(vix.get("state_code", "")), bool(vix.get("drop_flag", False)))
        vix_main = state_name(str(vix.get("state_code", "")), str(vix.get("state_label", "")), key="VIX")
        vix_sub = "VIX"

    cards = [
        ("신용", credit_main, credit_sub, "●" if participants else "○"),
        ("금리", rate_main, rate_sub, rate_symbol),
        ("변동성", vix_main, vix_sub, vix_symbol),
    ]
    return '<div class="rr-domain-strip">' + ''.join(
        '<div class="rr-domain-card">'
        f'<small>{escape(title)}</small>'
        f'<strong><span>{escape(symbol)}</span> {escape(main)}</strong>'
        f'<em>{escape(sub)}</em>'
        '</div>'
        for title, main, sub, symbol in cards
    ) + '</div>'

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



def _event_card_name(section: str, key: str) -> str:
    if section == "core":
        return core_name(key, short=True)
    if section == "credit_nodes":
        return key
    if section == "credit_lens":
        return "HY−BBB"
    if section == "credit_episode":
        return "신용 흐름"
    return _event_name(section, key)


def _compact_transition_text(value: Any) -> str:
    text = plain_language(str(value))
    return text.split(" · ", 1)[0].strip()


def render_recent_changes_html(diff: dict | None, *, max_cards: int = 3) -> str:
    """최근 시장 변화를 발표 슬라이드처럼 사건 카드로 보여준다."""
    diff = diff or {}
    status = str(diff.get("status", ""))
    market = [event for event in (diff.get("market_transitions") or []) if _is_change_center_event(event)]
    recovery = [event for event in (diff.get("recovery_gap_events") or []) if _is_change_center_event(event)]
    events = [(event, False) for event in market] + [(event, True) for event in recovery]

    if not diff or status == "cold_start":
        text = "다음 정상 데이터부터 이전 기록과 비교합니다." if status == "cold_start" else "이전 정상 데이터와 비교할 기록이 아직 없습니다."
        return f'<section class="rr-section"><div class="rr-section-title"><h2>새로 달라진 점</h2></div><div class="rr-empty">{escape(text)}</div></section>'
    if not events:
        return '<section class="rr-section"><div class="rr-section-title"><h2>새로 달라진 점</h2><span class="rr-count">0</span></div><div class="rr-quiet-line">○ 새로 확인된 시장 변화는 없습니다.</div></section>'

    cards: list[str] = []
    for event, is_recovery in events[:max_cards]:
        section = str(event.get("section", ""))
        key = str(event.get("key", ""))
        name = _event_card_name(section, key)
        previous = event.get("previous")
        current = event.get("current")
        if is_recovery:
            title = "자료 복구 뒤 상태 변화"
            path = "공백 이전 상태 → 현재 상태"
        elif previous is not None and current is not None:
            title = _compact_transition_text(current)
            path = f"{_compact_transition_text(previous)} → {_compact_transition_text(current)}"
        else:
            title = plain_language(str(event.get("message") or "변화 확인"))
            path = plain_language(_friendly_event(event).replace("**", ""))
        symbol = "↑" if any(x in title for x in ("상승", "높", "확대", "오름")) else ("↘" if any(x in title for x in ("되돌", "감소", "축소", "내림")) else "●")
        cards.append(
            '<article class="rr-event-card">'
            '<div class="rr-event-head">'
            f'<strong>{escape(name)}</strong><span>최근</span>'
            '</div>'
            f'<div class="rr-event-title">{escape(symbol)} {escape(title)}</div>'
            f'<div class="rr-event-path">{escape(path)}</div>'
            '</article>'
        )
    more = len(events) - len(cards)
    more_html = f'<div class="rr-more">+ {more}개 더 있음 · 상세에서 확인</div>' if more > 0 else ""
    return (
        '<section class="rr-section">'
        f'<div class="rr-section-title"><h2>새로 달라진 점</h2><span class="rr-count">{len(events)}</span></div>'
        '<div class="rr-event-grid">' + ''.join(cards) + '</div>' + more_html +
        '</section>'
    )


def render_remaining_changes_html(decision_snapshot: dict | None, data_quality: dict | None) -> str:
    """지속 중인 상태를 짧은 칩으로 보여준다. 날짜가 확실한 신용만 일수를 계산한다."""
    snap = decision_snapshot or {}
    credit_nodes = (((snap.get("credit") or {}).get("nodes")) or {})
    core = snap.get("core") or {}
    items: list[tuple[str, str]] = []

    for node in ("HY", "BBB", "A", "CP"):
        row = credit_nodes.get(node) or {}
        if str(row.get("source_status", "unavailable")) != "ok":
            continue
        state = str(row.get("state", ""))
        if state not in {"newly_rising", "rising_persistent", "retracing"} and not bool(row.get("participant", False)):
            continue
        label = _text(row.get("state_label"), "변화")
        confirmed_at = row.get("confirmed_at")
        duration = "지속 중"
        if confirmed_at:
            try:
                end_date = row.get("observed_date") or pd.Timestamp.now(tz="Asia/Seoul").date().isoformat()
                days = max(1, (pd.Timestamp(end_date).date() - pd.Timestamp(confirmed_at).date()).days + 1)
                duration = f"{days}일째"
            except Exception:
                pass
        items.append((f"{node} {label}", duration))

    for key, row in core.items():
        if len(items) >= 4:
            break
        if key == "HYOAS" and credit_nodes:
            continue
        fake = pd.Series({"key": key, "state_code": row.get("state_code"), "drop_flag": row.get("drop_flag", False)})
        if _core_noteworthy(fake):
            label = _text(row.get("state_label"), "변화")
            items.append((f"{core_name(key, short=True)} {label}", "지속 중"))

    if not items:
        return '<section class="rr-section rr-compact-section"><div class="rr-section-title"><h2>계속 이어지는 변화</h2></div><div class="rr-quiet-line">○ 뚜렷하게 이어지는 변화가 많지 않습니다.</div></section>'
    chips = ''.join(
        '<div class="rr-chip"><span>' + escape(label) + '</span><strong>' + escape(duration) + '</strong></div>'
        for label, duration in items[:4]
    )
    return '<section class="rr-section rr-compact-section"><div class="rr-section-title"><h2>계속 이어지는 변화</h2></div><div class="rr-chip-row">' + chips + '</div></section>'


def render_next_checks_html(data_quality: dict | None, decision_snapshot: dict | None) -> str:
    """다음 확인 대상을 번호와 한 줄로 최대 3개만 보여준다."""
    dq = data_quality or {}
    snap = decision_snapshot or {}
    nodes = (((snap.get("credit") or {}).get("nodes")) or {})
    checks: list[tuple[str, str]] = []

    def good(node: str) -> bool:
        return str((nodes.get(node) or {}).get("source_status", "unavailable")) == "ok"

    def participant(node: str) -> bool:
        return bool((nodes.get(node) or {}).get("participant", False))

    if participant("HY") and not participant("BBB") and good("BBB"):
        checks.append(("BBB", "다른 신용등급에도 변화가 나타나는지"))
    elif participant("BBB") and not participant("A") and good("A"):
        checks.append(("A", "회사채 변화가 더 넓게 나타나는지"))
    if any(participant(x) for x in ("HY", "BBB", "A")) and not participant("CP") and good("CP"):
        checks.append(("CP", "단기 기업자금도 함께 움직이는지"))
    for node in ("HY", "BBB", "A", "CP"):
        row = nodes.get(node) or {}
        if participant(node) and str(row.get("state")) in {"newly_rising", "rising_persistent"}:
            checks.append((node, "부담이 줄기 시작하는지, 더 커지는지"))
            break
    if len(checks) < 3:
        axes = dq.get("axes") or {}
        changed = [axis_name(x) for x in (axes.get("changed_axes") or [])]
        for name in changed:
            if len(checks) >= 3:
                break
            checks.append((name, "현재 움직임이 다음 데이터에서도 이어지는지"))
    if not checks:
        checks = [("HY OAS", "새 변화가 나타나는지"), ("VIX", "변동성까지 커지는지")]

    rows = ''.join(
        '<div class="rr-next-item">'
        f'<span class="rr-next-num">{i}</span>'
        f'<div><strong>{escape(title)}</strong><small>{escape(text)}</small></div>'
        '</div>'
        for i, (title, text) in enumerate(checks[:3], start=1)
    )
    return '<section class="rr-section"><div class="rr-section-title"><h2>다음에 볼 것</h2></div><div class="rr-next-list">' + rows + '</div></section>'

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
    """상세 아코디언 안에서도 긴 문단 대신 결론·근거·반대 근거로 구조화한다."""
    dq = data_quality or {}
    readings = dq.get("readings") or []
    lines = ["### 현재 판단"]
    rows: list[tuple[str, str]] = []
    weakened: list[str] = []

    if readings:
        reading = readings[0]
        label = plain_language(str(reading.get("label", "현재 가장 잘 맞는 설명")))
        observed = plain_language(str(reading.get("observed", "")))
        lines += ["", f"**{label}**", "", observed]
        explanations = {str(x.get("id")): plain_language(str(x.get("text", ""))) for x in reading.get("explanations", [])}
        supported = [explanations[x] for x in (reading.get("supported_ids") or []) if x in explanations][:2]
        weakened = [explanations[x] for x in (reading.get("weakened_ids") or []) if x in explanations][:1]
        rows.extend(("근거", x) for x in supported)
    else:
        credit = dq.get("credit_episode") or {}
        current = credit.get("current") or {}
        if current:
            lines += ["", _text(current.get("scope_text"))]
        else:
            lines += ["", "현재 앞에 내세울 해석이 뚜렷하지 않습니다."]

    missing: list[str] = []
    if aux_df is not None and not aux_df.empty:
        for _, row in aux_df.iterrows():
            if len(missing) >= 2:
                break
            if str(row.get("staleness_label", "normal")) == "stale" or str(row.get("fetch_status", "ok")) in {"failed", "carried_forward"}:
                missing.append(aux_name(str(row.get("key", ""))))

    if rows:
        lines += ["", "| 구분 | 내용 |", "|---|---|"]
        lines.extend(f"| {kind} | {text} |" for kind, text in rows)
    if weakened:
        lines += ["", "**반대로 볼 점**", "", weakened[0]]
    if missing:
        lines += ["", "**현재 확인이 어려운 부분**", ""] + [f"- {name}: 자료 상태 때문에 조심해서 봅니다." for name in missing]
    lines += ["", "> 근거 개수를 점수처럼 세지 않습니다. 중요한 근거와 반대로 볼 점만 보여줍니다."]
    return "\n".join(lines)

def render_credit_range_map_html(data_quality: dict | None) -> str:
    """HY·BBB·A·CP를 한눈에 보는 2×2 개인용 상태 지도."""
    credit = (data_quality or {}).get("credit_episode") or {}
    current = credit.get("current") or {}
    nodes = current.get("nodes") or {}
    episode = current.get("episode") or {}
    participants = {str(x) for x in (episode.get("participants") or [])}
    lens = credit.get("lens") or {}
    if not current:
        return '<div class="rr-empty">기업 신용 상태를 읽을 수 없습니다.</div>'

    subtitles = {
        "HY": "낮은 등급 회사채",
        "BBB": "투자등급 경계",
        "A": "우량 회사채",
        "CP": "단기 기업자금",
    }

    def node_card(node: str) -> str:
        row = nodes.get(node) or {}
        available = bool(row.get("available", False))
        state = str(row.get("state", "unavailable"))
        label = _text(row.get("state_label"), "확인 불가") if available else "확인 불가"
        symbol = _STATE_SYMBOLS.get(state, "○" if state in {"normal", "normalized"} else "?")
        hot = node in participants or state == "early_change"
        cls = "rr-credit-tile rr-credit-tile-hot" if hot else "rr-credit-tile rr-credit-tile-quiet"
        return (
            f'<div class="{cls}">'
            '<div class="rr-credit-tile-head">'
            f'<strong>{escape(node)}</strong><small>{escape(subtitles[node])}</small>'
            '</div>'
            f'<div class="rr-credit-tile-state">{escape(symbol)} {escape(label)}</div>'
            '</div>'
        )

    scope = _text(current.get("scope_text"), "현재 범위를 확인할 수 없습니다.")
    lens_label = _text(lens.get("label"), "확인 불가")
    return (
        '<section class="rr-credit-visual">'
        '<div class="rr-section-title"><h2>기업 신용</h2></div>'
        '<div class="rr-credit-grid-2x2">'
        + ''.join(node_card(node) for node in ("HY", "BBB", "A", "CP")) +
        '</div>'
        f'<div class="rr-credit-scope">{escape(scope)}</div>'
        f'<div class="rr-credit-lens-line"><span>HY−BBB</span><strong>{escape(lens_label)}</strong></div>'
        '</section>'
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
