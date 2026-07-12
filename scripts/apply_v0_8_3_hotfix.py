from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


# 1) Product version sources.
pyproject = read("pyproject.toml")
pyproject = replace_once(
    pyproject,
    'version = "0.8.2"',
    'version = "0.8.3"',
    label="pyproject version",
)
write("pyproject.toml", pyproject)

version_py = read("src/riskradar/version.py")
version_py = replace_once(
    version_py,
    '__version__ = "0.8.2"',
    '__version__ = "0.8.3"',
    label="runtime version",
)
version_py = replace_once(
    version_py,
    "#   0.8.2  사용자 문구 단일화 + 직접 결과 설명 + Visual Polish   <- 현재",
    "#   0.8.1  사용자 문구 단일화 + 직접 결과 설명 + Visual Polish\n"
    "#   0.8.2  현황 중심 UI + 탭별 정보 구조 정리\n"
    "#   0.8.3  README·OAS 표현·UI 데이터 호환·릴리스 검사 핫픽스   <- 현재",
    label="release line",
)
write("src/riskradar/version.py", version_py)

# 2) README: preserve historical notes but make the current release and current UI accurate.
readme = read("README.md")
readme = replace_once(
    readme,
    "# RiskRadar v0.8.1 — 미국 시장 흐름 신호판",
    "# RiskRadar v0.8.3 — 미국 시장 흐름 신호판",
    label="README title",
)
release_notes = """## v0.8.3 릴리스 일관성 핫픽스

v0.8.3은 v0.8.2의 화면 구조와 판정 로직을 유지하면서, 릴리스 과정에서 빠진 문서·표현·호환 등록을 바로잡고 같은 누락이 다시 병합되지 않도록 자동 검사를 추가합니다.

- README를 현재 `현황 / 신용 / 금리 / 흐름 / 비교 / 설명` 구조와 v0.8.3 기준으로 갱신
- OAS를 회사채의 절대 금리나 실제 조달비용과 동일시하지 않고 **같은 만기 국채 대비 추가 금리**로 표현
- `금리곡선` 대신 기본 화면과 안내에서 **단기·장기 금리 관계**를 우선 사용
- v0.8.2·v0.8.3 UI가 직전 호환 캐시를 읽도록 데이터 버전 호환 목록 보완
- 버전·README·호환 목록·임시 전달 파일·금지 문구를 검사하는 릴리스 일관성 테스트 추가
- main 대상 PR에서 전체 pytest와 Gradio `Blocks` 생성 smoke를 자동 실행하는 GitHub Actions 추가

수집, threshold, 핵심 상태 규칙, 신용 에피소드 전이, 30Y 계산, 캐시 발행, decision snapshot·diff·ledger, prune, Telegram 조건은 변경하지 않습니다.

## v0.8.2 현황 중심 UI

v0.8.2는 새 시장 신호나 새 계산을 추가하지 않고, 핵심 상태를 더 빨리 읽도록 화면의 정보 순서와 한국어 표현을 정리했습니다.

- 첫 탭을 `오늘`에서 **`현황`**으로 바꾸고 `자료 기준일 → 현황 한눈에 → 시장 해석 → 주요 지표 → 최근 상태 변화 → 판정 근거` 순서로 재구성
- 기업 신용·장기금리·시장 변동성을 대형 카드로 배치하고 정상 카드도 선명하게 표시
- 신용 탭은 HY·BBB·A·CP 2×2 구조와 최근 90일 변화 기록을 유지하되 중복 설명을 축소
- 금리 탭을 `금리 현황 → 단기·장기 금리 관계 → 30Y 금리 변화 나눠보기 → 장기금리 참고` 순서로 정리
- 흐름 탭은 지난 30일의 시간 경로와 선택 지표 차트에 집중
- 비교 탭은 최신 관측일 차이를 안내하고 `같은 날짜로 비교`를 명확히 표시
- 설명 탭은 지표 선택기를 먼저 배치하고 상세 설명의 중복을 줄임

"""
readme = replace_once(
    readme,
    "## v0.8.1 표현·디자인 정리",
    release_notes + "## v0.8.1 표현·디자인 정리",
    label="README release notes",
)
old_flow = """## 지난 30일 흐름

핵심 6개의 과거 point-in-time 경로를 현재 규칙으로 재구성합니다.

- 한 달 사이 어떻게 달라졌나
- 한때 크게 움직였다가 되돌아온 변화
- 아직 남아 있는 변화
- 새 변화가 처음 확인된 날짜
- 2년·30년 금리의 엇갈림
- 현재 기업 신용 범위·지속 상태

엔진 내부는 최대 90개 관측치를 사용하지만 사용자 월간 화면은 최근 30일을 보여줍니다.
"""
new_flow = """## 지난 30일 요약과 흐름

핵심 6개의 과거 point-in-time 경로를 현재 규칙으로 재구성합니다.

- 한 달 사이 어떻게 달라졌나
- 한때 크게 움직였다가 되돌아온 변화
- 현재까지 남아 있는 추세
- 선택 지표의 지난 30일 값 변화
- 접어서 확인하는 현재 제공 전체 기간 흐름과 표

사용자 화면은 시간 경로를 정리할 뿐, 어느 지표가 원인이거나 먼저 움직였다고 주장하지 않습니다.
"""
readme = replace_once(readme, old_flow, new_flow, label="README flow section")
old_tabs = """## 화면 탭

1. **한눈에 보기** — 오늘 한 줄, 최근 갱신 변화, 남은 변화, 다음 확인, 모바일 핵심 카드
2. **기업 신용** — HY·BBB·A·CP 범위 지도와 범위·지속 상세
   - 최근 90일 기업 신용 변화
   - 현재 공식 자료 범위에서 재구성한 지난 기업 신용 변화 기록
3. **흐름과 차트** — 지난 30일 과정 + 선택 지표 원자료 차트
4. **비교** — 전체 지표 비교 + 같은 날짜 비교
5. **지표 설명** — 14개 상세 가이드 + 지표를 같이 보는 법

운영 정보는 독립 탭이 아니라 상단 `데이터 상태·운영 진단 보기` 아코디언에서 확인합니다.
"""
new_tabs = """## 화면 탭

1. **현황** — 자료 기준일, 핵심 3카드, 시장 해석, 주요 지표, 최근 상태 변화, 판정 근거
2. **신용** — HY·BBB·A·CP 2×2, 최근 90일 신용 변화, 지난 변화, 현재 상태 상세
3. **금리** — 금리 현황, 단기·장기 금리 관계, 30Y 금리 변화 나눠보기, 장기금리 참고
4. **흐름** — 지난 30일 요약, 선택 지표의 30일 차트, 접어서 보는 전체 기간·표·설명
5. **비교** — 최신 관측값 비교와 실제 공통 관측일 기준 같은 날짜 비교
6. **설명** — 지표 선택형 상세 설명, RiskRadar 읽는 법, 지표를 함께 보는 법

운영 정보는 독립 탭이 아니라 상단 `관리·진단` 아코디언에서 확인합니다.
"""
readme = replace_once(readme, old_tabs, new_tabs, label="README tabs")
readme = replace_once(
    readme,
    "cron-job.org\n  → GitHub workflow_dispatch",
    "cron-job.org 수동 호출 또는 main의 version.py 변경\n  → GitHub Actions refresh",
    label="README pipeline trigger",
)
write("README.md", readme)

