from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from tests import synth
from riskradar import pipeline
from riskradar.axis_engine import composite_view
from riskradar.display_text import aux_name, core_name, plain_language, state_name
from riskradar.formatting import fmt_pct
from riskradar.indicator_detail_view import render_indicator_detail
from riskradar.interpretation_engine import read_all
from riskradar.relationship_guide import RELATIONSHIP_GUIDE
from riskradar.today_view import render_today_markdown
from riskradar.ui import _board_df, _history_table, _one_line_interpretation


def _context():
    out = pipeline.compute_all(synth.make_raw_by_key(n=1600))
    frames = out["frames"]
    matrix = out["signal_matrix"]
    aux_objs = {
        "BREAKEVEN": SimpleNamespace(direction="상승"),
        "IGOAS": SimpleNamespace(direction="보합"),
        "TERMPREM": SimpleNamespace(direction="하락"),
    }
    aux_status = {key: "normal" for key in aux_objs}
    aux_df = pd.DataFrame([
        {"key": "BREAKEVEN", "direction": "상승", "change_1m": 12.0, "change_unit": "bp", "staleness_label": "normal"},
        {"key": "IGOAS", "direction": "보합", "change_1m": 2.0, "change_unit": "bp", "staleness_label": "normal"},
        {"key": "TERMPREM", "direction": "하락", "change_1m": -8.0, "change_unit": "bp", "staleness_label": "normal"},
    ])
    dq = {
        "axes": composite_view(frames).to_dict(),
        "readings": [r.to_dict() for r in read_all(frames, aux_objs, aux_status)],
    }
    return frames, matrix, aux_df, dq


def test_cycle_states_describe_what_is_happening():
    assert state_name("normal") == "장기금리가 더 높음"
    assert state_name("watch", key="T10Y3M") == "두 금리가 거의 비슷함"
    assert state_name("inverted") == "단기금리가 더 높음"
    assert state_name("long_inverted") == "단기금리가 오래 더 높음"
    assert state_name("re_normalizing") == "장기금리가 다시 높아짐"
    assert state_name("re_normalized") == "장기금리가 다시 높은 상태가 이어짐"


def test_indicator_names_are_explanatory_not_market_acronyms():
    assert core_name("HYOAS") == "신용등급 낮은 기업의 추가금리"
    assert core_name("T10Y3M") == "10년 금리와 3개월 금리의 차이"
    assert core_name("DFII10") == "물가 영향을 뺀 10년 금리"
    assert aux_name("IGOAS") == "신용등급 높은 기업의 추가금리"
    assert aux_name("TERMPREM") == "장기채 추가 보상"


def test_historical_position_reads_as_rank_not_probability():
    assert fmt_pct(82) == "상위 18% 구간"
    assert fmt_pct(12) == "하위 12% 구간"


def test_current_board_uses_plain_columns_and_names():
    _, matrix, _, _ = _context()
    board = _board_df(matrix)
    assert "지금 뜻" in board.columns
    assert "왜 이렇게 표시됐나" in board.columns
    assert "최근 5년 중 현재 위치" in board.columns
    assert "최근 10년 중 현재 위치" in board.columns
    text = "\n".join(board.astype(str).to_numpy().ravel())
    assert "HY OAS" not in text
    assert "20obs" not in text
    assert "60obs" not in text


def test_full_render_does_not_leak_old_jargon():
    frames, matrix, aux_df, dq = _context()
    parts = [render_today_markdown(dq, aux_df)]
    for _, row in matrix.iterrows():
        parts.append(render_indicator_detail(
            row,
            dq,
            _one_line_interpretation(row),
            frames=frames,
            aux_df=aux_df,
            matrix=matrix,
        ))
    parts.append(plain_language(RELATIONSHIP_GUIDE))
    text = "\n".join(parts)

    forbidden = [
        "재정상화", "역전 해소", "오래된 역전", "장기 역전",
        "복합 조망", "기준상 변화", "HY OAS", "IG OAS",
        "Term Premium", "Breakeven", "실질금리", "명목금리",
        "인플레이션 보상", "정책경로", "평탄화", "판정불가",
        "변동성·신용", "경기 사이클", "하이일드", "투자등급 신용스프레드",
        "수익률곡선", "시장 기반 물가전망", "장기채 추가보상",
        "저신용 기업",
    ]
    for word in forbidden:
        assert word not in text, word


def test_recent_history_table_builds_with_plain_drop_column():
    _, matrix, _, _ = _context()
    history = matrix.copy()
    history.insert(0, "cache_version", "2026-07-05T08-00-00KST")
    history.insert(1, "snapshot_at_kst", "2026-07-05 08:00:00")
    history.insert(2, "snapshot_date", "2026-07-05")
    table = _history_table(history, "VIX")
    assert "빠르게 내림" in table.columns
    assert "빠른 하락" not in table.columns
