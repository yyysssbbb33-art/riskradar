"""현재 상태에서 '다음에 무엇을 보고, 결과별로 어떻게 읽는지'를 연결한다.

이 모듈은 특정 조합이 탐지되지 않아도 각 핵심 지표마다 다음 확인 순서를 제공한다.
판정은 기존 핵심/보조지표 방향과 상태를 재사용하며 새 종합점수는 만들지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from . import config as C
from .core_directions import compute_core_direction
from .display_text import aux_name, core_name
from .formatting import fmt_change

UP, DOWN, FLAT, NA = "상승", "하락", "보합", "판정불가"


@dataclass(frozen=True)
class GuidanceCheck:
    key: str
    source: str  # direction | cycle_state
    why: str
    branches: Mapping[str, str]


@dataclass(frozen=True)
class GuidancePlan:
    intro: str
    checks: tuple[GuidanceCheck, ...]


def _direction(key: str, frames: dict[str, pd.DataFrame] | None,
               aux_df: pd.DataFrame | None) -> tuple[str, str]:
    """현재 방향과 freshness를 반환."""
    if key in {"BREAKEVEN", "IGOAS", "TERMPREM"}:
        if aux_df is None or aux_df.empty or "key" not in aux_df.columns:
            return NA, "unknown"
        hit = aux_df.loc[aux_df["key"].astype(str) == key]
        if hit.empty:
            return NA, "unknown"
        row = hit.iloc[-1]
        fresh = str(row.get("staleness_label", "unknown"))
        if fresh == "stale":
            return NA, fresh
        return str(row.get("direction", NA)), fresh

    frame = (frames or {}).get(key)
    result = compute_core_direction(key, frame)
    return result.direction, "normal"


def _cycle_state(matrix: pd.DataFrame | None) -> str:
    if matrix is None or matrix.empty or "key" not in matrix.columns:
        return "판정불가"
    hit = matrix.loc[matrix["key"].astype(str) == "T10Y3M"]
    if hit.empty:
        return "판정불가"
    return str(hit.iloc[-1].get("state_label", "판정불가"))


def _cycle_bucket(state: str) -> str:
    if state in {"역전", "장기 역전"}:
        return "역전 계열"
    if state in {"재정상화 관찰", "재정상화 확정"}:
        return "재정상화 계열"
    if state == "정상":
        return "정상"
    if state == "관찰":
        return "관찰"
    return "판정불가"


def _check(key: str, why: str, up: str, down: str, flat: str,
           source: str = "direction", extra: Mapping[str, str] | None = None) -> GuidanceCheck:
    branches = {UP: up, DOWN: down, FLAT: flat, NA: "데이터가 없거나 오래돼 이 확인은 보류합니다."}
    if extra:
        branches.update(extra)
    return GuidanceCheck(key=key, source=source, why=why, branches=branches)


def _plan_vix(state: str) -> GuidancePlan:
    if state == "평온":
        intro = "VIX는 현재 기본 구간입니다. 먼저 신용스프레드가 별도로 움직이는지 확인하면 '주식 변동성은 조용하지만 신용시장은 다른가'를 구분할 수 있습니다."
    else:
        intro = f"VIX는 현재 '{state}' 상태입니다. 지금은 이 변화가 주식시장 중심인지, 기업 신용시장까지 같은 방향인지 확인하는 순서가 가장 중요합니다."
    return GuidancePlan(intro, (
        _check("HYOAS", "주식 변동성 변화가 하이일드 신용시장 가격과 동반되는지 확인합니다.",
               "HY OAS도 확대 방향이면 주식 변동성만의 변화라는 설명은 약해지고, 신용시장도 같은 방향으로 움직이는지 확인할 근거가 커집니다.",
               "HY OAS가 축소 방향이면 광범위한 신용 동반 근거는 약해지고 주식시장 중심·이벤트성 변화 설명과 더 잘 맞습니다.",
               "HY OAS에 뚜렷한 변화가 없으면 현재 VIX 변화가 광범위한 신용 스트레스로 이어졌다고 볼 근거는 약합니다."),
        _check("IGOAS", "신용 변화가 투자등급 회사채까지 넓어지는지 확인합니다.",
               "투자등급 신용스프레드도 확대되면 신용 변화의 범위가 넓다는 설명을 더 지지합니다.",
               "투자등급 신용스프레드가 축소되면 광범위한 신용시장 동반 설명은 약해집니다.",
               "투자등급 신용스프레드가 보합이면 현재 변화는 주식 변동성 또는 하이일드 쪽에 더 국한됐을 가능성을 확인합니다."),
    ))


def _plan_hy(state: str) -> GuidancePlan:
    if state in {"평온", "중립"}:
        intro = "HY OAS는 현재 큰 확대 상태가 아닙니다. 신용시장에 변화가 숨어 있는지 보려면 투자등급 스프레드와 VIX를 같이 확인합니다."
    else:
        intro = f"HY OAS는 현재 '{state}' 상태입니다. 지금은 변화가 하이일드에 국한됐는지, 투자등급과 주식 변동성까지 넓어지는지가 핵심입니다."
    return GuidancePlan(intro, (
        _check("IGOAS", "하이일드 변화가 기업 신용시장 전반으로 넓어지는지 확인합니다.",
               "IG OAS도 확대되면 하이일드에 국한된 변화보다 신용시장 전반의 재평가 설명을 더 지지합니다.",
               "IG OAS가 축소되면 광범위한 신용 변화 설명은 약해지고 하이일드·특정 위험군 중심 가능성을 더 봅니다.",
               "IG OAS가 보합이면 신용 변화가 하이일드 쪽에 더 집중됐을 가능성을 확인합니다."),
        _check("VIX", "신용시장 변화가 주식시장 기대변동성과 같은 시기에 나타나는지 확인합니다.",
               "VIX도 상승 방향이면 변동성과 신용이 같은 시기에 움직이는 설명을 더 지지합니다.",
               "VIX가 하락 방향이면 신용 변화가 주식 변동성과 같은 방향은 아니며, 신용 고유 요인을 더 확인합니다.",
               "VIX가 보합이면 주식시장 기대변동성의 뚜렷한 동반 변화는 아직 약합니다."),
        GuidanceCheck(
            "T10Y3M", "cycle_state",
            "현재 신용가격을 경기 사이클 선행 경로와 분리해서 봅니다.",
            {
                "정상": "금리차는 정상 경로입니다. 현재 HY OAS 변화와 경기 사이클 선행 신호를 자동으로 연결할 근거는 약합니다.",
                "관찰": "금리차가 0선 부근 관찰 상태입니다. 신용 변화와 같은 방향인지 보되 하나의 경기 결론으로 묶지 않습니다.",
                "역전 계열": "역전 경로가 이어지고 있습니다. 선행 사이클 신호와 현재 신용가격이 함께 움직이는지 볼 수 있지만 침체 시점은 정할 수 없습니다.",
                "재정상화 계열": "장기 역전 뒤 재정상화 경로입니다. 신용스프레드 확대가 같이 나타나면 두 축이 같은 시기에 변한다는 사실을 확인할 수 있습니다.",
                "판정불가": "금리차 경로를 판정할 수 없어 이 확인은 보류합니다.",
            },
        ),
    ))


def _plan_cycle(state: str) -> GuidancePlan:
    intro = f"10년-3개월 금리차는 현재 '{state}' 경로입니다. 이 지표는 현재 시장 공포보다 선행축이므로, 지금 실제 신용시장 가격과 2년물 움직임을 따로 확인해야 합니다."
    return GuidancePlan(intro, (
        _check("HYOAS", "경기 사이클 경로와 현재 하이일드 신용가격이 같은 시기에 변하는지 확인합니다.",
               "HY OAS가 확대되면 선행 사이클 경로와 현재 신용시장 변화가 같은 시기에 나타난다는 설명을 더 지지합니다.",
               "HY OAS가 축소되면 현재 신용가격은 사이클 우려와 같은 방향이 아니며 둘을 분리해서 봅니다.",
               "HY OAS가 보합이면 현재 신용시장에서 같은 방향의 확인 신호는 뚜렷하지 않습니다."),
        _check("IGOAS", "신용 변화가 투자등급까지 넓어지는지 확인합니다.",
               "IG OAS도 확대되면 기업 신용시장 전반의 변화가 같은 시기에 나타난다는 설명을 더 지지합니다.",
               "IG OAS가 축소되면 광범위한 신용시장 악화 설명은 약해집니다.",
               "IG OAS가 보합이면 투자등급 시장의 동반 변화는 뚜렷하지 않습니다."),
        _check("DGS2", "가까운 정책금리 기대가 현재 수익률곡선 경로에 어떤 방향으로 작용하는지 확인합니다.",
               "2년물이 상승하면 가까운 정책금리 경로가 높아지는 방향이어서 금리차 경로와 원인을 따로 봐야 합니다.",
               "2년물이 하락하면 완화 기대가 금리차 상승·재정상화에 기여하는지 확인합니다. 경기둔화형 완화인지도 신용스프레드로 구분합니다.",
               "2년물에 뚜렷한 변화가 없으면 금리차 경로의 최근 변화 원인을 단기 정책 기대 하나로 설명하기 어렵습니다."),
    ))


def _plan_dgs30(direction: str, state: str) -> GuidancePlan:
    if direction == UP:
        intro = f"30년물은 현재 '{state}'이며 조합 해석용 방향도 상승입니다. 상승 원인을 실질금리·인플레이션 보상·Term Premium·단기 정책경로로 나눠 확인합니다."
        real = ("실질금리도 상승하면 장기금리 상승에 실질 할인율·장기 요구수익률 요인이 함께 있다는 설명을 더 지지합니다.",
                "실질금리가 하락하면 장기금리 상승을 실질금리로 설명하기 어렵고 기대인플레이션·Term Premium을 더 봅니다.",
                "실질금리가 보합이면 실질금리 하나로 현재 30년물 상승을 설명할 근거는 강하지 않습니다.")
        be = ("기대인플레이션도 상승하면 인플레이션 보상 요인이 장기금리 상승에 기여했다는 설명을 더 지지합니다.",
              "기대인플레이션이 하락하면 인플레이션 설명은 약해지고 실질금리·Term Premium 쪽을 더 확인합니다.",
              "기대인플레이션이 보합이면 장기금리 상승을 인플레이션 하나로 설명할 근거는 약합니다.")
        tp = ("Term Premium도 상승하면 장기채 수급·재정 불확실성·장기구간 위험보상 설명을 더 지지합니다.",
              "Term Premium이 하락하면 장기채 위험보상 확대만으로 설명하기 어렵습니다.",
              "Term Premium이 보합이면 장기구간 위험보상 요인은 강한 확인 신호가 아닙니다.")
        two = ("2년물도 상승하면 단기와 장기 금리가 함께 위로 재평가되는 방향입니다.",
               "2년물이 하락하면 단기 완화 기대와 장기구간 상승압력이 엇갈리는 조합이므로 원인 분해가 더 중요합니다.",
               "2년물이 보합이면 현재 움직임이 장기구간에 더 집중됐을 가능성을 확인합니다.")
    elif direction == DOWN:
        intro = f"30년물은 현재 '{state}'이며 조합 해석용 방향은 하락입니다. 완화·물가둔화인지 경기둔화·위험회피인지 구분하는 순서로 봅니다."
        real = ("실질금리가 상승하면 30년물 하락과 방향이 엇갈려 하나의 원인으로 정리하기 어렵습니다.",
                "실질금리도 하락하면 장기 실질금리 하락이 명목 장기금리 하락에 함께 작용했다는 설명을 더 지지합니다.",
                "실질금리가 보합이면 명목금리 하락 원인을 실질금리 하나로 설명하기 어렵습니다.")
        be = ("기대인플레이션이 상승하면 단순한 물가둔화 설명은 약해집니다.",
              "기대인플레이션도 하락하면 물가보상 둔화가 장기금리 하락에 기여했다는 설명을 더 지지합니다.",
              "기대인플레이션이 보합이면 물가 요인만으로 원인을 정하기 어렵습니다.")
        tp = ("Term Premium이 상승하면 장기금리 하락과 방향이 엇갈려 다른 요인이 더 강하게 작용했는지 봅니다.",
              "Term Premium도 하락하면 장기구간 위험보상 완화가 함께 작용했다는 설명을 더 지지합니다.",
              "Term Premium이 보합이면 장기구간 위험보상은 강한 설명이 아닙니다.")
        two = ("2년물이 상승하면 가까운 정책금리 기대와 장기금리가 반대로 움직이는 평탄화 방향입니다.",
               "2년물도 하락하면 완화·물가둔화 또는 경기둔화 설명을 신용스프레드로 더 구분해야 합니다.",
               "2년물이 보합이면 하락 움직임이 장기구간에 더 집중됐을 가능성을 확인합니다.")
    else:
        intro = f"30년물은 현재 '{state}'이고 조합 해석용으로는 뚜렷한 방향이 없습니다. 다른 구성요인이 먼저 움직이는지 확인합니다."
        real = ("실질금리가 상승하면 명목 30년물이 아직 크게 움직이지 않아도 실질 할인율 부담은 커지는 방향입니다.",
                "실질금리가 하락하면 명목금리보다 실질금리 쪽 변화가 먼저 나타나는지 봅니다.",
                "둘 다 보합이면 장기금리 구성요인의 뚜렷한 변화가 약합니다.")
        be = ("기대인플레이션이 상승하면 명목금리의 향후 상승 압력 여부를 관찰합니다.",
              "기대인플레이션이 하락하면 물가보상 둔화가 명목금리에 반영되는지 봅니다.",
              "보합이면 인플레이션 보상에서도 뚜렷한 변화가 없습니다.")
        tp = ("Term Premium이 상승하면 장기구간 고유 요인이 먼저 움직이는지 확인합니다.",
              "Term Premium이 하락하면 장기구간 위험보상 완화 방향을 확인합니다.",
              "보합이면 Term Premium에서도 뚜렷한 변화가 없습니다.")
        two = ("2년물이 상승하면 앞단 정책금리 기대가 먼저 올라가는지 봅니다.",
               "2년물이 하락하면 완화 기대가 앞단에서 먼저 나타나는지 봅니다.",
               "보합이면 단기와 장기 모두 강한 방향성이 약합니다.")
    return GuidancePlan(intro, (
        _check("DFII10", "명목 장기금리 변화 중 실질금리 요인이 같은 방향인지 확인합니다.", *real),
        _check("BREAKEVEN", "인플레이션 보상 방향이 현재 30년물 움직임을 설명하는지 확인합니다.", *be),
        _check("TERMPREM", "장기채 수급·재정 불확실성 등 장기구간 고유 요인을 확인합니다.", *tp),
        _check("DGS2", "단기 정책금리 기대와 장기금리 방향이 같은지 엇갈리는지 확인합니다.", *two),
    ))


def _plan_dgs2(direction: str, state: str) -> GuidancePlan:
    if direction == DOWN:
        intro = f"2년물은 현재 '{state}'이며 조합 해석용 방향은 하락입니다. 완화 기대가 물가둔화형인지 경기둔화형인지 신용과 장기금리로 구분합니다."
    elif direction == UP:
        intro = f"2년물은 현재 '{state}'이며 조합 해석용 방향은 상승입니다. 높은 정책금리 경로 재평가가 물가·성장·장기금리와 같이 움직이는지 봅니다."
    else:
        intro = f"2년물은 현재 '{state}'이고 조합 해석용으로는 뚜렷한 방향이 없습니다. 장기금리와 신용시장이 먼저 움직이는지 확인합니다."

    if direction == DOWN:
        credit_up = "신용스프레드도 확대되면 2년물 하락을 단순한 좋은 금리인하 기대보다 경기둔화·금융여건 우려와 함께 읽을 근거가 늘어납니다."
        credit_down = "신용스프레드가 축소되면 광범위한 신용 스트레스 설명은 약해지고 완화·디스인플레이션 설명과 더 잘 맞습니다."
        credit_flat = "신용스프레드가 보합이면 광범위한 신용 스트레스 확인은 약하고, 완화 기대의 이유는 다른 데이터로 더 구분해야 합니다."
    elif direction == UP:
        credit_up = "신용스프레드도 확대되면 높은 금리 기대와 신용시장 부담이 같은 시기에 나타나는지 확인합니다."
        credit_down = "신용스프레드가 축소되면 금융스트레스보다는 정책경로 재평가 설명과 더 잘 맞습니다."
        credit_flat = "신용스프레드가 보합이면 광범위한 신용 악화가 2년물 상승을 설명하는 근거는 약합니다."
    else:
        credit_up = "신용스프레드가 확대되면 금리보다 신용시장이 먼저 변하는지 확인합니다."
        credit_down = "신용스프레드가 축소되면 금융여건 완화 방향을 확인합니다."
        credit_flat = "신용스프레드도 보합이면 현재 금리·신용 모두 강한 방향성이 약합니다."

    return GuidancePlan(intro, (
        _check("DGS30", "단기와 장기 금리의 방향이 같은지 엇갈리는지 확인합니다.",
               "30년물도 상승하면 금리 전반의 상향 재평가 방향입니다.",
               "30년물이 하락하면 단기와 장기 구간이 엇갈리는 평탄화 방향입니다.",
               "30년물이 보합이면 현재 움직임이 2년물 쪽에 더 집중됐을 가능성을 확인합니다."),
        _check("HYOAS", "2년물 변화가 하이일드 신용시장 변화와 함께 나타나는지 확인합니다.",
               credit_up, credit_down, credit_flat),
        _check("IGOAS", "신용 변화가 투자등급까지 넓어지는지 확인합니다.",
               "IG OAS도 확대되면 신용 변화의 범위가 넓다는 설명을 더 지지합니다.",
               "IG OAS가 축소되면 광범위한 신용 악화 설명은 약해집니다.",
               "IG OAS가 보합이면 투자등급 시장의 뚜렷한 동반 변화는 없습니다."),
        _check("BREAKEVEN", "물가보상 방향이 정책금리 기대 변화와 같은 방향인지 확인합니다.",
               "기대인플레이션이 상승하면 높은 정책금리 지속 설명을 더 확인합니다.",
               "기대인플레이션이 하락하면 물가둔화·완화 기대 설명을 더 지지할 수 있습니다.",
               "기대인플레이션이 보합이면 물가 요인만으로 2년물 움직임을 설명하기 어렵습니다."),
    ))


def _plan_real(direction: str, state: str) -> GuidancePlan:
    if direction == UP:
        intro = f"10년 실질금리는 현재 '{state}'이며 방향은 상승입니다. 명목 장기금리와 같이 오르는지, 기대인플레이션과 Term Premium도 움직이는지 확인해 상승의 성격을 구분합니다."
    elif direction == DOWN:
        intro = f"10년 실질금리는 현재 '{state}'이며 방향은 하락입니다. 완화적 할인율 변화인지 경기둔화·위험회피와 함께 나타나는지 다른 시장을 확인합니다."
    else:
        intro = f"10년 실질금리는 현재 '{state}'이고 뚜렷한 방향이 없습니다. 명목금리나 기대인플레이션이 먼저 움직이는지 확인합니다."
    return GuidancePlan(intro, (
        _check("DGS30", "실질금리 변화가 명목 장기금리와 같은 방향인지 확인합니다.",
               "30년물도 상승하면 실질금리 변화가 명목 장기금리 움직임과 같은 방향입니다.",
               "30년물이 하락하면 실질·명목 금리가 엇갈려 하나의 원인으로 정리하기 어렵습니다.",
               "30년물이 보합이면 현재 변화가 실질금리 쪽에 더 집중됐을 가능성을 확인합니다."),
        _check("BREAKEVEN", "실질금리와 인플레이션 보상이 함께 움직이는지 확인합니다.",
               "기대인플레이션도 상승하면 실질금리와 물가보상이 함께 작용하는 복합 설명을 봅니다.",
               "기대인플레이션이 하락하면 명목금리 구성에서 실질금리 쪽 변화가 상대적으로 더 두드러질 수 있습니다.",
               "기대인플레이션이 보합이면 인플레이션 보상보다 실질금리 변화가 상대적으로 더 뚜렷합니다."),
        _check("TERMPREM", "장기구간 위험보상·수급 요인이 같이 움직이는지 확인합니다.",
               "Term Premium도 상승하면 장기구간 위험보상 요인까지 함께 작용할 가능성을 확인합니다.",
               "Term Premium이 하락하면 장기채 위험보상 확대 설명은 약합니다.",
               "Term Premium이 보합이면 실질금리 변화와 별개로 강한 장기구간 확인 신호는 없습니다."),
    ))


def build_plan(key: str, row: pd.Series | dict,
               frames: dict[str, pd.DataFrame] | None = None) -> GuidancePlan:
    r = pd.Series(row)
    state = str(r.get("state_label", "판정불가"))
    primary_direction, _ = _direction(key, frames, None)

    if key == "VIX":
        return _plan_vix(state)
    if key == "HYOAS":
        return _plan_hy(state)
    if key == "T10Y3M":
        return _plan_cycle(state)
    if key == "DGS30":
        return _plan_dgs30(primary_direction, state)
    if key == "DGS2":
        return _plan_dgs2(primary_direction, state)
    if key == "DFII10":
        return _plan_real(primary_direction, state)
    return GuidancePlan("현재 상태에서 추가 확인 순서를 만들 수 없습니다.", ())


def _current_result(check: GuidanceCheck, frames: dict[str, pd.DataFrame] | None,
                    aux_df: pd.DataFrame | None, matrix: pd.DataFrame | None) -> tuple[str, str, str]:
    if check.source == "cycle_state":
        state = _cycle_state(matrix)
        return _cycle_bucket(state), "normal", f"현재 상태 {state}"

    result, freshness = _direction(check.key, frames, aux_df)
    detail = ""
    if check.key in C.SERIES:
        frame = (frames or {}).get(check.key)
        if frame is not None and not frame.empty and "change_20obs" in frame.columns:
            value = pd.to_numeric(frame["change_20obs"], errors="coerce").iloc[-1]
            if pd.notna(value):
                detail = f"약 1개월 변화 {fmt_change(float(value), C.SERIES[check.key].change_unit)}"
    elif check.key in {"BREAKEVEN", "IGOAS", "TERMPREM"} and aux_df is not None and not aux_df.empty:
        hit = aux_df.loc[aux_df["key"].astype(str) == check.key] if "key" in aux_df.columns else pd.DataFrame()
        if not hit.empty:
            row = hit.iloc[-1]
            value = row.get("change_1m")
            unit = str(row.get("change_unit", ""))
            if value is not None and pd.notna(value):
                detail = f"약 1개월 변화 {fmt_change(float(value), unit)}"
    return result, freshness, detail


def render_state_guidance(key: str, row: pd.Series | dict,
                          frames: dict[str, pd.DataFrame] | None = None,
                          aux_df: pd.DataFrame | None = None,
                          matrix: pd.DataFrame | None = None) -> str:
    """현재 상태 → 다음 확인지표 → 결과별 해석을 렌더링한다."""
    plan = build_plan(key, row, frames=frames)
    lines = [
        "## 지금 이 상태에서 다음으로 볼 것",
        "",
        plan.intro,
    ]
    if key in {"DGS30", "DGS2", "DFII10"}:
        lines += [
            "",
            "> 참고: `상태`는 강한 변화속도를 잡는 기존 규칙이고, `조합 방향`은 자기 과거 변화폭 대비 방향입니다. 그래서 `안정 + 상승 방향`처럼 둘이 동시에 표시될 수 있습니다.",
        ]
    lines += [
        "",
        "아래는 **현재 결과를 먼저 해석하고**, 같은 확인지표가 다르게 움직일 경우 해석이 어떻게 달라지는지도 함께 보여줍니다.",
    ]

    for idx, check in enumerate(plan.checks, start=1):
        result, freshness, detail = _current_result(check, frames, aux_df, matrix)
        current_text = check.branches.get(result, check.branches.get(NA, "현재 결과를 해석할 수 없습니다."))
        label = aux_name(check.key) if check.key in {"BREAKEVEN", "IGOAS", "TERMPREM"} else core_name(check.key, short=True)
        fresh_note = ""
        if freshness == "delayed":
            fresh_note = " · 업데이트 지연"
        elif freshness == "stale":
            fresh_note = " · 오래된 자료, 현재 해석에서 제외"

        lines += [
            "",
            f"### {idx}. {label}",
            f"**왜 보나:** {check.why}",
            "",
            f"**현재 결과: {result}{(' · ' + detail) if detail else ''}{fresh_note}**",
            "",
            f"> {current_text}",
            "",
            "**결과가 달라지면**",
        ]
        for branch, text in check.branches.items():
            if branch == NA or branch == result:
                continue
            lines.append(f"- **{branch}:** {text}")

    lines += [
        "",
        "> 결과가 서로 다른 설명을 동시에 지지하면 하나를 억지로 고르지 않습니다. 그 경우 복수 요인 또는 판단 어려움으로 남깁니다.",
    ]
    return "\n".join(lines)
