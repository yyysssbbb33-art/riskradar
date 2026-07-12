"""지난 30일의 '과정'을 읽는 요약.

시작값과 현재값만 비교하지 않는다. 기간 중 크게 움직였다가 되돌아온 경우와
현재 남아 있는 추세를 함께 본다. 원인관계나 위험점수는 만들지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config as C
from .display_text import aux_name, core_name, plain_language
from .formatting import fmt_change, fmt_value
from . import state_rules as SR


# 내부 latest_value 단위 기준. 과거 한 달 안의 움직임을 '설명할 만한 변화'로
# 잡기 위한 C등급 초기값이며 학술 기준이 아니다.
MATERIAL_MOVE = {
    "VIX": 5.0,      # index point
    "HYOAS": 50.0,  # bp
    "T10Y3M": 30.0, # bp
    "DGS30": 0.25,  # %p (25bp)
    "DGS2": 0.25,
    "DFII10": 0.25,
}

RATE_DIRECTION_MOVE = 0.10  # %p (10bp)


def reconstruct_history_from_chart_data(chart_data: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    """최신 캐시의 과거 시계열로 지난 ``days``일 기록을 즉석 재구성한다.

    저장 스냅샷이 없어도 ``chart_data``에는 핵심 6개 지표의 과거 관측값과
    point-in-time 상태가 들어 있다. 이를 signal_matrix 스냅샷과 비슷한 형태로
    바꿔 월간 흐름 엔진과 표/차트가 그대로 사용할 수 있게 한다.

    주의: 이것은 당시 앱 화면의 보존본이 아니라 *현재 코드 규칙으로 계산된
    과거 관측일 기준 기록*이다.
    """
    if chart_data is None or chart_data.empty or "key" not in chart_data.columns or "date" not in chart_data.columns:
        return pd.DataFrame()

    d = chart_data.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.loc[d["date"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    latest_date = d["date"].max()
    cutoff = latest_date - pd.Timedelta(days=max(1, int(days)))
    d = d.loc[d["date"] >= cutoff].copy()
    if d.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for _, row in d.sort_values(["date", "key"]).iterrows():
        key = str(row.get("key", ""))
        if key not in C.SERIES:
            continue
        spec = C.SERIES[key]
        observed = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
        try:
            reason = SR.state_reason(key, row)
        except Exception:
            reason = str(row.get("state_label", ""))
        rows.append({
            "cache_version": "reconstructed-from-chart-data",
            "snapshot_at_kst": f"{observed} 00:00:00",
            "snapshot_date": observed,
            "history_source": "reconstructed",
            "series_id": spec.series_id,
            "key": key,
            "display_name": spec.display_name,
            "axis": spec.axis,
            "latest_observed_date": observed,
            "latest_value": row.get("value"),
            "value_unit": spec.value_unit,
            "change_20obs": row.get("change_20obs"),
            "change_60obs": row.get("change_60obs"),
            "change_unit": spec.change_unit,
            "percentile_3y": row.get("percentile_3y"),
            "percentile_5y": row.get("percentile_5y"),
            "percentile_10y": row.get("percentile_10y"),
            "state_code": row.get("state_code", ""),
            "state_label": row.get("state_label", ""),
            "state_reason": reason,
            "drop_flag": bool(row.get("drop_flag", False)),
        })
    return pd.DataFrame(rows).sort_values(["snapshot_at_kst", "key"]).reset_index(drop=True)


@dataclass(frozen=True)
class MonthStat:
    key: str
    start: float
    end: float
    high: float
    low: float
    net: float
    excursion: float
    reverted: bool
    remaining: bool
    first_date: str
    last_date: str


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(out) else out


def _stats(history: pd.DataFrame) -> dict[str, MonthStat]:
    if history is None or history.empty or "key" not in history.columns:
        return {}
    out: dict[str, MonthStat] = {}
    for key, group in history.groupby("key", sort=False):
        if str(key) not in C.SERIES:
            continue
        d = group.copy()
        sort_col = "snapshot_at_kst" if "snapshot_at_kst" in d.columns else "snapshot_date"
        d = d.sort_values(sort_col)
        vals = pd.to_numeric(d["latest_value"], errors="coerce").dropna()
        if len(vals) < 2:
            continue
        start, end = float(vals.iloc[0]), float(vals.iloc[-1])
        high, low = float(vals.max()), float(vals.min())
        net = end - start
        excursion = max(abs(high - start), abs(low - start))
        threshold = MATERIAL_MOVE[str(key)]
        reverted = excursion >= threshold and abs(net) <= max(threshold * 0.35, excursion * 0.35)
        remaining = abs(net) >= threshold * 0.60
        out[str(key)] = MonthStat(
            key=str(key), start=start, end=end, high=high, low=low,
            net=net, excursion=excursion, reverted=reverted, remaining=remaining,
            first_date=str(d.iloc[0].get("snapshot_date", "")),
            last_date=str(d.iloc[-1].get("snapshot_date", "")),
        )
    return out


def _value_text(key: str, value: float) -> str:
    return fmt_value(value, C.SERIES[key].value_unit)


def _net_text(key: str, net: float) -> str:
    s = C.SERIES[key]
    change = net * s.change_to_bp
    return fmt_change(change, s.change_unit)


def _direction_from_net(key: str, net: float) -> str:
    threshold = MATERIAL_MOVE[key] * 0.40
    if net >= threshold:
        return "올랐습니다"
    if net <= -threshold:
        return "내렸습니다"
    return "시작 때와 큰 차이가 없습니다"


def _is_changed_row(key: str, row: pd.Series) -> bool:
    code = str(row.get("state_code", ""))
    if key == "VIX":
        return code in {"watch", "stress"}
    if key == "HYOAS":
        return code in {"watch", "stress"}
    if key == "T10Y3M":
        return code not in {"", "normal"}
    if key in {"DGS30", "DGS2", "DFII10"}:
        return code in {"rise_watch", "rate_shock"} or bool(row.get("drop_flag", False))
    return False


def _first_new_changes(history: pd.DataFrame) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    if history is None or history.empty:
        return events
    for key, group in history.groupby("key", sort=False):
        key = str(key)
        if key not in C.SERIES:
            continue
        d = group.sort_values("snapshot_at_kst" if "snapshot_at_kst" in group.columns else "snapshot_date")
        changed = [_is_changed_row(key, row) for _, row in d.iterrows()]
        # 기간 시작부터 이미 켜져 있던 상태는 '이번 달 새로 생긴 변화'로 세지 않는다.
        for i in range(1, len(changed)):
            if changed[i] and not changed[i - 1]:
                events.append((str(d.iloc[i].get("snapshot_date", "")), key))
                break
    return sorted(events)


def _aux_row(aux_df: pd.DataFrame | None, key: str) -> pd.Series | None:
    if aux_df is None or aux_df.empty or "key" not in aux_df.columns:
        return None
    hit = aux_df.loc[aux_df["key"].astype(str) == key]
    return None if hit.empty else hit.iloc[-1]


def _aux_direction_text(aux_df: pd.DataFrame | None, key: str) -> str:
    row = _aux_row(aux_df, key)
    if row is None:
        return "확인 불가"
    if str(row.get("staleness_label", "")) == "stale":
        return "자료가 오래돼 현재 해석에서 제외"
    direction = str(row.get("direction", "확인 불가"))
    return {
        "상승": "상승",
        "하락": "하락",
        "보합": "뚜렷한 움직임 없음",
        "확인 불가": "확인 불가",
    }.get(direction, direction)


def _rate_direction(stat: MonthStat | None) -> str:
    if stat is None:
        return "확인 불가"
    if stat.net >= RATE_DIRECTION_MOVE:
        return "상승"
    if stat.net <= -RATE_DIRECTION_MOVE:
        return "하락"
    return "큰 방향 없음"


def render_monthly_markdown(history: pd.DataFrame, aux_df: pd.DataFrame | None = None,
                            credit_node_history: pd.DataFrame | None = None,
                            credit_episode: dict | None = None) -> str:
    stats = _stats(history)
    if not stats:
        return (
            "## 지난 30일 흐름\n\n"
            "아직 한 달 흐름을 해석할 만큼 과거 관측 데이터가 없습니다."
        )

    lines = [
        "## 지난 30일 요약",
        "",
        "시작값과 현재값만 비교하지 않고, **기간 중 크게 움직였다가 되돌아온 변화와 현재 남아 있는 추세**를 함께 봅니다.",
        "",
        "> 이 요약은 원인이나 위험을 확정하지 않습니다. 지난 한 달 동안 데이터에서 실제로 나타난 경로를 정리합니다.",
    ]

    # 1) 가장 달라진 것: 자기 지표별 기준 대비 순위
    ranked = sorted(
        stats.values(),
        key=lambda st: abs(st.net) / max(MATERIAL_MOVE[st.key], 1e-9),
        reverse=True,
    )
    lines += ["", "### 한 달 사이 어떻게 달라졌나"]
    for st in ranked[:3]:
        lines.append(
            f"- **{core_name(st.key, short=True)}:** {_value_text(st.key, st.start)} → {_value_text(st.key, st.end)}. "
            f"한 달 전체로는 {_direction_from_net(st.key, st.net)} ({_net_text(st.key, st.net)})."
        )

    # 2) 되돌림
    reverted = [st for st in ranked if st.reverted]
    lines += ["", "### 한때 크게 움직였다가 되돌아온 것"]
    if reverted:
        for st in reverted[:3]:
            peak = st.high if abs(st.high - st.start) >= abs(st.low - st.start) else st.low
            lines.append(
                f"- **{core_name(st.key, short=True)}:** {_value_text(st.key, st.start)}에서 기간 중 {_value_text(st.key, peak)}까지 움직였지만 "
                f"현재는 {_value_text(st.key, st.end)}입니다. 시작과 현재만 보면 놓칠 수 있는 월중 움직임입니다."
            )
    else:
        lines.append("- 크게 움직인 뒤 시작점 근처로 돌아온 지표는 뚜렷하지 않습니다.")

    # 3) 남은 변화
    remaining = [st for st in ranked if st.remaining]
    lines += ["", "### 현재 남아 있는 추세"]
    if remaining:
        for st in remaining[:4]:
            direction = "높은" if st.net > 0 else "낮은"
            lines.append(
                f"- **{core_name(st.key, short=True)}:** 기간 시작보다 현재가 {direction} 상태입니다 "
                f"({_net_text(st.key, st.net)})."
            )
    else:
        lines.append("- 기간 시작과 비교해 현재까지 남아 있는 뚜렷한 추세는 없습니다.")

    return plain_language("\n".join(lines))
