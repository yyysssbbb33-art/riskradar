"""기업 신용 범위·지속 에피소드 엔진.

목적
- 순서를 억지로 주장하지 않고, 현재 어떤 실제 시장이 참여하고 있는지 본다.
- 실제 시장 노드는 HY / BBB / A / CP 네 개만 사용한다.
- HY-BBB는 별도 시장이 아니라 저신용 집중도를 읽는 해석 렌즈다.
- VIX는 신용 사슬의 노드가 아니라 에피소드 시작 무렵의 주식시장 맥락이다.

v0.6.0 원칙
- 최근 공식 자료 범위 안에서 변화 강도·지속·잔존을 본다.
- 최근 3년 분포는 장기 역사 희귀도가 아니라 현재 운영 기준의 비교 범위다.
- 변화 시작은 변화 강도, 지속/되돌림/정상화는 동결된 사전 기준선 대비 잔존 변화로 본다.
- 추정 시작일과 기준선은 확정 순간 동결하고 이후 소급 수정하지 않는다.
- 사용자 출력에서 선행/후행을 주장하지 않지만 관련 타임스탬프는 처음부터 저장한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd


NODE_ORDER = ("HY", "BBB", "A", "CP")
NODE_NAMES = {
    "HY": "신용등급 낮은 기업의 회사채",
    "BBB": "투자등급 경계 기업의 회사채",
    "A": "A등급 기업의 회사채",
    "CP": "단기 기업자금시장",
}

NODE_STATE_LABELS = {
    "normal": "평소 상태",
    "early_change": "초기 변화",
    "newly_rising": "새로 상승",
    "rising_persistent": "상승 지속",
    "retracing": "되돌림",
    "normalized": "정상화",
}

EPISODE_STATE_LABELS = {
    "active": "활성",
    "dormant": "휴면",
    "ended": "종료",
    "none": "현재 에피소드 없음",
}


@dataclass(frozen=True)
class CreditEpisodeCfg:
    # 최근 공식 자료 범위 안에서 현재 국면을 비교한다. 장기 역사 희귀도라는 뜻이 아니다.
    regime_years: int = 3
    fast_lookback: int = 5
    slow_lookback: int = 20
    min_history_obs: int = 250
    candidate_pct: float = 90.0
    confirm_obs: int = 3
    baseline_obs: int = 7
    baseline_noise_obs: int = 20
    new_state_obs: int = 5
    normalize_confirm_obs: int = 3
    retrace_ratio: float = 0.30
    normalize_peak_ratio: float = 0.20
    dormant_obs: int = 15
    engine_window_obs: int = 90
    # 같은 구조를 쓰되 향후 데이터 품질 검증 결과에 따라 지표별로만 보정한다.
    confirm_obs_by_node: dict[str, int] = field(default_factory=dict)


DEFAULT_CFG = CreditEpisodeCfg()


@dataclass
class CreditEpisodeResult:
    node_history: pd.DataFrame
    episodes: pd.DataFrame
    current: dict
    lens: dict
    vix_context: dict

    def to_quality_dict(self) -> dict:
        return {
            "current": self.current,
            "lens": self.lens,
            "vix_context": self.vix_context,
        }


def _coverage_years(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    d = pd.to_datetime(df["date"])
    return max(0.0, (d.max() - d.min()).days / 365.25)


def _point_in_time_change_percentile(changes: pd.Series, dates: pd.Series,
                                     years: int, min_obs: int) -> pd.Series:
    """양(+)의 변화 강도를 시점별 최근 자료 범위에서 경험적 백분위로 계산한다.

    과거 데이터 누수를 막기 위해 날짜 t에서는 t까지의 자료만 사용한다.
    현재 변화가 0 이하이면 확대 후보가 아니므로 0으로 둔다.
    """
    c = pd.to_numeric(changes, errors="coerce").to_numpy(dtype=float)
    d = np.array([np.datetime64(x, "D") for x in pd.to_datetime(dates)])
    out = np.full(len(c), np.nan)
    win = np.timedelta64(int(365.25 * years), "D")
    lo = 0
    for i in range(len(c)):
        while lo < i and d[i] - d[lo] > win:
            lo += 1
        hist = c[lo:i + 1]
        hist = hist[np.isfinite(hist)]
        if len(hist) < min_obs:
            continue
        if not np.isfinite(c[i]) or c[i] <= 0:
            out[i] = 0.0
            continue
        out[i] = float(np.mean(hist <= c[i]) * 100.0)
    return pd.Series(out, index=changes.index)


def _noise_floor(values: pd.Series, end_idx: int, obs: int) -> float:
    """후보 시작 이전의 작은 일상 변동 규모를 robust하게 추정한다."""
    lo = max(0, end_idx - obs)
    pre = pd.to_numeric(values.iloc[lo:end_idx], errors="coerce").dropna()
    if len(pre) < 3:
        return 0.0
    diffs = pre.diff().abs().dropna()
    if diffs.empty:
        return 0.0
    # 중앙값보다 약간 넓은 일상 잡음 범위. 극단치 한두 개에 끌리지 않는다.
    return float(diffs.quantile(0.75) * 2.0)


def _prepare_node_frame(node: str, df: pd.DataFrame, cfg: CreditEpisodeCfg) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[["date", "value"]].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d.dropna().sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    d["change_fast"] = d["value"] - d["value"].shift(cfg.fast_lookback)
    d["change_slow"] = d["value"] - d["value"].shift(cfg.slow_lookback)
    d["pct_fast"] = _point_in_time_change_percentile(
        d["change_fast"], d["date"], cfg.regime_years, cfg.min_history_obs
    )
    d["pct_slow"] = _point_in_time_change_percentile(
        d["change_slow"], d["date"], cfg.regime_years, cfg.min_history_obs
    )
    d["movement_strength"] = d[["pct_fast", "pct_slow"]].max(axis=1, skipna=True)
    d["candidate_signal"] = d["movement_strength"] >= cfg.candidate_pct
    d["node"] = node
    d["source_history_years"] = round(_coverage_years(d), 2)
    return d


def _node_state_machine(node: str, prepared: pd.DataFrame,
                        cfg: CreditEpisodeCfg) -> tuple[pd.DataFrame, list[dict]]:
    if prepared.empty:
        return pd.DataFrame(), []
    d = prepared.copy()
    n_confirm = max(1, int(cfg.confirm_obs_by_node.get(node, cfg.confirm_obs)))

    # 출력 컬럼 기본값
    d["state"] = "normal"
    d["event_id"] = pd.NA
    d["candidate_start"] = pd.NaT
    d["estimated_onset"] = pd.NaT
    d["confirmed_at"] = pd.NaT
    d["baseline"] = np.nan
    d["peak_value"] = np.nan
    d["peak_at"] = pd.NaT
    d["residual_change"] = np.nan
    d["residual_ratio"] = np.nan
    d["normalize_tolerance"] = np.nan
    d["meaningful_activity"] = False
    d["activity_kind"] = ""
    d["confirmed_today"] = False
    d["normalized_today"] = False

    events: list[dict] = []
    event_no = 0
    current: dict | None = None
    candidate_start_idx: int | None = None
    signal_streak = 0
    normalize_streak = 0
    normalized_hold = 0

    for i in range(len(d)):
        signal = bool(d.at[i, "candidate_signal"])
        dt = pd.Timestamp(d.at[i, "date"])
        value = float(d.at[i, "value"])

        if current is None:
            if signal:
                if candidate_start_idx is None:
                    candidate_start_idx = i
                    signal_streak = 1
                else:
                    signal_streak += 1
                d.at[i, "state"] = "early_change"
                d.at[i, "candidate_start"] = d.at[candidate_start_idx, "date"]
            else:
                candidate_start_idx = None
                signal_streak = 0
                if normalized_hold > 0:
                    d.at[i, "state"] = "normalized"
                    normalized_hold -= 1

            if candidate_start_idx is not None and signal_streak >= n_confirm:
                onset_idx = candidate_start_idx
                pre = pd.to_numeric(
                    d.loc[max(0, onset_idx - cfg.baseline_obs):onset_idx - 1, "value"],
                    errors="coerce",
                ).dropna()
                # 기준선 구간은 추정 시작일 직전에서 끝난다. 초기 상승분을 섞지 않는다.
                baseline = float(pre.median()) if not pre.empty else float(d.at[max(0, onset_idx - 1), "value"])
                noise = _noise_floor(d["value"], onset_idx, cfg.baseline_noise_obs)
                event_no += 1
                current = {
                    "node": node,
                    "event_id": f"{node}-{event_no}",
                    "candidate_start": pd.Timestamp(d.at[onset_idx, "date"]),
                    "estimated_onset": pd.Timestamp(d.at[onset_idx, "date"]),
                    "confirmed_at": dt,
                    "confirmed_idx": i,
                    "baseline": baseline,
                    "baseline_noise": noise,
                    "peak_value": value,
                    "peak_at": dt,
                    "last_meaningful_activity_at": dt,
                    "normalized_at": None,
                }
                # 확정 순간 onset/baseline을 동결한다.
                d.at[i, "confirmed_today"] = True
                d.at[i, "meaningful_activity"] = True
                d.at[i, "activity_kind"] = "confirmed"
                signal_streak = 0
                candidate_start_idx = None
                normalize_streak = 0

        if current is not None:
            # 새 확정 행 포함 현재 이벤트 상태를 기록한다.
            if value > current["peak_value"]:
                # 일상 잡음보다 큰 새 고점만 의미 있는 활동으로 본다.
                old_peak = current["peak_value"]
                current["peak_value"] = value
                current["peak_at"] = dt
                if value - old_peak > max(current["baseline_noise"], 1e-12):
                    current["last_meaningful_activity_at"] = dt
                    d.at[i, "meaningful_activity"] = True
                    d.at[i, "activity_kind"] = d.at[i, "activity_kind"] or "new_peak"

            baseline = float(current["baseline"])
            peak_exc = max(0.0, float(current["peak_value"]) - baseline)
            residual = value - baseline
            tolerance = max(float(current["baseline_noise"]), cfg.normalize_peak_ratio * peak_exc)
            residual_ratio = residual / peak_exc if peak_exc > 1e-12 else 0.0
            retraced = peak_exc > 1e-12 and (float(current["peak_value"]) - value) >= cfg.retrace_ratio * peak_exc

            if residual <= tolerance:
                normalize_streak += 1
            else:
                normalize_streak = 0

            prev_state = str(d.at[i - 1, "state"]) if i > 0 else "normal"
            if normalize_streak >= cfg.normalize_confirm_obs:
                state = "normalized"
                if current["normalized_at"] is None:
                    current["normalized_at"] = dt
                    current["last_meaningful_activity_at"] = dt
                    d.at[i, "normalized_today"] = True
                    d.at[i, "meaningful_activity"] = True
                    d.at[i, "activity_kind"] = d.at[i, "activity_kind"] or "normalized"
            elif retraced:
                state = "retracing"
                if prev_state != "retracing":
                    current["last_meaningful_activity_at"] = dt
                    d.at[i, "meaningful_activity"] = True
                    d.at[i, "activity_kind"] = d.at[i, "activity_kind"] or "retracing"
            elif (i - int(current["confirmed_idx"])) < cfg.new_state_obs:
                state = "newly_rising"
            else:
                state = "rising_persistent"

            d.at[i, "state"] = state
            d.at[i, "event_id"] = current["event_id"]
            d.at[i, "candidate_start"] = current["candidate_start"]
            d.at[i, "estimated_onset"] = current["estimated_onset"]
            d.at[i, "confirmed_at"] = current["confirmed_at"]
            d.at[i, "baseline"] = baseline
            d.at[i, "peak_value"] = current["peak_value"]
            d.at[i, "peak_at"] = current["peak_at"]
            d.at[i, "residual_change"] = residual
            d.at[i, "residual_ratio"] = residual_ratio
            d.at[i, "normalize_tolerance"] = tolerance

            if current["normalized_at"] is not None:
                event = {k: v for k, v in current.items() if k != "confirmed_idx"}
                event["normalized_at"] = pd.Timestamp(current["normalized_at"])
                event["final_peak_excursion"] = peak_exc
                events.append(event)
                current = None
                normalized_hold = cfg.new_state_obs
                normalize_streak = 0

    if current is not None:
        event = {k: v for k, v in current.items() if k != "confirmed_idx"}
        event["final_peak_excursion"] = max(0.0, float(current["peak_value"]) - float(current["baseline"]))
        events.append(event)

    d["state_label"] = d["state"].map(NODE_STATE_LABELS)
    return d, events


def _business_obs_between(dates: Iterable[pd.Timestamp], start: pd.Timestamp, end: pd.Timestamp) -> int:
    ds = [pd.Timestamp(x) for x in dates if pd.Timestamp(x) > start and pd.Timestamp(x) <= end]
    return len(ds)


def _asof_node_row(hist: pd.DataFrame, dt: pd.Timestamp) -> pd.Series | None:
    hit = hist.loc[pd.to_datetime(hist["date"]) <= dt]
    if hit.empty:
        return None
    return hit.iloc[-1]


def _build_episode_records(node_histories: dict[str, pd.DataFrame], cfg: CreditEpisodeCfg) -> pd.DataFrame:
    """노드 상태 기록을 한 번만 훑어 에피소드 레코드를 만든다.

    날짜별 ``loc``/과거 재검색을 피하고 노드별 포인터를 전진시켜 전체 복잡도를
    관측치 수에 거의 선형으로 유지한다.
    """
    valid_histories: dict[str, pd.DataFrame] = {}
    for node, hist in node_histories.items():
        if hist is None or hist.empty or "date" not in hist.columns:
            continue
        h = hist.copy().sort_values("date").reset_index(drop=True)
        h["date"] = pd.to_datetime(h["date"])
        valid_histories[node] = h

    all_dates = sorted({pd.Timestamp(x) for h in valid_histories.values() for x in h["date"]})
    if not all_dates:
        return pd.DataFrame()
    date_pos = {dt: i for i, dt in enumerate(all_dates)}
    pointers = {node: -1 for node in valid_histories}
    current_rows: dict[str, pd.Series] = {}

    current: dict | None = None
    episodes: list[dict] = []
    episode_no = 0

    for dt in all_dates:
        confirmed_nodes: list[str] = []
        activity_nodes: list[str] = []
        expansion_activity_nodes: list[str] = []
        for node, hist in valid_histories.items():
            p = pointers[node]
            while p + 1 < len(hist) and pd.Timestamp(hist.iloc[p + 1]["date"]) <= dt:
                p += 1
                row = hist.iloc[p]
                current_rows[node] = row
                if pd.Timestamp(row["date"]) == dt:
                    if bool(row.get("confirmed_today", False)):
                        confirmed_nodes.append(node)
                    if bool(row.get("meaningful_activity", False)):
                        activity_nodes.append(node)
                        if str(row.get("activity_kind", "")) in {"confirmed", "new_peak"}:
                            expansion_activity_nodes.append(node)
            pointers[node] = p

        if current is not None:
            residual_nodes = []
            for node in current["participants"]:
                row = current_rows.get(node)
                if row is None:
                    continue
                if str(row.get("state")) not in {"normal", "normalized"}:
                    residual_nodes.append(node)
                elif pd.notna(row.get("residual_change")) and pd.notna(row.get("normalize_tolerance")):
                    if float(row.get("residual_change")) > float(row.get("normalize_tolerance")):
                        residual_nodes.append(node)

            last_pos = date_pos.get(pd.Timestamp(current["last_meaningful_activity_at"]), 0)
            quiet_obs = date_pos[dt] - last_pos
            if current["state"] == "active" and quiet_obs >= cfg.dormant_obs and residual_nodes:
                current["state"] = "dormant"
                current["dormant_at"] = dt
            elif not residual_nodes and not confirmed_nodes:
                current["state"] = "ended"
                current["ended_at"] = dt
                episodes.append(current)
                current = None

        # 휴면 뒤 같은 노드의 재확대도 새 에피소드로 분리한다. 잔존 변화는 주석으로 남긴다.
        if current is not None and current["state"] == "dormant" and expansion_activity_nodes and not confirmed_nodes:
            prior_residual = []
            for node in current["participants"]:
                row = current_rows.get(node)
                if row is not None and str(row.get("state")) not in {"normal", "normalized"}:
                    prior_residual.append(node)
            episodes.append(current)
            episode_no += 1
            current = {
                "episode_id": f"credit-{episode_no}",
                "state": "active",
                "started_at": dt,
                "participants": list(dict.fromkeys(expansion_activity_nodes)),
                "last_meaningful_activity_at": dt,
                "dormant_at": pd.NaT,
                "ended_at": pd.NaT,
                "prior_residual_nodes": prior_residual,
            }

        if confirmed_nodes:
            if current is None:
                episode_no += 1
                current = {
                    "episode_id": f"credit-{episode_no}",
                    "state": "active",
                    "started_at": dt,
                    "participants": list(dict.fromkeys(confirmed_nodes)),
                    "last_meaningful_activity_at": dt,
                    "dormant_at": pd.NaT,
                    "ended_at": pd.NaT,
                    "prior_residual_nodes": [],
                }
            elif current["state"] == "dormant":
                prior_residual = []
                for node in current["participants"]:
                    row = current_rows.get(node)
                    if row is not None and str(row.get("state")) not in {"normal", "normalized"}:
                        prior_residual.append(node)
                episodes.append(current)
                episode_no += 1
                current = {
                    "episode_id": f"credit-{episode_no}",
                    "state": "active",
                    "started_at": dt,
                    "participants": list(dict.fromkeys(confirmed_nodes)),
                    "last_meaningful_activity_at": dt,
                    "dormant_at": pd.NaT,
                    "ended_at": pd.NaT,
                    "prior_residual_nodes": prior_residual,
                }
            else:
                for node in confirmed_nodes:
                    if node not in current["participants"]:
                        current["participants"].append(node)
                current["last_meaningful_activity_at"] = dt

        if current is not None and activity_nodes:
            current["last_meaningful_activity_at"] = dt

    if current is not None:
        episodes.append(current)

    if not episodes:
        return pd.DataFrame()
    out = pd.DataFrame(episodes)
    out["participants"] = out["participants"].map(lambda xs: ",".join(xs))
    out["prior_residual_nodes"] = out["prior_residual_nodes"].map(lambda xs: ",".join(xs))
    return out


def _current_node_rows(node_histories: dict[str, pd.DataFrame]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for node in NODE_ORDER:
        h = node_histories.get(node)
        if h is None or h.empty:
            out[node] = {"node": node, "state": "normal", "state_label": "확인 불가", "available": False}
            continue
        r = h.iloc[-1]
        out[node] = {
            "node": node,
            "name": NODE_NAMES[node],
            "available": True,
            "date": pd.Timestamp(r["date"]).date().isoformat(),
            "value": float(r["value"]),
            "state": str(r["state"]),
            "state_label": str(r["state_label"]),
            "movement_strength": None if pd.isna(r.get("movement_strength")) else round(float(r.get("movement_strength")), 1),
            "estimated_onset": None if pd.isna(r.get("estimated_onset")) else pd.Timestamp(r.get("estimated_onset")).date().isoformat(),
            "confirmed_at": None if pd.isna(r.get("confirmed_at")) else pd.Timestamp(r.get("confirmed_at")).date().isoformat(),
            "baseline": None if pd.isna(r.get("baseline")) else float(r.get("baseline")),
            "peak_value": None if pd.isna(r.get("peak_value")) else float(r.get("peak_value")),
            "peak_at": None if pd.isna(r.get("peak_at")) else pd.Timestamp(r.get("peak_at")).date().isoformat(),
            "residual_change": None if pd.isna(r.get("residual_change")) else float(r.get("residual_change")),
            "residual_ratio": None if pd.isna(r.get("residual_ratio")) else round(float(r.get("residual_ratio")), 3),
            "source_history_years": None if pd.isna(r.get("source_history_years")) else float(r.get("source_history_years")),
        }
    return out


def _scope_text(nodes: dict[str, dict]) -> str:
    confirmed = [n for n in NODE_ORDER if nodes.get(n, {}).get("state") in {
        "newly_rising", "rising_persistent", "retracing"
    }]
    early = [n for n in NODE_ORDER if nodes.get(n, {}).get("state") == "early_change"]
    if not confirmed:
        if early:
            names = "·".join(NODE_NAMES[n] for n in early)
            return f"공식 참여로 확정되기 전의 초기 변화가 {names}에서 관찰되고 있습니다."
        return "현재 기업 신용시장에서 새로 이어지는 범위 변화는 뚜렷하지 않습니다."
    if confirmed == ["HY"]:
        text = "현재 확인된 변화는 신용등급 낮은 기업의 회사채에 집중돼 있습니다."
    else:
        parts = []
        if "HY" in confirmed:
            parts.append("신용등급 낮은 기업")
        if "BBB" in confirmed:
            parts.append("투자등급 경계 기업")
        if "A" in confirmed:
            parts.append("A등급 기업")
        text = "회사채 변화가 " + "·".join(parts) + "에서 확인되고 있습니다." if parts else ""
        if "CP" in confirmed:
            text += (" " if text else "") + "단기 기업자금시장도 함께 참여하고 있습니다."
        else:
            text += (" " if text else "") + "단기 기업자금시장까지 번진 모습은 아직 뚜렷하지 않습니다."
    if early:
        text += " " + "·".join(NODE_NAMES[n] for n in early) + "에서는 초기 변화를 관찰 중입니다."
    return text.strip()


def _lens_from_histories(node_frames: dict[str, pd.DataFrame], cfg: CreditEpisodeCfg) -> dict:
    hy = node_frames.get("HY")
    bbb = node_frames.get("BBB")
    if hy is None or bbb is None or hy.empty or bbb.empty:
        return {"available": False, "state": "unavailable", "label": "확인 불가"}
    m = hy[["date", "value"]].merge(bbb[["date", "value"]], on="date", how="inner", suffixes=("_hy", "_bbb"))
    if m.empty:
        return {"available": False, "state": "unavailable", "label": "확인 불가"}
    m["spread"] = m["value_hy"] - m["value_bbb"]
    m["change_20"] = m["spread"] - m["spread"].shift(cfg.slow_lookback)
    valid = m["change_20"].dropna()
    r = m.iloc[-1]
    ch = None if pd.isna(r["change_20"]) else float(r["change_20"])
    pct = None
    if ch is not None and len(valid) >= cfg.min_history_obs:
        pct = float((valid.abs() <= abs(ch)).mean() * 100.0)
    if ch is None or pct is None:
        state, label = "unclear", "등급 간 차별 변화 확인이 아직 어렵습니다."
    elif pct < 60:
        state, label = "together", "투기등급과 투자등급 경계가 비교적 함께 움직이고 있습니다."
    elif ch > 0:
        state, label = "low_credit_concentrated", "부담 증가가 투기등급 기업에 더 집중되는 방향입니다."
    else:
        state, label = "boundary_catching_up", "투자등급 경계 기업의 부담이 상대적으로 더 따라오는 방향입니다."
    return {
        "available": True,
        "state": state,
        "label": label,
        "latest_date": pd.Timestamp(r["date"]).date().isoformat(),
        "latest_value_bp": round(float(r["spread"]), 2),
        "change_1m_bp": None if ch is None else round(ch, 2),
        "change_magnitude_pct_recent_data": None if pct is None else round(pct, 1),
        "comparison_window": f"최근 약 {cfg.regime_years}년 자료 범위",
    }


def _vix_context(vix_frame: pd.DataFrame | None, current_episode: dict | None) -> dict:
    if vix_frame is None or vix_frame.empty:
        return {"available": False, "onset": "확인 불가", "current": "확인 불가"}
    v = vix_frame.copy().sort_values("date")
    current_state = str(v.iloc[-1].get("state_code", ""))
    current = "주식시장 불안이 현재도 높음" if current_state in {"watch", "stress"} else "주식시장 불안은 현재 평소 수준"
    if not current_episode or not current_episode.get("started_at"):
        return {"available": True, "onset": "현재 신용 에피소드 없음", "current": current}
    onset = pd.Timestamp(current_episode["started_at"])
    window = v.loc[(pd.to_datetime(v["date"]) >= onset - pd.Timedelta(days=7)) &
                   (pd.to_datetime(v["date"]) <= onset + pd.Timedelta(days=7))]
    if window.empty:
        onset_text = "시작 무렵 주식시장 자료 확인 불가"
    else:
        active = window["state_code"].astype(str).isin({"watch", "stress"}).any()
        onset_text = "시작 무렵 주식시장 불안도 함께 나타남" if active else "시작 무렵 주식시장 불안은 뚜렷하지 않았음"
    return {"available": True, "onset": onset_text, "current": current}



def _cp_calendar_context(nodes: dict[str, dict]) -> dict:
    """CP 신호를 삭제하지 않고 연말 기술요인 가능성만 진단 정보로 붙인다."""
    cp = nodes.get("CP") or {}
    if not cp.get("available") or not cp.get("date"):
        return {"available": False, "year_end": False, "note": "확인 불가"}
    dt = pd.Timestamp(cp["date"])
    year_end = dt.month == 12
    note = (
        "연말에는 단기 기업자금시장에 기술적 요인이 섞일 수 있어 지속 여부를 함께 확인합니다."
        if year_end else
        "현재 관측일은 연말 캘린더 진단 구간이 아닙니다."
    )
    return {"available": True, "year_end": year_end, "note": note}

def build_credit_episode(node_frames: dict[str, pd.DataFrame],
                         vix_frame: pd.DataFrame | None = None,
                         cfg: CreditEpisodeCfg = DEFAULT_CFG) -> CreditEpisodeResult:
    """네 시장 노드의 최근 경로를 범위·지속 에피소드로 읽는다.

    node_frames 값 단위는 모두 bp여야 한다.
    """
    prepared: dict[str, pd.DataFrame] = {}
    node_histories: dict[str, pd.DataFrame] = {}
    event_rows: list[dict] = []
    for node in NODE_ORDER:
        frame = node_frames.get(node)
        p = _prepare_node_frame(node, frame, cfg) if frame is not None else pd.DataFrame()
        prepared[node] = p
        h, events = _node_state_machine(node, p, cfg)
        node_histories[node] = h
        event_rows.extend(events)

    episodes = _build_episode_records(node_histories, cfg)
    node_history = pd.concat(
        [h for h in node_histories.values() if h is not None and not h.empty],
        ignore_index=True,
    ) if any(h is not None and not h.empty for h in node_histories.values()) else pd.DataFrame()

    # 저장·UI 크기를 제한하되 엔진 계산은 전체 공식 자료 범위로 끝낸 뒤 자른다.
    if not node_history.empty:
        keep_parts = []
        for node, h in node_history.groupby("node", sort=False):
            keep_parts.append(h.sort_values("date").tail(cfg.engine_window_obs))
        node_history = pd.concat(keep_parts, ignore_index=True).sort_values(["date", "node"]).reset_index(drop=True)

    nodes = _current_node_rows(node_histories)
    current_episode = None
    if not episodes.empty:
        row = episodes.iloc[-1]
        participants = [x for x in str(row.get("participants", "")).split(",") if x]
        prior = [x for x in str(row.get("prior_residual_nodes", "")).split(",") if x]
        current_episode = {
            "episode_id": str(row.get("episode_id")),
            "state": str(row.get("state", "none")),
            "state_label": EPISODE_STATE_LABELS.get(str(row.get("state", "none")), "확인 불가"),
            "started_at": None if pd.isna(row.get("started_at")) else pd.Timestamp(row.get("started_at")).date().isoformat(),
            "last_meaningful_activity_at": None if pd.isna(row.get("last_meaningful_activity_at")) else pd.Timestamp(row.get("last_meaningful_activity_at")).date().isoformat(),
            "dormant_at": None if pd.isna(row.get("dormant_at")) else pd.Timestamp(row.get("dormant_at")).date().isoformat(),
            "ended_at": None if pd.isna(row.get("ended_at")) else pd.Timestamp(row.get("ended_at")).date().isoformat(),
            "participants": participants,
            "prior_residual_nodes": prior,
        }
    else:
        current_episode = {
            "episode_id": None, "state": "none", "state_label": EPISODE_STATE_LABELS["none"],
            "started_at": None, "last_meaningful_activity_at": None,
            "dormant_at": None, "ended_at": None, "participants": [],
            "prior_residual_nodes": [],
        }

    current = {
        "episode": current_episode,
        "nodes": nodes,
        "scope_text": _scope_text(nodes),
        "engine_window_obs": cfg.engine_window_obs,
        "regime_years": cfg.regime_years,
        "sequence_claims_enabled": False,
        "cp_calendar_context": _cp_calendar_context(nodes),
    }
    lens = _lens_from_histories(prepared, cfg)
    vix_context = _vix_context(vix_frame, current_episode)
    return CreditEpisodeResult(node_history, episodes, current, lens, vix_context)


def raw_to_node_frames(core_frames: dict[str, pd.DataFrame],
                       aux_raw_frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """기존 핵심/확인지표 raw 프레임을 네 신용 노드 공통 단위(bp)로 맞춘다."""
    out: dict[str, pd.DataFrame] = {}
    hy = core_frames.get("HYOAS")
    if hy is not None and not hy.empty:
        out["HY"] = hy[["date", "value"]].copy()
    for node, key in (("BBB", "BBBOAS"), ("A", "AOAS"), ("CP", "CPSPREAD")):
        df = aux_raw_frames.get(key)
        if df is None or df.empty:
            continue
        d = df[["date", "value_raw"]].copy()
        d["date"] = pd.to_datetime(d["date"])
        # BBB/A/CP 원자료는 FRED percent 단위이므로 bp로 통일한다.
        d["value"] = pd.to_numeric(d["value_raw"], errors="coerce") * 100.0
        out[node] = d[["date", "value"]].dropna().sort_values("date").reset_index(drop=True)
    return out
