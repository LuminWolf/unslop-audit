import json
import sys
from dataclasses import asdict
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from unslop_audit import (
    SUPPORTED_EXTS,
    AuditReport,
    DIM_CN,
    Dimension,
    EMOJI_RE,
    Finding,
    RULES,
    Severity,
    build_args,
    build_report,
    collect_files,
    configure_utf8,
    print_report,
    print_summary,
    Scanner,
    write_csv,
)

__all__ = [
    "DIM_CN",
    "EMOJI_RE",
    "RULES",
    "AuditReport",
    "Dimension",
    "Finding",
    "Scanner",
    "Severity",
    "build_args",
    "build_report",
    "collect_files",
    "main",
    "print_report",
]


def main(argv=None):
    configure_utf8()
    args = build_args(argv)

    files = collect_files(args.target)
    if not files:
        print(
            "No scannable files found. Supported: " + ", ".join(sorted(SUPPORTED_EXTS)),
            file=sys.stderr,
        )
        return 1

    scanner = Scanner()
    all_findings = []
    for file_path in files:
        all_findings.extend(scanner.scan_file(file_path))
    report = build_report(files, all_findings)

    write_csv(all_findings, args.csv)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        print_summary(report, all_findings, stream=sys.stderr, csv_path=args.csv)
    else:
        print_summary(report, all_findings, csv_path=args.csv)

    if args.fail_on:
        severity_order = ["low", "medium", "high", "critical"]
        blocking_index = severity_order.index(args.fail_on)
        blocking = [
            finding
            for finding in all_findings
            if severity_order.index(finding.severity) >= blocking_index
        ]
        # 走 stderr，避免 --json 模式把 PASS/FAIL 混进 JSON。
        if blocking:
            print(
                f"FAIL: {len(blocking)} issues >= {args.fail_on}", file=sys.stderr
            )
            return 2
        print(f"PASS: no issues >= {args.fail_on}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
