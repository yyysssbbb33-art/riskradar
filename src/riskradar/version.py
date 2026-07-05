"""RiskRadar 버전 단일 소스.

- 제품 버전은 여기 하나만 고친다.
- pyproject / README / 앱 하단 표기가 이 값을 참조하도록 한다.
"""
from __future__ import annotations

__version__ = "0.4.1"

# 참고용 릴리스 라인
#   0.1.x  단일 지표 계기판
#   0.3.x  해석 카드(T10Y3M / HY OAS)
#   0.4.0  보조지표 3개 + 3축 + 초기 조건부 해석
#   0.4.1  쉬운 UI + 6개 상세카드 + 조합 해석 확장 + 반대 증거/불확실성   <- 현재
