"""RiskRadar v0.4.0 — 3축 엔진 단위 테스트."""
from __future__ import annotations

import pandas as pd

from riskradar import axis_engine as AX


def _frame(codes, drop=None):
    n = len(codes)
    return pd.DataFrame({
        "date": pd.bdate_range("2020-01-01", periods=n),
        "value": list(range(n)),
        "state_code": codes,
        "drop_flag": drop if drop is not None else [False] * n,
    })


def _frames(**over):
    base = {
        "VIX": _frame(["calm"] * 12),
        "HYOAS": _frame(["neutral"] * 12),
        "T10Y3M": _frame(["normal"] * 12),
        "DGS30": _frame(["stable"] * 12),
        "DGS2": _frame(["stable"] * 12),
        "DFII10": _frame(["stable"] * 12),
    }
    base.update(over)
    return base


def test_vc_A_quiet():
    vc = AX.vol_credit_axis(_frames())
    assert vc.state == "A" and not vc.changed


def test_vc_B_vix_leads_immediate():
    f = _frames(VIX=_frame(["calm"] * 11 + ["stress"]))
    vc = AX.vol_credit_axis(f)
    assert vc.state == "B" and vc.vix_active and vc.vix_reason == "immediate"
    assert not vc.hy_active


def test_vc_B_vix_persistent():
    f = _frames(VIX=_frame(["calm"] * 7 + ["watch", "calm", "watch", "calm", "watch"]))
    vc = AX.vol_credit_axis(f)
    assert vc.state == "B" and vc.vix_active and vc.vix_reason.startswith("persistent")


def test_vc_C_credit_only():
    f = _frames(HYOAS=_frame(["neutral"] * 11 + ["watch"]))
    vc = AX.vol_credit_axis(f)
    assert vc.state == "C" and vc.hy_active and not vc.vix_active


def test_vc_D_both():
    f = _frames(VIX=_frame(["calm"] * 11 + ["stress"]),
                HYOAS=_frame(["neutral"] * 11 + ["stress"]))
    vc = AX.vol_credit_axis(f)
    assert vc.state == "D" and vc.vix_active and vc.hy_active and vc.changed


def test_vc_E_vix_calmed_credit_persists():
    vix = _frame(["calm", "calm", "watch", "watch", "calm", "calm",
                  "calm", "calm", "calm", "calm", "calm", "calm"])
    f = _frames(VIX=vix, HYOAS=_frame(["neutral"] * 11 + ["watch"]))
    vc = AX.vol_credit_axis(f)
    assert vc.state == "E" and vc.hy_active and not vc.vix_active


def test_cycle_base_normal():
    assert not AX.cycle_axis(_frames()).changed


def test_cycle_changed_inverted():
    cy = AX.cycle_axis(_frames(T10Y3M=_frame(["normal"] * 11 + ["inverted"])))
    assert cy.changed and cy.state == "inverted"


def test_rate_up_only():
    rt = AX.rate_axis(_frames(DGS30=_frame(["stable"] * 11 + ["rate_shock"])))
    assert rt.result == "상승 방향" and rt.changed
    assert rt.members["DGS30"] == "상승"


def test_rate_down_via_drop_flag():
    f = _frames(DGS2=_frame(["stable"] * 12, drop=[False] * 11 + [True]))
    rt = AX.rate_axis(f)
    assert rt.result == "하락 방향" and rt.members["DGS2"] == "하락"


def test_rate_mixed_not_netted():
    f = _frames(DGS30=_frame(["stable"] * 11 + ["rise_watch"]),
                DGS2=_frame(["stable"] * 12, drop=[False] * 11 + [True]))
    rt = AX.rate_axis(f)
    assert rt.result == "혼합 방향" and rt.changed


def test_rate_none():
    assert AX.rate_axis(_frames()).result == "변화 없음"


def test_composite_counts_changed_axes():
    f = _frames(
        VIX=_frame(["calm"] * 11 + ["stress"]),
        DGS30=_frame(["stable"] * 11 + ["rate_shock"]),
    )
    cv = AX.composite_view(f)
    assert cv.changed_count == 2
    assert set(cv.changed_axes) == {"변동성·신용", "금리 방향"}
    assert cv.base_axes == ["경기 사이클"]
    assert cv.summary_line() == "현재 3축 중 2축에서 기준상 변화"


def test_composite_all_base():
    cv = AX.composite_view(_frames())
    assert cv.changed_count == 0 and cv.changed_axes == []


def test_composite_to_dict_has_no_score():
    d = AX.composite_view(_frames()).to_dict()
    for banned in ("score", "risk_level", "overall", "위험점수"):
        assert banned not in d
    assert "disclaimer" in d


def test_vix_persistence_is_filtered_by_own_history_change_size():
    n = 320
    df = pd.DataFrame({
        "date": pd.bdate_range("2020-01-01", periods=n),
        "value": [20.0] * n,
        "state_code": ["calm"] * (n - 5) + ["watch", "watch", "watch", "watch", "watch"],
        "drop_flag": [False] * n,
        # 과거 변화폭은 대부분 크고, 최신 변화는 매우 작아 자기 역사 대비 미미함
        "change_20obs": [10.0] * (n - 1) + [0.1],
    })
    vc = AX.vol_credit_axis(_frames(VIX=df))
    assert vc.state == "A"
    assert not vc.vix_active
    assert vc.vix_reason == "persistent_but_small_change"
