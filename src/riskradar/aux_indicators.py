"""RiskRadar — 보조지표 수집 + 방향 판정.

역할:
- FRED에서 보조 3개(Breakeven / IG OAS / Term Premium)를 수집한다.
- 각 지표의 '약 1개월 변화'가 자기 과거 변화분포에서 어디쯤인지로
  방향(상승/하락/보합/판정불가)을 낸다.
- 3축·종합상태에 개입하지 않는다. 조건부 해석 분기의 입력일 뿐이다.

원칙:
- anti-lookahead: 최신 방향은 과거 관측만으로 결정된다(마지막 시점이라 미래 없음).
- span guard: lookback을 가로지른 달력 공백이 크면 그 변화를 신뢰하지 않는다.
- 부분 실패: 한 지표가 실패해도 나머지는 살린다. (특히 Term Premium)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from . import aux_config as AC
from . import fred_client as FC

DIRECTION_UP = "상승"
DIRECTION_DOWN = "하락"
DIRECTION_FLAT = "보합"
DIRECTION_NA = "판정불가"


@dataclass
class AuxDirection:
    key: str
    display_name: str
    ok: bool
    latest_value: float | None      # 표시 단위(value_unit)
    latest_date: str | None         # ISO date
    change_1m: float | None         # 표시 단위(change_unit)
    direction: str
    pct_in_history: float | None    # |최신 변화|가 과거 |변화| 분포의 백분위(크기 이례성)
    n_obs: int                      # 방향 판정에 쓴 변화 관측 수
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def compute_direction(df: pd.DataFrame, spec: AC.AuxSeries,
                      cfg: AC.AuxDirectionCfg = AC.AUX_DIRECTION) -> AuxDirection:
    """raw DataFrame(date, value_raw) -> 방향 판정.

    분포는 lookback 변화 시계열 전체(span guard 통과분)를 쓴다.
    최신 변화가 그 분포의 몇 백분위인지로 상/하/보합을 가른다.
    """
    if df is None or df.empty:
        return AuxDirection(spec.key, spec.display_name, False, None, None,
                            None, DIRECTION_NA, None, 0, "empty df")

    d = df.sort_values("date").reset_index(drop=True).copy()
    d["value"] = d["value_raw"] * spec.raw_to_value

    lb = cfg.lookback_obs
    prev_val = d["value"].shift(lb)
    prev_date = d["date"].shift(lb)
    gap_days = (d["date"] - prev_date).dt.days
    # span guard: 공백이 크면 변화 무효화
    raw_change = d["value"] - prev_val
    d["change"] = raw_change.where(gap_days <= cfg.span_guard_days)

    valid = d["change"].dropna()
    latest_value = float(d["value"].iloc[-1])
    latest_date = d["date"].iloc[-1].date().isoformat()

    if valid.empty:
        return AuxDirection(spec.key, spec.display_name, True, latest_value,
                            latest_date, None, DIRECTION_NA, None, 0,
                            "no valid change (span guard)")

    latest_change = d["change"].iloc[-1]
    change_disp = (float(latest_change) * spec.change_to_disp
                   if pd.notna(latest_change) else None)
    n = int(valid.shape[0])

    if pd.isna(latest_change) or n < cfg.min_obs:
        return AuxDirection(spec.key, spec.display_name, True, latest_value,
                            latest_date, change_disp, DIRECTION_NA, None, n,
                            "insufficient history" if n < cfg.min_obs else "latest change NaN")

    # 방향은 부호, 유의성은 |변화|의 과거 백분위. 미미하면 보합으로 눌러 노이즈 차단.
    abs_pct = float((valid.abs() <= abs(float(latest_change))).mean() * 100.0)
    if abs_pct < cfg.flat_abs_pct:
        direction = DIRECTION_FLAT
    elif latest_change > 0:
        direction = DIRECTION_UP
    else:
        direction = DIRECTION_DOWN

    return AuxDirection(spec.key, spec.display_name, True, latest_value,
                        latest_date, change_disp, direction, round(abs_pct, 1), n)


def collect_aux(api_key: str | None = None, timeout: float | None = None,
                start: str | None = None, max_attempts: int = 2) -> dict[str, AuxDirection]:
    """보조 3개를 FRED에서 받아 방향까지 계산. 부분 실패 허용.

    각 지표는 일시적인 네트워크·FRED 오류에 대비해 최대 ``max_attempts``회
    요청한다. 한 지표가 끝내 실패해도 다른 보조지표와 핵심 6개는 계속 처리한다.
    """
    from . import config as C
    api_key, timeout = FC._resolve_creds(api_key, timeout)
    start = start or C.FRED_START_DATE
    max_attempts = max(1, int(max_attempts))

    out: dict[str, AuxDirection] = {}
    for key in AC.AUX_ORDER:
        spec = AC.AUX_SERIES[key]
        last_error = None
        res = None
        for _attempt in range(1, max_attempts + 1):
            res = FC.fetch_fred_series(spec.series_id, key, api_key, timeout, start)
            if res.ok:
                break
            last_error = res.error
        if res is None or not res.ok:
            error = last_error or (getattr(res, "error", None) if res is not None else "fetch failed")
            out[key] = AuxDirection(key, spec.display_name, False, None, None,
                                    None, DIRECTION_NA, None, 0, error)
            continue
        out[key] = compute_direction(res.df, spec)
    return out
