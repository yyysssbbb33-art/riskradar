from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.credit_timeline import render_credit_timeline_html
from riskradar.overview_view import (
    render_domain_strip_html,
    render_next_checks_html,
    render_recent_changes_html,
    render_remaining_changes_html,
)
from riskradar.rate_composition import render_scan_html
from riskradar.ui import _is_compatible_data_code_version


def _matrix() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "key": "VIX", "state_code": "calm", "state_label": "평소 수준", "drop_flag": False,
            "latest_value": 15.0, "value_unit": "index", "change_20obs": -1.0, "change_unit": "pt",
        },
        {
            "key": "DGS30", "state_code": "rise_watch", "state_label": "오르는 중", "drop_flag": False,
            "latest_value": 4.7, "value_unit": "%", "change_20obs": 20.0, "change_unit": "bp",
        },
    ])


def _credit_quality() -> dict:
    return {
        "credit_episode": {
            "current": {
                "scope_text": "HY와 BBB에서 변화가 나타남",
                "episode": {"participants": ["HY", "BBB"]},
                "nodes": {
                    "HY": {"state_label": "상승 지속", "state": "rising_persistent"},
                    "BBB": {"state_label": "상승 확인", "state": "newly_rising"},
                    "A": {"state_label": "평소", "state": "normal"},
                    "CP": {"state_label": "평소", "state": "normal"},
                },
            }
        }
    }


def test_domain_strip_is_three_fact_cards_without_aggregate_score():
    html = render_domain_strip_html(_credit_quality(), _matrix())
    assert html.count("rr-domain-card") == 3
    assert "신용" in html and "금리" in html and "변동성" in html
    assert "HY" in html and "3.84" not in html  # fixture has no numeric HY source
    assert "30Y" in html and "+0.20%p" in html
    assert "종합" not in html and "위험점수" not in html


def test_recent_changes_are_event_cards_capped_at_three():
    events = []
    for key in ("HY", "BBB", "A", "CP"):
        events.append({
            "section": "credit_nodes", "key": key,
            "previous": "평소", "current": "상승 확인",
            "transition_type": "new_observation_transition",
        })
    html = render_recent_changes_html({"status": "ok", "market_transitions": events})
    assert html.count("rr-event-card") == 3
    assert "평소 → 상승 확인" in html
    assert "+ 1개 더 있음" in html


def test_remaining_change_chips_use_days_only_when_confirmed_date_exists():
    snap = {
        "credit": {"nodes": {
            "HY": {
                "source_status": "ok", "state": "rising_persistent", "state_label": "상승 지속",
                "participant": True, "confirmed_at": "2026-07-01",
            },
            "BBB": {"source_status": "ok", "state": "normal", "participant": False},
        }},
        "core": {
            "DGS30": {"state_code": "rise_watch", "state_label": "오르는 중", "drop_flag": False},
        },
    }
    html = render_remaining_changes_html(snap, {})
    assert "rr-chip" in html
    assert "HY 높은 수준 지속" in html and "일째" in html
    assert "현재 추세" in html
    assert "지속 중" not in html


def test_next_checks_are_numbered_and_capped_at_three():
    snap = {
        "credit": {"nodes": {
            "HY": {"source_status": "ok", "participant": True, "state": "rising_persistent"},
            "BBB": {"source_status": "ok", "participant": False, "state": "normal"},
            "A": {"source_status": "ok", "participant": False, "state": "normal"},
            "CP": {"source_status": "ok", "participant": False, "state": "normal"},
        }}
    }
    html = render_next_checks_html({}, snap)
    assert html.count("rr-next-item") <= 3
    assert "BBB" in html and "CP" in html
    assert "rr-next-num" in html


def _rate_summary(real: float, gap: float, total: float = 20.0) -> dict:
    return {
        "status": "ok",
        "primary": {
            "DGS30_change_bp": total,
            "DFII30_change_bp": real,
            "INFLCOMP30_change_bp": gap,
        },
        "curve": {"text": "장·단기 금리가 함께 올랐습니다."},
    }


def test_rate_scan_uses_bars_only_when_movements_share_direction():
    same = render_scan_html(_rate_summary(8.0, 12.0))
    opposite = render_scan_html(_rate_summary(8.0, -6.0, 2.0))
    assert "rr-rate-track" in same
    assert "두 움직임이 같은 방향" in same
    assert "rr-rate-track" not in opposite
    assert "rr-rate-opposite" in opposite
    assert "서로 일부 상쇄" in opposite
    for banned in ("기여", "합계"):
        assert banned not in same and banned not in opposite


def test_credit_timeline_is_scan_list_and_keeps_safety_text():
    html = render_credit_timeline_html({
        "available": True,
        "days": 90,
        "window_start": "2026-04-01",
        "window_end": "2026-06-30",
        "events": [{
            "date": "2026-06-20", "node": "HY", "text": "부담 상승 확인",
            "state_label": "상승 확인", "event_type": "confirmed", "candidate_start": "2026-06-18",
        }],
    })
    assert "rr-timeline-row" in html
    assert "rr-market-badge" in html
    assert "상승 확인 전 조짐" in html
    assert "어느 시장이 먼저 움직였는지에 의미를 붙이거나" in html


def test_v074_source_is_scan_first_and_mobile_two_column_core_grid():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert 'with gr.Tab("현황")' in source
    assert 'with gr.Tab("신용")' in source
    assert 'gr.Checkbox(value=True, label="변화 있는 항목만 보기")' not in source
    assert ".rr-core-grid { display:grid; grid-template-columns:repeat(3" in source
    assert ".rr-core-grid { grid-template-columns:repeat(2" in source
    assert "rr-credit-grid-2x2" in source
    assert _is_compatible_data_code_version("0.7.3", "0.7.4") is True
