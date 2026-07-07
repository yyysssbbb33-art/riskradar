from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from riskradar import cache_store
from riskradar.decision_snapshot import (
    DecisionSnapshotSchemas,
    build_decision_snapshot,
    compare_decision_snapshots,
)


def _base_snapshot() -> dict:
    return {
        "snapshot_format_version": 1,
        "authoritative": True,
        "batch": {"cache_version": "2026-07-01T07-30-00KST", "generated_at": "2026-07-01T07:30:00+09:00", "app_version": "0.6.2"},
        "schemas": {"core_state": "core-v1", "credit_episode": "credit-v1", "aux_direction": "aux-v1"},
        "core": {
            "VIX": {"observed_date": "2026-07-01", "source_status": "ok", "state_code": "normal", "state_label": "평소 수준", "drop_flag": False},
        },
        "credit": {
            "nodes": {
                "HY": {"observed_date": "2026-07-01", "source_status": "ok", "state": "normal", "state_label": "평소 상태", "participant": False},
                "BBB": {"observed_date": "2026-07-01", "source_status": "ok", "state": "normal", "state_label": "평소 상태", "participant": False},
            },
            "episode": {"episode_id": "none", "state": "none", "participants": []},
            "lens": {"observed_date": "2026-07-01", "source_status": "ok", "state": "stable", "label": "큰 변화 없음"},
        },
        "aux": {
            "AOAS": {"observed_date": "2026-07-01", "source_status": "ok", "direction": "보합"},
        },
        "data_quality": {},
    }


def test_cold_start_is_not_an_error_or_transition():
    result = compare_decision_snapshots(None, _base_snapshot())
    assert result["status"] == "cold_start"
    assert result["cold_start_reason"] == "no_authoritative_previous_snapshot"
    assert result["summary"] == {"market": 0, "data_quality": 0, "recovery_gap": 0, "schema_boundary": 0}


def test_same_observation_decision_drift_is_suppressed():
    previous = _base_snapshot()
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["core"]["VIX"]["state_code"] = "watch"
    current["core"]["VIX"]["state_label"] = "평소보다 높음"
    result = compare_decision_snapshots(previous, current)
    assert result["market_transitions"] == []
    assert any(d["kind"] == "same_observation_decision_drift" for d in result["diagnostics"])


def test_new_observation_state_change_is_market_transition():
    previous = _base_snapshot()
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["core"]["VIX"].update({
        "observed_date": "2026-07-02", "state_code": "watch", "state_label": "평소보다 높음"
    })
    result = compare_decision_snapshots(previous, current)
    assert len(result["market_transitions"]) == 1
    assert result["market_transitions"][0]["transition_type"] == "new_observation_transition"


def test_data_failure_is_separate_from_market_change():
    previous = _base_snapshot()
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["aux"]["AOAS"].update({"source_status": "carried_forward", "direction": "상승"})
    result = compare_decision_snapshots(previous, current)
    assert len(result["data_quality_transitions"]) == 1
    assert result["market_transitions"] == []
    assert result["recovery_gap_events"] == []


def test_recovery_with_changed_decision_is_gap_event_not_precise_market_onset():
    previous = _base_snapshot()
    previous["aux"]["AOAS"].update({"source_status": "carried_forward", "observed_date": "2026-06-28", "direction": "보합"})
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["aux"]["AOAS"].update({"source_status": "ok", "observed_date": "2026-07-02", "direction": "상승"})
    result = compare_decision_snapshots(previous, current)
    assert len(result["recovery_gap_events"]) == 1
    event = result["recovery_gap_events"][0]
    assert event["timing_uncertain"] is True
    assert "정확히 언제" in event["message"]
    assert result["market_transitions"] == []


def test_schema_boundary_only_blocks_that_section():
    previous = _base_snapshot()
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["schemas"]["credit_episode"] = "credit-v2"
    current["core"]["VIX"].update({
        "observed_date": "2026-07-02", "state_code": "watch", "state_label": "평소보다 높음"
    })
    current["credit"]["nodes"]["HY"].update({
        "observed_date": "2026-07-02", "state": "early_change", "state_label": "초기 변화"
    })
    result = compare_decision_snapshots(previous, current)
    assert result["status"] == "partial_schema_boundary"
    assert any(e["section"] == "core" for e in result["market_transitions"])
    assert not any(e["section"] == "credit_nodes" for e in result["market_transitions"])
    assert any(e["section"] == "credit" for e in result["schema_boundaries"])


