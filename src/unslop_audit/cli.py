"""命令行参数解析与 UTF-8 配置。

执行入口不放在包内：main() 只写在根目录的 ai_ui_audit.py 脚本里。
"""

import argparse
import sys


DEFAULT_CSV = "ai_ui_audit_report.csv"


def configure_utf8():
    """把 stdout/stderr 显式切到 UTF-8，避免 Windows 默认 GBK 编码失败。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def build_args(argv=None):
    parser = argparse.ArgumentParser(
        description="AI UI Classic Problems Auditor (unslop-aligned) — "
                    "detect AI-generated UI patterns")
    parser.add_argument("target", help="File or directory to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--csv", nargs="?", const=DEFAULT_CSV, default=DEFAULT_CSV, metavar="PATH",
        help="Write findings to CSV (default: ai_ui_audit_report.csv)",
    )
    parser.add_argument("--fix-hints", action="store_true",
                        help="Deprecated: fix is always written to the CSV")
    parser.add_argument("--fail-on", choices=["critical", "high", "medium", "low"],
                        help="Exit non-zero if issues >= this severity (CI)")
    return parser.parse_args(argv)
