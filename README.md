---
title: RiskRadar
emoji: 📉
sdk: docker
app_port: 7860
pinned: false
---

# RiskRadar — 미국 매크로 스트레스 계기판

FRED 6개 시계열(변동성·신용·금리·실질금리·수익률곡선)의 최신값·변화속도·백분위·
상태 라벨을 분리해 보여주는 **읽기 전용 대시보드**.
폭락 예측·확률 모델·매매추천·과열/환율 판단은 하지 않는다.

## 구조 (원래 블루프린트에서 변경한 점)

원안은 `cron-job.org → HF Space refresh 엔드포인트(동기, 25초)` 였다.
HF Space 콜드스타트 + 전 구간 백분위 재계산 + HF 업로드를 25초 동기 창에
넣으면 자주 실패(캐시 미발행)한다. 그래서 **쓰기와 읽기를 분리**했다.

```
GitHub Actions (스케줄 cron, 콜드스타트/타임아웃 없음)
  └─ run_refresh.py
       FRED fetch → transform → state → HF Dataset repo(versioned) publish → Telegram

HF Docker Space (읽기 전용)
  └─ app.py : FastAPI(/api/healthz, /api/status) + Gradio UI(/)
       data_status.json → active_cache_version → 산출물 로드
```

- cron-job.org, refresh 엔드포인트, refresh lock, 동기/비동기 고민이 전부 사라짐.
- Actions `concurrency` 그룹이 lock을 대체.
- Telegram 성공 알림이 실제 완료 신호. HTTP 응답에 의존하지 않음.
- 원하면 refresh를 cron-job.org로도 트리거 가능 — `run_refresh()`를 감싸는
  얇은 FastAPI 엔드포인트만 추가하면 됨(즉시 202 반환 + 백그라운드). 기본은 Actions.

## 데이터 원칙

- raw 관측값만 계산 입력(ffill 금지). 상태는 매 refresh마다 raw에서 재계산.
- 모든 백분위/변화/상태는 point-in-time (미래 데이터 누수 없음).
  → `tests/test_core.py::test_no_lookahead_metrics_and_states` 가 보증.
- 긴 공백을 가로지른 변화량은 calendar-span guard로 NaN.
- Synced Snapshot은 ffill 전 원본 관측일 교집합의 최근일만 사용.
- 금리 급락은 상태가 아니라 `drop_flag`.
- 버전 폴더는 `CACHE_KEEP_LAST_N`(기본 14)만 유지, 나머지 prune → repo 무한증식 방지.

## 로컬 실행

```bash
pip install -e ".[ui,dev]"
pytest -q                     # 24 tests

# 오프라인 refresh(합성 데이터) 후 로컬 캐시로 UI 띄우기
CACHE_BACKEND=local CACHE_LOCAL_ROOT=./_cache python app.py
```

실데이터 refresh:
```bash
export FRED_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
CACHE_BACKEND=local python run_refresh.py
```

## 배포 셋업

1. **FRED API key** 발급 → `FRED_API_KEY`.
2. **HF Dataset repo** 생성(예: `you/riskradar-cache`) → `HF_DATASET_REPO_ID`, write 권한 `HF_TOKEN`.
3. **Telegram**: BotFather로 봇 생성 → `TELEGRAM_BOT_TOKEN`, 봇에 메시지 후
   `getUpdates`로 `TELEGRAM_CHAT_ID` 확인.
4. **GitHub repo** → Settings > Secrets 에 위 6개 등록. `.github/workflows/refresh.yml`이
   화~토 08:30 KST에 자동 실행(수동 실행도 가능).
5. **HF Docker Space** 생성 → 이 repo 연결. Space Secrets에
   `HF_DATASET_REPO_ID`, `HF_TOKEN`(read면 충분) 등록. `CACHE_BACKEND=hf_dataset`.

## 지표

VIXCLS · BAMLH0A0HYM2(HY OAS) · T10Y3M · DGS30 · DGS2 · DFII10.
임계값은 전부 `src/riskradar/config.py` 에서 튜닝.
