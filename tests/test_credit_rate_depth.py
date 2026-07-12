from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.context_view import render_credit_context_html, render_rate_context_html
from riskradar.overview_view import render_credit_range_map_html
from riskradar.ui import _is_compatible_data_code_version


def _matrix() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "VIX", "latest_value": 19.2, "value_unit": "index", "change_20obs": 1.4, "change_unit": "pt"},
        {"key": "HYOAS", "latest_value": 3.8, "value_unit": "%", "change_20obs": 24.0, "change_unit": "bp"},
        {"key": "DGS30", "latest_value": 4.9, "value_unit": "%", "change_20obs": 18.0, "change_unit": "bp"},
        {"key": "DGS2", "latest_value": 3.9, "value_unit": "%", "change_20obs": -7.0, "change_unit": "bp"},
        {"key": "DFII10", "latest_value": 2.2, "value_unit": "%", "change_20obs": 11.0, "change_unit": "bp"},
        {"key": "T10Y3M", "latest_value": 0.4, "value_unit": "%p", "change_20obs": 8.0, "change_unit": "bp"},
    ])


def _aux() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "BBBOAS", "latest_value": 1.2, "value_unit": "%", "change_1m": 5.0, "change_unit": "bp"},
        {"key": "AOAS", "latest_value": 0.8, "value_unit": "%", "change_1m": -1.0, "change_unit": "bp"},
        {"key": "CPSPREAD", "latest_value": 25.0, "value_unit": "bp", "change_1m": 3.0, "change_unit": "bp"},
        {"key": "BREAKEVEN", "latest_value": 2.4, "value_unit": "%", "change_1m": 4.0, "change_unit": "bp"},
        {"key": "TERMPREM", "latest_value": 0.7, "value_unit": "%", "change_1m": -3.0, "change_unit": "bp"},
        {"key": "NFCI", "latest_value": -0.2, "value_unit": "index", "change_1m": 0.1, "change_unit": "index"},
        {"key": "STLFSI", "latest_value": -0.4, "value_unit": "index", "change_1m": -0.1, "change_unit": "index"},
    ])


def _quality() -> dict:
    return {
        "credit_episode": {
            "current": {
                "scope_text": "HY와 BBB에서 상승이 확인되고 있습니다.",
                "episode": {"participants": ["HY", "BBB"]},
                "nodes": {
                    "HY": {"available": True, "state": "newly_rising", "state_label": "상승 확인"},
                    "BBB": {"available": True, "state": "early_change", "state_label": "상승 조짐"},
                    "A": {"available": True, "state": "normal", "state_label": "특이 신호 없음"},
                    "CP": {"available": True, "state": "normal", "state_label": "특이 신호 없음"},
                },
            },
            "lens": {"latest_value_bp": 260.0, "change_1m_bp": 9.0, "label": "HY 쪽 확대가 더 큽니다."},
        }
    }


def test_credit_context_restores_companion_depth_without_causal_claims():
    html = render_credit_context_html(_quality(), _matrix(), _aux())
    assert "같이 읽는 신용 지표" in html
    for text in ("HY−BBB", "BBB OAS", "A OAS", "CP Spread", "VIX", "NFCI", "STLFSI"):
        assert text in html
    assert html.count("rr-context-card") == 4
    assert "인과관계나 선행 순서" in html
    assert "국채 대비 추가 금리" in html


def test_rate_context_restores_alignment_and_background_reading():
    summary = {"curve": {"text": "30Y 상승 · 2Y 하락"}}
    html = render_rate_context_html(_matrix(), _aux(), summary)
    assert "같이 읽는 금리 지표" in html
    for text in ("30Y", "실질 10Y", "10Y Breakeven", "10Y Term Premium", "2Y", "10Y−3M"):
        assert text in html
    assert "같은 방향" in html and "반대 방향" in html
    assert "30Y 구성에 직접 더한다는 뜻은 아닙니다" in html


def test_credit_and_rate_tabs_use_shared_context_visual_grammar_and_restore_market_reference():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert "credit_context_component" in source
    assert "rate_context_component" in source
    assert "rr-context-card" in source
    assert ".rr-credit-grid-2x2, .rr-rate-overview-grid" in source
    assert 'with gr.Accordion("시장 전체 참고 지표"' in source
    assert "visible=False" not in source[source.index('with gr.Tab("설명")'):]


def test_credit_tab_has_one_section_heading_and_matches_narrow_mobile_columns():
    html = render_credit_range_map_html(_quality(), _matrix(), _aux())
    assert "<h2>기업 신용</h2>" not in html
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert ".rr-mini-grid, .rr-metric-grid, .rr-credit-grid-2x2, .rr-context-grid" in source


def test_v084_keeps_previous_ui_cache_compatibility():
    assert _is_compatible_data_code_version("0.8.3", "0.8.4")
    assert _is_compatible_data_code_version("0.8.2", "0.8.4")
