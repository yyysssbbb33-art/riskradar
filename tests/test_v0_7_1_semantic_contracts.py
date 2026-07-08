from __future__ import annotations

from riskradar import aux_config as AC
from riskradar import combo_rules as CR
from riskradar import decision_snapshot as DS
from riskradar import telegram_client as TG
from riskradar.rate_composition import render_markdown


def _summary():
    return {
        "status": "ok",
        "primary": {
            "DGS30_change_bp": 21.0,
            "DFII30_change_bp": 13.0,
            "INFLCOMP30_change_bp": 8.0,
        },
        "context": {
            "DGS30_change_bp": 35.0,
            "DFII30_change_bp": 20.0,
            "INFLCOMP30_change_bp": 15.0,
        },
        "curve": {
            "text": "장·단기 금리가 함께 올랐고 장기가 더 올라 곡선이 가팔라졌습니다(bear steepening)."
        },
        "term_premium": {
            "status": "ok",
            "latest_value": 0.42,
            "change_1m_bp": 5.0,
            "direction": "상승",
        },
    }


def test_change_center_policy_is_independent_from_detail_visibility():
    assert "BREAKEVEN" in AC.VISIBLE_AUX_ORDER
    assert "TERMPREM" in AC.VISIBLE_AUX_ORDER
    assert "BREAKEVEN" in AC.AUX_CHANGE_CENTER_KEYS
    assert "TERMPREM" in AC.AUX_CHANGE_CENTER_KEYS
    assert AC.AUX_CHANGE_CENTER_KEYS is not AC.VISIBLE_AUX_ORDER


def test_aux_snapshot_schema_stays_v1():
    assert DS.AUX_DIRECTION_SCHEMA == "aux-v1"


def test_mixed_maturity_rate_composition_rules_are_retired():
    ids = {c.combo_id for c in CR.COMBOS}
    assert "NOMINAL_REAL_UP" not in ids
    assert "NOMINAL_UP_REAL_NOT" not in ids
    assert not [c for c in CR.COMBOS if c.group == "rate_composition"]


def test_ui_and_telegram_share_same_rate_summary_values():
    summary = _summary()
    ui = render_markdown(summary)
    tg = "\n".join(TG._rate_composition_lines(summary))
    for token in ("0.21%p", "0.13%p", "0.08%p"):
        assert token in ui
        assert token in tg
    assert "물가 기대뿐 아니라 물가 위험과 채권 수요·공급 영향도" in ui
    assert "물가 기대뿐 아니라 물가 위험과 채권 수요·공급 영향도" in tg


def test_rate_composition_copy_does_not_add_causal_gloss():
    text = render_markdown(_summary())
    for forbidden in ("재정 우려", "채권 자경단", "국채 신뢰 붕괴"):
        assert forbidden not in text
