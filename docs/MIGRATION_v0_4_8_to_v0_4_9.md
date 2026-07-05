# RiskRadar v0.4.8 → v0.4.9

## 왜 필요한가

v0.4.8까지 HF Space UI는 `app.py` import 시 `build_app()`을 한 번 실행하면서 Dataset을 읽었다. 이후 GitHub refresh가 새 cache_version을 발행해도 Space 프로세스가 재시작되지 않으면 화면은 시작 시점의 옛 데이터를 계속 보여줄 수 있었다.

또한 핵심 parquet는 한 active version을 읽은 뒤 `data_quality.json`은 `data_status.json`을 다시 조회해 다른 active version을 읽을 수 있었고, HF metadata 다운로드 오류를 전부 빈 딕셔너리로 숨겨 실제 읽기 오류를 `구버전 데이터`로 오진할 수 있었다.

## 변경

1. 브라우저 page load마다 최신 HF Dataset 활성 캐시 재조회
2. 수동 `HF Dataset 최신 데이터 다시 읽기` 버튼 추가
3. 최초 active_cache_version 하나에 모든 부속 파일 고정
4. metadata 네트워크/다운로드 오류를 데이터 상태 탭에 노출
5. UI fallback 결과와 저장 원본 data_quality 분리
6. Telegram 후 parquet 전체 재업로드 제거, status만 갱신
7. `/api/status` 경량화

## 배포

- v0.4.8 사용자는 patch-only를 덮어써도 된다.
- workflow 파일은 변경하지 않았다.
- 배포 후 Space를 한 번 재빌드하면 이후부터는 GitHub refresh 뒤 Space 재시작 없이 브라우저 page load 또는 수동 버튼으로 최신 Dataset을 읽는다.
