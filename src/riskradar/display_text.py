"""사용자 화면용 이름과 설명.

내부 key/컬럼명은 데이터 호환성을 위해 유지하고, UI·Telegram·해석 화면에만 쉬운 표현을 쓴다.
"""
from __future__ import annotations

CORE_NAMES = {
    "VIX": "VIX (주식 변동성)",
    "HYOAS": "HY OAS (하이일드 신용스프레드)",
    "T10Y3M": "10년-3개월 금리차",
    "DGS30": "미국 30년물 금리",
    "DGS2": "미국 2년물 금리",
    "DFII10": "10년 실질금리",
}

CORE_SHORT_NAMES = {
    "VIX": "VIX",
    "HYOAS": "HY OAS",
    "T10Y3M": "10년-3개월 금리차",
    "DGS30": "30년물",
    "DGS2": "2년물",
    "DFII10": "10년 실질금리",
}

AUX_NAMES = {
    "BREAKEVEN": "10년 기대인플레이션",
    "IGOAS": "투자등급 신용스프레드",
    "TERMPREM": "10년 Term Premium (Kim-Wright)",
}

AUX_ROLES = {
    "BREAKEVEN": "장기금리 변화에서 인플레이션 보상 방향을 확인",
    "IGOAS": "신용 변화가 하이일드에 국한됐는지 투자등급까지 넓어졌는지 확인",
    "TERMPREM": "장기채 수급·재정 불확실성 등 장기구간 고유 요인을 확인",
}

LABEL_1M = "약 1개월 변화"
LABEL_3M = "약 3개월 변화"
LABEL_5Y = "최근 5년 위치"
LABEL_10Y = "최근 10년 위치"


def core_name(key: str, short: bool = False) -> str:
    mapping = CORE_SHORT_NAMES if short else CORE_NAMES
    return mapping.get(key, key)


def aux_name(key: str) -> str:
    return AUX_NAMES.get(key, key)
