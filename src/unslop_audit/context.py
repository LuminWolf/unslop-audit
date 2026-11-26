"""规则使用的语境谓词与颜色判断。"""

import re


COLOR_TOKEN = re.compile(
    r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)|hsla?\([^)]*\)",
    re.I,
)
NAMED_HUE = re.compile(
    r"\b(?:purple|violet|fuchsia|indigo|magenta|rebeccapurple|cyan|teal|aqua|"
    r"blue|pink|orange|green|red|yellow|gold)\b", re.I,
)
NEON_HEX = (
    "#a855f7", "#8b5cf6", "#7c3aed", "#6366f1", "#6d28d9", "#c084fc",
    "#a78bfa", "#06b6d4", "#22d3ee", "#3b82f6", "#ec4899",
)


def _is_chromatic(token):
    """判断一个颜色 token 是否明显带色相（灰阶/中性色返回 False）。"""

    normalized = token.strip()
    if normalized.startswith("#"):
        hex_digits = normalized[1:]
        if len(hex_digits) == 3:
            hex_digits = "".join(character * 2 for character in hex_digits)
        try:
            red = int(hex_digits[0:2], 16)
            green = int(hex_digits[2:4], 16)
            blue = int(hex_digits[4:6], 16)
        except ValueError:
            return False
        return max(red, green, blue) - min(red, green, blue) > 24
    if normalized.startswith("rgb"):
        numbers = [int(number) for number in re.findall(r"\d+", normalized)[:3]]
        return len(numbers) == 3 and max(numbers) - min(numbers) > 24
    if normalized.startswith("hsl"):
        return True
    return True


def has_chroma(body):
    """声明/渐变里是否出现彩色值或彩色色名。"""

    if NAMED_HUE.search(body):
        return True
    return any(_is_chromatic(token) for token in COLOR_TOKEN.findall(body))


def has_neon(body):
    lower_body = body.lower()
    if any(neon_hex in lower_body for neon_hex in NEON_HEX):
        return True
    if NAMED_HUE.search(lower_body) and re.search(
        r"purple|violet|fuchsia|indigo|cyan|teal|magenta", lower_body
    ):
        return True
    for token in COLOR_TOKEN.findall(lower_body):
        if token.startswith(("rgb", "#")) and _is_chromatic(token):
            if token.startswith("rgb"):
                numbers = [int(number) for number in re.findall(r"\d+", token)[:3]]
                if len(numbers) == 3 and numbers[2] - numbers[0] > 40:
                    return True
            else:
                hex_digits = token[1:]
                if len(hex_digits) == 3:
                    hex_digits = "".join(character * 2 for character in hex_digits)
                try:
                    red = int(hex_digits[0:2], 16)
                    blue = int(hex_digits[4:6], 16)
                    if blue - red > 40:
                        return True
                except ValueError:
                    pass
    return False


def _px_values(body):
    return [int(number) for number in re.findall(r"(\d+)px\b", body, re.I)]


def off_grid_guard(text, match):
    """4px 网格；2px 微调（SKILL 允许）与 4 的倍数放行。"""

    values = _px_values(match.group(1))
    return any(value % 4 != 0 and value != 2 for value in values)


def same_hue_class_guard(value, match):
    """同色明度渐变（from-gray-900 to-gray-800）是 SKILL 明确允许的。"""

    from_match = re.search(r"\bfrom-([a-z]+)-\d+\b", value, re.I)
    to_match = re.search(r"\bto-([a-z]+)-\d+\b", value, re.I)
    return not (
        from_match and to_match
        and from_match.group(1).lower() == to_match.group(1).lower()
    )


def has_class(value, name):
    return re.search(r"\b" + re.escape(name) + r"\b", value, re.I) is not None


def in_pseudo_element(text, match):
    """该声明是否落在 ::placeholder / ::selection 这类伪元素里。"""

    head = text[max(0, match.start() - 240):match.start()]
    brace = head.rfind("{")
    if brace < 0:
        return False
    start = max(head.rfind("}", 0, brace), head.rfind(";", 0, brace),
                head.rfind(">", 0, brace)) + 1
    selector = head[start:brace]
    return bool(re.search(r"::?(?:placeholder|selection|-webkit-input-placeholder)\b",
                          selector, re.I))


def is_text_node_bang(text, match):
    """只认界面文本里的感叹号，排除 <!DOCTYPE、!important、!= 等语法符号。"""

    previous = text[match.start() - 1] if match.start() else ""
    following = text[match.end():match.end() + 12].lstrip()
    if previous in "<=" or following.startswith("=") or following.lower().startswith("important"):
        return False
    left_angle = text.rfind("<", 0, match.start())
    right_angle = text.rfind(">", 0, match.start())
    return right_angle > left_angle


def unqualified_change_guard(text, match):
    following_text = text[match.end():match.end() + 60]
    return not re.search(r"\bvs\b|compared|last\s+\w+|previous|同比|环比", following_text, re.I)


def number_format_guard(text, match):
    """金额格式不一致，或用了金额却没开 tabular-nums。"""

    amounts = re.findall(r"\$\s*\d[\d,]*(?:\.\d+)?", text)
    if not amounts:
        return False
    decimals = {
        len(amount.split(".")[1]) if "." in amount else 0
        for amount in amounts
    }
    if len(decimals) > 1:
        return True
    return "tabular-nums" not in text


def icon_inconsistent_guard(text, match):
    svgs = re.findall(r"<svg\b[^>]*>", text, re.I)
    widths = {
        width
        for svg in svgs
        for width in re.findall(r'\bwidth="(\d+)"', svg)
    }
    strokes = {
        stroke
        for svg in svgs
        for stroke in re.findall(r'stroke-width="([\d.]+)"', svg)
    }
    return len(widths) > 1 or len(strokes) > 1


def too_many_actions_guard(text, match):
    button_positions = [button.start() for button in re.finditer(r"<button\b", text, re.I)]
    return len(button_positions) >= 3 and (button_positions[-1] - button_positions[0]) < 320


def rtl_guard(text, match):
    return not re.search(r'\bdir\s*=\s*["\']rtl["\']', text, re.I)


def trailing_period_guard(text, match):
    return not re.search(r"\.\s+[A-Z]", match.group(1))
