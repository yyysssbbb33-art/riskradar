# RiskRadar v0.8.0 → v0.8.1 마이그레이션

## 성격

v0.8.1은 **표현·상세 정보 배치·디자인 패치**입니다. 시장 데이터 schema와 판정 엔진은 바뀌지 않습니다.

## 배포

가장 안전한 방법은 v0.8.1 전체 ZIP의 저장소 내용을 기존 GitHub 저장소에 덮어쓰고 commit한 뒤 기존 `refresh` workflow를 한 번 실행하는 것입니다.

기존 환경변수와 secrets는 그대로 사용합니다.

- `FRED_API_KEY`
- `HF_TOKEN`
- `HF_DATASET_REPO_ID`
- Telegram 관련 secret

## 캐시 호환

v0.8.1 UI는 v0.8.0 캐시를 그대로 읽습니다. 새 refresh 전에도 화면은 열리며, 다음 정상 refresh부터 코드 버전이 0.8.1로 기록됩니다.

## 바뀌는 화면

- 신용·금리 상세 설명의 문체와 배치
- CP 하락 전환 범위 요약
- HY 핵심 카드 수준 표현
- Telegram 사용자 문구
- 카드·표·아코디언 색상과 시각 계층

## 바뀌지 않는 것

- 수집 대상과 FRED series
- threshold와 상태 판정
- 기업 신용 상태머신 로직
- 30년 금리 구성 계산
- decision snapshot / diff / ledger schema
- cache prune 정책
- Telegram 전송 조건과 전송 순서

## 배포 후 확인

1. GitHub Actions refresh 성공
2. 앱 상단 버전 `v0.8.1`
3. 신용 탭의 CP 하락 전환 문구가 상승 신호로 나오지 않는지
4. 금리 탭의 상세 설명과 Visual Polish가 정상 표시되는지
5. Telegram에 `평소 범위`, `오르는 중`이 다시 나오지 않는지
