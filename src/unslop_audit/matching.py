"""通用匹配器：全文正则、class 属性内匹配与注释屏蔽。"""

import re

from .views import ScanView


CLASS_ATTR = re.compile(
    r'(?:class|className)\s*=\s*(["\'])(.*?)\1', re.I | re.S
)


class Matcher:
    """全文正则匹配器，可带语境谓词。

    guard(text, match) -> bool；返回 False 则丢弃该次命中。
    text 是已屏蔽注释但长度/行号与原文一致的字符串。
    """

    def __init__(self, regex, flags=re.I, guard=None):
        self.regex = re.compile(regex, flags)
        self.guard = guard

    def find(self, text):
        target = text.text if isinstance(text, ScanView) else text
        for match in self.regex.finditer(target):
            if self.guard is None or self.guard(target, match):
                yield match.start(), match.end()


class ClassMatcher:
    """只在 class="..." / className="..." 的属性值内匹配 Tailwind 类名。

    guard(value, match) -> bool，value 是当前 class 串，便于判断"同串共存"。
    这样既避免把正文/注释里的普通单词当类名，也天然支持顺序无关的组合判断。
    """

    def __init__(self, regex, guard=None):
        self.regex = re.compile(regex, re.I)
        self.guard = guard

    def find(self, text):
        target = text.text if isinstance(text, ScanView) else text
        for attribute_match in CLASS_ATTR.finditer(target):
            attribute_value, base_offset = attribute_match.group(2), attribute_match.start(2)
            for match in self.regex.finditer(attribute_value):
                if self.guard is None or self.guard(attribute_value, match):
                    yield base_offset + match.start(), base_offset + match.end()


def mask_comments(text):
    """把 CSS / HTML 注释替换成等长空格，保留换行和行列位置。"""

    if "/*" not in text and "<!--" not in text:
        return text
    masked = list(text)
    for comment_match in re.finditer(r"/\*.*?\*/|<!--.*?-->", text, re.S):
        for index in range(comment_match.start(), comment_match.end()):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)
