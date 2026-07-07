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
OPTIONAL_ARTIFACTS = ["aux_signal_matrix", "aux_raw", "credit_episode_nodes", "credit_episodes"]
# v0.6.2부터 시작하는 권위 있는 판정 기록. 옛 버전은 백필하지 않는다.
OPTIONAL_JSON_ARTIFACTS = ["decision_snapshot", "decision_diff"]
# 최근 흐름·diff 감사를 위해 날짜와 개수를 함께 본다.
# - 최근 KEEP_MIN_DAYS 안의 버전은 우선 보존
# - 실행이 드물어도 최소 KEEP_LAST_N개는 보존
# - 수동 refresh 폭주로 저장소가 무한히 커지지 않도록 KEEP_MAX_N 상한 적용
KEEP_LAST_N = int(os.environ.get("CACHE_KEEP_LAST_N", "45"))
KEEP_MIN_DAYS = int(os.environ.get("CACHE_KEEP_MIN_DAYS", "90"))
KEEP_MAX_N = int(os.environ.get("CACHE_KEEP_MAX_N", "180"))


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






def _versions_to_prune(versions: list[str]) -> list[str]:
    """날짜+개수 이중 기준으로 삭제할 cache_version을 반환한다."""
    ordered = sorted(set(versions), key=_safe_version_sort)
    valid = [v for v in ordered if _safe_version_sort(v) != datetime.min]
    if not valid:
        return []
    latest_dt = _version_dt(valid[-1])
    cutoff = latest_dt - timedelta(days=max(0, KEEP_MIN_DAYS))
    keep = {v for v in valid if _version_dt(v) >= cutoff}
    keep.update(valid[-max(1, KEEP_LAST_N):])
    # 안전 상한은 pathological refresh 폭주 방지용이다. 초과 시 가장 최근 버전을 우선한다.
    if KEEP_MAX_N > 0 and len(keep) > KEEP_MAX_N:
        keep = set(valid[-KEEP_MAX_N:])
    return [v for v in valid if v not in keep]

