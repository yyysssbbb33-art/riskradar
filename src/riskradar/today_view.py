"""RiskRadar v0.4.0 — '오늘의 해석' 렌더링 (gradio 비의존).

data_quality(dict) + aux_signal_matrix(DataFrame)를 마크다운 문자열로 만든다.
UI(ui.py)는 이 문자열을 gr.Markdown에 넣기만 한다. 여기서 판단 문장을 새로 만들지 않는다.
"""
from __future__ import annotations

import pandas as pd

_DIR_MARK = {"상승": "▲ 상승", "하락": "▼ 하락", "보합": "· 보합", "판정불가": "— 판정불가"}


def _fmt_change(row) -> str:
    d = row.get("direction", "")
    if d in ("보합", "판정불가") or row.get("change_1m") is None or pd.isna(row.get("change_1m")):
        return _DIR_MARK.get(d, d)
    unit = row.get("change_unit", "")
    return f"{_DIR_MARK.get(d, d)} ({row['change_1m']:+.0f}{unit}, 최신 {row.get('latest_date','?')})"


def _aux_section(aux_df: pd.DataFrame) -> str:
    if aux_df is None or aux_df.empty:
        return "### 보조지표 방향\n보조지표 데이터가 아직 없습니다.\n"
    lines = ["### 보조지표 방향 (원인 확인용)"]
    for _, r in aux_df.iterrows():
        lines.append(f"- {r['display_name']}: {_fmt_change(r)}")
    lines.append("\n*보조지표는 3축·종합상태에 넣지 않고 원인 확인에만 씁니다.*")
    return "\n".join(lines)


def _axes_section(axes: dict) -> str:
    if not axes:
        return "축 조망 데이터가 아직 없습니다. 다음 배치 후 표시됩니다."
    vc, cy, rt = axes["vol_credit"], axes["cycle"], axes["rate"]
    members = rt.get("members", {})
    mtxt = ", ".join(f"{k} {members.get(k,'기본')}" for k in ("DGS30", "DGS2", "DFII10"))
    lines = [
        f"**{axes['summary_line']}**",
        "",
        f"- 변동성·신용: {vc['label']} — {vc['note']}",
        f"- 경기 사이클: {cy['label']}",
        f"- 금리 방향: {rt['result']} ({mtxt})",
        "",
        f"> {axes.get('disclaimer','')}",
    ]
    return "\n".join(lines)


def _reading_block(r: dict) -> str:
    lines = [f"#### {r['label']}", f"관찰: {r['observed']}", "", "가능한 설명:"]
    lines += [f"- {e['text']}" for e in r["explanations"]]
    lines.append("\n확인지표:")
    for c in r["checks"]:
        lines.append(f"- [{c['direction']}] {c['text']}")
    if r.get("conflict"):
        lines.append(f"\n⚠️ {r['conflict']}")
    lines.append(f"\n남은 불확실성: {r['uncertainty']}")
    return "\n".join(lines)


def render_today_markdown(dq: dict, aux_df: pd.DataFrame | None) -> str:
    """오늘의 해석 탭 전체 마크다운."""
    dq = dq or {}
    parts = ["## 오늘의 해석", "", _axes_section(dq.get("axes")), "",
             _aux_section(aux_df), "", "### 관찰된 조합"]
    readings = dq.get("readings") or []
    if not readings:
        parts.append("현재 정의된 조합 중 뚜렷하게 관찰된 것이 없습니다. "
                     "각 지표는 다른 탭에서 개별 확인하세요.")
    else:
        for r in readings:
            parts.append(_reading_block(r))
            parts.append("")
    parts.append("---\n*이 탭은 지표를 함께 읽는 법을 돕는 도구입니다. "
                 "매수·매도나 종합 위험 판단을 제공하지 않습니다.*")
    return "\n".join(parts)
