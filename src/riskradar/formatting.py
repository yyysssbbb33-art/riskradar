"""표시용 값 포매팅 (Telegram + UI 공용)."""
from __future__ import annotations

import pandas as pd


def fmt_value(value: float, unit: str) -> str:
    if pd.isna(value):
        return "-"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "bp":
        return f"{value:.0f}bp"
    return f"{value:.1f}"  # index 등


def fmt_change(x: float, unit: str = "bp") -> str:
    if pd.isna(x):
        return "-"
    return f"{x:+.0f}{unit}"


def fmt_pct(x: float) -> str:
    return "-" if pd.isna(x) else f"{x:.0f}%"
