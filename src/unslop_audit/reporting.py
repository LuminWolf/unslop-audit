"""评分与报告输出。"""

import csv
import sys
from dataclasses import asdict

from .models import AuditReport, DIM_CN, Dimension


SEVERITY_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 1}

SEVERITY_ICON = {"critical": "[!]", "high": "[!]", "medium": "[~]", "low": "[-]"}
SEVERITY_LABEL = {
    "critical": "CRITICAL (一眼AI)",
    "high": "HIGH     (明显AI痕迹)",
    "medium": "MEDIUM   (需要留意)",
    "low": "LOW      (轻微问题)",
}


def compute_score(findings, file_count):
    if file_count == 0:
        return 100
    penalty = sum(SEVERITY_WEIGHT.get(finding.severity, 1) for finding in findings)
    return max(0, min(100, int(100 - penalty / max(file_count, 1) * 3)))


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
    report.score = compute_score(findings, len(files))
    return report


def write_csv(findings, path):
    """把逐条问题写入 CSV，列固定为 path / line / problem / fix。"""

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(findings, key=lambda finding: (
        finding.file, finding.line, severity_order.get(finding.severity, 9)
    ))
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "line", "problem", "fix"])
        for finding in ordered:
            writer.writerow([
                finding.file, finding.line, finding.message, finding.suggestion
            ])


def print_findings(findings, show_fix_hints=False, stream=None):
    """逐行输出 `文件路径:行号: 问题`，保持 linter 风格。"""

    stream = stream or sys.stdout
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(findings, key=lambda finding: (
        finding.file, finding.line, severity_order.get(finding.severity, 9)
    ))
    for finding in ordered:
        line = "%s:%d: %s" % (finding.file, finding.line, finding.message)
        if show_fix_hints and finding.suggestion:
            line += "  [fix: %s]" % finding.suggestion
        print(line, file=stream)


def print_summary(report, findings_raw, stream=None, csv_path=None):
    """把汇总输出到控制台（默认 stdout；JSON 模式下走 stderr）。"""

    stream = stream or sys.stdout
    sep, thin = "=" * 72, "-" * 72

    print("\n" + sep, file=stream)
    print("  SUMMARY", file=stream)
    print(sep, file=stream)
    print("  Scanned files : %d" % report.scanned_files, file=stream)
    print("  Total issues  : %d" % report.total_findings, file=stream)
    if csv_path:
        print("  CSV file      : %s" % csv_path, file=stream)
    if report.score < 40:
        grade = "HEAVY AI flavor"
    elif report.score < 60:
        grade = "Noticeable AI traces"
    elif report.score < 80:
        grade = "Room for improvement"
    else:
        grade = "Fairly restrained"
    print("  Design score  : %d/100  [%s]" % (report.score, grade), file=stream)

    print("\n  BY DIMENSION", file=stream)
    print("  %-22s %5s %5s %5s %5s %6s" % (
        "Dimension", "CRIT", "HIGH", "MED", "LOW", "Total"), file=stream)
    print("  " + thin[:52], file=stream)
    for dimension in [item.value for item in Dimension]:
        items = [finding for finding in findings_raw if finding.dimension == dimension]
        if not items:
            continue
        critical_count = sum(1 for finding in items if finding.severity == "critical")
        high_count = sum(1 for finding in items if finding.severity == "high")
        medium_count = sum(1 for finding in items if finding.severity == "medium")
        low_count = sum(1 for finding in items if finding.severity == "low")
        label = "%s (%s)" % (dimension, DIM_CN.get(dimension, ""))
        print("  %-22s %5d %5d %5d %5d %6d" % (
            label, critical_count, high_count, medium_count, low_count, len(items)
        ), file=stream)

    print("\n  BY SEVERITY", file=stream)
    for severity in ["critical", "high", "medium", "low"]:
        count = report.by_severity.get(severity, 0)
        if count:
            print("  %s %s  %d found" % (
                SEVERITY_ICON[severity], SEVERITY_LABEL[severity], count
            ), file=stream)

    affected_files = {finding.file for finding in findings_raw}
    print("\n" + sep, file=stream)
    print("  Total: %d issues across %d files" % (
        report.total_findings, len(affected_files)
    ), file=stream)
    print(sep + "\n", file=stream)


def print_report(report, findings_raw, show_fix_hints=False, stream=None, csv_path=None):
    """兼容旧调用：文本报告先逐条问题，再输出汇总。"""

    print_findings(findings_raw, show_fix_hints=show_fix_hints, stream=stream)
    print_summary(report, findings_raw, stream=stream, csv_path=csv_path)
