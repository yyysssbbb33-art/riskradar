"""캐시 저장/조회.

쓰기(refresh, GitHub Actions에서):
  1) versions/<cache_version>/ 에 산출물 업로드
  2) 검증
  3) data_status.json(포인터) 마지막에 갱신
읽기(HF Space UI에서):
  data_status.json -> active_cache_version -> 해당 버전 산출물 로드

backend: "local" | "hf_dataset"
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

ARTIFACT_PARQUETS = ["raw_fred", "signal_matrix", "synced_snapshot", "chart_data"]
KEEP_LAST_N = int(os.environ.get("CACHE_KEEP_LAST_N", "14"))


# ---------------------------------------------------------------- local -----

class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "versions").mkdir(parents=True, exist_ok=True)

    def publish(self, cache_version: str, artifacts: dict, status: dict) -> None:
        vdir = self.root / "versions" / cache_version
        vdir.mkdir(parents=True, exist_ok=True)
        for name in ARTIFACT_PARQUETS:
            artifacts[name].to_parquet(vdir / f"{name}.parquet", index=False)
        (vdir / "data_quality.json").write_text(
            json.dumps(artifacts["data_quality"], ensure_ascii=False, indent=2))
        _verify(vdir)
        # 포인터 마지막
        (self.root / "data_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2))
        self._prune()

    def load(self) -> tuple[dict, dict]:
        status = json.loads((self.root / "data_status.json").read_text())
        vdir = self.root / "versions" / status["active_cache_version"]
        arts = {n: pd.read_parquet(vdir / f"{n}.parquet") for n in ARTIFACT_PARQUETS}
        return status, arts

    def last_good_raw(self) -> pd.DataFrame | None:
        p = self.root / "data_status.json"
        if not p.exists():
            return None
        status = json.loads(p.read_text())
        vdir = self.root / "versions" / status["active_cache_version"]
        f = vdir / "raw_fred.parquet"
        return pd.read_parquet(f) if f.exists() else None

    def _prune(self):
        vs = sorted((self.root / "versions").iterdir())
        for old in vs[:-KEEP_LAST_N]:
            shutil.rmtree(old, ignore_errors=True)


# ------------------------------------------------------------- hf dataset ---

class HfDatasetStore:
    """huggingface_hub 기반. 로컬과 동일한 레이아웃을 원격 repo에 유지한다."""

    def __init__(self, repo_id: str, token: str):
        from huggingface_hub import HfApi
        self.repo_id = repo_id
        self.api = HfApi(token=token)
        self.token = token

    def publish(self, cache_version: str, artifacts: dict, status: dict) -> None:
        from huggingface_hub import CommitOperationAdd
        ops = []
        for name in ARTIFACT_PARQUETS:
            buf = io.BytesIO()
            artifacts[name].to_parquet(buf, index=False)
            ops.append(CommitOperationAdd(
                f"versions/{cache_version}/{name}.parquet", buf.getvalue()))
        ops.append(CommitOperationAdd(
            f"versions/{cache_version}/data_quality.json",
            json.dumps(artifacts["data_quality"], ensure_ascii=False).encode()))
        # 1) 산출물 커밋
        self.api.create_commit(self.repo_id, repo_type="dataset", operations=ops,
                               commit_message=f"artifacts {cache_version}")
        # 2) 포인터 마지막 커밋 (원자적 활성화)
        self.api.upload_file(
            path_or_fileobj=json.dumps(status, ensure_ascii=False, indent=2).encode(),
            path_in_repo="data_status.json", repo_id=self.repo_id,
            repo_type="dataset", commit_message=f"activate {cache_version}")
        self._prune()

    def load(self) -> tuple[dict, dict]:
        from huggingface_hub import hf_hub_download
        sp = hf_hub_download(self.repo_id, "data_status.json",
                             repo_type="dataset", token=self.token)
        status = json.loads(Path(sp).read_text())
        cv = status["active_cache_version"]
        arts = {}
        for n in ARTIFACT_PARQUETS:
            fp = hf_hub_download(self.repo_id, f"versions/{cv}/{n}.parquet",
                                 repo_type="dataset", token=self.token)
            arts[n] = pd.read_parquet(fp)
        return status, arts

    def last_good_raw(self) -> pd.DataFrame | None:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError
        try:
            sp = hf_hub_download(self.repo_id, "data_status.json",
                                 repo_type="dataset", token=self.token)
            cv = json.loads(Path(sp).read_text())["active_cache_version"]
            fp = hf_hub_download(self.repo_id, f"versions/{cv}/raw_fred.parquet",
                                 repo_type="dataset", token=self.token)
            return pd.read_parquet(fp)
        except (EntryNotFoundError, Exception):  # noqa: BLE001
            return None

    def _prune(self):
        try:
            files = self.api.list_repo_files(self.repo_id, repo_type="dataset")
            versions = sorted({f.split("/")[1] for f in files
                               if f.startswith("versions/")})
            for old in versions[:-KEEP_LAST_N]:
                self.api.delete_folder(f"versions/{old}", self.repo_id,
                                       repo_type="dataset",
                                       commit_message=f"prune {old}")
        except Exception as e:  # noqa: BLE001 - prune 실패는 치명적 아님
            log.warning("prune failed: %s", e)


def _verify(vdir: Path) -> None:
    for name in ARTIFACT_PARQUETS:
        f = vdir / f"{name}.parquet"
        if not f.exists() or f.stat().st_size == 0:
            raise RuntimeError(f"artifact missing/empty: {f}")
    if not (vdir / "data_quality.json").exists():
        raise RuntimeError("data_quality.json missing")


def get_store():
    """환경변수로 backend 결정."""
    backend = os.environ.get("CACHE_BACKEND", "local")
    if backend == "hf_dataset":
        return HfDatasetStore(os.environ["HF_DATASET_REPO_ID"],
                              os.environ["HF_TOKEN"])
    return LocalStore(os.environ.get("CACHE_LOCAL_ROOT", "./_cache"))
