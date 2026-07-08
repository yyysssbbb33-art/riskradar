from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from riskradar import cache_store as CS
from riskradar import decision_ledger as DL


def _snapshot(cache_version: str, *, authoritative: bool = True, hy_state: str = "confirmed") -> dict:
    return {
        "snapshot_format_version": 1,
        "authoritative": authoritative,
        "batch": {
            "cache_version": cache_version,
            "generated_at": "2026-07-08T07:30:00+09:00",
            "app_version": "0.7.3",
        },
        "schemas": {
            "core_state": "core-v1",
            "credit_episode": "credit-v1",
            "aux_direction": "aux-v1",
        },
        "core": {
            "VIX": {
                "observed_date": "2026-07-07",
                "source_status": "ok",
                "state_code": "normal",
                "state_label": "평소 수준",
                "latest_value": 15.0,
                "value_unit": "지수",
            }
        },
        "aux": {
            "BBBOAS": {
                "observed_date": "2026-07-07",
                "source_status": "ok",
                "direction": "상승",
                "latest_value": 120.0,
                "value_unit": "bp",
            }
        },
        "credit": {
            "nodes": {
                "HY": {
                    "observed_date": "2026-07-07",
                    "source_status": "ok",
                    "state": hy_state,
                    "state_label": "부담 상승 확인",
                    "latest_value": 350.0,
                    "value_unit": "bp",
                    "participant": True,
                }
            },
            "episode": {
                "episode_id": "credit-1",
                "state": "active",
                "state_label": "진행 중",
                "participants": ["HY"],
            },
            "lens": {
                "observed_date": "2026-07-07",
                "source_status": "ok",
                "state": "widening",
                "label": "등급 간 차이 확대",
                "latest_value_bp": 55.0,
            },
        },
    }


def _artifacts(snapshot: dict) -> dict:
    frame = pd.DataFrame({"x": [1]})
    return {
        "raw_fred": frame,
        "signal_matrix": frame,
        "synced_snapshot": frame,
        "chart_data": frame,
        "decision_snapshot": snapshot,
        "decision_diff": {"status": "cold_start"},
        "data_quality": {"code_version": "0.7.3"},
    }


def test_snapshot_to_ledger_rows_keeps_all_decision_sections_and_original_payload():
    rows = DL.snapshot_to_ledger_rows(_snapshot("2026-07-08T07-30-00KST"))
    assert set(rows["section"]) == {"core", "aux", "credit_node", "credit_episode", "credit_lens"}
    assert set(rows["cache_version"]) == {"2026-07-08T07-30-00KST"}
    assert rows[DL.LEDGER_KEY_COLUMNS].duplicated().sum() == 0

    hy = rows.loc[(rows["section"] == "credit_node") & (rows["key"] == "HY")].iloc[0]
    assert hy["decision_code"] == "confirmed"
    assert hy["decision_label"] == "부담 상승 확인"
    assert json.loads(hy["payload_json"])["participant"] is True
    lens = rows.loc[rows["section"] == "credit_lens"].iloc[0]
    assert lens["latest_value"] == 55.0
    assert lens["value_unit"] == "bp"
    assert len(hy["payload_sha256"]) == 64


def test_non_authoritative_snapshot_is_never_backfilled():
    rows = DL.snapshot_to_ledger_rows(
        _snapshot("2026-07-08T07-30-00KST", authoritative=False)
    )
    assert rows.empty


def test_ledger_merge_is_idempotent_and_rejects_same_key_with_changed_history():
    first = DL.snapshot_to_ledger_rows(_snapshot("2026-07-08T07-30-00KST"))
    merged = DL.merge_ledgers(first, first)
    assert len(merged) == len(first)

    changed = DL.snapshot_to_ledger_rows(
        _snapshot("2026-07-08T07-30-00KST", hy_state="normal")
    )
    with pytest.raises(RuntimeError, match="decision ledger conflict"):
        DL.merge_ledgers(first, changed)


def test_local_ledger_backfills_only_stored_authoritative_snapshots_and_is_idempotent(tmp_path):
    store = CS.LocalStore(tmp_path)
    old = tmp_path / "versions" / "2026-07-01T07-30-00KST"
    old.mkdir(parents=True)
    # v0.6.2 이전처럼 snapshot이 없는 버전은 건드리지 않는다.
    (old / "status.json").write_text("{}")

    non_auth = tmp_path / "versions" / "2026-07-02T07-30-00KST"
    non_auth.mkdir(parents=True)
    (non_auth / "decision_snapshot.json").write_text(
        json.dumps(_snapshot(non_auth.name, authoritative=False), ensure_ascii=False)
    )

    for cv in ("2026-07-03T07-30-00KST", "2026-07-04T07-30-00KST"):
        vdir = tmp_path / "versions" / cv
        vdir.mkdir(parents=True)
        (vdir / "decision_snapshot.json").write_text(
            json.dumps(_snapshot(cv), ensure_ascii=False)
        )

    result = store.sync_decision_ledger()
    ledger = store.load_decision_ledger()
    assert result["versions_added"] == ["2026-07-03T07-30-00KST", "2026-07-04T07-30-00KST"]
    assert DL.ledger_versions(ledger) == {"2026-07-03T07-30-00KST", "2026-07-04T07-30-00KST"}
    assert result["raw_recomputation"] is False
    assert result["pre_v0_6_2_backfill"] is False

    again = store.sync_decision_ledger()
    assert again["rows_added"] == 0
    assert len(store.load_decision_ledger()) == len(ledger)


