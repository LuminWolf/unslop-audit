"""TSX/JSX 的 tree-sitter AST 视图。

把 AST 转成规则可消费的文本片段：
- 全文按等长空格屏蔽，非 UI 代码与注释不参与匹配；
- 追加虚拟片段表达 UI 值（class 属性、CSS 声明、元素文本内容），
  每个片段的字符都映射到产生它的 AST 节点起点，以保证行号准确。
"""

from __future__ import annotations

import re

import tree_sitter as ts
import tree_sitter_typescript as tst

from .views import ScanView

CLASS_FNS = {"cx", "clsx", "classnames", "cn", "classNames"}
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")
_LENGTH_PROPS = {
    "gap", "row-gap", "column-gap",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "padding-inline", "padding-block",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "margin-inline", "margin-block",
    "height", "width", "min-height", "max-height", "min-width", "max-width",
    "top", "right", "bottom", "left", "inset", "border-radius", "font-size",
}
_MAX_DEPTH = 12


def _text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _byte_map(text: str) -> list[int]:
    """字节偏移 -> 字符偏移。"""

    mapping: list[int] = []
    for index, char in enumerate(text):
        mapping.extend([index] * len(char.encode("utf-8")))
    return mapping


def _decode_escape(raw: str) -> str:
    try:
        return raw.encode("ascii").decode("unicode_escape")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _named(node) -> list:
    return [child for child in node.children if child.is_named]


def _unwrap(node):
    """透传包裹层：jsx_expression 与 parenthesized_expression。"""

    while node is not None and node.type in ("jsx_expression", "parenthesized_expression"):
        children = _named(node)
        if len(children) != 1:
            return None
        node = children[0]
    return node


def resolve_expr(node, source_bytes: bytes, bindings: dict,
                 depth: int = 0, seen: frozenset | None = None) -> str | None:
    """保守解析表达式为可匹配的界面字符串；无法解析返回 None。"""

    if node is None or depth > _MAX_DEPTH:
        return None
    seen = seen or frozenset()
    node = _unwrap(node)
    if node is None:
        return None

    kind = node.type

    if kind == "string":
        parts = []
        for child in node.children:
            if child.type == "string_fragment":
                parts.append(_text(child, source_bytes))
            elif child.type == "escape_sequence":
                parts.append(_decode_escape(_text(child, source_bytes)))
        return "".join(parts)

    if kind == "template_string":
        parts = []
        for child in node.children:
            if child.type == "string_fragment":
                parts.append(_text(child, source_bytes))
            elif child.type == "escape_sequence":
                parts.append(_decode_escape(_text(child, source_bytes)))
            elif child.type == "template_substitution":
                expressions = _named(child)
                if not expressions:
                    return None
                value = resolve_expr(
                    expressions[0], source_bytes, bindings, depth + 1, seen
                )
                if value is None:
                    return None
                parts.append(value)
        return "".join(parts)

    if kind == "identifier":
        name = _text(node, source_bytes)
        if name in seen or name not in bindings:
            return None
        return resolve_expr(
            bindings[name], source_bytes, bindings, depth + 1, seen | {name}
        )

    if kind == "number":
        return _text(node, source_bytes)

    if kind == "call_expression":
        children = _named(node)
        if len(children) < 2 or children[0].type != "identifier":
            return None
        if _text(children[0], source_bytes) not in CLASS_FNS:
            return None
        arguments = node.child_by_field_name("arguments") or children[1]
        parts = []
        for argument in _named(arguments):
            value = resolve_expr(argument, source_bytes, bindings, depth + 1, seen)
            if value is None:
                return None
            parts.append(value)
        return " ".join(parts)

    if kind == "array":
        parts = []
        for element in _named(node):
            value = resolve_expr(element, source_bytes, bindings, depth + 1, seen)
            if value is None:
                return None
            parts.append(value)
        return " ".join(parts)

    if kind == "binary_expression":
        operators = [child for child in node.children if not child.is_named]
        operator = operators[0].type if operators else ""
        operands = _named(node)
        if operator == "+" and len(operands) == 2:
            left = resolve_expr(operands[0], source_bytes, bindings, depth + 1, seen)
            right = resolve_expr(operands[1], source_bytes, bindings, depth + 1, seen)
            if left is None or right is None:
                return None
            return left + right
        if operator in ("&&", "||"):
            parts = []
            for operand in operands:
                value = resolve_expr(operand, source_bytes, bindings, depth + 1, seen)
                if value is not None:
                    parts.append(value)
            return " ".join(parts) if parts else None
        return None

    if kind == "ternary_expression":
        operands = _named(node)
        if len(operands) != 3:
            return None
        parts = []
        for branch in operands[1:]:
            value = resolve_expr(branch, source_bytes, bindings, depth + 1, seen)
            if value is not None:
                parts.append(value)
        return " ".join(parts) if parts else None

    return None


