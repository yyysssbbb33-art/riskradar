from __future__ import annotations

import pandas as pd

from riskradar.monthly_view import reconstruct_history_from_chart_data
from riskradar.ui import _data_generation_info, _history_table


def _chart_rows(days: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2026-05-25", periods=days, freq="D")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "series_id": "DGS2",
            "key": "DGS2",
            "date": d,
            "value": 4.0 + i * 0.01,
            "change_20obs": 20.0,
            "change_60obs": 30.0,
            "percentile_5y": 70.0,
            "percentile_10y": 60.0,
            "state_code": "stable",
            "state_label": "안정",
            "drop_flag": False,
        })
    return pd.DataFrame(rows)


def test_reconstruct_30d_from_chart_data_without_snapshots():
    history = reconstruct_history_from_chart_data(_chart_rows(), days=30)
    assert not history.empty
    assert set(history["history_source"]) == {"reconstructed"}
    assert history["snapshot_date"].max() == "2026-07-03"
    assert history["snapshot_date"].min() == "2026-06-03"
    assert history["key"].eq("DGS2").all()


def test_reconstructed_history_table_uses_observation_date_not_saved_date():
    history = reconstruct_history_from_chart_data(_chart_rows(), days=30)
    table = _history_table(history, "DGS2")
    assert "관측일" in table.columns
    assert "저장일" not in table.columns
    assert "저장시각(KST)" not in table.columns


def test_missing_code_version_means_old_metadata_not_missing_data():
    info = _data_generation_info(
        {"active_cache_version": "2026-07-05T08-30-00KST"},
        {},
    )
    assert info["code_version_missing"] == "yes"
    assert info["code_version"] == "기록되지 않음 (구버전 데이터)"
    assert info["generated_at"] == "2026-07-05 08:30 KST"


def test_generation_info_prefers_recorded_batch_version():
    info = _data_generation_info(
        {
            "active_cache_version": "2026-07-05T08-30-00KST",
            "last_refresh_finished_at": "2026-07-05T08:31:00+09:00",
            "code_version": "0.4.8",
        },
        {},
    )
    assert info["code_version_missing"] == "no"
    assert info["code_version"] == "0.4.8"
    assert info["generated_at"] == "2026-07-05T08:31:00+09:00"
