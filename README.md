---
title: RiskRadar
emoji: 📉
sdk: docker
app_port: 7860
pinned: false
---

# RiskRadar — 미국 매크로 스트레스 계기판

FRED 6개 시계열(변동성·신용·금리·실질금리·수익률곡선)의 최신값·변화속도·과거 대비 위치·
상태 라벨을 분리해 보여주는 **읽기 전용 대시보드**.
폭락 예측·확률 모델·매매추천·과열/환율 판단은 하지 않는다.

## 구조 (원래 블루프린트에서 변경한 점)

원안은 `cron-job.org → HF Space refresh 엔드포인트(동기, 25초)` 였다.
HF Space 콜드스타트 + 전 구간 과거 대비 위치 재계산 + HF 업로드를 25초 동기 창에
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
- 모든 과거 대비 위치·변화·상태 계산은 그 시점까지의 데이터만 사용해 미래 데이터가 섞이지 않음.
  → `tests/test_core.py::test_no_lookahead_metrics_and_states` 가 보증.
- 긴 공백을 가로지른 변화량은 calendar-span guard로 NaN.
- Synced Snapshot은 ffill 전 원본 관측일 교집합의 최근일만 사용.
- 금리 급락은 상태가 아니라 `drop_flag`.
- 매 refresh마다 `versions/<cache_version>/` 아래에 raw, signal matrix, synced snapshot, chart data를 저장한다.
- HF 화면의 `30D History` 탭은 과거 버전의 `signal_matrix.parquet`를 읽어 최근 30일 변화를 보여준다.
- 버전 폴더는 `CACHE_KEEP_LAST_N`(기본 45)만 유지, 나머지 prune → repo 무한증식 방지. 30일 히스토리를 안정적으로 보려면 30 이상을 권장한다.

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

## 화면에서 보는 법

RiskRadar의 메인 화면은 `현재 상황`입니다. 먼저 HY OAS와 VIX를 같이 보고,
그다음 2Y·30Y·10Y Real의 변화속도를 확인합니다. T10Y3M은 현재 시장 스트레스라기보다
경기 사이클의 배경 지표로 봅니다.

- `상태`: 평온·관찰·스트레스 등 현재 구간. 단독 매매 신호가 아니라 빠른 분류용 라벨.
- `최신값`: FRED에서 가져온 가장 최근 원자료 관측값.
- `관측일/경과일`: 실제 데이터가 마지막으로 찍힌 날짜와 현재 기준 경과일.
- `약 1개월 변화/약 3개월 변화`: 달력 기준 정확히 1개월·3개월이 아니라 실제 관측치 20개·60개 전 대비 변화량.
- `최근 5년 위치/최근 10년 위치`: 해당 기간의 과거 관측값 중 현재값이 어느 위치인지 보여줌. 90%면 과거 관측값 약 90%보다 현재값이 높다는 뜻.
- `급락`: 금리 지표가 짧은 기간에 크게 하락했는지 표시. 완화 기대일 수도, 경기둔화 공포일 수도 있음.
- `근거`: 상태 라벨이 붙은 이유를 한 문장으로 요약.

### 최근 30일 탭

`최근 30일`은 HF Dataset에 저장된 과거 `versions/<cache_version>/signal_matrix.parquet`를 모아서
최근 30일 동안 각 지표가 어떻게 변했는지 보여주는 탭입니다. 선택 상자에서 VIX, HY OAS, T10Y3M,
30Y, 2Y, 10Y Real 중 하나를 고르면 날짜별 최신값·상태·약 1개월/약 3개월 변화·최근 5년/10년 위치·근거를 볼 수 있습니다.

여기서 날짜는 FRED 관측일이 아니라 **RiskRadar가 저장한 스냅샷 날짜**입니다. 미국 휴장이나 공표 지연이 있으면
같은 관측값이 며칠 반복될 수 있으므로, 표의 `관측일`도 함께 확인해야 합니다.

## 지표 해설

| 지표 | 의미 | 해석 포인트 |
|---|---|---|
| VIX | 미국 주식 옵션시장이 반영하는 단기 변동성 | 단기 불안·공포를 빠르게 반영. HY OAS와 같이 상승할 때 더 위험하게 봄. |
| HY OAS | 투기등급 회사채와 국채 사이의 신용 스프레드 | 신용 스트레스의 핵심 지표. 높아질수록 저신용 기업 자금조달 압박이 커짐. |
| T10Y3M | 미국 10년 국채금리 - 3개월 국채금리 | 수익률곡선 기울기. 현재 스트레스보다 경기 사이클 배경으로 해석. |
| 30Y | 미국 30년 장기국채 금리 | 장기 할인율·자금조달 비용 부담. 수준보다 변화속도가 중요. |
| 2Y | 미국 2년 국채금리 | 연준 정책금리 기대에 민감. 빠른 상승은 정책 압박을 뜻할 수 있음. |
| 10Y Real | 미국 10년 실질금리 | 인플레이션을 뺀 실질 할인율. 성장주·장기자산에 부담이 되기 쉬움. |

## 해석상 주의

- 평온은 위험이 없다는 뜻이 아니라, 이 지표 기준으로 스트레스가 크지 않다는 뜻이다.
- 관찰은 매도 신호가 아니라, 변화가 커졌으니 다른 지표와 같이 보라는 뜻이다.
- 스트레스는 시장이 이미 위험을 가격에 반영하고 있다는 뜻이지, 앞으로 반드시 더 하락한다는 뜻은 아니다.
- T10Y3M의 역전·재정상화는 단기 매매 신호가 아니라 경기 사이클 배경 신호다.

## v0.3 해석 카드

`30D History` 탭에서 지표를 선택하면 상세 해석 카드가 함께 바뀝니다.

현재 적용 지표:

- `T10Y3M` — New York Fed의 10Y-3M Yield Curve 선행지표 모델을 중심 근거로 8칸 해석 카드 제공
- `HY OAS` — 신용스프레드의 절대수준·변화속도·역사적 위치를 구분해 읽는 8칸 해석 카드 제공

카드는 `뭘 측정하나`, `뭘 우선 보나`, `값 구간 감각`, `같이 볼 지표`, `흔한 오해`, `오를 때/내릴 때`, `실증 근거`, `근거의 한계` 순서입니다. 투자 결론이나 종합 위험 판단을 대신하지 않습니다.
