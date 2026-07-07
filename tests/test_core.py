import numpy as np
import pandas as pd
import pytest

from riskradar import config as C
from riskradar import pipeline, state_rules as SR, transforms as T
from tests import synth


@pytest.fixture(scope="module")
def raw_by_key():
    return synth.make_raw_by_key()


# ---- 단위 변환 ------------------------------------------------------------

def test_hyoas_percent_to_bp():
    r = synth.raw(pd.bdate_range("2020-01-01", periods=3),
                  np.array([3.56, 4.00, 5.00]))
    v = T.to_internal_value("HYOAS", r["value_raw"])
    assert list(v) == [356.0, 400.0, 500.0]


def test_t10y3m_pp_to_bp():
    r = synth.raw(pd.bdate_range("2020-01-01", periods=2), np.array([0.42, -0.10]))
    v = T.to_internal_value("T10Y3M", r["value_raw"])
    assert list(v) == [42.0, -10.0]


def test_rate_change_in_bp():
    df = T.build_series_frame("DGS30", synth.raw(
        pd.bdate_range("2020-01-01", periods=25), np.linspace(3.0, 3.30, 25)))
    # 0.30pp를 24스텝에 걸쳐 상승 -> 20스텝이면 0.25pp = 25bp
    assert df["change_20obs"].iloc[-1] == pytest.approx(25.0, abs=0.5)


# ---- calendar-span guard --------------------------------------------------

def test_calendar_span_guard_20obs():
    # 20 관측치인데 사이에 큰 달력 공백을 넣어 span > 45일 유도
    dates = list(pd.bdate_range("2020-01-01", periods=10))
    dates += list(pd.bdate_range("2020-06-01", periods=15))  # 큰 공백
    dates = pd.DatetimeIndex(dates)
    df = T.build_series_frame("DGS30",
                              synth.raw(dates, np.linspace(3, 4, len(dates))))
    # 마지막 관측의 20obs 이전이 공백 반대편이면 span>45 -> NaN
    assert np.isnan(df["change_20obs"].iloc[20])


def test_nan_change_no_rate_state():
    cfg = C.THRESHOLDS.rate
    assert SR._rate_candidate(np.nan, np.nan, cfg) == "stable"


# ---- 백분위 point-in-time ------------------------------------------------

def test_percentile_monotone_and_bounds(raw_by_key):
    df = T.build_series_frame("VIX", raw_by_key["VIX"])
    p = df["percentile_5y"].dropna()
    assert p.min() >= 0 and p.max() <= 100


def test_percentile_min_obs_nan_early(raw_by_key):
    df = T.build_series_frame("VIX", raw_by_key["VIX"])
    # 5년(500관측) 미만 구간은 NaN
    assert df["percentile_5y"].iloc[:400].isna().all()


# ---- anti-lookahead (핵심) -----------------------------------------------

@pytest.mark.parametrize("cut", [800, 1100, 1400])
def test_no_lookahead_metrics_and_states(raw_by_key, cut):
    full = pipeline.compute_frames(raw_by_key)
    cut_raw = {k: v.iloc[:cut].copy() for k, v in raw_by_key.items()}
    cutf = pipeline.compute_frames(cut_raw)
    cols = ["value", "change_20obs", "change_60obs", "percentile_3y",
            "percentile_5y", "percentile_10y", "state_code", "drop_flag"]
    for key in C.SERIES_ORDER:
        a = full[key].iloc[:cut][cols].reset_index(drop=True)
        b = cutf[key][cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b, check_dtype=False,
                                      obj=f"{key}@cut{cut}")


# ---- synced snapshot ------------------------------------------------------

def test_synced_snapshot_raw_intersection():
    rb = synth.make_raw_by_key(n=1200)
    # HY OAS만 마지막 3영업일 관측 누락 (raw에서 drop)
    rb["HYOAS"] = rb["HYOAS"].iloc[:-3].copy()
    frames = pipeline.compute_frames(rb)
    snap = T.synced_snapshot(frames)
    latest_hy = pd.to_datetime(frames["HYOAS"]["date"]).max()
    assert pd.to_datetime(snap["synced_date"]) == latest_hy
    assert snap["synced_staleness_days"] >= 1  # 다른 시리즈가 더 최신


def test_synced_empty_intersection():
    d1 = synth.raw(pd.bdate_range("2020-01-01", periods=10),
                   np.ones(10))
    d2 = synth.raw(pd.bdate_range("2021-01-01", periods=10),
                   np.ones(10))
    snap = T.synced_snapshot({"VIX": d1.assign(value=1.0),
                              "HYOAS": d2.assign(value=1.0)})
    assert snap["synced_date"] is None


# ---- 상태 전이 ------------------------------------------------------------

def test_rate_direct_to_shock():
    # 20obs 안에서 +40bp 급등 -> stable에서 rate_shock 직행 가능
    dates = pd.bdate_range("2020-01-01", periods=40)
    vals = np.concatenate([np.full(20, 3.0), np.linspace(3.0, 3.40, 20)])
    df = T.build_series_frame("DGS30", synth.raw(dates, vals))
    df = SR.attach_states("DGS30", df, C.THRESHOLDS)
    assert "rate_shock" in set(df["state_code"])


def test_rate_drop_is_flag_not_state():
    dates = pd.bdate_range("2020-01-01", periods=40)
    vals = np.concatenate([np.full(20, 4.0), np.linspace(4.0, 3.50, 20)])
    df = T.build_series_frame("DGS2", synth.raw(dates, vals))
    df = SR.attach_states("DGS2", df, C.THRESHOLDS)
    assert df["drop_flag"].iloc[-1]
    assert df["state_code"].iloc[-1] != "rate_shock"


def test_t10y3m_long_inverted():
    # 70영업일 연속 음수 -> long_inverted
    dates = pd.bdate_range("2020-01-01", periods=80)
    vals = np.concatenate([np.full(70, -0.5), np.full(10, -0.5)])  # 모두 역전
    df = T.build_series_frame("T10Y3M", synth.raw(dates, vals))
    df = SR.attach_states("T10Y3M", df, C.THRESHOLDS)
    assert df["state_code"].iloc[-1] == "long_inverted"


def test_t10y3m_seed_watch():
    dates = pd.bdate_range("2020-01-01", periods=3)
    df = T.build_series_frame("T10Y3M", synth.raw(dates, np.array([0.5, 0.6, 0.7])))
    df = SR.attach_states("T10Y3M", df, C.THRESHOLDS)
    assert df["state_code"].iloc[0] == "watch"


def test_state_recompute_deterministic(raw_by_key):
    a = pipeline.compute_frames(raw_by_key)["VIX"]["state_code"].tolist()
    b = pipeline.compute_frames(raw_by_key)["VIX"]["state_code"].tolist()
    assert a == b
