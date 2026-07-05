"""RiskRadar v0.4.0 — 조건부 해석 엔진.

흐름: frames + 보조지표 방향 -> 3축 -> 조합 탐지 -> 조합별 해석
해석 = 관찰 사실 + 가능한 설명 + 확인지표 방향별 지지/약화 + 결과 충돌 + 남은 불확실성.

지키는 선:
- '안전/위험/조심하라' 같은 종합 판단·행동 지시를 만들지 않는다.
- 확인지표가 여러 설명을 동시에 지지하면 하나로 정리하지 않고 '복합'으로 남긴다.
- 보조지표가 판정불가면 그 확인만 보류하고 나머지는 살린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import axis_engine as AX
from . import combo_rules as CR

# 최상단에 한 번에 보여줄 조합 수 상한 (blueprint: 최대 3)
MAX_READINGS = 3

# rate 방향(상승/하락/기본) -> 통일 방향(상승/하락/보합)
_RATE_DIR_MAP = {"상승": CR.UP, "하락": CR.DOWN, "기본": CR.FLAT}


@dataclass
class ReadingContext:
    frames: dict
    aux: dict            # key -> AuxDirection (aux_indicators)
    vc: AX.VolCreditAxis
    cycle: AX.CycleAxis
    rate: AX.RateAxis

    def rate_member(self, key: str) -> str:
        return self.rate.members.get(key, "기본")

    def direction(self, key: str) -> str:
        """확인지표 방향을 상승/하락/보합/판정불가로 통일."""
        if key in ("DGS30", "DGS2", "DFII10"):
            return _RATE_DIR_MAP.get(self.rate.members.get(key, "기본"), CR.FLAT)
        a = self.aux.get(key)
        if a is None:
            return CR.NA
        return getattr(a, "direction", CR.NA)


def build_context(frames: dict, aux: dict, cfg: AX.AxisCfg = AX.AXIS) -> ReadingContext:
    return ReadingContext(
        frames=frames, aux=aux,
        vc=AX.vol_credit_axis(frames, cfg),
        cycle=AX.cycle_axis(frames),
        rate=AX.rate_axis(frames),
    )


@dataclass
class CheckResult:
    key: str
    label: str
    direction: str
    text: str


@dataclass
class ComboReading:
    combo_id: str
    label: str
    observed: str
    explanations: list          # [(id, text)]
    checks: list                # [CheckResult]
    supported_ids: list         # 확인으로 지지된 설명 id
    conflict: str               # "" | 복합 안내
    uncertainty: str

    def to_dict(self) -> dict:
        return {
            "combo_id": self.combo_id, "label": self.label,
            "observed": self.observed,
            "explanations": [{"id": i, "text": t} for i, t in self.explanations],
            "checks": [{"key": c.key, "label": c.label,
                        "direction": c.direction, "text": c.text} for c in self.checks],
            "supported_ids": self.supported_ids,
            "conflict": self.conflict,
            "uncertainty": self.uncertainty,
        }


def _resolve_check(chk: CR.Check, direction: str) -> tuple[CheckResult, str | None]:
    """확인지표 방향 -> 문구 + 지지된 설명 id(있으면)."""
    if direction == CR.UP:
        text, sup = chk.up, (chk.supports_up or None)
    elif direction == CR.DOWN:
        text, sup = chk.down, (chk.supports_down or None)
    elif direction == CR.FLAT:
        text, sup = chk.flat, None
    else:  # NA
        text, sup = chk.na, None
    return CheckResult(chk.key, chk.label, direction, text), sup


def _build_reading(combo: CR.Combo, ctx: ReadingContext) -> ComboReading:
    checks, supported = [], []
    for chk in combo.checks:
        cr, sup = _resolve_check(chk, ctx.direction(chk.key))
        checks.append(cr)
        if sup:
            supported.append(sup)

    # 충돌: 서로 다른 설명이 2개 이상 동시 지지되면 하나로 정리하지 않는다
    distinct = list(dict.fromkeys(supported))
    conflict = ""
    if len(distinct) >= 2:
        conflict = ("확인지표가 여러 설명을 동시에 지지합니다. "
                    "복수 요인이 함께 작용하는 국면으로, 하나의 원인으로 정리하기 어렵습니다.")

    uncertainty = combo.uncertainty
    if any(c.direction == CR.NA for c in checks):
        uncertainty += " 일부 보조지표가 판정불가여서 해당 확인은 보류했습니다."

    return ComboReading(
        combo_id=combo.combo_id, label=combo.label, observed=combo.observed,
        explanations=combo.explanations, checks=checks,
        supported_ids=distinct, conflict=conflict, uncertainty=uncertainty,
    )


def read_all(frames: dict, aux: dict, cfg: AX.AxisCfg = AX.AXIS,
             max_readings: int = MAX_READINGS) -> list[ComboReading]:
    ctx = build_context(frames, aux, cfg)
    out = []
    for combo in CR.COMBOS:
        try:
            if combo.detect(ctx):
                out.append(_build_reading(combo, ctx))
        except Exception:  # noqa: BLE001 - 한 조합의 문제로 전체를 깨지 않음
            continue
        if len(out) >= max_readings:
            break
    return out