def test_missing_new_field_is_not_a_transition():
    previous = _base_snapshot()
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["snapshot_format_version"] = 2
    current["core"]["VIX"]["new_future_field"] = "x"
    result = compare_decision_snapshots(previous, current)
    assert result["market_transitions"] == []
    assert any(e["section"] == "snapshot_format" for e in result["schema_boundaries"])


def test_observation_clock_transition_for_dormancy():
    previous = _base_snapshot()
    previous["credit"]["episode"] = {"episode_id": "credit-1", "state": "active", "participants": ["HY"]}
    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["credit"]["nodes"]["HY"]["observed_date"] = "2026-07-02"
    current["credit"]["episode"] = {"episode_id": "credit-1", "state": "dormant", "participants": ["HY"]}
    result = compare_decision_snapshots(previous, current)
    episode_events = [e for e in result["market_transitions"] if e["section"] == "credit_episode"]
    assert len(episode_events) == 1
    assert episode_events[0]["transition_type"] == "observation_clock_transition"


def test_build_snapshot_marks_carried_forward_without_inventing_new_observation_date():
    signal = pd.DataFrame([{
        "key": "VIX", "latest_observed_date": "2026-07-01", "state_code": "normal",
        "state_label": "평소 수준", "drop_flag": False, "latest_value": 15.0, "value_unit": "지수",
    }])
    aux = pd.DataFrame([{
        "key": "AOAS", "latest_date": "2026-06-28", "fetch_status": "carried_forward",
        "staleness_label": "delayed", "direction": "보합", "latest_value": 80.0, "value_unit": "bp",
    }])
    snap = build_decision_snapshot(
        cache_version="2026-07-02T07-30-00KST", generated_at="2026-07-02T07:30:00+09:00",
        app_version="0.6.2", signal_matrix=signal, aux_matrix=aux, credit_quality={},
    )
    assert snap["aux"]["AOAS"]["source_status"] == "carried_forward"
    assert snap["aux"]["AOAS"]["observed_date"] == "2026-06-28"


def test_old_versions_without_decision_snapshot_are_not_backfilled(tmp_path):
    store = cache_store.LocalStore(tmp_path)
    old = tmp_path / "versions" / "2026-07-01T07-30-00KST"
    old.mkdir(parents=True)
    (old / "status.json").write_text("{}")
    assert store.find_previous_decision_snapshot("2026-07-02T07-30-00KST") is None


def test_local_store_roundtrips_optional_decision_json(tmp_path):
    store = cache_store.LocalStore(tmp_path)
    cv = "2026-07-01T07-30-00KST"
    vdir = tmp_path / "versions" / cv
    vdir.mkdir(parents=True)
    payload = _base_snapshot()
    (vdir / "decision_snapshot.json").write_text(__import__("json").dumps(payload, ensure_ascii=False))
    loaded = store.load_json_artifact(cv, "decision_snapshot")
    assert loaded["authoritative"] is True
    assert store.find_previous_decision_snapshot("2026-07-02T07-30-00KST")["batch"]["cache_version"] == cv


def test_retention_uses_days_floor_and_hard_max(monkeypatch):
    monkeypatch.setattr(cache_store, "KEEP_MIN_DAYS", 90)
    monkeypatch.setattr(cache_store, "KEEP_LAST_N", 45)
    monkeypatch.setattr(cache_store, "KEEP_MAX_N", 180)
    start = datetime(2026, 1, 1, 7, 30)
    versions = [(start + timedelta(days=i)).strftime("%Y-%m-%dT%H-%M-%SKST") for i in range(200)]
    prune = cache_store._versions_to_prune(versions)
    kept = [v for v in versions if v not in set(prune)]
    assert len(kept) == 91  # 최신일 포함 최근 90일 경계

    # 같은 기간 수동 실행이 폭주하면 안전 상한을 적용한다.
    many = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H-%M-%SKST") for i in range(300)]
    prune2 = cache_store._versions_to_prune(many)
    assert len(many) - len(prune2) == 180


