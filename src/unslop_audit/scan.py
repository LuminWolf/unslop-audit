"""文件收集与扫描。"""

import sys
from pathlib import Path

from .models import Dimension, Finding, Severity
from .rules import EMOJI_RE, RULES
from .views import ScanView


SUPPORTED_EXTS = {".html", ".htm", ".css", ".scss", ".less",
                  ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next",
             "__pycache__", "vendor", ".cache", "venv", "reference"}


def collect_files(target):
    target_path = Path(target)
    if target_path.is_file():
        return [str(target_path)]
    files = []
    for extension in SUPPORTED_EXTS:
        files.extend(
            str(file_path) for file_path in target_path.rglob("*" + extension)
        )
    files = [
        file_path for file_path in files
        if not SKIP_DIRS & set(Path(file_path).parts)
    ]
    return sorted(set(files))


def truncate(text, maxlen=120):
    text = text.strip()
    return (text[:maxlen] + "...") if len(text) > maxlen else text


def scan_file(filepath, rules=None):
    findings = []
    rules = rules or RULES

    try:
        text = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    suffix = Path(filepath).suffix.lower()
    if suffix in {".tsx", ".jsx"}:
        view = ScanView.from_tsx(text)
        if view is None:
            print(f"WARNING: TSX AST 视图不可用，回退到文本视图: {filepath}",
                  file=sys.stderr)
            view = ScanView.from_source(text)
    else:
        view = ScanView.from_source(text)

    lines = text.splitlines()

    for rule in rules:
        seen = set()
        for matcher in rule.matchers:
            try:
                for start, end in matcher.find(view):
                    source_start, source_end = view.source_span(start, end)
                    key = (rule.name, source_start, source_end)
                    if key in seen:
                        continue
                    seen.add(key)
            except Exception:
                continue
        for _, source_start, source_end in sorted(seen):
            line_no = view.line_of(source_start)
            context_line = (
                lines[line_no - 1]
                if 0 <= line_no - 1 < len(lines)
                else text[source_start:source_end]
            )
            findings.append(Finding(
                file=filepath, line=line_no,
                dimension=rule.dimension.value, severity=rule.severity.value,
                pattern=rule.name, message=rule.message,
                suggestion=rule.suggestion, context=truncate(context_line),
            ))

    # Emoji 专项扫描（按源文件行聚合）。
    emoji_by_line = {}
    for match in EMOJI_RE.finditer(view.text):
        source_start, _ = view.source_span(match.start(), match.end())
        line_number = view.line_of(source_start)
        emoji_by_line.setdefault(line_number, []).append(match.group())

    for line_number in sorted(emoji_by_line):
        hits = emoji_by_line[line_number]
        findings.append(Finding(
            file=filepath, line=line_number,
            dimension=Dimension.ICONS.value,
            severity=Severity.HIGH.value,
            pattern="emoji-as-icon",
            message="检测到 emoji 装饰字符: " + " ".join(hits[:5]),
            suggestion="替换为统一图标库的线性图标",
            context=truncate(
                lines[line_number - 1]
                if line_number - 1 < len(lines)
                else ""
            ),
        ))

    return findings
