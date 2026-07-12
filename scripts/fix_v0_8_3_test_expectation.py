from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "src/riskradar/relationship_guide.py"
text = path.read_text(encoding="utf-8")
old = "| HY·BBB 상승 | BBB 회사채의 국채 대비 추가 금리도 함께 확대됩니다. |"
new = "| HY·BBB 상승 | BBB 기업 회사채의 국채 대비 추가 금리도 함께 확대됩니다. |"
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("BBB OAS 안내 문구를 찾을 수 없습니다.")
path.write_text(text, encoding="utf-8")

failure_report = root / "HOTFIX_TEST_FAILURE.txt"
if failure_report.exists():
    failure_report.unlink()

Path(__file__).unlink()
