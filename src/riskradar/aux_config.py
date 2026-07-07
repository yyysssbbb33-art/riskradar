"""RiskRadar 확인지표·외부참고 설정.

v0.6.0의 3층 구조
- 핵심 신호: 기존 핵심 6개 + 기업 신용 블록의 HY-BBB 해석 렌즈
- 확인 지표: 장기금리 원인(BREAKEVEN/TERMPREM), 신용 범위(BBB/A), 단기자금(CP)
- 외부 참고: NFCI/STLFSI

broad IG(IGOAS)는 과거 캐시와 운영 진단을 위해 수집은 유지하지만 범위 엔진·UI 상세 목록에서는 제외한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuxSeries:
    series_id: str
    key: str
    display_name: str
    role: str
    source: str
    raw_to_value: float
    value_unit: str
    change_to_disp: float
    change_unit: str
    category: str = "confirmation"
    fetch_kind: str = "direct"
    component_series_ids: tuple[str, ...] = ()
    use_in_engine: bool = True
    visible: bool = True
    layer: str = "confirmation"  # confirmation | external | legacy
    lookback_obs: int | None = None
    span_guard_days: int | None = None
    flat_abs_pct: float | None = None
    min_obs: int | None = None


AUX_SERIES: dict[str, AuxSeries] = {
    "BREAKEVEN": AuxSeries(
        "T10YIE", "BREAKEVEN", "채권시장이 보는 10년 물가 예상",
        "장기금리가 움직일 때 시장의 장기 물가 예상도 같은 방향인지 확인",
        "fred", 1.0, "%", 100.0, "bp", category="rate_cause",
    ),
    "TERMPREM": AuxSeries(
        "THREEFYTP10", "TERMPREM", "장기채 추가 보상",
        "장기채 수요·공급과 장기 보유 불확실성 때문에 요구하는 추가 보상이 변했는지 확인",
        "fred", 1.0, "%", 100.0, "bp", category="rate_cause",
    ),
    "BBBOAS": AuxSeries(
        "BAMLC0A4CBBB", "BBBOAS", "투자등급 경계 기업의 추가금리",
        "기업 자금 부담이 신용등급 낮은 기업을 넘어 투자등급 경계선까지 번지는지 확인",
        "fred", 100.0, "bp", 1.0, "bp", category="credit_breadth",
    ),
    "AOAS": AuxSeries(
        "BAMLC0A3CA", "AOAS", "A등급 기업의 추가금리",
        "기업 자금 부담이 투자등급 경계선을 넘어 투자등급 안쪽까지 넓어지는지 확인",
        "fred", 100.0, "bp", 1.0, "bp", category="credit_breadth",
    ),
    "CPSPREAD": AuxSeries(
        "RIFSPPNA2P2D30NB-RIFSPPNAAD30NB",
        "CPSPREAD",
        "기업 신용도에 따른 단기자금 금리 차이",
        "신용도가 상대적으로 낮은 기업이 높은 기업보다 30일짜리 자금을 빌릴 때 얼마나 더 많은 금리를 내는지 확인",
        "fred", 100.0, "bp", 1.0, "bp",
        category="short_funding", fetch_kind="spread",
        component_series_ids=("RIFSPPNA2P2D30NB", "RIFSPPNAAD30NB"),
    ),
    "NFCI": AuxSeries(
        "NFCI", "NFCI", "미국 금융시장 전반의 자금 사정",
        "여러 시장과 금융기관을 함께 봤을 때 돈을 빌리고 위험을 감수하기가 평소보다 쉬운지 어려운지 참고",
        "fred", 1.0, "지수", 1.0, "지수",
        category="external_reference", use_in_engine=False, layer="external",
        lookback_obs=4, span_guard_days=50, min_obs=100,
    ),
    "STLFSI": AuxSeries(
        "STLFSI4", "STLFSI", "미국 금융시장 전반의 불안",
        "여러 금리·금리 차이·시장 지표가 함께 흔들리는지 외부 종합지표로 참고",
        "fred", 1.0, "지수", 1.0, "지수",
        category="external_reference", use_in_engine=False, layer="external",
        lookback_obs=4, span_guard_days=50, min_obs=100,
    ),
    # v0.5.x 호환과 진단용. BBB를 포함하는 broad IG이므로 범위 엔진의 독립 노드로 사용하지 않는다.
    "IGOAS": AuxSeries(
        "BAMLC0A0CM", "IGOAS", "투자등급 회사채 전체 평균 추가금리",
        "과거 버전 호환과 운영 진단을 위해 수집만 유지",
        "fred", 100.0, "bp", 1.0, "bp",
        category="legacy_reference", use_in_engine=False, visible=False, layer="legacy",
    ),
}

CONFIRM_AUX_ORDER = ["BREAKEVEN", "TERMPREM", "BBBOAS", "AOAS", "CPSPREAD"]
EXTERNAL_AUX_ORDER = ["NFCI", "STLFSI"]
VISIBLE_AUX_ORDER = CONFIRM_AUX_ORDER + EXTERNAL_AUX_ORDER
LEGACY_AUX_ORDER = ["IGOAS"]
AUX_ORDER = VISIBLE_AUX_ORDER + LEGACY_AUX_ORDER
ENGINE_AUX_ORDER = [k for k in CONFIRM_AUX_ORDER if AUX_SERIES[k].use_in_engine]


@dataclass(frozen=True)
class AuxDirectionCfg:
    """확인지표 방향 판정 규칙 기본값.

    방향은 최근 약 1개월 변화의 부호로 정하고, 변화 크기가 현재 확보된 자료 범위의
    |변화| 분포 대비 미미하면 보합으로 누른다. ICE 계열은 현재 공식 FRED 자료 범위가
    약 3년이므로 장기 역사 희귀도로 부르지 않는다.
    """
    lookback_obs: int = 21
    span_guard_days: int = 45
    flat_abs_pct: float = 40.0
    min_obs: int = 250


AUX_DIRECTION = AuxDirectionCfg()
