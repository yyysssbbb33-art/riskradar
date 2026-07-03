"""refresh 오케스트레이션 (GitHub Actions 또는 CLI가 호출).

반환 status: success | partial_success | failed
Telegram 실패는 데이터 갱신 성공을 깨지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from . import config as C
from . import fred_client, pipeline
from . import telegram_client as tg
from . import transforms as T

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
                store=None, notify: bool = True) -> dict:
    """전체 refresh. fetcher/store 주입으로 오프라인 테스트 가능."""
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

        # 4) artifacts
        artifacts = {
            "raw_fred": _raw_long(raw_by_key, started, set(stale)),
            "signal_matrix": matrix,
            "chart_data": chart,
            "synced_snapshot": _synced_df(out["frames"], snap),
            "data_quality": {
                "failed_series": failed, "stale_series": stale,
                "synced_staleness_days": snap["synced_staleness_days"],
                "synced_staleness_label": T.staleness_label(
                    snap["synced_staleness_days"]),
                "row_counts": {k: int(len(v)) for k, v in raw_by_key.items()},
            },
        }
        status_str = "partial_success" if stale else "success"
        finished = _now_kst().isoformat()
        status = {
            "schema_version": "1.0", "active_cache_version": cache_version,
            "status": status_str,
            "last_refresh_started_at": started, "last_refresh_finished_at": finished,
            "last_success_at": finished,
            "failed_series": failed, "stale_series": stale,
            "synced_date": snap["synced_date"],
            "synced_staleness_days": snap["synced_staleness_days"],
            "latest_observation_dates": {
                C.SERIES[k].series_id: pd.to_datetime(v["date"]).max().strftime("%Y-%m-%d")
                for k, v in raw_by_key.items()},
            "telegram_sent": False,
        }

        # 5) publish (포인터 마지막)
        store.publish(cache_version, artifacts, status)

        # 6) telegram (실패해도 refresh 성공 유지)
        if notify:
            batch = now.strftime("%Y-%m-%d %H:%M KST")
            msg = (tg.build_partial(cache_version, matrix, snap, failed, stale)
                   if stale else
                   tg.build_success(batch, cache_version, matrix, snap, stale))
            sent = tg.send(msg)
            status["telegram_sent"] = sent
            store.publish(cache_version, artifacts, status)  # telegram_sent 반영

        log.info("refresh %s (%s)", status_str, cache_version)
        return status

    except Exception as e:  # noqa: BLE001
        log.exception("refresh failed")
        if notify:
            tg.send(tg.build_failure("run_refresh", f"{type(e).__name__}: {e}"))
        return {"status": "failed", "error": f"{type(e).__name__}: {e}",
                "active_cache_version": None}


def _n(x):
    return None if pd.isna(x) else float(x)
