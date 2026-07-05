"""읽기 전용 Gradio UI.

캐시(data_status.json + 산출물)만 읽는다. 절대 refresh 하지 않는다.
내부 컬럼명은 데이터 호환성을 위해 유지하고 사용자 화면에서는 쉬운 한국어 표현만 사용한다.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import gradio as gr
import pandas as pd

from . import cache_store
from . import config as C
from .display_text import LABEL_1M, LABEL_3M, LABEL_5Y, LABEL_10Y, core_name
from .formatting import fmt_change, fmt_pct, fmt_value
from .interpretation_cards import get_interpretation_card
from .indicator_detail_view import render_indicator_detail
from .relationship_guide import RELATIONSHIP_GUIDE
from .today_view import render_today_markdown

KST = ZoneInfo(C.APP_TIMEZONE)

GUIDE_INTRO = r"""
## RiskRadar를 읽는 법

RiskRadar는 미국 시장을 **변동성·신용·경기 사이클·금리**로 나눠 보는 계기판입니다. 하나의 점수로 시장을 단정하지 않고, 현재 어떤 축과 조합이 움직이는지 확인하는 데 초점을 둡니다.

이 앱은 폭락·침체 시점을 예측하거나 매수·매도 타이밍을 정하지 않습니다. 대신 다음 순서로 읽습니다.

1. **현재 상황**에서 6개 핵심 지표의 최신 상태와 한줄 해석을 본다.
2. **오늘의 해석**에서 지표 조합과 보조지표 확인 결과를 본다.
3. **최근 30일**에서 선택한 지표의 흐름과 상세 해석 카드를 본다.
4. 이해가 어려운 조합은 이 탭의 **지표를 같이 보는 법**을 참고한다.

### 표의 쉬운 용어

| 화면 표현 | 실제 계산 | 의미 |
|---|---|---|
| **약 1개월 변화** | 20개 관측치 전 대비 | 달력 1개월과 정확히 같지는 않음 |
| **약 3개월 변화** | 60개 관측치 전 대비 | 실제 관측치 개수 기준 |
| **최근 5년 위치** | 5년 백분위 | 90%면 과거 관측값 약 90%보다 현재값이 높음 |
| **최근 10년 위치** | 10년 백분위 | 장기 역사 속 현재 위치 |

상태 라벨은 수치를 빠르게 읽기 위한 C등급 참고선입니다. 라벨만 보지 말고 **최신값·변화속도·역사적 위치·조합 해석**을 같이 봅니다.
"""

BOARD_HELP = r"""
### 현재 상황 읽는 법

먼저 **HY OAS와 VIX**를 보고 신용스프레드와 주식 변동성이 어떻게 움직이는지 확인합니다. 다음으로 **2년물·30년물·10년 실질금리**의 방향을 보고, **10년-3개월 금리차**는 경기 사이클의 배경으로 분리해서 봅니다.

- `약 1개월 변화`, `약 3개월 변화`는 실제 관측치 20개·60개 기준입니다.
- `최근 5년 위치`, `최근 10년 위치`는 과거 대비 현재 위치입니다.
- `한줄 해석`은 현재 지표 하나를 사실 중심으로 읽는 문장입니다. 전체 시장 결론이 아닙니다.
"""

HISTORY_HELP = r"""
### 최근 30일 변화 읽는 법

매일 저장된 RiskRadar 기록을 모아 최근 30일 동안 각 지표가 어떻게 변했는지 보여줍니다. 같은 날짜에 자동·수동 실행이 여러 번 있었다면 **그 날짜의 마지막 성공 스냅샷 한 개만** 표시합니다.

날짜는 FRED 관측일이 아니라 RiskRadar 저장일입니다. 미국 휴장·공표 지연으로 같은 관측값이 며칠 반복될 수 있으니 `관측일`도 같이 봅니다.
"""

SYNCED_HELP = r"""
### 같은 날짜 비교 읽는 법

