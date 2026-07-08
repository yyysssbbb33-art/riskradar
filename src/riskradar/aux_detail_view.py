"""함께 볼 지표·외부참고의 현재값 연결 상세 설명.

보이는 7개 지표를 현재 데이터와 고정 상세카드에 연결한다.
판정 규칙을 새로 만들지 않고 저장된 방향·수준·다른 지표의 현재값을 설명한다.
"""
from __future__ import annotations

import pandas as pd

from .aux_interpretation_cards import get_aux_interpretation_card
from .display_text import aux_name, core_name, plain_language, state_name
from .formatting import fmt_change, fmt_pct, fmt_value

_FRESHNESS = {
    "normal": "최신",
    "delayed": "업데이트가 조금 늦음",
    "stale": "오래된 자료 · 현재 해석에서 제외",
}
_DIR_TEXT = {
    "상승": "상승",
    "하락": "하락",
    "보합": "뚜렷한 변화 없음",
    "확인 불가": "확인 불가",
    "판정불가": "확인 불가",
}

_COMPANIONS: dict[str, tuple[str, ...]] = {
    "BREAKEVEN": ("DGS30", "DFII10", "TERMPREM"),
    "TERMPREM": ("DGS30", "DGS2", "BREAKEVEN", "DFII10"),
    "BBBOAS": ("HYOAS", "AOAS", "CPSPREAD"),
    "AOAS": ("HYOAS", "BBBOAS", "CPSPREAD", "VIX"),
    "CPSPREAD": ("HYOAS", "BBBOAS", "AOAS", "NFCI", "STLFSI"),
    "NFCI": ("VIX", "HYOAS", "CPSPREAD", "STLFSI"),
    "STLFSI": ("VIX", "HYOAS", "CPSPREAD", "NFCI"),
}

_BRANCHES: dict[str, tuple[str, str, str]] = {
    "BREAKEVEN": (
        "오르면 10년 일반 국채와 물가연동 국채의 금리 차이가 커집니다. 30년 금리 변화는 금리 탭의 ‘30년 금리’에서 따로 봅니다.",
        "내리면 10년 일반 국채와 물가연동 국채의 금리 차이가 줄어듭니다. 이 변화만으로 다른 만기의 금리 움직임을 설명하지 않습니다.",
        "뚜렷한 움직임이 없으면 10년 일반 국채와 물가연동 국채의 금리 차이도 최근 크게 달라지지 않았다는 뜻입니다.",
    ),
    "TERMPREM": (
        "오르면 10년 장기채를 오래 보유하기 위해 요구되는 추가 보상 추정치가 커집니다. 이 값은 30년 금리 변화에 더하는 항목이 아닙니다.",
        "내리면 10년 장기채 추가 보상 추정치가 줄어듭니다. 30년 금리와 같은 방향이어도 직접 원인으로 단정하지 않습니다.",
        "뚜렷한 움직임이 없으면 10년 장기채 추가 보상 추정치도 최근 크게 달라지지 않았다는 뜻입니다.",
    ),
    "BBBOAS": (
        "오르면 기업 신용 부담이 투자등급 경계선까지 이어지는지 봅니다. A등급과 단기 기업자금도 같이 움직이면 변화 범위가 더 넓습니다.",
        "내리면 투자등급 경계선의 부담이 줄어드는 방향입니다. HY만 오르면 변화가 신용등급 낮은 기업에 더 집중됐다는 설명과 잘 맞습니다.",
        "뚜렷한 움직임이 없으면 현재 회사채 부담 변화가 BBB까지 이어졌다고 보기는 어렵습니다.",
    ),
    "AOAS": (
        "오르면 기업 자금 부담이 투자등급 경계선을 넘어 A등급 기업까지 넓어지는 방향입니다. HY와 BBB도 같이 움직이면 변화 범위가 넓다는 설명이 강해집니다.",
        "내리면 투자등급 안쪽까지 부담이 넓어졌다는 설명은 약해집니다. HY나 BBB만 오르면 변화가 더 낮은 신용등급에 집중됐을 수 있습니다.",
        "뚜렷한 움직임이 없으면 회사채 부담이 투자등급 안쪽까지 이어졌다고 볼 근거는 아직 약합니다.",
    ),
    "CPSPREAD": (
        "오르면 신용도가 낮은 기업이 단기 자금을 빌릴 때 상대적으로 더 큰 금리 부담을 지는 방향입니다. 회사채 추가 금리도 같이 오르면 기업 자금 부담이 여러 만기로 이어지는지 봅니다.",
        "내리면 단기 기업자금시장의 신용도 차별이 줄어드는 방향입니다. 회사채가 움직여도 단기시장까지 이어졌다는 설명은 약해질 수 있습니다.",
        "뚜렷한 움직임이 없으면 현재 변화가 단기 기업자금시장까지 이어졌다고 보기는 어렵습니다.",
    ),
    "NFCI": (
        "오르면 미국 전반의 금융여건이 어려워지는 방향입니다. RiskRadar의 여러 시장 지표도 같은 방향이면 외부 참고 지표와 같은 그림인지 봅니다.",
        "내리면 전반적인 자금 사정이 느슨해지는 방향입니다. 특정 시장만 움직인다면 변화가 넓게 이어지지 않았을 가능성을 봅니다.",
        "뚜렷한 움직임이 없으면 넓은 금융여건이 최근 크게 바뀌었다는 외부 확인은 약합니다.",
    ),
    "STLFSI": (
        "오르면 여러 금융시장의 불안이 함께 높아지는 방향입니다. VIX·회사채·단기 기업자금 지표도 같은 방향이면 더 넓은 시장 불안이라는 설명과 잘 맞습니다.",
        "내리면 금융시장 전반의 불안이 줄어드는 방향입니다. 특정 지표만 상승한다면 변화가 그 시장에 더 집중됐을 수 있습니다.",
        "뚜렷한 움직임이 없으면 여러 시장이 함께 불안해졌다는 외부 참고는 아직 약합니다.",
    ),
}


