"""RiskRadar v0.4.2 — 조합 카탈로그.

각 조합은 관찰 사실, 가능한 설명, 확인지표별 결과 분기, 남은 불확실성을 가진다.
해석은 지지/약화/충돌까지만 제공하고 투자행동이나 단일 위험 판정을 만들지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

UP, DOWN, FLAT, NA = "상승", "하락", "보합", "판정불가"


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    up: str
    down: str
    flat: str
    na: str = "데이터가 없거나 오래돼 이 확인은 보류합니다."
    supports_up: tuple[str, ...] = ()
    supports_down: tuple[str, ...] = ()
    supports_flat: tuple[str, ...] = ()
    weakens_up: tuple[str, ...] = ()
    weakens_down: tuple[str, ...] = ()
    weakens_flat: tuple[str, ...] = ()


@dataclass(frozen=True)
class Combo:
    combo_id: str
    group: str
    priority: int
    label: str
    detect: Callable
    observed: str
    explanations: list[tuple[str, str]]
    checks: list[Check]
    uncertainty: str


# ---------------------------------------------------------------- rates -----

RATES_30UP_2DOWN = Combo(
    "rates_30up_2down", "rate_curve", 100,
    "30년물 상승 · 2년물 하락",
    lambda ctx: ctx.core_direction("DGS30") == UP and ctx.core_direction("DGS2") == DOWN,
    "30년물은 상승하고 2년물은 하락 방향입니다. 단기와 장기 구간을 움직이는 힘이 엇갈립니다.",
    [
        ("real", "실질 할인율·장기 요구수익률 상승이 장기금리를 밀어올린다는 설명"),
        ("infl", "장기 인플레이션 보상 상승이 장기금리에 반영된다는 설명"),
        ("tp", "장기채 수급·재정 불확실성 등 Term Premium 상승이라는 설명"),
        ("cut", "2년물 하락이 정책완화 기대·경기둔화 우려를 반영한다는 설명"),
    ],
    [
        Check("DFII10", "10년 실질금리",
              "실질금리도 상승합니다. 실질 할인율·장기 요구수익률 설명을 더 지지합니다.",
              "실질금리는 하락합니다. 실질금리 상승만으로 장기금리 상승을 설명하기 어렵습니다.",
              "실질금리에 뚜렷한 변화가 없습니다. 이 지표로는 원인 구분이 어렵습니다.",
              supports_up=("real",), weakens_down=("real",)),
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션도 상승합니다. 인플레이션 보상 요인 설명을 더 지지합니다.",
              "기대인플레이션은 하락합니다. 인플레이션 설명은 약해집니다.",
              "기대인플레이션에 뚜렷한 변화가 없습니다. 장기금리 상승을 인플레이션 하나로 설명할 근거는 약합니다.",
              supports_up=("infl",), weakens_down=("infl",), weakens_flat=("infl",)),
        Check("TERMPREM", "10년 Term Premium",
              "Term Premium도 상승합니다. 장기채 수급·재정 불확실성·장기구간 위험보상 설명을 더 지지합니다.",
              "Term Premium은 하락합니다. 장기채 위험보상 확대만으로 설명하기 어렵습니다.",
              "Term Premium에 뚜렷한 변화가 없습니다. 이 요인은 현재 설명을 강하게 지지하지 않습니다.",
              supports_up=("tp",), weakens_down=("tp",)),
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 2년물 하락을 경기둔화·금융여건 우려와 함께 읽을 근거가 늘어납니다.",
              "투자등급 신용스프레드는 축소됩니다. 광범위한 신용 스트레스 설명은 약해집니다.",
              "투자등급 신용스프레드에 뚜렷한 변화가 없습니다. 광범위한 신용 변화 근거는 약합니다.",
              supports_up=("cut",), weakens_down=("cut",), weakens_flat=("cut",)),
    ],
    "같은 금리 조합도 원인이 하나가 아닐 수 있습니다. 여러 확인지표가 다른 설명을 동시에 지지하면 복수 요인으로 남깁니다.",
)

RATES_30DOWN_2UP = Combo(
    "rates_30down_2up", "rate_curve", 95,
    "30년물 하락 · 2년물 상승",
    lambda ctx: ctx.core_direction("DGS30") == DOWN and ctx.core_direction("DGS2") == UP,
    "30년물은 하락하고 2년물은 상승 방향입니다. 가까운 정책금리 기대와 장기금리가 반대로 움직입니다.",
    [
        ("tight", "가까운 시기 높은 정책금리 기대가 2년물을 끌어올린다는 설명"),
        ("growth", "장기 성장 기대 둔화 또는 장기채 수요가 30년물을 낮춘다는 설명"),
        ("infl", "장기 인플레이션 보상 둔화가 장기금리를 낮춘다는 설명"),
    ],
    [
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션은 상승합니다. 장기금리 하락을 물가보상 둔화로 설명하기 어렵습니다.",
              "기대인플레이션도 하락합니다. 장기 물가보상 둔화 설명을 더 지지합니다.",
              "기대인플레이션에 뚜렷한 변화가 없습니다. 물가 요인은 중립적입니다.",
              supports_down=("infl",), weakens_up=("infl",)),
        Check("DFII10", "10년 실질금리",
              "실질금리는 상승합니다. 장기금리 하락과 방향이 엇갈려 하나의 설명으로 정리하기 어렵습니다.",
              "실질금리도 하락합니다. 장기 성장·실질금리 하락 설명을 더 확인할 근거가 생깁니다.",
              "실질금리에 뚜렷한 변화가 없습니다. 장기금리 하락 원인 구분이 어렵습니다.",
              supports_down=("growth",)),
    ],
    "장기채 안전자산 수요와 장기 성장 기대 둔화는 비슷한 가격 움직임을 만들 수 있어 현재 데이터만으로 분리하기 어렵습니다.",
)

RATES_BROAD_UP = Combo(
    "rates_broad_up", "rate_level", 80,
    "30년물·2년물·실질금리 동반 상승",
    lambda ctx: all(ctx.core_direction(k) == UP for k in ("DGS30", "DGS2", "DFII10")),
    "30년물·2년물·10년 실질금리가 함께 상승 방향입니다.",
    [
        ("real", "실질금리 주도의 전반적 할인율 상승이라는 설명"),
        ("infl", "인플레이션 보상 상승도 함께 작용한다는 설명"),
        ("policy", "가까운 정책금리 경로가 더 높아졌다는 설명"),
    ],
    [
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션도 상승합니다. 인플레이션 보상 동반 설명을 더 지지합니다.",
              "기대인플레이션은 하락합니다. 실질금리 주도 설명을 더 지지합니다.",
              "기대인플레이션은 보합입니다. 인플레이션 보상 설명은 강하지 않습니다.",
              supports_up=("infl",), supports_down=("real",), weakens_down=("infl",), weakens_flat=("infl",)),
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 금리 상승과 신용시장 변화가 같은 시기에 나타납니다.",
              "투자등급 신용스프레드는 축소됩니다. 광범위한 신용 스트레스 설명은 약합니다.",
              "투자등급 신용스프레드는 기본입니다. 현재는 신용 변화보다 금리 재평가 쪽을 더 확인합니다."),
    ],
    "성장 기대·정책경로·수급 중 무엇이 주도인지는 추가 정보 없이는 하나로 정하기 어렵습니다.",
)

RATES_BROAD_DOWN = Combo(
    "rates_broad_down", "rate_level", 78,
    "30년물·2년물 동반 하락",
    lambda ctx: ctx.core_direction("DGS30") == DOWN and ctx.core_direction("DGS2") == DOWN,
    "30년물과 2년물이 함께 하락 방향입니다.",
    [
        ("easing", "물가 둔화와 정책완화 기대가 금리를 낮춘다는 설명"),
        ("slow", "경기둔화·위험회피가 금리를 낮춘다는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드가 확대됩니다. 경기둔화·금융여건 우려 설명을 더 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 광범위한 신용 스트레스 설명은 약해집니다.",
              "투자등급 신용스프레드는 기본입니다. 정책완화·물가둔화 설명과 상대적으로 더 잘 맞을 수 있습니다.",
              supports_up=("slow",), supports_flat=("easing",), weakens_down=("slow",)),
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션은 상승합니다. 단순한 물가둔화 설명은 약합니다.",
              "기대인플레이션도 하락합니다. 물가둔화·완화 기대 설명을 더 지지합니다.",
              "기대인플레이션은 보합입니다. 물가 요인만으로 설명하기 어렵습니다.",
              supports_down=("easing",), weakens_up=("easing",)),
    ],
    "같은 금리 하락이라도 정책완화 기대와 경기둔화·위험회피는 의미가 다릅니다.",
)

NOMINAL_REAL_UP = Combo(
    "nominal_real_up", "rate_composition", 72,
    "장기 명목금리·실질금리 동반 상승",
    lambda ctx: ctx.core_direction("DGS30") == UP and ctx.core_direction("DFII10") == UP,
    "30년물과 10년 실질금리가 함께 상승 방향입니다.",
    [
        ("real", "실질금리·할인율 상승이 명목 장기금리 상승의 중요한 부분이라는 설명"),
        ("multi", "실질금리와 다른 요인이 함께 작용한다는 설명"),
    ],
    [
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션도 상승합니다. 실질금리와 인플레이션 보상이 함께 작용하는 복합 설명을 지지합니다.",
              "기대인플레이션은 하락합니다. 실질금리 주도 설명을 더 지지합니다.",
              "기대인플레이션은 보합입니다. 실질금리 요인이 상대적으로 더 두드러집니다.",
              supports_up=("multi",), supports_down=("real",), supports_flat=("real",)),
        Check("TERMPREM", "10년 Term Premium",
              "Term Premium도 상승합니다. 장기구간 위험보상 요인도 함께 작용할 가능성을 확인합니다.",
              "Term Premium은 하락합니다. 장기채 위험보상 확대 설명은 약합니다.",
              "Term Premium은 보합입니다. 이 요인은 중립적입니다.",
              supports_up=("multi",)),
    ],
    "실질금리 상승 자체도 성장 기대·정책 기대·수급의 영향을 받을 수 있어 한 원인으로 단정하지 않습니다.",
)

NOMINAL_UP_REAL_NOT = Combo(
    "nominal_up_real_not", "rate_composition", 70,
    "30년물 상승 · 실질금리 비동행",
    lambda ctx: ctx.core_direction("DGS30") == UP and ctx.core_direction("DFII10") in (DOWN, FLAT),
    "30년물은 상승하지만 10년 실질금리는 같은 방향으로 뚜렷하게 움직이지 않습니다.",
    [
        ("infl", "인플레이션 보상 상승이 명목금리를 밀어올린다는 설명"),
        ("tp", "Term Premium 등 장기구간 고유 요인이 명목금리를 밀어올린다는 설명"),
    ],
    [
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션이 상승합니다. 인플레이션 보상 설명을 더 지지합니다.",
              "기대인플레이션은 하락합니다. 인플레이션 설명은 약합니다.",
              "기대인플레이션은 보합입니다. 인플레이션 설명을 강하게 지지하지 않습니다.",
              supports_up=("infl",), weakens_down=("infl",), weakens_flat=("infl",)),
        Check("TERMPREM", "10년 Term Premium",
              "Term Premium이 상승합니다. 장기구간 고유 요인 설명을 더 지지합니다.",
              "Term Premium은 하락합니다. 장기채 위험보상 확대 설명은 약합니다.",
              "Term Premium은 보합입니다. 현재 보조지표만으로 원인 구분이 어렵습니다.",
              supports_up=("tp",), weakens_down=("tp",)),
    ],
    "기대인플레이션과 Term Premium이 함께 움직이더라도 각각의 기여도를 현재 지표만으로 정확히 분리하기 어렵습니다.",
)

TWO_DOWN_CREDIT_WIDENING = Combo(
    "two_down_credit_widening", "policy_credit", 88,
    "2년물 하락 · 신용스프레드 확대",
    lambda ctx: ctx.core_direction("DGS2") == DOWN and ctx.credit_widening(),
    "2년물은 하락하고 기업 신용스프레드는 확대 방향입니다.",
    [
        ("slow", "정책완화 기대가 경기둔화·금융여건 우려와 함께 나타난다는 설명"),
        ("mixed", "정책 기대와 신용시장 움직임이 서로 다른 원인에서 나온다는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 신용 변화의 범위가 넓다는 설명을 더 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 광범위한 신용 변화 설명은 약합니다.",
              "투자등급 신용스프레드는 보합입니다. 하이일드 중심 변화일 가능성을 확인합니다.",
              supports_up=("slow",), weakens_down=("slow",)),
    ],
    "2년물 하락만으로 인하의 원인을 알 수 없고, 신용스프레드 확대만으로 침체를 확정할 수 없습니다.",
)

TWO_DOWN_CREDIT_QUIET = Combo(
    "two_down_credit_quiet", "policy_credit", 74,
    "2년물 하락 · 신용스프레드 기본",
    lambda ctx: ctx.core_direction("DGS2") == DOWN and not ctx.credit_widening(),
    "2년물은 하락하지만 HY OAS와 투자등급 신용스프레드의 광범위한 확대는 뚜렷하지 않습니다.",
    [
        ("easing", "물가 둔화·정책 정상화 기대가 2년물을 낮춘다는 설명"),
        ("early", "경기둔화 우려가 아직 신용시장에 뚜렷하게 나타나지 않았다는 설명"),
    ],
    [
        Check("BREAKEVEN", "10년 기대인플레이션",
              "기대인플레이션은 상승합니다. 단순한 물가둔화 설명은 약합니다.",
              "기대인플레이션도 하락합니다. 물가둔화·완화 기대 설명을 더 지지합니다.",
              "기대인플레이션은 보합입니다. 이 지표만으로 원인 구분이 어렵습니다.",
              supports_down=("easing",), weakens_up=("easing",)),
    ],
    "신용스프레드가 기본이라고 경기둔화 가능성이 없다는 뜻은 아닙니다. 현재 가격에 같은 변화가 뚜렷하지 않다는 뜻입니다.",
)

# --------------------------------------------------------- volatility/credit

VOL_LEADS = Combo(
    "vol_leads", "vol_credit", 86,
    "변동성 선행",
    lambda ctx: ctx.vc.state == "B",
    "VIX 변화가 먼저 나타나고 HY OAS는 기본 상태입니다.",
    [
        ("event", "이벤트성·주식시장 중심 변동성이라는 설명"),
        ("early", "신용시장 변화보다 변동성이 먼저 나타나는 초기 국면이라는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 주식 변동성만의 변화라는 설명은 약해집니다.",
              "투자등급 신용스프레드는 축소됩니다. 주식시장 중심 변화 설명과 더 잘 맞습니다.",
              "투자등급 신용스프레드는 보합입니다. 광범위한 신용 변화 근거는 아직 약합니다.",
              supports_down=("event",), supports_flat=("event",), supports_up=("early",), weakens_up=("event",)),
    ],
    "VIX는 빠르게 움직이므로 이후 며칠간 신용스프레드가 같은 방향으로 움직이는지 확인해야 합니다.",
)

CREDIT_ONLY = Combo(
    "credit_only", "vol_credit", 90,
    "신용 단독 변화",
    lambda ctx: ctx.vc.state == "C",
    "HY OAS의 변화가 VIX보다 더 뚜렷합니다.",
    [
        ("idio", "저신용 기업·특정 업종에 더 국한된 신용 변화라는 설명"),
        ("broad", "투자등급까지 넓어지는 신용 변화의 초기라는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 변화가 더 넓은 신용시장으로 이어지는 설명을 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 저신용 구간에 국한된 설명을 더 지지합니다.",
              "투자등급 신용스프레드는 보합입니다. 아직 하이일드 중심 변화일 가능성을 확인합니다.",
              supports_up=("broad",), supports_down=("idio",), supports_flat=("idio",)),
    ],
    "HY 지수 평균은 업종별 스트레스를 가릴 수 있어 지수만으로 원인 업종을 특정하기 어렵습니다.",
)

VOL_CREDIT_TOGETHER = Combo(
    "vol_credit_together", "vol_credit", 100,
    "변동성·신용 동반 변화",
    lambda ctx: ctx.vc.state == "D",
    "VIX와 HY OAS가 함께 기준상 변화 상태입니다.",
    [
        ("broad", "주식 변동성과 기업 신용 변화가 같은 시기에 나타난다는 설명"),
        ("hy", "신용 변화가 아직 하이일드 중심이라는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 신용 변화의 범위가 넓어진다는 설명을 더 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 신용 변화가 하이일드 중심이라는 설명과 더 잘 맞습니다.",
              "투자등급 신용스프레드는 보합입니다. 투자등급까지 넓어지는 근거는 아직 약합니다.",
              supports_up=("broad",), supports_down=("hy",), supports_flat=("hy",)),
    ],
    "동반 변화의 원인과 지속성은 현재 가격만으로 특정할 수 없습니다.",
)

VOL_CALM_CREDIT_PERSIST = Combo(
    "vol_calm_credit_persist", "vol_credit", 96,
    "변동성 진정 · 신용 변화 지속",
    lambda ctx: ctx.vc.state == "E",
    "최근 VIX 변화는 완화됐지만 HY OAS는 아직 변화 상태입니다.",
    [
        ("persist", "주식 변동성보다 신용시장 변화가 더 오래 남는다는 설명"),
        ("hy", "변화가 하이일드 중심으로 지속된다는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 신용 변화가 더 넓게 지속된다는 설명을 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 하이일드 중심 지속 설명과 더 잘 맞습니다.",
              "투자등급 신용스프레드는 보합입니다. 투자등급 확산은 뚜렷하지 않습니다.",
              supports_up=("persist",), supports_down=("hy",), supports_flat=("hy",)),
    ],
    "VIX가 진정됐다는 사실만으로 신용시장 변화가 끝났다고 볼 수 없습니다.",
)

# --------------------------------------------------------------- cycle -----

CYCLE_RENORM_CREDIT_WIDE = Combo(
    "cycle_renorm_credit_wide", "cycle", 89,
    "재정상화 경로 · 신용스프레드 확대",
    lambda ctx: ctx.cycle.state in {"re_normalizing", "re_normalized"} and ctx.credit_widening(),
    "10년-3개월 금리차는 재정상화 경로이고 기업 신용스프레드는 확대 방향입니다.",
    [
        ("joint", "수익률곡선의 경로 변화와 신용시장 변화가 같은 시기에 나타난다는 설명"),
        ("separate", "두 변화가 서로 다른 원인에서 나왔다는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 신용 변화의 범위가 넓다는 설명을 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 광범위한 신용 변화 설명은 약합니다.",
              "투자등급 신용스프레드는 보합입니다. 하이일드 중심 변화일 수 있습니다.",
              supports_up=("joint",), supports_down=("separate",)),
    ],
    "수익률곡선은 선행 정보이고 신용스프레드는 현재 가격 변화라 시점과 인과를 하나로 묶을 수 없습니다.",
)

CYCLE_RENORM_CREDIT_QUIET = Combo(
    "cycle_renorm_credit_quiet", "cycle", 76,
    "재정상화 경로 · 신용스프레드 기본",
    lambda ctx: ctx.cycle.state in {"re_normalizing", "re_normalized"} and not ctx.credit_widening(),
    "10년-3개월 금리차는 재정상화 경로이지만 기업 신용스프레드의 광범위한 확대는 뚜렷하지 않습니다.",
    [
        ("cycle", "경기 사이클 경로 변화와 현재 신용시장 가격을 분리해서 봐야 한다는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드가 확대됩니다. 신용시장 변화도 함께 나타나는지 다시 확인합니다.",
              "투자등급 신용스프레드는 축소됩니다. 현재 신용시장 변화가 넓다는 설명은 약합니다.",
              "투자등급 신용스프레드는 보합입니다. 수익률곡선 경로와 현재 신용가격은 서로 다른 신호입니다.",
              supports_flat=("cycle",), supports_down=("cycle",)),
    ],
    "재정상화 자체는 호재·악재 단일 신호가 아니며 정확한 경기 시점을 알려주지 않습니다.",
)

LONG_INV_2Y_DOWN = Combo(
    "long_inv_2y_down", "cycle", 75,
    "장기 역전 · 2년물 하락",
    lambda ctx: ctx.cycle.state == "long_inverted" and ctx.core_direction("DGS2") == DOWN,
    "수익률곡선은 장기 역전 상태이고 2년물은 하락 방향입니다.",
    [
        ("easing", "가까운 정책완화 기대가 강화된다는 설명"),
        ("slow", "경기둔화 우려가 2년물 하락에 반영된다는 설명"),
    ],
    [
        Check("IGOAS", "투자등급 신용스프레드",
              "투자등급 신용스프레드도 확대됩니다. 경기둔화·금융여건 우려 설명을 더 지지합니다.",
              "투자등급 신용스프레드는 축소됩니다. 광범위한 신용 스트레스 설명은 약합니다.",
              "투자등급 신용스프레드는 보합입니다. 현재 신용가격만으로 두 설명을 구분하기 어렵습니다.",
              supports_up=("slow",), weakens_down=("slow",)),
    ],
    "수익률곡선과 2년물만으로 정책완화의 이유를 확정할 수 없습니다.",
)


COMBOS: list[Combo] = [
    RATES_30UP_2DOWN,
    VOL_CREDIT_TOGETHER,
    VOL_CALM_CREDIT_PERSIST,
    CREDIT_ONLY,
    CYCLE_RENORM_CREDIT_WIDE,
    TWO_DOWN_CREDIT_WIDENING,
    VOL_LEADS,
    RATES_30DOWN_2UP,
    RATES_BROAD_UP,
    RATES_BROAD_DOWN,
    CYCLE_RENORM_CREDIT_QUIET,
    LONG_INV_2Y_DOWN,
    TWO_DOWN_CREDIT_QUIET,
    NOMINAL_REAL_UP,
    NOMINAL_UP_REAL_NOT,
]
