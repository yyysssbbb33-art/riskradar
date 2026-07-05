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
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

ARTIFACT_PARQUETS = ["raw_fred", "signal_matrix", "synced_snapshot", "chart_data"]
# 하위호환: 옛 캐시 버전에는 없을 수 있는 옵셔널 아티팩트.
# _verify/필수 load 대상이 아니며, 없으면 빈 DataFrame으로 관용 처리한다.
OPTIONAL_ARTIFACTS = ["aux_signal_matrix"]
# 최근 30일 변화 탭을 안정적으로 보여주려면 14개 보관은 부족하다.
# 영업일 기준 30일 + 수동 실행 여유분을 고려해 기본 45개 버전을 보관한다.
KEEP_LAST_N = int(os.environ.get("CACHE_KEEP_LAST_N", "45"))


# ---------------------------------------------------------------- common ----

def _version_dt(cache_version: str) -> datetime:
    """YYYY-MM-DDTHH-MM-SSKST 형식의 cache_version을 naive datetime으로 변환."""
    return datetime.strptime(cache_version, "%Y-%m-%dT%H-%M-%SKST")


def _versions_from_paths(paths: list[str]) -> list[str]:
    versions = {
        p.split("/")[1]
        for p in paths
        if p.startswith("versions/") and len(p.split("/")) >= 3
    }
    return sorted(versions, key=_safe_version_sort)


def _safe_version_sort(cache_version: str):
    try:
        return _version_dt(cache_version)
    except ValueError:
        return datetime.min