# 3) User-facing relationship guide: OAS is a spread, not an absolute yield.
guide = read("src/riskradar/relationship_guide.py")
replacements = {
    "| HY도 상승 | 낮은 등급 기업의 회사채 금리와 조달비용도 함께 올라갑니다. |":
        "| HY도 상승 | 낮은 등급 기업 회사채의 국채 대비 추가 금리도 함께 확대됩니다. |",
    "| BBB·A까지 상승 | 더 높은 신용등급 기업의 조달비용까지 올라갑니다. |":
        "| BBB·A까지 상승 | 더 높은 신용등급 회사채의 국채 대비 추가 금리까지 확대됩니다. |",
    "| HY만 상승 | 낮은 등급 기업의 회사채 금리 상승이 두드러집니다. |":
        "| HY만 상승 | 낮은 등급 기업 회사채의 국채 대비 추가 금리 확대가 두드러집니다. |",
    "| HY·BBB 상승 | BBB 기업의 회사채 금리와 조달비용도 함께 올라갑니다. |":
        "| HY·BBB 상승 | BBB 회사채의 국채 대비 추가 금리도 함께 확대됩니다. |",
    "| HY·BBB·A 상승 | 우량 기업의 회사채 금리까지 같이 올라갑니다. |":
        "| HY·BBB·A 상승 | A등급 회사채의 국채 대비 추가 금리까지 함께 확대됩니다. |",
    "### 2Y와 30Y": "### 단기·장기 금리 관계(2Y와 30Y)",
    "| 둘 다 상승, 30Y가 더 큼 | 금리곡선이 가팔라집니다. |":
        "| 둘 다 상승, 30Y가 더 큼 | 30Y와 2Y의 금리 차이가 확대됩니다. |",
    "| 둘 다 상승, 2Y가 더 큼 | 금리곡선이 평평해집니다. |":
        "| 둘 다 상승, 2Y가 더 큼 | 30Y와 2Y의 금리 차이가 축소됩니다. |",
    "| 둘 다 하락, 2Y가 더 큼 | 금리곡선이 가팔라집니다. |":
        "| 둘 다 하락, 2Y가 더 큼 | 30Y와 2Y의 금리 차이가 확대됩니다. |",
    "| 둘 다 하락, 30Y가 더 큼 | 금리곡선이 평평해집니다. |":
        "| 둘 다 하락, 30Y가 더 큼 | 30Y와 2Y의 금리 차이가 축소됩니다. |",
    "`bear steepening` 같은 이름은 가격 움직임을 나타낼 뿐, 원인을 자동으로 뜻하지 않습니다.":
        "이 표는 두 만기의 상대 움직임만 설명하며, 변화의 원인을 자동으로 뜻하지 않습니다.",
}
for old, new in replacements.items():
    guide = replace_once(guide, old, new, label=f"relationship guide: {old[:28]}")
