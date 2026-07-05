from __future__ import annotations

import pandas as pd

from riskradar.today_view import render_today_markdown


def test_today_view_shows_alternative_outcome_branches():
    dq = {
        "axes": {},
        "readings": [
            {
                "combo_id": "demo",
                "label": "예시 조합",
                "observed": "현재 관찰된 사실",
                "explanations": [{"id": "a", "text": "설명 A"}],
                "checks": [
                    {
                        "key": "BREAKEVEN",
                        "label": "10년 기대인플레이션",
                        "direction": "상승",
                        "text": "현재 상승 해석",
                        "freshness": "normal",
                        "branches": {
                            "상승": "상승이면 이렇게 해석",
                            "하락": "하락이면 이렇게 해석",
                            "보합": "보합이면 이렇게 해석",
                        },
                    }
                ],
                "supported_ids": ["a"],
                "weakened_ids": [],
                "conflict": "",
                "uncertainty": "남은 불확실성",
            }
        ],
    }
    md = render_today_markdown(dq, pd.DataFrame())
    assert "현재 상승 해석" in md
    assert "결과가 달라지면" in md
    assert "하락이면 이렇게 해석" in md
    assert "뚜렷한 움직임이 없으면 이렇게 해석" in md
    assert "상승이면 이렇게 해석" not in md  # 현재 branch는 위의 현재 결과에서 이미 표시
