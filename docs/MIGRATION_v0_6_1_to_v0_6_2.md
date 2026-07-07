# RiskRadar v0.6.1 → v0.6.2

v0.6.2는 **변화 중심 첫 화면을 만들기 전의 판정 기록 기반 버전**입니다. UI 구조와 시장 판정 규칙은 거의 그대로 두고, 이후 `최근 갱신에서 달라진 것` 기능이 코드 변경이나 데이터 장애에 속지 않도록 권위 있는 스냅샷과 diff 토대를 추가합니다.

## 핵심 변화

### 1. 권위 있는 `decision_snapshot.json`

각 성공 배치가 실제 사용한 다음 판정을 버전 폴더에 저장합니다.

- 핵심 6개 상태와 실제 관측일
- HY / BBB / A / CP 상태·참여·잔존
- 현재 신용 에피소드 상태와 참여 범위
- HY-BBB 렌즈
- 확인지표 방향·실제 관측일·fetch 상태
- core / credit / aux 데이터 상태

`지난 30일 흐름`의 현재 규칙 기반 재구성본은 이 diff에 사용하지 않습니다.

### 2. 백필하지 않음

v0.6.1 이전 캐시에는 `decision_snapshot.json`이 없습니다. 이를 현재 코드로 재생성하면 과거 판정을 현재 규칙으로 다시 쓰는 오염이 생기므로 백필하지 않습니다.

따라서:

- v0.6.2 첫 성공 refresh → `cold_start`
- 다음 성공 refresh부터 → 직전 권위 있는 snapshot과 비교

### 3. 포맷과 판정 규칙 버전 분리

- `snapshot_format_version`
- `core_state_schema`
- `credit_episode_schema`
- `aux_direction_schema`

앱 버전이 바뀌어도 판정 의미가 같으면 diff는 이어집니다. 반대로 임계값·지속성·상태 의미가 바뀌면 해당 영역 schema를 올리고 그 경계의 비교만 보류합니다.

### 4. transition 분류

- 새 관측에 따른 시장 판정 변화
- 관측 타임라인 경과에 따른 에피소드 활성→휴면/종료
- 데이터 수집 실패·stale·복구
- 판정 schema 경계

수집 공백 뒤 복구된 값이 공백 전 판정과 달라졌다면 `복구 + 공백 전후 변화`로 별도 기록합니다. 공백 중 정확한 변화 시점은 주장하지 않습니다.

### 5. 실제 관측일 전진 검사

배치 시간이 바뀌었더라도 지표의 실제 관측일이 그대로면 판정 차이를 시장 변화로 세지 않습니다. carry-forward도 이전 실제 관측일을 그대로 유지합니다.

### 6. 캐시 보존 정책

기존 고정 45개 버전 대신 기본값으로:

- 최근 90일 우선 보존
- 실행이 드물어도 최소 45개 보존
- 수동 refresh 폭주 시 최대 180개 안전 상한

을 함께 적용합니다. 환경변수로 조정할 수 있습니다.

- `CACHE_KEEP_MIN_DAYS`
- `CACHE_KEEP_LAST_N`
- `CACHE_KEEP_MAX_N`

## 새 파일

- `src/riskradar/decision_snapshot.py`
- `tests/test_v0_6_2_decision_snapshots.py`

## 새 캐시 파일

- `versions/<cache_version>/decision_snapshot.json`
- `versions/<cache_version>/decision_diff.json`

옛 캐시에 파일이 없어도 UI는 정상 동작합니다.

## 배포

workflow는 변경하지 않습니다. 코드 업로드 후 새 `refresh`를 한 번 실행하면 첫 권위 있는 snapshot이 생성됩니다. 그 첫 배치는 비교 대상이 없어 `cold_start`가 정상이며, 다음 성공 배치부터 diff가 생깁니다.
