from __future__ import annotations

from riskradar import aux_config as AC
from riskradar.decision_snapshot import compare_decision_snapshots
from riskradar.overview_view import render_recent_changes_markdown


def _event(channel: str, key: str) -> dict:
    base = {"section": "aux", "key": key}
    if channel == "market_transitions":
        return {
            **base,
            "transition_type": "new_observation_transition",
            "previous": "보합",
            "current": "상승",
        }
    if channel == "recovery_gap_events":
        return {**base, "transition_type": "recovery_gap_transition"}
    return {**base, "transition_type": "source_status_transition"}


def _render_one(channel: str, key: str) -> str:
    diff = {
        "status": "ok",
        "market_transitions": [],
        "recovery_gap_events": [],
        "data_quality_transitions": [],
        "schema_boundaries": [],
    }
    diff[channel] = [_event(channel, key)]
    return render_recent_changes_markdown(diff)


def test_change_center_policy_is_independent_from_detail_list_policy():
    assert AC.AUX_CHANGE_CENTER_KEYS is not AC.VISIBLE_AUX_ORDER
    assert "BREAKEVEN" in AC.VISIBLE_AUX_ORDER
    assert "BREAKEVEN" in AC.AUX_CHANGE_CENTER_KEYS
    assert "TERMPREM" in AC.AUX_CHANGE_CENTER_KEYS
    assert "IGOAS" not in AC.AUX_CHANGE_CENTER_KEYS


def test_hidden_aux_market_transition_is_not_shown():
    assert "투자등급 회사채 전체 평균" not in _render_one("market_transitions", "IGOAS")


def test_hidden_aux_recovery_gap_is_not_shown():
    assert "투자등급 회사채 전체 평균" not in _render_one("recovery_gap_events", "IGOAS")


def test_hidden_aux_data_quality_transition_is_not_shown():
    assert "투자등급 회사채 전체 평균" not in _render_one("data_quality_transitions", "IGOAS")


def test_visible_aux_market_transition_is_still_shown():
    assert "투자등급 경계 기업" in _render_one("market_transitions", "BBBOAS")


def test_hidden_aux_does_not_consume_visible_event_slots():
    hidden = [_event("market_transitions", "IGOAS") for _ in range(5)]
    visible = _event("market_transitions", "BBBOAS")
    diff = {
        "status": "ok",
        "market_transitions": hidden + [visible],
        "recovery_gap_events": [],
        "data_quality_transitions": [],
        "schema_boundaries": [],
    }
    text = render_recent_changes_markdown(diff)
    assert "투자등급 경계 기업" in text
    assert "투자등급 회사채 전체 평균" not in text


def test_raw_decision_diff_keeps_hidden_aux_for_diagnostics():
    previous = {
        "snapshot_format_version": 1,
        "authoritative": True,
        "batch": {"cache_version": "2026-07-07T09-00-00KST"},
        "schemas": {"core_state": "core-v1", "credit_episode": "credit-v1", "aux_direction": "aux-v1"},
        "core": {},
        "credit": {"nodes": {}, "episode": {}, "lens": {}},
        "aux": {
            "IGOAS": {
                "observed_date": "2026-07-06",
                "source_status": "ok",
                "direction": "보합",
            }
        },
    }
    current = {
        **previous,
        "batch": {"cache_version": "2026-07-08T09-00-00KST"},
        "aux": {
            "IGOAS": {
                "observed_date": "2026-07-07",
                "source_status": "ok",
                "direction": "상승",
            }
        },
    }
    diff = compare_decision_snapshots(previous, current)
    assert any(
        e.get("section") == "aux" and e.get("key") == "IGOAS"
        for e in diff.get("market_transitions", [])
    )
