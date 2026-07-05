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
from .today_view import render_today_markdown
from .formatting import fmt_change, fmt_pct, fmt_value
from .interpretation_cards import get_interpretation_card

KST = ZoneInfo(C.APP_TIMEZONE)

GUIDE = """\
## RiskRadar를 읽는 법

RiskRadar는 미국 시장의 **변동성, 신용, 금리, 실질금리, 수익률곡선**을 따로 보여주는
매크로 스트레스 계기판입니다. 하나의 점수로 시장을 단정하지 않고, 어떤 축에서 압력이
올라오는지 분해해서 보는 용도입니다.

이 앱은 주식 폭락, 경기침체, 환율, 시장 과열, 매수·매도 타이밍을 예측하지 않습니다.
상태 라벨은 투자 판단이 아니라 수치를 빠르게 읽기 위한 보조 장치입니다. 최종 판단은
**최신값, 관측일, 20obs/60obs 변화, 5년·10년 백분위, 차트**를 함께 봐야 합니다.

### 핵심 지표 설명

| 지표 | 쉽게 말하면 | 높아지면 보통 무엇을 뜻하나 | 읽을 때 주의점 |
|---|---|---|---|
| **VIX** | 미국 주식시장 옵션이 반영하는 단기 변동성, 흔히 공포지수라고 부르는 지표 | 주식시장이 단기 충격이나 불확실성을 크게 가격에 반영 중 | VIX만 높다고 신용위기라고 보면 안 됩니다. **HY OAS와 같이 상승**할 때 더 위험하게 봅니다. |
| **HY OAS** | 투기등급 회사채가 국채보다 얼마나 더 높은 금리를 요구받는지 보여주는 신용 스프레드 | 부실기업·저신용 기업에 대한 경계가 커지고, 신용시장이 얼어붙는 방향 | RiskRadar에서 가장 중요한 신용 스트레스 지표입니다. VIX보다 느리지만 더 본질적인 경우가 많습니다. |
| **T10Y3M** | 미국 10년 국채금리에서 3개월 국채금리를 뺀 값, 수익률곡선 기울기 | 음수면 단기금리가 장기금리보다 높은 역전 상태 | 현재 시장 스트레스라기보다 **경기 사이클 배경**입니다. 역전 자체보다 장기역전 후 재정상화 과정도 같이 봅니다. |
| **30Y** | 미국 30년 장기국채 금리 | 장기 자금조달 비용과 할인율 부담 상승 | 절대 수준보다 **20obs/60obs 변화속도**가 중요합니다. 급등은 금리 충격, 급락은 경기둔화 신호일 수도 있습니다. |
| **2Y** | 미국 2년 국채금리, 통화정책 기대에 민감한 금리 | 연준 금리 경로가 더 높거나 오래갈 가능성 반영 | 장기금리보다 정책 기대를 더 빠르게 반영합니다. 주식에는 유동성 압박으로 작용할 수 있습니다. |
| **10Y Real** | 물가연동국채 기준 10년 실질금리 | 인플레이션을 뺀 실질 할인율 상승 | 성장주·장기자산에는 부담이 되기 쉽습니다. 명목금리보다 금융여건 압박을 더 직접적으로 보여줄 때가 있습니다. |

### 표 컬럼 설명

| 컬럼 | 뜻 | 해석 방법 |
|---|---|---|
| **상태** | 현재 지표가 평온·관찰·스트레스 등 어느 구간인지 표시 | 라벨만 보지 말고 근거와 변화율을 같이 봅니다. |
| **최신값** | FRED에서 가져온 가장 최근 원자료 관측값 | 단위가 지표마다 다릅니다. VIX는 index, HY OAS와 T10Y3M은 bp, 금리는 %입니다. |
| **관측일 / 경과일** | 실제 원자료가 마지막으로 관측된 날짜와 오늘 기준 며칠 지났는지 | 미국 휴장·공표 지연 때문에 며칠 차이가 날 수 있습니다. 너무 오래되면 최신 판단에 쓰기 어렵습니다. |
| **20obs / 60obs** | 최근 20개·60개 관측치 전과 비교한 변화량 | 달력 기준 20일/60일이 아니라 **실제 관측치 개수 기준**입니다. 대략 1개월·3개월 변화로 보면 됩니다. |
| **5Y% / 10Y%** | 과거 5년·10년 중 현재값이 어느 위치인지 보는 백분위 | 90%면 최근 10년 기준으로 상당히 높은 편이라는 뜻입니다. 미래 데이터를 쓰지 않는 point-in-time 계산입니다. |
| **급락** | 금리 지표가 짧은 기간에 크게 하락했는지 표시 | 좋은 신호로만 보면 안 됩니다. 금리 급락은 완화 기대일 수도 있지만 경기둔화 공포일 수도 있습니다. |
| **근거** | 상태 라벨이 붙은 이유를 한 문장으로 요약 | 가장 먼저 읽어야 하는 설명 칸입니다. |

### 상태 라벨을 과신하면 안 되는 이유

- **평온**은 위험이 없다는 뜻이 아니라, 이 지표 기준으로 아직 스트레스가 크지 않다는 뜻입니다.
- **관찰**은 매도 신호가 아니라, 변화가 커졌으니 다른 지표와 함께 보라는 뜻입니다.
- **스트레스**는 시장이 이미 위험을 가격에 반영하고 있다는 뜻이지, 앞으로 반드시 더 하락한다는 뜻은 아닙니다.
- **T10Y3M의 역전/재정상화**는 단기 매매 신호가 아니라 경기 사이클을 읽기 위한 배경 신호입니다.
"""

