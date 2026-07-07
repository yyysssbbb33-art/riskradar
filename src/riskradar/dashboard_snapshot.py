"""UI가 읽을 한 시점의 캐시 스냅샷.

핵심 원칙:
- data_status.json의 active_cache_version을 한 번 정한 뒤 모든 부속 파일을 그 버전으로 읽는다.
- 브라우저가 페이지를 열 때마다 다시 호출할 수 있다.
- 부속 파일 하나의 오류를 '구버전 데이터'로 조용히 오인하지 않고 진단 정보로 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from . import config as C
from .monthly_view import reconstruct_history_from_chart_data

KST = ZoneInfo(C.APP_TIMEZONE)


@dataclass
class DashboardSnapshot:
    status: dict
    arts: dict[str, pd.DataFrame]
    data_quality: dict
    aux_df: pd.DataFrame
    aux_raw: pd.DataFrame
    credit_node_history: pd.DataFrame
    credit_episodes: pd.DataFrame
    decision_snapshot: dict
    decision_diff: dict
    history: pd.DataFrame
    history_source: str
    history_error: str | None = None
    load_errors: list[str] = field(default_factory=list)
    loaded_at_kst: str = ""


def load_dashboard_snapshot(store, days: int = 30) -> DashboardSnapshot:
    """활성 버전 하나를 고정해 UI용 자료를 일관되게 읽는다."""
    status, arts = store.load()
    cache_version = str(status["active_cache_version"])
    errors: list[str] = []

    try:
        data_quality = store.load_data_quality(cache_version)
    except Exception as e:  # noqa: BLE001 - UI는 핵심표를 살리고 오류를 노출한다.
        data_quality = {}
        errors.append(f"data_quality.json 읽기 실패: {type(e).__name__}: {e}")

    try:
        aux_df = store.load_artifact(cache_version, "aux_signal_matrix")
    except Exception as e:  # noqa: BLE001
        aux_df = pd.DataFrame()
        errors.append(f"보조지표 파일 읽기 실패: {type(e).__name__}: {e}")


    def _optional(name: str, label: str) -> pd.DataFrame:
        try:
            return store.load_artifact(cache_version, name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{label} 읽기 실패: {type(e).__name__}: {e}")
            return pd.DataFrame()

    aux_raw = _optional("aux_raw", "확인지표 원자료")
    credit_node_history = _optional("credit_episode_nodes", "신용 에피소드 노드 기록")
    credit_episodes = _optional("credit_episodes", "신용 에피소드 기록")

    def _optional_json(name: str, label: str) -> dict:
        loader = getattr(store, "load_json_artifact", None)
        if loader is None:
            return {}
        try:
            return loader(cache_version, name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{label} 읽기 실패: {type(e).__name__}: {e}")
            return {}

    decision_snapshot = _optional_json("decision_snapshot", "판정 스냅샷")
    decision_diff = _optional_json("decision_diff", "판정 변화 기록")

    history = reconstruct_history_from_chart_data(arts.get("chart_data", pd.DataFrame()), days=days)
    history_source = "과거 원자료 재구성" if not history.empty else "저장 스냅샷"
    history_error = None
    if history.empty:
        try:
            history = store.load_history(days=days)
        except Exception as e:  # noqa: BLE001
            history = pd.DataFrame()
            history_error = f"지난 {days}일 기록 읽기 실패: {type(e).__name__}: {e}"
            errors.append(history_error)

    return DashboardSnapshot(
        status=status,
        arts=arts,
        data_quality=data_quality,
        aux_df=aux_df,
        aux_raw=aux_raw,
        credit_node_history=credit_node_history,
        credit_episodes=credit_episodes,
        decision_snapshot=decision_snapshot,
        decision_diff=decision_diff,
        history=history,
        history_source=history_source,
        history_error=history_error,
        load_errors=errors,
        loaded_at_kst=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
    )
