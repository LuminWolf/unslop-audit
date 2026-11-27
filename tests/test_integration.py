#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成测试：对 tests/sample_slop.html 与 tests/sample_clean.html 做整页审计。

sample_slop.html 覆盖全部 49 条规则（48 条声明规则 + emoji-as-icon 兜底），
sample_clean.html 为每条规则提供一处合规写法（同样覆盖 49 条）且必须零命中。
通过 CLI 子进程验证 JSON/CSV/--fail-on 门禁，确保报告字段、维度顺序、
严重级别与 stdout 纯净性不被破坏。

运行：
    python3 tests/test_integration.py
"""

import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import atexit
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIT_SCRIPT = ROOT / "ai_ui_audit.py"
SLOP = HERE / "sample_slop.html"
CLEAN = HERE / "sample_clean.html"

_TMP = tempfile.mkdtemp(prefix="unslop-integration-test-")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

_spec = importlib.util.spec_from_file_location("ai_ui_audit_integration_under_test", str(AUDIT_SCRIPT))
AUDIT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AUDIT)


def _subprocess_env():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(target, *extra):
    csv_path = Path(_TMP) / ("%s.csv" % target.stem)
    command = [
        sys.executable, str(AUDIT_SCRIPT), str(target),
        "--csv", str(csv_path), *extra,
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        cwd=str(ROOT), env=_subprocess_env(),
    )
    return result, csv_path


class IntegrationTests(unittest.TestCase):

    def test_01_slop_covers_all_rules(self):
        """sample_slop.html 直接扫描必须覆盖全部声明规则 + emoji 兜底。"""

        declared = {rule.name for rule in AUDIT.RULES} | {"emoji-as-icon"}
        hits = {f.pattern for f in AUDIT.scan_file(str(SLOP))}
        self.assertEqual(declared - hits, set(),
                         "sample_slop.html 未触发: %s" % sorted(declared - hits))

    def test_02_clean_has_zero_findings(self):
        """sample_clean.html 直接扫描必须零命中。"""

        findings = AUDIT.scan_file(str(CLEAN))
        self.assertEqual(findings, [],
                         "sample_clean.html 意外命中: %s" %
                         ", ".join("%s:%d" % (f.pattern, f.line) for f in findings))

    def test_02b_clean_covers_all_rules(self):
        """sample_clean.html 必须为每条规则提供一处合规写法。"""

        declared = {rule.name for rule in AUDIT.RULES} | {"emoji-as-icon"}
        source = CLEAN.read_text(encoding="utf-8")
        marked = set(re.findall(r"rule:\s*([\w-]+)", source))
        self.assertEqual(declared - marked, set(),
                         "sample_clean.html 缺少合规写法: %s" %
                         sorted(declared - marked))
        self.assertEqual(marked - declared, set(),
                         "sample_clean.html 含未知规则标记: %s" %
                         sorted(marked - declared))

    def test_03_slop_cli_json_and_score(self):
        """脏页 CLI：exit 0、纯 JSON、低分、维度齐全。"""

        result, _ = run_cli(SLOP, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)  # 纯 JSON，无 PASS/FAIL 污染
        self.assertGreater(report["total_findings"], 0)
        self.assertLess(report["score"], 40)
        self.assertEqual(set(report["by_dimension"]),
                         {d.value for d in AUDIT.Dimension})

    def test_04_clean_cli_json_and_score(self):
        """干净页 CLI：exit 0、纯 JSON、零 finding、满分。"""

        result, _ = run_cli(CLEAN, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["total_findings"], 0)
        self.assertEqual(report["score"], 100)

    def test_05_fail_on_gate(self):
        """--fail-on 门禁：脏页 exit 2，干净页 exit 0，stdout 始终纯 JSON。"""

        dirty, _ = run_cli(SLOP, "--json", "--fail-on", "high")
        self.assertEqual(dirty.returncode, 2)
        self.assertIn("FAIL", dirty.stderr)
        self.assertIsInstance(json.loads(dirty.stdout), dict)

        clean, _ = run_cli(CLEAN, "--json", "--fail-on", "high")
        self.assertEqual(clean.returncode, 0)
        self.assertIn("PASS", clean.stderr)
        self.assertIsInstance(json.loads(clean.stdout), dict)

    def test_06_csv_columns_and_rows(self):
        """CSV 输出列固定，行数与 JSON finding 数一致，字段非空。"""

        result, csv_path = run_cli(SLOP, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)

        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(list(rows[0]), ["path", "line", "problem", "fix"])
        self.assertEqual(len(rows), report["total_findings"])
        self.assertTrue(all(row["path"].endswith("sample_slop.html") for row in rows))
        self.assertTrue(all(row["line"].isdigit() for row in rows))
        self.assertTrue(all(row["problem"] and row["fix"] for row in rows))

    def test_07_line_numbers_in_range(self):
        """finding 行号必须落在 sample_slop.html 的实际行数内。"""

        total_lines = len(SLOP.read_text(encoding="utf-8").splitlines())
        for finding in AUDIT.scan_file(str(SLOP)):
            self.assertGreaterEqual(finding.line, 1)
            self.assertLessEqual(finding.line, total_lines,
                                 "%s 行号 %d 超出 %d" %
                                 (finding.pattern, finding.line, total_lines))

    def test_08_severity_and_dimension_totals(self):
        """严重级别与维度分桶之和等于 finding 总数，统计不虚高。"""

        result, _ = run_cli(SLOP, "--json")
        report = json.loads(result.stdout)
        total = report["total_findings"]
        self.assertEqual(sum(report["by_dimension"].values()), total)
        self.assertEqual(sum(report["by_severity"].values()), total)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
