from __future__ import annotations

import re
import tomllib
from pathlib import Path

import riskradar.ui as ui
from riskradar.version import __version__

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_version_is_consistent_across_runtime_package_and_readme():
    pyproject = tomllib.loads(_read("pyproject.toml"))
    assert pyproject["project"]["version"] == __version__

    readme = _read("README.md")
    match = re.search(r"^# RiskRadar v([^ ]+) ", readme, re.MULTILINE)
    assert match, "README의 현재 버전 제목을 찾을 수 없습니다."
    assert match.group(1) == __version__
    assert f"## v{__version__} " in readme


def test_current_ui_version_has_explicit_cache_compatibility():
    assert __version__ in ui._UI_DATA_COMPATIBLE_VERSIONS
    compatible = ui._UI_DATA_COMPATIBLE_VERSIONS[__version__]
    assert __version__ in compatible
    assert "0.8.2" in compatible
    assert ui._is_compatible_data_code_version("0.8.2", __version__)


def test_release_does_not_ship_temporary_handoff_files():
    assert not (ROOT / "CODEX_HANDOFF_v0_8_2.md").exists()
    assert not list(ROOT.glob("CODEX_HANDOFF*.md"))


def test_active_ui_uses_current_navigation_terms():
    source = _read("src/riskradar/ui.py")
    assert 'with gr.Tab("현황")' in source
    assert 'with gr.Tab("오늘")' not in source
    assert "## 금리곡선" not in source
    assert "날짜별 지표 보기" not in source


def test_active_user_copy_does_not_restore_removed_credit_wording():
    source = "\n".join(
        _read(path)
        for path in (
            "src/riskradar/credit_timeline.py",
            "src/riskradar/overview_view.py",
            "src/riskradar/rate_view.py",
            "src/riskradar/rate_composition.py",
            "src/riskradar/relationship_guide.py",
        )
    )
    assert "이전 고점 돌파" not in source


def test_relationship_guide_treats_oas_as_spread_not_absolute_yield():
    guide = _read("src/riskradar/relationship_guide.py")
    forbidden = (
        "HY도 상승 | 낮은 등급 기업의 회사채 금리와 조달비용도 함께 올라갑니다",
        "HY만 상승 | 낮은 등급 기업의 회사채 금리 상승이 두드러집니다",
        "HY·BBB 상승 | BBB 기업의 회사채 금리와 조달비용도 함께 올라갑니다",
        "HY·BBB·A 상승 | 우량 기업의 회사채 금리까지 같이 올라갑니다",
    )
    for phrase in forbidden:
        assert phrase not in guide
    assert "국채 대비 추가 금리" in guide
    assert "절대 금리" in guide
    assert "단기·장기 금리 관계" in guide


def test_refresh_workflow_keeps_manual_and_version_release_triggers():
    workflow = _read(".github/workflows/refresh.yml")
    assert "workflow_dispatch" in workflow
    assert "branches:" in workflow and "main" in workflow
    assert "src/riskradar/version.py" in workflow
