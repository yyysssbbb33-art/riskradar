"""RiskRadar v0.4.0 — 조건부 해석 엔진 테스트."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from riskradar import combo_rules as CR
from riskradar import interpretation_engine as IE


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


def _aux(**dirs):
    # key -> 방향 문자열을 direction 속성을 가진 stub으로
    return {k: SimpleNamespace(direction=v) for k, v in dirs.items()}


def _30up_2down(**rate_over):
    # 30Y 상승(rate_shock), 2Y 하락(drop_flag)
    f = _frames(
        DGS30=_frame(["stable"] * 11 + ["rate_shock"]),
        DGS2=_frame(["stable"] * 12, drop=[False] * 11 + [True]),
    )
    for k, codes in rate_over.items():
        f[k] = codes
    return f


def test_detect_30up_2down():
    f = _30up_2down()
    readings = IE.read_all(f, _aux(BREAKEVEN="보합", IGOAS="보합", TERMPREM="보합"))
    ids = [r.combo_id for r in readings]
    assert "rates_30up_2down" in ids


def test_real_up_supports_real_explanation():
    # DFII10 상승 -> real 설명 지지
    f = _30up_2down(DFII10=_frame(["stable"] * 11 + ["rate_shock"]))
    readings = IE.read_all(f, _aux(BREAKEVEN="하락", IGOAS="보합", TERMPREM="보합"))
    r = next(x for x in readings if x.combo_id == "rates_30up_2down")
    assert "real" in r.supported_ids
    # 단일 지지이므로 충돌 없음
    assert r.conflict == ""


def test_multiple_supports_flag_conflict():
    # DFII10 상승(real) + BREAKEVEN 상승(infl) -> 두 설명 동시 지지 -> 충돌 안내
    f = _30up_2down(DFII10=_frame(["stable"] * 11 + ["rate_shock"]))
    readings = IE.read_all(f, _aux(BREAKEVEN="상승", IGOAS="보합", TERMPREM="보합"))
    r = next(x for x in readings if x.combo_id == "rates_30up_2down")
    assert {"real", "infl"}.issubset(set(r.supported_ids))
    assert r.conflict != "" and "정리하기 어렵" in r.conflict


def test_na_defers_that_check_only():
    f = _30up_2down()
    readings = IE.read_all(f, _aux(BREAKEVEN="판정불가", IGOAS="보합", TERMPREM="보합"))
    r = next(x for x in readings if x.combo_id == "rates_30up_2down")
    be = next(c for c in r.checks if c.key == "BREAKEVEN")
    assert be.direction == "판정불가" and "보류" in be.text
    assert "보류했습니다" in r.uncertainty
    # 다른 확인은 살아있음
    assert any(c.key == "DFII10" for c in r.checks)


def test_no_detection_when_quiet():
    readings = IE.read_all(_frames(), _aux(BREAKEVEN="보합", IGOAS="보합", TERMPREM="보합"))
    assert readings == []


def test_max_readings_cap():
    # 여러 조합이 동시에 잡혀도 상한을 넘지 않는다
    f = _30up_2down(
        DFII10=_frame(["stable"] * 11 + ["rate_shock"]),  # 30up2down + broad_up 후보
    )
    # VIX/HY 동반(D)도 유발
    f["VIX"] = _frame(["calm"] * 11 + ["stress"])
    f["HYOAS"] = _frame(["neutral"] * 11 + ["stress"])
    readings = IE.read_all(f, _aux(BREAKEVEN="상승", IGOAS="상승", TERMPREM="상승"),
                           max_readings=2)
    assert len(readings) <= 2


def test_no_directive_language():
    # 어떤 조합 해석에도 종합 판단/행동 지시 단어가 없어야 한다
    f = _30up_2down(DFII10=_frame(["stable"] * 11 + ["rate_shock"]))
    f["VIX"] = _frame(["calm"] * 11 + ["stress"])
    f["HYOAS"] = _frame(["neutral"] * 11 + ["stress"])
    readings = IE.read_all(f, _aux(BREAKEVEN="상승", IGOAS="상승", TERMPREM="하락"))
    banned = ["위험합니다", "안전합니다", "조심하", "매수", "매도", "팔아", "사야"]
    for r in readings:
        blob = " ".join([r.observed, r.conflict, r.uncertainty]
                        + [t for _, t in r.explanations]
                        + [c.text for c in r.checks])
        for w in banned:
            assert w not in blob, f"directive word '{w}' in {r.combo_id}"


def test_weakened_explanation_is_structured():
    f = _30up_2down()
    readings = IE.read_all(f, _aux(BREAKEVEN="하락", IGOAS="보합", TERMPREM="보합"))
    r = next(x for x in readings if x.combo_id == "rates_30up_2down")
    assert "infl" in r.weakened_ids


def test_stale_aux_is_excluded_from_support():
    f = _30up_2down()
    readings = IE.read_all(
        f,
        _aux(BREAKEVEN="상승", IGOAS="보합", TERMPREM="보합"),
        aux_status={"BREAKEVEN": "stale", "IGOAS": "normal", "TERMPREM": "normal"},
    )
    r = next(x for x in readings if x.combo_id == "rates_30up_2down")
    be = next(c for c in r.checks if c.key == "BREAKEVEN")
    assert be.direction == "판정불가"
    assert "infl" not in r.supported_ids
