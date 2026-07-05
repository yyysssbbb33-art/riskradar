from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from riskradar import cache_store
from riskradar.cache_store import LocalStore
from riskradar.dashboard_snapshot import load_dashboard_snapshot
from riskradar.fred_client import FetchResult
from riskradar.refresh_service import run_refresh
from riskradar.ui import _data_status_summary
from tests.synth import make_raw_by_key


def _fetcher(n: int = 1200):
    rb = make_raw_by_key(n=n)
    return lambda: {k: FetchResult(k, True, v) for k, v in rb.items()}


class VersionPinnedStore:
    def __init__(self, arts: dict[str, pd.DataFrame]):
        self.arts = arts
        self.calls: list[tuple[str, str]] = []
        self.repo_id = "owner/cache"

    def load(self):
        return {"active_cache_version": "v1", "code_version": "0.4.9"}, self.arts

    def load_data_quality(self, cache_version=None):
        self.calls.append(("dq", str(cache_version)))
        return {"code_version": "0.4.9", "from_version": cache_version}

    def load_artifact(self, cache_version, name):
        self.calls.append((name, str(cache_version)))
        return pd.DataFrame()

    def load_history(self, days=30):
        return pd.DataFrame()


def test_dashboard_snapshot_pins_all_side_files_to_active_version():
    chart = pd.DataFrame({"key": ["DGS2"], "date": ["2026-07-01"], "value": [4.0]})
    store = VersionPinnedStore({"chart_data": chart})
    snap = load_dashboard_snapshot(store)
    assert ("dq", "v1") in store.calls
    assert ("aux_signal_matrix", "v1") in store.calls
    assert snap.data_quality["from_version"] == "v1"


class BrokenMetadataStore(VersionPinnedStore):
    def load_data_quality(self, cache_version=None):
        raise RuntimeError("network down")


def test_metadata_read_error_is_not_misreported_as_old_cache():
    chart = pd.DataFrame({"key": ["DGS2"], "date": ["2026-07-01"], "value": [4.0]})
    store = BrokenMetadataStore({"chart_data": chart})
    snap = load_dashboard_snapshot(store)
    summary, warning = _data_status_summary(snap, store)
    assert "data_quality.json 읽기 실패" in warning
    assert "구버전 캐시일 수 있습니다" not in warning
    assert "0.4.9" in summary


def test_local_update_status_does_not_rewrite_parquet(tmp_path):
    store = LocalStore(tmp_path)
    cv = "2026-07-05T12-00-00KST"
    frame = pd.DataFrame({"x": [1, 2, 3]})
    artifacts = {
        "raw_fred": frame,
        "signal_matrix": frame,
        "synced_snapshot": frame,
        "chart_data": frame,
        "aux_signal_matrix": pd.DataFrame(),
        "data_quality": {"code_version": "0.4.9"},
    }
    status = {"active_cache_version": cv, "status": "success", "telegram_sent": False}
    store.publish(cv, artifacts, status)
    parquet = Path(tmp_path) / "versions" / cv / "chart_data.parquet"
    before = parquet.read_bytes()

    status2 = dict(status, telegram_sent=True)
    store.update_status(cv, status2)

    assert parquet.read_bytes() == before
    assert store.load_status()["telegram_sent"] is True


def test_refresh_publishes_artifacts_once_and_updates_status_once(monkeypatch, tmp_path):
    delegate = LocalStore(tmp_path)

    class SpyStore:
        def __init__(self):
            self.publish_calls = 0
            self.update_calls = 0

        def publish(self, *args, **kwargs):
            self.publish_calls += 1
            return delegate.publish(*args, **kwargs)

        def update_status(self, *args, **kwargs):
            self.update_calls += 1
            return delegate.update_status(*args, **kwargs)

        def last_good_raw(self):
            return delegate.last_good_raw()

        def last_good_aux(self):
            return delegate.last_good_aux()

        def find_last_good_aux(self, key):
            return delegate.find_last_good_aux(key)

    spy = SpyStore()
    monkeypatch.setattr("riskradar.refresh_service.tg.send", lambda _msg: True)
    status = run_refresh(fetcher=_fetcher(), aux_fetcher=lambda: {}, store=spy, notify=True)
    assert status["status"] == "success"
    assert spy.publish_calls == 1
    assert spy.update_calls == 1


def test_hf_data_quality_network_error_is_not_swallowed(monkeypatch):
    import huggingface_hub

    store = object.__new__(cache_store.HfDatasetStore)
    store.repo_id = "owner/repo"
    store.token = "token"
    store.api = None

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", boom)
    with pytest.raises(RuntimeError, match="network down"):
        store.load_data_quality("v1")



def test_ui_source_registers_page_load_and_manual_dataset_reload():
    import inspect
    from riskradar import ui

    source = inspect.getsource(ui.build_app)
    assert "demo.load(" in source
    assert "reload_button.click(" in source
    assert "load_dashboard_snapshot(store)" in source


def test_snapshot_loader_sees_new_active_version_without_process_restart(tmp_path):
    store = LocalStore(tmp_path)
    run_refresh(fetcher=_fetcher(), aux_fetcher=lambda: {}, store=store, notify=False)
    first = load_dashboard_snapshot(store)
    old_cv = first.status["active_cache_version"]

    new_cv = "2099-01-01T00-00-00KST"
    artifacts = dict(first.arts)
    artifacts["aux_signal_matrix"] = store.load_artifact(old_cv, "aux_signal_matrix")
    artifacts["data_quality"] = store.load_data_quality(old_cv)
    new_status = dict(first.status, active_cache_version=new_cv, code_version="0.4.9")
    store.publish(new_cv, artifacts, new_status)

    second = load_dashboard_snapshot(store)
    assert second.status["active_cache_version"] == new_cv
    assert new_cv in second.status["active_cache_version"]
