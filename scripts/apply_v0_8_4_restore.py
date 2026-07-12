from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


CONTEXT_VIEW = r'''"""신용·금리 탭의 관계 맥락을 복원하는 읽기 전용 렌더러.

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
    return (
        '<div class="rr-context-metric">'
        f'<div><strong>{escape(name)}</strong>{suffix}</div>'
        f'<span>{escape(metric["value"])}</span>'
        f'<b>{escape(_symbol(metric["raw"]))} {escape(metric["change"])}</b>'
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
'''


TESTS = r'''from __future__ import annotations

from pathlib import Path

import pandas as pd

from riskradar.context_view import render_credit_context_html, render_rate_context_html
from riskradar.ui import _is_compatible_data_code_version


def _matrix() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "VIX", "latest_value": 19.2, "value_unit": "index", "change_20obs": 1.4, "change_unit": "pt"},
        {"key": "HYOAS", "latest_value": 3.8, "value_unit": "%", "change_20obs": 24.0, "change_unit": "bp"},
        {"key": "DGS30", "latest_value": 4.9, "value_unit": "%", "change_20obs": 18.0, "change_unit": "bp"},
        {"key": "DGS2", "latest_value": 3.9, "value_unit": "%", "change_20obs": -7.0, "change_unit": "bp"},
        {"key": "DFII10", "latest_value": 2.2, "value_unit": "%", "change_20obs": 11.0, "change_unit": "bp"},
        {"key": "T10Y3M", "latest_value": 0.4, "value_unit": "%p", "change_20obs": 8.0, "change_unit": "bp"},
    ])


def _aux() -> pd.DataFrame:
    return pd.DataFrame([
        {"key": "BBBOAS", "latest_value": 1.2, "value_unit": "%", "change_1m": 5.0, "change_unit": "bp"},
        {"key": "AOAS", "latest_value": 0.8, "value_unit": "%", "change_1m": -1.0, "change_unit": "bp"},
        {"key": "CPSPREAD", "latest_value": 25.0, "value_unit": "bp", "change_1m": 3.0, "change_unit": "bp"},
        {"key": "BREAKEVEN", "latest_value": 2.4, "value_unit": "%", "change_1m": 4.0, "change_unit": "bp"},
        {"key": "TERMPREM", "latest_value": 0.7, "value_unit": "%", "change_1m": -3.0, "change_unit": "bp"},
        {"key": "NFCI", "latest_value": -0.2, "value_unit": "index", "change_1m": 0.1, "change_unit": "index"},
        {"key": "STLFSI", "latest_value": -0.4, "value_unit": "index", "change_1m": -0.1, "change_unit": "index"},
    ])


def _quality() -> dict:
    return {
        "credit_episode": {
            "current": {"scope_text": "HY와 BBB에서 상승이 확인되고 있습니다."},
            "lens": {"latest_value_bp": 260.0, "change_1m_bp": 9.0, "label": "HY 쪽 확대가 더 큽니다."},
        }
    }


def test_credit_context_restores_companion_depth_without_causal_claims():
    html = render_credit_context_html(_quality(), _matrix(), _aux())
    assert "같이 읽는 신용 지표" in html
    for text in ("HY−BBB", "BBB OAS", "A OAS", "CP Spread", "VIX", "NFCI", "STLFSI"):
        assert text in html
    assert html.count("rr-context-card") == 4
    assert "인과관계나 선행 순서" in html
    assert "국채 대비 추가 금리" in html


def test_rate_context_restores_alignment_and_background_reading():
    summary = {"curve": {"text": "30Y 상승 · 2Y 하락"}}
    html = render_rate_context_html(_matrix(), _aux(), summary)
    assert "같이 읽는 금리 지표" in html
    for text in ("30Y", "실질 10Y", "10Y Breakeven", "10Y Term Premium", "2Y", "10Y−3M"):
        assert text in html
    assert "같은 방향" in html and "반대 방향" in html
    assert "30Y 구성에 직접 더한다는 뜻은 아닙니다" in html


def test_credit_and_rate_tabs_use_shared_context_visual_grammar_and_restore_market_reference():
    source = (Path(__file__).parents[1] / "src" / "riskradar" / "ui.py").read_text(encoding="utf-8")
    assert "credit_context_component" in source
    assert "rate_context_component" in source
    assert "rr-context-card" in source
    assert 'with gr.Accordion("시장 전체 참고 지표"' in source
    assert "visible=False" not in source[source.index('with gr.Tab("설명")'):]


def test_v084_keeps_previous_ui_cache_compatibility():
    assert _is_compatible_data_code_version("0.8.3", "0.8.4")
    assert _is_compatible_data_code_version("0.8.2", "0.8.4")
'''


write("src/riskradar/context_view.py", CONTEXT_VIEW)
write("tests/test_credit_rate_depth.py", TESTS)

# ui.py
ui = read("src/riskradar/ui.py")
ui = replace_once(
    ui,
    "from . import rate_view as RV\n",
    "from . import rate_view as RV\nfrom .context_view import render_credit_context_html, render_rate_context_html\n",
    label="ui import",
)

