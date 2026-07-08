# RiskRadar v0.7.2 → v0.7.3 마이그레이션

## 목적

v0.7.3은 새 시장 신호를 추가하지 않고, v0.6.2부터 저장해 온 **당시 실제 권위 판정**을 장기 보존하는 작은 원장을 추가합니다.

## 기준본

- 입력: `riskradar_v0.7.2_final.zip`
- 출력 버전: `0.7.3`
- v0.7.2의 쉬운 사용자 문구, 30년 금리 설명, 90일 기업 신용 변화 UI를 그대로 유지합니다.

## 새 파일

첫 정상 refresh에서 Dataset 또는 로컬 캐시 루트에 다음 파일이 생깁니다.

- `audit/decision_ledger.parquet`
- `audit/decision_ledger_status.json`

`audit/`는 `versions/` 밖에 있으므로 일반 cache version prune 대상이 아닙니다.

## 첫 refresh에서 하는 일

1. 새 `versions/<cache_version>/` 산출물을 저장합니다.
2. `data_status.json`으로 새 버전을 활성화합니다.
3. 현재 보존 중인 버전 가운데 `decision_snapshot.json`이 있고 `authoritative == true`인 것만 원장에 보충합니다.
4. 원장 보충이 성공한 뒤에만 오래된 cache version을 prune합니다.

### 하지 않는 일

- 현재 raw 데이터로 과거 날짜를 다시 계산하지 않습니다.
- v0.6.2 이전 기록을 추정 백필하지 않습니다.
- 권위 snapshot이 없는 버전을 가짜 역사로 만들지 않습니다.

## 중복과 충돌

고유키는 `(cache_version, section, key)`입니다. 같은 refresh를 재시도해도 동일 행은 한 번만 남습니다. 같은 고유키에 다른 payload가 들어오면 기존 원장을 덮지 않고 충돌로 처리합니다.

## 원장 실패 시 동작

원장 보충 실패가 핵심 시장 데이터 업데이트를 되돌리지는 않습니다. 대신 그 실행에서는 prune을 건너뜁니다. 아직 원장으로 옮기지 못한 권위 snapshot이 `versions/`에 남아 다음 refresh에서 다시 보충될 수 있게 하기 위해서입니다.

## 기존 설정

다음은 변경하지 않습니다.

- GitHub Actions workflow
- `FRED_API_KEY`
- `HF_TOKEN`
- `HF_DATASET_REPO_ID`
- Telegram secrets
- core·aux·신용 판정 규칙
- decision snapshot schema

## 배포 후 확인

GitHub Actions refresh를 1회 실행한 뒤 Dataset에서 다음을 확인합니다.

- `audit/decision_ledger.parquet` 존재
- `audit/decision_ledger_status.json`의 `raw_recomputation`이 `false`
- `pre_v0_6_2_backfill`이 `false`
- `authoritative_versions_total`이 1 이상
- 새 refresh를 다시 실행해도 이미 저장된 cache_version 행이 중복되지 않음
