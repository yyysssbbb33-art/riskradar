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
    """과거 위치를 확률처럼 보이지 않는 구간 표현으로 표시한다.

    예:
    - 82 -> ``상위 18% 구간``
    - 13 -> ``하위 13% 구간``
    - 50 -> ``중간 구간``

    이 값은 위험확률·상승확률·하락확률이 아니라 과거 관측값을
    낮은 값부터 높은 값까지 줄 세웠을 때 현재 값이 놓인 자리다.
    """
    if pd.isna(x):
        return "비교 불가"
    x = max(0.0, min(100.0, float(x)))
    if 40.0 <= x <= 60.0:
        return "중간 구간"
    if x < 40.0:
        return f"하위 {x:.0f}% 구간"
    return f"상위 {100.0 - x:.0f}% 구간"
