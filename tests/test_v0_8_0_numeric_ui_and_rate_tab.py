from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.display_text import credit_state_name, state_name
from riskradar.overview_view import (
    render_credit_range_map_html,
    render_domain_strip_html,
    render_remaining_changes_html,
)
from riskradar.rate_composition import render_scan_html
from riskradar.rate_view import (
    render_rate_change_table_html,
    render_rate_curve_html,
    render_rate_overview_cards_html,
    render_rate_reference_cards_html,
)
from riskradar.ui import (
    _common_date_choices,
    _date_cards_html,
    _is_compatible_data_code_version,
    _signal_matrix_df,
)


def _matrix() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "VIX", "state_code": "calm", "state_label": "평소 수준", "drop_flag": False,
         "latest_value": 17.4, "value_unit": "index", "change_20obs": -1.2, "change_60obs": 0.5, "change_unit": "pt", "latest_observed_date": "2026-07-07"},
        {"key": "HYOAS", "state_code": "watch", "state_label": "평소보다 높음", "drop_flag": False,
         "latest_value": 3.84, "value_unit": "%", "change_20obs": 32.0, "change_60obs": 40.0, "change_unit": "bp", "latest_observed_date": "2026-07-07"},
        {"key": "T10Y3M", "state_code": "normal", "state_label": "정상", "drop_flag": False,
         "latest_value": 42.0, "value_unit": "bp", "change_20obs": 11.0, "change_60obs": 8.0, "change_unit": "bp", "latest_observed_date": "2026-07-07"},
        {"key": "DGS30", "state_code": "stable", "state_label": "큰 움직임 없음", "drop_flag": False,
         "latest_value": 4.99, "value_unit": "%", "change_20obs": 2.0, "change_60obs": 31.0, "change_unit": "bp", "latest_observed_date": "2026-07-07"},
        {"key": "DGS2", "state_code": "stable", "state_label": "큰 움직임 없음", "drop_flag": False,
         "latest_value": 3.88, "value_unit": "%", "change_20obs": -7.0, "change_60obs": -11.0, "change_unit": "bp", "latest_observed_date": "2026-07-07"},
        {"key": "DFII10", "state_code": "rise_watch", "state_label": "오르는 중", "drop_flag": False,
         "latest_value": 2.24, "value_unit": "%", "change_20obs": 13.0, "change_60obs": 19.0, "change_unit": "bp", "latest_observed_date": "2026-07-07"},
    ])


def _aux() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "BBBOAS", "latest_value": 1.21, "value_unit": "%", "change_1m": 4.0, "change_unit": "bp"},
        {"key": "AOAS", "latest_value": 0.78, "value_unit": "%", "change_1m": 2.0, "change_unit": "bp"},
        {"key": "CPSPREAD", "latest_value": 24.0, "value_unit": "bp", "change_1m": -1.0, "change_unit": "bp"},
        {"key": "TERMPREM", "latest_value": 0.73, "value_unit": "%", "change_1m": -3.0, "change_unit": "bp"},
    ])


def _quality() -> dict:
    return {
        "credit_episode": {
            "current": {
                "scope_text": "HY와 BBB에서 상승이 확인되고 있습니다.",
                "episode": {"participants": ["HY", "BBB"]},
                "nodes": {
                    "HY": {"available": True, "state": "newly_rising", "state_label": "상승 확인", "confirmed_at": "2026-07-01", "observed_date": "2026-07-07"},
                    "BBB": {"available": True, "state": "early_change", "state_label": "초기 변화"},
                    "A": {"available": True, "state": "normal", "state_label": "평소"},
                    "CP": {"available": True, "state": "normal", "state_label": "평소"},
                },
            },
            "lens": {"latest_value_bp": 263.0, "change_1m_bp": 6.0, "label": "두 시장이 비교적 함께 움직이는 중"},
        }
    }


def _rate_summary() -> dict:
    return {
        "status": "ok",
        "latest": {"DGS30": 4.99, "DFII30": 2.46, "INFLCOMP30": 2.53},
        "primary": {"DGS30_change_bp": 2.0, "DFII30_change_bp": 8.0, "INFLCOMP30_change_bp": -6.0},
        "context": {"DGS30_change_bp": 31.0, "DFII30_change_bp": 24.0, "INFLCOMP30_change_bp": 7.0},
        "curve": {"status": "ok", "code": "long_up_short_down", "DGS2_change_bp": -7.0, "DGS30_change_bp": 2.0, "text": "30Y 상승 · 2Y 하락"},
    }


def test_state_and_trend_language_are_separate_and_domain_specific():
    assert credit_state_name("normal") == "특이 신호 없음"
    assert credit_state_name("early_change") == "상승 조짐"
    assert credit_state_name("newly_rising") == "상승 확인"
    assert credit_state_name("rising_persistent") == "높은 수준 지속"
    assert credit_state_name("retracing") == "하락 전환"
    assert credit_state_name("normalized") == "신호 해제"
    assert state_name("calm", key="VIX") == "경계 신호 없음"
    assert state_name("stable", key="DGS30") == "급격한 상승 없음"


