from __future__ import annotations

import pandas as pd

from riskradar import aux_config as AC
from riskradar import cache_store as CS
from riskradar import config as C
from riskradar import fred_client as FC
from riskradar import refresh_service as RS
from riskradar import telegram_client as TG
from tests import synth


def _core_fetcher(rb):
    return lambda: {k: FC.FetchResult(k, True, v) for k, v in rb.items()}


def _dfii30_from_core(rb):
    d = rb["DGS30"].copy()
    d["value_raw"] = pd.to_numeric(d["value_raw"], errors="coerce") - 2.0
    return d


def test_rate_component_is_not_core_or_aux_signal():
    assert "DFII30" not in C.SERIES
    assert "DFII30" not in AC.AUX_ORDER
    assert "INFLCOMP30" not in AC.AUX_ORDER


def test_refresh_fetches_dfii30_once_and_publishes_shared_result(tmp_path):
    rb = synth.make_raw_by_key(n=1200)
    dfii30 = _dfii30_from_core(rb)
    calls = {"n": 0}

    def rate_fetcher():
        calls["n"] += 1
        return FC.FetchResult("DFII30", True, dfii30)

    store = CS.LocalStore(tmp_path)
    status = RS.run_refresh(
        fetcher=_core_fetcher(rb),
        aux_fetcher=lambda: {},
        rate_fetcher=rate_fetcher,
        store=store,
        notify=False,
    )
    assert status["status"] == "success"
    assert calls["n"] == 1

    cv = status["active_cache_version"]
    series = store.load_artifact(cv, "rate_composition_series")
    summary = store.load_json_artifact(cv, "rate_composition")
    assert not series.empty
    assert summary["status"] == "ok"
    assert summary["schema_version"] == "rate-composition-v1"
    p = summary["primary"]
    assert abs(p["identity_residual_bp"]) < 1e-8
    assert p["DGS30_change_bp"] == p["DFII30_change_bp"] + p["INFLCOMP30_change_bp"]


def test_dfii30_failure_is_consistently_unavailable_without_breaking_core_refresh(tmp_path):
    rb = synth.make_raw_by_key(n=1200)
    store = CS.LocalStore(tmp_path)

    status = RS.run_refresh(
        fetcher=_core_fetcher(rb),
        aux_fetcher=lambda: {},
        rate_fetcher=lambda: FC.FetchResult("DFII30", False, None, "timeout"),
        store=store,
        notify=False,
    )
    assert status["status"] == "success"
    cv = status["active_cache_version"]
    summary = store.load_json_artifact(cv, "rate_composition")
    series = store.load_artifact(cv, "rate_composition_series")
    dq = store.load_data_quality(cv)
    assert summary["status"] == "unavailable"
    assert "timeout" in str(summary.get("fetch_error"))
    assert series.empty
    assert dq["rate_composition"]["status"] == "unavailable"
    assert "확인 불가" in TG._rate_composition_lines(summary)[-1] or "확인 불가" in "\n".join(TG._rate_composition_lines(summary))


def test_rate_artifacts_are_optional_for_old_cache_versions(tmp_path):
    store = CS.LocalStore(tmp_path)
    cv = "2026-07-08T09-00-00KST"
    vdir = tmp_path / "versions" / cv
    vdir.mkdir(parents=True)
    assert store.load_artifact(cv, "rate_composition_series").empty
    assert store.load_json_artifact(cv, "rate_composition") == {}
