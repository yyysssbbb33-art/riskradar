"""지난 30일의 '과정'을 읽는 요약.

시작값과 현재값만 비교하지 않는다. 기간 중 크게 움직였다가 되돌아온 경우,
계속 이어지는 변화, 새 변화가 처음 잡힌 순서, 2년·30년 금리의 방향을 함께 본다.
원인관계나 위험점수는 만들지 않는다.
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
        "상승": "오르는 중",
        "하락": "내리는 중",
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
        "## 지난 30일 흐름",
        "",
        "시작값과 현재값만 비교하지 않고, **기간 중 크게 움직였다가 되돌아온 변화·계속 이어지는 변화·처음 확인된 날짜**를 함께 봅니다.",
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
    lines += ["", "### 계속 이어지는 변화"]
    if remaining:
        for st in remaining[:4]:
            direction = "높은" if st.net > 0 else "낮은"
            lines.append(
                f"- **{core_name(st.key, short=True)}:** 기간 시작보다 현재가 {direction} 상태입니다 "
                f"({_net_text(st.key, st.net)})."
            )
    else:
        lines.append("- 기간 시작과 비교해 크게 계속 이어지는 변화는 뚜렷하지 않습니다.")

    # 4) 새 변화가 처음 확인된 날짜. 실제 선행/후행 엔진이 아니다.
    events = _first_new_changes(history)
    lines += ["", "### 새 변화가 처음 확인된 날짜"]
    if events:
        for date, key in events[:5]:
            lines.append(f"- **{date}:** {core_name(key, short=True)}에서 평소와 다른 움직임이 처음 잡혔습니다.")
        lines.append("\n> 날짜를 나열할 뿐 선행·후행이나 원인을 주장하지 않습니다. 지표별 판정 규칙 차이도 있기 때문입니다.")
    else:
        lines.append("- 기간 중 기본 상태에서 새 변화 상태로 바뀐 전환은 뚜렷하지 않습니다.")

    # 5) 2Y/30Y
    d2 = _rate_direction(stats.get("DGS2"))
    d30 = _rate_direction(stats.get("DGS30"))
    lines += ["", "### 2년 금리와 30년 금리는 어떻게 움직였나"]
    if d2 == "하락" and d30 == "상승":
        lines.append("- **2년 금리는 내리고 30년 금리는 올랐습니다.** 가까운 기준금리 예상과 장기금리를 움직이는 힘이 서로 달랐을 가능성을 확인합니다.")
    elif d2 == "상승" and d30 == "하락":
        lines.append("- **2년 금리는 오르고 30년 금리는 내렸습니다.** 가까운 기준금리 예상은 높아졌지만 장기 쪽은 다른 방향이었습니다.")
    elif d2 == "상승" and d30 == "상승":
        lines.append("- **2년·30년 금리가 함께 올랐습니다.** 단기와 장기 금리에 공통으로 작용한 요인이 있는지 확인합니다.")
    elif d2 == "하락" and d30 == "하락":
        lines.append("- **2년·30년 금리가 함께 내렸습니다.** 물가 부담 완화인지 경기 둔화 우려인지 회사채 추가 금리와 고용 흐름으로 구분합니다.")
    else:
        lines.append(f"- 2년 금리: **{d2}**, 30년 금리: **{d30}**. 한 달 전체에서 뚜렷한 공통 방향은 제한적입니다.")

    # 6) 신용 범위·지속 엔진
    credit = credit_episode or {}
    current = credit.get("current") or {}
    episode = current.get("episode") or {}
    nodes = current.get("nodes") or {}
    if current:
        lines += ["", "### 기업 신용 범위와 지속"]
        lines.append(f"- **변화 흐름 상태:** {episode.get('state_label', '현재 변화 흐름 없음')}")
        lines.append(f"- **현재 변화가 나타난 곳:** {current.get('scope_text', '확인 불가')}")
        for key in ("HY", "BBB", "A", "CP"):
            row = nodes.get(key) or {}
            if row.get("available"):
                lines.append(f"- **{row.get('name', key)}:** {row.get('state_label', '확인 불가')}")
        if credit_node_history is not None and not credit_node_history.empty and {"date", "node", "state"}.issubset(credit_node_history.columns):
            ch = credit_node_history.copy()
            ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
            ch = ch.loc[ch["date"].notna()].sort_values(["node", "date"])
            if not ch.empty:
                cutoff = ch["date"].max() - pd.Timedelta(days=30)
                ch = ch.loc[ch["date"] >= cutoff]
                transitions = []
                for node, group in ch.groupby("node", sort=False):
                    g = group.sort_values("date").copy()
                    prev = g["state"].shift(1)
                    changed_rows = g.loc[g["state"].astype(str) != prev.astype(str)]
                    changed_rows = changed_rows.iloc[1:] if len(changed_rows) > 1 else changed_rows.iloc[0:0]
                    for _, tr in changed_rows.tail(2).iterrows():
                        transitions.append((pd.Timestamp(tr["date"]), str(node), str(tr.get("state_label", tr.get("state", "")))))
                if transitions:
                    lines.append("- **최근 30일 상태 전환:**")
                    for dt, node, label in sorted(transitions)[-6:]:
                        lines.append(f"  - {dt.date().isoformat()} · {node}: {label}")
        lines.append("> 이 부분은 현재 변화가 나타난 곳와 지속을 보여주며, 어느 시장이 원인인지나 실제 선후행을 주장하지 않습니다.")

    # 7) 다음에 볼 것
    lines += ["", "### 지금부터 확인할 것"]
    added = 0
    vix = stats.get("VIX")
    hy = stats.get("HYOAS")
    if vix and vix.reverted and hy and hy.net > MATERIAL_MOVE["HYOAS"] * 0.40:
        aoas = _aux_direction_text(aux_df, "AOAS")
        lines.append(
            f"- 주식시장 변동성은 되돌아왔지만 신용등급 낮은 기업의 추가 금리는 기간 시작보다 높습니다. "
            f"현재 **{aux_name('AOAS')}**은 `{aoas}`입니다. 이 지표도 오르면 기업 자금 부담이 더 넓게 이어지는 설명이 강해지고, "
            "뚜렷한 움직임이 없거나 내리면 낮은 등급 기업 쪽에 더 집중된 변화라는 설명과 잘 맞습니다."
        )
        added += 1

    if d2 == "하락" and d30 == "상승":
        be = _aux_direction_text(aux_df, "BREAKEVEN")
        tp = _aux_direction_text(aux_df, "TERMPREM")
        lines.append(
            f"- 2년 금리 하락·30년 금리 상승이 엇갈렸습니다. 현재 **{aux_name('BREAKEVEN')}**은 `{be}`, "
            f"**{aux_name('TERMPREM')}**은 `{tp}`입니다. 물가 예상이 오르면 물가 요인 설명이, 장기채 추가 보상이 오르면 "
            "장기채 수요·공급이나 오래 보유하는 부담 설명이 더 잘 맞습니다."
        )
        added += 1

    if hy and hy.net > MATERIAL_MOVE["HYOAS"] * 0.40 and not (vix and vix.reverted):
        aoas = _aux_direction_text(aux_df, "AOAS")
        lines.append(
            f"- 신용등급 낮은 기업의 추가 금리가 한 달 동안 높아졌습니다. 현재 **{aux_name('AOAS')}**은 `{aoas}`입니다. "
            "이 지표도 오르면 기업 자금 부담이 넓게 이어지는 설명을, 그렇지 않으면 낮은 등급 기업 쪽에 집중된 설명을 더 확인합니다."
        )
        added += 1

    if added == 0:
        lines.append("- 현재 한 달 경로만으로 특정 함께 볼 지표 하나를 우선해야 할 정도의 조합은 뚜렷하지 않습니다. 오늘의 해석과 각 지표 상세 설명을 함께 봅니다.")

    return plain_language("\n".join(lines))
