"""Telegram 알림.

원칙
- 숫자 결과를 먼저, 해석을 뒤에 보여준다.
- 단일 위험점수·매매 조언·인과/선행 과장 표현을 만들지 않는다.
- 핵심 6개 → HY-BBB 해석 기준 → 함께 볼 지표 → 외부 참고 → 범위·지속 해석 순서다.
- Telegram 실패는 데이터 업데이트 성공을 깨지 않는다.
"""
from __future__ import annotations

import logging
import os

import pandas as pd
import requests

log = logging.getLogger(__name__)

_VOL_CREDIT_LABELS = {
    "A": "큰 변화 없음",
    "B": "주식시장 쪽만 움직임",
    "C": "회사채 쪽만 움직임",
    "D": "주식시장과 회사채가 함께 움직임",
    "E": "주식시장은 진정했지만 회사채 변화는 이어짐",
}
_RATE_RESULTS = {
    "변화 없음": "큰 변화 없음",
    "상승 방향": "상승 쪽",
    "하락 방향": "하락 쪽",
    "혼합 방향": "서로 다른 방향",
}
_DIRECTION_TEXT = {
    "상승": "상승",
    "하락": "하락",
    "보합": "큰 변화 없음",
    "확인 불가": "확인 불가",
}
_AUX_SHORT_NAMES = {
    "BREAKEVEN": "10년 일반·물가연동 국채금리 차이",
    "TERMPREM": "10년 장기채 추가 보상",
    "BBBOAS": "BBB OAS",
    "AOAS": "A OAS",
    "CPSPREAD": "CP Spread",
    "NFCI": "NFCI",
    "STLFSI": "STLFSI",
}
_NODE_SHORT_NAMES = {
    "HY": "HY OAS",
    "BBB": "BBB OAS",
    "A": "A OAS",
    "CP": "단기 기업자금",
}


def _shorten(text: str, limit: int = 220) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def send(text: str, token: str | None = None, chat_id: str | None = None) -> bool:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("telegram creds missing; skip send")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("telegram send failed: %s", e)
        return False


def _fmt_row(r: pd.Series) -> str:
    from .display_text import core_name, state_name

    state = state_name(
        str(r.get("state_code", "")), str(r.get("state_label", "")),
        drop=bool(r.get("drop_flag", False)), key=str(r.get("key", "")),
    )
    return f"• {core_name(str(r['key']), short=True)}: {state}"


def _core_result_lines(matrix: pd.DataFrame) -> list[str]:
    """핵심 6개의 최신값과 1개월/3개월 변화를 모두 보여준다."""
    from . import config as C
    from .display_text import core_name, state_name
    from .formatting import fmt_change, fmt_value

    if matrix is None or matrix.empty:
        return ["핵심 지표", "• 확인 불가"]
    by_key = {str(r.get("key", "")): r for _, r in matrix.iterrows()}
    lines = ["핵심 지표 (최신값 · 약 1개월 / 약 3개월)"]
    for key in C.SERIES_ORDER:
        r = by_key.get(key)
        if r is None:
            continue
        state = state_name(
            str(r.get("state_code", "")), str(r.get("state_label", "확인 불가")),
            drop=bool(r.get("drop_flag", False)), key=key,
        )
        if r.get("latest_value") is None or pd.isna(r.get("latest_value")):
            lines.append(f"• {core_name(key, short=True)}: 값 확인 불가 · {state}")
            continue
        value = fmt_value(r.get("latest_value"), str(r.get("value_unit", "")))
        c1 = fmt_change(r.get("change_20obs"), str(r.get("change_unit", "")))
        c3 = fmt_change(r.get("change_60obs"), str(r.get("change_unit", "")))
        lines.append(f"• {core_name(key, short=True)}: {value} · {c1} / {c3} · {state}")
    return lines


def _lens_result_lines(credit_episode: dict | None) -> list[str]:
    lens = (credit_episode or {}).get("lens") or {}
    if not lens.get("available"):
        return ["", "회사채 등급 차이", "• HY-BBB: 확인 불가"]
    latest = lens.get("latest_value_bp")
    change = lens.get("change_1m_bp")
    latest_text = "확인 불가" if latest is None else f"{float(latest) / 100.0:.2f}%p"
    change_text = "확인 불가" if change is None else f"{float(change) / 100.0:+.2f}%p"
    return [
        "",
        "회사채 등급 차이 (HY-BBB)",
        f"• 투기등급-투자등급 경계 차이: {latest_text} · 약 1개월 {change_text} · {lens.get('label', '확인 불가')}",
    ]


