"""신용·금리 탭의 관계 맥락을 복원하는 읽기 전용 렌더러.

새 판정이나 점수를 만들지 않는다. 이미 저장된 signal matrix, aux matrix,
credit episode, rate composition 결과를 같은 시각 문법으로 묶어 보여준다.
"""
from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd

from .display_text import aux_name, core_name, plain_language
from .formatting import fmt_change, fmt_value


def _row(df: pd.DataFrame | None, key: str) -> pd.Series | None:
    if df is None or df.empty or "key" not in df.columns:
        return None
    hit = df.loc[df["key"].astype(str) == key]
    return None if hit.empty else hit.iloc[-1]


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _sign(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return 1 if number > 0 else (-1 if number < 0 else 0)


def _symbol(value: Any) -> str:
    return {1: "↑", -1: "↓", 0: "→"}[_sign(value)]


def _metric(df: pd.DataFrame | None, key: str, *, aux: bool = False) -> dict[str, Any]:
    row = _row(df, key)
    if row is None:
        return {"key": key, "value": "-", "change": "-", "raw": None, "available": False}
    raw = row.get("change_1m") if aux else row.get("change_20obs")
    return {
        "key": key,
        "value": fmt_value(row.get("latest_value"), str(row.get("value_unit", ""))),
        "change": fmt_change(raw, str(row.get("change_unit", ""))),
        "raw": raw,
        "available": True,
    }


def _metric_row(name: str, metric: dict[str, Any], note: str = "") -> str:
    suffix = f'<small>{escape(note)}</small>' if note else ""
    direction = "·" if not metric.get("available", True) else _symbol(metric["raw"])
    return (
        '<div class="rr-context-metric">'
        f'<div><strong>{escape(name)}</strong>{suffix}</div>'
        f'<span>{escape(metric["value"])}</span>'
        f'<b>{escape(direction)} {escape(metric["change"])}</b>'
        '</div>'
    )


def _card(domain: str, title: str, subtitle: str, rows: list[str], reading: str,
          caution: str = "") -> str:
    caution_html = f'<div class="rr-context-caution">{escape(caution)}</div>' if caution else ""
    return (
        f'<article class="rr-context-card rr-context-domain-{escape(domain)}">'
        f'<div class="rr-context-kicker">{escape(subtitle)}</div>'
        f'<h3>{escape(title)}</h3>'
        '<div class="rr-context-metrics">' + ''.join(rows) + '</div>'
        f'<div class="rr-context-reading">{escape(reading)}</div>'
        + caution_html +
        '</article>'
    )


def _credit_breadth_reading(bbb: dict[str, Any], a: dict[str, Any]) -> str:
    bbb_sign, a_sign = _sign(bbb["raw"]), _sign(a["raw"])
    if bbb_sign > 0 and a_sign > 0:
        return "BBB와 A의 국채 대비 추가 금리가 함께 확대돼 투자등급 안쪽까지 같은 방향이 나타납니다."
    if bbb_sign > 0 and a_sign <= 0:
        return "BBB의 추가 금리는 확대됐지만 A까지 같은 방향은 아닙니다. 변화가 투자등급 안쪽 전체로 번졌다고 보기는 어렵습니다."
    if bbb_sign <= 0 and a_sign > 0:
        return "A의 추가 금리는 확대됐지만 BBB와 방향이 엇갈립니다. 투자등급 회사채를 한 방향으로 묶지 않습니다."
    if bbb_sign < 0 and a_sign < 0:
        return "BBB와 A의 국채 대비 추가 금리가 함께 줄어 투자등급 회사채의 상대 부담은 완화되는 방향입니다."
    return "BBB와 A에서 함께 강조할 추가 금리 확대는 현재 제한적입니다."


def _credit_cross_market_reading(cp: dict[str, Any], vix: dict[str, Any]) -> str:
    cp_sign, vix_sign = _sign(cp["raw"]), _sign(vix["raw"])
    if cp_sign > 0 and vix_sign > 0:
        return "단기 기업자금의 금리 차이와 주식시장 변동성이 함께 상승했습니다. 같은 시기 움직임이며 어느 쪽이 원인이라는 뜻은 아닙니다."
    if cp_sign > 0 and vix_sign <= 0:
        return "CP 금리 차이는 확대됐지만 VIX는 같은 방향이 아닙니다. 변화가 주식시장 불안과 함께 나타난 것은 아닙니다."
    if cp_sign <= 0 and vix_sign > 0:
        return "VIX는 상승했지만 CP 금리 차이는 확대되지 않았습니다. 불안이 단기 기업자금까지 확인된 상태는 아닙니다."
    return "CP와 VIX에서 함께 강조할 상승은 현재 제한적입니다."


def _external_reading(nfci: dict[str, Any], stlfsi: dict[str, Any]) -> str:
    n, s = _sign(nfci["raw"]), _sign(stlfsi["raw"])
    if n > 0 and s > 0:
        return "두 주간 종합지표가 함께 상승해 금융여건과 시장 스트레스가 모두 빡빡해지는 방향입니다."
    if n < 0 and s < 0:
        return "두 주간 종합지표가 함께 하락해 금융여건과 시장 스트레스는 완화되는 방향입니다."
    if n == 0 and s == 0:
        return "두 종합지표에서 뚜렷한 공통 방향은 확인되지 않습니다."
    return "NFCI와 STLFSI가 엇갈립니다. 금융시장 전체가 한 방향이라고 묶지 않습니다."


def render_credit_context_html(data_quality: dict | None, matrix: pd.DataFrame | None,
                               aux_df: pd.DataFrame | None) -> str:
    """신용 탭에서 등급 확산·단기자금·외부 종합지표를 함께 읽는다."""
    credit = (data_quality or {}).get("credit_episode") or {}
    current = credit.get("current") or {}
    lens = credit.get("lens") or {}

    bbb = _metric(aux_df, "BBBOAS", aux=True)
    a = _metric(aux_df, "AOAS", aux=True)
    cp = _metric(aux_df, "CPSPREAD", aux=True)
    vix = _metric(matrix, "VIX")
    nfci = _metric(aux_df, "NFCI", aux=True)
    stlfsi = _metric(aux_df, "STLFSI", aux=True)

    lens_value = _number(lens.get("latest_value_bp"))
    lens_change = _number(lens.get("change_1m_bp"))
    lens_metric = {
        "value": "-" if lens_value is None else f"{lens_value / 100.0:.2f}%p",
        "change": "-" if lens_change is None else f"{lens_change / 100.0:+.2f}%p",
        "raw": lens_change,
    }
    scope = plain_language(str(current.get("scope_text") or "현재 기업 신용에 새로 강조할 움직임이 없습니다."))
    lens_label = plain_language(str(lens.get("label") or "HY와 BBB의 상대 차이를 확인할 수 없습니다."))

    cards = [
        _card(
            "credit", "HY와 BBB의 상대 차이", "신용등급별 집중도",
            [_metric_row("HY−BBB", lens_metric, "HY와 BBB의 추가 금리 차이")],
            f"{scope} {lens_label}",
            "HY−BBB는 두 시장의 상대 차이이며 회사채 절대금리 자체가 아닙니다.",
        ),
        _card(
            "credit", "투자등급 안쪽까지 번졌나", "등급 확산 확인",
            [_metric_row("BBB OAS", bbb), _metric_row("A OAS", a)],
            _credit_breadth_reading(bbb, a),
            "OAS는 같은 만기의 국채 대비 추가 금리입니다.",
        ),
        _card(
            "credit", "단기자금과 주식 변동성", "다른 시장의 동시 움직임",
            [_metric_row("CP Spread", cp), _metric_row("VIX", vix)],
            _credit_cross_market_reading(cp, vix),
            "동시에 움직였다는 사실만 보여주며 인과관계나 선행 순서를 뜻하지 않습니다.",
        ),
        _card(
            "credit", "시장 전체 참고", "주간 외부 종합지표",
            [_metric_row("NFCI", nfci), _metric_row("STLFSI", stlfsi)],
            _external_reading(nfci, stlfsi),
            "두 지표는 신용 에피소드 판정을 직접 바꾸지 않는 외부 참고 자료입니다.",
        ),
    ]
    return (
        '<section class="rr-context-section">'
        '<div class="rr-section-title"><h2>같이 읽는 신용 지표</h2><span>현재값 · 최근 약 1개월</span></div>'
        '<div class="rr-context-grid">' + ''.join(cards) + '</div>'
        '</section>'
    )


def _alignment_text(d30: dict[str, Any], items: list[tuple[str, dict[str, Any]]]) -> str:
    base = _sign(d30["raw"])
    if base == 0:
        return "30Y의 최근 방향이 뚜렷하지 않아 참고 지표와의 방향 비교도 제한적입니다."
    same: list[str] = []
    opposite: list[str] = []
    flat: list[str] = []
    for name, metric in items:
        sign = _sign(metric["raw"])
        if sign == 0:
            flat.append(name)
        elif sign == base:
            same.append(name)
        else:
            opposite.append(name)
    parts = [f"30Y는 최근 {'상승' if base > 0 else '하락'}했습니다."]
    if same:
        parts.append("같은 방향: " + "·".join(same) + ".")
    if opposite:
        parts.append("반대 방향: " + "·".join(opposite) + ".")
    if flat:
        parts.append("뚜렷한 변화 없음: " + "·".join(flat) + ".")
    return " ".join(parts)


def _curve_background_reading(d2: dict[str, Any], d30: dict[str, Any], curve: dict[str, Any]) -> str:
    s2, s30 = _sign(d2["raw"]), _sign(d30["raw"])
    if s2 < 0 < s30:
        first = "2Y는 하락하고 30Y는 상승해 단기와 장기의 방향이 엇갈립니다."
    elif s30 < 0 < s2:
        first = "2Y는 상승하고 30Y는 하락해 단기와 장기의 방향이 엇갈립니다."
    elif s2 == s30 and s2 != 0:
        first = f"2Y와 30Y가 함께 {'상승' if s2 > 0 else '하락'}했습니다."
    else:
        first = "2Y와 30Y에서 뚜렷한 공통 방향은 제한적입니다."
    text = str(curve.get("text") or "").strip()
    return first + (f" 저장된 관계 요약은 ‘{plain_language(text)}’입니다." if text else "")


def render_rate_context_html(matrix: pd.DataFrame | None, aux_df: pd.DataFrame | None,
                             rate_summary: dict | None) -> str:
    """금리 탭에서 장기금리 참고 요인과 단기·장기 배경을 한 화면에 묶는다."""
    d30 = _metric(matrix, "DGS30")
    d2 = _metric(matrix, "DGS2")
    real10 = _metric(matrix, "DFII10")
    curve10_3m = _metric(matrix, "T10Y3M")
    breakeven = _metric(aux_df, "BREAKEVEN", aux=True)
    term = _metric(aux_df, "TERMPREM", aux=True)
    curve = (rate_summary or {}).get("curve") or {}

    alignment = _alignment_text(
        d30,
        [("실질 10Y", real10), ("10Y Breakeven", breakeven), ("10Y Term Premium", term)],
    )
    cards = [
        _card(
            "rate", "장기금리 방향 비교", "30Y와 참고 지표",
            [
                _metric_row("30Y", d30),
                _metric_row("실질 10Y", real10),
                _metric_row("10Y Breakeven", breakeven),
                _metric_row("10Y Term Premium", term),
            ],
            alignment,
            "방향을 나란히 비교한 것이며 10Y Breakeven·Term Premium을 30Y 구성에 직접 더한다는 뜻은 아닙니다.",
        ),
        _card(
            "rate", "단기·장기와 경기 배경", "2Y · 30Y · 10Y−3M",
            [
                _metric_row("2Y", d2),
                _metric_row("30Y", d30),
                _metric_row("10Y−3M", curve10_3m),
            ],
            _curve_background_reading(d2, d30, curve),
            "10Y−3M은 현재 시장 스트레스의 직접 판정이 아니라 경기 흐름의 배경으로 봅니다.",
        ),
    ]
    return (
        '<section class="rr-context-section">'
        '<div class="rr-section-title"><h2>같이 읽는 금리 지표</h2><span>관계·반대 방향까지 확인</span></div>'
        '<div class="rr-context-grid rr-context-grid-rate">' + ''.join(cards) + '</div>'
        '</section>'
    )
