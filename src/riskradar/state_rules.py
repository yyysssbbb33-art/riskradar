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
from .display_text import state_name
from .formatting import fmt_change, fmt_pct

LABELS = {
    "calm": "평소 수준", "watch": "평소보다 높음", "neutral": "보통 수준", "stress": "매우 높은 편",
    "normal": "장기금리가 더 높음", "inverted": "단기금리가 더 높음",
    "long_inverted": "단기금리가 오래 더 높음",
    "re_normalizing": "장기금리가 다시 높아짐",
    "re_normalized": "장기금리가 다시 높은 상태가 이어짐",
    "stable": "큰 움직임 없음", "rise_watch": "오르는 중", "rate_shock": "빠르게 오름",
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
    """최신 상태에 대한 사용자용 한 문장 근거."""
    s = C.SERIES[key]
    code = row["state_code"]
    c60 = row.get("change_60obs")
    p10 = row.get("percentile_10y")
    p3 = row.get("percentile_3y")

    if s.state_kind == "vix":
        ptxt = (f"최근 10년 관측일의 {fmt_pct(p10)}" if not pd.isna(p10)
                else "최근 10년 비교 불가")
        return f"현재 {row['value']:.1f}, {ptxt}. 현재 상태는 '{state_name(code, key=key)}'입니다."

    if s.state_kind == "hyoas":
        ptxt = (f"최근 공식 자료 약 3년 중 {fmt_pct(p3)}" if not pd.isna(p3)
                else "최근 3년 위치 비교 불가")
        return (f"현재 {row['value']:.0f}bp, {ptxt}. 현재 상태는 '{state_name(code, key=key)}'입니다. "
                "ICE 계열은 장기 과거 위치 대신 현재 확보된 약 3년 자료를 맥락으로만 보여줍니다.")

    if s.state_kind == "t10y3m":
        value_pctp = row["value"] / 100.0
        if value_pctp > 0:
            relation = f"현재 10년 금리가 3개월 금리보다 {abs(value_pctp):.2f}%p 높습니다."
        elif value_pctp < 0:
            relation = f"현재 3개월 금리가 10년 금리보다 {abs(value_pctp):.2f}%p 높습니다."
        else:
            relation = "현재 10년 금리와 3개월 금리가 같습니다."
        return f"{relation} 지금 상태는 '{state_name(code, key=key)}'입니다."

    ctxt = (f"약 3개월 동안 {fmt_change(c60, s.change_unit)}" if not pd.isna(c60)
            else "약 3개월 변화는 비교 불가")
    base = f"현재 {row['value']:.2f}%, {ctxt}. 현재 상태는 '{state_name(code, drop=bool(row.get('drop_flag')), key=key)}'입니다."
    if row.get("drop_flag"):
        base += " 빠른 하락이 금리인하 기대 때문인지 경기둔화 우려 때문인지는 다른 지표와 함께 봅니다."
    return base

