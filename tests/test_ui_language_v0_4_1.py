from tests import synth
from riskradar import pipeline
from riskradar.ui import _board_df, _signal_matrix_df


def test_user_tables_use_plain_korean_labels():
    matrix = pipeline.compute_all(synth.make_raw_by_key(n=1200))["signal_matrix"]
    board = _board_df(matrix)
    detail = _signal_matrix_df(matrix)
    for df in (board, detail):
        cols = set(df.columns)
        assert "약 1개월 변화" in cols
        assert "약 3개월 변화" in cols
        assert "최근 5년 중 현재 위치" in cols
        assert "최근 10년 중 현재 위치" in cols
        assert "20obs" not in cols
        assert "60obs" not in cols
        assert "5Y%" not in cols
        assert "10Y%" not in cols
