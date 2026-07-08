from __future__ import annotations

import pandas as pd

from tests import synth
from riskradar import pipeline
from riskradar.indicator_detail_view import render_indicator_detail
from riskradar.state_guidance import render_state_guidance


def _context():
    out = pipeline.compute_all(synth.make_raw_by_key(n=1200))
    chart = out["chart_data"]
    frames = {
        str(key): group.sort_values("date").reset_index(drop=True)
        for key, group in chart.groupby("key", sort=False)
    }
    aux = pd.DataFrame([
        {"key": "BREAKEVEN", "direction": "상승", "staleness_label": "normal"},
        {"key": "IGOAS", "direction": "보합", "staleness_label": "normal"},
        {"key": "TERMPREM", "direction": "하락", "staleness_label": "normal"},
    ])
    return out["signal_matrix"], frames, aux


def test_each_indicator_has_current_state_to_next_check_flow():
    matrix, frames, aux = _context()
    for key in ["VIX", "HYOAS", "T10Y3M", "DGS30", "DGS2", "DFII10"]:
        row = matrix.loc[matrix["key"] == key].iloc[0]
        md = render_state_guidance(key, row, frames=frames, aux_df=aux, matrix=matrix)
        assert "## 지금 이 상태에서 다음으로 볼 것" in md
        assert "왜 보나" in md
        assert "현재 결과:" in md
        assert "결과가 달라지면" in md
        assert "오르면" in md
        assert "내리면" in md
        assert "뚜렷한 변화가 없으면" in md


def test_dgs30_detail_shows_current_aux_result_and_alternative_branches():
    matrix, frames, aux = _context()
    row = matrix.loc[matrix["key"] == "DGS30"].iloc[0]
    md = render_indicator_detail(
        row, {}, "한줄 해석", frames=frames, aux_df=aux, matrix=matrix
    )
    assert "10년 일반·물가연동 국채금리 차이" in md
    assert "30년 금리 변화" in md
    assert "현재 결과: 오르는 중" in md
    assert "결과가 달라지면" in md
    assert "내리면:" in md
    assert "뚜렷한 변화가 없으면:" in md


def test_stale_aux_is_marked_and_not_presented_as_current_direction():
    matrix, frames, aux = _context()
    aux.loc[aux["key"] == "TERMPREM", "staleness_label"] = "stale"
    row = matrix.loc[matrix["key"] == "DGS30"].iloc[0]
    md = render_state_guidance("DGS30", row, frames=frames, aux_df=aux, matrix=matrix)
    assert "오래된 자료, 현재 해석에서 제외" in md
    assert "현재 결과: 확인 불가" in md
