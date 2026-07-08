from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.credit_timeline import (
    build_credit_timeline,
    render_credit_timeline_markdown,
    render_past_credit_episodes_markdown,
)
from riskradar.today_view import render_credit_episode_markdown


def _row(date: str, node: str, state: str, **extra):
    labels = {
        "normal": "평소 상태",
        "early_change": "초기 변화",
        "newly_rising": "상승 확인",
        "rising_persistent": "상승 지속",
        "retracing": "되돌림",
        "normalized": "정상화",
    }
    row = {
        "date": date,
        "node": node,
        "value": 100.0,
        "state": state,
        "state_label": labels[state],
        "event_id": pd.NA,
        "candidate_start": pd.NaT,
        "activity_kind": "",
        "meaningful_activity": False,
        "confirmed_today": False,
        "normalized_today": False,
    }
    row.update(extra)
    return row


def _history() -> pd.DataFrame:
    rows = [
        _row("2026-01-10", "HY", "normal"),
        # 확정된 HY 변화: early_change 자체는 독립 사건이 아니고 확인 사건의 참고 날짜다.
        _row("2026-03-01", "HY", "early_change", candidate_start="2026-03-01"),
        _row("2026-03-02", "HY", "early_change", candidate_start="2026-03-01"),
        _row(
            "2026-03-03", "HY", "newly_rising", event_id="HY-1",
            candidate_start="2026-03-01", activity_kind="confirmed",
            meaningful_activity=True, confirmed_today=True,
        ),
        _row("2026-03-08", "HY", "rising_persistent", event_id="HY-1"),
        _row(
            "2026-03-10", "HY", "rising_persistent", event_id="HY-1",
            activity_kind="new_peak", meaningful_activity=True,
        ),
        _row(
            "2026-03-15", "HY", "retracing", event_id="HY-1",
            activity_kind="retracing", meaningful_activity=True,
        ),
        _row(
            "2026-03-20", "HY", "normalized", event_id="HY-1",
            activity_kind="normalized", meaningful_activity=True, normalized_today=True,
        ),
        _row("2026-04-10", "HY", "normal"),
        # 확정되지 않고 사라진 BBB 후보 신호는 타임라인 독립 사건으로 나오면 안 된다.
        _row("2026-02-01", "BBB", "normal"),
        _row("2026-02-02", "BBB", "early_change", candidate_start="2026-02-02"),
        _row("2026-02-03", "BBB", "normal"),
        _row("2026-04-10", "BBB", "normal"),
    ]
    return pd.DataFrame(rows)


def _episodes() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "episode_id": "credit-1", "state": "dormant", "started_at": "2026-01-01",
            "last_meaningful_activity_at": "2026-01-10", "dormant_at": "2026-01-20",
            "ended_at": None, "participants": "HY", "prior_residual_nodes": "",
        },
        {
            "episode_id": "credit-2", "state": "ended", "started_at": "2026-02-01",
            "last_meaningful_activity_at": "2026-02-08", "dormant_at": None,
            "ended_at": "2026-02-12", "participants": "HY,BBB", "prior_residual_nodes": "HY",
        },
        {
            "episode_id": "credit-3", "state": "active", "started_at": "2026-03-03",
            "last_meaningful_activity_at": "2026-03-20", "dormant_at": None,
            "ended_at": None, "participants": "HY", "prior_residual_nodes": "",
        },
    ])


def test_calendar_90_day_window_and_boundary_context():
    out = build_credit_timeline(_history(), _episodes(), days=90)
    assert out["window_end"] == "2026-04-10"
    assert out["window_start"] == "2026-01-11"
    assert all(event["date"] >= "2026-01-11" for event in out["events"])

    boundary = pd.DataFrame([
        _row("2026-01-10", "HY", "normal"),
        _row("2026-01-11", "HY", "rising_persistent", event_id="HY-1"),
        _row("2026-04-10", "HY", "rising_persistent", event_id="HY-1"),
    ])
    edge = build_credit_timeline(boundary, pd.DataFrame(), days=90)
    assert any(e["date"] == "2026-01-11" and e["event_type"] == "state_change" for e in edge["events"])
    assert all(e["date"] != "2026-01-10" for e in edge["events"])


def test_early_change_is_not_coequal_event_but_confirmed_event_keeps_candidate_date():
    out = build_credit_timeline(_history(), _episodes())
    assert not [e for e in out["events"] if e["state"] == "early_change"]
    assert not [e for e in out["events"] if e["node"] == "BBB"]

    confirmed = next(e for e in out["events"] if e["event_type"] == "confirmed")
    assert confirmed["date"] == "2026-03-03"
    assert confirmed["candidate_start"] == "2026-03-01"

    text = render_credit_timeline_markdown(out)
    assert "상승 확인 전 조짐: 2026-03-01부터" in text
    assert "당시 상태" in text
    assert "현재 표시는" not in text