def test_domain_strip_restores_value_state_and_one_month_change():
    html = render_domain_strip_html(_quality(), _matrix())
    assert html.count("rr-domain-card") == 3
    assert "3.84%" in html and "+0.32%p" in html
    assert "4.99%" in html and "+0.02%p" in html
    assert "17.4" in html and "-1.2포인트" in html
    assert "큰 움직임 없음" not in html
    assert "평소" not in html


def test_credit_2x2_restores_numbers_and_hy_bbb_numbers():
    html = render_credit_range_map_html(_quality(), _matrix(), _aux())
    assert html.count("rr-credit-tile") >= 4
    for text in ("3.84%", "1.21%", "0.78%", "0.24%p"):
        assert text in html
    for text in ("+0.32%p", "+0.04%p", "+0.02%p", "-0.01%p"):
        assert text in html
    assert "HY−BBB" in html and "2.63%p" in html and "+0.06%p" in html
    assert "상승 조짐" in html and "특이 신호 없음" in html


def test_current_trend_has_no_duplicate_persistence_wording_or_normal_items():
    snap = {
        "credit": {"nodes": {
            "HY": {"source_status": "ok", "state": "newly_rising", "confirmed_at": "2026-07-01", "observed_date": "2026-07-07"},
            "A": {"source_status": "ok", "state": "normal"},
        }},
        "core": {"DGS30": {"state_code": "rise_watch", "drop_flag": False}},
    }
    html = render_remaining_changes_html(snap, {}, _matrix(), _aux())
    assert "현재 추세" in html
    assert "HY 상승 확인" in html and "7일째" in html
    assert "30Y 상승" in html and "1개월 +0.02%p" in html
    assert "지속 중" not in html
    assert "특이 신호 없음" not in html


def test_rate_tab_components_are_numeric_cards_and_three_column_table():
    overview = render_rate_overview_cards_html(_matrix())
    assert overview.count('<article class="rr-metric-card') == 4
    for text in ("4.99%", "3.88%", "2.24%", "0.42%p"):
        assert text in overview
    assert "급격한 상승 없음" in overview and "상승 신호" in overview

    curve = render_rate_curve_html(_rate_summary())
    assert "2Y" in curve and "30Y" in curve
    assert "-0.07%p" in curve and "+0.02%p" in curve

    scan = render_scan_html(_rate_summary())
    assert "4.99%" in scan and "+0.02%p" in scan
    assert "서로 일부 상쇄" in scan

    table = render_rate_change_table_html(_rate_summary())
    assert table.count("<th>") == 6
    assert "1개월" in table and "3개월" in table
    assert "실질 30Y" in table and "국채 금리 차이" in table


def test_rate_reference_indicators_are_cards_not_line_list():
    html = render_rate_reference_cards_html(_matrix(), _aux())
    assert html.count("rr-metric-card") == 2
    assert "실질 10Y" in html and "2.24%" in html and "+0.13%p" in html
    assert "Term Premium" in html and "0.73%" in html and "-0.03%p" in html
    assert "미국 30년 국채금리(30Y):" not in html


def test_date_selector_uses_only_common_exact_dates_and_renders_six_cards():
    rows = []
    for date in ("2026-07-07", "2026-07-08"):
        for idx, key in enumerate(("VIX", "HYOAS", "T10Y3M", "DGS30", "DGS2", "DFII10")):
            if date == "2026-07-08" and key == "DFII10":
                continue
            rows.append({
                "date": date, "key": key, "value": 1.0 + idx,
                "change_20obs": idx, "change_60obs": idx * 2,
                "state_code": "calm" if key == "VIX" else ("stable" if key in {"DGS30", "DGS2", "DFII10"} else "normal"),
                "state_label": "", "drop_flag": False,
            })
    chart = pd.DataFrame(rows)
    assert _common_date_choices(chart) == ["2026-07-07"]
    html = _date_cards_html(chart, "2026-07-07")
    assert html.count("rr-core-card") >= 6
    assert "2026-07-08" not in html


def test_latest_comparison_is_mobile_three_columns():
    latest = _signal_matrix_df(_matrix())
    assert list(latest.columns) == ["지표", "현재", "최근 변화"]
    assert latest["현재"].astype(str).str.contains("급격한 상승 없음|상승 신호|경계 신호 없음|특이 신호 없음|장기금리").any()


def test_v080_ui_has_rate_tab_and_date_selector_and_no_large_rate_panel_on_today():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert 'with gr.Tab("금리")' in source
    assert 'gr.Markdown("## 금리 현황")' in source
    assert 'gr.Markdown("---\\n\\n## 날짜별 지표 보기")' in source
    today = source[source.index('with gr.Tab("오늘")'):source.index('with gr.Tab("신용")')]
    assert "rate_scan_component" not in today
    assert _is_compatible_data_code_version("0.7.4", "0.8.0") is True
