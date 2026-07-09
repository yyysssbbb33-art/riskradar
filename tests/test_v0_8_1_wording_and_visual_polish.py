from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.credit_episode import _scope_text
from riskradar.display_text import state_name
from riskradar.aux_detail_view import render_aux_detail
from riskradar.user_copy import movement_result, render_static_explainer


def _aux_row(key: str, direction: str = "상승") -> pd.Series:
    return pd.Series({
        "key": key,
        "latest_value": 0.73,
        "value_unit": "%",
        "change_1m": 0.03,
        "change_unit": "%p",
        "direction": direction,
        "staleness_label": "normal",
        "latest_date": "2026-07-08",
        "level_pct": 70.0,
    })


def test_cp_retracing_scope_is_not_called_an_upward_signal():
    text = _scope_text({
        "HY": {"state": "normal"},
        "BBB": {"state": "normal"},
        "A": {"state": "normal"},
        "CP": {"state": "retracing"},
    })
    assert text == "CP는 앞선 상승 후 내려오기 시작했습니다."
    assert "상승 신호" not in text
    assert "상승이 확인" not in text


def test_hy_core_card_uses_level_language_not_trend_language():
    assert state_name("watch", key="HYOAS") == "높은 수준"
    assert state_name("stress", key="HYOAS") == "매우 높은 수준"
    assert "상승 신호" not in state_name("watch", key="HYOAS")


def test_term_premium_uses_direct_but_not_absolute_causality():
    text = movement_result("TERMPREM", "up")
    assert "10년·30년 장기금리를 끌어올리는 요인" in text
    assert "장기금리가 올라갑니다" not in text
    assert "힘과 맞을 수" not in text


def test_bbb_and_cp_results_name_the_actual_financing_effect():
    bbb = movement_result("BBBOAS", "up")
    cp = movement_result("CPSPREAD", "up")
    assert "BBB 기업의 국채 대비 추가 조달비용이 커집니다" in bbb
    assert "단기 자금조달 금리가 우량 기업보다 더 높아집니다" in cp
    assert "설명을 지지" not in bbb + cp
    assert "잘 맞" not in bbb + cp


def test_aux_detail_is_structured_once_without_legacy_branch_heading():
    row = _aux_row("TERMPREM")
    md = render_aux_detail(row, aux_df=pd.DataFrame([row]), matrix=pd.DataFrame())
    assert "## 지금 데이터로 보면" in md
    assert "### 지금 이렇게 읽습니다" in md
    assert "### 같이 볼 지표" in md
    assert "### 움직임별 결과" in md
    assert md.count("결과적으로 볼 수 있는 변화") == 1
    assert "결과가 달라지면" not in md
    assert "오르면 | 오르면" not in md


def test_static_explainer_keeps_result_first_and_caution_small():
    md = render_static_explainer("TERMPREM", "Term Premium")
    assert "## 움직임별 결과" in md
    assert "10년·30년 장기금리를 끌어올리는 요인" in md
    assert "> **참고:** Term Premium은 모형 추정치" in md


def test_tabs_place_credit_rate_and_market_reference_details_correctly():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    credit_start = source.index('with gr.Tab("신용")')
    rate_start = source.index('with gr.Tab("금리")')
    flow_start = source.index('with gr.Tab("흐름")')
    guide_start = source.index('with gr.Tab("설명")')
    credit_block = source[credit_start:rate_start]
    rate_block = source[rate_start:flow_start]
    guide_block = source[guide_start:]

    for key in ("BBBOAS", "AOAS", "CPSPREAD"):
        assert key in credit_block
    for key in ("DGS30", "DGS2", "DFII10", "T10Y3M", "BREAKEVEN", "TERMPREM"):
        assert key in rate_block
    for key in ("NFCI", "STLFSI"):
        assert key in guide_block


def test_visual_polish_has_restrained_domain_and_state_classes():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    for token in (
        "--rr-blue", "--rr-amber", "--rr-red", "--rr-teal", "--rr-green",
        ".rr-domain-credit", ".rr-domain-rate", ".rr-domain-vol",
        ".rr-state-quiet", ".rr-state-watch", ".rr-state-hot",
        ".rr-state-easing", ".rr-state-done", ".rr-detail-accordion",
    ):
        assert token in source


def test_main_user_surfaces_do_not_restore_old_vocabulary():
    root = Path(__file__).parents[1] / "src" / "riskradar"
    files = [
        "ui.py", "overview_view.py", "today_view.py", "monthly_view.py",
        "aux_detail_view.py", "indicator_detail_view.py", "relationship_guide.py",
        "telegram_client.py", "user_copy.py",
    ]
    text = "\n".join((root / name).read_text(encoding="utf-8") for name in files)
    for phrase in (
        "결과가 달라지면", "계속 이어지는 변화", "평소 범위",
        "오르는 중", "내리는 중", "부담 확대",
    ):
        assert phrase not in text, phrase


def test_telegram_uses_same_direction_and_reference_language_as_web():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "telegram_client.py").read_text(encoding="utf-8")
    assert '"상승": "상승"' in source
    assert '"하락": "하락"' in source
    assert 'return "중간 구간"' in source
    assert "과거 기준 금융여건이 빡빡한 쪽" in source
    assert "과거 기준 시장 스트레스가 높은 쪽" in source


def test_combo_check_results_reuse_central_user_copy():
    from riskradar.combo_rules import Check, UP, DOWN, FLAT
    from riskradar.interpretation_engine import _branch, _branch_map

    check = Check(
        "TERMPREM", "Term Premium",
        "legacy up wording", "legacy down wording", "legacy flat wording",
    )
    up_text, _, _ = _branch(check, UP)
    branches = _branch_map(check)
    assert "10년·30년 장기금리를 끌어올리는 요인" in up_text
    assert branches[UP] == up_text
    assert "legacy" not in " ".join(branches.values())
    assert DOWN in branches and FLAT in branches


def test_combo_scenario_copy_does_not_use_legacy_explanation_debate_language():
    from riskradar.combo_rules import COMBOS

    text = "\n".join(
        [combo.observed, combo.uncertainty, *(item[1] for item in combo.explanations)]
        for combo in []
    ) if False else "\n".join(
        part
        for combo in COMBOS
        for part in [combo.observed, combo.uncertainty, *(item[1] for item in combo.explanations)]
    )
    for phrase in ("설명을 지지", "설명과 잘 맞", "설명은 약해", "힘과 맞을"):
        assert phrase not in text, phrase


def test_rendered_state_guidance_uses_result_language_not_legacy_debate_language():
    from riskradar.state_guidance import render_state_guidance

    row = pd.Series({"key": "HYOAS", "state_code": "watch", "state_label": "높은 수준", "drop_flag": False})
    md = render_state_guidance("HYOAS", row, frames={}, aux_df=pd.DataFrame(), matrix=pd.DataFrame())
    assert "## 다음에 같이 볼 것" in md
    assert "움직임별 결과" in md
    for phrase in ("설명을 더 지지", "설명과 잘 맞", "부담 확대"):
        assert phrase not in md, phrase
