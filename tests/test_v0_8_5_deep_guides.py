from __future__ import annotations

import pandas as pd

from riskradar.deep_guides import guide_markdown, BACKGROUND_NOTE
from riskradar.indicator_detail_view import render_indicator_detail
from riskradar.aux_detail_view import render_aux_detail
from riskradar.ui import _is_compatible_data_code_version


def _matrix():
    return pd.DataFrame([
        {"key":"VIX","latest_value":19.2,"value_unit":"index","change_20obs":1.4,"change_60obs":2.0,"change_unit":"pt","state_code":"calm","state_label":"경계 신호 없음","latest_observed_date":"2026-07-10","percentile_5y":55,"percentile_10y":50},
        {"key":"HYOAS","latest_value":3.8,"value_unit":"%","change_20obs":24.0,"change_60obs":30.0,"change_unit":"bp","state_code":"watch","state_label":"높은 수준","latest_observed_date":"2026-07-10","percentile_5y":70,"percentile_10y":65},
        {"key":"DGS30","latest_value":4.9,"value_unit":"%","change_20obs":18.0,"change_60obs":20.0,"change_unit":"bp","state_code":"stable","state_label":"급격한 상승 없음","latest_observed_date":"2026-07-10","percentile_5y":80,"percentile_10y":75},
        {"key":"DGS2","latest_value":3.9,"value_unit":"%","change_20obs":-7.0,"change_60obs":-4.0,"change_unit":"bp","state_code":"stable","state_label":"급격한 상승 없음","latest_observed_date":"2026-07-10","percentile_5y":65,"percentile_10y":60},
        {"key":"DFII10","latest_value":2.2,"value_unit":"%","change_20obs":11.0,"change_60obs":14.0,"change_unit":"bp","state_code":"rise_watch","state_label":"상승 경계","latest_observed_date":"2026-07-10","percentile_5y":82,"percentile_10y":78},
        {"key":"T10Y3M","latest_value":0.4,"value_unit":"%p","change_20obs":8.0,"change_60obs":6.0,"change_unit":"bp","state_code":"normal","state_label":"장기금리가 더 높음","latest_observed_date":"2026-07-10","percentile_5y":45,"percentile_10y":42},
    ])


def _aux():
    return pd.DataFrame([
        {"key":"BBBOAS","latest_value":1.2,"value_unit":"%","change_1m":5.0,"change_unit":"bp","direction":"상승","latest_date":"2026-07-10","staleness_label":"normal"},
        {"key":"AOAS","latest_value":0.8,"value_unit":"%","change_1m":-1.0,"change_unit":"bp","direction":"하락","latest_date":"2026-07-10","staleness_label":"normal"},
        {"key":"CPSPREAD","latest_value":25.0,"value_unit":"bp","change_1m":3.0,"change_unit":"bp","direction":"상승","latest_date":"2026-07-10","staleness_label":"normal"},
        {"key":"BREAKEVEN","latest_value":2.4,"value_unit":"%","change_1m":4.0,"change_unit":"bp","direction":"상승","latest_date":"2026-07-10","staleness_label":"normal"},
        {"key":"TERMPREM","latest_value":0.7,"value_unit":"%","change_1m":-3.0,"change_unit":"bp","direction":"하락","latest_date":"2026-07-10","staleness_label":"normal"},
        {"key":"NFCI","latest_value":-0.2,"value_unit":"지수","change_1m":0.1,"change_unit":"지수","direction":"상승","latest_date":"2026-07-05","staleness_label":"normal"},
        {"key":"STLFSI","latest_value":-0.4,"value_unit":"지수","change_1m":None,"change_unit":"지수","direction":"확인 불가","latest_date":"2026-07-05","staleness_label":"stale"},
    ])


def _dq():
    return {"credit_episode":{"lens":{"latest_value_bp":260.0,"change_1m_bp":9.0,"label":"HY 쪽 확대가 더 큽니다.","latest_date":"2026-07-10"}}}


