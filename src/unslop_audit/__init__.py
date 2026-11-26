"""unslop-audit：前端 AI 味静态审计器。"""

from .cli import build_args, configure_utf8
from .matching import CLASS_ATTR, ClassMatcher, Matcher, mask_comments
from .models import AuditReport, DIM_CN, Dimension, Finding, Severity
from .reporting import (
    SEVERITY_ICON,
    SEVERITY_LABEL,
    SEVERITY_WEIGHT,
    build_report,
    compute_score,
    print_findings,
    print_report,
    print_summary,
    write_csv,
)
from .rules import EMOJI_RE, RULES, Rule, build_rules
from .scan import SKIP_DIRS, SUPPORTED_EXTS, collect_files, scan_file, truncate

__version__ = "0.1.0"

__all__ = [
    "AuditReport", "DIM_CN", "Dimension", "Finding", "Severity",
    "CLASS_ATTR", "ClassMatcher", "Matcher", "mask_comments",
    "RULES", "EMOJI_RE", "Rule", "build_rules",
    "SKIP_DIRS", "SUPPORTED_EXTS", "collect_files", "scan_file", "truncate",
    "SEVERITY_ICON", "SEVERITY_LABEL", "SEVERITY_WEIGHT",
    "build_report", "compute_score", "print_findings", "print_report",
    "print_summary", "write_csv",
    "build_args", "configure_utf8",
]
