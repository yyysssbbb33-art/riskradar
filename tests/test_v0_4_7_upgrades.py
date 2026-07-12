from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar import aux_indicators as AI
from riskradar import cache_store as CS
from riskradar.external_guidance import render_external_guidance
from riskradar.formatting import fmt_pct
from riskradar.fred_client import FetchResult
from riskradar.monthly_view import render_monthly_markdown


def test_past_position_uses_top_bottom_or_middle_zone():
    assert fmt_pct(82) == "상위 18% 구간"
    assert fmt_pct(13) == "하위 13% 구간"
    assert fmt_pct(50) == "중간 구간"


def test_aux_collection_retries_each_failed_series(monkeypatch):
    calls: list[str] = []
    dates = pd.bdate_range("2024-01-01", periods=320)
    good_df = pd.DataFrame({"date": dates, "value_raw": [2.0 + i * 0.001 for i in range(len(dates))]})

    def fake_fetch(series_id, out_key, api_key, timeout, start):
        calls.append(out_key)
        if len(calls) == 1:
            return FetchResult(out_key, False, None, "temporary timeout")
        return FetchResult(out_key, True, good_df.copy(), None)

    monkeypatch.setattr(AI.AC, "AUX_ORDER", ["BREAKEVEN"])
    monkeypatch.setattr(AI.FC, "fetch_fred_series", fake_fetch)
    result = AI.collect_aux(api_key="test", timeout=1, max_attempts=2)

    assert calls == ["BREAKEVEN", "BREAKEVEN"]
    assert result["BREAKEVEN"].ok is True


def test_last_good_aux_search_skips_newer_carried_forward_rows(tmp_path: Path):
    store = CS.LocalStore(tmp_path)
    versions = [
        "2026-07-01T08-00-00KST",
        "2026-07-02T08-00-00KST",
        "2026-07-03T08-00-00KST",
    ]
    rows = [
        {"key": "IGOAS", "latest_value": 73.0, "fetch_status": "ok", "ok": True},
        {"key": "IGOAS", "latest_value": 73.0, "fetch_status": "carried_forward", "ok": False},
        {"key": "IGOAS", "latest_value": None, "fetch_status": "failed", "ok": False},
    ]
    for version, row in zip(versions, rows):
        vdir = tmp_path / "versions" / version
        vdir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([row]).to_parquet(vdir / "aux_signal_matrix.parquet", index=False)

    found = store.find_last_good_aux("IGOAS")
    assert found is not None
    assert float(found.iloc[0]["latest_value"]) == 73.0
    assert found.iloc[0]["fetch_status"] == "ok"


def test_external_guidance_explains_what_to_watch_and_how_to_branch():
    text = render_external_guidance("DGS2")
    assert "Fed 금리회의(FOMC)" in text
    assert "미국 고용보고서" in text
    assert "무엇을 볼까" in text
    assert "앞으로의 금리 예상 하락 + 실업률 전망 상승" in text
    assert "실업률 전망도 오르면 경기 둔화 우려가 금리인하 기대를 키우는 모습" in text


def test_monthly_view_catches_reversion_remaining_change_and_rate_split():
    dates = pd.date_range("2026-06-10", periods=8, freq="D")
    series = {
        "VIX": [18, 20, 28, 35, 30, 24, 21, 19],
        "HYOAS": [300, 305, 315, 330, 345, 360, 370, 380],
        "DGS2": [4.50, 4.47, 4.44, 4.40, 4.35, 4.30, 4.25, 4.20],
        "DGS30": [4.30, 4.34, 4.38, 4.43, 4.49, 4.55, 4.60, 4.65],
    }
    rows = []
    for key, values in series.items():
        for i, (date, value) in enumerate(zip(dates, values)):
            if key == "VIX":
                state = "calm" if i < 2 or i == len(values) - 1 else "watch"
            elif key == "HYOAS":
                state = "calm" if i < 3 else "watch"
            else:
                state = "stable"
            rows.append({
                "snapshot_date": date.strftime("%Y-%m-%d"),
                "snapshot_at_kst": f"{date.strftime('%Y-%m-%d')} 08:00:00",
                "key": key,
                "latest_value": value,
                "state_code": state,
                "drop_flag": False,
            })
    history = pd.DataFrame(rows)
    aux_df = pd.DataFrame([
        {"key": "AOAS", "direction": "상승", "staleness_label": "normal"},
        {"key": "BREAKEVEN", "direction": "보합", "staleness_label": "normal"},
        {"key": "TERMPREM", "direction": "상승", "staleness_label": "normal"},
    ])

    text = render_monthly_markdown(history, aux_df)
    assert "한때 크게 움직였다가 되돌아온 것" in text
    assert "VIX" in text
    assert "2년 금리는 내리고 30년 금리는 올랐습니다" not in text
    assert "현재 남아 있는 추세" in text
