from __future__ import annotations

import pandas as pd
import pytest

from riskradar import rate_composition as RC


def _raw(values, start="2026-01-01"):
    return pd.DataFrame({
        "date": pd.bdate_range(start, periods=len(values)),
        "value_raw": values,
    })


def test_same_maturity_proxy_is_computed_once_from_common_dates():
    nominal = _raw([4.0, 4.1, 4.2])
    real = _raw([1.5, 1.6, 1.7])
    out = RC.build_composition_series(nominal, real)
    assert list(out.columns) == ["date", "DGS30", "DFII30", "INFLCOMP30"]
    assert out["INFLCOMP30"].tolist() == pytest.approx([2.5, 2.5, 2.5])


def test_primary_identity_holds_on_shared_series():
    n = 90
    nominal = _raw([4.0 + i * 0.002 for i in range(n)])
    real = _raw([1.5 + i * 0.001 for i in range(n)])
    series = RC.build_composition_series(nominal, real)
    summary = RC.build_summary(series, nominal, _raw([3.5 + i * 0.001 for i in range(n)]), pd.DataFrame())
    primary = summary["primary"]
    assert abs(primary["identity_residual_bp"]) < 1e-8
    assert primary["DGS30_change_bp"] == primary["DFII30_change_bp"] + primary["INFLCOMP30_change_bp"]


def test_bear_steepening_uses_same_20_observation_window():
    n = 80
    dgs30 = _raw([4.0] * 59 + [4.0 + i * 0.01 for i in range(21)])
    dgs2 = _raw([3.5] * 59 + [3.5 + i * 0.003 for i in range(21)])
    series = RC.build_composition_series(dgs30, _raw([1.5] * n))
    summary = RC.build_summary(series, dgs30, dgs2, pd.DataFrame())
    curve = summary["curve"]
    assert curve["lookback_obs"] == 20
    assert curve["code"] == "bear_steepening"
    assert "bear steepening" in curve["text"]


def test_long_up_short_down_is_not_mislabeled_bear_steepening():
    n = 80
    dgs30 = _raw([4.0] * 59 + [4.0 + i * 0.01 for i in range(21)])
    dgs2 = _raw([3.5] * 59 + [3.5 - i * 0.01 for i in range(21)])
    series = RC.build_composition_series(dgs30, _raw([1.5] * n))
    summary = RC.build_summary(series, dgs30, dgs2, pd.DataFrame())
    assert summary["curve"]["code"] == "long_up_short_down"
    assert "bear steepening" not in summary["curve"]["text"]


def test_small_changes_are_not_given_named_curve_regime():
    n = 80
    dgs30 = _raw([4.0 + i * 0.0005 for i in range(n)])
    dgs2 = _raw([3.5 + i * 0.0003 for i in range(n)])
    series = RC.build_composition_series(dgs30, _raw([1.5] * n))
    summary = RC.build_summary(series, dgs30, dgs2, pd.DataFrame())
    assert summary["curve"]["code"] == "no_clear_curve_move"


def test_markdown_separates_term_premium_from_30y_arithmetic():
    n = 90
    nominal = _raw([4.0 + i * 0.002 for i in range(n)])
    real = _raw([1.5 + i * 0.001 for i in range(n)])
    aux = pd.DataFrame([{
        "key": "TERMPREM", "latest_value": 0.8, "value_unit": "%",
        "change_1m": 12.0, "direction": "상승", "latest_date": "2026-05-01",
        "fetch_status": "ok", "staleness_label": "normal",
    }])
    summary = RC.build_summary(RC.build_composition_series(nominal, real), nominal, _raw([3.5] * n), aux)
    text = RC.render_markdown(summary)
    assert "같은 **30년 만기**" in text
    assert "물가보상 proxy" in text
    assert "10년 Term Premium은 별도 맥락" in text
    assert "산술 구성에 더하는 항목이 아닙니다" in text
