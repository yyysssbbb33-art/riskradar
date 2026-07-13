"""함께 볼 지표·외부참고의 현재값 연결 상세 설명.

보이는 7개 지표를 현재 데이터와 고정 상세카드에 연결한다.
판정 규칙을 새로 만들지 않고 저장된 방향·수준·다른 지표의 현재값을 설명한다.
"""
from __future__ import annotations

import pandas as pd

from .display_text import aux_name, core_name, plain_language, state_name
from .formatting import fmt_change, fmt_pct, fmt_value
from .user_copy import indicator_summary, indicator_caution, movement_label, movement_result, movement_result_cell
from .deep_guides import guide_markdown

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
    key: (
        movement_result(key, "up"),
        movement_result(key, "down"),
        movement_result(key, "flat"),
    )
    for key in ("BREAKEVEN", "TERMPREM", "BBBOAS", "AOAS", "CPSPREAD", "NFCI", "STLFSI")
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
    if direction == "상승":
        return movement_result_cell(key, "up")
    if direction == "하락":
        return movement_result_cell(key, "down")
    if direction == "보합":
        return movement_result_cell(key, "flat")
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
    """보조지표 deep guide를 현재 스냅샷 기반으로 한 번만 렌더링한다."""
    r = pd.Series(row)
    return guide_markdown(str(r.get("key", "")), r, matrix=matrix, aux_df=aux_df)
