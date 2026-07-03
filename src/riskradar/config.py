"""RiskRadar 설정.

지표별 FRED id, 단위 변환, 상태 임계값을 한 곳에 모은다.
임계값은 전부 여기서 튜닝한다. 코드에 하드코딩하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

APP_TIMEZONE = "Asia/Seoul"
FRED_START_DATE = "1990-01-01"

# point-in-time 백분위 최소 관측치
MIN_OBS_5Y = 500
MIN_OBS_10Y = 1000

# calendar-span guard (긴 공백을 가로지른 변화량은 NaN 처리)
SPAN_GUARD_20OBS_DAYS = 45
SPAN_GUARD_60OBS_DAYS = 120

CHANGE_LOOKBACKS = (20, 60)  # 관측일 개수 기준


@dataclass(frozen=True)
class Series:
    series_id: str
    key: str                # 앱 내부 짧은 키
    display_name: str
    axis: str               # 변동성 / 신용 / 경기사이클 / 장기금리 / 정책금리 / 실질금리
    raw_to_value: float     # FRED raw -> 내부 저장 value 배율
    value_unit: str         # 저장 value 표시 단위
    change_to_bp: float     # 내부 value diff -> change 표시값 배율
    change_unit: str        # change 표시 단위
    percentile_applicable: bool  # 백분위를 상태 판정에 쓰는지
    state_kind: str         # "vix" | "hyoas" | "t10y3m" | "rate"


SERIES: dict[str, Series] = {
    "VIX": Series("VIXCLS", "VIX", "VIX", "변동성",
                  1.0, "index", 1.0, "pt", True, "vix"),
    "HYOAS": Series("BAMLH0A0HYM2", "HYOAS", "HY OAS", "신용",
                    100.0, "bp", 1.0, "bp", True, "hyoas"),
    "T10Y3M": Series("T10Y3M", "T10Y3M", "T10Y3M", "경기사이클",
                     100.0, "bp", 1.0, "bp", False, "t10y3m"),
    "DGS30": Series("DGS30", "DGS30", "30Y", "장기금리",
                    1.0, "%", 100.0, "bp", False, "rate"),
    "DGS2": Series("DGS2", "DGS2", "2Y", "정책금리",
                   1.0, "%", 100.0, "bp", False, "rate"),
    "DFII10": Series("DFII10", "DFII10", "10Y Real", "실질금리",
                     1.0, "%", 100.0, "bp", False, "rate"),
}

SERIES_ORDER = ["VIX", "HYOAS", "T10Y3M", "DGS30", "DGS2", "DFII10"]


# ---- 상태 임계값 ----------------------------------------------------------

@dataclass(frozen=True)
class VixCfg:
    watch_pct10y: float = 75
    stress_pct10y: float = 90
    watch_abs: float = 22
    stress_abs: float = 30
    up_confirm: int = 2
    down_confirm: int = 3


@dataclass(frozen=True)
class HyOasCfg:
    neutral_bp: float = 300
    watch_bp: float = 400
    stress_bp: float = 500
    watch_pct10y: float = 75
    stress_pct10y: float = 90
    up_confirm: int = 2
    down_confirm: int = 3


@dataclass(frozen=True)
class RateCfg:
    # bp 기준 change 임계값
    rise_watch_60: float = 25
    rise_watch_20: float = 20
    rate_shock_60: float = 50
    rate_shock_20: float = 30
    drop_60: float = -50
    drop_20: float = -30
    up_confirm: int = 2
    down_confirm: int = 3


@dataclass(frozen=True)
class T10Y3MCfg:
    strong_pos_bp: float = 10     # >= +10bp
    box_bp: float = 10            # -10 ~ +10bp
    long_inverted_streak: int = 60
    renorm_watch_streak: int = 5   # long_inverted -> re_normalizing
    renorm_confirm_streak: int = 20  # re_normalizing -> re_normalized
    inverted_streak: int = 5
    normal_streak: int = 5
    box_streak: int = 5


@dataclass(frozen=True)
class Thresholds:
    vix: VixCfg = field(default_factory=VixCfg)
    hyoas: HyOasCfg = field(default_factory=HyOasCfg)
    rate: RateCfg = field(default_factory=RateCfg)
    t10y3m: T10Y3MCfg = field(default_factory=T10Y3MCfg)


THRESHOLDS = Thresholds()

STALENESS_BANDS = ((2, "normal"), (5, "delayed"), (10**9, "stale"))
