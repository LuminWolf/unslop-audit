"""HTML DOM 与最小计算样式规则；只新增低严重级别结构 finding。"""

from __future__ import annotations

import re

from .css_cascade import StyleEnvironment, collect_style_rules, compute_style
from .html_dom import HtmlDocument, HtmlNode, parse_html
from .models import Dimension, Finding, Severity


def _truncate(text: str, maxlen: int = 120) -> str:
    text = text.strip()
    return text[:maxlen] + "..." if len(text) > maxlen else text


def _finding(
    filepath: str,
    text: str,
    node: HtmlNode,
    pattern: str,
    dimension: Dimension,
    message: str,
    suggestion: str,
) -> Finding:
    lines = text.splitlines()
    line = max(1, node.line)
    context = lines[line - 1] if 0 <= line - 1 < len(lines) else "<element>"
    return Finding(
        file=filepath,
        line=line,
        dimension=dimension.value,
        severity=Severity.LOW.value,
        pattern=pattern,
        message=message,
        suggestion=suggestion,
        context=_truncate(context),
    )


def _all_nodes(document: HtmlDocument) -> list[HtmlNode]:
    if document.root is None:
        return []
    return [document.root, *document.root.descendants()]


def analyze_html(filepath: str, text: str) -> list[Finding]:
    """执行 HTML 结构路径；grammar 不可用时返回空列表。"""

    document = parse_html(text)
    if document is None or document.root is None:
        return []

    css_rules = collect_style_rules(filepath, text, document)
    styles: dict[int, StyleEnvironment] = {}

    def visit(node: HtmlNode, parent: StyleEnvironment | None) -> None:
        environment = compute_style(node, css_rules, parent)
        styles[id(node)] = environment
        for child in node.children:
            visit(child, environment)

    visit(document.root, None)
    nodes = _all_nodes(document)
    findings: list[Finding] = []

    for node in nodes:
        classes = node.classes()
        if "card" not in classes:
            continue
        if any("card" in descendant.classes() for descendant in node.descendants()):
            findings.append(
                _finding(
                    filepath,
                    text,
                    node,
                    "nested-card-container",
                    Dimension.LAYOUT,
                    "卡片容器内嵌套卡片容器",
                    "减少嵌套层级，用分区和留白表达层级",
                )
            )

    headings = [
        node
        for node in nodes
        if re.fullmatch(r"h[1-6]", node.tag)
    ]
    for previous, current in zip(headings, headings[1:]):
        previous_level = int(previous.tag[1])
        current_level = int(current.tag[1])
        if current_level - previous_level > 1:
            findings.append(
                _finding(
                    filepath,
                    text,
                    current,
                    "heading-level-skip",
                    Dimension.LAYOUT,
                    f"标题层级从 h{previous_level} 跳到 h{current_level}",
                    "标题层级逐递增，不要跳级",
                )
            )

    for node in nodes:
        if node.tag != "button":
            continue
        if node.text_content().strip():
            continue
        if node.attrs.get("aria-label") or node.attrs.get("title"):
            continue
        if any(child.tag in {"svg", "img"} for child in node.descendants()):
            findings.append(
                _finding(
                    filepath,
                    text,
                    node,
                    "icon-only-button-without-name",
                    Dimension.ICONS,
                    "只有图标、没有可访问名称的按钮",
                    "添加 aria-label 或可见文字",
                )
            )

    for node in nodes:
        radius = styles.get(id(node), StyleEnvironment()).get("border-radius")
        if not radius:
            continue
        values = [int(value) for value in re.findall(r"(\d+)px", radius)]
        if any(value >= 24 and value % 4 != 0 for value in values):
            findings.append(
                _finding(
                    filepath,
                    text,
                    node,
                    "computed-radius-off-grid",
                    Dimension.DETAILS,
                    "计算样式的圆角不在 4px 网格上",
                    "圆角使用 8/12/16/20/24 等网格值",
                )
            )

    return findings
