"""RiskRadar v0.4.1 — 조건부 해석 엔진.

핵심 3축은 기존 강한 상태 규칙을 유지한다.
조합 탐지는 별도의 자기역사 대비 방향 판정을 사용해 일반적인 상승/하락 엇갈림도 잡는다.
보조지표는 stale이면 지지/약화 집계에서 제외한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import axis_engine as AX
from . import combo_rules as CR
from .core_directions import compute_core_direction

MAX_READINGS = 3


@dataclass
class ReadingContext:
    frames: dict
    aux: dict
    aux_status: dict[str, str]
    vc: AX.VolCreditAxis
    cycle: AX.CycleAxis
    rate: AX.RateAxis
    _core_cache: dict[str, str] = field(default_factory=dict)

    def rate_member(self, key: str) -> str:
        return self.rate.members.get(key, "기본")

    def core_direction(self, key: str) -> str:
        if key not in self._core_cache:
            direction = compute_core_direction(key, self.frames.get(key)).direction
            # 짧은 합성 테스트나 초기 데이터처럼 자기역사 분포가 부족하면
            # 기존 강한 금리축 상태를 fallback으로 쓴다. 실데이터에서는 역사분포 방향이 우선이다.
            if direction == CR.NA and key in ("DGS30", "DGS2", "DFII10"):
                fallback = self.rate.members.get(key, "기본")
                direction = {"상승": CR.UP, "하락": CR.DOWN, "기본": CR.FLAT}.get(fallback, CR.FLAT)
            self._core_cache[key] = direction
        return self._core_cache[key]

    def direction(self, key: str) -> str:
        if key in ("DGS30", "DGS2", "DFII10"):
            return self.core_direction(key)
        if self.aux_status.get(key) == "stale":
            return CR.NA
        a = self.aux.get(key)
        if a is None:
            return CR.NA
        return getattr(a, "direction", CR.NA)

    def freshness(self, key: str) -> str:
        if key in ("DGS30", "DGS2", "DFII10"):
            return "normal"
        return self.aux_status.get(key, "unknown")

    def credit_widening(self) -> bool:
        if self.vc.hy_active:
            return True
        return self.direction("IGOAS") == CR.UP


def build_context(frames: dict, aux: dict,
                  aux_status: dict[str, str] | None = None,
                  cfg: AX.AxisCfg = AX.AXIS) -> ReadingContext:
    return ReadingContext(
        frames=frames,
        aux=aux,
        aux_status=aux_status or {},
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
    freshness: str = "normal"


@dataclass
class ComboReading:
    combo_id: str
    group: str
    priority: int
    label: str
    observed: str
    explanations: list
    checks: list
    supported_ids: list
    weakened_ids: list
    conflict: str
    uncertainty: str

    def to_dict(self) -> dict:
        return {
            "combo_id": self.combo_id,
            "group": self.group,
            "priority": self.priority,
            "label": self.label,
            "observed": self.observed,
            "explanations": [{"id": i, "text": t} for i, t in self.explanations],
            "checks": [
                {
                    "key": c.key,
                    "label": c.label,
                    "direction": c.direction,
                    "text": c.text,
                    "freshness": c.freshness,
                }
                for c in self.checks
            ],
            "supported_ids": self.supported_ids,
            "weakened_ids": self.weakened_ids,
            "conflict": self.conflict,
            "uncertainty": self.uncertainty,
        }


def _branch(chk: CR.Check, direction: str):
    if direction == CR.UP:
        return chk.up, chk.supports_up, chk.weakens_up
    if direction == CR.DOWN:
        return chk.down, chk.supports_down, chk.weakens_down
    if direction == CR.FLAT:
        return chk.flat, chk.supports_flat, chk.weakens_flat
    return chk.na, (), ()


def _build_reading(combo: CR.Combo, ctx: ReadingContext) -> ComboReading:
    checks: list[CheckResult] = []
    supported: list[str] = []
    weakened: list[str] = []

    for chk in combo.checks:
        direction = ctx.direction(chk.key)
        text, supports, weakens = _branch(chk, direction)
        freshness = ctx.freshness(chk.key)
        if freshness == "delayed" and direction != CR.NA:
            text += " (업데이트가 다소 지연된 자료입니다.)"
        checks.append(CheckResult(chk.key, chk.label, direction, text, freshness))
        supported.extend(supports)
        weakened.extend(weakens)

    supported_ids = list(dict.fromkeys(supported))
    weakened_ids = [x for x in dict.fromkeys(weakened) if x not in supported_ids]

    conflict = ""
    if len(supported_ids) >= 2:
        conflict = (
            "확인지표가 서로 다른 설명을 동시에 지지합니다. 복수 요인이 함께 작용하는 국면일 수 있어 "
            "하나의 원인으로 정리하기 어렵습니다."
        )

    uncertainty = combo.uncertainty
    if any(c.direction == CR.NA for c in checks):
        uncertainty += " 일부 확인지표가 판정불가 또는 오래된 상태라 해당 확인은 보류했습니다."
    if not supported_ids:
        uncertainty += " 현재 확인지표만으로 상대적으로 우세한 설명을 고르기 어렵습니다."

    return ComboReading(
        combo_id=combo.combo_id,
        group=combo.group,
        priority=combo.priority,
        label=combo.label,
        observed=combo.observed,
        explanations=combo.explanations,
        checks=checks,
        supported_ids=supported_ids,
        weakened_ids=weakened_ids,
        conflict=conflict,
        uncertainty=uncertainty,
    )


def read_all(frames: dict, aux: dict,
             aux_status: dict[str, str] | None = None,
             cfg: AX.AxisCfg = AX.AXIS,
             max_readings: int = MAX_READINGS) -> list[ComboReading]:
    ctx = build_context(frames, aux, aux_status=aux_status, cfg=cfg)

    matched: list[ComboReading] = []
    for combo in CR.COMBOS:
        try:
            if combo.detect(ctx):
                matched.append(_build_reading(combo, ctx))
        except Exception:
            continue

    matched.sort(key=lambda r: r.priority, reverse=True)

    # 같은 영역에서 유사한 조합을 여러 개 보여주지 않는다.
    selected: list[ComboReading] = []
    seen_groups: set[str] = set()
    for reading in matched:
        if reading.group in seen_groups:
            continue
        selected.append(reading)
        seen_groups.add(reading.group)
        if len(selected) >= max_readings:
            break
    return selected