def test_confirmed_lifecycle_events_are_kept_without_sequence_claims():
    out = build_credit_timeline(_history(), _episodes())
    kinds = {e["event_type"] for e in out["events"] if e["node"] == "HY"}
    assert {"confirmed", "state_change", "new_peak", "retracing", "normalized"}.issubset(kinds)

    text = render_credit_timeline_markdown(out)
    assert "어느 시장이 먼저 움직였는지에 의미를 붙이거나 다음 움직임을 예측하지 않습니다" in text
    assert "선행지표" not in text
    assert "다음은" not in text


def test_past_episode_uses_same_end_date_for_title_and_duration_and_excludes_open_current():
    out = build_credit_timeline(_history(), _episodes())
    ids = [row["episode_id"] for row in out["past_episodes"]]
    assert ids == ["credit-2", "credit-1"]

    dormant = next(row for row in out["past_episodes"] if row["episode_id"] == "credit-1")
    assert dormant["display_end_at"] == "2026-01-20"
    assert dormant["duration_days"] == 20

    text = render_past_credit_episodes_markdown(out)
    assert "### 2026-01-01 ~ 2026-01-20" in text
    assert "기록된 기간:** 20일" in text
    assert "credit-3" not in text


def test_past_episode_copy_is_reconstruction_not_accumulation_and_warns_about_revision():
    out = build_credit_timeline(_history(), _episodes())
    text = render_past_credit_episodes_markdown(out, max_episodes=1)
    assert "지난 변화 기록 2개 중 최근 1개" in text
    assert "현재 제공되는 공식 자료로 다시 계산한 기록" in text
    assert "공식 원자료가 수정되거나 제공 기간이 달라지면" in text
    assert "과거 날짜와 포함된 시장도 바뀔 수 있습니다" in text
    assert "누적" not in text


def test_existing_credit_detail_no_longer_exposes_estimated_onset_as_change_start():
    dq = {
        "credit_episode": {
            "current": {
                "episode": {"state": "active", "state_label": "변화 진행 중"},
                "scope_text": "신용등급 낮은 기업의 회사채에서 변화가 확인되고 있습니다.",
                "nodes": {
                    "HY": {
                        "available": True,
                        "name": "신용등급 낮은 기업의 회사채",
                        "state_label": "상승 확인",
                        "estimated_onset": "2026-03-01",
                        "confirmed_at": "2026-03-03",
                        "residual_change": 20.0,
                    },
                    "BBB": {"available": False},
                    "A": {"available": False},
                    "CP": {"available": False},
                },
                "cp_calendar_context": {},
            },
            "lens": {},
            "vix_context": {},
        }
    }
    text = render_credit_episode_markdown(dq)
    assert "변화 시작 2026-03-01" not in text
    assert "상승 확인 2026-03-03" in text


def test_known_mechanical_replacement_artifacts_are_removed_from_source():
    forbidden = (
        "평소 변화가 나타난 곳",
        "자료 변화가 나타난 곳",
        "변화가 나타난 곳",
        "곳를",
        "곳와",
        "흐름가",
        "흐름**가",
        "데이터 데이터",
        "기준다",
        "흐름로",
        "업데이트을",
    )
    root = Path(__file__).parents[1] / "src" / "riskradar"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for phrase in forbidden:
        assert phrase not in text, phrase


def test_v072_ui_accepts_v071_and_v070_data_and_places_timeline_in_credit_tab():
    from riskradar.ui import _is_compatible_data_code_version

    assert _is_compatible_data_code_version("0.7.1", "0.7.2") is True
    assert _is_compatible_data_code_version("0.7.0", "0.7.2") is True
    assert _is_compatible_data_code_version("0.6.2", "0.7.2") is False

    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert 'credit_timeline_component = gr.HTML(initial["credit_timeline_html"])' in source
    assert 'with gr.Accordion("지난 변화 기록", open=False)' in source
    assert source.index('with gr.Tab("신용")') < source.index('credit_timeline_component = gr.HTML(initial["credit_timeline_html"])')


def test_timeline_reads_actual_credit_engine_output_without_new_judgment():
    from dataclasses import replace
    import numpy as np

    from riskradar.credit_episode import CreditEpisodeCfg, build_credit_episode

    values = np.r_[np.full(60, 300.0), 310.0, 320.0, 330.0, 340.0, np.full(12, 340.0)]
    frame = pd.DataFrame({
        "date": pd.bdate_range("2025-01-02", periods=len(values)),
        "value": values,
    })
    cfg = replace(
        CreditEpisodeCfg(),
        fast_lookback=3,
        slow_lookback=8,
        min_history_obs=35,
        candidate_pct=80.0,
        confirm_obs=3,
        baseline_obs=5,
        baseline_noise_obs=15,
        dormant_obs=50,
    )
    engine = build_credit_episode({"HY": frame}, cfg=cfg)
    out = build_credit_timeline(engine.node_history, engine.episodes)

    confirmed = [e for e in out["events"] if e["event_type"] == "confirmed"]
    assert len(confirmed) == 1
    assert confirmed[0]["candidate_start"] is not None
    assert confirmed[0]["candidate_start"] < confirmed[0]["date"]
    assert out["sequence_claims_enabled"] is False
