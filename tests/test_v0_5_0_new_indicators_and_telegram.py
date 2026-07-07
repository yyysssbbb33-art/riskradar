"""v0.5.0 — 신규 확인지표, 용어, Telegram 요약 회귀 테스트."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from riskradar import aux_config as AC
from riskradar import aux_indicators as AI
from riskradar import fred_client as FC
from riskradar import interpretation_engine as IE
from riskradar import telegram_client as TG
from riskradar.display_text import AUX_NAMES
from riskradar.today_view import render_today_markdown


def _weekly(values):
    return pd.DataFrame({
        "date": pd.date_range("2020-01-03", periods=len(values), freq="W-FRI"),
        "value_raw": values,
    })


def test_user_facing_terms_are_fixed():
    assert AUX_NAMES["CPSPREAD"] == "기업 신용도에 따른 단기자금 금리 차이"
    assert AUX_NAMES["BBBOAS"] == "투자등급 경계 기업의 추가금리"
    assert AUX_NAMES["NFCI"] == "미국 금융시장 전반의 자금 사정"
    assert AUX_NAMES["STLFSI"] == "미국 금융시장 전반의 불안"


def test_cp_spread_is_a2p2_minus_aa_on_matching_dates(monkeypatch):
    dates = pd.bdate_range("2025-01-01", periods=400)
    a2p2 = pd.DataFrame({"date": dates, "value_raw": np.linspace(4.0, 4.8, 400)})
    aa = pd.DataFrame({"date": dates, "value_raw": np.linspace(3.8, 4.0, 400)})

    def fake_fetch(series_id, out_key, api_key, timeout, start):
        if series_id == "RIFSPPNA2P2D30NB":
            return FC.FetchResult(out_key, True, a2p2)
        if series_id == "RIFSPPNAAD30NB":
            return FC.FetchResult(out_key, True, aa)
        # 나머지 확인지표는 이 테스트 관심 밖이므로 실패로 반환
        return FC.FetchResult(out_key, False, None, "skip")

    monkeypatch.setattr(FC, "_resolve_creds", lambda api_key, timeout: ("x", 1.0))
    monkeypatch.setattr(FC, "fetch_fred_series", fake_fetch)

    out = AI.collect_aux(api_key="x", timeout=1.0, max_attempts=1)
    cp = out["CPSPREAD"]
    assert cp.ok
    # 마지막 원시 차이는 0.8%p, 내부 표시는 bp이므로 약 80bp
    assert cp.latest_value is not None and abs(cp.latest_value - 80.0) < 1e-6
    assert cp.direction == AI.DIRECTION_UP


def test_weekly_reference_uses_four_observation_change():
    # 4주 전 대비 최근 상승이 뚜렷하도록 구성한다.
    vals = np.concatenate([np.linspace(-1.0, 0.0, 180), np.linspace(0.0, 2.0, 20)])
    res = AI.compute_direction(_weekly(vals), AC.AUX_SERIES["STLFSI"])
    assert res.ok
    assert res.n_obs >= 100
    assert res.change_1m is not None and res.change_1m > 0
    assert res.level_pct is not None and res.level_pct > 90


def test_external_references_are_not_engine_inputs():
    assert "NFCI" not in AC.ENGINE_AUX_ORDER
    assert "STLFSI" not in AC.ENGINE_AUX_ORDER
    assert "BBBOAS" in AC.ENGINE_AUX_ORDER
    assert "CPSPREAD" in AC.ENGINE_AUX_ORDER


def test_bbb_can_confirm_credit_widening_without_a():
    frames = {}
    ctx = SimpleNamespace()
    # ReadingContext 메서드 자체를 최소 의존으로 직접 검증한다.
    rc = IE.ReadingContext(
        frames=frames,
        aux={
            "BBBOAS": SimpleNamespace(direction="상승"),
            "AOAS": SimpleNamespace(direction="보합"),
        },
        aux_status={"BBBOAS": "normal", "AOAS": "normal"},
        vc=SimpleNamespace(hy_active=False),
        cycle=SimpleNamespace(),
        rate=SimpleNamespace(members={}),
    )
    assert rc.credit_widening()


def _aux_df_for_view():
    rows = []
    for key, direction, level_pct in [
        ("BREAKEVEN", "상승", 70.0),
        ("TERMPREM", "하락", 30.0),
        ("BBBOAS", "상승", 80.0),
        ("AOAS", "보합", 50.0),
        ("CPSPREAD", "상승", 85.0),
        ("NFCI", "상승", 75.0),
        ("STLFSI", "보합", 20.0),
    ]:
        rows.append({
            "key": key,
            "display_name": AC.AUX_SERIES[key].display_name,
            "latest_value": 1.0,
            "latest_date": "2026-07-03",
            "change_1m": 5.0,
            "change_unit": "bp" if key not in {"NFCI", "STLFSI"} else "지수",
            "direction": direction,
            "level_pct": level_pct,
            "staleness_label": "normal",
            "fetch_status": "ok",
        })
    return pd.DataFrame(rows)


def test_today_view_groups_new_indicators_by_question():
    md = render_today_markdown({}, _aux_df_for_view())
    assert "장기금리가 왜 움직이나" in md
    assert "기업 부담이 어디까지 번졌나" in md
    assert "단기 자금시장도 영향을 받고 있나" in md
    assert "외부 종합 참고" in md
    assert "기업 신용도에 따른 단기자금 금리 차이" in md
    assert "투자등급 경계 기업의 추가금리" in md
    assert "RiskRadar 해석 엔진에 넣지 않고" in md


def test_telegram_summarizes_axes_instead_of_listing_six_rows():
    matrix = pd.DataFrame([
        {"key": "VIX", "state_code": "calm", "state_label": "calm", "drop_flag": False},
        {"key": "HYOAS", "state_code": "neutral", "state_label": "neutral", "drop_flag": False},
    ])
    axes = {
        "changed_count": 2,
        "vol_credit": {"state": "B"},
        "cycle": {"state": "re_normalizing", "label": ""},
        "rate": {"result": "혼합 방향"},
    }
    readings = [{"label": "30년물 상승 · 2년물 하락"}]
    text = TG.build_success(
        "2026-07-06 08:30 KST", "cv", matrix, {"synced_date": "2026-07-03"}, [],
        axes=axes, readings=readings, aux_df=_aux_df_for_view(),
    )
    assert "현재 3개 영역 중 2개" in text
    assert "주식시장 쪽만 움직임" in text
    assert "눈에 띄는 조합" in text
    assert "기업 신용 범위와 지속" in text and "단기자금" in text and "외부 참고" in text
    assert "캐시:" not in text
