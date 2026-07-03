"""읽기 전용 Gradio UI.

캐시(data_status.json + 산출물)만 읽는다. 절대 refresh 하지 않는다.
days_since_observed는 여기서 현재 KST 날짜 기준으로 렌더 시점 계산한다.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import gradio as gr
import pandas as pd

from . import config as C
from . import cache_store
from .formatting import fmt_change, fmt_pct, fmt_value

KST = ZoneInfo(C.APP_TIMEZONE)

GUIDE = """\
**RiskRadar**는 미국 시장의 변동성·신용·금리·실질금리·수익률곡선 신호를
분리해서 보여주는 매크로 스트레스 계기판입니다.

이 앱은 주식 폭락, 경기침체, 환율, 시장 과열, 매수·매도 타이밍을 예측하지 않습니다.
상태 라벨은 판단이 아니라 수치를 읽기 위한 시각 보조입니다.
최종 판단은 현재값·관측일·변화율·백분위·차트를 함께 보고 하세요.

- **VIX**: 주식 옵션시장 단기 변동성. 단독보다 HY OAS와 함께.
- **HY OAS**: 하이일드 신용 스프레드. 신용 스트레스의 핵심.
- **T10Y3M**: 현재 스트레스가 아니라 경기 사이클 배경 지표.
- **DGS30/DGS2/DFII10**: 금리 3종. 수준보다 변화속도. 급락은 상태가 아니라 플래그.
"""


def _days_since(date_str: str) -> int:
    d = pd.to_datetime(date_str).date()
    return (datetime.now(KST).date() - d).days


def _board_df(matrix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in matrix.iterrows():
        rows.append({
            "지표": r["display_name"],
            "상태": r["state_label"],
            "최신값": fmt_value(r["latest_value"], r["value_unit"]),
            "관측일": r["latest_observed_date"],
            "경과일": _days_since(r["latest_observed_date"]),
            "20obs": fmt_change(r["change_20obs"], r["change_unit"]),
            "60obs": fmt_change(r["change_60obs"], r["change_unit"]),
            "5Y%": fmt_pct(r["percentile_5y"]),
            "10Y%": fmt_pct(r["percentile_10y"]),
            "급락": "⚠︎" if r["drop_flag"] else "",
            "근거": r["state_reason"],
        })
    return pd.DataFrame(rows)


def _synced_df(arts: dict) -> pd.DataFrame:
    s = arts["synced_snapshot"]
    if s.empty:
        return pd.DataFrame([{"info": "동일 기준일 교집합 없음"}])
    view = s.copy()
    view["value"] = [fmt_value(v, C.SERIES[k].value_unit)
                     for v, k in zip(view["value"], view["key"])]
    return view[["synced_date", "key", "value", "change_20obs",
                 "change_60obs", "state_label"]]


def _chart(arts: dict, key: str):
    c = arts["chart_data"]
    d = c[c["key"] == key][["date", "value"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    return gr.LinePlot(value=d, x="date", y="value",
                       title=f"{C.SERIES[key].display_name} raw")


def build_app():
    store = cache_store.get_store()
    try:
        status, arts = store.load()
    except Exception as e:  # noqa: BLE001
        with gr.Blocks(title="RiskRadar") as demo:
            gr.Markdown(f"# RiskRadar\n\n캐시를 아직 읽을 수 없습니다: `{e}`")
        return demo

    with gr.Blocks(title="RiskRadar", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# RiskRadar — 미국 매크로 스트레스 계기판")
        with gr.Tab("Market Stress Board"):
            gr.Dataframe(_board_df(arts["signal_matrix"]), wrap=True,
                         interactive=False)
        with gr.Tab("Synced Snapshot"):
            gr.Markdown("모든 지표에 실제 raw 관측이 존재하는 가장 최근 날짜 기준.")
            gr.Dataframe(_synced_df(arts), interactive=False)
        with gr.Tab("Signal Matrix"):
            gr.Dataframe(arts["signal_matrix"], wrap=True, interactive=False)
        with gr.Tab("Charts"):
            for key in C.SERIES_ORDER:
                _chart(arts, key)
        with gr.Tab("Data Status"):
            gr.JSON(status)
        with gr.Tab("Guide"):
            gr.Markdown(GUIDE)
    return demo
