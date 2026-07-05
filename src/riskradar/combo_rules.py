"""RiskRadar v0.4.0 — 조합 카탈로그.

각 조합 = 탐지 조건 + 관찰 서술 + 가능한 설명 + 확인지표 분기 + 남은 불확실성.
해석은 '사실 + 방향 + 지지/약화'까지만. '안전/위험' 단정, 투자행동 지시는 넣지 않는다.
확인지표 분기는 보조지표(Breakeven/IG OAS/Term Premium)와 실질금리 방향을 입력으로 쓴다.

detect(ctx)는 ReadingContext를 받아 bool을 반환한다. (interpretation_engine 참조)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# 방향 상수 (context.direction 반환값과 일치)
UP, DOWN, FLAT, NA = "상승", "하락", "보합", "판정불가"


@dataclass(frozen=True)
class Check:
    """확인지표 하나의 방향별 해석. supports는 어떤 방향이 어떤 설명을 지지/약화하는지 태그."""
    key: str            # context.direction()이 아는 키 (DFII10 / BREAKEVEN / TERMPREM / IGOAS ...)
    label: str
    up: str
    down: str
    flat: str
    na: str = "데이터가 없어 이 확인은 보류합니다."
    supports_up: str = ""     # 상승일 때 지지되는 설명 id (충돌 집계용)
    supports_down: str = ""   # 하락일 때 지지되는 설명 id


@dataclass
class Combo:
    combo_id: str
    label: str
    detect: Callable         # (ctx) -> bool
    observed: str
    explanations: list       # [(id, text)]
    checks: list             # [Check]
    uncertainty: str


# ---- detect 헬퍼 (ctx 인터페이스에 의존) -----------------------------------

def _d(ctx, key):
    return ctx.direction(key)


# ---- 조합 1: 30Y↑ · 2Y↓ (완성형) ------------------------------------------

_C_30UP_2DOWN = Combo(
    combo_id="rates_30up_2down",
    label="장기금리 상승·단기금리 하락 (수익률곡선 스티프닝 방향)",
    detect=lambda ctx: ctx.rate_member("DGS30") == "상승" and ctx.rate_member("DGS2") == "하락",
    observed=("30년물은 상승, 2년물은 하락 방향입니다. "
              "장기금리와 단기금리가 반대로 움직이는 국면입니다."),
    explanations=[
        ("real", "실질 할인율·장기 요구수익률 상승이 장기금리를 밀어올린다는 설명"),
        ("infl", "장기 인플레이션 보상 상승이 장기금리에 반영된다는 설명"),
        ("tp", "장기채 수급·재정 불확실성 등 term premium 상승이라는 설명"),
        ("cut", "2년물 하락이 정책금리 인하 기대·경기둔화 우려를 반영한다는 설명"),
    ],
    checks=[
        Check("DFII10", "10Y 실질금리",
              up="10Y Real 상승 → 실질 할인율·장기 요구수익률 요인 설명을 지지합니다.",
              down="10Y Real 하락 → 실질금리 요인 설명은 약해지고, 명목금리의 다른 구성요인을 확인합니다.",
              flat="10Y Real 뚜렷한 변화 없음 → 실질금리 요인은 중립적입니다.",
              supports_up="real"),
        Check("BREAKEVEN", "10Y Breakeven",
              up="Breakeven 상승 → 인플레이션 보상 요인 설명을 지지합니다.",
              down="Breakeven 하락 → 인플레이션 요인 설명은 약화됩니다.",
              flat="Breakeven 뚜렷한 변화 없음 → 인플레이션 요인은 중립적입니다.",
              supports_up="infl"),
        Check("TERMPREM", "10Y Term Premium",
              up="Term Premium 상승 → 장기채 수급·위험보상(term premium) 설명을 강화합니다.",
              down="Term Premium 하락 → term premium만으로 장기금리 상승을 설명하기는 어렵습니다.",
              flat="Term Premium 뚜렷한 변화 없음 → 장기구간 위험보상 요인은 중립적입니다.",
              supports_up="tp"),
        Check("IGOAS", "IG OAS (신용 확산 확인)",
              up="IG OAS도 확대 → 2년물 하락이 경기둔화·신용여건 우려와 함께 나타나는지 확인 근거가 늘어납니다(cut 설명 보강).",
              down="IG OAS 축소 → 광범위 신용 스트레스로 읽을 근거는 약합니다.",
              flat="IG OAS 뚜렷한 변화 없음 → 신용 쪽 확산 신호는 아직 약합니다.",
              supports_up="cut"),
    ],
    uncertainty=("같은 방향 조합도 원인이 하나가 아닐 수 있습니다. "
                 "확인지표가 여러 설명을 동시에 지지하면 한 가지 원인으로 정리하기 어렵습니다."),
)


# ---- 조합 2: 변동성·신용 동반 (D) -----------------------------------------

_C_VOL_CREDIT = Combo(
    combo_id="vol_credit_together",
    label="변동성·신용 동반 변화",
    detect=lambda ctx: ctx.vc.state == "D",
    observed="VIX와 HY OAS가 함께 기준상 변화 상태입니다.",
    explanations=[
        ("broad", "주식 변동성과 기업 신용 우려가 함께 움직인다는 설명"),
        ("vol_only", "주식시장 변동성이 먼저 커지고 신용이 뒤따르는 초기 국면이라는 설명"),
    ],
    checks=[
        Check("IGOAS", "IG OAS (확산 범위)",
              up="IG OAS도 확대 → HY만이 아니라 투자등급까지 넓어지는 신용 변화 근거가 늘어납니다(broad 지지).",
              down="IG OAS 축소 → 신용 변화가 저신용 구간에 국한될 가능성이 큽니다.",
              flat="IG OAS 뚜렷한 변화 없음 → 아직 투자등급까지 번지는 신호는 약합니다.",
              supports_up="broad"),
    ],
    uncertainty="VIX와 HY OAS의 동반이 얼마나 지속되는지는 이 시점 데이터만으로 단정하기 어렵습니다.",
)


# ---- 조합 3: 신용 단독 변화 (C) -------------------------------------------

_C_CREDIT_ONLY = Combo(
    combo_id="credit_only",
    label="신용 단독 변화",
    detect=lambda ctx: ctx.vc.state == "C",
    observed="HY OAS의 변화가 VIX보다 뚜렷합니다. 주식 변동성 동반은 약합니다.",
    explanations=[
        ("idio", "특정 발행사·업종에 국한된 신용 변화라는 설명"),
        ("broad", "투자등급까지 번지는 신용 변화의 초기라는 설명"),
    ],
    checks=[
        Check("IGOAS", "IG OAS (확산 범위)",
              up="IG OAS도 확대 → 저신용 구간을 넘어 번지는 근거가 늘어납니다(broad 지지).",
              down="IG OAS 축소 → 저신용 구간에 국한된 변화(idio) 쪽을 지지합니다.",
              flat="IG OAS 뚜렷한 변화 없음 → 아직 국지적일 가능성이 큽니다.",
              supports_up="broad", supports_down="idio"),
    ],
    uncertainty="HY 지수 평균은 업종별 스트레스를 가릴 수 있어, 지수만으로 원인 업종을 특정하기 어렵습니다.",
)


# ---- 조합 4: 전반적 금리 상승 ---------------------------------------------

_C_RATES_BROAD_UP = Combo(
    combo_id="rates_broad_up",
    label="전반적 금리 상승",
    detect=lambda ctx: all(ctx.rate_member(k) == "상승" for k in ("DGS30", "DGS2", "DFII10")),
    observed="30년·2년·실질금리가 함께 상승 방향입니다.",
    explanations=[
        ("real", "실질금리 주도의 전반적 할인율 상승이라는 설명"),
        ("infl", "인플레이션 보상 상승이 동반된다는 설명"),
    ],
    checks=[
        Check("BREAKEVEN", "10Y Breakeven",
              up="Breakeven 상승 → 인플레이션 보상 동반(infl) 설명을 지지합니다.",
              down="Breakeven 하락 → 상승이 실질금리 주도(real)라는 설명을 지지합니다.",
              flat="Breakeven 뚜렷한 변화 없음 → 실질·명목 구분이 중립적입니다.",
              supports_up="infl", supports_down="real"),
    ],
    uncertainty="금리 3종이 함께 오를 때 성장 기대·정책·수급 중 무엇이 주도인지는 추가 확인이 필요합니다.",
)


COMBOS: list[Combo] = [
    _C_30UP_2DOWN,
    _C_VOL_CREDIT,
    _C_CREDIT_ONLY,
    _C_RATES_BROAD_UP,
]