css_marker = "/* v0.8.1 Visual Polish: 차분한 금융 대시보드 색 체계 */"
context_css = r'''/* v0.8.4 신용·금리 공통 관계 카드 */
.rr-tab-intro { margin:2px 0 11px; color:var(--body-text-color-subdued); line-height:1.55; }
.rr-context-section { margin:18px 0 16px; }
.rr-context-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.rr-context-card { border:1px solid var(--border-color-primary); border-radius:14px; padding:13px; background:var(--background-fill-primary); min-width:0; box-shadow:0 5px 18px rgba(20,32,55,.045); }
.rr-context-domain-credit { border-top:3px solid color-mix(in srgb, var(--rr-amber, #d68b1f) 72%, transparent); }
.rr-context-domain-rate { border-top:3px solid color-mix(in srgb, var(--rr-blue, #4f73d9) 72%, transparent); }
.rr-context-kicker { color:var(--body-text-color-subdued); font-size:.76rem; font-weight:800; }
.rr-context-card h3 { margin:4px 0 10px; font-size:1rem; letter-spacing:-.015em; }
.rr-context-metrics { border-top:1px solid var(--border-color-primary); }
.rr-context-metric { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:9px; align-items:center; padding:8px 0; border-bottom:1px solid var(--border-color-primary); font-size:.82rem; }
.rr-context-metric div { min-width:0; }
.rr-context-metric strong, .rr-context-metric small { display:block; }
.rr-context-metric small { margin-top:2px; color:var(--body-text-color-subdued); font-weight:400; }
.rr-context-metric span, .rr-context-metric b { white-space:nowrap; }
.rr-context-reading { margin-top:10px; line-height:1.5; font-size:.87rem; }
.rr-context-caution { margin-top:9px; padding-top:8px; border-top:1px dashed var(--border-color-primary); color:var(--body-text-color-subdued); font-size:.78rem; line-height:1.45; }

/* 두 전문 탭의 핵심 카드 문법을 동일하게 맞춘다. */
.rr-credit-grid-2x2, .rr-rate-overview-grid { gap:9px; margin:8px 0 14px; }
.rr-credit-tile, .rr-metric-card { border-radius:14px; padding:13px; }
.rr-credit-tile-head strong, .rr-metric-name { font-size:1rem; font-weight:900; }
.rr-credit-tile-head small, .rr-metric-subtitle { font-size:.76rem; opacity:.62; min-height:1.2em; }
.rr-credit-tile-value, .rr-metric-value { font-size:1.45rem; margin:12px 0 5px; }
.rr-credit-tile-state, .rr-metric-state { font-size:.84rem; min-height:1.3em; }
.rr-credit-tile-change, .rr-metric-change { margin-top:7px; font-size:.84rem; }

'''
ui = replace_once(ui, css_marker, context_css + css_marker, label="ui context css")
ui = replace_once(
    ui,
    "  .rr-mini-grid, .rr-metric-grid { grid-template-columns:1fr; }\n",
    "  .rr-mini-grid, .rr-metric-grid, .rr-context-grid { grid-template-columns:1fr; }\n",
    label="ui mobile context grid",
)
ui = replace_once(
    ui,
    '    "0.8.3": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2", "0.8.3"},\n',
    '    "0.8.3": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2", "0.8.3"},\n'
    '    # v0.8.4는 전문 탭의 관계 맥락과 시각 문법만 복원하며 캐시 schema는 그대로다.\n'
    '    "0.8.4": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2", "0.8.3", "0.8.4"},\n',
    label="ui compatibility",
)
ui = replace_once(
    ui,
    '        "credit_map": render_credit_range_map_html(effective_dq, arts["signal_matrix"], aux_df),\n',
    '        "credit_map": render_credit_range_map_html(effective_dq, arts["signal_matrix"], aux_df),\n'
    '        "credit_context_html": render_credit_context_html(effective_dq, arts["signal_matrix"], aux_df),\n'
    '        "rate_context_html": render_rate_context_html(arts["signal_matrix"], aux_df, snapshot.rate_composition),\n',
    label="ui payload context",
)

old_credit = '''        with gr.Tab("신용"):
            gr.Markdown("회사채 수치는 비슷한 만기의 국채 대비 추가 금리입니다.")
            credit_map_component = gr.HTML(initial["credit_map"])
            credit_timeline_component = gr.HTML(initial["credit_timeline_html"])
'''
new_credit = '''        with gr.Tab("신용"):
            gr.Markdown("## 신용 현황")
            gr.HTML('<div class="rr-tab-intro">회사채 OAS는 비슷한 만기의 국채 대비 추가 금리입니다. 현재 수준·최근 변화·어느 등급과 시장까지 같은 방향이 나타나는지를 함께 봅니다.</div>')
            credit_map_component = gr.HTML(initial["credit_map"])
            credit_context_component = gr.HTML(initial["credit_context_html"])
            credit_timeline_component = gr.HTML(initial["credit_timeline_html"])
'''
ui = replace_once(ui, old_credit, new_credit, label="ui credit tab")

