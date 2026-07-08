"""기업 신용 범위·지속 엔진 검증 보조도구.

임계값을 특정 위기 사례에 맞춰 학습시키지 않는다. 대신:
1) 평온 구간 오탐률,
2) 알려진 스트레스 구간의 상식적 작동(sanity check),
3) 임계 백분위 ±2~3 변화에 대한 민감도
를 따로 확인한다.

이 모듈은 운영 판정을 만들지 않고 개발·검증에서만 사용한다.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .credit_episode import CreditEpisodeCfg, build_credit_episode


def _episode_sets(episodes: pd.DataFrame) -> set[tuple[str, ...]]:
    if episodes is None or episodes.empty:
        return set()
    out: set[tuple[str, ...]] = set()
    for _, row in episodes.iterrows():
        participants = tuple(sorted(x for x in str(row.get("participants", "")).split(",") if x))
        if participants:
            out.add(participants)
    return out


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return 0.0 if not union else len(a & b) / len(union)


def threshold_sensitivity(node_frames: dict[str, pd.DataFrame],
                          vix_frame: pd.DataFrame | None = None,
                          cfg: CreditEpisodeCfg = CreditEpisodeCfg(),
                          deltas: tuple[float, ...] = (-3.0, 0.0, 3.0)) -> pd.DataFrame:
    """후보 백분위를 흔들었을 때 변화 흐름 변화 집합이 얼마나 유지되는지 본다."""
    runs: dict[float, object] = {}
    for delta in deltas:
        c = replace(cfg, candidate_pct=max(0.0, min(100.0, cfg.candidate_pct + delta)))
        runs[delta] = build_credit_episode(node_frames, vix_frame=vix_frame, cfg=c)

    base_delta = 0.0 if 0.0 in runs else deltas[len(deltas) // 2]
    base = runs[base_delta]
    base_sets = _episode_sets(base.episodes)
    base_count = len(base.episodes)
    rows = []
    for delta, result in runs.items():
        episode_sets = _episode_sets(result.episodes)
        current = result.current.get("episode") or {}
        rows.append({
            "delta_pct_point": float(delta),
            "candidate_pct": float(cfg.candidate_pct + delta),
            "episode_count": int(len(result.episodes)),
            "episode_count_change": int(len(result.episodes) - base_count),
            "participant_set_jaccard_vs_base": round(jaccard(base_sets, episode_sets), 3),
            "current_episode_state": str(current.get("state", "none")),
            "current_participants": ",".join(current.get("participants") or []),
        })
    return pd.DataFrame(rows).sort_values("delta_pct_point").reset_index(drop=True)


def calm_window_false_positive_rate(node_history: pd.DataFrame,
                                    start: str, end: str) -> dict:
    """지정 평온 구간에서 뚜렷한 변화 상태가 켜진 관측일 비율을 계산한다.

    ``early_change``는 관찰 단계라 뚜렷한 변화 오탐으로 세지 않는다.
    """
    if node_history is None or node_history.empty:
        return {"observations": 0, "official_active_observations": 0, "false_positive_rate": None}
    d = node_history.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.loc[(d["date"] >= pd.Timestamp(start)) & (d["date"] <= pd.Timestamp(end))]
    if d.empty:
        return {"observations": 0, "official_active_observations": 0, "false_positive_rate": None}
    active = d["state"].astype(str).isin({"newly_rising", "rising_persistent", "retracing"})
    return {
        "observations": int(len(d)),
        "official_active_observations": int(active.sum()),
        "false_positive_rate": round(float(active.mean()), 4),
    }
