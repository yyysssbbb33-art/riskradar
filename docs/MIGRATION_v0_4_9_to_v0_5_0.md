# RiskRadar v0.4.9 → v0.5.0 마이그레이션

## 한 줄 요약

기존 핵심 6개와 배포 구조는 유지하면서, **신용 확산·단기 기업자금 확인·외부 공식 종합 참고**를 추가하고 Telegram 알림을 현재 해석 구조에 맞게 바꾼 버전입니다.

## 배포 전 주의

- `.github/workflows/refresh.yml`은 수정하지 않았습니다.
- `.github/workflows/sync-to-hf-space.yml`도 수정하지 않았습니다.
- 현재 운영 중인 `cron-job.org → workflow_dispatch` 구조를 그대로 유지합니다.
- 새 FRED 시리즈도 기존 `FRED_API_KEY`를 사용하므로 새 secret은 필요하지 않습니다.
- HF Dataset 저장 구조는 그대로이며 `aux_signal_matrix.parquet`에 새 행과 메타데이터 열이 추가됩니다.

## 새로 수집하는 지표

### 기업 부담 확산

- `BAMLC0A4CBBB` — **투자등급 경계 기업의 추가금리**
- 기존 `BAMLC0A0CM` — **신용등급 높은 기업의 추가금리**

핵심지표인 저신용 기업의 추가금리와 함께 봐서 부담이 어디까지 넓어지는지 확인합니다.

### 단기 기업자금

- `RIFSPPNA2P2D30NB` — 30일 A2/P2 비금융 기업어음 금리
- `RIFSPPNAAD30NB` — 30일 AA 비금융 기업어음 금리
- 파생값: A2/P2 - AA
- 사용자 화면: **기업 신용도에 따른 단기자금 금리 차이**

두 시리즈에 실제 관측값이 함께 있는 날짜만 사용합니다. 차이는 내부에서 bp로 저장합니다. 한쪽 원자료 수집이 실패하면 해당 확인지표만 실패하며 핵심 6개 refresh는 계속됩니다.

### 외부 종합 참고

- `NFCI` — **미국 금융시장 전반의 자금 사정**
- `STLFSI4` — **미국 금융시장 전반의 불안**

두 지표는 참고용입니다. 다음 계산에서 제외됩니다.

- 3개 영역 개수
- 조합 탐지
- 가능한 설명의 지지·약화
- 최상단 상태

## 화면 구조 변경

확인지표를 낱개 목록으로 늘어놓지 않고 질문별로 묶습니다.

1. 장기금리가 왜 움직이나
2. 기업 부담이 어디까지 번졌나
3. 단기 자금시장도 영향을 받고 있나
4. 외부 종합 참고

NFCI와 STLFSI에는 단순 0선 판정 대신 자기 과거 수준 대비 현재 위치를 함께 사용합니다.

## Telegram 변경

기존 알림은 핵심 6개 상태를 한 줄씩 나열하고 캐시 버전과 배치 시각을 보여줬습니다. v0.5.0에서는 다음 순서로 바뀝니다.

1. 현재 3개 영역 중 몇 개가 움직이는지
2. 주식시장·기업 부담 / 경기 흐름 / 금리 움직임 요약
3. 최대 2개의 눈에 띄는 조합
4. 신용 확산·단기자금·외부 참고
5. 데이터 기준일

부분 성공이면 실패하거나 오래된 지표를 먼저 알리고 같은 현재 상태 요약을 이어서 보여줍니다.

## 변경 파일

- `src/riskradar/aux_config.py`
- `src/riskradar/aux_indicators.py`
- `src/riskradar/combo_rules.py`
- `src/riskradar/display_text.py`
- `src/riskradar/interpretation_engine.py`
- `src/riskradar/refresh_service.py`
- `src/riskradar/state_guidance.py`
- `src/riskradar/telegram_client.py`
- `src/riskradar/today_view.py`
- `src/riskradar/version.py`
- `tests/test_v0_5_0_new_indicators_and_telegram.py`
- `README.md`
- `CHANGELOG.md`

## 검증

```bash
pip install -e ".[ui,dev]"
pytest -q
```

개발 환경에서는 전체 119개 테스트를 여러 묶음으로 나눠 실행해 모두 통과했고, `compileall`도 통과했습니다.
