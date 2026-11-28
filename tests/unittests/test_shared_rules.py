"""读取 tests/shared/cases 的共享用例，执行 Python 侧 html/css surface。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from unslop_audit import Scanner  # noqa: E402

CASES_DIR = ROOT / "tests" / "shared" / "cases"
PYTHON_SURFACES = {"html", "css"}


def load_cases():
    for path in sorted(CASES_DIR.glob("*.json")):
        yield path.name, json.loads(path.read_text(encoding="utf-8"))


class SharedRuleTests(unittest.TestCase):
    def test_shared_html_css_cases(self):
        scanner = Scanner()
        with tempfile.TemporaryDirectory() as temporary:
            for filename, fixture in load_cases():
                rule = fixture["rule"]
                for case in fixture["cases"]:
                    if case["surface"] not in PYTHON_SURFACES:
                        continue
                    with self.subTest(fixture=filename, case=case["name"]):
                        filename_in_case = case.get("filename") or f"case.{case['surface']}"
                        path = Path(temporary) / filename_in_case
                        path.write_text(case["source"], encoding="utf-8")

                        hits = [
                            finding
                            for finding in scanner.scan_file(str(path))
                            if finding.pattern == rule
                        ]
                        expected = [
                            item
                            for item in case["expect"]
                            if item["rule"] in {rule, f"slop-audit/{rule}"}
                        ]
                        self.assertEqual(
                            len(hits),
                            len(expected),
                            f"{rule}/{case['name']}: {len(hits)} hits, expected {len(expected)}",
                        )
                        actual_lines = sorted(finding.line for finding in hits)
                        expected_lines = sorted(item["line"] for item in expected)
                        self.assertEqual(actual_lines, expected_lines)


if __name__ == "__main__":
    unittest.main()