def _rate_composition_lines(rate_composition: dict | None) -> list[str]:
    from .rate_composition import describe_rate_change, describe_total_sentence

    summary = rate_composition or {}
    lines = ["", "30년 미국 국채금리 · 최근 약 1개월"]
    if summary.get("status") != "ok":
        return lines + ["• 금리 변화를 나눠 볼 자료 확인 불가"]

    primary = summary.get("primary") or {}
    total = primary.get("DGS30_change_bp")
    real = primary.get("DFII30_change_bp")
    gap = primary.get("INFLCOMP30_change_bp")

    lines += [
        f"• 전체 금리: {describe_rate_change(total)}",
        f"• 물가 영향을 뺀 금리: {describe_rate_change(real)}",
        f"• 일반 국채와 물가연동국채의 금리 차이: {describe_rate_change(gap, gap=True)}",
        f"→ {describe_total_sentence(total)} 위 두 변화가 합쳐진 결과입니다.",
    ]
    curve = summary.get("curve") or {}
    if curve.get("text"):
        lines.append(f"• 금리 곡선: {curve['text']}")
    lines.append("• 참고: 이 금리 차이에는 물가 기대뿐 아니라 물가 위험과 채권 수요·공급 영향도 섞일 수 있습니다.")

    tp = summary.get("term_premium") or {}
    if tp.get("status") == "ok":
        change = describe_rate_change(tp.get("change_1m_bp"))
        if change == "거의 변화 없음":
            lines.append("• 참고: 10년 국채를 오래 보유할 때 시장이 요구하는 추가 보상(모형 추정)은 최근 약 1개월 거의 변하지 않았습니다.")
        else:
            change_sentence = change.replace(" 상승", " 높아졌습니다.").replace(" 하락", " 낮아졌습니다.")
            lines.append(f"• 참고: 10년 국채를 오래 보유할 때 시장이 요구하는 추가 보상(모형 추정)은 최근 약 1개월 {change_sentence}")
    else:
        lines.append("• 참고: 10년 국채 장기 보유에 대한 추가 보상은 현재 확인할 수 없습니다.")
    return lines


def _aux_row(aux_df: pd.DataFrame | None, key: str):
    if aux_df is None or aux_df.empty or "key" not in aux_df.columns:
        return None
    hit = aux_df.loc[aux_df["key"].astype(str) == key]
    if hit.empty:
        return None
    return hit.iloc[-1]


def _usable_aux_row(aux_df: pd.DataFrame | None, key: str):
    row = _aux_row(aux_df, key)
    if row is None or row.get("latest_value") is None or pd.isna(row.get("latest_value")):
        return None
    if str(row.get("staleness_label", "normal")) == "stale":
        return None
    return row


def _reference_level(aux_df: pd.DataFrame | None, key: str) -> str:
    row = _usable_aux_row(aux_df, key)
    if row is None:
        return "확인 불가"
    pct = row.get("level_pct")
    if pct is None or pd.isna(pct):
        return _DIRECTION_TEXT.get(str(row.get("direction", "확인 불가")), "확인 불가")
    pct = float(pct)
    if 40.0 <= pct <= 60.0:
        return "중간 구간"
    if key == "NFCI":
        return "과거 기준 금융여건이 빡빡한 쪽" if pct > 60 else "과거 기준 금융여건이 느슨한 쪽"
    return "과거 기준 시장 스트레스가 높은 쪽" if pct > 60 else "과거 기준 시장 스트레스가 낮은 쪽"


