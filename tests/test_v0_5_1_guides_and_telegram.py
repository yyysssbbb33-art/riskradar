"""v0.5.1 — 확인지표 상세 가이드와 Telegram 수치+해석 회귀 테스트."""
from __future__ import annotations

import pandas as pd

from riskradar import aux_config as AC
from riskradar import telegram_client as TG
from riskradar.aux_detail_view import render_aux_detail
from riskradar.aux_interpretation_cards import get_aux_interpretation_card
from riskradar.display_text import plain_language
from riskradar.relationship_guide import RELATIONSHIP_GUIDE


def _matrix() -> pd.DataFrame:
    rows = [
        ("VIX", 18.4, "index", 2.1, -0.4, "pt", "calm", "calm", False),
        ("HYOAS", 345.0, "bp", 12.0, 28.0, "bp", "neutral", "neutral", False),
        ("T10Y3M", 55.0, "bp", 18.0, 42.0, "bp", "re_normalizing", "", False),
        ("DGS30", 4.72, "%", 24.0, 41.0, "bp", "rise_watch", "", False),
        ("DGS2", 3.81, "%", -31.0, -45.0, "bp", "stable", "", True),
        ("DFII10", 2.18, "%", 14.0, 29.0, "bp", "stable", "", False),
    ]
    return pd.DataFrame([
        {
            "key": key, "latest_value": value, "value_unit": unit,
            "change_20obs": c1, "change_60obs": c3, "change_unit": cunit,
            "state_code": scode, "state_label": slabel, "drop_flag": drop,
        }
        for key, value, unit, c1, c3, cunit, scode, slabel, drop in rows
    ])


def _aux_df() -> pd.DataFrame:
    values = {
        "BREAKEVEN": (2.36, "%", 7.0, "bp", "상승", 68.0),
        "TERMPREM": (0.42, "%", -9.0, "bp", "하락", 62.0),
        "BBBOAS": (132.0, "bp", 14.0, "bp", "상승", 77.0),
        "AOAS": (84.0, "bp", 3.0, "bp", "보합", 55.0),
        "CPSPREAD": (46.0, "bp", 11.0, "bp", "상승", 82.0),
        "NFCI": (-0.18, "지수", 0.12, "지수", "상승", 74.0),
        "STLFSI": (-0.31, "지수", -0.08, "지수", "하락", 28.0),
    }
    rows = []
    for key in AC.VISIBLE_AUX_ORDER:
        value, unit, change, cunit, direction, level = values[key]
        rows.append({
            "key": key,
            "display_name": AC.AUX_SERIES[key].display_name,
            "latest_value": value,
            "value_unit": unit,
            "latest_date": "2026-07-03",
            "change_1m": change,
            "change_unit": cunit,
            "direction": direction,
            "level_pct": level,
            "staleness_label": "normal",
            "fetch_status": "ok",
        })
    return pd.DataFrame(rows)


def test_all_aux_indicators_have_full_eight_part_cards():
    for key in AC.VISIBLE_AUX_ORDER:
        card = get_aux_interpretation_card(key)
        for heading in (
            "### 1. 뭘 측정하나",
            "### 2. 뭘 우선 보나",
            "### 3. 값 구간 감각",
            "### 4. 같이 볼 지표 + 왜",
            "### 5. 흔한 오해",
            "### 6. 오를 때 / 내릴 때 방향",
            "### 7. 근거 수준",
            "### 8. 근거의 한계",
        ):
            assert heading in card, (key, heading)


def test_aux_detail_connects_current_data_companions_branches_and_card():
    aux_df = _aux_df()
    matrix = _matrix()
    row = aux_df.loc[aux_df["key"] == "CPSPREAD"].iloc[-1]
    md = render_aux_detail(row, aux_df=aux_df, matrix=matrix)
    assert "## 지금 데이터로 보면" in md
    assert "약 1개월 변화" in md and "+0.11%p" in md
    assert "### 같이 볼 지표와 현재 결과" in md
    assert "신용등급이 낮은 기업의 추가 금리(HY OAS)" in md
    assert "투자등급 경계 기업의 추가 금리(BBB OAS)" in md
    assert "미국 금융여건(NFCI)" in md
    assert "### 결과가 달라지면" in md
    assert "### 8. 근거의 한계" in md