def _actual_success_aux_row(df: pd.DataFrame | None, key: str) -> pd.DataFrame:
    """보조지표 캐시에서 '실제 정상 수집' 행만 반환한다.

    carried_forward 행을 다시 성공값으로 취급하면 실패가 연쇄 복사될 수 있으므로
    ``fetch_status == ok``인 행만 복구 원천으로 쓴다. 오래된 초기 캐시에
    fetch_status 컬럼이 없으면 ``ok == True``인 행만 허용한다.
    """
    if df is None or df.empty or "key" not in df.columns:
        return pd.DataFrame()
    hit = df.loc[df["key"].astype(str) == str(key)].copy()
    if hit.empty:
        return hit
    if "fetch_status" in hit.columns:
        hit = hit.loc[hit["fetch_status"].astype(str) == "ok"]
    elif "ok" in hit.columns:
        hit = hit.loc[hit["ok"].astype(bool)]
    if "latest_value" in hit.columns:
        hit = hit.loc[pd.to_numeric(hit["latest_value"], errors="coerce").notna()]
    return hit

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
        for name in OPTIONAL_JSON_ARTIFACTS:
            if artifacts.get(name) is not None:
                (vdir / f"{name}.json").write_text(
                    json.dumps(artifacts[name], ensure_ascii=False, indent=2))
        (vdir / "data_quality.json").write_text(
            json.dumps(artifacts["data_quality"], ensure_ascii=False, indent=2))
        (vdir / "status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2))
        _verify(vdir)
        # 포인터 마지막
        (self.root / "data_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2))
        self._prune()

    def update_status(self, cache_version: str, status: dict) -> None:
        """산출물은 건드리지 않고 status와 활성 포인터만 갱신한다."""
        vdir = self.root / "versions" / cache_version
        (vdir / "status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2))
        (self.root / "data_status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2))

    def load_status(self) -> dict:
        return json.loads((self.root / "data_status.json").read_text())

    def load(self) -> tuple[dict, dict]:
        status = self.load_status()
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

    def load_json_artifact(self, cache_version: str, name: str) -> dict:
        if name not in OPTIONAL_JSON_ARTIFACTS:
            raise ValueError(f"unknown json artifact: {name}")
        fp = self.root / "versions" / cache_version / f"{name}.json"
        return json.loads(fp.read_text()) if fp.exists() else {}

    def find_previous_decision_snapshot(self, before_version: str | None = None) -> dict | None:
        """이전 권위 있는 decision_snapshot만 찾는다. 옛 캐시 재구성/백필은 하지 않는다."""
        for version in reversed(self.list_versions()):
            if before_version is not None and _safe_version_sort(version) >= _safe_version_sort(before_version):
                continue
            fp = self.root / "versions" / version / "decision_snapshot.json"
            if not fp.exists():
                continue
            snap = json.loads(fp.read_text())
            if snap.get("authoritative") is True:
                return snap
        return None

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

    def find_last_good_aux(self, key: str) -> pd.DataFrame | None:
        """과거 버전을 최신→과거 순서로 훑어 마지막 실제 성공 행을 찾는다."""
        for version in reversed(self.list_versions()):
            try:
                df = self.load_artifact(version, "aux_signal_matrix")
            except Exception as e:  # noqa: BLE001
                log.warning("skip aux history version %s for %s: %s", version, key, e)
                continue
            hit = _actual_success_aux_row(df, key)
            if not hit.empty:
                return hit.tail(1).reset_index(drop=True)
        return None

    def find_last_good_aux_raw(self, key: str) -> pd.DataFrame | None:
        """최신→과거 버전에서 해당 확인지표의 마지막 저장 원자료를 찾는다."""
        for version in reversed(self.list_versions()):
            try:
                df = self.load_artifact(version, "aux_raw")
            except Exception as e:  # noqa: BLE001
                log.warning("skip aux raw version %s for %s: %s", version, key, e)
                continue
            if df is None or df.empty or "key" not in df.columns:
                continue
            hit = df.loc[df["key"].astype(str) == str(key)].copy()
            if not hit.empty:
                return hit.sort_values("date").reset_index(drop=True)
        return None

    def _prune(self):
        versions = self.list_versions()
        for old in _versions_to_prune(versions):
            shutil.rmtree(self.root / "versions" / old, ignore_errors=True)


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
        for name in OPTIONAL_JSON_ARTIFACTS:
            if artifacts.get(name) is not None:
                ops.append(CommitOperationAdd(
                    f"versions/{cache_version}/{name}.json",
                    json.dumps(artifacts[name], ensure_ascii=False, indent=2).encode()))
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

    def update_status(self, cache_version: str, status: dict) -> None:
        """Telegram 결과처럼 작은 상태 변화만 갱신한다. parquet은 재업로드하지 않는다."""
        payload = json.dumps(status, ensure_ascii=False, indent=2).encode()
        self.api.upload_file(
            path_or_fileobj=payload,
            path_in_repo=f"versions/{cache_version}/status.json",
            repo_id=self.repo_id, repo_type="dataset",
            commit_message=f"status {cache_version}")
        # 활성 포인터는 마지막에 갱신한다.
        self.api.upload_file(
            path_or_fileobj=payload, path_in_repo="data_status.json",
            repo_id=self.repo_id, repo_type="dataset",
            commit_message=f"status activate {cache_version}")

    def load_status(self) -> dict:
        from huggingface_hub import hf_hub_download
        sp = hf_hub_download(self.repo_id, "data_status.json",
                             repo_type="dataset", token=self.token)
        return json.loads(Path(sp).read_text())

    def load(self) -> tuple[dict, dict]:
        from huggingface_hub import hf_hub_download
        status = self.load_status()
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

    def load_json_artifact(self, cache_version: str, name: str) -> dict:
        if name not in OPTIONAL_JSON_ARTIFACTS:
            raise ValueError(f"unknown json artifact: {name}")
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError
        try:
            fp = hf_hub_download(
                self.repo_id, f"versions/{cache_version}/{name}.json",
                repo_type="dataset", token=self.token,
            )
        except EntryNotFoundError:
            return {}
        return json.loads(Path(fp).read_text())

    def find_previous_decision_snapshot(self, before_version: str | None = None) -> dict | None:
        """이전 권위 있는 decision_snapshot만 찾는다. 옛 캐시는 백필하지 않는다."""
        try:
            files = self.api.list_repo_files(self.repo_id, repo_type="dataset")
        except Exception as e:  # noqa: BLE001
            log.warning("decision snapshot file listing failed: %s", e)
            return None
        versions = sorted({
            p.split("/")[1]
            for p in files
            if p.startswith("versions/") and p.endswith("/decision_snapshot.json") and len(p.split("/")) >= 3
        }, key=_safe_version_sort)
        for version in reversed(versions):
            if before_version is not None and _safe_version_sort(version) >= _safe_version_sort(before_version):
                continue
            try:
                snap = self.load_json_artifact(version, "decision_snapshot")
            except Exception as e:  # noqa: BLE001
                log.warning("skip decision snapshot version %s: %s", version, e)
                continue
            if snap.get("authoritative") is True:
                return snap
        return None

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
        except EntryNotFoundError:
            # v0.4 이전 캐시에는 파일이 없을 수 있다. 그 경우만 구버전으로 관용 처리한다.
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
        except EntryNotFoundError:
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("last_good_raw read failed: %s", e)
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
        except EntryNotFoundError:
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("last_good_aux read failed: %s", e)
            return None

    def find_last_good_aux(self, key: str) -> pd.DataFrame | None:
        """과거 Dataset 버전을 최신→과거 순서로 훑어 마지막 실제 성공 행을 찾는다."""
        for version in reversed(self.list_versions()):
            try:
                df = self.load_artifact(version, "aux_signal_matrix")
            except Exception as e:  # noqa: BLE001
                log.warning("skip aux history version %s for %s: %s", version, key, e)
                continue
            hit = _actual_success_aux_row(df, key)
            if not hit.empty:
                return hit.tail(1).reset_index(drop=True)
        return None

    def find_last_good_aux_raw(self, key: str) -> pd.DataFrame | None:
        """최신→과거 버전에서 해당 확인지표의 마지막 저장 원자료를 찾는다."""
        for version in reversed(self.list_versions()):
            try:
                df = self.load_artifact(version, "aux_raw")
            except Exception as e:  # noqa: BLE001
                log.warning("skip aux raw version %s for %s: %s", version, key, e)
                continue
            if df is None or df.empty or "key" not in df.columns:
                continue
            hit = df.loc[df["key"].astype(str) == str(key)].copy()
            if not hit.empty:
                return hit.sort_values("date").reset_index(drop=True)
        return None

    def _prune(self):
        try:
            files = self.api.list_repo_files(self.repo_id, repo_type="dataset")
            versions = _versions_from_paths(files)
            for old in _versions_to_prune(versions):
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