old_rate = '''        with gr.Tab("금리"):
            gr.Markdown("## 금리 현황")
            rate_overview_component = gr.HTML(initial["rate_overview_html"])
            rate_curve_component = gr.HTML(initial["rate_curve_html"])

            gr.Markdown("## 30Y 금리 변화 나눠보기")
'''
new_rate = '''        with gr.Tab("금리"):
            gr.Markdown("## 금리 현황")
            gr.HTML('<div class="rr-tab-intro">현재 금리 수준과 최근 변화를 먼저 보고, 단기·장기 관계와 실질금리·물가 관련 금리 차이·Term Premium의 방향을 따로 확인합니다.</div>')
            rate_overview_component = gr.HTML(initial["rate_overview_html"])
            rate_curve_component = gr.HTML(initial["rate_curve_html"])
            rate_context_component = gr.HTML(initial["rate_context_html"])

            gr.Markdown("## 30Y 금리 변화 나눠보기")
'''
ui = replace_once(ui, old_rate, new_rate, label="ui rate tab")

old_market_reference = '''            market_reference_components = {}
            for key in ("NFCI", "STLFSI"):
                market_reference_components[key] = gr.Markdown(visible=False, value=initial["aux_details"].get(key, "현재 데이터를 읽을 수 없습니다."))

            with gr.Accordion("RiskRadar 읽는 법", open=False, elem_classes="rr-detail-accordion"):
'''
new_market_reference = '''            with gr.Accordion("시장 전체 참고 지표", open=False, elem_classes="rr-detail-accordion"):
                market_reference_components = {}
                for key in ("NFCI", "STLFSI"):
                    with gr.Accordion(f"{aux_name(key)} 설명", open=False, elem_classes="rr-detail-accordion"):
                        market_reference_components[key] = gr.Markdown(
                            initial["aux_details"].get(key, "현재 데이터를 읽을 수 없습니다.")
                        )

            with gr.Accordion("RiskRadar 읽는 법", open=False, elem_classes="rr-detail-accordion"):
'''
ui = replace_once(ui, old_market_reference, new_market_reference, label="ui restore market references")

ui = replace_once(
    ui,
    '            credit_map_component,\n            credit_timeline_component,\n',
    '            credit_map_component,\n            credit_context_component,\n            rate_context_component,\n            credit_timeline_component,\n',
    label="ui reload outputs context",
)
ui = replace_once(
    ui,
    '                payload["credit_map"],\n                payload["credit_timeline_html"],\n',
    '                payload["credit_map"],\n                payload["credit_context_html"],\n                payload["rate_context_html"],\n                payload["credit_timeline_html"],\n',
    label="ui reload return context",
)
write("src/riskradar/ui.py", ui)

# Version and README
pyproject = read("pyproject.toml")
pyproject = replace_once(pyproject, 'version = "0.8.3"', 'version = "0.8.4"', label="pyproject version")
write("pyproject.toml", pyproject)

version = read("src/riskradar/version.py")
version = replace_once(version, '__version__ = "0.8.3"', '__version__ = "0.8.4"', label="runtime version")
version = replace_once(
    version,
    '#   0.8.3  README·OAS 표현·UI 데이터 호환·릴리스 검사 핫픽스   <- 현재',
    '#   0.8.3  README·OAS 표현·UI 데이터 호환·릴리스 검사 핫픽스\n'
    '#   0.8.4  신용·금리 보조지표 깊이 복원 + 전문 탭 UI 문법 통일   <- 현재',
    label="version history",
)
write("src/riskradar/version.py", version)

readme = read("README.md")
readme = replace_once(readme, "# RiskRadar v0.8.3 —", "# RiskRadar v0.8.4 —", label="readme title")
release_section = '''## v0.8.4 신용·금리 깊이 복원

v0.8.4는 v0.8.2의 현황 중심 첫 화면을 유지하면서, 지나치게 축소됐던 신용·금리 전문 탭의 보조지표 맥락과 시각적 일관성을 복원합니다.

- 신용 탭에 `HY−BBB / BBB·A / CP·VIX / NFCI·STLFSI`를 함께 읽는 관계 카드 복원
- 금리 탭에 `30Y / 실질 10Y / 10Y Breakeven / 10Y Term Premium` 방향 비교와 `2Y / 30Y / 10Y−3M` 배경 카드 추가
- 같은 시기 움직임과 인과관계를 구분하고, OAS를 국채 대비 추가 금리로 유지
- 신용·금리 카드의 크기·타이포그래피·상태 칩·여백을 같은 시각 문법으로 통일
- 설명 탭에서 보이지 않던 NFCI·STLFSI 상세 아코디언 복원
- 새 계산·threshold·상태 전이 없이 저장된 데이터와 판정을 다시 배치

'''
readme = replace_once(readme, "## v0.8.3 릴리스 일관성 핫픽스\n", release_section + "## v0.8.3 릴리스 일관성 핫픽스\n", label="readme release section")
write("README.md", readme)

print("Applied v0.8.4 credit/rate depth restoration")