def test_external_reference_details_explain_reference_only_role():
    aux_df = _aux_df()
    matrix = _matrix()
    for key in ("NFCI", "STLFSI"):
        row = aux_df.loc[aux_df["key"] == key].iloc[-1]
        md = plain_language(render_aux_detail(row, aux_df=aux_df, matrix=matrix))
        assert "외부" in md
        assert "종합지표" in md
        assert "침체" in md or "금융위기" in md
        assert "해석 엔진" in md or "독립 판정" in md or "외부 검산용" in md or "넣지 않습니다" in md


def test_relationship_guide_covers_credit_ladder_cp_and_external_references():
    text = plain_language(RELATIONSHIP_GUIDE)
    assert "기업 신용 부담은 어디에서 나타나나" in text
    assert "단기 기업자금시장(CP)까지 변화가 나타나나" in text
    assert "외부 참고 지표는 어떻게 참고하나" in text
    assert "투자등급 경계 기업" in text
    assert "CP Spread" in text
    assert "미국 금융여건(NFCI)" in text
    assert "미국 금융시장 불안(STLFSI)" in text


def test_telegram_shows_all_results_then_interpretation():
    axes = {
        "changed_count": 2,
        "vol_credit": {"state": "B"},
        "cycle": {"state": "re_normalizing", "label": ""},
        "rate": {"result": "혼합 방향"},
    }
    readings = [{
        "label": "30년 금리 상승 · 2년 금리 하락",
        "explanations": [
            {"id": "long_end", "text": "장기금리 쪽 요인이 단기 기준금리 예상보다 더 강하게 움직인다는 설명"},
            {"id": "growth", "text": "경기 둔화 우려가 커졌다는 설명"},
        ],
        "supported_ids": ["long_end"],
        "weakened_ids": [],
        "uncertainty": "추가 확인 필요",
    }]
    rate_composition = {
        "status": "ok",
        "primary": {
            "DGS30_change_bp": 24.0,
            "DFII30_change_bp": 15.0,
            "INFLCOMP30_change_bp": 9.0,
        },
        "curve": {
            "text": "장기금리는 오르고 단기금리는 내려 곡선이 가팔라졌습니다(장·단기 엇갈림)."
        },
        "term_premium": {"status": "ok", "change_1m_bp": 6.0, "direction": "상승"},
    }
    text = TG.build_success(
        "2026-07-06 08:30 KST", "cv", _matrix(), {"synced_date": "2026-07-03"}, [],
        axes=axes, readings=readings, aux_df=_aux_df(), rate_composition=rate_composition,
    )

    # 핵심 6개: 값 + 1개월/3개월 변화
    assert "VIX: 18.4 · +2.1포인트 / -0.4포인트" in text
    assert "HY OAS: 3.45%p · +0.12%p / +0.28%p" in text
    assert "30Y: 4.72% · +0.24%p / +0.41%p" in text

    # 30년 금리 변화는 수식 대신 쉬운 문장으로 보여준다.
    assert "30년 미국 국채금리 · 최근 약 1개월" in text
    assert "전체 금리: 0.24%p 상승" in text
    assert "물가 영향을 뺀 금리: 0.15%p 상승" in text
    assert "일반 국채와 물가연동국채의 금리 차이: 0.09%p 확대" in text
    assert "10년 일반·물가연동 국채금리 차이" in text
    assert text.count("10년 국채를 오래 보유할 때 시장이 요구하는 추가 보상(모형 추정)") == 1
    assert "BBB OAS: 1.32%p · +0.14%p" in text
    assert "A OAS: 0.84%p · +0.03%p" in text
    assert "CP Spread: 0.46%p · +0.11%p" in text
    assert "NFCI: -0.18 · +0.12" in text
    assert "STLFSI: -0.31 · -0.08" in text

    # 결과 뒤에 영역과 조합 해석
    assert text.index("핵심 지표") < text.index("여러 지표를 같이 보면")
    assert "현재 3개 영역 중 2개" in text
    assert "눈에 띄는 조합과 해석" in text
    assert "장기금리 쪽 요인이 단기 기준금리 예상보다 더 강하게 움직인다는 설명" in text
    assert len(text) <= 3900


def test_plain_language_does_not_mangle_new_user_terms():
    text = plain_language(get_aux_interpretation_card("BBBOAS") + get_aux_interpretation_card("CPSPREAD"))
    assert "투자등급 경계 기업" in text
    assert "CP Spread" in text
    assert "신용등급 높은 기업의 회사채 경계 기업" not in text
    assert "기업이 돈을 갚을 능력도" not in text
