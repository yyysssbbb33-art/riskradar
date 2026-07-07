import pandas as pd

from riskradar import cache_store as CS
from riskradar import fred_client as FC
from riskradar import refresh_service as RS
from riskradar import telegram_client as tg
from tests import synth


def _fetcher(rb):
    return lambda: {k: FC.FetchResult(k, True, v) for k, v in rb.items()}


def test_publish_load_roundtrip(tmp_path):
    rb = synth.make_raw_by_key(n=1200)
    store = CS.LocalStore(tmp_path)
    status = RS.run_refresh(fetcher=_fetcher(rb), store=store, notify=False)
    assert status["status"] == "success"
    st2, arts = store.load()
    assert st2["active_cache_version"] == status["active_cache_version"]
    assert set(arts) >= {"raw_fred", "signal_matrix", "chart_data", "synced_snapshot"}
    assert len(arts["signal_matrix"]) == 6


def test_pointer_written_last(tmp_path):
    # data_status.json 은 versions/ 산출물이 모두 존재할 때만 유효해야 함
    rb = synth.make_raw_by_key(n=1200)
    store = CS.LocalStore(tmp_path)
    RS.run_refresh(fetcher=_fetcher(rb), store=store, notify=False)
    st, _ = store.load()
    vdir = tmp_path / "versions" / st["active_cache_version"]
    for name in CS.ARTIFACT_PARQUETS:
        assert (vdir / f"{name}.parquet").exists()


def test_partial_failure_uses_last_good_raw(tmp_path):
    rb = synth.make_raw_by_key(n=1200)
    store = CS.LocalStore(tmp_path)
    # 1차: 전체 성공으로 last-good raw 확보
    RS.run_refresh(fetcher=_fetcher(rb), store=store, notify=False)

    # 2차: HY OAS fetch 실패
    def partial():
        out = {k: FC.FetchResult(k, True, v) for k, v in rb.items()}
        out["HYOAS"] = FC.FetchResult("HYOAS", False, None, "timeout")
        return out

    status = RS.run_refresh(fetcher=partial, store=store, notify=False)
    assert status["status"] == "partial_success"
    assert status["stale_series"] == ["HYOAS"]
    assert status["failed_series"] == ["HYOAS"]
    _, arts = store.load()
    assert len(arts["signal_matrix"]) == 6  # HY OAS 여전히 표시(직전 raw)


def test_missing_required_no_lastgood_fails(tmp_path):
    rb = synth.make_raw_by_key(n=1200)
    store = CS.LocalStore(tmp_path)

    def partial():
        out = {k: FC.FetchResult(k, True, v) for k, v in rb.items()}
        out["VIX"] = FC.FetchResult("VIX", False, None, "timeout")
        return out

    status = RS.run_refresh(fetcher=partial, store=store, notify=False)
    assert status["status"] == "failed"


def test_retention_prune(tmp_path, monkeypatch):
    rb = synth.make_raw_by_key(n=1100)
    store = CS.LocalStore(tmp_path)
    # v0.6.2는 날짜+개수 이중 보존 정책이다. 이 테스트는 안전 상한 동작만 격리해 확인한다.
    monkeypatch.setattr(CS, "KEEP_LAST_N", 3)
    monkeypatch.setattr(CS, "KEEP_MIN_DAYS", 0)
    monkeypatch.setattr(CS, "KEEP_MAX_N", 3)
    import time
    for _ in range(5):
        RS.run_refresh(fetcher=_fetcher(rb), store=store, notify=False)
        time.sleep(1.1)  # cache_version 초 단위 구분
    versions = list((tmp_path / "versions").iterdir())
    assert len(versions) <= 3


def test_telegram_messages_build(tmp_path):
    rb = synth.make_raw_by_key(n=1100)
    store = CS.LocalStore(tmp_path)
    RS.run_refresh(fetcher=_fetcher(rb), store=store, notify=False)
    _, arts = store.load()
    from riskradar import pipeline
    snap = pipeline.compute_all(rb)["synced"]
    ok = tg.build_success("2026-07-03 08:30 KST", "cv", arts["signal_matrix"], snap, [])
    assert "RiskRadar 업데이트 완료" in ok
    part = tg.build_partial("cv", arts["signal_matrix"], snap, ["HYOAS"], ["HYOAS"])
    assert "부분 업데이트" in part and "HYOAS" in part
    fail = tg.build_failure("build", "ValueError: x")
    assert "실패" in fail


def test_telegram_send_no_creds_returns_false(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert tg.send("hi") is False


def test_load_30d_history_from_versions(tmp_path):
    rb = synth.make_raw_by_key(n=1200)
    store = CS.LocalStore(tmp_path)
    status = RS.run_refresh(fetcher=_fetcher(rb), store=store, notify=False)
    hist = store.load_history(days=30)
    assert not hist.empty
    assert set(hist["key"]) == set(rb.keys())
    assert status["active_cache_version"] in set(hist["cache_version"])
    assert {"snapshot_date", "latest_value", "state_label"}.issubset(hist.columns)


def test_history_keeps_last_snapshot_per_day():
    versions = ["2026-07-01T08-30-00KST", "2026-07-01T10-00-00KST", "2026-07-02T08-30-00KST"]

    def loader(version, name):
        assert name == "signal_matrix"
        return pd.DataFrame([{
            "key": "VIX", "display_name": "VIX", "latest_value": 10.0,
            "value_unit": "index", "change_20obs": 1.0, "change_60obs": 2.0,
            "change_unit": "pt", "percentile_5y": 50.0, "percentile_10y": 50.0,
            "state_label": "평온", "state_reason": version, "drop_flag": False,
        }])

    hist = CS._history_from_versions(loader, versions, days=3650)
    july1 = hist.loc[hist["snapshot_date"] == "2026-07-01"]
    assert len(july1) == 1
    assert july1.iloc[0]["cache_version"] == "2026-07-01T10-00-00KST"
