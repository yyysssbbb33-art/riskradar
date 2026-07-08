"""v0.7.2 최근 90일 기업 신용 변화와 지난 변화 기록 표시.

새 판정 엔진을 만들지 않는다. v0.6.0부터 저장해 온
``credit_episode_nodes``와 ``credit_episodes``를 읽기 쉬운 시간축으로 보여준다.
90일은 90개 관측치가 아니라 최신 관측일을 포함한 달력 90일이다.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .credit_episode import EPISODE_STATE_LABELS, NODE_NAMES, NODE_ORDER, NODE_STATE_LABELS

TIMELINE_DAYS = 90
_CONFIRMED_STATES = {"newly_rising", "rising_persistent", "retracing", "normalized"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value) if pd.notna(value) else False


def _iso(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _split_nodes(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _event_text(kind: str, state: str, state_label: str) -> tuple[str, str] | None:
    if kind == "confirmed":
        return "부담 상승 확인", "confirmed"
    if kind == "new_peak":
        return "확인 뒤 부담이 더 커져 이전 고점을 넘어섬", "new_peak"
    if kind == "retracing":
        return "부담이 줄기 시작", "retracing"
    if kind == "normalized":
        return "평소 수준으로 돌아옴", "normalized"
    if state == "rising_persistent":
        return "상승 지속으로 바뀜", "state_change"
    if state in _CONFIRMED_STATES:
        return f"상태가 ‘{state_label}’로 바뀜", "state_change"
    return None


def _timeline_events(history: pd.DataFrame) -> list[dict[str, Any]]:
    """확정된 변화 흐름의 사건만 만든다.

    ``early_change`` 자체는 독립 사건으로 내보내지 않는다. 확정된 사건의
    ``candidate_start``만 확인 사건에 종속된 참고 문장으로 붙인다.
    """
    events: list[dict[str, Any]] = []
    order = {node: idx for idx, node in enumerate(NODE_ORDER)}

    for node, group in history.groupby("node", sort=False):
        g = group.sort_values("date").reset_index(drop=True)
        prev_state: str | None = None
        for _, row in g.iterrows():
            state = str(row.get("state", "normal"))
            state_label = str(row.get("state_label") or NODE_STATE_LABELS.get(state, state))
            kind = str(row.get("activity_kind") or "")
            meaningful = _as_bool(row.get("meaningful_activity", False))
            confirmed = _as_bool(row.get("confirmed_today", False))
            normalized = _as_bool(row.get("normalized_today", False))
            changed = prev_state is not None and state != prev_state

            event_info: tuple[str, str] | None = None
            if confirmed:
                event_info = _event_text("confirmed", state, state_label)
            elif normalized:
                event_info = _event_text("normalized", state, state_label)
            elif meaningful:
                event_info = _event_text(kind, state, state_label)
            elif changed and pd.notna(row.get("event_id")) and state in _CONFIRMED_STATES:
                # 확정되지 않고 사라진 early_change 경로는 독립 사건으로 보여주지 않는다.
                event_info = _event_text("", state, state_label)

            if event_info:
                text, event_type = event_info
                candidate_start = _iso(row.get("candidate_start")) if event_type == "confirmed" else None
                event_date = _iso(row.get("date"))
                if candidate_start == event_date:
                    candidate_start = None
                events.append({
                    "date": event_date,
                    "node": str(node),
                    "node_name": NODE_NAMES.get(str(node), str(node)),
                    "state": state,
                    "state_label": state_label,
                    "event_type": event_type,
                    "text": text,
                    "candidate_start": candidate_start,
                    "value": None if pd.isna(row.get("value")) else float(row.get("value")),
                })
            prev_state = state

    return sorted(
        events,
        key=lambda x: (x["date"], -order.get(x["node"], 99)),
        reverse=True,
    )


def _past_episode_rows(episodes: pd.DataFrame | None, latest_date: pd.Timestamp | None) -> list[dict[str, Any]]:
    if episodes is None or episodes.empty:
        return []

    d = episodes.copy()
    for col in ("started_at", "last_meaningful_activity_at", "dormant_at", "ended_at"):
        if col in d.columns:
            d[col] = pd.to_datetime(d[col], errors="coerce")
    if "started_at" not in d.columns:
        return []

    d = d.loc[d["started_at"].notna()].sort_values("started_at").reset_index(drop=True)
    if d.empty:
        return []

    # 마지막 레코드가 아직 열려 있으면 현재 에피소드이므로 과거 목록에서만 제외한다.
    last_idx = d.index[-1]
    last_state = str(d.at[last_idx, "state"]) if "state" in d.columns else ""
    last_ended = d.at[last_idx, "ended_at"] if "ended_at" in d.columns else pd.NaT
    if last_state in {"active", "dormant"} and pd.isna(last_ended):
        d = d.drop(index=last_idx)

    rows: list[dict[str, Any]] = []
    for _, row in d.sort_values("started_at", ascending=False).iterrows():
        state = str(row.get("state", "ended"))
        start = pd.Timestamp(row["started_at"])
        ended = row.get("ended_at")
        dormant = row.get("dormant_at")
        last_activity = row.get("last_meaningful_activity_at")

        if pd.notna(ended):
            display_end = pd.Timestamp(ended)
        elif pd.notna(dormant):
            display_end = pd.Timestamp(dormant)
        elif pd.notna(last_activity):
            display_end = pd.Timestamp(last_activity)
        else:
            display_end = latest_date or start

        duration_days = max(1, int((display_end.normalize() - start.normalize()).days) + 1)
        participants = _split_nodes(row.get("participants"))
        residual = _split_nodes(row.get("prior_residual_nodes"))
        rows.append({
            "episode_id": str(row.get("episode_id", "")),
            "state": state,
            "state_label": EPISODE_STATE_LABELS.get(state, state or "확인 불가"),
            "started_at": _iso(start),
            "display_end_at": _iso(display_end),
            "last_meaningful_activity_at": _iso(last_activity),
            "dormant_at": _iso(dormant),
            "ended_at": _iso(ended),
            "duration_days": duration_days,
            "participants": participants,
            "participant_names": [NODE_NAMES.get(x, x) for x in participants],
            "prior_residual_nodes": residual,
            "prior_residual_names": [NODE_NAMES.get(x, x) for x in residual],
        })
    return rows


def build_credit_timeline(
    node_history: pd.DataFrame | None,
    episodes: pd.DataFrame | None,
    *,
    days: int = TIMELINE_DAYS,
) -> dict[str, Any]:
    """저장된 신용 엔진 결과를 달력 기준 최근 N일과 지난 변화 기록으로 정리한다."""
    days = max(1, int(days))
    if node_history is None or node_history.empty or not {"date", "node", "state"}.issubset(node_history.columns):
        return {
            "schema": "credit-timeline-v1",
            "available": False,
            "days": days,
            "reason": "credit node history unavailable",
            "events": [],
            "past_episodes": _past_episode_rows(episodes, None),
            "sequence_claims_enabled": False,
        }

    d = node_history.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.loc[d["date"].notna()].sort_values(["date", "node"]).reset_index(drop=True)
    if d.empty:
        return {
            "schema": "credit-timeline-v1",
            "available": False,
            "days": days,
            "reason": "credit node history unavailable",
            "events": [],
            "past_episodes": _past_episode_rows(episodes, None),
            "sequence_claims_enabled": False,
        }

    latest = pd.Timestamp(d["date"].max()).normalize()
    cutoff = latest - pd.Timedelta(days=days - 1)
    filtered = d.loc[d["date"].dt.normalize() >= cutoff].copy()

    # 경계일의 상태 전환을 놓치지 않도록 노드별 직전 관측치 한 줄만 비교 문맥으로 붙인다.
    # 직전 관측 자체는 90일 타임라인 사건으로 내보내지 않는다.
    before = d.loc[d["date"].dt.normalize() < cutoff].copy()
    context_rows = before.sort_values("date").groupby("node", sort=False).tail(1)
    event_input = pd.concat([context_rows, filtered], ignore_index=True).sort_values(["date", "node"])
    events = [event for event in _timeline_events(event_input) if pd.Timestamp(event["date"]) >= cutoff]

    current_nodes: list[dict[str, Any]] = []
    for node in NODE_ORDER:
        hit = filtered.loc[filtered["node"].astype(str) == node]
        if hit.empty:
            continue
        row = hit.iloc[-1]
        state = str(row.get("state", "normal"))
        current_nodes.append({
            "node": node,
            "node_name": NODE_NAMES[node],
            "date": _iso(row.get("date")),
            "state": state,
            "state_label": str(row.get("state_label") or NODE_STATE_LABELS.get(state, state)),
        })

    return {
        "schema": "credit-timeline-v1",
        "available": True,
        "days": days,
        "window_start": cutoff.date().isoformat(),
        "window_end": latest.date().isoformat(),
        "observation_rows": int(len(filtered)),
        "events": events,
        "current_nodes": current_nodes,
        "past_episodes": _past_episode_rows(episodes, latest),
        "sequence_claims_enabled": False,
        "source_window_note": "현재 제공되는 공식 자료로 다시 계산한 기록",
    }


def render_credit_timeline_markdown(data: dict | None, *, max_events: int = 24) -> str:
    data = data or {}
    days = int(data.get("days") or TIMELINE_DAYS)
    lines = [f"## 최근 {days}일 기업 신용 변화"]
    if not data.get("available"):
        lines += [
            "저장된 기업 신용 기록이 없어 최근 변화를 보여줄 수 없습니다.",
            "기업 신용 기록이 있는 최신 데이터를 읽으면 기존 판정을 그대로 보여줍니다.",
        ]
        return "\n".join(lines)

    lines += [
        f"**{data.get('window_start')} ~ {data.get('window_end')}** · 달력 {days}일 기준",
        "",
        "최근 90일 동안 HY·BBB·A·CP 시장에서 **실제로 확인된 변화와 이후 부담이 더 커진 시점·줄기 시작한 시점·평소 수준으로 돌아온 시점**만 모았습니다. 확인되지 않고 사라진 초기 움직임은 따로 사건으로 세지 않습니다.",
    ]

    events = list(data.get("events") or [])
    if not events:
        lines += ["", "이 기간에는 따로 표시할 만큼 확인된 기업 신용 변화가 없습니다."]
    else:
        lines.append("")
        shown = events[:max_events]
        current_date = None
        for event in shown:
            if event.get("date") != current_date:
                current_date = event.get("date")
                lines += [f"### {current_date}"]
            lines.append(
                f"- **{event.get('node_name', event.get('node'))}:** {event.get('text')} · 당시 상태: `{event.get('state_label', '확인 불가')}`"
            )
            if event.get("event_type") == "confirmed" and event.get("candidate_start"):
                lines.append(f"  - 확인되기 전부터 {event.get('candidate_start')}에 초기 변화가 보이기 시작했습니다.")
        if len(events) > len(shown):
            lines += ["", f"이 {days}일 동안 확인된 변화 {len(events)}개 중 최근 {len(shown)}개를 보여줍니다."]

    lines += [
        "",
        "> 이 기록은 변화가 언제 확인됐는지만 보여줍니다. 어느 시장이 먼저 움직였는지에 의미를 붙이거나 다음 움직임을 예측하지 않습니다.",
    ]
    return "\n".join(lines)


def render_past_credit_episodes_markdown(data: dict | None, *, max_episodes: int = 6) -> str:
    data = data or {}
    episodes = list(data.get("past_episodes") or [])
    lines = ["## 지난 기업 신용 변화 기록"]

    if not episodes:
        lines.append("현재 제공되는 공식 자료로 다시 계산했을 때, 끝난 지난 변화 기록이 없습니다.")
    else:
        shown = episodes[:max_episodes]
        if len(episodes) > len(shown):
            lines += [
                f"현재 자료로 다시 계산한 지난 변화 기록 {len(episodes)}개 중 최근 {len(shown)}개를 보여줍니다.",
                "",
            ]
        for ep in shown:
            participants = " · ".join(ep.get("participant_names") or []) or "기록 없음"
            lines += [
                "",
                f"### {ep.get('started_at')} ~ {ep.get('display_end_at') or '확인 불가'}",
                f"- **상태:** {ep.get('state_label', '확인 불가')}",
                f"- **변화가 확인된 시장:** {participants}",
                f"- **기록된 기간:** {ep.get('duration_days', '확인 불가')}일",
            ]
            residual = ep.get("prior_residual_names") or []
            if residual:
                lines.append(f"- **이전 변화가 아직 남아 있던 시장:** {' · '.join(residual)}")

    lines += [
        "",
        "> **현재 제공되는 공식 자료로 다시 계산한 기록**입니다. 공식 원자료가 수정되거나 제공 기간이 달라지면 과거 날짜와 포함된 시장도 바뀔 수 있습니다. 과거 위기와 닮았다는 뜻도, 다음 위기의 순서나 확률을 예측한다는 뜻도 아닙니다.",
    ]
    return "\n".join(lines)


def render_credit_timeline_html(data: dict | None, *, max_events: int = 24) -> str:
    """최근 90일 변화를 날짜·시장 배지·사건 중심의 스캔 리스트로 보여준다."""
    from html import escape

    data = data or {}
    days = int(data.get("days") or TIMELINE_DAYS)
    if not data.get("available"):
        return (
            '<section class="rr-timeline">'
            f'<div class="rr-section-title"><h2>최근 {days}일</h2></div>'
            '<div class="rr-empty">저장된 기업 신용 기록이 없습니다.</div>'
            '</section>'
        )

    events = list(data.get("events") or [])
    if not events:
        body = '<div class="rr-quiet-line">○ 이 기간에는 따로 표시할 만큼 확인된 변화가 없습니다.</div>'
    else:
        rows: list[str] = []
        for event in events[:max_events]:
            node = str(event.get("node") or "")
            text = str(event.get("text") or "변화 확인")
            state = str(event.get("state_label") or "")
            candidate = event.get("candidate_start") if event.get("event_type") == "confirmed" else None
            sub = f'확인 전 초기 변화 · {candidate}' if candidate else state
            raw_date = str(event.get("date") or "-")
            try:
                display_date = pd.Timestamp(raw_date).strftime("%m.%d")
            except Exception:
                display_date = raw_date
            rows.append(
                '<div class="rr-timeline-row">'
                f'<time>{escape(display_date)}</time>'
                f'<span class="rr-market-badge">{escape(node)}</span>'
                '<div class="rr-timeline-event">'
                f'<strong>{escape(text)}</strong>'
                f'<small>{escape(sub)}</small>'
                '</div>'
                '</div>'
            )
        more = len(events) - min(len(events), max_events)
        body = '<div class="rr-timeline-list">' + ''.join(rows) + '</div>'
        if more > 0:
            body += f'<div class="rr-more">+ {more}개 변화가 더 있습니다.</div>'

    return (
        '<section class="rr-timeline">'
        f'<div class="rr-section-title"><h2>최근 {days}일</h2><span>{escape(str(data.get("window_start") or ""))} ~ {escape(str(data.get("window_end") or ""))}</span></div>'
        + body +
        '<div class="rr-info-box">확인된 변화만 보여줍니다. 잠깐 나타났다가 확인 전에 사라진 움직임은 제외합니다. 어느 시장이 먼저 움직였는지에 의미를 붙이거나 다음 움직임을 예측하지 않습니다.</div>'
        '</section>'
    )


def render_past_credit_episodes_compact_markdown(data: dict | None, *, max_episodes: int = 6) -> str:
    """지난 기록을 모바일 3열 표로 압축한다."""
    data = data or {}
    episodes = list(data.get("past_episodes") or [])
    lines = ["### 지난 기업 신용 변화 기록"]
    if not episodes:
        lines.append("현재 제공되는 공식 자료로 다시 계산했을 때 끝난 지난 변화 기록이 없습니다.")
    else:
        lines += ["", "| 기간 | 시장 | 지속 |", "|---|---|---:|"]
        for ep in episodes[:max_episodes]:
            start = ep.get("started_at") or "-"
            end = ep.get("display_end_at") or "-"
            participants = "·".join(ep.get("participants") or []) or "기록 없음"
            lines.append(f"| {start} ~ {end} | {participants} | {ep.get('duration_days', '-')}일 |")
        if len(episodes) > max_episodes:
            lines += ["", f"최근 {max_episodes}개만 보여줍니다. 전체 기록은 데이터에 보존돼 있습니다."]
    lines += [
        "",
        "> **현재 제공되는 공식 자료로 다시 계산한 기록**입니다. 원자료가 수정되거나 제공 기간이 달라지면 과거 날짜와 포함된 시장도 바뀔 수 있습니다. 과거 위기와 닮았다는 뜻도, 다음 위기의 순서나 확률을 예측한다는 뜻도 아닙니다.",
    ]
    return "\n".join(lines)