def _find(df: pd.DataFrame | None, key: str):
    if df is None or df.empty or "key" not in df.columns:
        return None
    hit = df.loc[df["key"].astype(str) == key]
    return None if hit.empty else hit.iloc[-1]


def _aux_level_text(key: str, row) -> str:
    pct = row.get("level_pct")
    if pct is None or pd.isna(pct):
        return "비교 불가"
    if key == "NFCI":
        if 40 <= float(pct) <= 60:
            return "중간 구간"
        return "과거 기준 자금 사정이 어려운 쪽" if float(pct) > 60 else "과거 기준 자금 사정이 느슨한 쪽"
    if key == "STLFSI":
        if 40 <= float(pct) <= 60:
            return "중간 구간"
        return "과거 기준 시장 불안이 높은 쪽" if float(pct) > 60 else "과거 기준 시장 불안이 낮은 쪽"
    return fmt_pct(float(pct))


def _current_reading(key: str, row) -> str:
    direction = str(row.get("direction", "확인 불가"))
    up, down, flat = _BRANCHES[key]
    if direction == "상승":
        return up
    if direction == "하락":
        return down
    if direction == "보합":
        return flat
    return "현재는 방향을 확인할 수 없습니다. 자료가 충분한지와 최신성을 먼저 확인하고 다른 지표로 결론을 대신 만들지 않습니다."


def _core_companion_row(row) -> tuple[str, str, str]:
    key = str(row.get("key", ""))
    value = fmt_value(row.get("latest_value"), str(row.get("value_unit", "")))
    c1 = fmt_change(row.get("change_20obs"), str(row.get("change_unit", "")))
    direction = "↑" if float(row.get("change_20obs") or 0) > 0 else ("↓" if float(row.get("change_20obs") or 0) < 0 else "→")
    return core_name(key, short=True), value, f"{direction} {c1}"


def _aux_companion_row(row) -> tuple[str, str, str]:
    key = str(row.get("key", ""))
    value = fmt_value(row.get("latest_value"), str(row.get("value_unit", "")))
    c1 = fmt_change(row.get("change_1m"), str(row.get("change_unit", "")))
    raw = row.get("change_1m")
    direction = "↑" if raw is not None and pd.notna(raw) and float(raw) > 0 else ("↓" if raw is not None and pd.notna(raw) and float(raw) < 0 else "→")
    return aux_name(key), value, f"{direction} {c1}"


def _companion_table(key: str, aux_df: pd.DataFrame | None, matrix: pd.DataFrame | None) -> list[str]:
    rows: list[tuple[str, str, str]] = []
    for other in _COMPANIONS.get(key, ()):
        core_row = _find(matrix, other)
        if core_row is not None:
            rows.append(_core_companion_row(core_row))
            continue
        aux_row = _find(aux_df, other)
        if aux_row is not None and aux_row.get("latest_value") is not None and not pd.isna(aux_row.get("latest_value")):
            rows.append(_aux_companion_row(aux_row))
    if not rows:
        return ["현재 함께 볼 지표 데이터를 확인할 수 없습니다."]
    lines = ["| 지표 | 현재 | 1개월 |", "|---|---:|---:|"]
    lines.extend(f"| {name} | {value} | {change} |" for name, value, change in rows)
    return lines


def render_aux_detail(
    row: pd.Series | dict,
    *,
    aux_df: pd.DataFrame | None = None,
    matrix: pd.DataFrame | None = None,
) -> str:
    """현재 함께 볼 지표 데이터 + 결과별 가이드 + 8칸 상세카드."""
    r = pd.Series(row)
    key = str(r.get("key", ""))
    value = fmt_value(r.get("latest_value"), str(r.get("value_unit", "")))
    change = fmt_change(r.get("change_1m"), str(r.get("change_unit", "")))
    direction = _DIR_TEXT.get(str(r.get("direction", "확인 불가")), "확인 불가")
    fresh = _FRESHNESS.get(str(r.get("staleness_label", "unknown")), "확인 불가")
    latest_date = str(r.get("latest_date") or "확인 불가")

    up, down, flat = _BRANCHES.get(key, ("", "", ""))
    parts = [
        "## 지금 데이터로 보면",
        "",
        "| 항목 | 현재 |",
        "|---|---|",
        f"| 최신값 | {value} |",
        f"| 1개월 변화 | {change} |",
        f"| 최근 방향 | {direction} |",
        f"| 현재 자료 범위 안 위치 | {_aux_level_text(key, r)} |",
        f"| 관측일 | {latest_date} · {fresh} |",
        "",
        "### 지금 이렇게 읽습니다",
        _current_reading(key, r),
        "",
        "### 같이 볼 지표",
        *_companion_table(key, aux_df, matrix),
        "",
        "### 결과가 달라지면",
        "| 움직임 | 해석 |",
        "|---|---|",
        f"| 오르면 | {up} |",
        f"| 내리면 | {down} |",
        f"| 방향이 뚜렷하지 않으면 | {flat} |",
        "",
        "---",
        "",
        f"# {aux_name(key)} 상세 설명",
        "",
        plain_language(get_aux_interpretation_card(key)),
    ]
    return "\n".join(parts)
