"""현재 상황의 지표별 상세 설명 렌더링.

현재 스냅샷을 기존 8칸 해석 카드와 연결한다. 판정 로직은 새로 만들지 않고,
저장된 상태·조합 해석 결과를 사용자용 문장으로 재구성한다.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .display_text import (LABEL_1M, LABEL_3M, LABEL_5Y, LABEL_10Y,
                           core_name, plain_language, state_name)
from .formatting import fmt_change, fmt_pct, fmt_value
from .external_guidance import render_external_guidance
from .state_guidance import render_state_guidance
from .user_copy import indicator_caution, indicator_summary, render_movement_table
from .deep_guides import guide_markdown


# 어떤 조합이 어떤 핵심지표와 직접 연결되는지 명시적으로 관리한다.
# 조합명 문자열을 검색하지 않아 문구가 바뀌어도 연결이 깨지지 않는다.
COMBO_CORE_KEYS: dict[str, tuple[str, ...]] = {
    "rates_30up_2down": ("DGS30", "DGS2"),
    "rates_30down_2up": ("DGS30", "DGS2"),
    "rates_broad_up": ("DGS30", "DGS2", "DFII10"),
    "rates_broad_down": ("DGS30", "DGS2"),
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
            "### 이 지표와 함께 나타난 흐름\n"
            "오늘 데이터에서는 이 지표와 함께 따로 설명할 만한 주요 조합이 잡히지 않았습니다. "
            "이는 지표가 중요하지 않다는 뜻이 아니라, 현재 정의된 조합 규칙에서 별도 패턴이 탐지되지 않았다는 뜻입니다."
        )

    lines = ["### 같이 나타난 움직임"]
    for reading in readings:
        label = plain_language(str(reading.get("label", "현재 조합")))
        observed = plain_language(str(reading.get("observed", "")))
        lines += ["", f"#### {label}", observed]

        explanations = _reading_explanations(reading)
        supported = [
            plain_language(explanations[eid])
            for eid in (reading.get("supported_ids") or [])
            if eid in explanations
        ]
        weakened = [
            plain_language(explanations[eid])
            for eid in (reading.get("weakened_ids") or [])
            if eid in explanations
        ]

        if supported:
            lines.append("- **현재 함께 보이는 점:** " + " / ".join(supported))
        else:
            lines.append("- **현재 함께 보이는 점:** 같이 본 지표만으로 어느 경우가 더 중요한지 고르기 어렵습니다.")
        if weakened:
            lines.append("- **반대로 움직이는 점:** " + " / ".join(weakened))
        if reading.get("conflict"):
            lines.append(f"- **엇갈리는 부분:** {reading['conflict']}")

    lines.append("\n같이 본 지표가 엇갈리면 한 방향으로 억지로 묶지 않습니다.")
    return "\n".join(lines)


def render_indicator_detail(
    row: pd.Series | dict,
    data_quality: dict | None,
    one_line: str,
    frames: dict[str, pd.DataFrame] | None = None,
    aux_df: pd.DataFrame | None = None,
    matrix: pd.DataFrame | None = None,
) -> str:
    """지표별 deep guide를 현재 스냅샷 기반으로 한 번만 렌더링한다."""
    r = pd.Series(row)
    key = str(r["key"])
    parts = [
        guide_markdown(
            key, r, matrix=matrix, aux_df=aux_df, data_quality=data_quality,
            rate_summary=(data_quality or {}).get("rate_composition"), one_line=one_line,
        ),
        render_state_guidance(key, r, frames=frames, aux_df=aux_df, matrix=matrix),
        render_external_guidance(key),
        _linked_combo_markdown(data_quality, key),
    ]
    return "\n\n".join(part for part in parts if part)
