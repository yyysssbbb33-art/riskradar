from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from riskradar.display_text import aux_name, core_name, plain_language
from riskradar.formatting import fmt_pct
from riskradar.state_guidance import _cycle_bucket
from riskradar.today_view import _fmt_change
from riskradar.refresh_service import _aux_matrix, _carry_forward_aux


class _Store:
    def __init__(self, previous: pd.DataFrame | None):
        self.previous = previous

    def last_good_aux(self):
        return self.previous


def test_plain_names_hide_finance_acronyms():
    assert core_name("HYOAS") == "신용등급이 낮은 기업의 추가 금리(HY OAS)"
    assert aux_name("IGOAS") == "투자등급 회사채 전체 평균 추가 금리(IG OAS)"
    assert aux_name("TERMPREM") == "10년 장기채 추가 보상(10Y Term Premium)"


def test_percentile_is_explained_as_past_position_not_probability():
    assert fmt_pct(82) == "상위 18% 구간"
    text = plain_language("최근 10년 위치 82%")
    assert text == "최근 10년 중 상위 18% 구간"
    assert "위험확률" not in text


def test_bp_is_rendered_as_percentage_point_in_plain_language():
    assert plain_language("약 3개월 +50bp, 현재 300bp") == "약 3개월 +0.50%p, 현재 3.00%p"


def test_failed_aux_uses_previous_successful_value_with_freshness():
    now = datetime.fromisoformat("2026-07-05T08:00:00+09:00")
    current = _aux_matrix({
        "BREAKEVEN": SimpleNamespace(ok=True, latest_value=2.3, latest_date="2026-07-03", change_1m=0.1,
                                     direction="상승", pct_in_history=70.0, n_obs=300, error=None),
        "IGOAS": SimpleNamespace(ok=False, latest_value=None, latest_date=None, change_1m=None,
                                 direction="판정불가", pct_in_history=None, n_obs=0, error="timeout"),
        "TERMPREM": SimpleNamespace(ok=True, latest_value=0.2, latest_date="2026-07-03", change_1m=-0.05,
                                     direction="하락", pct_in_history=60.0, n_obs=300, error=None),
    }, now)
    previous = pd.DataFrame([{
        "key": "IGOAS", "series_id": "BAMLC0A0CM", "display_name": "우량 회사채 추가금리",
        "ok": True, "latest_value": 74.0, "value_unit": "bp", "latest_date": "2026-07-02",
        "change_1m": 3.0, "change_unit": "bp", "direction": "상승", "pct_in_history": 55.0,
        "n_obs": 300, "stale_days": 1, "staleness_label": "normal", "fetch_status": "ok",
        "error": None,
    }])

    merged = _carry_forward_aux(current, _Store(previous), now)
    row = merged.loc[merged["key"] == "IGOAS"].iloc[0]
    assert row["latest_value"] == 74.0
    assert row["direction"] == "상승"
    assert row["fetch_status"] == "carried_forward"
    assert row["staleness_label"] == "delayed"
    assert "timeout" in row["error"]


def test_cycle_bucket_accepts_internal_long_inversion_label():
    assert _cycle_bucket("장기역전") == "단기금리가 더 높은 흐름"


def test_today_aux_change_uses_percentage_points_not_bp():
    row = pd.Series({"direction": "상승", "change_1m": 12.0, "change_unit": "bp"})
    assert _fmt_change(row) == "▲ 상승 (+0.12%p)"


def test_more_professional_terms_are_simplified():
    text = plain_language("명목금리와 인플레이션 보상, 정책경로와 광범위한 신용 변화")
    assert "명목금리" not in text
    assert "인플레이션 보상" not in text
    assert "정책경로" not in text
    assert "광범위한" not in text