def _aux_result_lines(aux_df: pd.DataFrame | None, keys: list[str], title: str,
                      *, external: bool = False) -> list[str]:
    from .formatting import fmt_change, fmt_value

    lines = ["", title]
    if aux_df is None or aux_df.empty:
        return lines + ["• 확인 불가"]
    by_key = {str(r.get("key", "")): r for _, r in aux_df.iterrows()}
    added = 0
    for key in keys:
        r = by_key.get(key)
        if r is None:
            continue
        added += 1
        name = _AUX_SHORT_NAMES.get(key, key)
        if r.get("latest_value") is None or pd.isna(r.get("latest_value")):
            lines.append(f"• {name}: 값 확인 불가")
            continue
        value = fmt_value(r.get("latest_value"), str(r.get("value_unit", "")))
        change = fmt_change(r.get("change_1m"), str(r.get("change_unit", "")))
        direction = _DIRECTION_TEXT.get(str(r.get("direction", "확인 불가")), "확인 불가")
        if external:
            direction = f"{_reference_level(aux_df, key)} · {direction}"
        stale = " · 오래된 자료" if str(r.get("staleness_label", "normal")) == "stale" else ""
        lines.append(f"• {name}: {value} · {change} · {direction}{stale}")
    return lines if added else lines + ["• 확인 불가"]


def _axis_lines(axes: dict | None, matrix: pd.DataFrame) -> list[str]:
    from .display_text import state_name

    if not axes:
        return [_fmt_row(r) for _, r in matrix.iterrows()]
    vc = axes.get("vol_credit") or {}
    cy = axes.get("cycle") or {}
    rt = axes.get("rate") or {}
    changed_count = axes.get("changed_count")
    if changed_count is None:
        changed_count = len(axes.get("changed_axes") or [])
    vc_text = _VOL_CREDIT_LABELS.get(str(vc.get("state")), str(vc.get("label", "확인 불가")))
    cycle_text = state_name(cy.get("state"), cy.get("label", "확인 불가"), key="T10Y3M")
    rate_text = _RATE_RESULTS.get(str(rt.get("result")), str(rt.get("result", "확인 불가")))
    return [
        f"현재 3개 영역 중 {changed_count}개에서 눈에 띄는 움직임",
        f"• 주식시장·기업 신용: {vc_text}",
        f"• 경기 흐름: {cycle_text}",
        f"• 금리 움직임: {rate_text}",
    ]


def _reading_lines(readings: list[dict] | None) -> list[str]:
    from .display_text import plain_language

    if not readings:
        return ["", "눈에 띄는 조합과 해석", "• 현재 정의된 주요 조합은 따로 잡히지 않음"]
    lines = ["", "눈에 띄는 조합과 해석"]
    for reading in readings[:2]:
        label = plain_language(str(reading.get("label", "현재 조합"))).strip()
        explanations = {
            str(x.get("id", "")): plain_language(str(x.get("text", ""))).strip()
            for x in (reading.get("explanations") or []) if x.get("id")
        }
        supported = [
            explanations[x] for x in (reading.get("supported_ids") or [])
            if x in explanations and explanations[x]
        ]
        if supported:
            interpretation = supported[0]
        elif reading.get("conflict"):
            interpretation = "서로 다른 설명을 가리키는 부분이 있음: " + plain_language(str(reading.get("conflict")))
        else:
            interpretation = plain_language(str(reading.get("uncertainty") or "함께 볼 지표만으로 한 설명이 뚜렷하게 앞서지 않음"))
        lines.append(f"• {label}: {_shorten(interpretation)}")
    return lines


def _credit_episode_lines(credit_episode: dict | None) -> list[str]:
    if not credit_episode:
        return ["", "기업 신용", "• 현재 상태를 확인할 수 없음"]
    current = credit_episode.get("current") or {}
    episode = current.get("episode") or {}
    nodes = current.get("nodes") or {}
    lens = credit_episode.get("lens") or {}
    vix = credit_episode.get("vix_context") or {}
    lines = ["", "기업 신용"]
    lines.append(f"• 전체 흐름: {episode.get('state_label', '확인 불가')}")
    lines.append(f"• 움직이는 시장: {current.get('scope_text', '확인 불가')}")
    states = []
    for node in ("HY", "BBB", "A", "CP"):
        row = nodes.get(node) or {}
        if row.get("available"):
            states.append(f"{_NODE_SHORT_NAMES[node]} {row.get('state_label', '확인 불가')}")
    if states:
        lines.append("• 시장별 상태: " + " · ".join(states))
    if lens.get("available"):
        lines.append(f"• HY−BBB: {lens.get('label', '확인 불가')}")
    cp_calendar = current.get("cp_calendar_context") or {}
    if cp_calendar.get("year_end"):
        lines.append(f"• 단기자금 진단: {cp_calendar.get('note', '연말 기술요인도 확인')}")
    if vix.get("available"):
        lines.append(f"• 주식시장 맥락: {vix.get('onset', '확인 불가')} · {vix.get('current', '확인 불가')}")
    prior = episode.get("prior_residual_nodes") or []
    if prior:
        names = ", ".join(_NODE_SHORT_NAMES.get(x, x) for x in prior)
        lines.append(f"• 이전 변화가 남아 있는 시장: {names}")
    return lines


