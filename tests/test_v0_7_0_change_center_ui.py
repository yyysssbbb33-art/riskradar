from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.overview_view import (
    render_core_cards_html,
    render_credit_range_map_html,
    render_evidence_balance_markdown,
    render_recent_changes_markdown,
)
from riskradar.ui import _is_compatible_data_code_version


def _matrix() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "key": "VIX", "state_code": "calm", "state_label": "평소 수준",
            "drop_flag": False, "latest_value": 15.0, "value_unit": "index",
            "change_20obs": -1.0, "change_60obs": 0.5, "change_unit": "pt",
            "latest_observed_date": "2026-07-07",
        },
        {
            "key": "HYOAS", "state_code": "watch", "state_label": "부담 확대",
            "drop_flag": False, "latest_value": 420.0, "value_unit": "bp",
            "change_20obs": 55.0, "change_60obs": 80.0, "change_unit": "bp",
            "latest_observed_date": "2026-07-07",
        },
    ])


def _chart() -> pd.DataFrame:
    rows = []
    for key, values in {"VIX": [14, 15, 14, 15], "HYOAS": [350, 370, 390, 420]}.items():
        for i, value in enumerate(values):
            rows.append({"key": key, "date": f"2026-07-0{i + 1}", "value": value})
    return pd.DataFrame(rows)


def test_core_cards_default_change_filter_hides_quiet_items_but_all_view_keeps_them():
    changed = render_core_cards_html(_matrix(), _chart(), changes_only=True)
    all_cards = render_core_cards_html(_matrix(), _chart(), changes_only=False)

    assert "신용등급 낮은 기업의 추가금리" in changed
    assert "주식시장이 예상하는 흔들림" not in changed
    assert "나머지 1개 핵심 지표" in changed
    assert "주식시장이 예상하는 흔들림" in all_cards
    assert "약 1개월" in all_cards and "약 3개월" in all_cards


def test_recent_change_renderer_uses_user_names_and_keeps_data_issues_separate():
    diff = {
        "status": "ok",
        "market_transitions": [{
            "section": "credit_nodes", "key": "BBB", "transition_type": "new_observation_transition",
            "previous": "평소 상태 · 미참여", "current": "새로 상승 · 참여",
        }],
        "data_quality_transitions": [{"section": "aux", "key": "AOAS"}],
        "recovery_gap_events": [],
        "schema_boundaries": [],
    }
    text = render_recent_changes_markdown(diff)
    assert "투자등급 경계 기업" in text
    assert "시장 판정 변화" in text
    assert "데이터 확인 필요" in text
    assert "A등급 기업" in text
    assert "credit_nodes" not in text


def test_credit_range_map_is_participation_map_not_sequence_arrow():
    dq = {
        "credit_episode": {
            "current": {
                "scope_text": "신용등급 낮은 기업과 투자등급 경계 기업이 참여",
                "episode": {"state_label": "활성", "participants": ["HY", "BBB"]},
                "nodes": {
                    "HY": {"available": True, "state": "rising_persistent", "state_label": "상승 지속"},
                    "BBB": {"available": True, "state": "newly_rising", "state_label": "새로 상승"},
                    "A": {"available": True, "state": "normal", "state_label": "평소 상태"},
                    "CP": {"available": True, "state": "normal", "state_label": "평소 상태"},
                },
            },
            "lens": {"label": "저신용 기업 쪽 부담이 상대적으로 더 강함"},
        }
    }
    html = render_credit_range_map_html(dq)
    assert "HY" in html and "BBB" in html and "A" in html and "CP" in html
    assert html.count("참여 중") == 2
    assert "→" not in html
    assert "HY−BBB" in html


def test_evidence_balance_limits_visible_tally_and_keeps_uncertainty():
    dq = {
        "readings": [{
            "label": "기업 신용 부담 확대",
            "observed": "회사채 쪽 변화가 보입니다.",
            "explanations": [
                {"id": "a", "text": "첫 번째 지지"},
                {"id": "b", "text": "두 번째 지지"},
                {"id": "c", "text": "세 번째 지지"},
                {"id": "d", "text": "가장 큰 반대 근거"},
            ],
            "supported_ids": ["a", "b", "c"],
            "weakened_ids": ["d"],
        }]
    }
    aux = pd.DataFrame([{
        "key": "TERMPREM", "staleness_label": "stale", "fetch_status": "ok",
    }])
    text = render_evidence_balance_markdown(dq, aux)
    assert "첫 번째 지지" in text and "두 번째 지지" in text
    assert "세 번째 지지" not in text
    assert "가장 큰 반대 근거" in text
    assert "현재 확인 부족" in text
    assert "점수처럼 읽지 않습니다" in text


def test_v070_has_five_top_tabs_and_embeds_data_status_above_tabs():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    for name in ("한눈에 보기", "기업 신용", "흐름과 차트", "비교", "지표 설명"):
        assert f'with gr.Tab("{name}")' in source
    for old in ("현재 상황", "오늘의 해석", "지난 30일 흐름", "같은 날짜 비교", "전체 지표 비교", "차트", "데이터 상태"):
        assert f'with gr.Tab("{old}")' not in source
    assert 'with gr.Accordion("데이터 상태·운영 진단 보기", open=False)' in source
    assert 'gr.Checkbox(value=True, label="변화 있는 항목만 보기")' in source


def test_v070_accepts_v062_data_as_its_required_ui_baseline():
    assert _is_compatible_data_code_version("0.6.2", "0.7.0") is True
    assert _is_compatible_data_code_version("0.7.0", "0.7.0") is True
    assert _is_compatible_data_code_version("0.6.1", "0.7.0") is False
