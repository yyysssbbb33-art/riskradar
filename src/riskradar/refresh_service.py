"""refresh 오케스트레이션 (GitHub Actions 또는 CLI가 호출).

반환 status: success | partial_success | failed
Telegram 실패는 데이터 갱신 성공을 깨지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from . import config as C
from . import aux_config as AC
from . import aux_indicators
from . import axis_engine
from . import credit_episode
from . import interpretation_engine
from . import fred_client, pipeline
from . import telegram_client as tg
from . import transforms as T
from .version import __version__

log = logging.getLogger(__name__)
KST = ZoneInfo(C.APP_TIMEZONE)


def _now_kst() -> datetime:
    return datetime.now(KST)


def _cache_version(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H-%M-%SKST")


def _raw_long(raw_by_key: dict[str, pd.DataFrame], fetched_at: str,
              stale: set[str]) -> pd.DataFrame:
    parts = []
    for key, df in raw_by_key.items():
        s = C.SERIES[key]
        p = df.copy()
        p["series_id"] = s.series_id
        p["key"] = key
        p["value"] = T.to_internal_value(key, p["value_raw"])
        p["unit"] = s.value_unit
        p["fetched_at_kst"] = fetched_at
        p["source"] = "FRED"
        p["fetch_status"] = "stale" if key in stale else "ok"
        parts.append(p[["series_id", "key", "date", "value_raw", "value",
                        "unit", "fetched_at_kst", "source", "fetch_status"]])
    return pd.concat(parts, ignore_index=True)



def _aux_raw_long(raw_frames: dict[str, pd.DataFrame], fetched_at: str) -> pd.DataFrame:
    """확인지표 원자료를 장기 포맷으로 저장한다. 에피소드 재구성과 진단용."""
    parts = []
    for key, df in raw_frames.items():
        if key not in AC.AUX_SERIES or df is None or df.empty:
            continue
        spec = AC.AUX_SERIES[key]
        p = df.copy()
        p["date"] = pd.to_datetime(p["date"])
        p["key"] = key
        p["series_id"] = spec.series_id
        p["value"] = pd.to_numeric(p["value_raw"], errors="coerce") * spec.raw_to_value
        p["unit"] = spec.value_unit
        p["fetched_at_kst"] = fetched_at
        p["source"] = "FRED"
        parts.append(p[["series_id", "key", "date", "value_raw", "value", "unit", "fetched_at_kst", "source"]])
    if not parts:
        return pd.DataFrame(columns=["series_id", "key", "date", "value_raw", "value", "unit", "fetched_at_kst", "source"])
    return pd.concat(parts, ignore_index=True)


def _synced_df(frames: dict[str, pd.DataFrame], snap: dict) -> pd.DataFrame:
    if snap["synced_date"] is None:
        return pd.DataFrame(columns=["synced_date", "series_id", "key", "value",
                                     "change_20obs", "change_60obs", "state_code",
                                     "state_label"])
    sd = pd.to_datetime(snap["synced_date"])
    rows = []
    for key, f in frames.items():
        r = f.loc[pd.to_datetime(f["date"]) == sd].iloc[-1]
        rows.append({
            "synced_date": snap["synced_date"], "series_id": C.SERIES[key].series_id,
            "key": key, "value": float(r["value"]),
            "change_20obs": _n(r["change_20obs"]), "change_60obs": _n(r["change_60obs"]),
            "state_code": r["state_code"], "state_label": r["state_label"],
        })
    return pd.DataFrame(rows)


def run_refresh(fetcher: Callable[[], dict] | None = None,
                aux_fetcher: Callable[[], dict] | None = None,
                store=None, notify: bool = True) -> dict:
    """전체 refresh. fetcher/aux_fetcher/store 주입으로 오프라인 테스트 가능."""
    from . import cache_store
    store = store or cache_store.get_store()
    now = _now_kst()
    started = now.isoformat()
    cache_version = _cache_version(now)
    failed: list[str] = []
    stale: list[str] = []

    try:
        # 1) fetch
        results = (fetcher() if fetcher else
                   {k: v for k, v in fred_client.fetch_all().items()})
        raw_by_key: dict[str, pd.DataFrame] = {}
        for key in C.SERIES_ORDER:
            r = results[key]
            if getattr(r, "ok", False):
                raw_by_key[key] = r.df
            else:
                failed.append(key)

        # 2) 부분 실패 -> last-good raw 유지
        if failed:
            lg = store.last_good_raw()
            for key in list(failed):
                if lg is not None and key in set(lg["key"].unique()):
                    sub = lg.loc[lg["key"] == key, ["date", "value_raw"]].copy()
                    sub["date"] = pd.to_datetime(sub["date"])
                    raw_by_key[key] = sub.sort_values("date").reset_index(drop=True)
                    stale.append(key)
                else:
                    # 필수 시리즈에 과거 데이터조차 없으면 실패
                    raise RuntimeError(f"no last-good raw for {key}")

        # 3) compute
        out = pipeline.compute_all(raw_by_key)
        matrix, chart, snap = out["signal_matrix"], out["chart_data"], out["synced"]

        # 3b) 보조지표(2층). 실패해도 핵심 6개가 정상이면 전체는 성공.
        aux_raw_frames: dict[str, pd.DataFrame] = {}
        try:
            if aux_fetcher:
                supplied = aux_fetcher()
                if isinstance(supplied, aux_indicators.AuxCollection):
                    aux = supplied.directions
                    aux_raw_frames = supplied.raw_frames
                else:
                    aux = supplied
            else:
                bundle = aux_indicators.collect_aux_bundle()
                aux = bundle.directions
                aux_raw_frames = bundle.raw_frames
        except Exception as e:  # noqa: BLE001 - 확인지표는 전체를 깨지 않음
            log.warning("aux collect failed: %s", e)
            aux = {}
        aux_matrix = _aux_matrix(aux, now)
        aux_failed = [k for k in AC.AUX_ORDER
                      if k not in aux or not getattr(aux[k], "ok", False)]
        # 보조지표 일시 실패 시 직전 성공값을 가져오되 최신성 표시는 다시 계산한다.
        # 오래된 값은 해석 엔진이 자동으로 집계에서 제외한다.
        aux_matrix = _carry_forward_aux(aux_matrix, store, now)

        # 범위·지속 엔진은 최신값 한 점이 아니라 BBB/A/CP의 과거 경로가 필요하다.
        # 이번 수집이 실패했지만 직전 실제 성공값이 아직 stale이 아니면, 같은 원칙으로
        # 마지막 저장 원자료를 복구해 엔진 경로를 유지한다. 오래된 자료는 사용하지 않는다.
        raw_finder = getattr(store, "find_last_good_aux_raw", None)
        if raw_finder is not None:
            for key in AC.ENGINE_AUX_ORDER:
                if key in aux_raw_frames and aux_raw_frames[key] is not None and not aux_raw_frames[key].empty:
                    continue
                hit = aux_matrix.loc[aux_matrix["key"].astype(str) == key]
                if hit.empty or str(hit.iloc[-1].get("staleness_label", "stale")) == "stale":
                    continue
                try:
                    previous_raw = raw_finder(key)
                except Exception as e:  # noqa: BLE001
                    log.warning("last-good aux raw search failed for %s: %s", key, e)
                    previous_raw = None
                if previous_raw is None or previous_raw.empty:
                    continue
                aux_raw_frames[key] = previous_raw[["date", "value_raw"]].copy()

        # 3c) 기업 신용 범위·지속 엔진. 순서 주장은 하지 않고 범위·지속·잔존을 본다.
        credit_result = None
        try:
            node_frames = credit_episode.raw_to_node_frames(out["frames"], aux_raw_frames)
            credit_result = credit_episode.build_credit_episode(
                node_frames, vix_frame=out["frames"].get("VIX")
            )
        except Exception as e:  # noqa: BLE001
            log.warning("credit episode engine failed: %s", e)

        # 3d) 3축 복합 조망 + 조건부 해석. 계산 실패는 전체를 깨지 않음.
        try:
            composite = axis_engine.composite_view(out["frames"])
            aux_status = {
                str(r["key"]): str(r["staleness_label"])
                for _, r in aux_matrix.iterrows()
                if str(r["key"]) in AC.ENGINE_AUX_ORDER
            }
            aux_for_reading = {
                str(r["key"]): SimpleNamespace(direction=str(r["direction"]))
                for _, r in aux_matrix.iterrows()
                if str(r["key"]) in AC.ENGINE_AUX_ORDER
            }
            readings = interpretation_engine.read_all(
                out["frames"], aux_for_reading, aux_status=aux_status
            )
            axes = composite.to_dict()
            reading_dicts = [r.to_dict() for r in readings]
        except Exception as e:  # noqa: BLE001
            log.warning("axis/interpretation failed: %s", e)
            axes, reading_dicts = None, []

        # 4) artifacts
        artifacts = {
            "raw_fred": _raw_long(raw_by_key, started, set(stale)),
            "signal_matrix": matrix,
            "chart_data": chart,
            "synced_snapshot": _synced_df(out["frames"], snap),
            "aux_signal_matrix": aux_matrix,
            "aux_raw": _aux_raw_long(aux_raw_frames, started),
            "credit_episode_nodes": (credit_result.node_history if credit_result is not None else pd.DataFrame()),
            "credit_episodes": (credit_result.episodes if credit_result is not None else pd.DataFrame()),
            "data_quality": {
                "code_version": __version__,
                "failed_series": failed, "stale_series": stale,
                "synced_staleness_days": snap["synced_staleness_days"],
                "synced_staleness_label": T.staleness_label(
                    snap["synced_staleness_days"]),
                "row_counts": {k: int(len(v)) for k, v in raw_by_key.items()},
                # 실제 해석에 사용한 방향을 기록한다. 현재 수집 실패 후 과거값을
                # 이어 쓴 경우에도 aux_signal_matrix와 같은 방향을 보여준다.
                "aux_directions": {
                    str(r["key"]): str(r["direction"])
                    for _, r in aux_matrix.iterrows()
                },
                "aux_failed": aux_failed,
                "aux_fetch_status": {
                    str(r["key"]): str(r["fetch_status"])
                    for _, r in aux_matrix.iterrows()
                },
                "aux_errors": {
                    str(r["key"]): str(r.get("error", ""))
                    for _, r in aux_matrix.iterrows()
                    if str(r.get("fetch_status", "ok")) != "ok"
                },
                "axes": axes,
                "readings": reading_dicts,
                "credit_episode": (credit_result.to_quality_dict() if credit_result is not None else {}),
                "ice_history_policy": {
                    "company_bond_window": "최근 공식 FRED 약 3년 자료",
                    "long_history_claims": False,
                    "hyoas_position_years": 3,
                },
            },
        }
        status_str = "partial_success" if stale else "success"
        finished = _now_kst().isoformat()
        status = {
            "schema_version": "1.0", "code_version": __version__,
            "active_cache_version": cache_version,
            "status": status_str,
            "last_refresh_started_at": started, "last_refresh_finished_at": finished,
            "last_success_at": finished,
            "failed_series": failed, "stale_series": stale,
            "synced_date": snap["synced_date"],
            "synced_staleness_days": snap["synced_staleness_days"],
            "latest_observation_dates": {
                C.SERIES[k].series_id: pd.to_datetime(v["date"]).max().strftime("%Y-%m-%d")
                for k, v in raw_by_key.items()},
            "aux_failed": aux_failed,
            "aux_fetch_status": {
                str(r["key"]): str(r["fetch_status"])
                for _, r in aux_matrix.iterrows()
            },
            "telegram_sent": False,
        }

        # 5) publish (포인터 마지막)
        store.publish(cache_version, artifacts, status)

        # 6) telegram (실패해도 refresh 성공 유지)
        if notify:
            batch = now.strftime("%Y-%m-%d %H:%M KST")
            msg = (tg.build_partial(
                       cache_version, matrix, snap, failed, stale,
                       axes=axes, readings=reading_dicts, aux_df=aux_matrix,
                       credit_episode=(credit_result.to_quality_dict() if credit_result is not None else None),
                   )
                   if stale else
                   tg.build_success(
                       batch, cache_version, matrix, snap, stale,
                       axes=axes, readings=reading_dicts, aux_df=aux_matrix,
                       credit_episode=(credit_result.to_quality_dict() if credit_result is not None else None),
                   ))
            sent = tg.send(msg)
            status["telegram_sent"] = sent
            # parquet 전체를 다시 올리지 않는다. 상태 갱신 실패도 데이터 성공을 깨지 않는다.
            updater = getattr(store, "update_status", None)
            if updater is not None:
                try:
                    updater(cache_version, status)
                except Exception as e:  # noqa: BLE001
                    log.warning("telegram status update failed: %s", e)

        log.info("refresh %s (%s)", status_str, cache_version)
        return status

    except Exception as e:  # noqa: BLE001
        log.exception("refresh failed")
        if notify:
            tg.send(tg.build_failure("run_refresh", f"{type(e).__name__}: {e}"))
        return {"status": "failed", "error": f"{type(e).__name__}: {e}",
                "active_cache_version": None}


def _aux_matrix(aux: dict, now: datetime) -> pd.DataFrame:
    """보조지표 방향 결과 + freshness를 UI/저장용 표로. 항상 AUX_ORDER 전체 행."""
    batch_date = now.date()
    rows = []
    for key in AC.AUX_ORDER:
        spec = AC.AUX_SERIES[key]
        a = aux.get(key)
        if a is None:
            rows.append({
                "key": key, "series_id": spec.series_id,
                "display_name": spec.display_name, "category": spec.category,
                "use_in_engine": spec.use_in_engine, "ok": False,
                "latest_value": None, "value_unit": spec.value_unit,
                "latest_date": None, "change_1m": None,
                "change_unit": spec.change_unit, "direction": "판정불가",
                "pct_in_history": None, "level_pct": None, "n_obs": 0,
                "history_start": None, "history_end": None, "history_years": None,
                "layer": spec.layer, "visible": spec.visible,
                "stale_days": None, "staleness_label": "stale",
                "fetch_status": "failed", "error": "missing",
            })
            continue
        if a.latest_date:
            sd = (batch_date - pd.to_datetime(a.latest_date).date()).days
            slabel = T.staleness_label(sd)
        else:
            sd, slabel = None, "stale"
        rows.append({
            "key": key, "series_id": spec.series_id,
            "display_name": spec.display_name, "category": spec.category,
            "use_in_engine": spec.use_in_engine, "ok": a.ok,
            "latest_value": a.latest_value, "value_unit": spec.value_unit,
            "latest_date": a.latest_date, "change_1m": a.change_1m,
            "change_unit": spec.change_unit, "direction": a.direction,
            "pct_in_history": a.pct_in_history,
            "level_pct": getattr(a, "level_pct", None),
            "n_obs": a.n_obs,
            "history_start": getattr(a, "history_start", None),
            "history_end": getattr(a, "history_end", None),
            "history_years": getattr(a, "history_years", None),
            "layer": spec.layer, "visible": spec.visible,
            "stale_days": sd, "staleness_label": slabel,
            "fetch_status": "ok" if a.ok else "failed", "error": a.error,
        })
    return pd.DataFrame(rows)


def _carry_forward_aux(current: pd.DataFrame, store, now: datetime) -> pd.DataFrame:
    """실패한 보조지표는 과거의 마지막 '실제 정상 수집값'으로 복구한다.

    최신 활성 캐시 하나만 보지 않는다. 버전을 최신→과거 순서로 검색하고
    ``fetch_status=ok``인 실제 성공 행만 복구 원천으로 사용한다.
    carried_forward 행을 다시 복구 원천으로 쓰지 않아 실패값 연쇄 복사를 막는다.
    """
    finder = getattr(store, "find_last_good_aux", None)
    legacy_getter = getattr(store, "last_good_aux", None)
    if finder is None and legacy_getter is None:
        return current

    out = current.copy()
    for key in AC.AUX_ORDER:
        idx = out.index[out["key"] == key]
        if len(idx) == 0:
            continue
        i = idx[0]
        cur = out.loc[i]
        missing = (not bool(cur.get("ok", False)) or
                   cur.get("latest_value") is None or pd.isna(cur.get("latest_value")))
        if not missing:
            continue

        try:
            if finder is not None:
                previous = finder(key)
            else:
                previous_all = legacy_getter()
                if previous_all is None or previous_all.empty or "key" not in previous_all.columns:
                    previous = None
                else:
                    previous = previous_all.loc[previous_all["key"].astype(str) == key].copy()
                    if "fetch_status" in previous.columns:
                        previous = previous.loc[previous["fetch_status"].astype(str) == "ok"]
                    if "latest_value" in previous.columns:
                        previous = previous.loc[pd.to_numeric(previous["latest_value"], errors="coerce").notna()]
        except Exception as e:  # noqa: BLE001
            log.warning("last-good aux search failed for %s: %s", key, e)
            continue
        if previous is None or previous.empty:
            continue

        pr = previous.iloc[-1].copy()
        if pr.get("latest_value") is None or pd.isna(pr.get("latest_value")):
            continue
        current_error = cur.get("error")
        for col in out.columns:
            if col in pr.index:
                out.at[i, col] = pr[col]
        latest_date = pr.get("latest_date")
        if latest_date:
            sd = (now.date() - pd.to_datetime(latest_date).date()).days
            out.at[i, "stale_days"] = sd
            out.at[i, "staleness_label"] = T.staleness_label(sd)
        out.at[i, "ok"] = False
        out.at[i, "fetch_status"] = "carried_forward"
        out.at[i, "error"] = current_error or "current fetch failed; using last actual successful value"
    return out


def _n(x):
    return None if pd.isna(x) else float(x)
