"""Deep per-indicator guide rendering for v0.8.5.

This module is presentation-only: it reads already-stored snapshot values and
static guide metadata, and does not create new thresholds, scores, or signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .display_text import core_name, aux_name, state_name
from .formatting import fmt_change, fmt_pct, fmt_value
from .user_copy import indicator_caution, indicator_summary, movement_label, movement_result_cell

BACKGROUND_NOTE = "RiskRadar가 자동 판정하는 현재 데이터가 아니라 배경을 확인할 때 보는 항목입니다."

CORE_KEYS = {"VIX", "HYOAS", "T10Y3M", "DGS30", "DGS2", "DFII10"}

@dataclass(frozen=True)
class GuideDef:
    meaning: str
    importance: str
    companions: tuple[str, ...] = ()
    companion_notes: dict[str, str] = field(default_factory=dict)
    backgrounds: tuple[str, ...] = ()
    movement: dict[str, str] = field(default_factory=dict)
    cautions: tuple[str, ...] = ()


SPECIFIC_NOTES: dict[str, dict[str, str]] = {
    "HY_BBB": {
        "HYOAS": "HY 자체 추가 금리가 같이 오르는지 확인해 상대 격차와 절대 HY 수준을 분리합니다.",
        "BBBOAS": "HY−BBB의 기준축입니다. BBB도 같이 확대되면 상대 격차만으로 HY 단독 압력을 말하기 어렵습니다.",
        "AOAS": "A등급까지 움직이면 신용 약세가 투자등급 안쪽으로 넓어졌는지 확인할 수 있습니다.",
        "CPSPREAD": "단기 기업자금시장에서도 신용도별 금리 차이가 커지는지 봅니다.",
        "VIX": "주식시장 변동성이 같은 시기에 커지는지 확인합니다.",
        "NFCI": "주간 금융여건 참고 지표가 개별 신용 움직임과 같은 방향인지 봅니다.",
        "STLFSI": "주간 금융시장 스트레스 지표가 회사채·단기자금 움직임과 함께 움직이는지 봅니다.",
    },
    "BBBOAS": {
        "HYOAS": "움직임이 HY에 머무는지 BBB 경계로 내려오는지 비교합니다.",
        "HY_BBB": "HY와 BBB 사이 상대 격차가 커지는지 줄어드는지 확인합니다.",
        "AOAS": "A등급도 같이 움직이면 투자등급 내부로 확산되는지 볼 수 있습니다.",
        "CPSPREAD": "회사채 장기 스프레드와 단기 기업자금 차이가 같이 움직이는지 봅니다.",
        "VIX": "주식시장 변동성이 신용 스프레드 변화와 같은 시기에 움직이는지 확인합니다.",
        "NFCI": "넓은 금융여건 지표가 BBB 움직임과 같은 방향인지 참고합니다.",
        "STLFSI": "넓은 금융시장 스트레스가 투자등급 경계 움직임과 같이 움직이는지 참고합니다.",
        "DGS30": "OAS는 국채 대비 추가 금리이므로 국채금리 환경과 총 회사채 금리를 구분합니다.",
    },
    "AOAS": {
        "BBBOAS": "A보다 낮은 투자등급 경계가 먼저 또는 더 크게 움직이는지 봅니다.",
        "HYOAS": "저신용 회사채 움직임과 우량 투자등급 움직임이 같이 나타나는지 비교합니다.",
        "HY_BBB": "HY와 BBB 사이 상대 격차가 A OAS 변화와 별개로 확대되는지 확인합니다.",
        "CPSPREAD": "단기 기업자금 차이까지 움직이면 회사채 외 funding 압력도 같이 봅니다.",
        "VIX": "주식시장 변동성이 A OAS 변화와 같은 시기에 움직이는지 확인합니다.",
        "NFCI": "주간 금융여건 지표가 우량 투자등급 움직임과 같은 방향인지 참고합니다.",
        "STLFSI": "주간 스트레스 지표가 A·BBB·HY 움직임과 겹치는지 봅니다.",
        "DGS30": "OAS와 국채금리 환경을 분리해 총 회사채 금리를 단정하지 않도록 합니다.",
    },
    "CPSPREAD": {
        "HYOAS": "단기 funding 차이가 저신용 회사채 스프레드와 같이 움직이는지 봅니다.",
        "BBBOAS": "단기자금 압력이 투자등급 경계 회사채에도 같이 나타나는지 비교합니다.",
        "AOAS": "더 우량한 투자등급까지 같은 방향인지 확인합니다.",
        "VIX": "주식시장 변동성이 단기자금 압력과 같은 시기에 움직이는지 봅니다.",
        "NFCI": "전반적 금융여건이 단기자금 차이와 같은 방향인지 참고합니다.",
        "STLFSI": "전반적 금융시장 스트레스가 단기자금 신호와 겹치는지 참고합니다.",
    },
    "DGS30": {
        "DFII10": "물가 영향을 뺀 장기금리 압력이 명목 장기금리와 같은 방향인지 봅니다.",
        "BREAKEVEN": "일반·물가연동 국채금리 차이가 명목 장기금리 움직임과 같이 움직이는지 봅니다.",
        "TERMPREM": "장기채 보상 추정치가 장기금리와 같은 방향인지 별도 참고축으로 봅니다.",
        "DGS2": "단기금리와 장기금리가 함께 움직이는지 또는 벌어지는지 비교합니다.",
        "T10Y3M": "곡선 관계가 더 가팔라지는지 또는 평평해지는지 확인합니다.",
    },
    "DGS2": {"DGS30": "단기와 장기 금리가 같은 방향인지 비교합니다.", "T10Y3M": "단기금리 변화가 곡선 관계를 어떻게 바꾸는지 봅니다.", "DFII10": "단기금리 움직임과 물가조정 장기금리 압력을 나눠 봅니다.", "BREAKEVEN": "물가 관련 금리 차이가 단기금리 움직임과 다른지 봅니다."},
    "DFII10": {"DGS30": "물가 영향을 뺀 금리 압력이 명목 장기금리와 같이 움직이는지 봅니다.", "BREAKEVEN": "물가 관련 금리 차이가 실질 쪽 움직임을 보강하거나 상쇄하는지 봅니다.", "TERMPREM": "장기채 보상 추정치가 물가조정 금리 압력과 같은 방향인지 봅니다.", "DGS2": "단기금리 움직임과 장기 실질 압력을 분리합니다."},
    "T10Y3M": {"DGS2": "단기금리 변화가 역전 또는 해소 방향에 미치는 현재 기여를 봅니다.", "DGS30": "장기금리 변화가 곡선 관계를 바꾸는지 확인합니다.", "DFII10": "장기 실질 압력이 곡선 변화와 같이 움직이는지 봅니다.", "BREAKEVEN": "물가 관련 금리 차이가 장기금리 쪽 배경인지 참고합니다."},
    "BREAKEVEN": {"DFII10": "명목 장기금리 안에서 물가조정 금리와 금리차가 같은 방향인지 봅니다.", "DGS30": "명목 장기금리가 일반·물가연동 금리차와 같이 움직이는지 봅니다.", "TERMPREM": "장기채 보상 추정치와 물가 관련 금리차를 분리합니다."},
    "TERMPREM": {"DGS30": "장기채 보상 추정치가 명목 장기금리와 같은 방향인지 봅니다.", "DFII10": "실질 장기금리 압력과 장기채 보상 추정치를 구분합니다.", "BREAKEVEN": "물가 관련 금리차와 term premium 움직임을 분리합니다.", "DGS2": "단기 정책금리 민감 구간과 장기채 보상 추정치를 비교합니다."},
    "HYOAS": {"BBBOAS": "HY 움직임이 투자등급 경계로 이어지는지 봅니다.", "AOAS": "우량 투자등급까지 움직이는지 확인합니다.", "HY_BBB": "HY와 BBB 사이 상대 격차로 HY 집중 여부를 봅니다.", "CPSPREAD": "단기 기업자금시장도 같이 긴장되는지 확인합니다.", "VIX": "주식시장 변동성이 저신용 회사채 움직임과 같은 시기에 움직이는지 봅니다.", "NFCI": "넓은 금융여건 참고 지표와 비교합니다.", "STLFSI": "넓은 금융시장 스트레스 참고 지표와 비교합니다."},
    "VIX": {"HYOAS": "주식시장 변동성과 저신용 회사채 스프레드가 같이 움직이는지 봅니다.", "BBBOAS": "변동성 변화가 투자등급 경계 움직임과 겹치는지 봅니다.", "CPSPREAD": "단기 funding 차이와 변동성 움직임을 비교합니다.", "NFCI": "넓은 금융여건 지표와 변동성을 비교합니다.", "STLFSI": "넓은 스트레스 지표와 변동성을 비교합니다."},
    "NFCI": {"HYOAS": "복합 금융여건과 저신용 스프레드를 비교합니다.", "BBBOAS": "복합 금융여건과 투자등급 경계 스프레드를 비교합니다.", "AOAS": "복합 금융여건과 우량 투자등급 스프레드를 비교합니다.", "CPSPREAD": "복합 금융여건과 단기 funding 차이를 비교합니다.", "VIX": "복합 금융여건과 주식 변동성을 비교합니다."},
    "STLFSI": {"HYOAS": "복합 스트레스와 저신용 스프레드를 비교합니다.", "BBBOAS": "복합 스트레스와 투자등급 경계 스프레드를 비교합니다.", "AOAS": "복합 스트레스와 우량 투자등급 스프레드를 비교합니다.", "CPSPREAD": "복합 스트레스와 단기 funding 차이를 비교합니다.", "VIX": "복합 스트레스와 주식 변동성을 비교합니다."},
}

def _notes(owner: str, items: tuple[str, ...]) -> dict[str, str]:
    specific = SPECIFIC_NOTES.get(owner, {})
    return {k: specific.get(k, "현재 지표와 같은 시기에 움직이는지 확인합니다.") for k in items}

GUIDES: dict[str, GuideDef] = {
    "HY_BBB": GuideDef(
        "HY OAS와 BBB OAS의 차이입니다. HY−BBB가 커지면 저신용 기업과 투자등급 경계 기업 사이의 국채 대비 추가 금리 격차가 벌어집니다.",
        "회사채 추가 금리 확대가 HY에 더 집중되는지, 아니면 BBB·A·단기자금까지 넓어지는지 묻습니다.",
        ("HYOAS", "BBBOAS", "AOAS", "CPSPREAD", "VIX", "NFCI", "STLFSI"),
        _notes("HY_BBB", ("HYOAS", "BBBOAS", "AOAS", "CPSPREAD", "VIX", "NFCI", "STLFSI")),
        ("FOMC와 정책 환경", "넓은 국채금리 환경"),
        cautions=("HY−BBB는 두 신용 구간의 상대 격차이며 절대 스트레스 수준 자체는 아닙니다.", "같은 기간 움직임은 인과관계나 선행 순서를 증명하지 않습니다."),
    ),
    "BBBOAS": GuideDef(
        "BBB OAS는 BBB 기업이 비슷한 만기의 국채보다 추가로 부담하는 금리 격차입니다.",
        "저신용 시장의 움직임이 투자등급 경계까지 닿았는지 확인합니다.",
        ("HYOAS", "HY_BBB", "AOAS", "CPSPREAD", "VIX", "NFCI", "STLFSI", "DGS30"),
        _notes("BBBOAS", ("HYOAS", "HY_BBB", "AOAS", "CPSPREAD", "VIX", "NFCI", "STLFSI", "DGS30")),
        ("넓은 국채금리 환경",),
        cautions=("OAS 상승은 국채 대비 추가 금리 확대이지, 회사채 총수익률 상승을 단독으로 증명하지 않습니다.",),
    ),
    "AOAS": GuideDef(
        "A OAS는 A등급 기업이 비슷한 만기의 국채보다 추가로 부담하는 금리 격차입니다.",
        "스프레드 확대가 BBB 경계를 넘어 더 우량한 투자등급 회사채까지 넓어졌는지 확인합니다.",
        ("BBBOAS", "HYOAS", "HY_BBB", "CPSPREAD", "VIX", "NFCI", "STLFSI", "DGS30"),
        _notes("AOAS", ("BBBOAS", "HYOAS", "HY_BBB", "CPSPREAD", "VIX", "NFCI", "STLFSI", "DGS30")),
        ("FOMC와 정책 환경", "국채금리 환경"),
        cautions=("A OAS는 국채 대비 추가 금리이며 회사채의 총 금리가 아닙니다. 국채금리가 따로 움직이면 실제 회사채 금리의 방향은 달라질 수 있습니다.",),
    ),
    "CPSPREAD": GuideDef(
        "CP Spread는 신용도가 낮은 기업의 30일 단기자금 금리와 우량 기업의 단기자금 금리 차이입니다.",
        "단기 기업자금 조달에서도 신용도별 금리 차이가 커지는지 봅니다.",
        ("HYOAS", "BBBOAS", "AOAS", "VIX", "NFCI", "STLFSI"),
        _notes("CPSPREAD", ("HYOAS", "BBBOAS", "AOAS", "VIX", "NFCI", "STLFSI")),
        ("FOMC와 정책 환경", "RiskRadar가 수집하지 않는 머니마켓·펀딩시장 이벤트"),
        cautions=("CP는 단기자금시장 지표라 회사채 OAS와 만기와 시장 구조가 다릅니다.",),
    ),
    "DGS30": GuideDef(
        "미국 30년 국채의 명목 수익률입니다. 상승은 장기 국채금리가 높아졌다는 뜻입니다.",
        "장기 할인율과 장기 차입금리 환경이 최근 높아지는지 낮아지는지 확인합니다.",
        ("DFII10", "BREAKEVEN", "TERMPREM", "DGS2", "T10Y3M"),
        _notes("DGS30", ("DFII10", "BREAKEVEN", "TERMPREM", "DGS2", "T10Y3M")),
        ("FOMC와 정책 가이던스", "국채 수급과 발행 배경"),
        cautions=("30Y 같은만기 물가조정 금리·물가 관련 금리 차이 분해와 10Y Term Premium은 서로 다른 참고축입니다.",),
    ),
    "DGS2": GuideDef("미국 2년 국채금리입니다. 단기 정책금리 기대에 민감한 명목 금리입니다.", "단기금리가 장기금리와 같은 방향인지, 단기 구간만 다르게 움직이는지 확인합니다.", ("DGS30", "T10Y3M", "DFII10", "BREAKEVEN"), _notes("DGS2", ("DGS30", "T10Y3M", "DFII10", "BREAKEVEN")), ("FOMC 금리 결정", "정책 가이던스"), cautions=("2Y만으로 향후 FOMC 결정을 단정하지 않습니다.",)),
    "DFII10": GuideDef("물가 영향을 뺀 10년 금리입니다. 상승은 물가 관련 금리 차이를 제외한 장기 금리 압력이 커졌다는 뜻입니다.", "물가 영향을 뺀 장기금리 압력이 일반 장기금리와 함께 움직이는지 확인합니다.", ("DGS30", "BREAKEVEN", "TERMPREM", "DGS2"), _notes("DFII10", ("DGS30", "BREAKEVEN", "TERMPREM", "DGS2")), ("FOMC 정책 환경", "RiskRadar가 직접 분류하지 않는 성장·물가 배경"), cautions=("TIPS 유동성 등으로 물가 영향을 뺀 금리 해석에는 시장구조 영향이 섞일 수 있습니다.",)),
    "T10Y3M": GuideDef("10년 국채금리에서 3개월 국채금리를 뺀 값입니다. 낮아지면 단기금리가 장기금리보다 상대적으로 높아집니다.", "곡선이 더 역전되는지 또는 역전이 완화되는지 봅니다.", ("DGS2", "DGS30", "DFII10", "BREAKEVEN"), _notes("T10Y3M", ("DGS2", "DGS30", "DFII10", "BREAKEVEN")), ("FOMC 정책 환경", "경기침체 해석은 조건부 배경으로만 확인"), cautions=("10Y−3M을 경기침체 확률로 바꾸지 않습니다.",)),
    "BREAKEVEN": GuideDef("10년 일반 국채와 물가연동국채 금리의 차이입니다. 기대 인플레이션뿐 아니라 인플레이션 위험보상과 유동성 영향도 포함합니다.", "명목 장기금리 움직임에 일반·물가연동 국채금리 차이가 함께 움직이는지 봅니다.", ("DFII10", "DGS30", "TERMPREM"), _notes("BREAKEVEN", ("DFII10", "DGS30", "TERMPREM")), ("물가 지표와 인플레이션 위험 배경", "FOMC의 물가 관련 커뮤니케이션"), cautions=("10Y Breakeven은 순수 기대 인플레이션이 아닙니다.",)),
    "TERMPREM": GuideDef("10Y Term Premium은 장기채를 오래 보유하는 데 필요한 추가 보상에 대한 모델 추정치입니다.", "장기 듀레이션 보상이 장기금리를 끌어올리는 요인으로 움직이는지 확인합니다.", ("DGS30", "DFII10", "BREAKEVEN", "DGS2"), _notes("TERMPREM", ("DGS30", "DFII10", "BREAKEVEN", "DGS2")), ("국채 수급", "듀레이션 위험", "정책 불확실성"), cautions=("10Y Term Premium은 모델 추정치이며 저장된 30Y 같은만기 분해에 직접 더하는 항목이 아닙니다.",)),
    "HYOAS": GuideDef("HY OAS는 저신용 회사채가 비슷한 만기의 국채보다 추가로 부담하는 금리 격차입니다.", "HY 수준이 높은지와 최근 방향이 확대인지 축소인지 분리해 봅니다.", ("BBBOAS", "AOAS", "HY_BBB", "CPSPREAD", "VIX", "NFCI", "STLFSI"), _notes("HYOAS", ("BBBOAS", "AOAS", "HY_BBB", "CPSPREAD", "VIX", "NFCI", "STLFSI")), (), cautions=("HY 수준 상태와 신용 에피소드 상태는 같은 라벨 체계가 아닙니다.", "OAS는 총 회사채 금리가 아니라 국채 대비 추가 금리입니다.")),
    "VIX": GuideDef("VIX는 S&P 500 옵션 가격에 반영된 주식시장 예상 변동성 지수입니다.", "주식시장 변동성이 회사채 스프레드와 함께 움직이는지, 또는 변동성만 따로 움직이는지 봅니다.", ("HYOAS", "BBBOAS", "CPSPREAD", "NFCI", "STLFSI"), _notes("VIX", ("HYOAS", "BBBOAS", "CPSPREAD", "NFCI", "STLFSI")), (), cautions=("VIX 상승은 신용 스트레스의 증거가 아니라 주식시장 변동성의 변화입니다.",)),
    "NFCI": GuideDef("NFCI는 여러 금융시장과 금융기관 지표를 묶은 주간 외부 참고 지표이며 금융여건을 보여줍니다.", "개별 신용·변동성 지표가 넓은 금융여건 지표와 함께 움직이는지 참고합니다.", ("HYOAS", "BBBOAS", "AOAS", "CPSPREAD", "VIX"), _notes("NFCI", ("HYOAS", "BBBOAS", "AOAS", "CPSPREAD", "VIX")), (), cautions=("주간 복합지표라 관측일이 다를 수 있고 구성요소 중복과 수정 위험이 있습니다. 엔진 입력이 아니므로 RiskRadar의 핵심 상태를 직접 바꾸지 않으며 새 종합 점수로 쓰지 않습니다.",)),
    "STLFSI": GuideDef("STLFSI는 금융여건과 여러 금융시장 스트레스 지표를 묶은 주간 외부 참고 지표입니다.", "개별 신용·변동성 지표가 넓은 스트레스 지표와 함께 움직이는지 참고합니다.", ("HYOAS", "BBBOAS", "AOAS", "CPSPREAD", "VIX"), _notes("STLFSI", ("HYOAS", "BBBOAS", "AOAS", "CPSPREAD", "VIX")), (), cautions=("주간 복합지표라 관측일이 다를 수 있고 구성요소 중복과 수정 위험이 있습니다. 엔진 입력이 아니므로 RiskRadar의 핵심 상태를 직접 바꾸지 않으며 새 종합 점수로 쓰지 않습니다.",)),
}


def _as_float(x: Any) -> float | None:
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _find(df: pd.DataFrame | None, key: str):
    if df is None or df.empty or "key" not in df.columns:
        return None
    hit = df.loc[df["key"].astype(str) == key]
    return None if hit.empty else hit.iloc[-1]


def _dir_from_change(value: Any) -> str:
    v = _as_float(value)
    if v is None:
        return "확인 불가"
    if v > 0:
        return "상승"
    if v < 0:
        return "하락"
    return "보합"


def _name(key: str) -> str:
    if key == "HY_BBB":
        return "HY−BBB"
    return core_name(key, short=True) if key in CORE_KEYS else aux_name(key)


def _hy_bbb_row(data_quality: dict | None) -> dict[str, Any] | None:
    lens = (((data_quality or {}).get("credit_episode") or {}).get("lens") or {})
    if not lens:
        return None
    return {"key": "HY_BBB", "latest_value": lens.get("latest_value_bp"), "value_unit": "bp", "change_1m": lens.get("change_1m_bp"), "change_unit": "bp", "direction": lens.get("direction") or _dir_from_change(lens.get("change_1m_bp")), "state": lens.get("label"), "latest_date": lens.get("observed_date") or lens.get("latest_date") or "신용 에피소드 렌즈 기준"}


def _locate(key: str, *, matrix: pd.DataFrame | None, aux_df: pd.DataFrame | None, data_quality: dict | None = None):
    if key == "HY_BBB":
        return _hy_bbb_row(data_quality)
    return _find(matrix, key) if key in CORE_KEYS else _find(aux_df, key)


def _row_bits(key: str, row: Any) -> tuple[str, str, str, str, str]:
    if row is None:
        return ("현재 확인 불가", "현재 확인 불가", "현재 확인 불가", "확인 불가", "현재 확인 불가")
    r = pd.Series(row)
    if key in CORE_KEYS:
        val = fmt_value(r.get("latest_value"), str(r.get("value_unit", "")))
        chg = fmt_change(r.get("change_20obs"), str(r.get("change_unit", "")))
        st = state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=key)
        date = str(r.get("latest_observed_date") or r.get("latest_date") or "확인 불가")
        direction = str(r.get("direction") or r.get("direction_label") or "")
        if direction in {"판정불가", "확인 불가", "nan", "None", ""}:
            direction = _dir_from_change(r.get("change_20obs"))
    else:
        val = fmt_value(r.get("latest_value"), str(r.get("value_unit", "")))
        chg = fmt_change(r.get("change_1m"), str(r.get("change_unit", "")))
        st = str(r.get("state") or r.get("direction") or "확인 불가")
        date = str(r.get("latest_date") or r.get("latest_observed_date") or "확인 불가")
        stale = str(r.get("staleness_label") or "")
        if key in {"NFCI", "STLFSI"}:
            date = f"주간 관측 {date}"
        if stale and stale not in {"nan", "None", ""}:
            date = f"{date} · {stale}"
        direction = str(r.get("direction") or r.get("direction_label") or "")
        if direction in {"판정불가", "확인 불가", "nan", "None", ""}:
            direction = _dir_from_change(r.get("change_1m"))
        if stale == "stale":
            st = "현재 확인 불가(오래된 자료)"
            direction = "확인 불가"
    return val, chg, st, date, direction


def current_data_section(key: str, row: Any, *, data_quality: dict | None = None) -> str:
    if key == "HY_BBB" and row is None:
        row = _hy_bbb_row(data_quality)
    val, chg, st, date, _ = _row_bits(key, row)
    lines = ["## 현재 데이터", "", "| 항목 | 현재 |", "|---|---|", f"| 최신값 | {val} |", f"| 약 1개월 변화 | {chg} |", f"| 현재 상태/방향 | {st} |", f"| 관측일·자료상태 | {date} |"]
    if row is not None and key in CORE_KEYS:
        r = pd.Series(row)
        lines.extend([
            f"| 약 3개월 변화 | {fmt_change(r.get('change_60obs'), str(r.get('change_unit', '')))} |",
            f"| 최근 5년 중 현재 위치 | {fmt_pct(r.get('percentile_5y'))} |",
            f"| 최근 10년 중 현재 위치 | {fmt_pct(r.get('percentile_10y'))} |",
        ])
    return "\n".join(lines)

def companion_results(key: str, *, matrix: pd.DataFrame | None, aux_df: pd.DataFrame | None, data_quality: dict | None = None) -> str:
    guide = GUIDES.get(key)
    rows = ["## 현재 함께 보는 지표의 결과", "", "| 지표 | 현재 | 최근 변화 | 상태/방향 | 관측일 |", "|---|---:|---:|---|---|"]
    if not guide or not guide.companions:
        return "\n".join(rows + ["| 현재 확인 불가 | 현재 확인 불가 | 현재 확인 불가 | 현재 확인 불가 | 현재 확인 불가 |"])
    for other in guide.companions:
        val, chg, st, date, _ = _row_bits(other, _locate(other, matrix=matrix, aux_df=aux_df, data_quality=data_quality))
        rows.append(f"| {_name(other)} | {val} | {chg} | {st} | {date} |")
    return "\n".join(rows)


def combo_reading(key: str, row: Any, *, matrix: pd.DataFrame | None, aux_df: pd.DataFrame | None, data_quality: dict | None = None) -> str:
    guide = GUIDES.get(key)
    _, _, _, _, main_dir = _row_bits(key, row if not (key == "HY_BBB" and row is None) else _hy_bbb_row(data_quality))
    dirs = []
    missing = 0
    for other in (guide.companions if guide else ()):
        _, _, _, _, d = _row_bits(other, _locate(other, matrix=matrix, aux_df=aux_df, data_quality=data_quality))
        if d == "확인 불가":
            missing += 1
        else:
            dirs.append(d)
    if main_dir == "확인 불가" or missing:
        text = "일부 현재값을 확인할 수 없어 조합 해석은 제한적입니다. 빠진 지표를 다른 지표로 대신 판정하지 않습니다."
    elif main_dir == "보합" and all(d == "보합" for d in dirs):
        text = "주요 지표가 모두 제한적이거나 보합에 가까워 한 방향의 움직임으로 묶지 않습니다."
    elif dirs and sum(d == main_dir for d in dirs) >= max(1, len(dirs) // 2 + 1):
        text = f"주요 동반 지표 다수가 {main_dir} 방향입니다. 이는 같은 기간 여러 시장 지표가 함께 움직였다는 뜻이지 인과관계나 선행 순서를 뜻하지 않습니다."
    elif dirs and all(d != main_dir for d in dirs):
        text = f"주 지표는 {main_dir}이지만 동반 지표들은 같은 방향이 아닙니다. 단독 움직임 가능성을 열어 두고 종합 위험 라벨로 합치지 않습니다."
    else:
        text = "동반 지표의 방향이 갈립니다. 어느 한 설명으로 단정하지 않고 신용·금리·변동성 영역을 나눠 봅니다."
    return "## 지금 조합을 어떻게 읽는가\n\n" + text



def rate_composition_section(rate_summary: dict | None) -> str:
    summary = rate_summary or {}
    latest = summary.get("latest") or {}
    primary = summary.get("primary") or {}
    if summary.get("status") != "ok" or not latest:
        return "## 30Y 동일 만기 분해\n\n현재 30Y 동일 만기 분해 결과를 확인할 수 없습니다."
    rows = [
        "## 30Y 동일 만기 분해",
        "",
        "| 항목 | 현재 | 최근 변화 | 관측 구간 |",
        "|---|---:|---:|---|",
    ]
    period = f"{primary.get('start_date', '확인 불가')} → {primary.get('end_date', summary.get('observation_date', '확인 불가'))}"
    items = [("30Y 명목금리", "DGS30"), ("30Y 실질금리", "DFII30"), ("30Y 일반·물가연동 국채금리 차이", "INFLCOMP30")]
    for label, comp_key in items:
        value = latest.get(comp_key)
        change = primary.get(f"{comp_key}_change_bp")
        rows.append(f"| {label} | {fmt_value(value, '%')} | {fmt_change(change, 'bp')} | {period} |")
    rows.append("")
    rows.append("10Y Breakeven과 10Y Term Premium은 이 30Y 동일 만기 분해에 직접 더하는 값이 아니라 별도 참고축입니다.")
    return "\n".join(rows)

def guide_markdown(key: str, row: Any, *, matrix: pd.DataFrame | None = None, aux_df: pd.DataFrame | None = None, data_quality: dict | None = None, rate_summary: dict | None = None, one_line: str = "") -> str:
    guide = GUIDES.get(key) or GuideDef(indicator_summary(key), "RiskRadar의 현재 상태와 최근 방향을 분리해 확인합니다.")
    comp_lines = ["## 같이 볼 지표와 배경", "", "### RiskRadar current data"]
    if guide.companions:
        for c in guide.companions:
            comp_lines.append(f"- **{_name(c)}**: {guide.companion_notes.get(c, '함께 움직이는지 확인합니다.')}")
    else:
        comp_lines.append("- 현재 지정된 동반 지표가 없습니다.")
    comp_lines += ["", "### Background to check separately"]
    if guide.backgrounds:
        for b in guide.backgrounds:
            comp_lines.append(f"- **{b}**: {BACKGROUND_NOTE}")
    else:
        comp_lines.append(f"- 별도 거시 배경: {BACKGROUND_NOTE}")
    caution_items = list(guide.cautions)
    base_caution = indicator_caution(key)
    if base_caution:
        caution_items.append(base_caution)
    caution_items.append("같은 기간 움직임은 인과관계나 선행·후행 관계를 증명하지 않습니다.")
    sections = [
        "<!-- ## 지금 데이터로 보면 -->",
        current_data_section(key, row, data_quality=data_quality),
        "## 이 지표가 뜻하는 것\n\n" + guide.meaning,
        "## 왜 중요한가\n\n" + guide.importance,
        "\n".join(comp_lines),
        companion_results(key, matrix=matrix, aux_df=aux_df, data_quality=data_quality),
        rate_composition_section(rate_summary) if key == "DGS30" else "",
        combo_reading(key, row, matrix=matrix, aux_df=aux_df, data_quality=data_quality),
        "## 움직임별 해석\n\n" + "\n".join([
            f"- **{movement_label(key, 'up')}**: {movement_result_cell(key, 'up')}",
            f"- **{movement_label(key, 'down')}**: {movement_result_cell(key, 'down')}",
            f"- **{movement_label(key, 'flat')}**: {movement_result_cell(key, 'flat')}",
            "- **동반 지표와 같은 방향**: 여러 시장 구간이 같은 기간 움직였다는 뜻으로 읽되 원인으로 단정하지 않습니다.",
            "- **동반 지표와 다른 방향**: 주 지표 고유 움직임일 수 있으므로 전체 위험 라벨로 합치지 않습니다.",
        ]),
        "## 주의사항\n\n" + "\n".join(f"- {c}" for c in dict.fromkeys(caution_items)),
        "<!-- ### 무엇을 보나 -->\n<!-- ### 지금 이렇게 읽습니다 -->\n<!-- ### 같이 볼 지표 -->\n<!-- ### 움직임별 결과 -->\n<!-- 결과적으로 볼 수 있는 변화 -->\n<!-- ## 다음에 같이 볼 것 -->",
    ]
    return "\n\n".join(part for part in sections if part)
