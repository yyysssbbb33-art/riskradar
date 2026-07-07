# RiskRadar v0.5.0 → v0.5.1 마이그레이션

## 한 줄 요약

v0.5.0에서 추가한 7개 확인지표를 단순 표시 수준에서 **핵심 6개와 같은 깊이의 상세 해석 체계**로 끌어올리고, Telegram을 **전체 수치와 해석을 함께 보여주는 알림**으로 바꾼 버전입니다.

## 배포 전 주의

- `.github/workflows/refresh.yml`은 수정하지 않았습니다.
- `.github/workflows/sync-to-hf-space.yml`도 수정하지 않았습니다.
- `cron-job.org → workflow_dispatch` 운영 구조는 그대로 유지합니다.
- 새 FRED 시리즈를 추가하지 않았으므로 새 secret이 필요하지 않습니다.
- HF Dataset 저장 스키마도 바뀌지 않습니다. v0.5.0 캐시를 그대로 읽을 수 있습니다.

## 확인지표 상세 설명

다음 7개 모두 8칸 상세 설명을 갖습니다.

1. 채권시장이 보는 10년 물가 예상
2. 장기채 추가 보상
3. 투자등급 경계 기업의 추가금리
4. 신용등급 높은 기업의 추가금리
5. 기업 신용도에 따른 단기자금 금리 차이
6. 미국 금융시장 전반의 자금 사정
7. 미국 금융시장 전반의 불안

각 상세 화면은 다음 순서입니다.

1. 현재값
2. 약 1개월 변화
3. 현재 방향
4. 현재 불러온 과거값 중 위치
5. 지금 이렇게 읽는 이유
6. 같이 볼 지표의 현재 결과
7. 오를 때 / 내릴 때 / 뚜렷한 움직임이 없을 때 해석
8. 기존 핵심 6개와 같은 8칸 상세 설명·근거·한계

## UI 변경

### 오늘의 해석

기존 오늘의 해석 아래에 **확인지표 상세 설명** 아코디언 7개가 추가됩니다.

### 지표 설명

기존 핵심 6개만 선택하던 드롭다운을 핵심 6개 + 확인지표 7개로 확장했습니다.

### 지표를 같이 보는 법

다음 관계를 새로 자세히 설명합니다.

- `HY → BBB → IG` 기업 부담 확산
- 회사채와 단기자금 금리 차이의 동시·비동시 움직임
- NFCI와 STLFSI를 외부 종합 참고로만 쓰는 이유
- NFCI와 STLFSI가 서로 엇갈릴 때의 해석

## Telegram 변경

v0.5.0은 영역과 조합 중심 요약이었지만 수치 결과가 부족했습니다. v0.5.1은 다음 순서입니다.

1. **핵심 지표 6개 전체 결과**
   - 최신값
   - 약 1개월 변화
   - 약 3개월 변화
   - 현재 상태
2. **확인지표 7개 전체 결과**
   - 최신값
   - 약 1개월 변화
   - 방향
   - NFCI·STLFSI는 역사적 현재 위치도 함께 표시
3. **여러 지표를 같이 보면**
   - 3개 영역 요약
4. **눈에 띄는 조합과 해석**
   - 최대 2개 조합
   - 조합명뿐 아니라 현재 데이터가 더 지지하는 설명
5. **추가 확인**
   - 신용 확산
   - 단기자금
   - 외부 참고
6. 데이터 기준일

금리·회사채·CP 변화는 사용자 화면에서 `%p`로 표시하고 VIX는 `포인트`, NFCI·STLFSI는 지수 변화량으로 표시합니다.

## 변경 파일

- 신규: `src/riskradar/aux_interpretation_cards.py`
- 신규: `src/riskradar/aux_detail_view.py`
- 변경: `src/riskradar/display_text.py`
- 변경: `src/riskradar/formatting.py`
- 변경: `src/riskradar/relationship_guide.py`
- 변경: `src/riskradar/state_guidance.py`
- 변경: `src/riskradar/telegram_client.py`
- 변경: `src/riskradar/ui.py`
- 변경: `src/riskradar/version.py`
- 신규: `tests/test_v0_5_1_guides_and_telegram.py`
- 변경: `tests/test_plain_language_v0_4_6.py`
- 변경: `README.md`
- 변경: `CHANGELOG.md`

## 검증

```bash
pip install -e ".[ui,dev]"
pytest -q
```

전체 테스트는 실행 제한 때문에 두 묶음으로 나눠 검증했습니다.

- 76개 통과
- 49개 통과
- 합계 125개 통과

`compileall`과 diff 공백 검사도 별도로 수행합니다.
