"""표시용 값 포매팅 (Telegram + UI 공용)."""
from __future__ import annotations

import pandas as pd


def fmt_value(value: float, unit: str) -> str:
    if pd.isna(value):
        return "-"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "bp":
        # 내부 계산은 bp를 유지하지만 사용자 화면에서는 더 익숙한 %p로 보여준다.
        return f"{value / 100.0:.2f}%p"
    return f"{value:.1f}"  # VIX 등 지수값


def fmt_change(x: float, unit: str = "bp") -> str:
    if pd.isna(x):
        return "-"
    if unit == "bp":
        return f"{x / 100.0:+.2f}%p"
    if unit == "pt":
        return f"{x:+.1f}포인트"
    return f"{x:+.2f}{unit}"


def fmt_pct(x: float) -> str:
    """과거 위치를 확률이 아니라 '몇 %의 날보다 높은가'로 직접 표시한다.

    예: 82 -> '높은 편 · 82%의 날보다 높음'.
    위험확률이 아니라 과거 관측값과의 상대 비교다.
    """
    if pd.isna(x):
        return "비교 불가"
    x = max(0.0, min(100.0, float(x)))
    if x >= 90:
        level = "매우 높은 편"
    elif x >= 70:
        level = "높은 편"
    elif x <= 10:
        level = "매우 낮은 편"
    elif x <= 30:
        level = "낮은 편"
    else:
        level = "중간쯤"
    return f"{level} · {x:.0f}%의 날보다 높음"
