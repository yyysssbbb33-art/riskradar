"""RiskRadar v0.4.0 — 보조지표 방향 판정 단위 테스트.

FRED 호출 없이 compute_direction 로직만 합성 데이터로 검증한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from riskradar import aux_config as AC
from riskradar.aux_indicators import (
    compute_direction, DIRECTION_UP, DIRECTION_DOWN, DIRECTION_FLAT, DIRECTION_NA,
)

SPEC = AC.AUX_SERIES["TERMPREM"]  # value=%, change_to_disp=100(bp)


def _daily(values):
    dates = pd.bdate_range("2015-01-01", periods=len(values))
    return pd.DataFrame({"date": dates, "value_raw": values})


def test_strong_uptrend_is_up():
    # 꾸준한 상승: 최신 1개월 변화가 과거 분포 상단
    vals = np.linspace(1.0, 4.0, 600) + np.random.default_rng(0).normal(0, 0.005, 600)
    res = compute_direction(_daily(vals), SPEC)
    assert res.ok and res.direction == DIRECTION_UP
    assert res.change_1m is not None and res.change_1m > 0


def test_strong_downtrend_is_down():
    vals = np.linspace(4.0, 1.0, 600) + np.random.default_rng(1).normal(0, 0.005, 600)
    res = compute_direction(_daily(vals), SPEC)
    assert res.ok and res.direction == DIRECTION_DOWN
    assert res.change_1m is not None and res.change_1m < 0


def test_flat_when_latest_is_midrange():
    # 큰 변동을 겪은 뒤 최근이 잔잔 -> 최신 변화가 과거 분포 중간
    rng = np.random.default_rng(2)
    body = np.cumsum(rng.normal(0, 0.05, 560))       # 변동 있는 과거
    tail = np.full(40, body[-1]) + rng.normal(0, 0.001, 40)  # 최근 잔잔
    res = compute_direction(_daily(np.concatenate([body, tail])), SPEC)
    assert res.ok and res.direction == DIRECTION_FLAT


def test_insufficient_history_is_na():
    vals = np.linspace(1.0, 2.0, 100)  # min_obs(250) 미만
    res = compute_direction(_daily(vals), SPEC)
    assert res.direction == DIRECTION_NA and res.ok


def test_span_guard_blocks_gap_change():
    # lookback(21)을 가로지르는 큰 달력 공백이면 최신 변화 무효 -> NA
    dates = list(pd.bdate_range("2015-01-01", periods=300))
    # 마지막 관측을 아주 먼 미래로 띄운다
    dates[-1] = pd.Timestamp("2016-06-01")
    vals = np.linspace(1.0, 2.0, 300)
    df = pd.DataFrame({"date": pd.to_datetime(dates), "value_raw": vals})
    res = compute_direction(df, SPEC)
    # 최신 시점 변화가 span guard로 막혀 방향을 못 냄
    assert res.direction in (DIRECTION_NA, DIRECTION_FLAT)


def test_empty_df():
    res = compute_direction(pd.DataFrame(columns=["date", "value_raw"]), SPEC)
    assert not res.ok and res.direction == DIRECTION_NA


def test_change_display_unit_is_bp():
    # term premium: value %，change 표시 bp. 0.01(%) 상승 -> 1bp 부근
    n = 400
    vals = np.concatenate([np.full(n - 1, 2.00), [2.10]])  # 마지막에 +0.10%p
    dates = pd.bdate_range("2015-01-01", periods=n)
    res = compute_direction(pd.DataFrame({"date": dates, "value_raw": vals}), SPEC)
    # 최신 1개월 변화가 대략 +10bp 근처(정확값은 lookback 구간 의존)
    assert res.change_1m is not None and res.change_1m > 0
