# Changelog

버전은 `src/riskradar/version.py`의 `__version__`을 단일 소스로 한다.
`pyproject.toml`의 version도 이 값에 맞춘다.

## [0.4.0] — 진행 중 (해석 강화 라인, 경제일정 제외)

### 1단계 — 보조지표(2층) 수집 + 방향 판정  ✅

핵심 6개(1층)와 분리된 원인 확인용 보조지표를 추가했다. 3축·종합상태에는 넣지 않는다.

- **보조지표 3개 (전부 FRED로 통일)**
  - `T10YIE` — 10Y Breakeven (인플레이션 보상 방향)
  - `BAMLC0A0CM` — IG OAS (HY 단독인지 투자등급까지 확대인지)
  - `THREEFYTP10` — 10Y Term Premium, Kim-Wright (장기구간 고유 위험보상)
  - ※ 원래 설계의 NY Fed ACM(xls, 주간) 대신 FRED 일별 시리즈로 대체.
    별도 소스 파싱 의존을 없애고 기존 `fred_client` 경로를 그대로 재사용.
    ACM이 필요해지면 이후 `aux_sources/`에 옵션으로 추가.

- **방향 판정** (상승 / 하락 / 보합 / 판정불가)
  - 방향 = 최근 1개월(21거래일) 변화의 부호
  - 유의성 = |변화|가 자기 과거 |변화| 분포에서 차지하는 백분위
  - 크기가 미미하면(`flat_abs_pct` 미만) 보합으로 눌러 노이즈 차단
  - 등속 추세를 보합으로 놓치지 않도록 백분위-부호 방식이 아닌 부호+크기유의성 방식 채택
  - anti-lookahead(최신 시점은 과거만 사용) / span guard(달력 공백 큰 변화 무효) 적용

### 추가/변경 파일
- 신규: `src/riskradar/version.py`
- 신규: `src/riskradar/aux_config.py`
- 신규: `src/riskradar/aux_indicators.py`
- 신규: `tests/test_aux_v0_4.py`
- 변경: `src/riskradar/fred_client.py` (저수준 `fetch_fred_series` 노출, 기존 인터페이스 유지)

### 테스트
- 신규 7 + 기존 28 = 35개 통과. 기존 회귀 없음.

### 파이프라인 통합  ✅
- `run_refresh`가 `collect_aux()`를 호출하고 결과를 `aux_signal_matrix.parquet`로 저장
- 보조지표 freshness(`stale_days`, `staleness_label`) 표시
- 보조지표 실패는 전체를 깨지 않음(핵심 6개 정상이면 status=success). `data_quality.aux_failed`에 기록
- 하위호환: `aux_signal_matrix`는 옵셔널 아티팩트. 옛 캐시 버전에 없으면 빈 DataFrame으로 관용 처리 (`_verify` 대상 아님)
- `data_quality`에 `aux_directions` / `aux_failed` 요약 추가

### 추가/변경 파일 (통합분)
- 변경: `src/riskradar/cache_store.py` (OPTIONAL_ARTIFACTS + 두 스토어 publish/load_artifact)
- 변경: `src/riskradar/refresh_service.py` (aux 수집·저장·요약, `aux_fetcher` 주입 지원)
- 신규: `tests/test_aux_integration_v0_4.py`

### 테스트 (누적)
- 신규 11(방향 7 + 통합 4) + 기존 28 = 39개 통과. 회귀 없음.

### 아직 안 한 것 (다음 스텝)
- UI에 보조지표 방향/freshness 노출 (지금은 저장까지만)

---

### 2단계 — 3축 복합 조망 엔진  ✅

단일 지표 상태를 3개 축으로 묶는다. 6개를 그대로 더하지 않아 금리 중복 카운트를 피한다.

