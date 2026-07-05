"""RiskRadar v0.4.0 — '오늘의 해석' 렌더링 테스트 (gradio 비의존)."""
from __future__ import annotations

import pandas as pd

from riskradar.today_view import render_today_markdown


def _dq(with_reading=True):
    axes = {
        "summary_line": "현재 3축 중 2축에서 기준상 변화",
        "changed_axes": ["금리 방향", "변동성·신용"],
        "base_axes": ["경기 사이클"],
        "vol_credit": {"label": "변동성·신용 동반", "note": "둘 다 변화 상태입니다."},
        "cycle": {"label": "정상"},
        "rate": {"result": "혼합 방향",
                 "members": {"DGS30": "상승", "DGS2": "하락", "DFII10": "상승"}},
        "disclaimer": "축 요약은 내부 참고 규칙(C등급)입니다.",
    }
    readings = []
    if with_reading:
        readings = [{
            "combo_id": "rates_30up_2down",
            "label": "장기금리 상승·단기금리 하락",
            "observed": "30년물 상승, 2년물 하락 방향입니다.",
            "explanations": [{"id": "real", "text": "실질금리 상승 설명"}],
            "checks": [{"key": "DFII10", "label": "실질금리", "direction": "상승",
                        "text": "10Y Real 상승 → real 지지."}],
            "supported_ids": ["real"],
            "conflict": "",
            "uncertainty": "원인이 하나가 아닐 수 있습니다.",
        }]
    return {"axes": axes, "readings": readings}


def _aux_df():
    return pd.DataFrame([
        {"display_name": "10Y Breakeven", "direction": "상승", "change_1m": 12.0,
         "change_unit": "bp", "latest_date": "2026-07-03"},
        {"display_name": "IG OAS", "direction": "보합", "change_1m": 2.0,
         "change_unit": "bp", "latest_date": "2026-07-03"},
        {"display_name": "10Y Term Premium (KW)", "direction": "판정불가",
         "change_1m": None, "change_unit": "bp", "latest_date": None},
    ])


def test_renders_axes_and_reading():
    md = render_today_markdown(_dq(), _aux_df())
    assert "3개 영역 중 2개" in md
    assert "주식시장과 회사채가 함께 움직임" in md
    assert "장기금리 상승·단기금리 하락" in md
    assert "10Y Real 상승" in md


def test_aux_directions_shown():
    md = render_today_markdown(_dq(), _aux_df())
    assert "채권시장이 보는 10년 물가 예상" in md and "오르는 중" in md
    assert "확인 불가" in md  # 장기채 추가보상


def test_no_reading_message():
    md = render_today_markdown(_dq(with_reading=False), _aux_df())
    assert "따로 설명할 만한 패턴이 잡히지 않았습니다" in md


def test_empty_dq_shows_placeholder():
    md = render_today_markdown({}, pd.DataFrame())
    assert "여러 지표를 같이 본 결과를 계산할 수 없습니다" in md
    assert "확인 지표 데이터가 없습니다" in md


def test_no_directive_language():
    md = render_today_markdown(_dq(), _aux_df())
    # 행동 지시형 표현만 금지 (disclaimer의 '매수·매도를 제공하지 않습니다'는 원칙 선언)
    for w in ["위험합니다", "안전합니다", "조심하", "매수하", "매도하", "팔아야", "사야"]:
        assert w not in md


def test_disclaimer_present():
    md = render_today_markdown(_dq(), _aux_df())
    assert "매수·매도" in md and "제시하지 않습니다" in md
