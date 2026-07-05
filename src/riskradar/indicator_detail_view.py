"""현재 상황의 지표별 상세 설명 렌더링.

현재 스냅샷을 기존 8칸 해석 카드와 연결한다. 판정 로직은 새로 만들지 않고,
저장된 상태·조합 해석 결과를 사용자용 문장으로 재구성한다.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .display_text import LABEL_1M, LABEL_3M, LABEL_5Y, LABEL_10Y, core_name
from .formatting import fmt_change, fmt_pct, fmt_value
from .interpretation_cards import get_interpretation_card
from .state_guidance import render_state_guidance


# 어떤 조합이 어떤 핵심지표와 직접 연결되는지 명시적으로 관리한다.
# 조합명 문자열을 검색하지 않아 문구가 바뀌어도 연결이 깨지지 않는다.
COMBO_CORE_KEYS: dict[str, tuple[str, ...]] = {
    "rates_30up_2down": ("DGS30", "DGS2"),
    "rates_30down_2up": ("DGS30", "DGS2"),
    "rates_broad_up": ("DGS30", "DGS2", "DFII10"),
    "rates_broad_down": ("DGS30", "DGS2"),
    "nominal_real_up": ("DGS30", "DFII10"),
    "nominal_up_real_not": ("DGS30", "DFII10"),
    "two_down_credit_widening": ("DGS2", "HYOAS"),
    "two_down_credit_quiet": ("DGS2", "HYOAS"),
    "vol_leads": ("VIX", "HYOAS"),
    "credit_only": ("VIX", "HYOAS"),
    "vol_credit_together": ("VIX", "HYOAS"),
    "vol_calm_credit_persist": ("VIX", "HYOAS"),
    "cycle_renorm_credit_wide": ("T10Y3M", "HYOAS"),
    "cycle_renorm_credit_quiet": ("T10Y3M", "HYOAS"),
    "long_inv_2y_down": ("T10Y3M", "DGS2"),
}


def _reading_explanations(reading: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("id", "")): str(item.get("text", ""))
        for item in (reading.get("explanations") or [])
        if item.get("id")
    }


def _relevant_readings(data_quality: dict | None, key: str, limit: int = 2) -> list[dict]:
    readings = (data_quality or {}).get("readings") or []
    result: list[dict] = []
    for reading in readings:
        combo_id = str(reading.get("combo_id", ""))
        if key in COMBO_CORE_KEYS.get(combo_id, ()):
            result.append(reading)
        if len(result) >= limit:
            break
    return result


def _linked_combo_markdown(data_quality: dict | None, key: str) -> str:
    readings = _relevant_readings(data_quality, key)
    if not readings:
        return (
            "### 현재 연결된 조합\n"
            "오늘의 해석 엔진에서 이 지표와 직접 연결된 주요 조합은 현재 따로 잡히지 않았습니다. "
            "이는 지표가 중요하지 않다는 뜻이 아니라, 현재 정의된 조합 규칙에서 별도 패턴이 탐지되지 않았다는 뜻입니다."
        )

    lines = ["### 현재 연결된 조합"]
    for reading in readings:
        label = str(reading.get("label", "현재 조합"))
        observed = str(reading.get("observed", ""))
        lines += ["", f"#### {label}", observed]

        explanations = _reading_explanations(reading)
        supported = [
            explanations[eid]
            for eid in (reading.get("supported_ids") or [])
            if eid in explanations
        ]
        weakened = [
            explanations[eid]
            for eid in (reading.get("weakened_ids") or [])
            if eid in explanations
        ]

        if supported:
            lines.append("- **현재 상대적으로 더 잘 맞는 설명:** " + " / ".join(supported))
        else:
            lines.append("- **현재 상대적으로 더 잘 맞는 설명:** 확인지표만으로 한 설명이 뚜렷하게 우세하지 않습니다.")
        if weakened:
            lines.append("- **반대 증거·약해지는 설명:** " + " / ".join(weakened))
        if reading.get("conflict"):
            lines.append(f"- **결과가 엇갈리는 부분:** {reading['conflict']}")

    lines.append("\n더 자세한 확인지표별 분기는 **오늘의 해석** 탭에서 볼 수 있습니다.")
    return "\n".join(lines)


def render_indicator_detail(
    row: pd.Series | dict,
    data_quality: dict | None,
    one_line: str,
    frames: dict[str, pd.DataFrame] | None = None,
    aux_df: pd.DataFrame | None = None,
    matrix: pd.DataFrame | None = None,
) -> str:
    """현재 데이터 요약 + 현재 연결 조합 + 고정 8칸 카드를 한 문서로 렌더링한다."""
    r = pd.Series(row)
    key = str(r["key"])

    facts = [
        "## 현재 데이터와 연결해서 보면",
        "",
        f"- **상태:** {r['state_label']}",
        f"- **최신값:** {fmt_value(r['latest_value'], r['value_unit'])}",
        f"- **관측일:** {r['latest_observed_date']}",
        f"- **{LABEL_1M}:** {fmt_change(r['change_20obs'], r['change_unit'])}",
        f"- **{LABEL_3M}:** {fmt_change(r['change_60obs'], r['change_unit'])}",
        f"- **{LABEL_5Y}:** {fmt_pct(r['percentile_5y'])}",
        f"- **{LABEL_10Y}:** {fmt_pct(r['percentile_10y'])}",
        "",
        f"> {one_line}",
        "",
        render_state_guidance(key, r, frames=frames, aux_df=aux_df, matrix=matrix),
        "",
        _linked_combo_markdown(data_quality, key),
        "",
        "---",
        "",
        f"# {core_name(key)} 상세 설명",
        "",
        get_interpretation_card(key),
    ]
    return "\n".join(facts)
