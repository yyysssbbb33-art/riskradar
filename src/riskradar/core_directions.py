"""핵심 지표의 조합 해석용 방향 판정.

3축 상태 판정과 별개다. 축은 기존의 강한 상태 규칙을 쓰고,
조합 탐지는 각 지표의 약 1개월 변화가 자기 역사에서 충분히 큰지를 기준으로
상승/하락/보합을 구분한다. 모든 컷은 C등급 운영 규칙이다.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

UP, DOWN, FLAT, NA = "상승", "하락", "보합", "판정불가"


@dataclass(frozen=True)
class CoreDirectionCfg:
    flat_abs_pct: float = 40.0
    min_obs: int = 250


CORE_DIRECTION = CoreDirectionCfg()


@dataclass(frozen=True)
class CoreDirection:
    key: str
    direction: str
    change_1m: float | None
    pct_in_history: float | None
    n_obs: int


def compute_core_direction(key: str, frame: pd.DataFrame | None,
                           cfg: CoreDirectionCfg = CORE_DIRECTION) -> CoreDirection:
    if frame is None or frame.empty or "change_20obs" not in frame:
        return CoreDirection(key, NA, None, None, 0)

    changes = pd.to_numeric(frame["change_20obs"], errors="coerce")
    valid = changes.dropna()
    latest = changes.iloc[-1]
    n = int(valid.shape[0])

    if pd.isna(latest) or n < cfg.min_obs:
        return CoreDirection(key, NA, None if pd.isna(latest) else float(latest), None, n)

    latest = float(latest)
    abs_pct = float((valid.abs() <= abs(latest)).mean() * 100.0)
    if abs_pct < cfg.flat_abs_pct:
        direction = FLAT
    elif latest > 0:
        direction = UP
    elif latest < 0:
        direction = DOWN
    else:
        direction = FLAT
    return CoreDirection(key, direction, latest, round(abs_pct, 1), n)
