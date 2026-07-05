"""상태 라벨 계산.

원칙
- 상태는 raw 시계열에서 매번 처음부터 forward pass로 재계산한다.
- 이전 refresh의 상태를 입력으로 쓰지 않는다.
- forward pass는 과거만 참조하므로 anti-lookahead 안전하다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

LABELS = {
    "calm": "평온", "watch": "관찰", "neutral": "중립", "stress": "스트레스",
    "normal": "정상", "inverted": "역전", "long_inverted": "장기역전",
    "re_normalizing": "재정상화 관찰", "re_normalized": "재정상화 확정",
    "stable": "안정", "rise_watch": "상승 관찰", "rate_shock": "금리 충격",
}


# ---- 공통: 순서형 상태 hysteresis FSM ------------------------------------

def _commit_ordered(cands: list[str | None], order: list[str],
                    up_confirm: int, down_confirm: int) -> list[str]:
    rank = {s: i for i, s in enumerate(order)}
    # seed = 첫 유효 후보 (없으면 최저 상태)
    seed = next((c for c in cands if c is not None), order[0])
    cur = seed
    cand_prev, cand_streak = None, 0
    out = []
    for c in cands:
        c = c if c is not None else cur  # 후보 계산 불가 시 현 상태 유지 취급
        if c == cand_prev:
            cand_streak += 1
        else:
            cand_prev, cand_streak = c, 1
        if c != cur:
            need = up_confirm if rank[c] > rank[cur] else down_confirm
            if cand_streak >= need:
                cur = c
        out.append(cur)
    return out


# ---- VIX ------------------------------------------------------------------

def _vix_candidate(value: float, pct10y: float, cfg: C.VixCfg) -> str:
    p = pct10y if not pd.isna(pct10y) else -1
    if p >= cfg.stress_pct10y or value >= cfg.stress_abs:
        return "stress"
    if p >= cfg.watch_pct10y or value >= cfg.watch_abs:
        return "watch"
    return "calm"


def vix_states(df: pd.DataFrame, cfg: C.VixCfg) -> list[str]:
    cands = [_vix_candidate(v, p, cfg)
             for v, p in zip(df["value"], df["percentile_10y"])]
    return _commit_ordered(cands, ["calm", "watch", "stress"],
                           cfg.up_confirm, cfg.down_confirm)


# ---- HY OAS ---------------------------------------------------------------

def _hyoas_candidate(bp: float, pct10y: float, cfg: C.HyOasCfg) -> str:
    p = pct10y if not pd.isna(pct10y) else -1
    if p >= cfg.stress_pct10y or bp >= cfg.stress_bp:
        return "stress"
    if p >= cfg.watch_pct10y or bp >= cfg.watch_bp:
        return "watch"
    if bp >= cfg.neutral_bp:
        return "neutral"
    return "calm"


def hyoas_states(df: pd.DataFrame, cfg: C.HyOasCfg) -> list[str]:
    cands = [_hyoas_candidate(v, p, cfg)
             for v, p in zip(df["value"], df["percentile_10y"])]
    return _commit_ordered(cands, ["calm", "neutral", "watch", "stress"],
                           cfg.up_confirm, cfg.down_confirm)


# ---- 금리 3종 -------------------------------------------------------------

def _rate_candidate(c20: float, c60: float, cfg: C.RateCfg) -> str:
    c20 = -1e18 if pd.isna(c20) else c20
    c60 = -1e18 if pd.isna(c60) else c60
    if c60 >= cfg.rate_shock_60 or c20 >= cfg.rate_shock_20:
        return "rate_shock"
    if c60 >= cfg.rise_watch_60 or c20 >= cfg.rise_watch_20:
        return "rise_watch"
    return "stable"


def rate_states(df: pd.DataFrame, cfg: C.RateCfg) -> list[str]:
    cands = [_rate_candidate(c20, c60, cfg)
             for c20, c60 in zip(df["change_20obs"], df["change_60obs"])]
    return _commit_ordered(cands, ["stable", "rise_watch", "rate_shock"],
                           cfg.up_confirm, cfg.down_confirm)


def rate_drop_flags(df: pd.DataFrame, cfg: C.RateCfg) -> list[bool]:
    out = []
    for c20, c60 in zip(df["change_20obs"], df["change_60obs"]):
        c20v = 1e18 if pd.isna(c20) else c20
        c60v = 1e18 if pd.isna(c60) else c60
        out.append(bool(c60v <= cfg.drop_60 or c20v <= cfg.drop_20))
    return out


# ---- T10Y3M ---------------------------------------------------------------

def t10y3m_states(df: pd.DataFrame, cfg: C.T10Y3MCfg) -> list[str]:
    cur = "watch"
    neg = nonneg = strong_pos = box = 0
    out = []
    for x in df["value"]:  # value는 bp
        neg = neg + 1 if x < 0 else 0
        nonneg = nonneg + 1 if x >= 0 else 0
        strong_pos = strong_pos + 1 if x >= cfg.strong_pos_bp else 0
        box = box + 1 if -cfg.box_bp < x < cfg.box_bp else 0

        if neg >= cfg.long_inverted_streak:
            cur = "long_inverted"
        elif cur == "long_inverted" and nonneg >= cfg.renorm_watch_streak:
            cur = "re_normalizing"
        elif cur == "re_normalizing" and nonneg >= cfg.renorm_confirm_streak:
            cur = "re_normalized"
        elif neg >= cfg.inverted_streak:
            cur = "inverted"
        elif strong_pos >= cfg.normal_streak:
            cur = "normal"
        elif box >= cfg.box_streak:
            cur = "watch"
        # else: 유지
        out.append(cur)
    return out


# ---- 오케스트레이션 -------------------------------------------------------

def attach_states(key: str, df: pd.DataFrame, th: C.Thresholds) -> pd.DataFrame:
    df = df.copy()
    kind = C.SERIES[key].state_kind
    df["drop_flag"] = False
    if kind == "vix":
        states = vix_states(df, th.vix)
    elif kind == "hyoas":
        states = hyoas_states(df, th.hyoas)
    elif kind == "t10y3m":
        states = t10y3m_states(df, th.t10y3m)
    elif kind == "rate":
        states = rate_states(df, th.rate)
        df["drop_flag"] = rate_drop_flags(df, th.rate)
    else:
        raise ValueError(kind)
    df["state_code"] = states
    df["state_label"] = [LABELS[s] for s in states]
    return df


def state_reason(key: str, row: pd.Series) -> str:
    """최신 상태에 대한 한 문장 근거."""
    s = C.SERIES[key]
    code = row["state_code"]
    c60 = row.get("change_60obs")
    p10 = row.get("percentile_10y")
    if s.state_kind in ("vix", "hyoas"):
        ptxt = f"10년 백분위 {p10:.0f}%" if not pd.isna(p10) else "백분위 미가용"
        return f"{row['value']:.1f}{s.value_unit}, {ptxt} 기준 '{LABELS[code]}'."
    if s.state_kind == "t10y3m":
        return ("경기사이클 배경 지표. 현재 시장 스트레스가 아니라 "
                f"수익률곡선 상태가 '{LABELS[code]}'.")
    # rate
    ctxt = f"60obs {c60:+.0f}bp" if not pd.isna(c60) else "변화량 미가용"
    base = f"{row['value']:.2f}% ({ctxt}) 기준 '{LABELS[code]}'."
    if row.get("drop_flag"):
        base += " 금리 급락 플래그: 완화 기대일 수도, 경기둔화 신호일 수도 있음."
    return base
