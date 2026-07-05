"""읽기 전용 Gradio UI.

캐시(data_status.json + 산출물)만 읽는다. 절대 refresh 하지 않는다.
내부 컬럼명은 데이터 호환성을 위해 유지하고 사용자 화면에서는 쉬운 한국어 표현만 사용한다.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import gradio as gr
import pandas as pd

from . import axis_engine, cache_store, interpretation_engine
from . import config as C
from .display_text import (LABEL_1M, LABEL_3M, LABEL_5Y, LABEL_10Y,
                           aux_name, axis_name, core_name, plain_language, state_name)
from .formatting import fmt_change, fmt_pct, fmt_value
from .interpretation_cards import get_interpretation_card
from .indicator_detail_view import render_indicator_detail
from .relationship_guide import RELATIONSHIP_GUIDE
from .today_view import render_today_markdown
from .monthly_view import render_monthly_markdown
from .version import __version__

KST = ZoneInfo(C.APP_TIMEZONE)

GUIDE_INTRO = r"""
## RiskRadar를 읽는 순서

RiskRadar는 미국 시장을 **주식시장 흔들림·기업 자금 부담·경기 흐름·금리 움직임**으로 나눠 보는 계기판입니다. 하나의 점수로 시장을 단정하지 않고, 지금 어떤 부분이 움직이는지와 무엇을 더 확인해야 하는지 보여줍니다.

1. **현재 상황**에서 6개 핵심 지표의 상태와 지금 뜻을 봅니다.
2. **오늘의 해석**에서 여러 지표를 같이 봤을 때 어떤 모습인지 확인합니다.
3. **지난 30일 흐름**에서 한 달 동안 어떤 변화가 생겼다가 사라졌고 무엇이 남았는지 봅니다.
4. 각 지표의 **상세 설명 보기**를 펼쳐, 앱 안의 확인지표와 앱 밖의 발표·뉴스를 어떻게 읽을지 확인합니다.

### `최근 5년·10년 중 현재 위치` 읽는 법

`상위 18% 구간`은 **위험확률 18%가 아닙니다.** 과거 관측값을 낮은 값부터 높은 값까지 줄 세웠을 때 현재 값이 높은 쪽 18% 안에 있다는 뜻입니다.

`하위 13% 구간`은 현재 값이 낮은 쪽 13% 안에 있다는 뜻입니다.

| 화면 표현 | 실제 계산 | 쉬운 뜻 |
|---|---|---|
| **약 1개월 변화** | 20개 관측치 전 대비 | 대략 한 달 전보다 얼마나 변했는지 |
| **약 3개월 변화** | 60개 관측치 전 대비 | 대략 세 달 전보다 얼마나 변했는지 |
| **최근 5년 중 현재 위치** | 최근 5년 안의 상대 위치 | `상위 18% 구간`, `하위 13% 구간`, `중간 구간` |
| **최근 10년 중 현재 위치** | 최근 10년 안의 상대 위치 | 장기적으로 지금 값이 높은 쪽인지 낮은 쪽인지 |

상태 이름은 숫자를 빨리 읽기 위한 간단한 표지입니다. 상태 이름만 보지 말고 **현재값·최근 변화·과거 위치·같이 볼 지표**를 함께 봅니다.
"""
BOARD_HELP = r"""
### 현재 상황 읽는 법

먼저 **신용등급 낮은 기업의 추가금리**와 **주식시장이 예상하는 흔들림(VIX)**을 봅니다. 주식시장만 흔들리는지, 기업들이 회사채를 발행할 때 더 높은 금리를 요구받는지도 같이 확인합니다.

그다음 **2년·30년 국채금리와 물가 영향을 뺀 10년 금리**가 어느 쪽으로 움직이는지 봅니다. 마지막으로 **10년 금리와 3개월 금리의 관계**는 현재 시장 불안과 따로 떼어 경기 흐름의 배경으로 봅니다.

- `상위 18% 구간`은 위험확률이 아니라 과거 값 중 높은 쪽 18% 안에 있다는 뜻입니다.
- `하위 13% 구간`은 과거 값 중 낮은 쪽 13% 안에 있다는 뜻입니다.
- `지금 뜻`은 현재 지표 하나를 읽는 문장입니다. 전체 시장 결론이 아닙니다.
"""

EASY_GLOSSARY = r"""
### 먼저 이것만 알아두면 됩니다