각 지표의 최신 관측일은 다를 수 있습니다. 이 탭은 모든 핵심 지표에 실제 원자료가 함께 있는 가장 최근 날짜를 골라 같은 날짜 기준으로 비교합니다.
"""

SIGNAL_MATRIX_HELP = r"""
### 상세 지표표 읽는 법

핵심 6개 지표의 최신값·변화·역사적 위치·상태 근거를 한 번에 보는 상세표입니다. 내부 코드명 대신 사용자용 표현만 보여줍니다.
"""

CHART_HELP = r"""
### 차트 읽는 법

최신값 하나보다 흐름이 중요할 때가 많습니다. 최근 움직임이 급한지 완만한지, 이전 국면과 비교해 지속되는지 확인하세요.
"""


def _days_since(date_str: str) -> int:
    d = pd.to_datetime(date_str).date()
    return (datetime.now(KST).date() - d).days


def _one_line_interpretation(row: pd.Series) -> str:
    key = row["key"]
    state = row["state_label"]
    drop = bool(row.get("drop_flag", False))

    if key == "VIX":
        if state == "평온":
            return "주식시장 기대변동성은 현재 기본 구간입니다. HY OAS와 함께 봅니다."
        if state == "관찰":
            return "주식시장 기대변동성이 평소보다 커진 상태입니다. 지속성과 신용스프레드 동반 여부를 봅니다."
        return "주식시장 기대변동성이 높은 상태입니다. 하루 움직임보다 지속성과 신용시장 동반 여부가 중요합니다."

    if key == "HYOAS":
        if state in ("평온", "중립"):
            return "하이일드 신용스프레드는 현재 큰 확대 상태가 아닙니다. IG OAS와 변화 범위를 같이 봅니다."
        if state == "관찰":
            return "하이일드 신용스프레드가 확대된 상태입니다. 투자등급까지 넓어지는지 확인합니다."
        return "하이일드 신용스프레드가 높은 상태입니다. VIX·IG OAS와 함께 변화 범위를 봅니다."

    if key == "T10Y3M":
        return f"경기 사이클 경로는 현재 '{state}'입니다. 현재 시장 공포와는 별개의 선행축으로 봅니다."

    if drop:
        return "금리가 빠르게 하락한 플래그가 있습니다. 완화 기대인지 경기둔화 우려인지 다른 지표와 구분합니다."
    if state == "안정":
        return "최근 변화속도는 RiskRadar 기준상 기본 구간입니다."
    if state == "상승 관찰":
        return "최근 금리 상승속도가 커진 상태입니다. 다른 만기와 실질·명목 구성요인을 함께 봅니다."
    return "최근 금리 상승속도가 큰 상태입니다. 원인은 다른 금리와 보조지표 조합으로 구분합니다."


def _board_df(matrix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in matrix.iterrows():
        rows.append({
            "지표": core_name(str(r["key"])),
            "상태": r["state_label"],
            "최신값": fmt_value(r["latest_value"], r["value_unit"]),
            "관측일": r["latest_observed_date"],
            "경과일": _days_since(r["latest_observed_date"]),
            LABEL_1M: fmt_change(r["change_20obs"], r["change_unit"]),
            LABEL_3M: fmt_change(r["change_60obs"], r["change_unit"]),
            LABEL_5Y: fmt_pct(r["percentile_5y"]),
            LABEL_10Y: fmt_pct(r["percentile_10y"]),
            "급락": "⚠︎" if r["drop_flag"] else "",
            "한줄 해석": _one_line_interpretation(r),
            "상태 근거": r["state_reason"],
        })
    return pd.DataFrame(rows)


def _synced_df(arts: dict) -> pd.DataFrame:
    s = arts["synced_snapshot"]
    if s.empty:
        return pd.DataFrame([{"안내": "모든 지표가 함께 존재하는 공통 기준일이 아직 없습니다."}])
    rows = []
    for _, r in s.iterrows():
        key = str(r["key"])
        series = C.SERIES[key]
        rows.append({
            "공통 기준일": r["synced_date"],
            "지표": core_name(key),
            "값": fmt_value(r["value"], series.value_unit),
            LABEL_1M: fmt_change(r["change_20obs"], series.change_unit),
            LABEL_3M: fmt_change(r["change_60obs"], series.change_unit),
            "상태": r["state_label"],
        })
    return pd.DataFrame(rows)


def _history_table(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame([{"안내": "저장된 기록이 아직 없습니다. 다음 자동 갱신부터 쌓입니다."}])
    d = history.loc[history["key"] == key].copy()
    if d.empty:
        return pd.DataFrame([{"안내": f"{core_name(key)} 기록이 없습니다."}])
    d = d.sort_values("snapshot_at_kst")
    d["최신값"] = [fmt_value(v, u) for v, u in zip(d["latest_value"], d["value_unit"])]
    d[LABEL_1M] = [fmt_change(v, u) for v, u in zip(d["change_20obs"], d["change_unit"])]
    d[LABEL_3M] = [fmt_change(v, u) for v, u in zip(d["change_60obs"], d["change_unit"])]
    d[LABEL_5Y] = [fmt_pct(v) for v in d["percentile_5y"]]
    d[LABEL_10Y] = [fmt_pct(v) for v in d["percentile_10y"]]
    d["급락"] = ["⚠︎" if x else "" for x in d["drop_flag"]]
    d["지표"] = core_name(key)
    return d[[
        "snapshot_date", "snapshot_at_kst", "지표", "state_label",
        "최신값", "latest_observed_date", LABEL_1M, LABEL_3M, LABEL_5Y, LABEL_10Y,
        "급락", "state_reason",
    ]].rename(columns={
        "snapshot_date": "저장일",
        "snapshot_at_kst": "저장시각(KST)",
        "state_label": "상태",
        "latest_observed_date": "관측일",
        "state_reason": "상태 근거",
    })


def _signal_matrix_df(matrix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in matrix.iterrows():
        rows.append({
            "지표": core_name(str(r["key"])),
            "분류": r["axis"],
            "관측일": r["latest_observed_date"],
            "최신값": fmt_value(r["latest_value"], r["value_unit"]),
            LABEL_1M: fmt_change(r["change_20obs"], r["change_unit"]),
            LABEL_3M: fmt_change(r["change_60obs"], r["change_unit"]),
            LABEL_5Y: fmt_pct(r["percentile_5y"]),
            LABEL_10Y: fmt_pct(r["percentile_10y"]),
            "상태": r["state_label"],
            "급락": "⚠︎" if r["drop_flag"] else "",
            "상태 근거": r["state_reason"],
        })
    return pd.DataFrame(rows)


def _history_plot_data(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["저장일", "최신값"])
    d = history.loc[history["key"] == key, ["snapshot_date", "latest_value"]].copy()
    if d.empty:
        return pd.DataFrame(columns=["저장일", "최신값"])
    d["저장일"] = pd.to_datetime(d["snapshot_date"])
    d["최신값"] = d["latest_value"]
    return d[["저장일", "최신값"]].sort_values("저장일")


def _chart(arts: dict, key: str):
    c = arts["chart_data"]
    d = c[c["key"] == key][["date", "value"]].copy()
    d["날짜"] = pd.to_datetime(d["date"])
    d["값"] = d["value"]
    return gr.LinePlot(
        value=d[["날짜", "값"]], x="날짜", y="값",
        title=f"{core_name(key)} 원자료 흐름",
    )


def build_app():
    store = cache_store.get_store()
    try:
        status, arts = store.load()
    except Exception as e:
        with gr.Blocks(title="RiskRadar") as demo:
            gr.Markdown(f"# RiskRadar\n\n저장된 데이터를 아직 읽을 수 없습니다: `{e}`")
        return demo

    try:
        history = store.load_history(days=30)
        history_error = None
    except Exception as e:
        history = pd.DataFrame()
        history_error = f"최근 기록을 읽을 수 없습니다: {type(e).__name__}: {e}"

    try:
        data_quality = store.load_data_quality()
    except Exception:
        data_quality = {}
    try:
        aux_df = store.load_artifact(status["active_cache_version"], "aux_signal_matrix")
    except Exception:
        aux_df = pd.DataFrame()

    today_md = render_today_markdown(data_quality, aux_df)
    default_key = "HYOAS" if "HYOAS" in C.SERIES_ORDER else C.SERIES_ORDER[0]
    choices = [(core_name(k), k) for k in C.SERIES_ORDER]

    with gr.Blocks(title="RiskRadar") as demo:
        gr.Markdown("# RiskRadar — 미국 매크로 스트레스 계기판")
        gr.Markdown(
            "6개 핵심 지표와 3개 보조지표를 함께 읽어, 현재 어떤 축과 조합이 움직이는지 보여주는 읽기 전용 대시보드입니다. "
            "단일 위험점수나 매매 신호는 만들지 않습니다."
        )

        with gr.Tab("현재 상황"):
            gr.Markdown(BOARD_HELP)
            gr.Dataframe(_board_df(arts["signal_matrix"]), wrap=True, interactive=False)

            gr.Markdown("## 지표별 상세 설명")
            gr.Markdown(
                "궁금한 지표를 펼치면 **현재 데이터와 연결한 해석 → 현재 연결된 조합 → 8칸 상세 설명** 순서로 볼 수 있습니다."
            )
            matrix_by_key = {str(r["key"]): r for _, r in arts["signal_matrix"].iterrows()}
            for key in C.SERIES_ORDER:
                row = matrix_by_key.get(key)
                if row is None:
                    continue
                with gr.Accordion(f"{core_name(key)} 상세 설명 보기", open=False):
                    gr.Markdown(
                        render_indicator_detail(
                            row,
                            data_quality,
                            _one_line_interpretation(row),
                        )
                    )

            with gr.Accordion("현재 조합 해석 전체 보기", open=False):
                gr.Markdown(today_md)

        with gr.Tab("오늘의 해석"):
            gr.Markdown(today_md)

        with gr.Tab("최근 30일"):
            gr.Markdown(HISTORY_HELP)
            if history_error:
                gr.Markdown(f"⚠️ {history_error}")
            selector = gr.Dropdown(choices=choices, value=default_key, label="지표 선택")
            interpretation_card = gr.Markdown(get_interpretation_card(default_key))
            hist_plot = gr.LinePlot(
                value=_history_plot_data(history, default_key),
                x="저장일", y="최신값",
                title="선택 지표의 최근 30일 값 변화",
            )
            hist_table = gr.Dataframe(_history_table(history, default_key), wrap=True, interactive=False)
            selector.change(
                fn=lambda key: (
                    get_interpretation_card(key),
                    _history_plot_data(history, key),
                    _history_table(history, key),
                ),
                inputs=selector,
                outputs=[interpretation_card, hist_plot, hist_table],
            )

        with gr.Tab("같은 날짜 비교"):
            gr.Markdown(SYNCED_HELP)
            gr.Dataframe(_synced_df(arts), interactive=False)

        with gr.Tab("상세 지표표"):
            gr.Markdown(SIGNAL_MATRIX_HELP)
            gr.Dataframe(_signal_matrix_df(arts["signal_matrix"]), wrap=True, interactive=False)

        with gr.Tab("차트"):
            gr.Markdown(CHART_HELP)
            for key in C.SERIES_ORDER:
                _chart(arts, key)

        with gr.Tab("데이터 상태"):
            gr.Markdown("### 데이터 상태\n\n데이터 버전, 마지막 갱신 시각, 지연 지표를 확인하는 운영 점검용 정보입니다.")
            gr.JSON(status)

        with gr.Tab("지표 설명"):
            gr.Markdown(GUIDE_INTRO)
            guide_selector = gr.Dropdown(choices=choices, value=default_key, label="상세 설명을 볼 지표")
            guide_card = gr.Markdown(get_interpretation_card(default_key))
            guide_selector.change(fn=get_interpretation_card, inputs=guide_selector, outputs=guide_card)
            gr.Markdown(RELATIONSHIP_GUIDE)

    return demo
