"""RiskRadar 함께 볼 지표·외부참고 설정.

v0.7.1의 3층 구조
- 핵심 신호: 기존 핵심 6개 + 기업 신용 블록의 HY-BBB 해석 기준
- 확인 지표: 10년 금리 참고 자료(BREAKEVEN/TERMPREM), 신용 범위(BBB/A), 단기자금(CP)
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
        "T10YIE", "BREAKEVEN", "10년 일반·물가연동 국채금리 차이",
        "10년 일반 국채와 물가연동 국채의 금리 차이가 어떻게 움직이는지 참고",
        "fred", 1.0, "%", 100.0, "bp", category="rate_context",
    ),
    "TERMPREM": AuxSeries(
        "THREEFYTP10", "TERMPREM", "10년 장기채 추가 보상",
        "10년 국채를 오래 보유할 때 시장이 요구하는 추가 보상 추정치가 어떻게 움직이는지 참고",
        "fred", 1.0, "%", 100.0, "bp", category="rate_context",
    ),
    "BBBOAS": AuxSeries(
        "BAMLC0A4CBBB", "BBBOAS", "투자등급 경계 기업의 추가 금리",
        "BBB 기업이 국채보다 더 부담하는 추가 금리도 함께 오르는지 확인",
        "fred", 100.0, "bp", 1.0, "bp", category="credit_breadth",
    ),
    "AOAS": AuxSeries(
        "BAMLC0A3CA", "AOAS", "A등급 기업의 추가 금리",
        "A등급 기업이 국채보다 더 부담하는 추가 금리까지 함께 오르는지 확인",
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
        "여러 시장과 금융기관을 함께 봤을 때 미국 금융여건이 빡빡한지 느슨한지 참고",
        "fred", 1.0, "지수", 1.0, "지수",
        category="external_reference", use_in_engine=False, layer="external",
        lookback_obs=4, span_guard_days=50, min_obs=100,
    ),
    "STLFSI": AuxSeries(
        "STLFSI4", "STLFSI", "미국 금융시장 전반의 불안",
        "여러 금리·금리 차이·시장 지표가 함께 불안해지는지 외부 참고 지표로 참고",
        "fred", 1.0, "지수", 1.0, "지수",
        category="external_reference", use_in_engine=False, layer="external",
        lookback_obs=4, span_guard_days=50, min_obs=100,
    ),
    # v0.5.x 호환과 진단용. BBB를 포함하는 broad IG이므로 범위 엔진의 독립 노드로 사용하지 않는다.
    "IGOAS": AuxSeries(
        "BAMLC0A0CM", "IGOAS", "투자등급 회사채 전체 평균 추가 금리",
        "과거 버전 호환과 운영 진단을 위해 수집만 유지",
        "fred", 100.0, "bp", 1.0, "bp",
        category="legacy_reference", use_in_engine=False, visible=False, layer="legacy",
    ),
}

CONFIRM_AUX_ORDER = ["BREAKEVEN", "TERMPREM", "BBBOAS", "AOAS", "CPSPREAD"]
EXTERNAL_AUX_ORDER = ["NFCI", "STLFSI"]
VISIBLE_AUX_ORDER = CONFIRM_AUX_ORDER + EXTERNAL_AUX_ORDER
# 상세 목록과 첫 화면 변화센터는 서로 다른 사용자 표면이다.
# 현재 v0.7.1은 기존 사용자 노출을 보수적으로 유지해 IGOAS만 제외한다.
# 지표 역할이 바뀌어도 변화센터 노출 정책만 독립적으로 조정할 수 있어야 한다.
AUX_CHANGE_CENTER_KEYS = frozenset({
    "BREAKEVEN",
    "TERMPREM",
    "BBBOAS",
    "AOAS",
    "CPSPREAD",
    "NFCI",
    "STLFSI",
})
# Telegram은 30년 금리 변화와 10년 장기채 추가 보상을 따로 보여준다.
TELEGRAM_CONFIRM_AUX_ORDER = ["BREAKEVEN", "BBBOAS", "AOAS", "CPSPREAD"]
LEGACY_AUX_ORDER = ["IGOAS"]
AUX_ORDER = VISIBLE_AUX_ORDER + LEGACY_AUX_ORDER
ENGINE_AUX_ORDER = [k for k in CONFIRM_AUX_ORDER if AUX_SERIES[k].use_in_engine]


@dataclass(frozen=True)
class AuxDirectionCfg:
    """함께 볼 지표 방향 판정 규칙 기본값.

    방향은 최근 약 1개월 변화의 부호로 정하고, 변화 크기가 현재 확보된 자료 범위의
    |변화| 분포 대비 미미하면 보합으로 누른다. ICE 계열은 현재 공식 FRED 자료 범위가
    약 3년이므로 장기 역사 희귀도로 부르지 않는다.
    """
    lookback_obs: int = 21
    span_guard_days: int = 45
    flat_abs_pct: float = 40.0
    min_obs: int = 250


AUX_DIRECTION = AuxDirectionCfg()
