"""현재 상태에서 '다음에 무엇을 보고, 결과별로 어떻게 읽는지'를 연결한다.

이 모듈은 특정 조합이 탐지되지 않아도 각 핵심 지표마다 다음 확인 순서를 제공한다.
판정은 기존 핵심/보조지표 방향과 상태를 재사용하며 새 종합점수는 만들지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from . import aux_config as AC
from . import config as C
from .core_directions import compute_core_direction
from .display_text import aux_name, core_name, plain_language, state_name
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
    if key in AC.AUX_SERIES:
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
    return str(hit.iloc[-1].get("state_code", "판정불가"))


def _cycle_bucket(state: str) -> str:
    # state_code를 우선 쓰되, 구버전 캐시의 한국어 state_label도 받아준다.
    if state in {"inverted", "long_inverted", "역전", "장기 역전", "장기역전", "단기금리가 더 높음", "단기금리가 오래 더 높음"}:
        return "단기금리가 더 높은 흐름"
    if state in {"re_normalizing", "re_normalized", "재정상화 관찰", "재정상화 확정", "장기금리가 다시 높아짐", "장기금리가 다시 높은 상태가 이어짐"}:
        return "장기금리가 다시 높아지는 흐름"
    if state in {"normal", "정상", "장기금리가 더 높음"}:
        return "장기금리가 더 높음"
    if state in {"watch", "관찰", "두 금리가 거의 비슷함"}:
        return "두 금리가 거의 비슷함"
    return "판정불가"


def _check(key: str, why: str, up: str, down: str, flat: str,
           source: str = "direction", extra: Mapping[str, str] | None = None) -> GuidanceCheck:
    branches = {UP: up, DOWN: down, FLAT: flat, NA: "데이터가 없거나 오래돼 이 확인은 보류합니다."}
    if extra:
        branches.update(extra)
    return GuidanceCheck(key=key, source=source, why=why, branches=branches)


def _plan_vix(state: str) -> GuidancePlan:
    if state == "평소 수준":
        intro = (
            "주식시장이 예상하는 흔들림은 현재 평소 수준입니다. "
            "그래도 회사채 쪽이 따로 움직일 수 있으므로 기업의 추가금리를 함께 확인합니다."
        )
    else:
        intro = (
            f"주식시장이 예상하는 흔들림은 현재 '{state}'입니다. "
            "이 변화가 주식시장에만 있는지, 기업이 돈을 빌리는 비용에도 같이 나타나는지 확인합니다."
        )
    return GuidancePlan(intro, (
        _check(
            "HYOAS",
            "신용등급 낮은 기업이 국채보다 더 얹어 줘야 하는 금리도 같이 움직이는지 봅니다.",
            "이 추가금리도 오르면 주식시장만의 변화라는 설명은 약해지고, 회사채 쪽 부담도 같이 커지는지 볼 근거가 늘어납니다.",
            "이 추가금리가 내리면 회사채 시장 전반이 같이 나빠졌다는 설명은 약해지고, 주식시장 중심의 일시적 변화일 가능성을 더 봅니다.",
            "이 추가금리에 뚜렷한 움직임이 없으면 현재 주식시장 흔들림이 회사채 시장 전반으로 이어졌다고 볼 근거는 약합니다.",
        ),
        _check(
            "BBBOAS",
            "회사채 부담이 저신용 기업을 넘어 투자등급 경계 기업까지 번지는지 봅니다.",
            "투자등급 경계 기업의 추가금리도 오르면 주식시장 흔들림과 함께 기업 자금 부담의 범위도 넓어지는지 볼 근거가 늘어납니다.",
            "투자등급 경계 기업의 추가금리가 내리면 회사채 부담이 넓게 번진다는 설명은 약해집니다.",
            "투자등급 경계 기업의 추가금리에 뚜렷한 움직임이 없으면 변화가 주식시장이나 저신용 기업 쪽에 더 집중됐을 가능성을 봅니다.",
        ),
        _check(
            "AOAS",
            "기업 자금 부담이 A등급 기업까지 넓어지는지 봅니다.",
            "A등급 기업의 추가금리도 오르면 기업 자금 부담이 더 넓은 범위에서 커지고 있다는 설명을 더 지지합니다.",
            "A등급 기업의 추가금리가 내리면 기업 전반의 자금 부담이 같이 커졌다는 설명은 약해집니다.",
            "A등급 기업의 추가금리에 뚜렷한 움직임이 없으면 변화가 주식시장이나 신용등급 낮은 기업 쪽에 더 집중됐을 가능성을 봅니다.",
        ),
        _check(
            "CPSPREAD",
            "주식시장 흔들림이 단기 기업자금시장의 신용도 차별과 같은 시기에 나타나는지 봅니다.",
            "단기자금 금리 차이도 벌어지면 주식시장 불안이 기업의 단기 자금조달 차별과 함께 나타나는지 더 확인합니다.",
            "단기자금 금리 차이가 줄면 단기 기업자금시장까지 부담이 번졌다는 설명은 약해집니다.",
            "단기자금 금리 차이에 뚜렷한 움직임이 없으면 현재 변화가 단기 기업자금시장까지 이어졌다는 근거는 약합니다.",
        ),
    ))


def _plan_hy(state: str) -> GuidancePlan:
    if state in {"평소 수준", "보통 수준"}:
        intro = (
            "신용등급 낮은 기업의 추가금리는 현재 큰 변화가 없습니다. "
            "A등급 기업과 주식시장에도 다른 움직임이 있는지 함께 봅니다."
        )
    else:
        intro = (
            f"신용등급 낮은 기업의 추가금리는 현재 '{state}'입니다. "
            "이 변화가 낮은 등급 기업에만 있는지, A등급 기업과 주식시장까지 넓어지는지 확인합니다."
        )
    return GuidancePlan(intro, (
        _check(
            "BBBOAS",
            "저신용 기업의 부담이 투자등급 경계 기업까지 번지는지 봅니다.",
            "투자등급 경계 기업의 추가금리도 오르면 기업 자금 부담이 저신용 기업을 넘어 넓어지는 설명을 더 지지합니다.",
            "투자등급 경계 기업의 추가금리가 내리면 현재 변화가 저신용 기업에 더 집중됐다는 설명과 잘 맞습니다.",
            "투자등급 경계 기업의 추가금리에 뚜렷한 움직임이 없으면 BBB까지 부담이 번졌다는 확인 신호는 약합니다.",
        ),
        _check(
            "AOAS",
            "A등급 기업도 국채보다 더 높은 금리를 요구받는지 봅니다.",
            "A등급 기업의 추가금리도 오르면 기업 자금 부담이 더 넓은 범위에서 커지고 있다는 설명을 더 지지합니다.",
            "A등급 기업의 추가금리가 내리면 변화가 신용등급 낮은 기업이나 특정 업종에 더 집중됐다는 설명과 잘 맞습니다.",
            "A등급 기업의 추가금리에 뚜렷한 움직임이 없으면 변화가 낮은 등급 기업 쪽에 더 집중됐을 가능성을 봅니다.",
        ),
        _check(
            "CPSPREAD",
            "회사채 부담이 단기 기업자금시장의 신용도 차별까지 같이 나타나는지 봅니다.",
            "단기자금 금리 차이도 벌어지면 기업 자금조달 부담이 회사채뿐 아니라 단기시장에서도 나타나는지 더 확인합니다.",
            "단기자금 금리 차이가 줄면 단기 기업자금시장까지 부담이 번졌다는 설명은 약해집니다.",
            "단기자금 금리 차이에 뚜렷한 움직임이 없으면 현재 회사채 변화가 단기 자금시장까지 번졌다는 근거는 약합니다.",
        ),
        _check(
            "VIX",
            "기업 자금 부담 변화가 주식시장이 예상하는 흔들림과 같은 시기에 나타나는지 봅니다.",
            "주식시장 흔들림도 커지면 주식과 회사채가 같은 시기에 움직인다는 설명을 더 지지합니다.",
            "주식시장 흔들림이 줄면 회사채 쪽 변화가 주식시장과 같은 방향은 아니므로 회사채 자체 원인을 더 봅니다.",
            "주식시장 흔들림에 뚜렷한 변화가 없으면 주식과 회사채가 함께 움직인다는 신호는 아직 뚜렷하지 않습니다.",
        ),
        GuidanceCheck(
            "T10Y3M",
            "cycle_state",
            "현재 회사채 부담과 10년 금리·3개월 금리의 관계를 따로 봅니다.",
            {
                "장기금리가 더 높음": "10년 금리가 3개월 금리보다 높습니다. 이 사실만으로 현재 회사채 부담과 같은 경기 결론을 내리지는 않습니다.",
                "두 금리가 거의 비슷함": "10년 금리와 3개월 금리가 거의 비슷합니다. 회사채 부담과 같이 보되 하나의 경기 결론으로 묶지 않습니다.",
                "단기금리가 더 높은 흐름": "3개월 금리가 10년 금리보다 높습니다. 경기보다 먼저 움직이는 신호와 현재 회사채 부담이 함께 움직이는지는 볼 수 있지만 침체 시점은 정할 수 없습니다.",
                "장기금리가 다시 높아지는 흐름": "한동안 3개월 금리가 더 높았지만 최근 10년 금리가 다시 높아졌습니다. 회사채 추가금리도 같은 시기에 커지는지 따로 봅니다.",
                "판정불가": "10년 금리와 3개월 금리의 관계를 확인할 수 없어 이 확인은 보류합니다.",
            },
        ),
    ))


def _plan_cycle(state: str) -> GuidancePlan:
    state_intro = {
        "장기금리가 더 높음": "현재 10년 금리가 3개월 금리보다 높습니다.",
        "두 금리가 거의 비슷함": "현재 10년 금리와 3개월 금리가 거의 비슷합니다.",
        "단기금리가 더 높은 흐름": "현재 3개월 금리가 10년 금리보다 높습니다.",
        "장기금리가 다시 높아지는 흐름": "한동안 3개월 금리가 더 높았지만 최근 10년 금리가 다시 높아졌습니다.",
    }.get(state, f"현재 두 금리의 관계는 '{state}'입니다.")
    intro = (
        f"{state_intro} 이 지표는 지금 시장이 불안한지를 직접 보여주기보다 경기보다 먼저 움직이는 신호에 가깝습니다. "
        "그래서 현재 회사채 부담과 2년 금리를 따로 확인합니다."
    )
    return GuidancePlan(intro, (
        _check(
            "HYOAS",
            "10년 금리와 3개월 금리의 관계 변화가 현재 기업 자금 부담과 같은 시기에 나타나는지 봅니다.",
            "신용등급 낮은 기업의 추가금리가 오르면 경기보다 먼저 움직이는 신호와 현재 기업 자금 부담 변화가 같은 시기에 나타난다는 설명을 더 지지합니다.",
            "이 추가금리가 내리면 현재 기업 자금 부담은 같은 방향이 아니므로 두 움직임을 분리해서 봅니다.",
            "이 추가금리에 뚜렷한 움직임이 없으면 회사채 시장에서 같은 방향의 확인 신호는 뚜렷하지 않습니다.",
        ),
        _check(
            "AOAS",
            "기업 자금 부담 변화가 A등급 기업까지 넓어지는지 봅니다.",
            "A등급 기업의 추가금리도 오르면 기업 자금 부담이 더 넓은 범위에서 커지고 있다는 설명을 더 지지합니다.",
            "A등급 기업의 추가금리가 내리면 기업 전반의 자금 부담 악화라는 설명은 약해집니다.",
            "A등급 기업의 추가금리에 뚜렷한 움직임이 없으면 넓은 범위의 회사채가 함께 움직인다는 신호는 뚜렷하지 않습니다.",
        ),
        _check(
            "DGS2",
            "가까운 기준금리 예상이 10년 금리와 3개월 금리의 관계에 어떤 영향을 주는지 봅니다.",
            "2년 금리가 오르면 가까운 기준금리 예상도 높아지는 방향이므로, 두 금리의 관계가 바뀐 이유를 따로 봐야 합니다.",
            "2년 금리가 내리면 금리인하 기대가 두 금리의 관계 변화에 기여하는지 봅니다. 경기가 식을 우려로 금리인하 기대가 커진 것인지도 회사채 추가금리로 구분합니다.",
            "2년 금리에 뚜렷한 움직임이 없으면 최근 두 금리의 관계 변화를 가까운 기준금리 예상 하나로 설명하기 어렵습니다.",
        ),
    ))


def _direction_words(direction: str) -> str:
    return {UP: "오르는 쪽", DOWN: "내리는 쪽", FLAT: "뚜렷한 방향 없음", NA: "확인 불가"}.get(direction, direction)


def _plan_dgs30(direction: str, state: str) -> GuidancePlan:
    intro = (
        f"30년 금리는 현재 '{state}'입니다. 자기 과거 움직임과 비교하면 최근에는 '{_direction_words(direction)}'입니다. "
        "원인을 나누려면 물가 영향을 뺀 금리, 시장의 물가 예상, 장기채 추가 보상, 2년 금리를 차례로 봅니다."
    )
    if direction == UP:
        real = (
            "물가 영향을 뺀 금리도 오르면 장기금리 상승에 물가 이외의 금리 요인도 함께 작용한다는 설명을 더 지지합니다.",
            "물가 영향을 뺀 금리가 내리면 장기금리 상승을 그 요인 하나로 설명하기 어렵고 시장의 물가 예상과 장기채 추가 보상을 더 봅니다.",
            "물가 영향을 뺀 금리에 뚜렷한 움직임이 없으면 그 요인 하나로 현재 30년 금리 상승을 설명할 근거는 강하지 않습니다.",
        )
        be = (
            "시장의 물가 예상도 오르면 물가 관련 요인이 장기금리 상승에 기여했다는 설명을 더 지지합니다.",
            "시장의 물가 예상이 내리면 물가 설명은 약해지고 다른 금리 요인을 더 봅니다.",
            "시장의 물가 예상에 뚜렷한 움직임이 없으면 장기금리 상승을 물가 하나로 설명할 근거는 약합니다.",
        )
        tp = (
            "장기채 추가 보상도 오르면 장기채 수요·공급이나 재정 불확실성 같은 장기채 자체 요인을 더 지지합니다.",
            "장기채 추가 보상이 내리면 그 보상이 커진 것만으로 현재 금리 상승을 설명하기 어렵습니다.",
            "장기채 추가 보상에 뚜렷한 움직임이 없으면 이 요인은 강한 확인 신호가 아닙니다.",
        )
        two = (
            "2년 금리도 오르면 단기와 장기 금리가 함께 오르는 모습입니다.",
            "2년 금리가 내리면 가까운 금리인하 기대와 장기금리 상승이 엇갈리므로 원인 구분이 더 중요합니다.",
            "2년 금리에 뚜렷한 움직임이 없으면 현재 움직임이 장기금리 쪽에 더 집중됐을 가능성을 봅니다.",
        )
    elif direction == DOWN:
        real = (
            "물가 영향을 뺀 금리가 오르면 30년 금리와 방향이 엇갈려 하나의 원인으로 정리하기 어렵습니다.",
            "물가 영향을 뺀 금리도 내리면 이 요인이 장기금리 하락에 함께 작용했다는 설명을 더 지지합니다.",
            "물가 영향을 뺀 금리에 뚜렷한 움직임이 없으면 30년 금리 하락 원인을 이 지표 하나로 설명하기 어렵습니다.",
        )
        be = (
            "시장의 물가 예상이 오르면 단순한 물가 둔화 설명은 약해집니다.",
            "시장의 물가 예상도 내리면 물가 상승세 둔화가 장기금리 하락에 기여했다는 설명을 더 지지합니다.",
            "시장의 물가 예상에 뚜렷한 움직임이 없으면 물가 요인만으로 원인을 정하기 어렵습니다.",
        )
        tp = (
            "장기채 추가 보상이 오르면 30년 금리와 방향이 엇갈리므로 다른 요인이 더 강하게 작용했는지 봅니다.",
            "장기채 추가 보상도 내리면 장기채 자체 부담이 줄어드는 움직임이 함께 작용했다는 설명을 더 지지합니다.",
            "장기채 추가 보상에 뚜렷한 움직임이 없으면 이 요인은 강한 설명이 아닙니다.",
        )
        two = (
            "2년 금리가 오르면 단기금리와 장기금리가 서로 반대로 움직이며 두 금리 차이가 줄어드는 모습입니다.",
            "2년 금리도 내리면 금리인하 기대인지 경기 둔화 우려인지 회사채 추가금리로 더 구분합니다.",
            "2년 금리에 뚜렷한 움직임이 없으면 하락 움직임이 장기금리 쪽에 더 집중됐을 가능성을 봅니다.",
        )
    else:
        real = (
            "물가 영향을 뺀 금리가 오르면 30년 금리가 크게 움직이지 않아도 물가 이외의 금리 부담은 커지는 방향입니다.",
            "물가 영향을 뺀 금리가 내리면 그쪽 변화가 먼저 나타나는지 봅니다.",
            "둘 다 뚜렷한 움직임이 없으면 장기금리를 구성하는 요인에서도 큰 변화가 약합니다.",
        )
        be = (
            "시장의 물가 예상이 오르면 앞으로 장기금리에도 같은 방향의 압력이 나타나는지 봅니다.",
            "시장의 물가 예상이 내리면 물가 관련 금리 요인이 줄어드는 방향인지 봅니다.",
            "시장의 물가 예상에도 뚜렷한 움직임이 없습니다.",
        )
        tp = (
            "장기채 추가 보상이 오르면 장기채 자체 요인이 먼저 움직이는지 봅니다.",
            "장기채 추가 보상이 내리면 장기채를 오래 보유할 때 요구하는 보상이 줄어드는 방향인지 봅니다.",
            "장기채 추가 보상에도 뚜렷한 움직임이 없습니다.",
        )
        two = (
            "2년 금리가 오르면 가까운 기준금리 예상이 먼저 높아지는지 봅니다.",
            "2년 금리가 내리면 금리인하 기대가 단기금리 쪽에서 먼저 나타나는지 봅니다.",
            "2년 금리에도 뚜렷한 움직임이 없으면 단기와 장기 금리 모두 강한 방향이 약합니다.",
        )
    return GuidancePlan(intro, (
        _check("DFII10", "30년 금리 변화에 물가를 뺀 금리도 같은 방향으로 움직이는지 봅니다.", *real),
        _check("BREAKEVEN", "시장의 장기 물가 예상도 같은 방향으로 움직이는지 봅니다.", *be),
        _check("TERMPREM", "장기채를 오래 보유하기 위해 요구하는 추가 보상이 변했는지 봅니다.", *tp),
        _check("DGS2", "가까운 기준금리 예상에 민감한 2년 금리가 같은 방향인지 봅니다.", *two),
    ))


def _plan_dgs2(direction: str, state: str) -> GuidancePlan:
    intro = (
        f"2년 금리는 현재 '{state}'입니다. 자기 과거 움직임과 비교하면 최근에는 '{_direction_words(direction)}'입니다. "
        "이 변화가 가까운 기준금리 예상 때문인지, 경기나 물가 우려와 함께 나타나는지 다른 지표로 구분합니다."
    )
    if direction == DOWN:
        credit_up = "회사채 추가금리도 오르면 단순한 좋은 금리인하 기대보다 경기 둔화나 기업 자금 부담 우려를 함께 볼 근거가 늘어납니다."
        credit_down = "회사채 추가금리가 내리면 기업 전반의 자금 부담 악화라는 설명은 약해지고 금리인하·물가 둔화 설명과 더 잘 맞습니다."
        credit_flat = "회사채 추가금리에 뚜렷한 움직임이 없으면 기업 전반의 자금 부담 악화라는 확인 신호는 약합니다."
    elif direction == UP:
        credit_up = "회사채 추가금리도 오르면 높은 금리 예상과 기업 자금 부담이 같은 시기에 나타나는지 봅니다."
        credit_down = "회사채 추가금리가 내리면 시장 불안보다 기준금리 예상 변화라는 설명과 더 잘 맞습니다."
        credit_flat = "회사채 추가금리에 뚜렷한 움직임이 없으면 기업 자금 부담 악화가 2년 금리 상승을 설명할 근거는 약합니다."
    else:
        credit_up = "회사채 추가금리가 오르면 금리보다 기업 자금 부담이 먼저 변하는지 봅니다."
        credit_down = "회사채 추가금리가 내리면 기업 자금 부담이 줄어드는 방향인지 봅니다."
        credit_flat = "회사채 추가금리에도 뚜렷한 움직임이 없으면 금리와 기업 자금 부담 모두 강한 방향이 약합니다."
    return GuidancePlan(intro, (
        _check(
            "DGS30",
            "단기와 장기 금리가 같은 방향인지 엇갈리는지 봅니다.",
            "30년 금리도 오르면 단기와 장기 금리가 함께 오르는 모습입니다.",
            "30년 금리가 내리면 단기와 장기 금리가 엇갈리며 두 금리 차이가 줄어드는 모습입니다.",
            "30년 금리에 뚜렷한 움직임이 없으면 현재 변화가 2년 금리 쪽에 더 집중됐을 가능성을 봅니다.",
        ),
        _check("HYOAS", "신용등급 낮은 기업의 자금 부담이 같은 시기에 변하는지 봅니다.", credit_up, credit_down, credit_flat),
        _check(
            "AOAS",
            "기업 자금 부담 변화가 A등급 기업까지 넓어지는지 봅니다.",
            "A등급 기업의 추가금리도 오르면 기업 자금 부담이 더 넓은 범위에서 커지고 있다는 설명을 더 지지합니다.",
            "A등급 기업의 추가금리가 내리면 기업 전반의 자금 부담 악화라는 설명은 약해집니다.",
            "A등급 기업의 추가금리에 뚜렷한 움직임이 없으면 넓은 범위의 회사채가 함께 움직인다는 신호는 없습니다.",
        ),
        _check(
            "BREAKEVEN",
            "시장의 물가 예상이 가까운 기준금리 예상 변화와 같은 방향인지 봅니다.",
            "시장의 물가 예상이 오르면 높은 금리가 오래 이어질 수 있다는 설명을 더 확인합니다.",
            "시장의 물가 예상이 내리면 물가 상승세 둔화와 금리인하 기대 설명을 더 지지할 수 있습니다.",
            "시장의 물가 예상에 뚜렷한 움직임이 없으면 물가 요인만으로 2년 금리 움직임을 설명하기 어렵습니다.",
        ),
    ))


def _plan_real(direction: str, state: str) -> GuidancePlan:
    intro = (
        f"물가 영향을 뺀 10년 금리는 현재 '{state}'입니다. 자기 과거 움직임과 비교하면 최근에는 '{_direction_words(direction)}'입니다. "
        "30년 금리, 시장의 물가 예상, 장기채 추가 보상을 함께 봐야 무엇이 움직였는지 더 잘 구분할 수 있습니다."
    )
    return GuidancePlan(intro, (
        _check(
            "DGS30",
            "물가를 뺀 금리 변화가 일반 장기금리와 같은 방향인지 봅니다.",
            "30년 금리도 오르면 물가를 뺀 금리 변화가 일반 장기금리와 같은 방향입니다.",
            "30년 금리가 내리면 두 금리가 엇갈려 하나의 원인으로 정리하기 어렵습니다.",
            "30년 금리에 뚜렷한 움직임이 없으면 현재 변화가 물가를 뺀 금리 쪽에 더 집중됐을 가능성을 봅니다.",
        ),
        _check(
            "BREAKEVEN",
            "시장의 물가 예상도 같이 움직이는지 봅니다.",
            "시장의 물가 예상도 오르면 물가를 뺀 금리와 물가 관련 요인이 함께 움직이는 설명을 봅니다.",
            "시장의 물가 예상이 내리면 일반 장기금리 안에서 물가를 뺀 금리 쪽 변화가 상대적으로 더 두드러질 수 있습니다.",
            "시장의 물가 예상에 뚜렷한 움직임이 없으면 물가 관련 요인보다 물가를 뺀 금리 변화가 상대적으로 더 뚜렷합니다.",
        ),
        _check(
            "TERMPREM",
            "장기채를 오래 보유하기 위해 요구하는 추가 보상도 같이 움직이는지 봅니다.",
            "장기채 추가 보상도 오르면 장기채 자체 요인까지 함께 작용할 가능성을 봅니다.",
            "장기채 추가 보상이 내리면 그 보상이 커졌다는 설명은 약합니다.",
            "장기채 추가 보상에 뚜렷한 움직임이 없으면 이 지표에서 강한 추가 확인 신호는 없습니다.",
        ),
    ))


def build_plan(key: str, row: pd.Series | dict,
               frames: dict[str, pd.DataFrame] | None = None) -> GuidancePlan:
    r = pd.Series(row)
    state = state_name(str(r.get("state_code", "")), str(r.get("state_label", "판정불가")), drop=bool(r.get("drop_flag", False)), key=key)
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
        bucket = _cycle_bucket(state)
        return bucket, "normal", state_name(state, key="T10Y3M")

    result, freshness = _direction(check.key, frames, aux_df)
    detail = ""
    if check.key in C.SERIES:
        frame = (frames or {}).get(check.key)
        if frame is not None and not frame.empty and "change_20obs" in frame.columns:
            value = pd.to_numeric(frame["change_20obs"], errors="coerce").iloc[-1]
            if pd.notna(value):
                detail = f"약 1개월 변화 {fmt_change(float(value), C.SERIES[check.key].change_unit)}"
    elif check.key in AC.AUX_SERIES and aux_df is not None and not aux_df.empty:
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
            "> 참고: `상태`는 최근 움직임이 평소보다 큰지를 보고, `최근 움직임`은 자기 과거와 비교해 어느 쪽으로 움직이는지를 봅니다. 그래서 `큰 움직임 없음`이면서도 최근에는 조금 오르는 쪽일 수 있습니다.",
        ]
    lines += [
        "",
        "아래는 **현재 결과를 먼저 해석하고**, 같은 확인지표가 다르게 움직일 경우 해석이 어떻게 달라지는지도 함께 보여줍니다.",
    ]

    for idx, check in enumerate(plan.checks, start=1):
        result, freshness, detail = _current_result(check, frames, aux_df, matrix)
        current_text = check.branches.get(result, check.branches.get(NA, "현재 결과를 해석할 수 없습니다."))
        label = aux_name(check.key) if check.key in AC.AUX_SERIES else core_name(check.key, short=True)
        fresh_note = ""
        if freshness == "delayed":
            fresh_note = " · 업데이트 지연"
        elif freshness == "stale":
            fresh_note = " · 오래된 자료, 현재 해석에서 제외"

        if check.source == "cycle_state":
            result_display = detail or "확인 불가"
            detail = ""
        else:
            result_display = {"상승": "오르는 중", "하락": "내리는 중", "보합": "뚜렷한 변화 없음", "판정불가": "확인 불가"}.get(result, result)
        lines += [
            "",
            f"### {idx}. {label}",
            f"**왜 보나:** {check.why}",
            "",
            f"**현재 결과: {result_display}{(' · ' + detail) if detail else ''}{fresh_note}**",
            "",
            f"> {current_text}",
            "",
            "**결과가 달라지면**",
        ]
        for branch, text in check.branches.items():
            if branch == NA or branch == result:
                continue
            branch_display = {"상승": "오르면", "하락": "내리면", "보합": "뚜렷한 변화가 없으면"}.get(branch, branch)
            lines.append(f"- **{branch_display}:** {text}")

    lines += [
        "",
        "> 결과가 서로 다른 설명을 동시에 지지하면 하나를 억지로 고르지 않습니다. 그 경우 복수 요인 또는 판단 어려움으로 남깁니다.",
    ]
    return plain_language("\n".join(lines))