- **변동성·신용 축 (VIX + HY OAS, 비대칭)** — 동등 투표 안 함. 5개 상태:
  A 뚜렷한 변화 없음 / B 변동성 선행 / C 신용 단독 변화 / D 변동성·신용 동반 / E 변동성 진정·신용 지속.
  VIX 활성 = 즉시(stress) 또는 지속(최근 5개 중 3개 기본 이탈). HY 활성 = watch 이상.
  E는 최근 연결 창(10개)에 VIX 활성 이력이 있는 C와 구분.
- **경기 사이클 축 (T10Y3M)** — 기존 경로 상태 재사용. normal만 기본, 나머지는 변화.
- **금리 방향 축 (30Y·2Y·10Y Real)** — 다수결 안 함. 변화없음/상승/하락/혼합.
  혼합을 중립으로 상쇄하지 않는다(엇갈림 자체가 정보).
- **최상단 복합 조망** — "3축 중 N축 변화" + 변화축/기본축 목록.
  단일 위험점수·행동유도 라벨 없음(테스트로 score/risk_level 필드 부재 검증).
  모든 축 요약에 C등급 disclaimer 부착.

### 추가 파일 (2단계)
- 신규: `src/riskradar/axis_engine.py` (기존 파일 수정 없음, `state_rules.LABELS`만 참조)
- 신규: `tests/test_axis_v0_4.py`

### 테스트 (누적)
- 방향 7 + 통합 4 + 축 15 + 기존 28 = 54개 통과.

### 아직 안 한 것 (다음 스텝)
- 3축 결과를 refresh 파이프라인에 저장(`axis_snapshot.json`) + UI 노출
- 3단계: 조합 탐지 + 조건부 해석 엔진 (30Y↑·2Y↓ 완성형 기준, 조합 5개부터)

---

### 3단계 — 조합 탐지 + 조건부 해석 엔진  ✅

3축 위에서 관찰된 조합마다 해석을 생성한다. 해석은 사실+방향까지만, 종합 판단·행동 지시는 없다.

- **조합 카탈로그 (`combo_rules.py`)** — 4개. 30Y↑·2Y↓는 완성형(확인지표 4개: 실질금리·Breakeven·Term Premium·IG OAS), 변동성·신용 동반(D)·신용 단독(C)·전반적 금리 상승은 골격.
- **조건부 해석 (`interpretation_engine.py`)**:
  - 관찰 사실 → 가능한 설명 2~4개 → 확인지표 방향별 지지/약화 → 결과 충돌 → 남은 불확실성
  - 확인지표가 서로 다른 설명을 2개 이상 동시 지지하면 하나로 정리하지 않고 '복합'으로 남김
  - 보조지표 판정불가면 그 확인만 보류(uncertainty에 명시), 나머지는 유지
  - 최상단 노출 상한 3개
- **refresh 통합** — `data_quality`에 `axes`(복합 조망)·`readings`(조합 해석) 저장. 계산 실패는 전체를 안 깨뜸. (기존 잔재 `compute_axes` 호출을 `composite_view`+`read_all`로 정리)
- **가드 테스트** — 어떤 해석에도 "위험/안전/조심/매수/매도" 등 종합 판단·행동 지시어가 없음을 검증.

### 추가/변경 파일 (3단계)
- 신규: `src/riskradar/combo_rules.py`, `src/riskradar/interpretation_engine.py`
- 신규: `tests/test_interpretation_v0_4.py`
- 변경: `src/riskradar/refresh_service.py` (axis+interpretation 통합, 잔재 정리)

### 테스트 (누적)
- 방향 7 + aux통합 4 + 축 15 + 해석 7 + 기존 28 = 61개 통과.

### 아직 안 한 것 (다음 스텝)
- 4단계: "오늘의 해석" UI 탭 (축 조망 + 조합 해석 + 보조지표 방향을 화면에 표시)
- 과거 국면(2008/2020/2022)으로 C등급 컷 튜닝

---

### 4단계 — "오늘의 해석" UI 탭  ✅

지금까지 만든 축 조망·조합 해석·보조지표 방향을 화면에 노출한다.

