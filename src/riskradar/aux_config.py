"""RiskRadar v0.4.0 — 보조지표(2층) 설정.

원칙:
- 핵심 6개(1층)와 분리한다.
- 보조지표는 3축 개수·종합상태에 넣지 않는다. (원인 확인 전용)
- 출력은 방향(상승/하락/보합/판정불가)뿐. 상태 라벨을 새로 만들지 않는다.
- 3개 모두 FRED 소스로 통일한다. (별도 소스 파싱 의존 제거)

컷은 전부 C등급 운영 규칙이다. 학술 기준이 아니라 과거 국면으로 조정하는 값이다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuxSeries:
    series_id: str
    key: str
    display_name: str
    role: str            # 무엇을 확인하는 지표인지
    source: str          # "fred"
    raw_to_value: float  # FRED raw -> 내부 저장 value 배율
    value_unit: str      # 저장 value 표시 단위
    change_to_disp: float  # value diff -> 표시 change 배율
    change_unit: str     # change 표시 단위


# 3개 모두 FRED. Term Premium은 ACM(NY Fed xls) 대신 Kim-Wright THREEFYTP10(FRED, 일별)로 통일.
AUX_SERIES: dict[str, AuxSeries] = {
    "BREAKEVEN": AuxSeries(
        "T10YIE", "BREAKEVEN", "시장 기반 10년 물가전망",
        "장기금리 변화에 물가 전망이 얼마나 함께 움직였는지 확인",
        "fred", 1.0, "%", 100.0, "bp",
    ),
    "IGOAS": AuxSeries(
        "BAMLC0A0CM", "IGOAS", "우량 회사채 추가금리",
        "회사채 위험이 저신용 기업에만 있는지 더 넓게 퍼졌는지 확인",
        "fred", 100.0, "bp", 1.0, "bp",
    ),
    "TERMPREM": AuxSeries(
        "THREEFYTP10", "TERMPREM", "장기채 추가보상",
        "장기채를 오래 보유할 때 시장이 요구하는 추가 보상이 변했는지 확인",
        "fred", 1.0, "%", 100.0, "bp",
    ),
}

AUX_ORDER = ["BREAKEVEN", "IGOAS", "TERMPREM"]


@dataclass(frozen=True)
class AuxDirectionCfg:
    """보조지표 방향 판정 규칙 (C등급 초기값).

    방향은 최근 1개월 변화의 '부호'로 정하고,
    변화 크기가 자기 과거 |변화| 분포 대비 미미하면 보합으로 눌러 노이즈를 막는다.
    (등속 추세를 보합으로 놓치지 않기 위해 백분위-부호 방식이 아니라 부호+유의성 방식을 쓴다.)
    """
    lookback_obs: int = 21      # 약 1개월(거래일) 변화
    span_guard_days: int = 45   # lookback을 가로지른 달력 공백이 크면 방향 보류
    flat_abs_pct: float = 40.0  # 최신 |변화|가 과거 |변화| 분포 이 백분위 미만이면 보합
    min_obs: int = 250          # 분포 최소 관측치(약 1년) 미만이면 판정불가


AUX_DIRECTION = AuxDirectionCfg()
