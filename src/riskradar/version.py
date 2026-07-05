"""RiskRadar 버전 단일 소스.

- 제품 버전은 여기 하나만 고친다.
- pyproject / README / 앱 하단 표기가 이 값을 참조하도록 한다.
"""
from __future__ import annotations

__version__ = "0.4.0"

# 참고용 릴리스 라인
#   0.1.x  단일 지표 계기판
#   0.3.x  해석 카드(T10Y3M / HY OAS)
#   0.4.0  보조지표 3개(원인 확인용) + 방향 판정   <- 현재
#   0.4.x  3축 엔진 / 조합·조건부 해석 / 오늘의 해석 UI (예정)