| 화면 이름 | 쉽게 말하면 | 숫자가 오르면 |
|---|---|---|
| **신용등급 낮은 기업의 추가금리** | 신용등급이 낮은 기업이 국채보다 더 얹어줘야 하는 금리 | 시장이 신용등급 낮은 기업에 더 높은 금리를 요구함 |
| **신용등급 높은 기업의 추가금리** | 신용등급이 높은 기업도 국채보다 더 얹어줘야 하는 금리 | 기업 자금 부담 변화가 더 넓게 퍼지는지 확인할 단서 |
| **채권시장이 보는 10년 물가 예상** | 일반 국채와 물가에 따라 원금이 조정되는 국채의 금리 차이 | 시장이 장기 물가를 더 높게 보는 방향 |
| **장기채 추가 보상** | 장기채를 오래 들고 있을 불확실성 때문에 시장이 더 요구하는 보상 | 장기채 수요·공급이나 불확실성 요인을 더 확인 |
| **물가 영향을 뺀 10년 금리** | 물가 영향을 빼고 본 장기금리 | 미래에 받을 돈을 오늘 가치로 계산할 때 더 많이 깎는 방향 |

`추가금리`는 기업이 실제로 내는 대출금리 자체가 아닙니다. **같은 기간의 미국 국채보다 회사채가 얼마나 더 높은 금리를 요구받는지**를 뜻합니다.
"""

HISTORY_HELP = r"""
### 지난 30일 흐름 읽는 법

매일 저장된 RiskRadar 기록을 모아 **한 달 사이 무엇이 달라졌는지, 한때 크게 움직였다가 되돌아온 것은 무엇인지, 아직 남아 있는 변화는 무엇인지** 보여줍니다. 시작값과 현재값만 비교하지 않습니다.

같은 날짜에 자동·수동 실행이 여러 번 있었다면 **그 날짜의 마지막 성공 스냅샷 한 개만** 표시합니다. 날짜는 FRED 관측일이 아니라 RiskRadar 저장일이므로 `관측일`도 같이 봅니다.
"""

SYNCED_HELP = r"""
### 같은 날짜 비교 읽는 법

각 지표의 최신 관측일은 다를 수 있습니다. 이 탭은 모든 핵심 지표에 실제 원자료가 함께 있는 가장 최근 날짜를 골라 같은 날짜 기준으로 비교합니다.
"""

SIGNAL_MATRIX_HELP = r"""
### 전체 지표 비교 읽는 법

핵심 6개 지표의 최신값·변화·과거 위치·표시 이유를 한 번에 보는 표입니다. 내부 코드명 대신 사용자용 표현만 보여줍니다.
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
    code = str(row.get("state_code", ""))
    drop = bool(row.get("drop_flag", False))

    if key == "VIX":
        if code == "calm":
            return "주식시장이 예상하는 흔들림은 현재 평소 수준입니다. 회사채 시장도 조용한지 같이 봅니다."
        if code == "watch":
            return "주식시장이 예상하는 흔들림이 커졌습니다. 며칠 이어지는지와 회사채 시장도 같이 움직이는지 봅니다."
        return "주식시장이 큰 흔들림을 가격에 반영하고 있습니다. 하루 급등인지, 회사채 시장까지 함께 움직이는지가 중요합니다."

    if key == "HYOAS":
        if code in ("calm", "neutral"):
            return "신용등급 낮은 기업이 돈을 빌릴 때 요구받는 추가금리는 아직 크게 벌어지지 않았습니다."
        if code == "watch":
            return "신용등급 낮은 기업이 돈을 빌릴 때 요구받는 추가금리가 커지고 있습니다. 신용등급 높은 기업의 추가금리도 같은 움직임인지 봅니다."
        return "신용등급 낮은 기업이 돈을 빌리는 부담이 크게 커진 방향입니다. 주식시장 흔들림과 신용등급 높은 기업의 추가금리도 같이 봅니다."

    if key == "T10Y3M":
        return f"현재 10년 금리와 3개월 금리의 관계는 '{state_name(code, row.get('state_label'), key=key)}'입니다. 지금의 시장 불안과는 따로 떼어 경기 흐름의 배경으로 봅니다."

    if drop:
        return "금리가 빠르게 내려갔습니다. 좋은 금리인하 기대인지, 경기둔화 우려인지 다른 지표와 함께 봅니다."
    if code == "stable":
        return "최근 금리 변화는 큰 편이 아닙니다."
    if code == "rise_watch":
        return "최근 금리가 눈에 띄게 오르고 있습니다. 다른 만기 금리와 물가 요인을 같이 봅니다."
    return "최근 금리가 빠르게 오르고 있습니다. 어떤 원인인지 다른 금리와 보조지표를 함께 봅니다."


