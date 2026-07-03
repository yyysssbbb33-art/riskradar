"""Telegram 알림.

원칙: 매매 조언/폭락 예측/확률 표현 금지. 6개 지표 상태 + 데이터 상태만.
Telegram 실패는 데이터 갱신 성공을 깨지 않는다 (telegram_sent=False로 기록).
"""
from __future__ import annotations

import logging
import os

import pandas as pd
import requests

log = logging.getLogger(__name__)


def send(text: str, token: str | None = None, chat_id: str | None = None) -> bool:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("telegram creds missing; skip send")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "disable_web_page_preview": True},
            timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("telegram send failed: %s", e)
        return False


def _fmt_row(r: pd.Series) -> str:
    from .formatting import fmt_value
    val = fmt_value(r["latest_value"], r["value_unit"])
    tail = ""
    if pd.notna(r["percentile_10y"]):
        tail = f" | 10Y pct {r['percentile_10y']:.0f}%"
    elif pd.notna(r["change_60obs"]):
        tail = f" | 60obs {r['change_60obs']:+.0f}bp"
    drop = " ↓급락" if r["drop_flag"] else ""
    return f"[{r['display_name']}] {r['state_label']} | {val}{tail}{drop}"


def build_success(batch_kst: str, cache_version: str, matrix: pd.DataFrame,
                  synced: dict, stale: list[str]) -> str:
    lines = ["✅ RiskRadar 업데이트 완료", "",
             f"기준: {batch_kst}", f"캐시: {cache_version}", ""]
    lines += [_fmt_row(r) for _, r in matrix.iterrows()]
    lines += ["", f"Synced date: {synced.get('synced_date')}"]
    lines.append(f"Stale series: {', '.join(stale) if stale else 'none'}")
    return "\n".join(lines)


def build_partial(cache_version: str, matrix: pd.DataFrame, synced: dict,
                  failed: list[str], stale: list[str]) -> str:
    lines = ["⚠️ RiskRadar 부분 업데이트", "",
             f"캐시: {cache_version}",
             f"실패 fetch: {', '.join(failed)}",
             "처리: 직전 성공 raw 유지, stale 표시", ""]
    lines += [_fmt_row(r) for _, r in matrix.iterrows()]
    lines += ["", f"Synced date: {synced.get('synced_date')}",
              f"Stale series: {', '.join(stale)}"]
    return "\n".join(lines)


def build_failure(stage: str, error: str) -> str:
    return ("❌ RiskRadar 업데이트 실패\n\n"
            f"단계: {stage}\n에러: {error}\n\n"
            "새 캐시를 발행하지 않았습니다. 이전 캐시가 UI에 계속 표시됩니다.")
