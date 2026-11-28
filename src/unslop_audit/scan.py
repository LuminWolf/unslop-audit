"""文件收集与扫描。"""

import logging
import sys
from bisect import bisect_right
from pathlib import Path

from .models import Dimension, Finding, Severity
from .rules import EMOJI_RE, RULES
from .types import ScanView, _line_starts

logger = logging.getLogger(__name__)


SUPPORTED_EXTS = {
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".jsx",
    ".tsx",
    ".js",
    ".ts",
    ".vue",
    ".svelte",
}
SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "__pycache__",
    "vendor",
    ".cache",
    "venv",
    "reference",
}


def collect_files(target):
    target_path = Path(target)
    if target_path.is_file():
        return [str(target_path)]
    files = []
    for extension in SUPPORTED_EXTS:
        files.extend(str(file_path) for file_path in target_path.rglob("*" + extension))
    files = [
        file_path for file_path in files if not SKIP_DIRS & set(Path(file_path).parts)
    ]
    return sorted(set(files))


def truncate(text, maxlen=120):
    text = text.strip()
    return (text[:maxlen] + "...") if len(text) > maxlen else text


class Scanner:
    """构造扫描视图并执行扫描；按需复用同一个 TSX 解析器。"""

    def __init__(self) -> None:
        self._tsx_builder = None

    def _get_builder(self):
        if self._tsx_builder is None:
            from .tsx import TsxBuilder

            self._tsx_builder = TsxBuilder()
        return self._tsx_builder

    def from_source(self, text: str) -> ScanView:
        """HTML/CSS 等文本视图：等价于现有 mask_comments，恒等偏移映射。"""

        from .matching import mask_comments

        masked = mask_comments(text)
        return ScanView(
            text=masked,
            source=text,
            offsets=list(range(len(masked))),
            line_starts=_line_starts(text),
        )

    def from_tsx(self, text: str) -> ScanView | None:
        """TSX/JSX 的 AST 视图；解析或依赖失败返回 None 以便调用方回退。"""

        try:
            return self._get_builder().build_tsx_view(text)
        except Exception:  # noqa: BLE001 - 可选依赖缺失时回退到文本视图是有意设计
            return None

    def source_span(
        self, view: ScanView, start: int, end: int | None = None
    ) -> tuple[int, int]:
        """把扫描文本区间转换成源文件字符偏移区间。"""

        size = len(view.offsets)
        if size == 0:
            return 0, 0
        source_start = view.offsets[start] if start < size else len(view.source)
        if end is None or end <= start:
            return source_start, source_start + 1
        source_end = view.offsets[min(end - 1, size - 1)] + 1
        return source_start, max(source_start, source_end)

    def line_of(self, view: ScanView, offset: int) -> int:
        """源文件字符偏移 -> 1-based 行号。"""

        return bisect_right(view.line_starts, offset)

    def scan_file(self, filepath, rules=None):
        findings = []
        rules = rules or RULES

        try:
            text = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return findings

        suffix = Path(filepath).suffix.lower()
        if suffix in {".tsx", ".jsx"}:
            view = self.from_tsx(text)
            if view is None:
                print(
                    f"WARNING: TSX AST 视图不可用，回退到文本视图: {filepath}",
                    file=sys.stderr,
                )
                view = self.from_source(text)
        else:
            view = self.from_source(text)

        lines = text.splitlines()

        for rule in rules:
            seen = set()
            for matcher in rule.matchers:
                try:
                    for start, end in matcher.find(view):
                        source_start, source_end = self.source_span(view, start, end)
                        key = (rule.name, source_start, source_end)
                        if key in seen:
                            continue
                        seen.add(key)
                except Exception as exc:  # noqa: BLE001 - 单个 matcher 失败不应中断整份文件
                    logger.warning("matcher failed in rule %s: %s", rule.name, exc)
                    continue
            for _, source_start, source_end in sorted(seen):
                line_no = self.line_of(view, source_start)
                context_line = (
                    lines[line_no - 1]
                    if 0 <= line_no - 1 < len(lines)
                    else text[source_start:source_end]
                )
                findings.append(
                    Finding(
                        file=filepath,
                        line=line_no,
                        dimension=rule.dimension.value,
                        severity=rule.severity.value,
                        pattern=rule.name,
                        message=rule.message,
                        suggestion=rule.suggestion,
                        context=truncate(context_line),
                    )
                )

        # Emoji 专项扫描（按源文件行聚合）。
        emoji_by_line = {}
        for match in EMOJI_RE.finditer(view.text):
            source_start, _ = self.source_span(view, match.start(), match.end())
            line_number = self.line_of(view, source_start)
            emoji_by_line.setdefault(line_number, []).append(match.group())

        for line_number in sorted(emoji_by_line):
            hits = emoji_by_line[line_number]
            findings.append(
                Finding(
                    file=filepath,
                    line=line_number,
                    dimension=Dimension.ICONS.value,
                    severity=Severity.HIGH.value,
                    pattern="emoji-as-icon",
                    message="检测到 emoji 装饰字符: " + " ".join(hits[:5]),
                    suggestion="替换为统一图标库的线性图标",
                    context=truncate(
                        lines[line_number - 1] if line_number - 1 < len(lines) else ""
                    ),
                )
            )

        if suffix in {".html", ".htm"}:
            try:
                from .dom_rules import analyze_html

                findings.extend(analyze_html(filepath, text))
            except Exception as exc:  # noqa: BLE001 - 结构分析失败不应中断文本扫描
                logger.info("HTML structure analysis unavailable for %s: %s", filepath, exc)

        return findings