def _board_df(matrix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in matrix.iterrows():
        rows.append({
            "지표": core_name(str(r["key"])),
            "상태": state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=str(r.get("key", ""))),
            "최신값": fmt_value(r["latest_value"], r["value_unit"]),
            "관측일": r["latest_observed_date"],
            "경과일": _days_since(r["latest_observed_date"]),
            LABEL_1M: fmt_change(r["change_20obs"], r["change_unit"]),
            LABEL_3M: fmt_change(r["change_60obs"], r["change_unit"]),
            LABEL_5Y: fmt_pct(r["percentile_5y"]),
            LABEL_10Y: fmt_pct(r["percentile_10y"]),
            "빠르게 내림": "⚠︎" if r["drop_flag"] else "",
            "지금 뜻": _one_line_interpretation(r),
            "왜 이렇게 표시됐나": plain_language(str(r["state_reason"])),
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
            "상태": state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=str(r.get("key", ""))),
        })
    return pd.DataFrame(rows)


def _history_table(history: pd.DataFrame, key: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame([{"안내": "저장된 기록이 아직 없습니다. 다음 자동 갱신부터 쌓입니다."}])
    d = history.loc[history["key"] == key].copy()
    if d.empty:
        return pd.DataFrame([{"안내": f"{core_name(key)} 기록이 없습니다."}])
    d = d.sort_values("snapshot_at_kst")
    if "state_code" in d.columns:
        d["상태"] = [state_name(str(c), str(l), drop=bool(drop), key=key) for c, l, drop in zip(d["state_code"], d["state_label"], d["drop_flag"])]
    else:
        d["상태"] = d["state_label"]
    d["최신값"] = [fmt_value(v, u) for v, u in zip(d["latest_value"], d["value_unit"])]
    d[LABEL_1M] = [fmt_change(v, u) for v, u in zip(d["change_20obs"], d["change_unit"])]
    d[LABEL_3M] = [fmt_change(v, u) for v, u in zip(d["change_60obs"], d["change_unit"])]
    d[LABEL_5Y] = [fmt_pct(v) for v in d["percentile_5y"]]
    d[LABEL_10Y] = [fmt_pct(v) for v in d["percentile_10y"]]
    d["빠르게 내림"] = ["⚠︎" if x else "" for x in d["drop_flag"]]
    d["지표"] = core_name(key)
    d["state_reason"] = d["state_reason"].astype(str).map(plain_language)
    return d[[
        "snapshot_date", "snapshot_at_kst", "지표", "상태",
        "최신값", "latest_observed_date", LABEL_1M, LABEL_3M, LABEL_5Y, LABEL_10Y,
        "빠르게 내림", "state_reason",
    ]].rename(columns={
        "snapshot_date": "저장일",
        "snapshot_at_kst": "저장시각(KST)",
        "latest_observed_date": "관측일",
        "state_reason": "왜 이렇게 표시됐나",
    })


def _signal_matrix_df(matrix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in matrix.iterrows():
        rows.append({
            "지표": core_name(str(r["key"])),
            "무엇을 보는 지표": axis_name(str(r["axis"])),
            "관측일": r["latest_observed_date"],
            "최신값": fmt_value(r["latest_value"], r["value_unit"]),
            LABEL_1M: fmt_change(r["change_20obs"], r["change_unit"]),
            LABEL_3M: fmt_change(r["change_60obs"], r["change_unit"]),
            LABEL_5Y: fmt_pct(r["percentile_5y"]),
            LABEL_10Y: fmt_pct(r["percentile_10y"]),
            "상태": state_name(str(r.get("state_code", "")), str(r.get("state_label", "")), drop=bool(r.get("drop_flag", False)), key=str(r.get("key", ""))),
            "빠르게 내림": "⚠︎" if r["drop_flag"] else "",
            "왜 이렇게 표시됐나": plain_language(str(r["state_reason"])),
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



def _frames_from_chart_data(chart_data: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """기존 캐시의 chart_data를 3축/조합 엔진 입력 프레임으로 복원한다."""
    if chart_data is None or chart_data.empty or "key" not in chart_data.columns:
        return {}
    frames: dict[str, pd.DataFrame] = {}
    for key, group in chart_data.groupby("key", sort=False):
        frame = group.copy()
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame.sort_values("date")
        frames[str(key)] = frame.reset_index(drop=True)
    return frames


def _readings_need_branch_upgrade(readings: list[dict] | None) -> bool:
    """v0.4.4 이전 캐시의 checks에는 결과별 branches가 없다."""
    if not readings:
        return True
    for reading in readings:
        for check in reading.get("checks") or []:
            if not check.get("branches"):
                return True
    return False


def _today_context_with_fallback(data_quality: dict | None, arts: dict,
                                 aux_df: pd.DataFrame) -> dict:
    """옛 캐시에도 오늘의 해석을 표시한다.

    v0.4 이전/초기 v0.4 캐시에는 data_quality.json의 axes/readings가 없을 수 있다.
    이 경우 UI가 이미 읽은 chart_data와 aux_signal_matrix로 같은 규칙 엔진을
    즉석 실행한다. refresh는 하지 않으며 원격 데이터도 새로 가져오지 않는다.
    """
    dq = dict(data_quality or {})
    need_axes = not dq.get("axes")
    need_readings = _readings_need_branch_upgrade(dq.get("readings"))
    if not (need_axes or need_readings):
        return dq

    frames = _frames_from_chart_data(arts.get("chart_data", pd.DataFrame()))
    if not frames:
        return dq

    if need_axes:
        try:
            dq["axes"] = axis_engine.composite_view(frames).to_dict()
        except Exception:
            pass

    if need_readings:
        try:
            aux = {}
            aux_status = {}
            if aux_df is not None and not aux_df.empty:
                for _, row in aux_df.iterrows():
                    key = str(row.get("key", ""))
                    if not key:
                        continue
                    aux[key] = SimpleNamespace(direction=str(row.get("direction", "판정불가")))
                    aux_status[key] = str(row.get("staleness_label", "unknown"))
            dq["readings"] = [
                reading.to_dict()
                for reading in interpretation_engine.read_all(
                    frames, aux, aux_status=aux_status
                )
            ]
        except Exception:
            pass
    return dq

def _aux_status_df(aux_df: pd.DataFrame) -> pd.DataFrame:
    """보조지표 수집 상태를 사용자용 진단 표로 보여준다."""
    cols = ["지표", "FRED 시리즈", "수집 상태", "사용 중인 관측일", "최신성", "오류 내용"]
    if aux_df is None or aux_df.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    status_map = {
        "ok": "정상 수집",
        "carried_forward": "과거 마지막 성공값 사용",
        "failed": "수집 실패",
    }
    fresh_map = {
        "normal": "최신",
        "delayed": "업데이트 지연",
        "stale": "오래된 자료 · 현재 해석에서 제외",
    }
    for _, r in aux_df.iterrows():
        key = str(r.get("key", ""))
        rows.append({
            "지표": aux_name(key),
            "FRED 시리즈": str(r.get("series_id", "-")),
            "수집 상태": status_map.get(str(r.get("fetch_status", "failed")), str(r.get("fetch_status", "확인 불가"))),
            "사용 중인 관측일": str(r.get("latest_date", "-")) if pd.notna(r.get("latest_date")) else "-",
            "최신성": fresh_map.get(str(r.get("staleness_label", "unknown")), "확인 불가"),
            "오류 내용": plain_language(str(r.get("error", ""))) if str(r.get("error", "")) not in {"", "nan", "None"} else "-",
        })
    return pd.DataFrame(rows, columns=cols)


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

    frames = _frames_from_chart_data(arts.get("chart_data", pd.DataFrame()))
    data_quality = _today_context_with_fallback(data_quality, arts, aux_df)
    today_md = render_today_markdown(data_quality, aux_df)
    monthly_md = render_monthly_markdown(history, aux_df)
    default_key = "HYOAS" if "HYOAS" in C.SERIES_ORDER else C.SERIES_ORDER[0]
    choices = [(core_name(k), k) for k in C.SERIES_ORDER]

    with gr.Blocks(title="RiskRadar") as demo:
        gr.Markdown("# RiskRadar — 미국 시장 흐름 신호판")
        gr.Markdown(
            "6개 핵심 지표와 3개 보조 지표를 함께 읽어, 지금 어떤 부분이 움직이고 다음에 무엇을 확인할지 보여주는 읽기 전용 대시보드입니다. "
            "단일 위험점수나 매매 신호는 만들지 않습니다."
        )

        with gr.Tab("현재 상황"):
            gr.Markdown(BOARD_HELP)
            with gr.Accordion("용어가 어렵다면 먼저 보기", open=False):
                gr.Markdown(EASY_GLOSSARY)
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
                        plain_language(render_indicator_detail(
                            row,
                            data_quality,
                            _one_line_interpretation(row),
                            frames=frames,
                            aux_df=aux_df,
                            matrix=arts["signal_matrix"],
                        ))
                    )

            with gr.Accordion("지표를 함께 본 해석 전체 보기", open=False):
                gr.Markdown(today_md)

        with gr.Tab("오늘의 해석"):
            gr.Markdown(today_md)

        with gr.Tab("지난 30일 흐름"):
            gr.Markdown(HISTORY_HELP)
            if history_error:
                gr.Markdown(f"⚠️ {history_error}")
            gr.Markdown(monthly_md)
            gr.Markdown("---\n\n## 지표별 30일 기록")
            selector = gr.Dropdown(choices=choices, value=default_key, label="지표 선택")
            interpretation_card = gr.Markdown(plain_language(get_interpretation_card(default_key)))
            hist_plot = gr.LinePlot(
                value=_history_plot_data(history, default_key),
                x="저장일", y="최신값",
                title="선택 지표의 지난 30일 값 변화",
            )
            hist_table = gr.Dataframe(_history_table(history, default_key), wrap=True, interactive=False)
            selector.change(
                fn=lambda key: (
                    plain_language(get_interpretation_card(key)),
                    _history_plot_data(history, key),
                    _history_table(history, key),
                ),
                inputs=selector,
                outputs=[interpretation_card, hist_plot, hist_table],
            )

        with gr.Tab("같은 날짜 비교"):
            gr.Markdown(SYNCED_HELP)
            gr.Dataframe(_synced_df(arts), interactive=False)

        with gr.Tab("전체 지표 비교"):
            gr.Markdown(SIGNAL_MATRIX_HELP)
            gr.Dataframe(_signal_matrix_df(arts["signal_matrix"]), wrap=True, interactive=False)

        with gr.Tab("차트"):
            gr.Markdown(CHART_HELP)
            for key in C.SERIES_ORDER:
                _chart(arts, key)

        with gr.Tab("데이터 상태"):
            gr.Markdown("### 데이터 상태\n\n데이터 버전, 마지막 갱신 시각, 보조지표 수집 실패와 과거값 사용 여부를 확인하는 운영 점검용 정보입니다.")
            data_code_version = str(status.get("code_version") or data_quality.get("code_version") or "기록 없음")
            gr.Markdown(
                f"- **현재 화면 코드 버전:** `{__version__}`\n"
                f"- **마지막 데이터 생성 코드 버전:** `{data_code_version}`"
            )
            if data_code_version not in {"기록 없음", __version__}:
                gr.Markdown("⚠️ 화면 코드와 마지막 배치 코드 버전이 다릅니다. 보조지표가 계속 비어 있다면 GitHub 배치가 최신 코드를 실행하는지 먼저 확인하세요.")
            gr.Markdown("#### 보조지표 수집 상태")
            gr.Dataframe(_aux_status_df(aux_df), wrap=True, interactive=False)
            with gr.Accordion("원본 상태 정보 보기", open=False):
                gr.JSON(status)
                gr.JSON(data_quality)

        with gr.Tab("지표 설명"):
            gr.Markdown(GUIDE_INTRO)
            guide_selector = gr.Dropdown(choices=choices, value=default_key, label="상세 설명을 볼 지표")
            guide_card = gr.Markdown(plain_language(get_interpretation_card(default_key)))
            guide_selector.change(fn=lambda key: plain_language(get_interpretation_card(key)), inputs=guide_selector, outputs=guide_card)
            gr.Markdown(plain_language(RELATIONSHIP_GUIDE))

    return demo