anchor = "> 같은 시기에 움직였다는 뜻이지, 어느 시장이 먼저 원인이었다는 뜻은 아닙니다."
note = anchor + "\n\n> OAS 상승만으로 회사채의 절대 금리나 기업의 실제 조달비용이 반드시 올랐다고 단정하지 않습니다. 같은 만기의 국채금리 움직임도 함께 봐야 합니다."
guide = replace_once(guide, anchor, note, label="OAS caution")
write("src/riskradar/relationship_guide.py", guide)

# 4) UI-only cache compatibility for 0.8.2 and 0.8.3.
ui = read("src/riskradar/ui.py")
compat_old = '    "0.8.1": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1"},\n}'
compat_new = '''    "0.8.1": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1"},
    # v0.8.2와 v0.8.3은 UI·문구·릴리스 일관성 패치이며 화면용 캐시 schema는 그대로다.
    "0.8.2": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2"},
    "0.8.3": {"0.7.0", "0.7.1", "0.7.2", "0.7.3", "0.7.4", "0.8.0", "0.8.1", "0.8.2", "0.8.3"},
}'''
ui = replace_once(ui, compat_old, compat_new, label="UI compatibility map")
write("src/riskradar/ui.py", ui)

# 5) Release consistency tests.
test_text = r'''from __future__ import annotations

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
'''
write("tests/test_release_consistency.py", test_text)

# 6) Human checklist complements the automated gate.
pr_template = """## 변경 요약

- 

## 검증

- [ ] `pytest -q` 통과
- [ ] Gradio `Blocks` 생성 smoke 통과
- [ ] 제품 버전이 `version.py`, `pyproject.toml`, README에서 일치
- [ ] 현재 UI 버전이 데이터 호환 목록에 등록됨
- [ ] README의 최신 화면 탭·용어가 실제 UI와 일치
- [ ] OAS를 절대 회사채금리나 실제 조달비용으로 단정하지 않음
- [ ] 임시 Codex 전달 파일이 릴리스에 포함되지 않음
- [ ] UI 변경이면 배포 후 데스크톱·모바일 화면 확인

## 보호 로직

- [ ] 수집·threshold·핵심 상태·신용 에피소드·캐시 발행·decision ledger·Telegram 조건을 바꾸지 않았거나, 변경 이유와 검증을 명시함
"""
write(".github/pull_request_template.md", pr_template)

# Remove this one-time script from the resulting hotfix commit.
Path(__file__).unlink()