def test_all_target_guides_have_required_sections_and_dynamic_results():
    targets = ["HY_BBB","BBBOAS","AOAS","CPSPREAD","DGS30","DGS2","DFII10","T10Y3M","BREAKEVEN","TERMPREM","HYOAS","VIX","NFCI","STLFSI"]
    for key in targets:
        row = None if key == "HY_BBB" else (_matrix().loc[_matrix().key == key].iloc[0] if key in {"VIX","HYOAS","T10Y3M","DGS30","DGS2","DFII10"} else _aux().loc[_aux().key == key].iloc[0])
        md = guide_markdown(key, row, matrix=_matrix(), aux_df=_aux(), data_quality=_dq())
        for heading in ["## 현재 데이터", "## 이 지표가 뜻하는 것", "## 왜 중요한가", "## 같이 볼 지표와 배경", "## 현재 함께 보는 지표의 결과", "## 지금 조합을 어떻게 읽는가", "## 움직임별 해석", "## 주의사항"]:
            assert heading in md, (key, heading)
        assert "현재 확인 불가" in md or "2026-07" in md or "신용 에피소드" in md


def test_a_oas_background_and_oas_caution_are_separated():
    row = _aux().loc[_aux().key == "AOAS"].iloc[0]
    md = guide_markdown("AOAS", row, matrix=_matrix(), aux_df=_aux(), data_quality=_dq())
    assert "BBB" in md and "HY" in md
    assert "더 우량한 투자등급" in md
    assert "총 금리가 아닙니다" in md
    assert "FOMC" in md and BACKGROUND_NOTE in md
    after_current_results = md.split("## 현재 함께 보는 지표의 결과", 1)[1].split("## 지금 조합", 1)[0]
    assert "FOMC" not in after_current_results


def test_rate_guides_have_key_relationships_and_forbidden_claims_absent():
    for key in ["DGS30", "DGS2", "DFII10", "T10Y3M", "BREAKEVEN", "TERMPREM"]:
        row = _matrix().loc[_matrix().key == key].iloc[0] if key in set(_matrix().key) else _aux().loc[_aux().key == key].iloc[0]
        md = guide_markdown(key, row, matrix=_matrix(), aux_df=_aux(), data_quality=_dq())
        assert "실질" in md or "DFII10" in md or key == "DGS2"
        assert "Breakeven" in md or key in {"DGS2", "T10Y3M"}
        assert "Term Premium" in md or key in {"DGS2", "T10Y3M"}
    all_md = "\n".join(guide_markdown(k, (_aux().loc[_aux().key == k].iloc[0] if k in {"BREAKEVEN","TERMPREM"} else _matrix().loc[_matrix().key == k].iloc[0]), matrix=_matrix(), aux_df=_aux()) for k in ["BREAKEVEN","TERMPREM"])
    assert "순수 기대 인플레이션" not in all_md.replace("순수 기대 인플레이션이 아닙니다", "")
    assert "직접 더하는 항목이 아닙니다" in all_md


def test_existing_renderers_include_deep_guides_and_weekly_stale_truth():
    core = _matrix().loc[_matrix().key == "DGS30"].iloc[0]
    aux = _aux().loc[_aux().key == "CPSPREAD"].iloc[0]
    assert "## 현재 함께 보는 지표의 결과" in render_indicator_detail(core, _dq(), "한줄", matrix=_matrix(), aux_df=_aux())
    md = render_aux_detail(aux, aux_df=_aux(), matrix=_matrix())
    assert "## 현재 함께 보는 지표의 결과" in md
    assert "주간 관측 2026-07-05" in md
    assert "현재 확인 불가" in md


def test_v085_compatibility_covers_v082_to_v085():
    for data_version in ["0.8.2", "0.8.3", "0.8.4", "0.8.5"]:
        assert _is_compatible_data_code_version(data_version, "0.8.5")


