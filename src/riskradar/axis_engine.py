"""RiskRadar v0.4.0 — 3축 복합 조망 엔진.

원칙:
- 6개를 그대로 더하지 않는다. 금리 신호를 여러 번 세는 문제를 피해 3축으로 정리한다.
- 변동성·신용 축은 VIX(빠른 센서)와 HY OAS(확인 센서)를 '동등 투표'하지 않는다.
- 금리 방향 축은 다수결하지 않는다. 방향의 엇갈림(혼합) 자체를 정보로 남긴다.
- 최상단은 단일 위험점수/행동유도 라벨을 만들지 않는다. '몇 축이 변했는가'만 센다.

모든 컷은 C등급 운영 규칙이다. 기존 단일 지표 상태를 재사용하고 새 임계값을 최소화한다.
입력은 pipeline.compute_frames()의 frames(각 지표 시계열 + state_code).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .state_rules import LABELS

# 활성/방향 기준 상태 (기존 state_code 재사용)
VIX_ACTIVE_STATES = {"watch", "stress"}
VIX_STRONG = "stress"
HY_ACTIVE_STATES = {"watch", "stress"}   # calm/neutral = 기본
RATE_UP_STATES = {"rise_watch", "rate_shock"}
CYCLE_BASE = "normal"

DIR_UP, DIR_DOWN, DIR_BASE = "상승", "하락", "기본"


@dataclass(frozen=True)
class AxisCfg:
    """3축 판정 C등급 운영 규칙."""
    vix_persist_window: int = 5   # 최근 N개 관측
    vix_persist_min: int = 3      # 그 중 M개가 기본을 벗어나면 지속 후보
    vix_change_abs_pct: float = 40.0  # 약 1개월 변화가 자기 과거 변화폭의 이 위치 이상
    vix_change_min_obs: int = 250
    e_link_window: int = 10       # '변동성 진정·신용 지속' 판정용 연결 창


AXIS = AxisCfg()

DISCLAIMER = ("축 요약은 기존 단일 지표 상태를 묶어 보기 위한 RiskRadar 내부 참고 규칙(C등급)입니다. "
              "학술 모델·위험 확률·투자 신호가 아닙니다.")


# ---- 변동성·신용 축 --------------------------------------------------------

@dataclass
class VolCreditAxis:
    state: str          # A~E
    label: str
    changed: bool
    vix_active: bool
    vix_reason: str     # immediate | persistent+history | persistent_but_small_change | base
    vix_change_pct: float | None
    hy_active: bool
    vix_state: str
    hy_state: str
    note: str

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("state", "label", "changed", "vix_active", "vix_reason",
                 "vix_change_pct", "hy_active", "vix_state", "hy_state", "note")}


def _vix_change_is_meaningful(frame: pd.DataFrame, cfg: AxisCfg) -> tuple[bool, float | None]:
    if "change_20obs" not in frame:
        return True, None  # 짧은 합성 테스트·구버전 프레임은 기존 규칙 fallback
    changes = pd.to_numeric(frame["change_20obs"], errors="coerce")
    valid = changes.dropna()
    latest = changes.iloc[-1] if len(changes) else float("nan")
    if pd.isna(latest) or len(valid) < cfg.vix_change_min_obs:
        return True, None
    pct = float((valid.abs() <= abs(float(latest))).mean() * 100.0)
    return pct >= cfg.vix_change_abs_pct, round(pct, 1)


def _vix_active(frame: pd.DataFrame, cfg: AxisCfg) -> tuple[bool, str, float | None]:
    codes = frame["state_code"].tolist()
    if not codes:
        return False, "base", None
    meaningful, pct = _vix_change_is_meaningful(frame, cfg)
    if codes[-1] == VIX_STRONG:
        return True, "immediate", pct
    window = codes[-cfg.vix_persist_window:]
    off_base = sum(1 for c in window if c in VIX_ACTIVE_STATES)
    if off_base >= cfg.vix_persist_min and meaningful:
        return True, "persistent+history", pct
    if off_base >= cfg.vix_persist_min:
        return False, "persistent_but_small_change", pct
    return False, "base", pct


def _hy_active(frame: pd.DataFrame) -> bool:
    codes = frame["state_code"].tolist()
    return bool(codes) and codes[-1] in HY_ACTIVE_STATES


def vol_credit_axis(frames: dict[str, pd.DataFrame], cfg: AxisCfg = AXIS) -> VolCreditAxis:
    vf, hf = frames.get("VIX"), frames.get("HYOAS")
    vix_active, vreason, vchange_pct = (_vix_active(vf, cfg) if vf is not None
                                         else (False, "base", None))
    hy_active = _hy_active(hf) if hf is not None else False
    vix_state = vf["state_code"].iloc[-1] if vf is not None and len(vf) else "calm"
    hy_state = hf["state_code"].iloc[-1] if hf is not None and len(hf) else "calm"

    if vix_active and hy_active:
        state, label = "D", "주식시장과 회사채가 함께 움직임"
        note = "주식시장 예상 변동성과 저신용 기업 회사채 추가 금리가 모두 평소와 다른 움직임을 보입니다."
    elif vix_active:
        state, label = "B", "주식시장 쪽만 움직임"
        note = "주식시장 예상 변동성은 커졌지만 저신용 기업 회사채 추가 금리는 아직 평소 범위입니다. 실제 선후행을 뜻하지 않습니다."
    elif hy_active:
        recent = vf["state_code"].iloc[-cfg.e_link_window:].tolist() if vf is not None else []
        had_vix = any(c in VIX_ACTIVE_STATES for c in recent)
        if had_vix:
            state, label = "E", "주식시장은 진정 · 회사채 변화는 이어짐"
            note = "최근 주식시장 변동성은 줄었지만 저신용 기업 회사채 추가 금리는 아직 평소와 다른 움직임을 보입니다."
        else:
            state, label = "C", "회사채 쪽만 움직임"
            note = "저신용 기업 회사채 추가 금리의 움직임이 주식시장 예상 변동성보다 더 뚜렷합니다."
    else:
        state, label = "A", "큰 움직임 없음"
        note = "주식시장 예상 변동성과 저신용 기업 회사채 추가 금리 모두 큰 움직임이 없습니다."

    return VolCreditAxis(state, label, state != "A", vix_active, vreason,
                         vchange_pct, hy_active, vix_state, hy_state, note)


# ---- 경기 사이클 축 --------------------------------------------------------

@dataclass
class CycleAxis:
    state: str
    label: str
    changed: bool

    def to_dict(self) -> dict:
        return {"state": self.state, "label": self.label, "changed": self.changed}


def cycle_axis(frames: dict[str, pd.DataFrame]) -> CycleAxis:
    tf = frames.get("T10Y3M")
    code = tf["state_code"].iloc[-1] if tf is not None and len(tf) else CYCLE_BASE
    return CycleAxis(code, LABELS.get(code, code), code != CYCLE_BASE)


# ---- 금리 방향 축 ----------------------------------------------------------

@dataclass
class RateAxis:
    result: str                 # 변화 없음 / 상승 방향 / 하락 방향 / 혼합 방향
    changed: bool
    members: dict               # key -> 상승/하락/기본
    member_states: dict

    def to_dict(self) -> dict:
        return {"result": self.result, "changed": self.changed,
                "members": self.members, "member_states": self.member_states}


def _rate_dir(frame: pd.DataFrame) -> str:
    if frame is None or not len(frame):
        return DIR_BASE
    r = frame.iloc[-1]
    if bool(r.get("drop_flag", False)):
        return DIR_DOWN
    if r["state_code"] in RATE_UP_STATES:
        return DIR_UP
    return DIR_BASE


def rate_axis(frames: dict[str, pd.DataFrame]) -> RateAxis:
    members, states = {}, {}
    for key in ("DGS30", "DGS2", "DFII10"):
        f = frames.get(key)
        members[key] = _rate_dir(f)
        states[key] = f["state_code"].iloc[-1] if f is not None and len(f) else "stable"
    dirs = set(members.values())
    up, down = DIR_UP in dirs, DIR_DOWN in dirs
    if up and down:
        result = "혼합 방향"
    elif up:
        result = "상승 방향"
    elif down:
        result = "하락 방향"
    else:
        result = "변화 없음"
    return RateAxis(result, result != "변화 없음", members, states)


# ---- 최상단 복합 조망 ------------------------------------------------------

@dataclass
class CompositeView:
    changed_count: int
    changed_axes: list
    base_axes: list
    vol_credit: VolCreditAxis
    cycle: CycleAxis
    rate: RateAxis
    disclaimer: str = field(default=DISCLAIMER)

    def summary_line(self) -> str:
        return f"현재 3개 영역 중 {self.changed_count}개에서 눈에 띄는 움직임"

    def to_dict(self) -> dict:
        return {
            "changed_count": self.changed_count,
            "changed_axes": self.changed_axes,
            "base_axes": self.base_axes,
            "summary_line": self.summary_line(),
            "vol_credit": self.vol_credit.to_dict(),
            "cycle": self.cycle.to_dict(),
            "rate": self.rate.to_dict(),
            "disclaimer": self.disclaimer,
        }


def composite_view(frames: dict[str, pd.DataFrame], cfg: AxisCfg = AXIS) -> CompositeView:
    vc = vol_credit_axis(frames, cfg)
    cy = cycle_axis(frames)
    rt = rate_axis(frames)
    axes = [("변동성·신용", vc.changed), ("경기 사이클", cy.changed), ("금리 방향", rt.changed)]
    changed = [n for n, c in axes if c]
    base = [n for n, c in axes if not c]
    return CompositeView(len(changed), changed, base, vc, cy, rt)
