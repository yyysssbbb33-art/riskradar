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


def test_core_cards_keep_all_six_available_but_compact_change_view_still_works():
    changed = render_core_cards_html(_matrix(), _chart(), changes_only=True)
    all_cards = render_core_cards_html(_matrix(), _chart(), changes_only=False)

    assert "HY OAS" in changed
    assert "VIX" not in changed
    assert "나머지 1개 핵심 지표" in changed
    assert "VIX" in all_cards and "HY OAS" in all_cards
    assert "약 1개월" in all_cards
    assert "약 3개월" not in all_cards
    assert "rr-core-grid" in all_cards


def test_recent_change_renderer_uses_user_names_and_keeps_data_issues_separate():
    diff = {
        "status": "ok",
        "market_transitions": [{
            "section": "credit_nodes", "key": "BBB", "transition_type": "new_observation_transition",
            "previous": "평소 상태 · 뚜렷한 변화 없음", "current": "상승 확인 · 변화 나타남",
        }],
        "data_quality_transitions": [{"section": "aux", "key": "AOAS"}],
        "recovery_gap_events": [],
        "schema_boundaries": [],
    }
    text = render_recent_changes_markdown(diff)
    assert "투자등급 경계 기업" in text
    assert "시장에서 새로 보이는 변화" in text
    assert "데이터 확인 필요" in text
    assert "A등급 기업" in text
    assert "credit_nodes" not in text


def test_credit_range_map_is_participation_map_not_sequence_arrow():
    dq = {
        "credit_episode": {
            "current": {
                "scope_text": "신용등급 낮은 기업과 투자등급 경계 기업에서 변화가 나타남",
                "episode": {"state_label": "변화 진행 중", "participants": ["HY", "BBB"]},
                "nodes": {
                    "HY": {"available": True, "state": "rising_persistent", "state_label": "상승 지속"},
                    "BBB": {"available": True, "state": "newly_rising", "state_label": "상승 확인"},
                    "A": {"available": True, "state": "normal", "state_label": "평소 상태"},
                    "CP": {"available": True, "state": "normal", "state_label": "평소 상태"},
                },
            },
            "lens": {"label": "저신용 기업 쪽 부담이 상대적으로 더 강함"},
        }
    }
    html = render_credit_range_map_html(dq)
    assert "HY" in html and "BBB" in html and "A" in html and "CP" in html
    assert "rr-credit-grid-2x2" in html
    assert html.count("rr-credit-tile-hot") == 2
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
    assert "현재 확인이 어려운 부분" in text
    assert "점수처럼 세지 않습니다" in text


def test_v074_has_five_short_tabs_and_scan_first_structure():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    for name in ("오늘", "신용", "흐름", "비교", "설명"):
        assert f'with gr.Tab("{name}")' in source
    for old in ("한눈에 보기", "기업 신용", "흐름과 차트", "지표 설명"):
        assert f'with gr.Tab("{old}")' not in source
    assert 'with gr.Accordion("관리·진단", open=False)' in source
    assert 'gr.Checkbox(value=True, label="변화 있는 항목만 보기")' not in source
    assert 'domain_strip_component = gr.HTML(initial["domain_strip"])' in source
    assert 'core_cards_component = gr.HTML(initial["core_cards_all"])' in source


def test_v070_accepts_v062_data_as_its_required_ui_baseline():
    assert _is_compatible_data_code_version("0.6.2", "0.7.0") is True
    assert _is_compatible_data_code_version("0.7.0", "0.7.0") is True
    assert _is_compatible_data_code_version("0.6.1", "0.7.0") is False
