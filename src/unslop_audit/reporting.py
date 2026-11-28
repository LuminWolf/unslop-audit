"""报告输出。"""

import csv
import sys
from dataclasses import asdict

from .models import AuditReport, DIM_CN, Dimension


SEVERITY_ICON = {"critical": "[!]", "high": "[!]", "medium": "[~]", "low": "[-]"}
SEVERITY_LABEL = {
    "critical": "CRITICAL (一眼AI)",
    "high": "HIGH     (明显AI痕迹)",
    "medium": "MEDIUM   (需要留意)",
    "low": "LOW      (轻微问题)",
}


def build_report(files, findings):
    report = AuditReport(
        scanned_files=len(files),
        total_findings=len(findings),
        findings=[asdict(finding) for finding in findings],
    )
    for dimension in [item.value for item in Dimension]:
        count = sum(1 for finding in findings if finding.dimension == dimension)
        if count:
            report.by_dimension[dimension] = count
    for severity in ["critical", "high", "medium", "low"]:
        count = sum(1 for finding in findings if finding.severity == severity)
        if count:
            report.by_severity[severity] = count
    return report


def write_csv(findings, path):
    """把逐条问题写入 CSV，列固定为 path / line / problem / fix。"""

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(
        findings,
        key=lambda finding: (
            finding.file,
            finding.line,
            severity_order.get(finding.severity, 9),
        ),
    )
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "line", "problem", "fix"])
        for finding in ordered:
            writer.writerow(
                [finding.file, finding.line, finding.message, finding.suggestion]
            )


def print_findings(findings, show_fix_hints=False, stream=None):
    """逐行输出 `文件路径:行号: 问题`，保持 linter 风格。"""

    stream = stream or sys.stdout
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(
        findings,
        key=lambda finding: (
            finding.file,
            finding.line,
            severity_order.get(finding.severity, 9),
        ),
    )
    for finding in ordered:
        line = f"{finding.file}:{finding.line}: {finding.message}"
        if show_fix_hints and finding.suggestion:
            line += f"  [fix: {finding.suggestion}]"
        print(line, file=stream)


def print_summary(report, findings_raw, stream=None, csv_path=None):
    """把汇总输出到控制台（默认 stdout；JSON 模式下走 stderr）。"""

    stream = stream or sys.stdout
    sep, thin = "=" * 72, "-" * 72

    print("\n" + sep, file=stream)
    print("  SUMMARY", file=stream)
    print(sep, file=stream)
    print(f"  Scanned files : {report.scanned_files}", file=stream)
    print(f"  Total issues  : {report.total_findings}", file=stream)
    if csv_path:
        print(f"  CSV file      : {csv_path}", file=stream)

    print("\n  BY DIMENSION", file=stream)
    print(
        f"  {'Dimension':<22} {'CRIT':>5} {'HIGH':>5} {'MED':>5} {'LOW':>5} {'Total':>6}",
        file=stream,
    )
    print("  " + thin[:52], file=stream)
    for dimension in [item.value for item in Dimension]:
        items = [finding for finding in findings_raw if finding.dimension == dimension]
        if not items:
            continue
        critical_count = sum(1 for finding in items if finding.severity == "critical")
        high_count = sum(1 for finding in items if finding.severity == "high")
        medium_count = sum(1 for finding in items if finding.severity == "medium")
        low_count = sum(1 for finding in items if finding.severity == "low")
        label = "{} ({})".format(dimension, DIM_CN.get(dimension, ""))
        print(
            f"  {label:<22} {critical_count:>5} {high_count:>5} "
            f"{medium_count:>5} {low_count:>5} {len(items):>6}",
            file=stream,
        )

    print("\n  BY SEVERITY", file=stream)
    for severity in ["critical", "high", "medium", "low"]:
        count = report.by_severity.get(severity, 0)
        if count:
            print(
                f"  {SEVERITY_ICON[severity]} {SEVERITY_LABEL[severity]}  {count} found",
                file=stream,
            )

    affected_files = {finding.file for finding in findings_raw}
    print("\n" + sep, file=stream)
    print(
        f"  Total: {report.total_findings} issues across {len(affected_files)} files",
        file=stream,
    )
    print(sep + "\n", file=stream)


def print_report(
    report, findings_raw, show_fix_hints=False, stream=None, csv_path=None
):
    """兼容旧调用：文本报告先逐条问题，再输出汇总。"""

    print_findings(findings_raw, show_fix_hints=show_fix_hints, stream=stream)
    print_summary(report, findings_raw, stream=stream, csv_path=csv_path)
