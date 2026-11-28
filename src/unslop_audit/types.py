"""扫描视图：供 Scanner 构造与消费的纯数据对象。"""

from __future__ import annotations

from dataclasses import dataclass


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


@dataclass
class ScanView:
    """规则消费的纯数据视图。

    text: 扫描文本（屏蔽区 + 虚拟片段），长度可与 source 不同。
    source: 原始源文件文本。
    offsets: text 中每个字符对应的 source 字符偏移。
    line_starts: source 每一行的起始字符偏移。
    """

    text: str
    source: str
    offsets: list[int]
    line_starts: list[int]


__all__ = ["ScanView"]
