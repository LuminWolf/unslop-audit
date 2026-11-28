"""最小 CSS 级联：静态选择器、声明、`!important` 与有限继承。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .html_dom import HtmlDocument, HtmlNode
from .matching import mask_comments

logger = logging.getLogger(__name__)

INHERITED = {
    "color",
    "font-family",
    "font-size",
    "font-weight",
    "letter-spacing",
    "line-height",
    "text-align",
    "direction",
}
_SELECTOR_RE = re.compile(r"(?:(#[^#\s.]+)|(\.[^\s#.]+)|([a-zA-Z][\w-]*))")
_COMPLEX_RE = re.compile(r"[>+~*]|\s")
_LINK_RE = re.compile(
    r'<link\b[^>]*\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


@dataclass
class CssDeclaration:
    prop: str
    value: str
    important: bool = False


@dataclass
class CssRule:
    selector: str
    declarations: list[CssDeclaration]
    specificity: tuple[int, int, int]
    order: int


@dataclass
class StyleEnvironment:
    values: dict[str, str] = field(default_factory=dict)

    def get(self, prop: str) -> str | None:
        return self.values.get(prop)


def _declarations(body: str) -> list[CssDeclaration]:
    declarations: list[CssDeclaration] = []
    for part in body.split(";"):
        if ":" not in part:
            continue
        prop, raw_value = part.split(":", 1)
        important = bool(re.search(r"!important\s*$", raw_value, re.IGNORECASE))
        value = re.sub(r"!important\s*$", "", raw_value, flags=re.IGNORECASE)
        declarations.append(
            CssDeclaration(prop.strip().lower(), value.strip(), important)
        )
    return declarations


def _specificity(selector: str) -> tuple[int, int, int]:
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+", selector))
    tags = 1 if re.match(r"^[a-zA-Z][\w-]*", selector) else 0
    return ids, classes, tags


def _rule_texts(text: str) -> list[tuple[str, str]]:
    """返回 (selector, declarations_body)。优先用 grammar 找 rule_set。"""

    try:
        import tree_sitter_css as tscss
        from tree_sitter import Language, Parser
    except Exception:  # noqa: BLE001 - 回退正则提取
        pass
    else:
        try:
            source = mask_comments(text).encode("utf-8")
            tree = Parser(Language(tscss.language())).parse(source)
        except Exception:  # noqa: BLE001 - 回退正则提取
            pass
        else:
            blocks = []
            for node in _walk(tree.root_node):
                if node.type not in {"rule_set", "rule"}:
                    continue
                raw = source[node.start_byte : node.end_byte].decode("utf-8", "replace")
                if "{" not in raw or "}" not in raw:
                    continue
                selector, body = raw.split("{", 1)
                blocks.append((selector.strip(), body.rsplit("}", 1)[0]))
            if blocks:
                return blocks

    masked = mask_comments(text)
    blocks = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", masked, re.DOTALL):
        blocks.append((match.group(1).strip(), match.group(2)))
    return blocks


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def parse_css(text: str, base_order: int = 0) -> list[CssRule]:
    rules: list[CssRule] = []
    for selector, body in _rule_texts(text):
        if not selector or selector.startswith("@") or selector.startswith(":"):
            continue
        declarations = _declarations(body)
        if declarations:
            rules.append(
                CssRule(
                    selector=selector,
                    declarations=declarations,
                    specificity=_specificity(selector),
                    order=base_order + len(rules),
                )
            )
    return rules


def _selector_matches(selector: str, node: HtmlNode) -> bool:
    for group in selector.split(","):
        group = group.strip()
        if not group or _COMPLEX_RE.search(group):
            continue
        ids = re.findall(r"#([\w-]+)", group)
        classes = re.findall(r"\.([\w-]+)", group)
        tag_match = re.match(r"^[a-zA-Z][\w-]*", group)
        if ids and any(node.attrs.get("id") != value for value in ids):
            continue
        if classes and any(value not in node.classes() for value in classes):
            continue
        if tag_match and tag_match.group(0).lower() != node.tag:
            continue
        return True
    return False


def collect_style_rules(
    html_path: str, html_text: str, document: HtmlDocument
) -> list[CssRule]:
    rules: list[CssRule] = []
    for css, _line in document.style_blocks:
        rules.extend(parse_css(css, len(rules)))

    html_dir = Path(html_path).resolve().parent
    for href in _LINK_RE.findall(html_text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.IGNORECASE) or href.startswith("//"):
            continue
        stylesheet = (html_dir / href).resolve()
        try:
            stylesheet.relative_to(html_dir)
            css = stylesheet.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        rules.extend(parse_css(css, len(rules)))
    return rules


def compute_style(
    node: HtmlNode,
    rules: list[CssRule],
    parent: StyleEnvironment | None = None,
) -> StyleEnvironment:
    env = StyleEnvironment()
    if parent:
        for prop in INHERITED:
            value = parent.get(prop)
            if value is not None:
                env.values[prop] = value

    candidates: dict[str, tuple[bool, tuple[int, int, int], int, str]] = {}
    for rule in rules:
        if not _selector_matches(rule.selector, node):
            continue
        for declaration in rule.declarations:
            key = (declaration.important, rule.specificity, rule.order)
            current = candidates.get(declaration.prop)
            if current is None or key >= current[:3]:
                candidates[declaration.prop] = (
                    *key,
                    declaration.value,
                )

    inline = node.attrs.get("style", "")
    for declaration in _declarations(inline):
        key = (declaration.important, (1000, 1000, 1000), 10**9)
        candidates[declaration.prop] = (*key, declaration.value)

    for prop, candidate in candidates.items():
        env.values[prop] = candidate[3]
    return env
