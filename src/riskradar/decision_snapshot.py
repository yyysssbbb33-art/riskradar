"""권위 있는 배치별 판정 스냅샷과 안전한 변화 비교.

핵심 원칙:
- 당시 배치가 실제 저장한 판정만 비교한다. ``monthly_view`` 재구성본은 사용하지 않는다.
- v0.6.2 이전 캐시는 백필하지 않는다. ``decision_snapshot``이 없는 버전은 권위 있는 기록이 아니다.
- 앱 버전과 판정 규칙 버전을 분리한다. 영역별 판정 schema가 다르면 그 영역의 비교만 보류한다.
- 관측일이 전진하지 않은 판정 변화는 시장 변화로 세지 않는다.
- 데이터 장애와 시장 변화를 분리하고, 복구 뒤 판정이 달라졌다면 발생 시점 불명확한 복합 사건으로 기록한다.
- 필드 부재나 snapshot 포맷 변화 자체를 시장 변화로 세지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import aux_config as AC

SNAPSHOT_FORMAT_VERSION = 1
CORE_STATE_SCHEMA = "core-v1"
CREDIT_EPISODE_SCHEMA = "credit-v1"
AUX_DIRECTION_SCHEMA = "aux-v1"

SCHEMA_KEYS = {
    "core": "core_state",
    "credit": "credit_episode",
    "aux": "aux_direction",
}



@dataclass(frozen=True)
class DecisionSnapshotSchemas:
    core_state: str = CORE_STATE_SCHEMA
    credit_episode: str = CREDIT_EPISODE_SCHEMA
    aux_direction: str = AUX_DIRECTION_SCHEMA

    def to_dict(self) -> dict[str, str]:
        return {
            "core_state": self.core_state,
            "credit_episode": self.credit_episode,
            "aux_direction": self.aux_direction,
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if not isinstance(value, (str, bytes, dict, list, tuple, set)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    return value


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)


def _number(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) or math.isinf(out) else out


def _iso_date(value: Any) -> str | None:
    if value is None or str(value) in {"", "None", "nan", "NaT", "<NA>"}:
        return None
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:  # noqa: BLE001 - 진단 스냅샷은 잘못된 날짜 하나로 배치를 깨지 않는다.
        return None


def _source_status_from_aux(row: pd.Series | dict | None) -> str:
    if row is None:
        return "unavailable"
    get = row.get
    fetch_status = _text(get("fetch_status"), "failed")
    staleness = _text(get("staleness_label"), "unknown")
    if fetch_status == "carried_forward":
        return "carried_forward"
    if fetch_status != "ok":
        return "failed"
    if staleness == "stale":
        return "stale"
    return "ok"


def _worse_source_status(statuses: Iterable[str]) -> str:
    priority = {"failed": 5, "stale": 4, "carried_forward": 3, "unavailable": 2, "ok": 1}
    items = [str(s or "unavailable") for s in statuses]
    return max(items, key=lambda s: priority.get(s, 2)) if items else "unavailable"


def _rows_by_key(df: pd.DataFrame | None) -> dict[str, pd.Series]:
    if df is None or df.empty or "key" not in df.columns:
        return {}
    return {
        str(row["key"]): row
        for _, row in df.drop_duplicates(subset=["key"], keep="last").iterrows()
    }


def build_decision_snapshot(
    *,
    cache_version: str,
    generated_at: str,
    app_version: str,
    signal_matrix: pd.DataFrame,
    aux_matrix: pd.DataFrame | None,
    credit_quality: dict | None,
    failed_series: Iterable[str] = (),
    stale_series: Iterable[str] = (),
    schemas: DecisionSnapshotSchemas | None = None,
) -> dict:
    """현재 배치가 실제 만든 판정을 권위 있는 JSON 스냅샷으로 고정한다."""
    schemas = schemas or DecisionSnapshotSchemas()
    failed = {str(x) for x in failed_series}
    stale = {str(x) for x in stale_series}
    aux_rows = _rows_by_key(aux_matrix)

    core: dict[str, dict] = {}
    if signal_matrix is not None and not signal_matrix.empty:
        for _, row in signal_matrix.iterrows():
            key = str(row.get("key", ""))
            if not key:
                continue
            source_status = "stale" if key in stale else ("failed" if key in failed else "ok")
            core[key] = {
                "observed_date": _iso_date(row.get("latest_observed_date")),
                "source_status": source_status,
                "state_code": _text(row.get("state_code")),
                "state_label": _text(row.get("state_label")),
                "drop_flag": bool(row.get("drop_flag", False)),
                "latest_value": _number(row.get("latest_value")),
                "value_unit": _text(row.get("value_unit")),
            }

    aux: dict[str, dict] = {}
    for key in AC.AUX_ORDER:
        row = aux_rows.get(key)
        if row is None:
            aux[key] = {
                "observed_date": None,
                "source_status": "unavailable",
                "direction": "확인 불가",
                "latest_value": None,
                "value_unit": AC.AUX_SERIES[key].value_unit,
                "fetch_status": "missing",
                "staleness_label": "unknown",
            }
            continue
        aux[key] = {
            "observed_date": _iso_date(row.get("latest_date")),
            "source_status": _source_status_from_aux(row),
            "direction": _text(row.get("direction"), "확인 불가"),
            "latest_value": _number(row.get("latest_value")),
            "value_unit": _text(row.get("value_unit"), AC.AUX_SERIES[key].value_unit),
            "fetch_status": _text(row.get("fetch_status"), "failed"),
            "staleness_label": _text(row.get("staleness_label"), "unknown"),
        }

    credit_quality = credit_quality or {}
    current = credit_quality.get("current") or {}
    current_nodes = current.get("nodes") or {}
    current_episode = current.get("episode") or {}
    participants = {str(x) for x in (current_episode.get("participants") or [])}
    source_map = {"HY": ("core", "HYOAS"), "BBB": ("aux", "BBBOAS"), "A": ("aux", "AOAS"), "CP": ("aux", "CPSPREAD")}
    credit_nodes: dict[str, dict] = {}
    for node in ("HY", "BBB", "A", "CP"):
        data = current_nodes.get(node) or {}
        source_layer, source_key = source_map[node]
        source_status = (
            core.get(source_key, {}).get("source_status", "unavailable")
            if source_layer == "core"
            else aux.get(source_key, {}).get("source_status", "unavailable")
        )
        available = bool(data.get("available", False))
        if not available and source_status == "ok":
            source_status = "unavailable"
        credit_nodes[node] = {
            "observed_date": _iso_date(data.get("date")),
            "source_status": source_status,
            "available": available,
            "state": _text(data.get("state"), "unavailable"),
            "state_label": _text(data.get("state_label"), "확인 불가"),
            "participant": node in participants,
            "latest_value": _number(data.get("value")),
            "residual_change": _number(data.get("residual_change")),
            "residual_ratio": _number(data.get("residual_ratio")),
            "estimated_onset": _iso_date(data.get("estimated_onset")),
            "confirmed_at": _iso_date(data.get("confirmed_at")),
        }

    episode = {
        "episode_id": _text(current_episode.get("episode_id"), "none"),
        "state": _text(current_episode.get("state"), "none"),
        "state_label": _text(current_episode.get("state_label"), "없음"),
        "participants": sorted(participants),
        "last_meaningful_activity_at": _iso_date(current_episode.get("last_meaningful_activity_at")),
        "dormant_at": _iso_date(current_episode.get("dormant_at")),
        "ended_at": _iso_date(current_episode.get("ended_at")),
    }

    lens = credit_quality.get("lens") or {}
    lens_source_status = _worse_source_status([
        credit_nodes["HY"]["source_status"], credit_nodes["BBB"]["source_status"]
    ])
    credit_lens = {
        "observed_date": _iso_date(lens.get("latest_date")),
        "source_status": lens_source_status,
        "available": bool(lens.get("available", False)),
        "state": _text(lens.get("state"), "unavailable"),
        "label": _text(lens.get("label"), "확인 불가"),
        "latest_value_bp": _number(lens.get("latest_value_bp")),
    }

    snapshot = {
        "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
        "authoritative": True,
        "batch": {
            "cache_version": str(cache_version),
            "generated_at": str(generated_at),
            "app_version": str(app_version),
        },
        "schemas": schemas.to_dict(),
        "core": core,
        "credit": {
            "nodes": credit_nodes,
            "episode": episode,
            "lens": credit_lens,
        },
        "aux": aux,
        "data_quality": {
            "failed_series": sorted(failed),
            "stale_series": sorted(stale),
            "aux_failed": sorted(k for k, v in aux.items() if v["source_status"] == "failed"),
            "aux_carried_forward": sorted(k for k, v in aux.items() if v["source_status"] == "carried_forward"),
            "aux_stale": sorted(k for k, v in aux.items() if v["source_status"] == "stale"),
        },
    }
    return _json_safe(snapshot)


def _date_cmp(previous: Any, current: Any) -> str:
    p = _iso_date(previous)
    c = _iso_date(current)
    if p is None or c is None:
        return "unknown"
    pt, ct = pd.Timestamp(p), pd.Timestamp(c)
    if ct > pt:
        return "advanced"
    if ct < pt:
        return "regressed"
    return "same"


def _decision_signature(entity: dict, fields: tuple[str, ...]) -> tuple[Any, ...] | None:
    if not isinstance(entity, dict) or any(field not in entity for field in fields):
        return None
    return tuple(_json_safe(entity.get(field)) for field in fields)


def _event(
    *,
    category: str,
    transition_type: str,
    section: str,
    key: str,
    previous: Any = None,
    current: Any = None,
    previous_observed_date: Any = None,
    current_observed_date: Any = None,
    message: str,
    timing_uncertain: bool = False,
    details: dict | None = None,
) -> dict:
    return _json_safe({
        "category": category,
        "transition_type": transition_type,
        "section": section,
        "key": key,
        "previous": previous,
        "current": current,
        "previous_observed_date": _iso_date(previous_observed_date),
        "current_observed_date": _iso_date(current_observed_date),
        "timing_uncertain": bool(timing_uncertain),
        "message": message,
        "details": details or {},
    })


def _schema_status(previous: dict, current: dict, section: str) -> tuple[bool, str | None, str | None]:
    schema_key = SCHEMA_KEYS[section]
    p = (previous.get("schemas") or {}).get(schema_key)
    c = (current.get("schemas") or {}).get(schema_key)
    return bool(p and c and p == c), p, c


def _compare_source_statuses(previous: dict, current: dict, section: str, result: dict) -> None:
    psec = previous.get(section) or {}
    csec = current.get(section) or {}
    if not isinstance(psec, dict) or not isinstance(csec, dict):
        return
    for key in sorted(set(psec) | set(csec)):
        p = psec.get(key)
        c = csec.get(key)
        if not isinstance(p, dict) or not isinstance(c, dict):
            continue
        if "source_status" not in p or "source_status" not in c:
            continue
        ps, cs = str(p.get("source_status")), str(c.get("source_status"))
        if ps == cs:
            continue
        label = "핵심 지표" if section == "core" else "함께 볼 지표"
        result["data_quality_transitions"].append(_event(
            category="data_quality",
            transition_type="data_quality_transition",
            section=section,
            key=key,
            previous=ps,
            current=cs,
            previous_observed_date=p.get("observed_date"),
            current_observed_date=c.get("observed_date"),
            message=f"{label} {key}의 데이터 상태가 {ps} → {cs}로 바뀌었습니다.",
        ))


def _decision_display(entity: dict, label_field: str, fields: tuple[str, ...]) -> str:
    label = _text(entity.get(label_field), "확인 불가")
    if "participant" in fields:
        label += " · 변화" if bool(entity.get("participant")) else " · 뚜렷한 변화 없음"
    if "drop_flag" in fields and bool(entity.get("drop_flag")):
        label += " · 단기 하락 플래그"
    return label


def _compare_entities(
    *,
    previous_entities: dict,
    current_entities: dict,
    section: str,
    fields: tuple[str, ...],
    label_field: str,
    result: dict,
) -> None:
    for key in sorted(set(previous_entities) | set(current_entities)):
        p = previous_entities.get(key)
        c = current_entities.get(key)
        if not isinstance(p, dict) or not isinstance(c, dict):
            result["diagnostics"].append({
                "kind": "field_unavailable", "section": section, "key": key,
                "message": "한쪽 스냅샷에 비교 대상 항목이 없어 변화로 세지 않았습니다.",
            })
            continue
        psig = _decision_signature(p, fields)
        csig = _decision_signature(c, fields)
        if psig is None or csig is None:
            result["diagnostics"].append({
                "kind": "field_unavailable", "section": section, "key": key,
                "message": "비교 필드가 없어 변화로 세지 않았습니다.",
            })
            continue
        if psig == csig:
            continue

        ps = str(p.get("source_status", "unavailable"))
        cs = str(c.get("source_status", "unavailable"))
        date_status = _date_cmp(p.get("observed_date"), c.get("observed_date"))
        previous_label = _decision_display(p, label_field, fields)
        current_label = _decision_display(c, label_field, fields)

        if cs != "ok":
            result["diagnostics"].append({
                "kind": "market_change_suppressed_data_issue", "section": section, "key": key,
                "message": "현재 데이터 상태가 정상이 아니어서 판정 차이를 시장 변화로 세지 않았습니다.",
            })
            continue

        if ps != "ok":
            if date_status == "advanced":
                result["recovery_gap_events"].append(_event(
                    category="recovery_gap",
                    transition_type="recovery_with_gap_change",
                    section=section,
                    key=key,
                    previous=previous_label,
                    current=current_label,
                    previous_observed_date=p.get("observed_date"),
                    current_observed_date=c.get("observed_date"),
                    timing_uncertain=True,
                    message=(f"{key} 자료가 복구됐고 판정도 {previous_label} → {current_label}로 달라졌습니다. "
                             "수집 공백 중 정확히 언제 변화했는지는 확인할 수 없습니다."),
                ))
            else:
                result["diagnostics"].append({
                    "kind": "recovery_without_new_observation", "section": section, "key": key,
                    "message": "데이터는 복구됐지만 새 관측일 전진이 없어 시장 변화로 세지 않았습니다.",
                })
            continue

        if date_status == "advanced":
            result["market_transitions"].append(_event(
                category="market",
                transition_type="new_observation_transition",
                section=section,
                key=key,
                previous=previous_label,
                current=current_label,
                previous_observed_date=p.get("observed_date"),
                current_observed_date=c.get("observed_date"),
                message=f"{key} 판정이 {previous_label} → {current_label}로 바뀌었습니다.",
            ))
        else:
            kind = "observation_regressed" if date_status == "regressed" else "same_observation_decision_drift"
            result["diagnostics"].append({
                "kind": kind, "section": section, "key": key,
                "message": "관측일이 전진하지 않은 판정 차이를 시장 변화로 세지 않았습니다.",
            })


def _credit_observation_advanced(previous: dict, current: dict) -> bool:
    pnodes = ((previous.get("credit") or {}).get("nodes") or {})
    cnodes = ((current.get("credit") or {}).get("nodes") or {})
    for node in set(pnodes) & set(cnodes):
        p = pnodes.get(node) or {}
        c = cnodes.get(node) or {}
        if c.get("source_status") == "ok" and _date_cmp(p.get("observed_date"), c.get("observed_date")) == "advanced":
            return True
    return False


def compare_decision_snapshots(previous: dict | None, current: dict) -> dict:
    """두 권위 있는 판정 스냅샷을 비교한다.

    ``previous``가 없으면 cold start다. schema/필드 부재/데이터 문제는 시장 transition으로 세지 않는다.
    """
    current = current or {}
    result = {
        "status": "ok",
        "previous_cache_version": ((previous or {}).get("batch") or {}).get("cache_version"),
        "current_cache_version": (current.get("batch") or {}).get("cache_version"),
        "snapshot_format": {
            "previous": (previous or {}).get("snapshot_format_version"),
            "current": current.get("snapshot_format_version"),
            "compatible": False,
        },
        "section_compatibility": {},
        "market_transitions": [],
        "data_quality_transitions": [],
        "recovery_gap_events": [],
        "schema_boundaries": [],
        "diagnostics": [],
    }

    if not previous:
        result["status"] = "cold_start"
        result["cold_start_reason"] = "no_authoritative_previous_snapshot"
        result["summary"] = {
            "market": 0, "data_quality": 0, "recovery_gap": 0, "schema_boundary": 0,
        }
        return _json_safe(result)

    pformat = previous.get("snapshot_format_version")
    cformat = current.get("snapshot_format_version")
    result["snapshot_format"]["compatible"] = bool(pformat is not None and pformat == cformat)
    if pformat != cformat:
        result["schema_boundaries"].append(_event(
            category="schema_boundary",
            transition_type="schema_boundary",
            section="snapshot_format",
            key="snapshot_format_version",
            previous=pformat,
            current=cformat,
            message=f"판정 스냅샷 포맷이 {pformat} → {cformat}로 바뀌었습니다. 필드 추가 자체는 시장 변화로 세지 않습니다.",
        ))

    for section in ("core", "credit", "aux"):
        compatible, pschema, cschema = _schema_status(previous, current, section)
        result["section_compatibility"][section] = {
            "compatible": compatible,
            "previous": pschema,
            "current": cschema,
        }
        if not compatible:
            result["schema_boundaries"].append(_event(
                category="schema_boundary",
                transition_type="schema_boundary",
                section=section,
                key=SCHEMA_KEYS[section],
                previous=pschema,
                current=cschema,
                message=f"{section} 판정 규칙이 {pschema} → {cschema}로 바뀌어 이 영역 비교를 보류합니다.",
            ))

    # 데이터 상태 변화는 시장 판정 schema와 독립적으로 기록한다.
    _compare_source_statuses(previous, current, "core", result)
    _compare_source_statuses(previous, current, "aux", result)

    if result["section_compatibility"]["core"]["compatible"]:
        _compare_entities(
            previous_entities=previous.get("core") or {},
            current_entities=current.get("core") or {},
            section="core",
            fields=("state_code", "drop_flag"),
            label_field="state_label",
            result=result,
        )

    if result["section_compatibility"]["aux"]["compatible"]:
        _compare_entities(
            previous_entities=previous.get("aux") or {},
            current_entities=current.get("aux") or {},
            section="aux",
            fields=("direction",),
            label_field="direction",
            result=result,
        )

    if result["section_compatibility"]["credit"]["compatible"]:
        pcredit = previous.get("credit") or {}
        ccredit = current.get("credit") or {}
        _compare_entities(
            previous_entities=pcredit.get("nodes") or {},
            current_entities=ccredit.get("nodes") or {},
            section="credit_nodes",
            fields=("state", "participant"),
            label_field="state_label",
            result=result,
        )
        _compare_entities(
            previous_entities={"HY_BBB": pcredit.get("lens") or {}},
            current_entities={"HY_BBB": ccredit.get("lens") or {}},
            section="credit_lens",
            fields=("state",),
            label_field="label",
            result=result,
        )

        pep = pcredit.get("episode") or {}
        cep = ccredit.get("episode") or {}
        required = ("episode_id", "state", "participants")
        psig = _decision_signature(pep, required)
        csig = _decision_signature(cep, required)
        if psig is None or csig is None:
            result["diagnostics"].append({
                "kind": "field_unavailable", "section": "credit_episode", "key": "episode",
                "message": "변화 흐름 비교 필드가 없어 변화로 세지 않았습니다.",
            })
        elif psig != csig:
            pnodes = pcredit.get("nodes") or {}
            cnodes = ccredit.get("nodes") or {}
            relevant_nodes = set(pep.get("participants") or []) | set(cep.get("participants") or [])
            unreliable_nodes = sorted(
                node for node in relevant_nodes
                if str((pnodes.get(node) or {}).get("source_status", "unavailable")) != "ok"
                or str((cnodes.get(node) or {}).get("source_status", "unavailable")) != "ok"
            )
            if unreliable_nodes:
                result["diagnostics"].append({
                    "kind": "episode_change_suppressed_data_issue",
                    "section": "credit_episode",
                    "key": "episode",
                    "nodes": unreliable_nodes,
                    "message": "변화 관련 노드의 데이터 상태가 정상이 아니어서 변화 흐름 차이를 시장 변화로 세지 않았습니다.",
                })
            elif _credit_observation_advanced(previous, current):
                same_episode = pep.get("episode_id") == cep.get("episode_id")
                state_changed = pep.get("state") != cep.get("state")
                observation_clock = same_episode and state_changed and cep.get("state") in {"dormant", "ended"}
                transition_type = "observation_clock_transition" if observation_clock else "new_observation_transition"
                result["market_transitions"].append(_event(
                    category="market",
                    transition_type=transition_type,
                    section="credit_episode",
                    key="episode",
                    previous={"episode_id": pep.get("episode_id"), "state": pep.get("state"), "participants": pep.get("participants")},
                    current={"episode_id": cep.get("episode_id"), "state": cep.get("state"), "participants": cep.get("participants")},
                    message=("신용 변화 흐름가 관측 타임라인 경과로 상태 전환했습니다."
                             if observation_clock else "신용 변화 흐름의 상태 또는 변화가 나타난 곳이 바뀌었습니다."),
                ))
            else:
                result["diagnostics"].append({
                    "kind": "same_observation_episode_drift", "section": "credit_episode", "key": "episode",
                    "message": "새 신용 관측 없이 달라진 변화 흐름 판정을 시장 변화로 세지 않았습니다.",
                })

    if result["schema_boundaries"] and not (result["market_transitions"] or result["data_quality_transitions"] or result["recovery_gap_events"]):
        result["status"] = "schema_boundary"
    elif result["schema_boundaries"]:
        result["status"] = "partial_schema_boundary"

    result["summary"] = {
        "market": len(result["market_transitions"]),
        "data_quality": len(result["data_quality_transitions"]),
        "recovery_gap": len(result["recovery_gap_events"]),
        "schema_boundary": len(result["schema_boundaries"]),
    }
    return _json_safe(result)