def _rate_summary():
    return {
        "status": "ok",
        "observation_date": "2026-07-10",
        "latest": {"DGS30": 4.9, "DFII30": 2.1, "INFLCOMP30": 2.8},
        "primary": {
            "start_date": "2026-06-10", "end_date": "2026-07-10",
            "DGS30_change_bp": 18.0, "DFII30_change_bp": 11.0, "INFLCOMP30_change_bp": 7.0,
        },
    }


def test_hy_bbb_dynamic_guide_is_wired_to_credit_tab_and_reload():
    source = __import__("pathlib").Path("src/riskradar/ui.py").read_text(encoding="utf-8")
    assert 'credit_hy_bbb_detail_component = gr.Markdown' in source
    assert 'initial["aux_details"].get("HY_BBB"' in source
    assert 'payload["aux_details"].get("HY_BBB"' in source


def test_explanation_selector_uses_dynamic_deep_guides_for_core_and_aux():
    source = __import__("pathlib").Path("src/riskradar/ui.py").read_text(encoding="utf-8")
    assert 'details_state = gr.State(initial["details"])' in source
    assert 'aux_details_state = gr.State(initial["aux_details"])' in source
    assert 'if key in details:' in source and 'if key in aux_details:' in source
    assert 'guide_card = gr.Markdown(initial["details"].get(default_key' in source


def test_detail_documents_do_not_duplicate_current_data_or_movement_sections():
    core = render_indicator_detail(_matrix().loc[_matrix().key == "HYOAS"].iloc[0], _dq(), "한줄", matrix=_matrix(), aux_df=_aux())
    aux = render_aux_detail(_aux().loc[_aux().key == "AOAS"].iloc[0], aux_df=_aux(), matrix=_matrix())
    for md in (core, aux):
        assert md.count("## 현재 데이터") == 1
        assert md.count("## 움직임별 해석") == 1
        assert md.count("## 주의사항") == 1


def test_companion_notes_are_specific_not_generic_for_major_guides():
    from riskradar.deep_guides import GUIDES
    for key in ["HY_BBB", "AOAS", "DGS30", "HYOAS", "VIX"]:
        notes = list(GUIDES[key].companion_notes.values())
        assert len(set(notes)) == len(notes)
        assert "현재 지표가 단독 움직임인지, 같은 시장 영역의 다른 지표와 함께 움직이는지 확인합니다." not in notes


def test_stored_direction_is_used_and_stale_excluded_from_combo_direction():
    aux_df = _aux().copy()
    aux_df.loc[aux_df.key == "AOAS", "change_1m"] = 0.01
    aux_df.loc[aux_df.key == "AOAS", "direction"] = "보합"
    md = guide_markdown("AOAS", aux_df.loc[aux_df.key == "AOAS"].iloc[0], matrix=_matrix(), aux_df=aux_df, data_quality=_dq())
    assert "| 현재 상태/방향 | 보합 |" in md

    aux_df.loc[aux_df.key == "BBBOAS", "staleness_label"] = "stale"
    md = guide_markdown("AOAS", aux_df.loc[aux_df.key == "AOAS"].iloc[0], matrix=_matrix(), aux_df=aux_df, data_quality=_dq())
    assert "오래된 자료" in md
    assert "조합 해석은 제한적" in md


def test_dgs30_guide_includes_30y_same_maturity_decomposition():
    md = guide_markdown("DGS30", _matrix().loc[_matrix().key == "DGS30"].iloc[0], matrix=_matrix(), aux_df=_aux(), data_quality=_dq(), rate_summary=_rate_summary())
    assert "## 30Y 동일 만기 분해" in md
    assert "30Y 명목금리" in md
    assert "30Y 실질금리" in md
    assert "30Y 일반·물가연동 국채금리 차이" in md
    assert "직접 더하는 값이 아니라 별도 참고축" in md
