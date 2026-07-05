"""RiskRadar v0.4.0 — 보조지표 파이프라인 통합 테스트.

- run_refresh가 aux_signal_matrix를 저장하는가
- 보조지표 실패해도 핵심 6개 정상이면 전체 success인가
- 옛 버전(aux 없음)에서도 load_artifact가 빈 df로 관용 처리되는가
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from riskradar import cache_store, fred_client as FC
from riskradar import refresh_service as RS
from riskradar import aux_config as AC
from riskradar.aux_indicators import AuxDirection, DIRECTION_UP

from synth import make_raw_by_key


def _core_fetcher(rb):
    return lambda: {k: FC.FetchResult(k, True, v) for k, v in rb.items()}


def _aux_ok():
    def _f():
        out = {}
        for key in AC.AUX_ORDER:
            spec = AC.AUX_SERIES[key]
            out[key] = AuxDirection(
                key, spec.display_name, True, 2.0, "2026-07-03",
                12.0, DIRECTION_UP, 88.0, 400, None)
        return out
    return _f


def test_refresh_writes_aux_matrix(tmp_path):
    store = cache_store.LocalStore(tmp_path)
    rb = make_raw_by_key()
    status = RS.run_refresh(fetcher=_core_fetcher(rb), aux_fetcher=_aux_ok(),
                            store=store, notify=False)
    assert status["status"] == "success"

    cv = status["active_cache_version"]
    aux = store.load_artifact(cv, "aux_signal_matrix")
    assert not aux.empty
    assert set(aux["key"]) == set(AC.AUX_ORDER)
    assert (aux["direction"] == DIRECTION_UP).all()
    # freshness 컬럼 존재
    assert {"stale_days", "staleness_label", "change_1m"}.issubset(aux.columns)


def test_aux_failure_does_not_break_refresh(tmp_path):
    store = cache_store.LocalStore(tmp_path)
    rb = make_raw_by_key()

    def _aux_boom():
        raise RuntimeError("aux source down")

    status = RS.run_refresh(fetcher=_core_fetcher(rb), aux_fetcher=_aux_boom,
                            store=store, notify=False)
    # 핵심 6개 정상 -> 전체는 성공
    assert status["status"] == "success"
    cv = status["active_cache_version"]
    aux = store.load_artifact(cv, "aux_signal_matrix")
    # 행은 있되 전부 판정불가/실패로 표시
    assert set(aux["key"]) == set(AC.AUX_ORDER)
    assert (aux["direction"] == "판정불가").all()
    assert not aux["ok"].any()


def test_partial_aux_marks_only_failed(tmp_path):
    store = cache_store.LocalStore(tmp_path)
    rb = make_raw_by_key()

    def _aux_partial():
        out = _aux_ok()()
        out["TERMPREM"] = AuxDirection(
            "TERMPREM", "10Y Term Premium (KW)", False, None, None,
            None, "판정불가", None, 0, "source timeout")
        return out

    status = RS.run_refresh(fetcher=_core_fetcher(rb), aux_fetcher=_aux_partial,
                            store=store, notify=False)
    assert status["status"] == "success"
    cv = status["active_cache_version"]
    aux = store.load_artifact(cv, "aux_signal_matrix").set_index("key")
    assert aux.loc["BREAKEVEN", "ok"] and aux.loc["IGOAS", "ok"]
    assert not aux.loc["TERMPREM", "ok"]


def test_backward_compat_missing_aux(tmp_path):
    # aux 없이 저장된 옛 버전을 흉내: aux_signal_matrix 파일이 없어도 빈 df
    store = cache_store.LocalStore(tmp_path)
    rb = make_raw_by_key()
    status = RS.run_refresh(fetcher=_core_fetcher(rb), aux_fetcher=_aux_ok(),
                            store=store, notify=False)
    cv = status["active_cache_version"]
    # 파일 강제 삭제 (옛 버전 시뮬레이션)
    (tmp_path / "versions" / cv / "aux_signal_matrix.parquet").unlink()
    got = store.load_artifact(cv, "aux_signal_matrix")
    assert got.empty  # 예외 대신 빈 DataFrame
