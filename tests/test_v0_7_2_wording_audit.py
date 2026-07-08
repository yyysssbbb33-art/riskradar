from riskradar import telegram_client as TG
from riskradar.credit_timeline import (
    render_credit_timeline_markdown,
    render_past_credit_episodes_markdown,
)
from riskradar.rate_composition import render_markdown


def _rate_summary():
    return {
        "status": "ok",
        "primary": {
            "DGS30_change_bp": 20.0,
            "DFII30_change_bp": 8.0,
            "INFLCOMP30_change_bp": 12.0,
        },
        "context": {
            "DGS30_change_bp": 35.0,
            "DFII30_change_bp": 18.0,
            "INFLCOMP30_change_bp": 17.0,
        },
        "curve": {
            "text": "장·단기 금리가 함께 올랐고 장기가 더 올라 곡선이 가팔라졌습니다(bear steepening)."
        },
        "term_premium": {
            "status": "ok",
            "latest_value": 0.42,
            "change_1m_bp": -2.6,
            "direction": "하락",
        },
    }


def test_rate_panel_uses_plain_language_instead_of_formula_and_design_jargon():
    text = render_markdown(_rate_summary())
    assert "30년 미국 국채금리 변화 나눠보기" in text
    assert "전체 금리" in text
    assert "물가 영향을 뺀 금리" in text
    assert "일반 국채와 물가연동국채의 금리 차이" in text
    assert "물가 기대뿐 아니라 물가 위험과 채권 수요·공급 영향도" in text
    assert "10년 국채를 오래 보유할 때 요구되는 추가 보상" in text
    for banned in ("proxy", "별도 맥락", "교차 만기", "30Y 명목", "30Y 실질", "같은 만기 확인"):
        assert banned not in text


def test_telegram_rate_block_is_readable_without_equation_or_bp_jargon():
    text = "\n".join(TG._rate_composition_lines(_rate_summary()))
    assert "전체 금리: 0.20%p 상승" in text
    assert "물가 영향을 뺀 금리: 0.08%p 상승" in text
    assert "일반 국채와 물가연동국채의 금리 차이: 0.12%p 확대" in text
    assert "10년 국채를 오래 보유할 때 시장이 요구하는 추가 보상(모형 추정)은 최근 약 1개월 0.03%p 낮아졌습니다" in text
    for banned in ("30Y 명목", "30Y 실질", "물가보상 proxy", "별도 맥락", "Term Premium 별도"):
        assert banned not in text


def test_credit_timeline_uses_plain_change_record_wording():
    data = {
        "available": True,
        "days": 90,
        "window_start": "2026-01-01",
        "window_end": "2026-03-31",
        "events": [{
            "date": "2026-03-03",
            "node": "HY",
            "node_name": "신용등급 낮은 기업의 회사채",
            "event_type": "confirmed",
            "text": "부담 상승 확인",
            "state_label": "상승 확인",
            "candidate_start": "2026-03-01",
        }],
    }
    text = render_credit_timeline_markdown(data)
    assert "최근 90일 기업 신용 변화" in text
    assert "상승 확인 전 조짐: 2026-03-01부터" in text
    assert "다음 움직임을 예측하지 않습니다" in text
    for banned in ("신용 타임라인", "확정 전 후보 신호", "독립 사건"):
        assert banned not in text


def test_past_credit_records_do_not_use_episode_or_reconstruction_jargon():
    data = {
        "past_episodes": [{
            "started_at": "2026-01-01",
            "display_end_at": "2026-01-20",
            "state_label": "휴면",
            "participant_names": ["신용등급 낮은 기업의 회사채"],
            "duration_days": 20,
            "prior_residual_names": [],
        }]
    }
    text = render_past_credit_episodes_markdown(data)
    assert "지난 기업 신용 변화 기록" in text
    assert "변화가 확인된 시장" in text
    assert "기록된 기간" in text
    assert "현재 제공되는 공식 자료로 다시 계산한 기록" in text
    for banned in ("과거 에피소드", "재구성한 기록", "관찰된 기간"):
        assert banned not in text
