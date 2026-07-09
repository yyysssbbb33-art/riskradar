from __future__ import annotations

from pathlib import Path

from tests import synth
from riskradar import pipeline
from riskradar.today_view import render_today_summary_markdown
from riskradar.ui import _board_df, _signal_matrix_detail_df, _signal_matrix_df


def test_current_and_matrix_first_views_are_compact_but_detail_is_preserved():
    matrix = pipeline.compute_all(synth.make_raw_by_key(n=1200))["signal_matrix"]

    board = _board_df(matrix)
    first_matrix = _signal_matrix_df(matrix)
    detail = _signal_matrix_detail_df(matrix)

    for table in (board, first_matrix):
        assert "지금 뜻" not in table.columns
        assert "왜 이렇게 표시됐나" not in table.columns

    assert list(first_matrix.columns) == ["지표", "현재", "최근 변화"]
    assert list(detail.columns) == ["지표", "과거 위치", "관측일"]


def test_today_summary_keeps_only_core_sections_and_points_to_full_detail():
    summary = render_today_summary_markdown(
        {
            "axes": {
                "changed_axes": ["변동성·신용"],
                "base_axes": ["경기 흐름", "금리 움직임"],
                "changed_count": 1,
            },
            "readings": [
                {
                    "label": "테스트 조합",
                    "observed": "한 영역만 움직였습니다.",
                    "explanations": [{"id": "x", "text": "한 가지 설명입니다."}],
                    "supported_ids": ["x"],
                }
            ],
        }
    )

    assert "# 오늘의 해석" in summary
    assert "시장 전체" in summary
    assert "눈에 띄는 조합" in summary
    assert "신용·금리 탭" in summary
    assert "결과가 달라지면" not in summary


def test_non_guide_tabs_keep_reference_content_behind_short_closed_accordions():
    source = Path(__file__).parents[1] / "src" / "riskradar" / "ui.py"
    text = source.read_text(encoding="utf-8")

    expected = [
        'with gr.Accordion("관리·진단", open=False)',
        'with gr.Accordion("왜 이렇게 봤나", open=False, elem_classes="rr-detail-accordion")',
        'with gr.Accordion("금리 설명·주의사항", open=False, elem_classes="rr-detail-accordion")',
        'with gr.Accordion("지난 30일 읽는 법", open=False)',
        'with gr.Accordion("데이터 설명·주의사항", open=False)',
        '## 날짜별 지표 보기',
        'with gr.Accordion("표 읽는 법", open=False)',
        'with gr.Accordion("차트 읽는 법", open=False)',
        'with gr.Accordion("함께 볼 지표 수집 상태", open=False)',
    ]
    for phrase in expected:
        assert phrase in text

    guide_start = text.index('with gr.Tab("설명")')
    assert 'gr.Markdown(GUIDE_INTRO)' in text[guide_start:]


def test_v061_ui_accepts_v060_data_without_false_version_warning():
    from riskradar.ui import _is_compatible_data_code_version

    assert _is_compatible_data_code_version("0.6.0", "0.6.1") is True
    assert _is_compatible_data_code_version("0.6.1", "0.6.1") is True
    assert _is_compatible_data_code_version("0.4.9", "0.6.1") is False