def test_publish_syncs_ledger_before_prune_and_ledger_survives_version_pruning(tmp_path, monkeypatch):
    monkeypatch.setattr(CS, "KEEP_LAST_N", 1)
    monkeypatch.setattr(CS, "KEEP_MIN_DAYS", 0)
    monkeypatch.setattr(CS, "KEEP_MAX_N", 1)
    store = CS.LocalStore(tmp_path)

    old_cv = "2026-07-01T07-30-00KST"
    old = tmp_path / "versions" / old_cv
    old.mkdir(parents=True)
    (old / "decision_snapshot.json").write_text(
        json.dumps(_snapshot(old_cv), ensure_ascii=False)
    )

    new_cv = "2026-07-08T07-30-00KST"
    status = {"active_cache_version": new_cv, "status": "success"}
    result = store.publish(new_cv, _artifacts(_snapshot(new_cv)), status)

    assert result["status"] == "ok"
    assert not old.exists()  # 보존정책상 old version은 지워짐
    ledger = store.load_decision_ledger()
    assert DL.ledger_versions(ledger) == {old_cv, new_cv}  # 하지만 권위 판정은 먼저 원장에 보존됨
    assert (tmp_path / CS.DECISION_LEDGER_PATH).exists()


def test_publish_skips_prune_when_ledger_sync_fails_but_keeps_active_version(tmp_path, monkeypatch):
    store = CS.LocalStore(tmp_path)
    calls: list[str] = []

    def boom(*_args, **_kwargs):
        calls.append("sync")
        raise RuntimeError("ledger unavailable")

    def prune():
        calls.append("prune")

    monkeypatch.setattr(store, "sync_decision_ledger", boom)
    monkeypatch.setattr(store, "_prune", prune)

    cv = "2026-07-08T07-30-00KST"
    result = store.publish(cv, _artifacts(_snapshot(cv)), {"active_cache_version": cv, "status": "success"})

    assert result["status"] == "failed"
    assert result["prune_skipped"] is True
    assert calls == ["sync"]
    assert store.load_status()["active_cache_version"] == cv
    assert (tmp_path / "versions" / cv / "decision_snapshot.json").exists()


def test_current_cache_version_change_is_not_silently_overwritten(tmp_path):
    store = CS.LocalStore(tmp_path)
    cv = "2026-07-08T07-30-00KST"
    vdir = tmp_path / "versions" / cv
    vdir.mkdir(parents=True)
    (vdir / "decision_snapshot.json").write_text(json.dumps(_snapshot(cv), ensure_ascii=False))
    store.sync_decision_ledger()

    (vdir / "decision_snapshot.json").write_text(
        json.dumps(_snapshot(cv, hy_state="normal"), ensure_ascii=False)
    )
    # 과거 버전 전체를 매번 재검사하지는 않지만, 현재 publish 버전은 다시 대조한다.
    with pytest.raises(RuntimeError, match="decision ledger conflict"):
        store.sync_decision_ledger(current_cache_version=cv)

class _FakeHfApi:
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
        self.deleted: list[str] = []
        self.commits: list[str] = []

    def list_repo_files(self, _repo_id, repo_type="dataset"):
        assert repo_type == "dataset"
        return sorted(self.files)

    @staticmethod
    def _payload_bytes(payload):
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, bytearray):
            return bytes(payload)
        if hasattr(payload, "read"):
            pos = payload.tell() if hasattr(payload, "tell") else None
            data = payload.read()
            if pos is not None and hasattr(payload, "seek"):
                payload.seek(pos)
            return data
        return bytes(payload)

    def create_commit(self, _repo_id, *, repo_type, operations, commit_message):
        assert repo_type == "dataset"
        self.commits.append(commit_message)
        for op in operations:
            self.files[op.path_in_repo] = self._payload_bytes(op.path_or_fileobj)

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message):
        assert repo_id == "owner/repo"
        assert repo_type == "dataset"
        self.commits.append(commit_message)
        self.files[path_in_repo] = self._payload_bytes(path_or_fileobj)

    def delete_folder(self, path, _repo_id, *, repo_type, commit_message):
        assert repo_type == "dataset"
        self.deleted.append(path)
        self.commits.append(commit_message)
        prefix = path.rstrip("/") + "/"
        for key in list(self.files):
            if key.startswith(prefix):
                del self.files[key]