- **렌더링 (`today_view.py`, gradio 비의존)** — data_quality + aux 표를 마크다운으로.
  복합 조망 요약 → 3축 상태 → disclaimer → 보조지표 방향(+freshness) → 관찰된 조합 해석.
  판단 문장을 새로 만들지 않고 엔진 출력만 표시.
- **데이터 로드 (`cache_store.py`)** — 두 스토어에 `load_data_quality()` 추가.
  (`axes`/`readings`는 parquet가 아니라 data_quality.json에 있어 별도 로더 필요)
- **탭 배치 (`ui.py`)** — Market Stress Board 다음 2번째 탭. aux는 옵셔널이라 `load_artifact`로 별도 로드, 실패해도 대시보드 안 깨뜸.
- **가드 테스트** — 행동 지시형 표현 부재, 빈 상태(옛 캐시) placeholder, disclaimer 노출 검증.

### 추가/변경 파일 (4단계)
- 신규: `src/riskradar/today_view.py`, `tests/test_today_view_v0_4.py`
- 변경: `src/riskradar/cache_store.py` (`load_data_quality` 두 스토어)
- 변경: `src/riskradar/ui.py` ("오늘의 해석" 탭, data_quality/aux 로드)

### 테스트 (누적)
- 방향 7 + aux통합 4 + 축 15 + 해석 7 + 오늘의해석 6 + 기존 28 = 67개 통과.

### 아직 안 한 것 (다음 스텝)
- 과거 국면(2008/2020/2022)으로 C등급 컷 튜닝 (VIX 지속활성 5중3, flat_abs_pct 40 등)
- Guide 탭에 "지표를 같이 보는 법"(조합 설명) 반영

---

### 2단계 — 3축 엔진  ✅

단일 지표 상태(state_rules 출력)를 3개 축으로 묶는다. 6개를 그대로 더하지 않는다.

- **변동성·신용 축 (VIX/HY 비대칭)** — 5개 상태
  - 뚜렷한 변화 없음 / 변동성 선행 / 신용 단독 변화 / 변동성·신용 동반 / 변동성 진정·신용 지속(E)
  - VIX 활성: 최신이 stress면 즉시, 아니면 최근 5개 중 3개 활성이면 지속 활성 (하루 급등만으론 안 켬)
  - HY 활성: 최신 상태가 기본집합(calm/neutral)을 벗어남
  - E상태(변동성 진정·신용 지속)는 연결창(최근10) 이력으로 신용 단독과 구분
- **경기 사이클 축 (T10Y3M)** — 기존 경로 상태 재사용, normal=기본 그 외=변화
- **금리 방향 축 (30Y+2Y+Real)** — 다수결 금지. 상승/하락/혼합/변화없음. 혼합을 중립으로 상쇄하지 않음(엇갈림 자체가 정보)
- **최상단 복합 조망** — 단일 위험 라벨·점수 없음. "3축 중 N축 변화" + 변화/기본 축 목록. 각 축에 구성지표 원 상태 병기 + C등급 표시

### 추가/변경 파일 (2단계)
- 신규: `src/riskradar/axis_config.py`
- 신규: `src/riskradar/axis_engine.py`
- 신규: `tests/test_axis_v0_4.py`
- 변경: `src/riskradar/refresh_service.py` (axis 계산 후 `data_quality["axes"]`에 실어 저장 — 별도 스토어 배관 불필요)

### 테스트 (누적)
- 방향 7 + aux통합 4 + 3축 16 + 기존 28 = 55개 통과. 회귀 없음.

### 아직 안 한 것 (다음 스텝)
- 3단계: 조합·조건부 해석 엔진 (3축 상태 + 보조지표 방향을 입력으로)
- UI: 오늘의 해석 탭 (3축 조망 + 조합 카드)

### C등급 초기값 (과거 국면으로 조정 예정)
- `lookback_obs=21`, `flat_abs_pct=40`, `min_obs=250`, `span_guard_days=45`
