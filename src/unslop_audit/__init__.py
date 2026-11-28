"""unslop-audit：前端 AI 味静态审计器。"""

from .cli import build_args, configure_utf8
from .matching import CLASS_ATTR, ClassMatcher, Matcher, mask_comments
from .models import AuditReport, DIM_CN, Dimension, Finding, Severity
from .reporting import (
    SEVERITY_ICON,
    SEVERITY_LABEL,
    build_report,
    print_findings,
    print_report,
    print_summary,
    write_csv,
)
from .rules import EMOJI_RE, RULES, Rule, build_rules
from .scan import SKIP_DIRS, SUPPORTED_EXTS, Scanner, collect_files, truncate
from .types import ScanView

__version__ = "0.1.0"

__all__ = [
    "CLASS_ATTR",
    "DIM_CN",
    "EMOJI_RE",
    "RULES",
    "SEVERITY_ICON",
    "SEVERITY_LABEL",
    "SKIP_DIRS",
    "SUPPORTED_EXTS",
    "AuditReport",
    "ClassMatcher",
    "Dimension",
    "Finding",
    "Matcher",
    "Rule",
    "ScanView",
    "Scanner",
    "Severity",
    "build_args",
    "build_report",
    "build_rules",
    "collect_files",
    "configure_utf8",
    "mask_comments",
    "print_findings",
    "print_report",
    "print_summary",
    "truncate",
    "write_csv",
]
