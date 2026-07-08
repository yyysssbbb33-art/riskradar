# RiskRadar v0.7.4 → v0.8.0 마이그레이션

## 결론

v0.8.0은 **UI·표현 계층 변경**입니다. 수집 엔진, 핵심 6개 판정, 기업 신용 엔진, 30년 금리 계산, decision snapshot/diff, decision ledger, prune 정책, Telegram 전송 규칙은 변경하지 않습니다.

전체 패키지를 교체한 뒤 기존과 같은 GitHub Actions refresh를 1회 실행하면 됩니다. 기존 HF Dataset과 v0.7.x 캐시를 그대로 읽을 수 있습니다.

## 바뀌는 화면

### 오늘
- 상단 신용·금리·변동성 카드에 현재값과 1개월 변화 표시
- `계속 이어지는 변화` → `현재 추세`
- 30년 금리 대형 패널 제거
- 기업 신용 2×2에 현재값·상태·1개월 변화 표시
- HY−BBB 현재값·1개월 변화 표시

### 신용
- 사용자 상태명 변경:
  - normal → 특이 신호 없음
  - early_change → 상승 조짐
  - newly_rising → 상승 확인
  - rising_persistent → 높은 수준 지속
  - retracing → 하락 전환
  - normalized → 신호 해제
- 최근 90일 기록도 같은 언어 체계를 사용

### 금리
새 전용 탭이 추가됩니다.

1. 금리 현황 2×2
2. 금리곡선
3. 30년 금리
4. 장기금리 참고
5. 금리 설명·주의사항

### 비교
- `전체 지표 비교` → `최신 지표 비교`
- 고정 `같은 날짜 비교` 제거
- 핵심 6개에 실제 관측값이 모두 있는 날짜를 사용자가 직접 선택

## 배포 후 확인

1. 앱 상단에 현재값·상태·1개월 변화가 함께 보이는지
2. `금리` 탭이 보이는지
3. 신용 2×2에 HY·BBB·A·CP 수치가 보이는지
4. HY−BBB에 현재 차이와 1개월 변화가 보이는지
5. 비교 탭에서 날짜를 선택하면 핵심 6개 카드가 바뀌는지
6. `audit/decision_ledger.parquet`가 기존처럼 유지되는지

## 바꿀 필요 없는 것

- GitHub Actions workflow
- FRED API key
- HF token / Dataset repo
- Telegram secrets
- 기존 cache retention 환경변수