BOARD_HELP = """\
### Market Stress Board 읽는 법

이 화면이 메인입니다. 먼저 **HY OAS와 VIX**를 보고 신용 스트레스와 주식 변동성이 같이
올라오는지 확인하고, 그다음 **2Y·30Y·10Y Real**의 변화속도로 금리 압박을 봅니다.
**T10Y3M**은 지금 당장 위험하다는 신호가 아니라 경기 사이클 배경으로 읽는 게 맞습니다.

- `20obs`, `60obs`는 달력 일수가 아니라 실제 관측치 개수 기준 변화입니다.
- `5Y%`, `10Y%`는 과거 대비 현재 위치입니다. 90% 근처면 역사적으로 높은 구간입니다.
- `급락` 표시는 금리 급락 플래그입니다. 완화 기대일 수도, 경기둔화 공포일 수도 있어 단독 해석은 위험합니다.
"""

HISTORY_HELP = """\
### 30D History 읽는 법

이 탭은 HF Dataset에 저장된 과거 `versions/<cache_version>/signal_matrix.parquet`를 읽어서
최근 30일 동안 RiskRadar가 매일 어떤 상태였는지 보여줍니다. 위의 선택 상자에서 지표를 고르면
그 지표의 날짜별 최신값, 상태, 20obs/60obs 변화, 백분위, 판정 근거를 확인할 수 있습니다.

주의할 점은, 여기의 날짜는 **FRED 관측일**이 아니라 **RiskRadar가 그날 저장한 스냅샷 날짜**입니다.
미국 휴장이나 데이터 공표 지연이 있으면 같은 관측값이 며칠 반복될 수 있습니다. 그래서 표의 `관측일`도 같이 봐야 합니다.
"""

SYNCED_HELP = """\
### Synced Snapshot 읽는 법

각 지표의 최신 관측일은 서로 다를 수 있습니다. 이 탭은 모든 지표가 동시에 실제 raw 관측값을
가진 가장 최근 날짜만 골라서 보여줍니다. 지표끼리 같은 날짜 기준으로 비교하고 싶을 때 씁니다.
"""

SIGNAL_MATRIX_HELP = """\
### Signal Matrix 읽는 법

운영·점검용 원본 산출표입니다. Market Stress Board보다 컬럼이 더 많고 가공이 덜 되어 있습니다.
일반 사용자는 Market Stress Board, 30D History, Charts 위주로 보면 충분합니다.
"""

