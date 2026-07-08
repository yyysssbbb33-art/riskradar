"""v0.7.2 기업 신용 90일 타임라인과 과거 에피소드 표시.

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
        return "상승 변화 확인", "confirmed"
    if kind == "new_peak":
        return "확인된 변화 안에서 새 고점", "new_peak"
    if kind == "retracing":
        return "되돌림 시작", "retracing"
    if kind == "normalized":
        return "정상화 확인", "normalized"
    if state == "rising_persistent":
        return "상승 지속 상태로 전환", "state_change"
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
    """저장된 신용 엔진 결과를 달력 기준 최근 N일과 과거 에피소드로 정리한다."""
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
        "source_window_note": "현재 공식 자료 범위에서 재구성한 기록",
    }


def render_credit_timeline_markdown(data: dict | None, *, max_events: int = 24) -> str:
    data = data or {}
    days = int(data.get("days") or TIMELINE_DAYS)
    lines = [f"## 최근 {days}일 기업 신용 타임라인"]
    if not data.get("available"):
        lines += [
            "저장된 신용 노드 기록이 없어 타임라인을 만들 수 없습니다.",
            "신용 엔진 기록이 있는 최신 캐시를 읽으면 별도 재판정 없이 그대로 보여줍니다.",
        ]
        return "\n".join(lines)

    lines += [
        f"**{data.get('window_start')} ~ {data.get('window_end')}** · 달력 {days}일 기준",
        "",
        "새 판정을 만들지 않고, 기존 HY·BBB·A·CP 엔진에 저장된 **확인·새 고점·되돌림·정상화와 확정 뒤 상태 전환**만 모았습니다. 확정되지 않고 사라진 후보 신호는 독립 사건으로 보여주지 않습니다.",
    ]

    events = list(data.get("events") or [])
    if not events:
        lines += ["", "이 기간에는 저장된 규칙상 따로 표시할 확인·상태 전환·의미 있는 활동이 없습니다."]
    else:
        lines.append("")
        shown = events[:max_events]
        current_date = None
        for event in shown:
            if event.get("date") != current_date:
                current_date = event.get("date")
                lines += [f"### {current_date}"]
            lines.append(
                f"- **{event.get('node_name', event.get('node'))}:** {event.get('text')} · 당시 상태 `{event.get('state_label', '확인 불가')}`"
            )
            if event.get("event_type") == "confirmed" and event.get("candidate_start"):
                lines.append(f"  - 확정 전 후보 신호는 {event.get('candidate_start')}부터 이어졌습니다.")
        if len(events) > len(shown):
            lines += ["", f"이 {days}일 구간의 기록 {len(events)}개 중 최근 {len(shown)}개를 표시했습니다."]

    lines += [
        "",
        "> 이 시간축은 각 시장에서 저장된 변화가 언제 기록됐는지만 보여줍니다. 실제 선후행·인과 관계·다음 움직임을 주장하지 않습니다.",
    ]
    return "\n".join(lines)


def render_past_credit_episodes_markdown(data: dict | None, *, max_episodes: int = 6) -> str:
    data = data or {}
    episodes = list(data.get("past_episodes") or [])
    lines = ["## 과거 에피소드"]

    if not episodes:
        lines.append("현재 공식 자료 범위에서 재구성할 수 있는 끝난 과거 에피소드가 없습니다.")
    else:
        shown = episodes[:max_episodes]
        if len(episodes) > len(shown):
            lines += [
                f"현재 자료 범위에서 재구성된 과거 에피소드 {len(episodes)}개 중 최근 {len(shown)}개를 표시합니다.",
                "",
            ]
        for ep in shown:
            participants = " · ".join(ep.get("participant_names") or []) or "기록 없음"
            lines += [
                "",
                f"### {ep.get('started_at')} ~ {ep.get('display_end_at') or '확인 불가'}",
                f"- **상태:** {ep.get('state_label', '확인 불가')}",
                f"- **변화가 기록된 시장:** {participants}",
                f"- **관찰된 기간:** {ep.get('duration_days', '확인 불가')}일",
            ]
            residual = ep.get("prior_residual_names") or []
            if residual:
                lines.append(f"- **이전 변화가 남아 있던 시장:** {' · '.join(residual)}")

    lines += [
        "",
        "> **현재 공식 자료 범위에서 재구성한 기록**입니다. 원자료 개정이나 이용 가능한 자료 범위 변화에 따라 과거 날짜와 변화가 기록된 시장이 조정될 수 있습니다. 과거 금융위기와의 유사도, 발생 순서의 법칙, 다음 위기 확률을 뜻하지 않습니다.",
    ]
    return "\n".join(lines)
