# RiskRadar v0.4.3 → v0.4.4

## 핵심 변경

v0.4.3에는 세 요소가 따로 존재했다.

1. 현재 지표의 한줄 해석
2. 고정 8칸 상세 설명
3. 특정 조합이 탐지됐을 때의 현재 확인결과

하지만 사용자가 실제로 필요한 연결 흐름인 아래가 충분하지 않았다.

```text
지금 상태는 무엇인가
→ 다음에 어떤 지표를 봐야 하나
→ 왜 그 지표를 보나
→ 현재 그 지표는 어떤 결과인가
→ 상승/하락/보합이면 각각 해석이 어떻게 달라지나
```

v0.4.4는 이 연결층을 추가한다.

## 1. 지표별 상태 후속 가이드

신규 모듈:

- `src/riskradar/state_guidance.py`

핵심 6개 지표마다 현재 상태를 기준으로 다음 확인 순서를 제공한다.

예: 30년물 금리

1. 10년 실질금리
2. 10년 기대인플레이션
3. 10년 Term Premium
4. 2년물 금리

각 확인지표에는 다음을 모두 표시한다.

- 왜 보는가
- 현재 결과
- 현재 결과에 대한 해석
- 상승할 경우
- 하락할 경우
- 보합일 경우

특정 조합이 탐지되지 않아도 이 가이드는 항상 표시된다.

## 2. 오늘의 해석 분기 강화

기존에는 조합의 확인지표에 현재 결과만 표시했다.

v0.4.4에서는 현재 결과 아래에 `결과가 달라지면`을 추가해 다른 방향의 해석도 보여준다.

예:

```text
10년 기대인플레이션
현재: 상승
→ 인플레이션 보상 요인 설명을 더 지지

결과가 달라지면
- 하락: 인플레이션 설명 약화
- 보합: 인플레이션 하나로 설명할 근거 약함
```

## 3. 저장 스키마 확장

`interpretation_engine.CheckResult`에 결과별 `branches`를 추가했다.

```text
상승
하락
보합
```

세 방향의 해석 문장을 `data_quality.json`의 readings에 함께 저장한다.

## 4. 구버전 캐시 호환

v0.4.4 이전의 `readings`에는 `branches`가 없다.

UI는 이를 감지하면 기존 `chart_data`와 `aux_signal_matrix`를 이용해 같은 해석 엔진을 즉석 실행한다.

- 새 원격 데이터 수집 없음
- refresh 실행 없음
- 기존 캐시만 재해석

따라서 코드 배포 후 다음 배치를 기다리지 않아도 결과별 분기를 표시할 수 있다.

## 5. 금리 상태와 조합 방향 구분

금리 지표에서는 다음 두 기준이 다르다.

- `상태`: 강한 변화속도를 잡는 기존 상태 규칙
- `조합 방향`: 자기 과거 변화폭 대비 상승/하락/보합

따라서 `상태=안정`, `조합 방향=상승`이 동시에 가능하다. v0.4.4 UI는 이 차이를 상세 설명에 명시한다.

## 변경 파일

### 신규
- `src/riskradar/state_guidance.py`
- `tests/test_state_guidance_v0_4_4.py`
- `tests/test_conditional_branches_v0_4_4.py`

### 수정
- `src/riskradar/indicator_detail_view.py`
- `src/riskradar/interpretation_engine.py`
- `src/riskradar/today_view.py`
- `src/riskradar/ui.py`
- `src/riskradar/version.py`
- `pyproject.toml`
- `CHANGELOG.md`

## 범위 제외

사용자 결정에 따라 아래는 계속 제외한다.

- 경제 일정
- FOMC/CPI/고용 이벤트 캘린더
- 이벤트 뉴스 플레이북

workflow 파일은 수정하지 않는다.
