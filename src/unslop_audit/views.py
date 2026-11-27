"""扫描视图：统一文本入口与到源文件的偏移映射。"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


@dataclass
class ScanView:
    """规则消费的扫描文本 + 到源文件的偏移映射。

    text: 扫描文本（屏蔽区 + 虚拟片段），长度可与 source 不同。
    source: 原始源文件文本。
    offsets: text 中每个字符对应的 source 字符偏移。
    """

    text: str
    source: str
    offsets: list[int]
    line_starts: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.line_starts:
            self.line_starts = _line_starts(self.source)

    @classmethod
    def from_source(cls, text: str) -> ScanView:
        """HTML/CSS 等文本视图：等价于现有 mask_comments，恒等偏移映射。"""

        from .matching import mask_comments

        masked = mask_comments(text)
        return cls(text=masked, source=text, offsets=list(range(len(masked))))

    @classmethod
    def from_tsx(cls, text: str) -> ScanView | None:
        """TSX/JSX 的 AST 视图；解析或依赖失败返回 None 以便调用方回退。"""

        try:
            from .tsx import build_tsx_view

            return build_tsx_view(text)
        except Exception:
            return None

    def source_span(self, start: int, end: int | None = None) -> tuple[int, int]:
        """把扫描文本区间转换成源文件字符偏移区间。"""

        size = len(self.offsets)
        if size == 0:
            return 0, 0
        source_start = self.offsets[start] if start < size else len(self.source)
        if end is None or end <= start:
            return source_start, source_start + 1
        source_end = self.offsets[min(end - 1, size - 1)] + 1
        return source_start, max(source_start, source_end)

    def line_of(self, offset: int) -> int:
        """源文件字符偏移 -> 1-based 行号。"""

        return bisect_right(self.line_starts, offset)


__all__ = ["ScanView"]
