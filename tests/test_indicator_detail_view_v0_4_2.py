from tests import synth
from riskradar import pipeline
from riskradar.indicator_detail_view import COMBO_CORE_KEYS, render_indicator_detail


def _matrix_row(key):
    matrix = pipeline.compute_all(synth.make_raw_by_key(n=1200))["signal_matrix"]
    return matrix.loc[matrix["key"] == key].iloc[0]


def test_all_six_indicator_details_include_current_context_and_structured_explanation():
    for key in ["VIX", "HYOAS", "T10Y3M", "DGS30", "DGS2", "DFII10"]:
        md = render_indicator_detail(_matrix_row(key), {}, "현재 상태를 설명하는 한줄 해석입니다.")
        assert "## 지금 데이터로 보면" in md
        assert "### 무엇을 보나" in md
        assert "### 지금 이렇게 읽습니다" in md
        assert "## 움직임별 결과" in md
        assert "## 다음에 같이 볼 것" in md
        assert "약 1개월 변화" in md
        assert "약 3개월 변화" in md
        assert "최근 5년 중 현재 위치" in md
        assert "최근 10년 중 현재 위치" in md


def test_relevant_combo_surfaces_supported_and_weakened_explanations():
    dq = {
        "readings": [
            {
                "combo_id": "rates_30up_2down",
                "label": "30년물 상승 · 2년물 하락",
                "observed": "장단기 구간의 방향이 엇갈립니다.",
                "explanations": [
                    {"id": "real", "text": "실질금리 설명"},
                    {"id": "infl", "text": "인플레이션 설명"},
                ],
                "supported_ids": ["real"],
                "weakened_ids": ["infl"],
                "conflict": "",
            }
        ]
    }
    md = render_indicator_detail(_matrix_row("DGS30"), dq, "한줄 해석")
    assert "30년 금리 상승 · 2년 금리 하락" in md
    assert "현재 함께 보이는 점" in md
    assert "물가 영향을 뺀 금리 설명" in md
    assert "반대로 움직이는 점" in md
    assert "물가 상승 설명" in md


def test_combo_indicator_mapping_covers_all_current_combo_ids():
    expected = {
        "rates_30up_2down", "rates_30down_2up", "rates_broad_up", "rates_broad_down",
        "two_down_credit_widening",
        "two_down_credit_quiet", "vol_leads", "credit_only", "vol_credit_together",
        "vol_calm_credit_persist", "cycle_renorm_credit_wide",
        "cycle_renorm_credit_quiet", "long_inv_2y_down",
    }
    assert expected == set(COMBO_CORE_KEYS)
