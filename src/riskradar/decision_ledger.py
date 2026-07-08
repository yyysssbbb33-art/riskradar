"""권위 있는 판정 스냅샷을 장기 보존하는 작은 판정 원장.

원칙:
- 현재 raw를 다시 계산해 과거 판정을 만들지 않는다.
- ``authoritative == true``인 저장 당시 decision_snapshot만 옮긴다.
- ``(cache_version, section, key)``를 고유키로 삼아 재실행을 중복 저장하지 않는다.
- 같은 고유키에 다른 내용이 들어오면 조용히 덮지 않고 충돌로 처리한다.
- 상세 원문은 ``payload_json``에 함께 남겨 미래 검증에서 정보 손실을 줄인다.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

LEDGER_SCHEMA_VERSION = "decision-ledger-v1"
LEDGER_KEY_COLUMNS = ["cache_version", "section", "key"]
LEDGER_COLUMNS = [
    "ledger_schema_version",
    "snapshot_format_version",
    "cache_version",
    "batch_generated_at",
    "app_version",
    "section",
    "key",
    "decision_schema",
    "observed_date",
    "source_status",
    "decision_code",
    "decision_label",
    "latest_value",
    "value_unit",
    "payload_sha256",
    "payload_json",
]


def empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def _payload_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_hash(payload_text: str) -> str:
    return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()


def _scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _row(
    *,
    batch: dict[str, Any],
    snapshot_format_version: Any,
    section: str,
    key: str,
    decision_schema: str,
    payload: dict[str, Any],
    code_field: str,
    label_field: str,
    value_field: str = "latest_value",
    fixed_value_unit: str | None = None,
) -> dict[str, Any]:
    payload_text = _payload_text(payload)
    return {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "snapshot_format_version": _scalar(snapshot_format_version),
        "cache_version": str(batch.get("cache_version") or ""),
        "batch_generated_at": str(batch.get("generated_at") or ""),
        "app_version": str(batch.get("app_version") or ""),
        "section": section,
        "key": key,
        "decision_schema": decision_schema,
        "observed_date": _scalar(payload.get("observed_date")),
        "source_status": _scalar(payload.get("source_status")),
        "decision_code": _scalar(payload.get(code_field)),
        "decision_label": _scalar(payload.get(label_field)),
        "latest_value": _scalar(payload.get(value_field)),
        "value_unit": fixed_value_unit if fixed_value_unit is not None else _scalar(payload.get("value_unit")),
        "payload_sha256": _payload_hash(payload_text),
        "payload_json": payload_text,
    }


def snapshot_to_ledger_rows(snapshot: dict[str, Any] | None) -> pd.DataFrame:
    """권위 snapshot 하나를 장기 보존용 행들로 펼친다."""
    if not snapshot or snapshot.get("authoritative") is not True:
        return empty_ledger()

    batch = snapshot.get("batch") or {}
    cache_version = str(batch.get("cache_version") or "")
    if not cache_version:
        raise ValueError("authoritative decision snapshot missing cache_version")

    schemas = snapshot.get("schemas") or {}
    fmt = snapshot.get("snapshot_format_version")
    rows: list[dict[str, Any]] = []

    for key, payload in sorted((snapshot.get("core") or {}).items()):
        rows.append(_row(
            batch=batch,
            snapshot_format_version=fmt,
            section="core",
            key=str(key),
            decision_schema=str(schemas.get("core_state") or ""),
            payload=payload or {},
            code_field="state_code",
            label_field="state_label",
        ))

    for key, payload in sorted((snapshot.get("aux") or {}).items()):
        rows.append(_row(
            batch=batch,
            snapshot_format_version=fmt,
            section="aux",
            key=str(key),
            decision_schema=str(schemas.get("aux_direction") or ""),
            payload=payload or {},
            code_field="direction",
            label_field="direction",
        ))

    credit = snapshot.get("credit") or {}
    credit_schema = str(schemas.get("credit_episode") or "")
    for key, payload in sorted((credit.get("nodes") or {}).items()):
        rows.append(_row(
            batch=batch,
            snapshot_format_version=fmt,
            section="credit_node",
            key=str(key),
            decision_schema=credit_schema,
            payload=payload or {},
            code_field="state",
            label_field="state_label",
        ))

    # 에피소드가 없다는 판정도 당시 상태이므로 매 권위 snapshot마다 한 행을 남긴다.
    episode = credit.get("episode") or {}
    rows.append(_row(
        batch=batch,
        snapshot_format_version=fmt,
        section="credit_episode",
        key="episode",
        decision_schema=credit_schema,
        payload=episode,
        code_field="state",
        label_field="state_label",
    ))

    lens = credit.get("lens") or {}
    rows.append(_row(
        batch=batch,
        snapshot_format_version=fmt,
        section="credit_lens",
        key="HY_BBB",
        decision_schema=credit_schema,
        payload=lens,
        code_field="state",
        label_field="label",
        value_field="latest_value_bp",
        fixed_value_unit="bp",
    ))

    return pd.DataFrame(rows, columns=LEDGER_COLUMNS)


def _normalise(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_ledger()
    out = df.copy()
    for col in LEDGER_COLUMNS:
        if col not in out.columns:
            out[col] = None
    return out[LEDGER_COLUMNS].copy()


def ledger_versions(df: pd.DataFrame | None) -> set[str]:
    df = _normalise(df)
    if df.empty:
        return set()
    return {str(x) for x in df["cache_version"].dropna().tolist() if str(x)}


def _assert_unique_keys(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        return
    dup = df.loc[df.duplicated(subset=LEDGER_KEY_COLUMNS, keep=False), LEDGER_KEY_COLUMNS]
    if not dup.empty:
        sample = tuple(dup.iloc[0][c] for c in LEDGER_KEY_COLUMNS)
        raise RuntimeError(
            f"duplicate decision ledger key in {label}: "
            f"cache_version={sample[0]} section={sample[1]} key={sample[2]}"
        )


def merge_ledgers(existing: pd.DataFrame | None, incoming: pd.DataFrame | None) -> pd.DataFrame:
    """기존 원장에 새 행을 idempotent하게 합친다.

    같은 고유키의 payload가 다르면 저장 당시 기록이 바뀐 것이므로 충돌로 처리한다.
    기존 행을 조용히 덮어쓰지 않는다.
    """
    left = _normalise(existing)
    right = _normalise(incoming)
    _assert_unique_keys(left, "existing ledger")
    _assert_unique_keys(right, "incoming snapshot rows")
    if right.empty:
        return left.sort_values(LEDGER_KEY_COLUMNS).reset_index(drop=True)

    if not left.empty:
        old = left.set_index(LEDGER_KEY_COLUMNS)["payload_sha256"].astype(str)
        new = right.set_index(LEDGER_KEY_COLUMNS)["payload_sha256"].astype(str)
        overlap = old.index.intersection(new.index)
        conflicts = [idx for idx in overlap if old.loc[idx] != new.loc[idx]]
        if conflicts:
            sample = conflicts[0]
            raise RuntimeError(
                "decision ledger conflict for "
                f"cache_version={sample[0]} section={sample[1]} key={sample[2]}"
            )

    merged = right.copy() if left.empty else pd.concat([left, right], ignore_index=True)
    merged = merged.drop_duplicates(subset=LEDGER_KEY_COLUMNS, keep="first")
    return merged.sort_values(LEDGER_KEY_COLUMNS).reset_index(drop=True)
