# RiskRadar v0.7.0 → v0.7.1 마이그레이션

## 목적

v0.7.1은 v0.7.0의 변화 중심 첫 화면을 유지하면서 장기금리 해석을 같은 만기의 산술 구성으로 정리합니다. 기업 신용 범위·지속 엔진, 핵심 6개 상태 규칙, aux direction schema, decision snapshot schema는 바꾸지 않습니다.

## 핵심 변경

### 1. 첫 화면 aux 누출 수정

상세 목록과 변화센터의 노출 정책을 분리했습니다.

- `AUX_CHANGE_CENTER_KEYS` 독립 정의
- `market_transitions`, `recovery_gap_events`, `data_quality_transitions` 세 채널 모두 필터
- 필터 뒤에 5개·3개·4개 표시 제한 적용
- IGOAS 수집, direction, decision snapshot/diff, 운영 진단은 유지

### 2. DFII30 전용 경로

DFII30은 core나 aux에 추가하지 않습니다.

- core 6개 카드 증가 없음
- aux 방향 판정·schema 변경 없음
- `AUX_DIRECTION_SCHEMA`는 계속 `aux-v1`
- refresh당 DFII30 1회 수집

### 3. 동일 만기 구성

공통 관측일에서 한 번만 계산합니다.

```text
INFLCOMP30 = DGS30 - DFII30

ΔDGS30 = ΔDFII30 + ΔINFLCOMP30
```

산출물:

- `rate_composition_series.parquet`
- `rate_composition.json`

UI와 Telegram은 동일한 `rate_composition.json` 요약을 사용합니다.

### 4. 곡선 설명

- 주 판정창: 20관측치(약 1개월)
- 60관측치(약 3개월): 구성 변화의 배경 표시만 사용
- 최소 유의폭: 각 변화 10bp
- 30년 변화와 30Y-2Y 스프레드 변화는 같은 20관측 창 사용
- 쉬운 한국어를 먼저 쓰고 실제 시장 약칭은 괄호로 표시
- 재정 우려·인플레이션 공포 같은 자동 인과 설명은 붙이지 않음

### 5. 기존 10년 지표의 역할

- `NOMINAL_REAL_UP`, `NOMINAL_UP_REAL_NOT` 제거
- 10년 실질금리와 10년 명목−실질 금리차는 교차 만기 참고
- 10년 Term Premium은 30년 산술 구성에 더하지 않는 별도 맥락
- 변화센터 노출 정책은 상세 목록과 독립 정의하며, 현재 v0.7.1은 기존 사용자 노출을 유지해 IGOAS만 제외

## 배포

전체 패키지 교체를 권장합니다. workflow와 secrets는 바꿀 필요가 없습니다.

배포 뒤 **정상 refresh 1회가 필요합니다.** 새 refresh가 완료되어야 DFII30을 수집하고 새 rate artifact를 생성합니다. 그 전에는 앱의 기존 기능은 정상 동작하고 장기금리 구성 패널만 `자료 확인 불가` fallback을 표시합니다.

## 실패 격리

DFII30 전용 수집이 실패해도 핵심 6개 refresh는 실패하지 않습니다. 해당 배치의 rate composition은 전체 소비자에서 일관되게 unavailable로 표시됩니다.

## 검증 기준

- 한 refresh에서 DFII30 fetch 정확히 1회
- proxy 계산 1회, UI·Telegram·저장 동일 결과
- DFII30 실패 시 core refresh 유지 + rate composition 일관된 unavailable
- IGOAS 세 이벤트 채널 첫 화면 미노출
- 숨은 사건이 표시 슬롯을 차지하지 않음
- raw decision diff에는 IGOAS 유지
- aux schema `aux-v1` 유지
- 전체 테스트 통과