def _external_summary(aux_df: pd.DataFrame | None) -> list[str]:
    if aux_df is None or aux_df.empty:
        return []
    return [
        "",
        "외부 참고",
        f"• 자금 사정: {_reference_level(aux_df, 'NFCI')} · 시장 불안: {_reference_level(aux_df, 'STLFSI')}",
    ]


def _build_summary(title: str, matrix: pd.DataFrame, synced: dict,
                   *, axes: dict | None = None, readings: list[dict] | None = None,
                   aux_df: pd.DataFrame | None = None,
                   credit_episode: dict | None = None,
                   rate_composition: dict | None = None,
                   notice_lines: list[str] | None = None) -> str:
    from . import aux_config as AC

    lines = [title, ""]
    if notice_lines:
        lines.extend(notice_lines)
        lines.append("")
    lines.extend(_core_result_lines(matrix))
    lines.extend(_rate_composition_lines(rate_composition))
    lines.extend(_lens_result_lines(credit_episode))
    lines.extend(_aux_result_lines(aux_df, AC.TELEGRAM_CONFIRM_AUX_ORDER, "확인 지표 (최신값 · 약 1개월)"))
    lines.extend(_aux_result_lines(aux_df, AC.EXTERNAL_AUX_ORDER, "외부 참고 지표 (최신값 · 약 1개월)", external=True))
    lines.extend(_credit_episode_lines(credit_episode))
    lines += ["", "여러 지표를 같이 보면"]
    lines.extend(_axis_lines(axes, matrix))
    lines.extend(_reading_lines(readings))
    lines.extend(_external_summary(aux_df))
    lines += ["", f"데이터 기준일: {synced.get('synced_date') or '확인 불가'}"]
    text = "\n".join(lines)
    return text if len(text) <= 3900 else text[:3899] + "…"


def build_success(batch_kst: str, cache_version: str, matrix: pd.DataFrame,
                  synced: dict, stale: list[str], *, axes: dict | None = None,
                  readings: list[dict] | None = None,
                  aux_df: pd.DataFrame | None = None,
                  credit_episode: dict | None = None,
                  rate_composition: dict | None = None) -> str:
    del batch_kst, cache_version, stale  # 정상 알림에는 운영 메타데이터를 넣지 않는다.
    return _build_summary(
        "✅ RiskRadar 업데이트 완료", matrix, synced,
        axes=axes, readings=readings, aux_df=aux_df, credit_episode=credit_episode,
        rate_composition=rate_composition,
    )


def build_partial(cache_version: str, matrix: pd.DataFrame, synced: dict,
                  failed: list[str], stale: list[str], *, axes: dict | None = None,
                  readings: list[dict] | None = None,
                  aux_df: pd.DataFrame | None = None,
                  credit_episode: dict | None = None,
                  rate_composition: dict | None = None) -> str:
    del cache_version
    notice = ["⚠️ 일부 핵심 데이터는 직전 정상값을 사용했습니다."]
    if failed:
        notice.append("• 이번 수집 실패: " + ", ".join(failed))
    if stale:
        notice.append("• 직전 정상값 사용: " + ", ".join(stale))
    return _build_summary(
        "⚠️ RiskRadar 부분 업데이트", matrix, synced,
        axes=axes, readings=readings, aux_df=aux_df,
        credit_episode=credit_episode, rate_composition=rate_composition,
        notice_lines=notice,
    )


def build_failure(step: str, error: str) -> str:
    return f"❌ RiskRadar 데이터 업데이트 실패\n\n단계: {step}\n오류: {_shorten(error, 500)}"
