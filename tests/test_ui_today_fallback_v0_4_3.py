from __future__ import annotations

import pandas as pd

from riskradar import pipeline
from riskradar.ui import _today_context_with_fallback
from synth import make_raw_by_key


def _aux_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "BREAKEVEN10Y", "direction": "보합", "staleness_label": "normal"},
        {"key": "IGOAS", "direction": "보합", "staleness_label": "normal"},
        {"key": "TERM10Y", "direction": "보합", "staleness_label": "normal"},
    ])


def test_fallback_builds_axes_from_old_cache_without_axes_or_readings():
    out = pipeline.compute_all(make_raw_by_key())
    dq = _today_context_with_fallback({}, {"chart_data": out["chart_data"]}, _aux_df())
    assert dq.get("axes")
    assert dq["axes"]["summary_line"].startswith("현재 3개 영역 중")
    assert "readings" in dq


def test_existing_axes_and_readings_are_preserved():
    original = {"axes": {"sentinel": True}, "readings": [{"combo_id": "keep"}]}
    dq = _today_context_with_fallback(original, {"chart_data": pd.DataFrame()}, pd.DataFrame())
    assert dq == original


def test_fallback_does_not_require_aux_cache_for_axes():
    out = pipeline.compute_all(make_raw_by_key())
    dq = _today_context_with_fallback({}, {"chart_data": out["chart_data"]}, pd.DataFrame())
    assert dq.get("axes")
    assert "readings" in dq


def test_old_readings_without_branches_are_upgraded_when_chart_data_exists():
    out = pipeline.compute_all(make_raw_by_key())
    old = {
        "axes": {"sentinel": True},
        "readings": [
            {
                "combo_id": "old",
                "checks": [{"key": "BREAKEVEN", "direction": "상승", "text": "old"}],
            }
        ],
    }
    dq = _today_context_with_fallback(old, {"chart_data": out["chart_data"]}, _aux_df())
    for reading in dq.get("readings", []):
        for check in reading.get("checks", []):
            assert check.get("branches"), check