def test_hf_dataset_sync_writes_permanent_ledger_and_status_in_one_commit(tmp_path, monkeypatch):
    import huggingface_hub
    from huggingface_hub.utils import EntryNotFoundError

    cv1 = "2026-07-07T07-30-00KST"
    cv2 = "2026-07-08T07-30-00KST"
    api = _FakeHfApi({
        f"versions/{cv1}/decision_snapshot.json": json.dumps(_snapshot(cv1), ensure_ascii=False).encode(),
        f"versions/{cv2}/decision_snapshot.json": json.dumps(_snapshot(cv2), ensure_ascii=False).encode(),
    })

    def fake_download(_repo_id, filename, *, repo_type, token):
        assert repo_type == "dataset"
        assert token == "token"
        if filename not in api.files:
            raise EntryNotFoundError(filename)
        fp = tmp_path / filename.replace("/", "__")
        fp.write_bytes(api.files[filename])
        return str(fp)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    store = object.__new__(CS.HfDatasetStore)
    store.repo_id = "owner/repo"
    store.token = "token"
    store.api = api

    result = store.sync_decision_ledger(current_cache_version=cv2)
    assert result["rows_added"] > 0
    assert CS.DECISION_LEDGER_PATH in api.files
    assert CS.DECISION_LEDGER_STATUS_PATH in api.files
    assert api.commits[-1].startswith("decision ledger")

    ledger_fp = tmp_path / "ledger.parquet"
    ledger_fp.write_bytes(api.files[CS.DECISION_LEDGER_PATH])
    ledger = pd.read_parquet(ledger_fp)
    assert DL.ledger_versions(ledger) == {cv1, cv2}

    # 같은 원장을 다시 동기화해도 새 커밋과 중복 행이 생기지 않는다.
    commits_before = len(api.commits)
    result2 = store.sync_decision_ledger(current_cache_version=cv2)
    assert result2["rows_added"] == 0
    assert len(api.commits) == commits_before


def test_hf_publish_preserves_old_authoritative_snapshot_before_remote_prune(tmp_path, monkeypatch):
    import huggingface_hub
    from huggingface_hub.utils import EntryNotFoundError

    monkeypatch.setattr(CS, "KEEP_LAST_N", 1)
    monkeypatch.setattr(CS, "KEEP_MIN_DAYS", 0)
    monkeypatch.setattr(CS, "KEEP_MAX_N", 1)

    old_cv = "2026-07-01T07-30-00KST"
    new_cv = "2026-07-08T07-30-00KST"
    api = _FakeHfApi({
        f"versions/{old_cv}/decision_snapshot.json": json.dumps(_snapshot(old_cv), ensure_ascii=False).encode(),
    })

    def fake_download(_repo_id, filename, *, repo_type, token):
        assert repo_type == "dataset"
        if filename not in api.files:
            raise EntryNotFoundError(filename)
        fp = tmp_path / filename.replace("/", "__")
        fp.write_bytes(api.files[filename])
        return str(fp)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    store = object.__new__(CS.HfDatasetStore)
    store.repo_id = "owner/repo"
    store.token = "token"
    store.api = api

    result = store.publish(
        new_cv,
        _artifacts(_snapshot(new_cv)),
        {"active_cache_version": new_cv, "status": "success"},
    )
    assert result["status"] == "ok"
    assert f"versions/{old_cv}/decision_snapshot.json" not in api.files

    fp = tmp_path / "remote-ledger.parquet"
    fp.write_bytes(api.files[CS.DECISION_LEDGER_PATH])
    ledger = pd.read_parquet(fp)
    assert DL.ledger_versions(ledger) == {old_cv, new_cv}
    assert any(msg == f"prune {old_cv}" for msg in api.commits)


def test_v073_ui_reads_v072_cache_without_new_per_version_artifacts():
    from riskradar.ui import _is_compatible_data_code_version

    assert _is_compatible_data_code_version("0.7.2", "0.7.3") is True
    assert _is_compatible_data_code_version("0.7.1", "0.7.3") is True
    assert _is_compatible_data_code_version("0.7.0", "0.7.3") is True


def test_merge_rejects_duplicate_keys_inside_existing_ledger():
    rows = DL.snapshot_to_ledger_rows(_snapshot("2026-07-08T07-30-00KST"))
    broken = pd.concat([rows, rows.iloc[[0]]], ignore_index=True)
    with pytest.raises(RuntimeError, match="duplicate decision ledger key"):
        DL.merge_ledgers(broken, DL.empty_ledger())
