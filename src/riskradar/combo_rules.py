"""RiskRadar v0.4.2 — 조합 카탈로그.

각 조합은 관찰 사실, 가능한 설명, 함께 볼 지표별 결과 분기, 남은 불확실성을 가진다.
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
    "30Y는 오르고 2Y는 내렸습니다. 장기금리와 가까운 기준금리 예상이 반대로 움직입니다.",
    [
        ("real", "실질 10Y도 올라 장기금리 상승 쪽 움직임이 함께 나타나는 경우"),
        ("infl", "10년 일반·물가연동 국채금리 차이도 커져 명목 장기금리를 끌어올리는 요인이 함께 움직이는 경우"),
        ("tp", "Term Premium도 올라 장기금리를 끌어올리는 요인이 함께 움직이는 경우"),
        ("cut", "2Y 하락에 정책완화 기대나 경기둔화 우려가 반영된 경우"),
    ],
    [
        Check("DFII10", "10년 실질금리",
              "물가 영향을 뺀 10년 금리도 상승합니다. 30년 금리와 같은 방향의 참고 신호입니다.",
              "물가 영향을 뺀 10년 금리는 하락합니다. 30년 금리와 방향이 엇갈립니다.",
              "물가 영향을 뺀 10년 금리에 뚜렷한 변화가 없습니다. 30년 금리 변화를 나눈 항목으로 보지 않습니다.",
              supports_up=("real",), weakens_down=("real",)),
        Check("BREAKEVEN", "10년 일반·물가연동 국채금리 차이",
              "10년 일반·물가연동 국채금리 차이도 상승합니다. 30년 금리와 같은 방향의 참고 신호입니다.",
              "10년 일반·물가연동 국채금리 차이는 하락합니다. 30년 금리와 방향이 엇갈립니다.",
              "10년 일반·물가연동 국채금리 차이에 뚜렷한 변화가 없습니다. 30년 금리 변화는 금리 탭의 ‘30년 금리’에서 먼저 봅니다.",
              supports_up=("infl",), weakens_down=("infl",), weakens_flat=("infl",)),
        Check("TERMPREM", "10년 장기채 추가 보상",
              "10년 장기채 추가 보상도 상승합니다. 30년 금리 변화를 나눈 항목은 아니지만 같은 방향으로 움직입니다.",
              "10년 장기채 추가 보상은 하락합니다. 30년 금리와 방향이 엇갈립니다.",
              "10년 장기채 추가 보상에 뚜렷한 변화가 없습니다. 30년 금리 변화와 따로 봅니다.",
              supports_up=("tp",), weakens_down=("tp",)),
        Check("AOAS", "A등급 기업의 추가 금리",
              "A등급 기업의 추가 금리도 확대됩니다. 2년물 하락을 경기둔화·금융여건 우려와 함께 읽을 그 설명을 더 살펴볼 필요가 있습니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리에 뚜렷한 변화가 없습니다. 넓은 범위의 신용 변화라고 보기는 어렵습니다.",
              supports_up=("cut",), weakens_down=("cut",), weakens_flat=("cut",)),
    ],
    "10년 지표는 30년 금리 변화를 나눈 항목이 아닙니다. 다른 만기에서 같은 방향인지 참고할 때만 사용합니다.",
)

RATES_30DOWN_2UP = Combo(
    "rates_30down_2up", "rate_curve", 95,
    "30년물 하락 · 2년물 상승",
    lambda ctx: ctx.core_direction("DGS30") == DOWN and ctx.core_direction("DGS2") == UP,
    "30Y는 내리고 2Y는 올랐습니다. 가까운 기준금리 예상과 장기금리가 반대로 움직입니다.",
    [
        ("tight", "가까운 시기의 높은 기준금리 예상이 2Y를 끌어올린 경우"),
        ("growth", "장기 성장 기대 둔화나 장기채 수요 증가가 30Y를 낮춘 경우"),
        ("infl", "10년 일반·물가연동 국채금리 차이도 줄어 장기금리를 낮추는 요인이 함께 움직인 경우"),
    ],
    [
        Check("BREAKEVEN", "10년 일반·물가연동 국채금리 차이",
              "10년 일반·물가연동 국채금리 차이는 상승합니다. 30년 금리와 방향이 엇갈립니다.",
              "10년 일반·물가연동 국채금리 차이도 하락합니다. 30년 금리와 같은 방향의 참고 신호입니다.",
              "10년 일반·물가연동 국채금리 차이에 뚜렷한 변화가 없습니다. 30년 금리 변화는 금리 탭의 ‘30년 금리’에서 먼저 봅니다.",
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
    "30Y·2Y·실질 10Y가 함께 올랐습니다.",
    [
        ("real", "실질금리 상승이 장기금리와 자산 할인율을 함께 끌어올린 경우"),
        ("infl", "10년 일반·물가연동 국채금리 차이도 커져 명목금리를 끌어올리는 요인이 함께 움직인 경우"),
        ("policy", "가까운 기준금리 예상이 높아져 2Y를 끌어올린 경우"),
    ],
    [
        Check("BREAKEVEN", "10년 일반·물가연동 국채금리 차이",
              "10년 일반·물가연동 국채금리 차이도 상승합니다. 금리 전반과 같은 방향의 참고 신호입니다.",
              "10년 일반·물가연동 국채금리 차이는 하락합니다. 금리 전반과 방향이 엇갈립니다.",
              "10년 일반·물가연동 국채금리 차이는 보합입니다. 30년 금리 변화를 나눈 항목으로 해석하지 않습니다.",
              supports_up=("infl",), supports_down=("real",), weakens_down=("infl",), weakens_flat=("infl",)),
        Check("AOAS", "A등급 기업의 추가 금리",
              "A등급 기업의 추가 금리도 확대됩니다. 금리 상승과 신용시장 변화가 같은 시기에 나타납니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 기본입니다. 현재는 신용 변화보다 금리 재평가 쪽을 더 확인합니다."),
    ],
    "성장 기대·정책경로·수급 중 무엇이 주도인지는 추가 정보 없이는 하나로 정하기 어렵습니다.",
)

RATES_BROAD_DOWN = Combo(
    "rates_broad_down", "rate_level", 78,
    "30년물·2년물 동반 하락",
    lambda ctx: ctx.core_direction("DGS30") == DOWN and ctx.core_direction("DGS2") == DOWN,
    "30Y와 2Y가 함께 내렸습니다.",
    [
        ("easing", "물가 둔화와 정책완화 기대가 금리를 낮춘 경우"),
        ("slow", "경기둔화 우려나 위험회피가 금리를 낮춘 경우"),
    ],
    [
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS가 오릅니다. A등급 회사채의 국채 대비 추가 금리와 우량 기업의 추가 조달비용도 커집니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 기본입니다. 정책완화·물가둔화 설명과 상대적으로 더 잘 맞을 수 있습니다.",
              supports_up=("slow",), supports_flat=("easing",), weakens_down=("slow",)),
        Check("BREAKEVEN", "10년 일반·물가연동 국채금리 차이",
              "10년 일반·물가연동 국채금리 차이는 상승합니다. 두 10년 국채의 금리 차이가 줄어드는 모습과는 방향이 엇갈립니다.",
              "10년 일반·물가연동 국채금리 차이도 하락합니다. 10년 구간에서도 두 국채의 금리 차이가 줄어드는 방향입니다.",
              "10년 일반·물가연동 국채금리 차이는 보합입니다. 이 지표만으로 금리 하락 이유를 정하지 않습니다.",
              supports_down=("easing",), weakens_up=("easing",)),
    ],
    "같은 금리 하락이라도 정책완화 기대와 경기둔화·위험회피는 의미가 다릅니다.",
)

TWO_DOWN_CREDIT_WIDENING = Combo(
    "two_down_credit_widening", "policy_credit", 88,
    "2년물 하락 · 신용스프레드 확대",
    lambda ctx: ctx.core_direction("DGS2") == DOWN and ctx.credit_widening(),
    "2Y는 내리고 기업 신용스프레드는 올랐습니다.",
    [
        ("slow", "정책완화 기대와 기업 신용 약세가 같은 시기에 나타난 경우"),
        ("mixed", "2Y 하락과 신용스프레드 상승이 서로 다른 원인에서 나온 경우"),
    ],
    [
        Check("BBBOAS", "투자등급 경계 기업의 추가 금리",
              "BBB OAS도 오릅니다. BBB 회사채의 국채 대비 추가 금리와 BBB 기업의 추가 조달비용도 커집니다.",
              "투자등급 경계 기업의 추가 금리는 줄어듭니다. 금리 상승이 더 넓은 등급에서 나타난다는 설명은 약해집니다.",
              "투자등급 경계 기업에는 뚜렷한 변화가 없습니다. 현재는 저신용 기업 중심 변화일 수 있습니다.",
              supports_up=("slow",), weakens_down=("slow",)),
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS도 오릅니다. A등급 회사채의 국채 대비 추가 금리와 우량 기업의 추가 조달비용까지 커집니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 보합입니다. 하이일드 중심 변화일 가능성을 확인합니다.",
              supports_up=("slow",), weakens_down=("slow",)),
        Check("CPSPREAD", "기업 신용도에 따른 단기자금 금리 차이",
              "CP Spread도 커집니다. 신용도가 낮은 기업의 단기 조달금리가 우량 기업보다 더 높아집니다.",
              "단기자금 금리 차이는 줄어듭니다. 단기 자금시장까지 부담이 이어졌다는 설명은 약해집니다.",
              "단기자금 금리 차이에 뚜렷한 변화가 없습니다. 단기 자금시장까지 같은 변화가 이어졌다는 근거는 아직 약합니다.",
              supports_up=("slow",), weakens_down=("slow",), weakens_flat=("slow",)),
    ],
    "2년물 하락만으로 인하의 원인을 알 수 없고, 신용스프레드 확대만으로 침체를 확정할 수 없습니다.",
)

TWO_DOWN_CREDIT_QUIET = Combo(
    "two_down_credit_quiet", "policy_credit", 74,
    "2년물 하락 · 신용스프레드 기본",
    lambda ctx: ctx.core_direction("DGS2") == DOWN and not ctx.credit_widening(),
    "2Y는 내렸지만 HY와 A등급 회사채에서 함께 오르는 움직임은 뚜렷하지 않습니다.",
    [
        ("easing", "물가 둔화나 정책완화 기대가 2Y를 낮춘 경우"),
        ("early", "경기둔화 우려가 있어도 아직 회사채 금리에는 뚜렷하게 나타나지 않은 경우"),
    ],
    [
        Check("BREAKEVEN", "10년 일반·물가연동 국채금리 차이",
              "10년 일반·물가연동 국채금리 차이는 상승합니다. 두 10년 국채의 금리 차이가 줄어드는 모습과는 방향이 엇갈립니다.",
              "10년 일반·물가연동 국채금리 차이도 하락합니다. 10년 구간에서도 두 국채의 금리 차이가 줄어드는 방향입니다.",
              "10년 일반·물가연동 국채금리 차이는 보합입니다. 이 지표만으로 2년물 하락 이유를 정하지 않습니다.",
              supports_down=("easing",), weakens_up=("easing",)),
    ],
    "신용스프레드가 기본이라고 경기둔화 가능성이 없다는 뜻은 아닙니다. 현재 가격에 같은 변화가 뚜렷하지 않다는 뜻입니다.",
)

# --------------------------------------------------------- volatility/credit

VOL_LEADS = Combo(
    "vol_leads", "vol_credit", 86,
    "주식시장 쪽만 움직임",
    lambda ctx: ctx.vc.state == "B",
    "VIX 변화는 두드러지지만 HY OAS는 높은 수준이 아닙니다.",
    [
        ("event", "변화가 주식시장 변동성에 집중된 경우"),
        ("early", "주식시장 변동성이 먼저 커졌고 회사채 금리에는 아직 뚜렷한 변화가 없는 경우"),
    ],
    [
        Check("AOAS", "A등급 기업의 추가 금리",
              "A등급 기업의 추가 금리도 확대됩니다. 주식 변동성만의 변화라는 설명은 약해집니다.",
              "A OAS는 내려갑니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 보합입니다. 광범위한 신용 변화 근거는 아직 약합니다.",
              supports_down=("event",), supports_flat=("event",), supports_up=("early",), weakens_up=("event",)),
        Check("CPSPREAD", "기업 신용도에 따른 단기자금 금리 차이",
              "단기자금 금리 차이도 벌어집니다. 주식시장만의 이벤트보다 자금시장으로 이어지는 초기 설명을 더 확인합니다.",
              "CP Spread는 줄어듭니다. 단기 기업자금시장까지 같은 상승이 나타난 것은 아닙니다.",
              "단기자금 금리 차이에 뚜렷한 변화가 없습니다. 현재로서는 단기 자금시장까지 이어진 근거가 약합니다.",
              supports_up=("early",), supports_down=("event",), supports_flat=("event",), weakens_up=("event",)),
    ],
    "VIX는 빠르게 움직이므로 이후 신용스프레드에도 변화가 나타나는지 별도로 확인해야 합니다. 현재 상태만으로 선행·후행을 판단하지 않습니다.",
)

CREDIT_ONLY = Combo(
    "credit_only", "vol_credit", 90,
    "신용 단독 변화",
    lambda ctx: ctx.vc.state == "C",
    "HY OAS의 변화가 VIX보다 더 뚜렷합니다.",
    [
        ("idio", "변화가 낮은 등급 기업이나 특정 업종에 집중된 경우"),
        ("broad", "BBB·A등급 회사채 금리도 따라 오르기 시작한 경우"),
    ],
    [
        Check("BBBOAS", "투자등급 경계 기업의 추가 금리",
              "BBB OAS도 오릅니다. BBB 기업의 국채 대비 추가 조달비용까지 커집니다.",
              "BBB OAS는 내려갑니다. 현재 신용 약세는 낮은 등급 기업에 더 집중된 상태입니다.",
              "투자등급 경계 기업에는 뚜렷한 변화가 없습니다. 아직 저신용 기업 중심일 가능성이 큽니다.",
              supports_up=("broad",), supports_down=("idio",), supports_flat=("idio",)),
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS도 오릅니다. 우량 기업 회사채의 국채 대비 추가 금리와 추가 조달비용까지 커집니다.",
              "A OAS는 내려갑니다. 현재 신용 약세는 낮은 등급 기업에 더 집중된 상태입니다.",
              "A등급 기업의 추가 금리는 보합입니다. 아직 하이일드 중심 변화일 가능성을 확인합니다.",
              supports_up=("broad",), supports_down=("idio",), supports_flat=("idio",)),
        Check("CPSPREAD", "기업 신용도에 따른 단기자금 금리 차이",
              "CP Spread도 커집니다. 신용도가 낮은 기업의 단기 조달금리가 우량 기업보다 더 높아집니다.",
              "단기자금 금리 차이는 줄어듭니다. 현재 변화가 회사채 쪽에 더 집중된 설명과 맞습니다.",
              "단기자금 금리 차이에 뚜렷한 변화가 없습니다. 단기 자금시장까지 이어졌다고 보기는 어렵습니다.",
              supports_up=("broad",), supports_down=("idio",), supports_flat=("idio",)),
    ],
    "HY 지수 평균은 업종별 스트레스를 가릴 수 있어 지수만으로 원인 업종을 특정하기 어렵습니다.",
)

VOL_CREDIT_TOGETHER = Combo(
    "vol_credit_together", "vol_credit", 100,
    "변동성·신용 동반 변화",
    lambda ctx: ctx.vc.state == "D",
    "VIX와 HY OAS가 함께 경계 기준에 걸렸습니다.",
    [
        ("broad", "주식시장 변동성과 낮은 등급 기업의 회사채 금리가 함께 오른 경우"),
        ("hy", "회사채 금리 상승이 아직 HY에 더 집중된 경우"),
    ],
    [
        Check("BBBOAS", "투자등급 경계 기업의 추가 금리",
              "BBB OAS도 오릅니다. BBB 기업의 국채 대비 추가 조달비용까지 커집니다.",
              "투자등급 경계 기업의 추가 금리는 줄어듭니다. 회사채 금리 상승이 저신용 기업에 더 집중됐을 수 있습니다.",
              "투자등급 경계 기업에는 뚜렷한 변화가 없습니다. 확산 범위가 넓다는 근거는 아직 제한적입니다.",
              supports_up=("broad",), supports_down=("hy",), supports_flat=("hy",)),
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS도 오릅니다. 우량 기업의 국채 대비 추가 조달비용까지 커집니다.",
              "A OAS는 내려갑니다. 현재 신용 약세는 하이일드에 더 집중된 상태입니다.",
              "A등급 기업의 추가 금리는 보합입니다. 투자등급 안쪽까지 넓어지는 근거는 아직 약합니다.",
              supports_up=("broad",), supports_down=("hy",), supports_flat=("hy",)),
        Check("CPSPREAD", "기업 신용도에 따른 단기자금 금리 차이",
              "단기자금 금리 차이도 벌어집니다. 주식과 회사채뿐 아니라 단기 자금시장에서도 부담 차이가 커지는 모습입니다.",
              "단기자금 금리 차이는 줄어듭니다. 단기 자금시장까지 같은 변화가 이어졌다는 설명은 약해집니다.",
              "단기자금 금리 차이에 뚜렷한 변화가 없습니다. 현재 동반 변화가 단기 자금시장까지 이어졌다고 보기는 어렵습니다.",
              supports_up=("broad",), supports_down=("hy",), supports_flat=("hy",)),
    ],
    "동반 변화의 원인과 지속성은 현재 가격만으로 특정할 수 없습니다.",
)

VOL_CALM_CREDIT_PERSIST = Combo(
    "vol_calm_credit_persist", "vol_credit", 96,
    "변동성 진정 · 신용 변화 지속",
    lambda ctx: ctx.vc.state == "E",
    "VIX는 내려왔지만 HY OAS는 아직 높은 상태입니다.",
    [
        ("persist", "주식시장 변동성보다 높은 HY 회사채 금리가 더 오래 남는 경우"),
        ("hy", "높은 회사채 금리가 아직 HY에 더 집중된 경우"),
    ],
    [
        Check("BBBOAS", "투자등급 경계 기업의 추가 금리",
              "BBB OAS도 오릅니다. BBB 기업의 높은 국채 대비 추가 조달비용도 함께 남아 있습니다.",
              "BBB OAS는 내려갑니다. 남아 있는 신용 약세는 저신용 기업에 더 집중된 상태입니다.",
              "투자등급 경계 기업에는 뚜렷한 변화가 없습니다. 확산 범위는 제한적일 수 있습니다.",
              supports_up=("persist",), supports_down=("hy",), supports_flat=("hy",)),
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS도 오릅니다. 우량 기업의 높은 국채 대비 추가 조달비용까지 함께 남아 있습니다.",
              "A OAS는 내려갑니다. 남아 있는 신용 약세는 하이일드에 더 집중된 상태입니다.",
              "A등급 기업의 추가 금리는 보합입니다. 투자등급 확산은 뚜렷하지 않습니다.",
              supports_up=("persist",), supports_down=("hy",), supports_flat=("hy",)),
        Check("CPSPREAD", "기업 신용도에 따른 단기자금 금리 차이",
              "단기자금 금리 차이도 벌어집니다. 주식시장 진정 뒤에도 자금조달 부담 차이가 남는 설명을 더 확인합니다.",
              "단기자금 금리 차이는 줄어듭니다. 부담 지속이 회사채 쪽에 더 집중된 설명과 맞습니다.",
              "단기자금 금리 차이에 뚜렷한 변화가 없습니다. 단기 자금시장까지 지속된다고 보기는 어렵습니다.",
              supports_up=("persist",), supports_down=("hy",), supports_flat=("hy",)),
    ],
    "VIX가 진정됐다는 사실만으로 신용시장 변화가 끝났다고 볼 수 없습니다.",
)

# --------------------------------------------------------------- cycle -----

CYCLE_RENORM_CREDIT_WIDE = Combo(
    "cycle_renorm_credit_wide", "cycle", 89,
    "재정상화 경로 · 신용스프레드 확대",
    lambda ctx: ctx.cycle.state in {"re_normalizing", "re_normalized"} and ctx.credit_widening(),
    "10Y-3M은 역전이 줄어드는 흐름이고 기업 신용스프레드는 오르고 있습니다.",
    [
        ("joint", "금리곡선 변화와 기업 신용 약세가 같은 시기에 나타난 경우"),
        ("separate", "금리곡선 변화와 신용스프레드 상승이 서로 다른 원인에서 나온 경우"),
    ],
    [
        Check("AOAS", "A등급 기업의 추가 금리",
              "A등급 기업의 추가 금리도 확대됩니다. 우량 기업의 국채 대비 추가 조달비용까지 커집니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 보합입니다. 하이일드 중심 변화일 수 있습니다.",
              supports_up=("joint",), supports_down=("separate",)),
    ],
    "수익률곡선은 선행 정보이고 신용스프레드는 현재 가격 변화라 시점과 인과를 하나로 묶을 수 없습니다.",
)

CYCLE_RENORM_CREDIT_QUIET = Combo(
    "cycle_renorm_credit_quiet", "cycle", 76,
    "재정상화 경로 · 신용스프레드 기본",
    lambda ctx: ctx.cycle.state in {"re_normalizing", "re_normalized"} and not ctx.credit_widening(),
    "10Y-3M은 역전이 줄어드는 흐름이지만 기업 신용스프레드의 동반 상승은 뚜렷하지 않습니다.",
    [
        ("cycle", "금리곡선 변화와 현재 회사채 가격이 서로 다른 흐름인 경우"),
    ],
    [
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS가 오릅니다. 우량 기업의 국채 대비 추가 조달비용까지 커지는지 확인합니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 현재 신용 약세가 우량 기업까지 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 보합입니다. 수익률곡선 경로와 현재 신용가격은 서로 다른 신호입니다.",
              supports_flat=("cycle",), supports_down=("cycle",)),
    ],
    "재정상화 자체는 호재·악재 단일 신호가 아니며 정확한 경기 시점을 알려주지 않습니다.",
)

LONG_INV_2Y_DOWN = Combo(
    "long_inv_2y_down", "cycle", 75,
    "장기 역전 · 2년물 하락",
    lambda ctx: ctx.cycle.state == "long_inverted" and ctx.core_direction("DGS2") == DOWN,
    "10Y-3M은 장기 역전 상태이고 2Y는 내렸습니다.",
    [
        ("easing", "가까운 정책완화 기대가 커져 2Y를 낮춘 경우"),
        ("slow", "경기둔화 우려가 2Y 하락에 반영된 경우"),
    ],
    [
        Check("AOAS", "A등급 기업의 추가 금리",
              "A OAS도 오릅니다. A등급 회사채의 국채 대비 추가 금리와 우량 기업의 추가 조달비용까지 커집니다.",
              "A등급 기업의 추가 금리는 축소됩니다. 우량 기업 회사채까지 같은 상승이 나타난 것은 아닙니다.",
              "A등급 기업의 추가 금리는 보합입니다. 현재 신용가격만으로 두 설명을 구분하기 어렵습니다.",
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
]
