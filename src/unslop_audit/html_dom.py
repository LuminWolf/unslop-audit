"""HTML DOM 结构视图；grammar 不可用时返回 None 由调用方回退。"""

from __future__ import annotations

import logging
import re
from bisect import bisect_right
from dataclasses import dataclass, field

from .types import _line_starts

logger = logging.getLogger(__name__)

_ATTR_RE = re.compile(
    r"([:@\w.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))"
)


@dataclass
class HtmlNode:
    tag: str
    start: int
    end: int
    line: int
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode"] = field(default_factory=list)
    parent: "HtmlNode | None" = None
    text: str = ""

    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()

    def text_content(self) -> str:
        return self.text + "".join(child.text_content() for child in self.children)


@dataclass
class HtmlDocument:
    root: HtmlNode | None
    style_blocks: list[tuple[str, int]] = field(default_factory=list)


def _build_char_map(text: str) -> list[int]:
    mapping: list[int] = []
    for index, char in enumerate(text):
        mapping.extend([index] * len(char.encode("utf-8")))
    mapping.append(len(text))
    return mapping


def _decode(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _attributes(start_tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(start_tag):
        value = match.group(2) or match.group(3) or match.group(4) or ""
        attrs[match.group(1).lower()] = value
    return attrs


def _tag_name(ts_node, source_bytes: bytes) -> str:
    if ts_node.type == "style_element":
        return "style"
    if ts_node.type == "script_element":
        return "script"
    name_node = ts_node.child_by_field_name("name")
    if name_node is not None:
        return _decode(source_bytes[name_node.start_byte : name_node.end_byte])
    for child in ts_node.named_children:
        if child.type in {"tag_name", "style_element", "script_element"}:
            return _decode(source_bytes[child.start_byte : child.end_byte])
    return ts_node.type


def parse_html(text: str) -> HtmlDocument | None:
    """用 tree-sitter HTML grammar 解析；依赖缺失或失败返回 None。"""

    try:
        import tree_sitter_html as tsh
        from tree_sitter import Language, Parser
    except Exception as exc:  # noqa: BLE001 - 可选依赖缺失时安静回退
        logger.info("HTML grammar unavailable: %s", exc)
        return None

    try:
        source_bytes = text.encode("utf-8")
        parser = Parser(Language(tsh.language()))
        tree = parser.parse(source_bytes)
    except Exception as exc:  # noqa: BLE001 - 解析失败不中断文本扫描
        logger.info("HTML parse failed: %s", exc)
        return None

    char_map = _build_char_map(text)
    line_starts = _line_starts(text)
    style_blocks: list[tuple[str, int]] = []
    root: HtmlNode | None = None

    def char_offset(byte_offset: int) -> int:
        return char_map[min(max(byte_offset, 0), len(char_map) - 1)]

    def line_of(offset: int) -> int:
        return bisect_right(line_starts, offset)

    def visit(ts_node, parent: HtmlNode | None) -> None:
        nonlocal root
        node_type = ts_node.type
        if node_type == "comment":
            return
        if node_type == "text":
            if parent is not None:
                parent.text += _decode(source_bytes[ts_node.start_byte : ts_node.end_byte])
            return

        is_element = "element" in node_type or node_type in {
            "style_element",
            "script_element",
        }
        if not is_element:
            for child in ts_node.named_children:
                visit(child, parent)
            return

        start = char_offset(ts_node.start_byte)
        end = char_offset(ts_node.end_byte)
        node = HtmlNode(
            tag=_tag_name(ts_node, source_bytes).lower(),
            start=start,
            end=end,
            line=line_of(start),
            parent=parent,
        )
        start_tag = ""
        for child in ts_node.named_children:
            if child.type in {"start_tag", "self_closing_tag"}:
                start_tag = _decode(source_bytes[child.start_byte : child.end_byte])
                break
        if not start_tag:
            head = _decode(source_bytes[ts_node.start_byte : ts_node.end_byte])
            closing = head.find(">")
            start_tag = head[: closing + 1] if closing >= 0 else head
        node.attrs = _attributes(start_tag)

        if parent is None:
            root = node
        else:
            parent.children.append(node)

        if node.tag == "style":
            style_text = _decode(source_bytes[ts_node.start_byte : ts_node.end_byte])
            match = re.search(r">\s*(.*?)\s*</style\s*>", style_text, re.DOTALL | re.I)
            if match:
                style_blocks.append((match.group(1), node.line))

        for child in ts_node.named_children:
            if child.type in {"start_tag", "end_tag", "self_closing_tag"}:
                continue
            visit(child, node)

    for child in tree.root_node.named_children:
        visit(child, None)

    return HtmlDocument(root=root, style_blocks=style_blocks)