def _history_from_versions(loader, versions: list[str], days: int = 30) -> pd.DataFrame:
    """여러 version의 signal_matrix를 합쳐 UI용 일별 스냅샷 히스토리를 만든다."""
    if not versions:
        return pd.DataFrame()

    cutoff = datetime.now() - timedelta(days=days)
    recent_versions = []
    for v in versions:
        try:
            if _version_dt(v) >= cutoff:
                recent_versions.append(v)
        except ValueError:
            continue

    rows = []
    for v in recent_versions:
        try:
            matrix = loader(v, "signal_matrix")
        except Exception as e:  # noqa: BLE001 - 일부 과거 버전 손상은 전체 UI를 깨지 않음
            log.warning("skip history version %s: %s", v, e)
            continue
        if matrix.empty:
            continue
        ts = _version_dt(v)
        m = matrix.copy()
        m.insert(0, "cache_version", v)
        m.insert(1, "snapshot_at_kst", ts.strftime("%Y-%m-%d %H:%M:%S"))
        m.insert(2, "snapshot_date", ts.strftime("%Y-%m-%d"))
        rows.append(m)

    if not rows:
        return pd.DataFrame()
    hist = pd.concat(rows, ignore_index=True)
    # 같은 KST 날짜에 자동·수동 실행이 여러 번 있었으면 원본 버전은 모두 보존하되
    # UI 히스토리에는 그날의 마지막 성공 스냅샷 하나만 사용한다.
    latest_by_date = (
        hist[["snapshot_date", "snapshot_at_kst", "cache_version"]]
        .drop_duplicates()
        .sort_values("snapshot_at_kst")
        .groupby("snapshot_date", as_index=False)
        .tail(1)
    )
    keep_versions = set(latest_by_date["cache_version"].tolist())
    hist = hist.loc[hist["cache_version"].isin(keep_versions)].copy()
    return hist.sort_values(["snapshot_at_kst", "key"]).reset_index(drop=True)


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
        for name in OPTIONAL_ARTIFACTS:
            if artifacts.get(name) is not None:
                artifacts[name].to_parquet(vdir / f"{name}.parquet", index=False)
        (vdir / "data_quality.json").write_text(
            json.dumps(artifacts["data_quality"], ensure_ascii=False, indent=2))
        (vdir / "status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2))
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

    def load_artifact(self, cache_version: str, name: str) -> pd.DataFrame:
        if name not in ARTIFACT_PARQUETS and name not in OPTIONAL_ARTIFACTS:
            raise ValueError(f"unknown parquet artifact: {name}")
        fp = self.root / "versions" / cache_version / f"{name}.parquet"
        if name in OPTIONAL_ARTIFACTS and not fp.exists():
            return pd.DataFrame()
        return pd.read_parquet(fp)

    def list_versions(self) -> list[str]:
        vroot = self.root / "versions"
        if not vroot.exists():
            return []
        return sorted([p.name for p in vroot.iterdir() if p.is_dir()], key=_safe_version_sort)

    def load_history(self, days: int = 30) -> pd.DataFrame:
        return _history_from_versions(self.load_artifact, self.list_versions(), days=days)

    def load_data_quality(self, cache_version: str | None = None) -> dict:
        if cache_version is None:
            p = self.root / "data_status.json"
            if not p.exists():
                return {}
            cache_version = json.loads(p.read_text())["active_cache_version"]
        fp = self.root / "versions" / cache_version / "data_quality.json"
        return json.loads(fp.read_text()) if fp.exists() else {}

    def last_good_raw(self) -> pd.DataFrame | None:
        p = self.root / "data_status.json"
        if not p.exists():
            return None
        status = json.loads(p.read_text())
        vdir = self.root / "versions" / status["active_cache_version"]
        f = vdir / "raw_fred.parquet"
        return pd.read_parquet(f) if f.exists() else None

    def last_good_aux(self) -> pd.DataFrame | None:
        p = self.root / "data_status.json"
        if not p.exists():
            return None
        status = json.loads(p.read_text())
        vdir = self.root / "versions" / status["active_cache_version"]
        f = vdir / "aux_signal_matrix.parquet"
        return pd.read_parquet(f) if f.exists() else None

    def _prune(self):
        vs = sorted((self.root / "versions").iterdir())
        for old in vs[:-KEEP_LAST_N]:
            shutil.rmtree(old, ignore_errors=True)


# ------------------------------------------------------------- hf dataset ---

class HfDatasetStore:
    """huggingface_hub 기반. 로컬과 동일한 레이아웃을 원격 repo에 유지한다."""

    def __init__(self, repo_id: str, token: str | None):
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
        for name in OPTIONAL_ARTIFACTS:
            if artifacts.get(name) is not None:
                buf = io.BytesIO()
                artifacts[name].to_parquet(buf, index=False)
                ops.append(CommitOperationAdd(
                    f"versions/{cache_version}/{name}.parquet", buf.getvalue()))
        ops.append(CommitOperationAdd(
            f"versions/{cache_version}/data_quality.json",
            json.dumps(artifacts["data_quality"], ensure_ascii=False).encode()))
        ops.append(CommitOperationAdd(
            f"versions/{cache_version}/status.json",
            json.dumps(status, ensure_ascii=False, indent=2).encode()))
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

    def load_artifact(self, cache_version: str, name: str) -> pd.DataFrame:
        if name not in ARTIFACT_PARQUETS and name not in OPTIONAL_ARTIFACTS:
            raise ValueError(f"unknown parquet artifact: {name}")
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError
        try:
            fp = hf_hub_download(self.repo_id, f"versions/{cache_version}/{name}.parquet",
                                 repo_type="dataset", token=self.token)
        except EntryNotFoundError:
            if name in OPTIONAL_ARTIFACTS:
                return pd.DataFrame()
            raise
        return pd.read_parquet(fp)

    def list_versions(self) -> list[str]:
        return _versions_from_paths(self.api.list_repo_files(self.repo_id, repo_type="dataset"))

    def load_history(self, days: int = 30) -> pd.DataFrame:
        return _history_from_versions(self.load_artifact, self.list_versions(), days=days)

    def load_data_quality(self, cache_version: str | None = None) -> dict:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError
        try:
            if cache_version is None:
                sp = hf_hub_download(self.repo_id, "data_status.json",
                                     repo_type="dataset", token=self.token)
                cache_version = json.loads(Path(sp).read_text())["active_cache_version"]
            fp = hf_hub_download(self.repo_id, f"versions/{cache_version}/data_quality.json",
                                 repo_type="dataset", token=self.token)
            return json.loads(Path(fp).read_text())
        except (EntryNotFoundError, Exception):  # noqa: BLE001
            return {}

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

    def last_good_aux(self) -> pd.DataFrame | None:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError
        try:
            sp = hf_hub_download(self.repo_id, "data_status.json",
                                 repo_type="dataset", token=self.token)
            cv = json.loads(Path(sp).read_text())["active_cache_version"]
            fp = hf_hub_download(self.repo_id, f"versions/{cv}/aux_signal_matrix.parquet",
                                 repo_type="dataset", token=self.token)
            return pd.read_parquet(fp)
        except (EntryNotFoundError, Exception):  # noqa: BLE001
            return None

    def _prune(self):
        try:
            files = self.api.list_repo_files(self.repo_id, repo_type="dataset")
            versions = _versions_from_paths(files)
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
        # 공개 Dataset을 읽기만 하는 Space는 HF_TOKEN 없이 동작한다.
        return HfDatasetStore(os.environ["HF_DATASET_REPO_ID"],
                              os.environ.get("HF_TOKEN"))
    return LocalStore(os.environ.get("CACHE_LOCAL_ROOT", "./_cache"))