CHART_HELP = """\
### Charts 읽는 법

차트는 상태 라벨보다 중요할 때가 많습니다. 최신값 하나만 보지 말고, 최근 상승·하락 속도가
과거 위기 구간과 비교해 빠른지 천천히 올라오는지 확인하세요.
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


def _history_table(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame([{"info": "저장된 히스토리가 아직 없습니다. 다음 자동 refresh부터 쌓입니다."}])
    d = history.loc[history["key"] == key].copy()
    if d.empty:
        return pd.DataFrame([{"info": f"{key} 히스토리가 없습니다."}])
    d = d.sort_values("snapshot_at_kst")
    d["최신값"] = [fmt_value(v, u) for v, u in zip(d["latest_value"], d["value_unit"])]
    d["20obs"] = [fmt_change(v, u) for v, u in zip(d["change_20obs"], d["change_unit"])]
    d["60obs"] = [fmt_change(v, u) for v, u in zip(d["change_60obs"], d["change_unit"])]
    d["5Y%"] = [fmt_pct(v) for v in d["percentile_5y"]]
    d["10Y%"] = [fmt_pct(v) for v in d["percentile_10y"]]
    d["급락"] = ["⚠︎" if x else "" for x in d["drop_flag"]]
    return d[[
        "snapshot_date", "snapshot_at_kst", "display_name", "state_label",
        "최신값", "latest_observed_date", "20obs", "60obs", "5Y%", "10Y%",
        "급락", "state_reason",
    ]].rename(columns={
        "snapshot_date": "저장일",
        "snapshot_at_kst": "저장시각(KST)",
        "display_name": "지표",
        "state_label": "상태",
        "latest_observed_date": "관측일",
        "state_reason": "근거",
    })


def _history_plot_data(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["snapshot_date", "latest_value"])
    d = history.loc[history["key"] == key, ["snapshot_date", "latest_value"]].copy()
    if d.empty:
        return pd.DataFrame(columns=["snapshot_date", "latest_value"])
    d["snapshot_date"] = pd.to_datetime(d["snapshot_date"])
    return d.sort_values("snapshot_date")


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

    try:
        history = store.load_history(days=30)
        history_error = None
    except Exception as e:  # noqa: BLE001 - 히스토리 실패가 최신 대시보드를 깨면 안 됨
        history = pd.DataFrame()
        history_error = f"히스토리를 읽을 수 없습니다: {type(e).__name__}: {e}"

    # 오늘의 해석용 데이터 (실패해도 대시보드를 깨지 않음)
    try:
        data_quality = store.load_data_quality()
    except Exception:  # noqa: BLE001
        data_quality = {}
    try:
        aux_df = store.load_artifact(status["active_cache_version"], "aux_signal_matrix")
    except Exception:  # noqa: BLE001
        aux_df = pd.DataFrame()

    default_key = "HYOAS" if "HYOAS" in C.SERIES_ORDER else C.SERIES_ORDER[0]
    choices = [(C.SERIES[k].display_name, k) for k in C.SERIES_ORDER]

    with gr.Blocks(title="RiskRadar", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# RiskRadar — 미국 매크로 스트레스 계기판")
        gr.Markdown(
            "미국 시장 스트레스를 변동성·신용·금리·실질금리·수익률곡선으로 나눠 보는 읽기 전용 대시보드입니다. "
            "예측 모델이나 매매 신호가 아니라, 현재 시장 압력이 어느 축에서 커지는지 확인하는 도구입니다."
        )
        with gr.Tab("Market Stress Board"):
            gr.Markdown(BOARD_HELP)
            gr.Dataframe(_board_df(arts["signal_matrix"]), wrap=True,
                         interactive=False)
        with gr.Tab("오늘의 해석"):
            gr.Markdown(render_today_markdown(data_quality, aux_df))
        with gr.Tab("30D History"):
            gr.Markdown(HISTORY_HELP)
            if history_error:
                gr.Markdown(f"⚠️ {history_error}")
            selector = gr.Dropdown(choices=choices, value=default_key,
                                   label="지표 선택")
            interpretation_card = gr.Markdown(get_interpretation_card(default_key))
            hist_plot = gr.LinePlot(
                value=_history_plot_data(history, default_key),
                x="snapshot_date", y="latest_value",
                title="선택 지표의 최근 30일 저장값 변화",
            )
            hist_table = gr.Dataframe(_history_table(history, default_key),
                                      wrap=True, interactive=False)
            selector.change(
                fn=lambda key: (
                    get_interpretation_card(key),
                    _history_plot_data(history, key),
                    _history_table(history, key),
                ),
                inputs=selector,
                outputs=[interpretation_card, hist_plot, hist_table],
            )
        with gr.Tab("Synced Snapshot"):
            gr.Markdown(SYNCED_HELP)
            gr.Dataframe(_synced_df(arts), interactive=False)
        with gr.Tab("Signal Matrix"):
            gr.Markdown(SIGNAL_MATRIX_HELP)
            gr.Dataframe(arts["signal_matrix"], wrap=True, interactive=False)
        with gr.Tab("Charts"):
            gr.Markdown(CHART_HELP)
            for key in C.SERIES_ORDER:
                _chart(arts, key)
        with gr.Tab("Data Status"):
            gr.Markdown("### Data Status\n\n캐시 버전, 마지막 갱신 시각, 산출물 위치를 확인하는 운영 점검용 정보입니다.")
            gr.JSON(status)
        with gr.Tab("Guide"):
            gr.Markdown(GUIDE)
    return demo