def _resolve_pair(pair, source_bytes: bytes, bindings: dict) -> str | None:
    children = _named(pair)
    if len(children) < 2:
        return None
    prop = _CAMEL_BOUNDARY.sub("-", _text(children[0], source_bytes)).lower()
    resolved = _unwrap(children[-1])
    if resolved is None:
        return None
    if resolved.type == "number":
        value = _text(resolved, source_bytes)
        if value != "0" and prop in _LENGTH_PROPS:
            value += "px"
    else:
        value = resolve_expr(resolved, source_bytes, bindings)
    if value is None:
        return None
    return f"{prop}: {value}"


def _emit_jsx(node, source_bytes: bytes, byte_map: list[int],
              bindings: dict, fragments: list) -> None:
    if node.type == "jsx_self_closing_element":
        opening = node
    else:
        opening = next(
            (child for child in node.children
             if child.type == "jsx_opening_element"),
            None,
        )
    if opening is None:
        return

    name_node = opening.child_by_field_name("name")
    tag = _text(name_node, source_bytes) if name_node is not None else "div"

    for attribute in opening.children:
        if attribute.type != "jsx_attribute":
            continue
        children = _named(attribute)
        if len(children) < 2:
            continue
        attr_name = _text(children[0], source_bytes)
        value_node = children[-1]
        if attr_name == "className":
            value = resolve_expr(value_node, source_bytes, bindings)
            if value is not None:
                fragments.append((
                    f'class="{value}"', byte_map[value_node.start_byte]
                ))
        elif attr_name == "style":
            object_node = _unwrap(value_node)
            if object_node is None or object_node.type != "object":
                continue
            for pair in object_node.children:
                if pair.type != "pair":
                    continue
                declaration = _resolve_pair(pair, source_bytes, bindings)
                if declaration is not None:
                    fragments.append((
                        declaration, byte_map[pair.start_byte]
                    ))

    if node.type != "jsx_element":
        return
    parts = []
    for child in node.children:
        if child.type == "jsx_text":
            parts.append(_text(child, source_bytes))
        elif child.type == "jsx_expression":
            value = resolve_expr(child, source_bytes, bindings)
            if value is not None:
                parts.append(value)
    content = "".join(parts).strip()
    if not content:
        return
    content = content.replace("<", "&lt;").replace(">", "&gt;")
    fragments.append((f"<{tag}>{content}</{tag}>", byte_map[node.start_byte]))


def _collect(node, source_bytes: bytes, byte_map: list[int],
             bindings: dict, fragments: list) -> None:
    if node.type == "variable_declarator":
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if (name_node is not None and value_node is not None
                and name_node.type == "identifier"):
            bindings.setdefault(_text(name_node, source_bytes), value_node)
    elif node.type in ("jsx_element", "jsx_self_closing_element"):
        _emit_jsx(node, source_bytes, byte_map, bindings, fragments)
    for child in node.children:
        _collect(child, source_bytes, byte_map, bindings, fragments)


def build_tsx_view(text: str) -> ScanView | None:
    """构造 TSX AST 视图；解析异常或语法错误返回 None 以触发回退。"""

    try:
        language = ts.Language(tst.language_tsx())
        parser = ts.Parser(language)
        source_bytes = text.encode("utf-8")
        tree = parser.parse(source_bytes)
        if tree.root_node.has_error:
            return None
        byte_map = _byte_map(text)
        bindings: dict = {}
        fragments: list = []
        _collect(tree.root_node, source_bytes, byte_map, bindings, fragments)
    except Exception:
        return None

    chars = [char if char in "\r\n" else " " for char in text]
    offsets = list(range(len(text)))
    for fragment, source_offset in fragments:
        # 每个片段独立成行，避免全文正则跨越片段边界产生误匹配。
        offsets.append(source_offset)
        chars.append("\n")
        offsets.extend([source_offset] * len(fragment))
        chars.extend(fragment)
    return ScanView(text="".join(chars), source=text, offsets=offsets)
