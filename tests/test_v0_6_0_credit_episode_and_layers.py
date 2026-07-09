"""v0.6.0 — 기업 신용 범위·지속 엔진과 3층 지표 구조 회귀 테스트."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from riskradar import aux_config as AC
from riskradar import config as C
from riskradar import pipeline
from riskradar.credit_episode import (
    CreditEpisodeCfg,
    NODE_ORDER,
    build_credit_episode,
)
from riskradar.credit_episode_validation import calm_window_false_positive_rate, threshold_sensitivity
from riskradar.credit_lens_card import HY_BBB_CARD
from riskradar.display_text import LABEL_3Y
from riskradar.transforms import point_in_time_percentile


def _frame(values, start="2025-01-02"):
    return pd.DataFrame({
        "date": pd.bdate_range(start, periods=len(values)),
        "value": np.asarray(values, dtype=float),
    })


def _cfg(**kwargs):
    base = CreditEpisodeCfg(
        regime_years=3,
        fast_lookback=3,
        slow_lookback=8,
        min_history_obs=35,
        candidate_pct=80,
        confirm_obs=3,
        baseline_obs=5,
        baseline_noise_obs=15,
        new_state_obs=4,
        normalize_confirm_obs=2,
        retrace_ratio=0.30,
        normalize_peak_ratio=0.20,
        dormant_obs=6,
        engine_window_obs=90,
    )
    return replace(base, **kwargs)


def test_three_layer_indicator_structure_and_broad_ig_is_hidden():
    assert AC.CONFIRM_AUX_ORDER == ["BREAKEVEN", "TERMPREM", "BBBOAS", "AOAS", "CPSPREAD"]
    assert AC.EXTERNAL_AUX_ORDER == ["NFCI", "STLFSI"]
    assert "IGOAS" not in AC.VISIBLE_AUX_ORDER
    assert AC.AUX_SERIES["IGOAS"].visible is False
    assert AC.AUX_SERIES["IGOAS"].use_in_engine is False
    assert "AOAS" in AC.ENGINE_AUX_ORDER
    assert "NFCI" not in AC.ENGINE_AUX_ORDER


def test_credit_nodes_are_real_markets_and_hy_bbb_is_only_a_lens():
    assert NODE_ORDER == ("HY", "BBB", "A", "CP")
    assert "HY_BBB" not in NODE_ORDER
    assert "별도 시장" in HY_BBB_CARD
    assert "이중계상" in HY_BBB_CARD


def test_ice_company_bond_core_position_is_three_year_only():
    assert C.SERIES["HYOAS"].position_years == (3,)
    assert LABEL_3Y == "최근 3년 중 현재 위치"


def test_long_window_percentile_requires_real_calendar_coverage():
    dates = pd.bdate_range("2020-01-01", periods=800)  # 약 3년
    values = pd.Series(np.linspace(1.0, 2.0, len(dates)))
    p5 = point_in_time_percentile(values, pd.Series(dates), 5, 500)
    assert p5.dropna().empty
    p3 = point_in_time_percentile(values, pd.Series(dates), 3, 500)
    assert not p3.dropna().empty


def test_pipeline_does_not_fake_hy_five_or_ten_year_position():
    dates = pd.bdate_range("2023-01-02", periods=800)
    raw = pd.DataFrame({"date": dates, "value_raw": np.linspace(3.0, 4.0, len(dates))})
    frame = pipeline.compute_frames({"HYOAS": raw})["HYOAS"]
    assert frame["percentile_5y"].isna().all()
    assert frame["percentile_10y"].isna().all()
    assert frame["percentile_3y"].notna().any()


def test_early_change_is_not_counted_as_official_scope():
    values = np.r_[np.full(60, 300.0), 310.0, 320.0, np.full(8, 320.0)]
    result = build_credit_episode({"HY": _frame(values)}, cfg=_cfg(confirm_obs=3))
    # 후보가 2관측만 이어진 시점의 별도 run에서는 공식 참여 전이다.
    partial = build_credit_episode({"HY": _frame(values[:62])}, cfg=_cfg(confirm_obs=3))
    assert partial.current["nodes"]["HY"]["state"] == "early_change"
    assert "상승 조짐" in partial.current["scope_text"]
    assert partial.current["episode"]["state"] == "none"
    assert result.current["nodes"]["HY"]["state"] in {"newly_rising", "rising_persistent", "dormant", "retracing"}


def test_confirmed_event_freezes_onset_and_pre_event_baseline():
    values = np.r_[np.full(60, 300.0), 310.0, 320.0, 330.0, 340.0, np.full(8, 340.0)]
    result = build_credit_episode({"HY": _frame(values)}, cfg=_cfg())
    h = result.node_history.loc[result.node_history["node"] == "HY"].sort_values("date")
    confirmed = h.loc[h["confirmed_today"].astype(bool)].iloc[0]
    assert pd.Timestamp(confirmed["estimated_onset"]) < pd.Timestamp(confirmed["confirmed_at"])
    assert confirmed["baseline"] == 300.0
    # 이후 행에서도 동결된 onset/baseline 유지
    after = h.loc[h["event_id"].notna()]
    assert after["baseline"].nunique() == 1
    assert after["estimated_onset"].nunique() == 1


def test_range_engine_separates_hy_bbb_a_cp_and_lens():
    n = 90
    hy = np.r_[np.full(60, 300.0), np.linspace(310, 380, 8), np.full(n - 68, 380.0)]
    bbb = np.r_[np.full(64, 120.0), np.linspace(125, 155, 6), np.full(n - 70, 155.0)]
    a = np.full(n, 80.0)
    cp = np.full(n, 20.0)
    result = build_credit_episode(
        {"HY": _frame(hy), "BBB": _frame(bbb), "A": _frame(a), "CP": _frame(cp)},
        cfg=_cfg(dormant_obs=50),
    )
    participants = set(result.current["episode"]["participants"])
    assert {"HY", "BBB"}.issubset(participants)
    assert "A" not in participants and "CP" not in participants
    assert result.lens["available"]
    assert "HY_BBB" not in participants


def test_dormant_episode_and_reexpansion_create_new_episode_with_prior_residual():
    # 첫 상승 후 긴 정체로 휴면, 이후 같은 HY가 다시 새 고점을 만들면 새 에피소드.
    values = np.r_[
        np.full(55, 300.0),
        310.0, 325.0, 340.0, 350.0,
        np.full(12, 350.0),
        365.0, 380.0, 395.0,
        np.full(8, 395.0),
    ]
    result = build_credit_episode({"HY": _frame(values)}, cfg=_cfg(dormant_obs=5))
    assert len(result.episodes) >= 2
    last = result.episodes.iloc[-1]
    assert "HY" in str(last["participants"])
    assert "HY" in str(last["prior_residual_nodes"])


def test_cp_year_end_is_diagnostic_not_signal_deletion():
    values = np.r_[np.full(55, 20.0), 25.0, 30.0, 35.0, np.full(10, 35.0)]
    result = build_credit_episode({"CP": _frame(values, start="2025-09-01")}, cfg=_cfg())
    ctx = result.current["cp_calendar_context"]
    assert ctx["available"]
    # 마지막 날짜가 12월이면 진단 플래그만 붙고 노드 데이터는 그대로 남는다.
    if pd.Timestamp(result.current["nodes"]["CP"]["date"]).month == 12:
        assert ctx["year_end"] is True
        assert result.current["nodes"]["CP"]["available"] is True


def test_validation_helpers_measure_calm_false_positives_and_sensitivity():
    values = np.r_[np.full(60, 300.0), np.linspace(305, 350, 6), np.full(20, 350.0)]
    frames = {"HY": _frame(values)}
    result = build_credit_episode(frames, cfg=_cfg())
    calm = calm_window_false_positive_rate(result.node_history, "2025-01-02", "2025-02-28")
    assert calm["observations"] > 0
    assert calm["false_positive_rate"] == 0.0
    sens = threshold_sensitivity(frames, cfg=_cfg(), deltas=(-2.0, 0.0, 2.0))
    assert list(sens["delta_pct_point"]) == [-2.0, 0.0, 2.0]
    assert sens["participant_set_jaccard_vs_base"].between(0, 1).all()


def _recent_core_fetcher():
    from riskradar.fred_client import FetchResult
    from tests.synth import make_raw_by_key

    raw_by_key = make_raw_by_key(n=900)
    dates = pd.bdate_range(end="2026-07-03", periods=900)
    for df in raw_by_key.values():
        df["date"] = dates
    return lambda: {k: FetchResult(k, True, v.copy()) for k, v in raw_by_key.items()}


def _aux_bundle(*, omit: set[str] | None = None):
    from riskradar import aux_indicators as AI

    omit = omit or set()
    dates = pd.bdate_range(end="2026-07-03", periods=800)
    bases = {
        "BREAKEVEN": 2.1,
        "TERMPREM": 0.2,
        "BBBOAS": 1.2,
        "AOAS": 0.8,
        "CPSPREAD": 0.2,
        "NFCI": -0.3,
        "STLFSI": -0.4,
        "IGOAS": 1.0,
    }
    directions = {}
    raw_frames = {}
    for key in AC.AUX_ORDER:
        if key in omit:
            continue
        vals = np.full(len(dates), bases[key], dtype=float)
        # 마지막 한 달에 작지만 뚜렷한 상승 경로를 넣어 원자료가 실제 엔진 입력이 되게 한다.
        vals[-25:] += np.linspace(0.0, 0.15 if key not in {"NFCI", "STLFSI"} else 0.05, 25)
        df = pd.DataFrame({"date": dates, "value_raw": vals})
        raw_frames[key] = df
        directions[key] = AI.compute_direction(df, AC.AUX_SERIES[key])
    return AI.AuxCollection(directions=directions, raw_frames=raw_frames)


def test_refresh_publishes_credit_artifacts_and_snapshot_reads_same_version(monkeypatch, tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from riskradar.cache_store import LocalStore
    from riskradar.dashboard_snapshot import load_dashboard_snapshot
    from riskradar.refresh_service import run_refresh

    kst = ZoneInfo("Asia/Seoul")
    times = iter([
        datetime(2026, 7, 6, 8, 0, tzinfo=kst),
        datetime(2026, 7, 6, 8, 1, tzinfo=kst),
    ])
    monkeypatch.setattr("riskradar.refresh_service._now_kst", lambda: next(times))

    store = LocalStore(tmp_path)
    status = run_refresh(
        fetcher=_recent_core_fetcher(),
        aux_fetcher=lambda: _aux_bundle(),
        store=store,
        notify=False,
    )
    cv = status["active_cache_version"]
    assert not store.load_artifact(cv, "aux_raw").empty
    assert not store.load_artifact(cv, "credit_episode_nodes").empty
    assert "ice_history_policy" in store.load_data_quality(cv)

    snap = load_dashboard_snapshot(store)
    assert snap.status["active_cache_version"] == cv
    assert not snap.aux_raw.empty
    assert not snap.credit_node_history.empty
    assert set(snap.credit_node_history["node"].unique()).issuperset({"HY", "BBB", "A", "CP"})


def test_aux_raw_recovery_keeps_a_node_path_after_temporary_fetch_failure(monkeypatch, tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from riskradar.cache_store import LocalStore
    from riskradar.refresh_service import run_refresh

    kst = ZoneInfo("Asia/Seoul")
    times = iter([
        datetime(2026, 7, 6, 8, 0, tzinfo=kst),
        datetime(2026, 7, 6, 8, 1, tzinfo=kst),
        datetime(2026, 7, 6, 9, 0, tzinfo=kst),
        datetime(2026, 7, 6, 9, 1, tzinfo=kst),
    ])
    monkeypatch.setattr("riskradar.refresh_service._now_kst", lambda: next(times))

    store = LocalStore(tmp_path)
    first = run_refresh(
        fetcher=_recent_core_fetcher(),
        aux_fetcher=lambda: _aux_bundle(),
        store=store,
        notify=False,
    )
    first_cv = first["active_cache_version"]
    assert not store.find_last_good_aux_raw("AOAS").empty

    second = run_refresh(
        fetcher=_recent_core_fetcher(),
        aux_fetcher=lambda: _aux_bundle(omit={"AOAS"}),
        store=store,
        notify=False,
    )
    second_cv = second["active_cache_version"]
    assert second_cv != first_cv
    aux_matrix = store.load_artifact(second_cv, "aux_signal_matrix")
    arow = aux_matrix.loc[aux_matrix["key"] == "AOAS"].iloc[-1]
    assert arow["fetch_status"] == "carried_forward"
    assert arow["staleness_label"] != "stale"

    recovered_raw = store.load_artifact(second_cv, "aux_raw")
    assert not recovered_raw.loc[recovered_raw["key"] == "AOAS"].empty
    nodes = store.load_artifact(second_cv, "credit_episode_nodes")
    assert "A" in set(nodes["node"].astype(str))


def test_telegram_keeps_results_before_credit_range_and_interpretation():
    from riskradar import telegram_client as TG

    matrix = pd.DataFrame([
        {"key": "VIX", "latest_value": 18.4, "value_unit": "index", "change_20obs": 2.1, "change_60obs": -0.4, "change_unit": "pt", "state_code": "calm", "state_label": "calm", "drop_flag": False},
        {"key": "HYOAS", "latest_value": 345.0, "value_unit": "bp", "change_20obs": 12.0, "change_60obs": 28.0, "change_unit": "bp", "state_code": "neutral", "state_label": "neutral", "drop_flag": False},
    ])
    bundle = _aux_bundle()
    aux_rows = []
    for key in AC.AUX_ORDER:
        d = bundle.directions[key]
        spec = AC.AUX_SERIES[key]
        aux_rows.append({
            "key": key,
            "latest_value": d.latest_value,
            "value_unit": spec.value_unit,
            "change_1m": d.change_1m,
            "change_unit": spec.change_unit,
            "direction": d.direction,
            "level_pct": d.level_pct,
            "staleness_label": "normal",
        })
    aux_df = pd.DataFrame(aux_rows)
    credit = {
        "current": {
            "episode": {"state_label": "활성", "participants": ["HY", "BBB"]},
            "scope_text": "신용등급 낮은 기업과 투자등급 경계 기업이 참여",
            "nodes": {
                "HY": {"available": True, "state_label": "상승 지속"},
                "BBB": {"available": True, "state_label": "새로 상승"},
                "A": {"available": True, "state_label": "정상"},
                "CP": {"available": True, "state_label": "정상"},
            },
            "cp_calendar_context": {"year_end": False},
        },
        "lens": {"available": True, "latest_value_bp": 213.0, "change_1m_bp": 8.0, "label": "저신용 기업 쪽 부담이 더 강함"},
        "vix_context": {"available": True, "onset": "시작 무렵 주식시장 불안도 있었음", "current": "현재는 진정"},
    }
    axes = {
        "changed_count": 1,
        "vol_credit": {"state": "C"},
        "cycle": {"state": "normal", "label": ""},
        "rate": {"result": "변화 없음"},
    }
    text = TG.build_success(
        "2026-07-06 08:30 KST", "cv", matrix, {"synced_date": "2026-07-03"}, [],
        axes=axes, readings=[], aux_df=aux_df, credit_episode=credit,
    )
    assert "투기등급-투자등급 경계 차이: 2.13%p · 약 1개월 +0.08%p" in text
    assert "기업 신용" in text
    assert "신용등급 낮은 기업과 투자등급 경계 기업이 참여" in text
    assert text.index("핵심 지표") < text.index("기업 신용")
    assert text.index("기업 신용") < text.index("여러 지표를 같이 보면")
    assert "신용등급 높은 기업의 추가금리" not in text
    assert len(text) <= 3900