def test_v062_first_refresh_is_cold_start_and_second_uses_only_authoritative_snapshot(monkeypatch, tmp_path):
    from tests.test_v0_6_0_credit_episode_and_layers import _aux_bundle, _recent_core_fetcher
    from riskradar import refresh_service

    kst = ZoneInfo("Asia/Seoul")
    times = iter([
        datetime(2026, 7, 8, 7, 30, 0, tzinfo=kst),
        datetime(2026, 7, 8, 7, 30, 1, tzinfo=kst),
        datetime(2026, 7, 9, 7, 30, 0, tzinfo=kst),
        datetime(2026, 7, 9, 7, 30, 1, tzinfo=kst),
    ])
    monkeypatch.setattr(refresh_service, "_now_kst", lambda: next(times))
    store = cache_store.LocalStore(tmp_path)

    first = refresh_service.run_refresh(
        fetcher=_recent_core_fetcher(), aux_fetcher=lambda: _aux_bundle(), store=store, notify=False
    )
    d1 = store.load_json_artifact(first["active_cache_version"], "decision_diff")
    assert d1["status"] == "cold_start"

    second = refresh_service.run_refresh(
        fetcher=_recent_core_fetcher(), aux_fetcher=lambda: _aux_bundle(), store=store, notify=False
    )
    d2 = store.load_json_artifact(second["active_cache_version"], "decision_diff")
    assert d2["previous_cache_version"] == first["active_cache_version"]
    assert d2["summary"]["market"] == 0


def test_v062_ui_accepts_v060_and_v061_data_and_has_decision_diagnostic_accordion():
    from riskradar.ui import _is_compatible_data_code_version

    assert _is_compatible_data_code_version("0.6.0", "0.6.2") is True
    assert _is_compatible_data_code_version("0.6.1", "0.6.2") is True
    assert _is_compatible_data_code_version("0.6.2", "0.6.2") is True
    assert _is_compatible_data_code_version("0.4.9", "0.6.2") is False

    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert 'with gr.Accordion("판정 기록·변화 진단 보기", open=False)' in source


def test_old_cache_without_decision_json_loads_gracefully(monkeypatch, tmp_path):
    from tests.test_v0_6_0_credit_episode_and_layers import _aux_bundle, _recent_core_fetcher
    from riskradar import refresh_service
    from riskradar.dashboard_snapshot import load_dashboard_snapshot

    kst = ZoneInfo("Asia/Seoul")
    times = iter([
        datetime(2026, 7, 8, 7, 30, 0, tzinfo=kst),
        datetime(2026, 7, 8, 7, 30, 1, tzinfo=kst),
    ])
    monkeypatch.setattr(refresh_service, "_now_kst", lambda: next(times))
    store = cache_store.LocalStore(tmp_path)
    status = refresh_service.run_refresh(
        fetcher=_recent_core_fetcher(), aux_fetcher=lambda: _aux_bundle(), store=store, notify=False
    )
    cv = status["active_cache_version"]
    (tmp_path / "versions" / cv / "decision_snapshot.json").unlink()
    (tmp_path / "versions" / cv / "decision_diff.json").unlink()

    snapshot = load_dashboard_snapshot(store)
    assert snapshot.decision_snapshot == {}
    assert snapshot.decision_diff == {}
    assert not any("판정 스냅샷" in e for e in snapshot.load_errors)


def test_decision_tracking_failure_does_not_break_core_refresh(monkeypatch, tmp_path):
    from tests.test_v0_6_0_credit_episode_and_layers import _aux_bundle, _recent_core_fetcher
    from riskradar import refresh_service

    def boom(**_kwargs):
        raise RuntimeError("decision test failure")

    monkeypatch.setattr(refresh_service.DS, "build_decision_snapshot", boom)
    store = cache_store.LocalStore(tmp_path)
    status = refresh_service.run_refresh(
        fetcher=_recent_core_fetcher(), aux_fetcher=lambda: _aux_bundle(), store=store, notify=False
    )
    assert status["status"] == "success"
    dq = store.load_data_quality(status["active_cache_version"])
    assert "decision test failure" in str((dq.get("decision_tracking") or {}).get("error"))
    assert store.find_previous_decision_snapshot() is None


def test_episode_scope_change_caused_by_unreliable_node_is_not_market_transition():
    previous = _base_snapshot()
    previous["credit"]["nodes"]["HY"].update({"participant": True})
    previous["credit"]["nodes"]["BBB"].update({"participant": True})
    previous["credit"]["episode"] = {"episode_id": "credit-1", "state": "active", "participants": ["HY", "BBB"]}

    current = deepcopy(previous)
    current["batch"]["cache_version"] = "2026-07-02T07-30-00KST"
    current["credit"]["nodes"]["HY"]["observed_date"] = "2026-07-02"
    current["credit"]["nodes"]["BBB"].update({"source_status": "stale", "participant": False})
    current["credit"]["episode"] = {"episode_id": "credit-1", "state": "active", "participants": ["HY"]}

    result = compare_decision_snapshots(previous, current)
    assert not any(e["section"] == "credit_episode" for e in result["market_transitions"])
    assert any(d["kind"] == "episode_change_suppressed_data_issue" for d in result["diagnostics"])
