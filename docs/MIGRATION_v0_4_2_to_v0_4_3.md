# RiskRadar v0.4.2 → v0.4.3

## 문제

v0.4.2 코드를 HF Space에 먼저 배포하고, HF Dataset의 활성 캐시가 이전 버전이면 `data_quality.json`에 `axes`와 `readings`가 없을 수 있었다. 이 경우 `오늘의 해석` 탭은 다음 문구만 표시했다.

> 축 조망 데이터가 아직 없습니다. 다음 배치 후 표시됩니다.

핵심 6개 시계열과 `chart_data`는 이미 존재하므로, 다음 배치를 기다려야 할 기술적 이유는 없었다.

## 변경

v0.4.3 UI는 `axes/readings`가 없는 기존 캐시를 읽을 때 아래 fallback을 수행한다.

1. 기존 `chart_data`를 지표별 시계열 프레임으로 복원한다.
2. 같은 `axis_engine`으로 3축 조망을 즉석 계산한다.
3. `aux_signal_matrix`가 있으면 보조지표 방향과 freshness를 복원한다.
4. 같은 `interpretation_engine`으로 조합 해석을 즉석 계산한다.
5. 새 데이터 수집이나 refresh는 수행하지 않는다.

정상적인 새 캐시에 이미 `axes/readings`가 있으면 저장된 결과를 그대로 사용하고 fallback은 실행하지 않는다.

## 효과

- 코드 배포 직후 다음 배치를 기다리지 않아도 3축 조망 표시
- v0.4 계열 보조지표 캐시가 있으면 조합 해석도 즉시 복원
- 더 오래된 캐시라 보조지표가 없어도 3축 조망은 표시
- 다음 정규 배치 후에는 저장된 `axes/readings`가 다시 우선 사용됨

## 변경 파일

- `src/riskradar/ui.py`
- `src/riskradar/version.py`
- `pyproject.toml`
- `CHANGELOG.md`
- `tests/test_ui_today_fallback_v0_4_3.py`

## 테스트

- 전체 78개 통과
- 기존 캐시에서 axes/readings 자동 복원
- 기존 axes/readings 보존
- 보조지표 캐시가 없어도 축 조망 복원
