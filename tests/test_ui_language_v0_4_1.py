from tests import synth
from riskradar import pipeline
from riskradar.ui import _board_df, _signal_matrix_df


def test_user_tables_use_plain_korean_labels():
    matrix = pipeline.compute_all(synth.make_raw_by_key(n=1200))["signal_matrix"]
    board = _board_df(matrix)
    latest = _signal_matrix_df(matrix)

    assert {"약 1개월 변화", "약 3개월 변화", "최근 5년 중 현재 위치", "최근 10년 중 현재 위치"}.issubset(board.columns)
    assert list(latest.columns) == ["지표", "현재", "최근 변화"]
    assert latest["최근 변화"].astype(str).str.contains("1개월").all()
    assert latest["최근 변화"].astype(str).str.contains("3개월").all()
    assert not any(x in latest.columns for x in ("20obs", "60obs", "5Y%", "10Y%"))
