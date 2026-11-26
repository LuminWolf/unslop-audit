#!/usr/bin/env python3
"""
自动扫描前端源码，检测 AI 味
按 9 个维度（间距/颜色/图标/文案/字体/布局/细节/视觉/动效）
输出结构化审计报告。

支持文件类型: .html / .css / .scss / .less / .jsx / .tsx / .vue / .svelte

用法:
    python ai_ui_audit.py <文件或目录路径> [--fix-hints] [--json]
    python ai_ui_audit.py ./src --fix-hints
    python ai_ui_audit.py ./src --json > report.json
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum

import pyparsing as pp

pp.ParserElement.enable_packrat()


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class Dimension(str, Enum):
    SPACING  = "1-Spacing"
    COLOR    = "2-Color"
    ICONS    = "3-Icons"
    COPY     = "4-Copy"
    TYPE     = "5-Type"
    LAYOUT   = "6-Layout"
    DETAILS  = "7-Details"
    VISUALS  = "8-Visuals"
    MOTION   = "9-Motion"


DIM_CN = {
    "1-Spacing":  "间距",
    "2-Color":    "颜色",
    "3-Icons":    "图标",
    "4-Copy":     "文案",
    "5-Type":     "字体",
    "6-Layout":   "布局",
    "7-Details":  "细节",
    "8-Visuals":  "视觉",
    "9-Motion":   "动效",
}


@dataclass
class Finding:
    file: str
    line: int
    dimension: str
    severity: str
    pattern: str
    message: str
    suggestion: str = ""
    context: str = ""


@dataclass
class AuditReport:
    scanned_files: int = 0
    total_findings: int = 0
    by_dimension: dict = field(default_factory=dict)
    by_severity: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    score: int = 100


# pyparsing 基础工具

def kw(s):
    """不区分大小写的完整关键词。"""
    return pp.CaselessKeyword(s)


def one(s):
    """不区分大小写的多选一关键词（自动加边界检查）。"""
    return pp.oneOf(s, caseless=True, as_keyword=True)


def is_off_grid(tokens):
    """判断最后一个 token 的数值不是 4 的倍数（4px 网格）。"""
    try:
        return int(tokens[-1]) % 4 != 0
    except (ValueError, TypeError):
        return False


# 间距

def _make_arbitrary_spacing():
    """mt-[13px] / p-[13px] 这类 Tailwind 任意值。"""
    return (
        pp.Word("mp", exact=1) +
        pp.Optional(one("t b l r x y")) +
        pp.Suppress("-") + pp.Suppress("[") +
        pp.Regex(r"\d+") +
        pp.Suppress("px") + pp.Suppress("]")
    ).add_condition(is_off_grid)


def _make_css_spacing():
    """margin: 13px / padding: 13px。"""
    return (
        (kw("margin") | kw("padding")) +
        pp.Suppress(":") +
        pp.Regex(r"\d+") +
        pp.Suppress("px")
    ).add_condition(is_off_grid)


def _make_css_gap():
    """gap: 13px / row-gap / column-gap。"""
    return (
        (kw("gap") | kw("row-gap") | kw("column-gap")) +
        pp.Suppress(":") +
        pp.Regex(r"\d+") +
        pp.Suppress("px")
    ).add_condition(is_off_grid)


def _make_translate_tweak():
    """translateX(1px) —— 用 transform 补偿本应由布局解决的间距。"""
    return (
        (kw("translateX") | kw("translateY")) +
        pp.Suppress("(") +
        pp.Regex(r"[1-9]px") +
        pp.Suppress(")")
    )


# 颜色

NEON_HEX    = "#a855f7 #8b5cf6 #7c3aed #6366f1"
GLOW_HEX    = "#a855f7 #8b5cf6 #7c3aed #6366f1 #06b6d4 #22d3ee"
PURPLE_HUES = "purple violet fuchsia indigo"


def _make_tw_purple_gradient():
    """Tailwind 的 from-purple-500 / to-violet-500 之类。"""
    return (
        one("from to via") + pp.Suppress("-") +
        one(PURPLE_HUES) + pp.Suppress("-") +
        pp.Word(pp.nums)
    )


def _make_linear_gradient_purple():
    """CSS linear-gradient(...) 且内容里出现紫色/靛蓝色值。"""
    def has_purple(tokens):
        body = tokens[-1].lower()
        return any(k in body for k in (
            "purple", "violet",
            "#a855f7", "#8b5cf6", "#7c3aed", "#6d28d9", "#c084fc", "#a78bfa",
        ))
    return (
        kw("linear-gradient") +
        pp.Regex(r"\([^)]*\)")
    ).add_condition(has_purple)


def _make_colored_shadow():
    """box-shadow / text-shadow 中带霓虹色。"""
    def has_neon(tokens):
        body = tokens[-1].lower()
        return any(k in body for k in (
            "#a855f7", "#8b5cf6", "#7c3aed", "#6366f1", "#06b6d4", "#22d3ee",
        ))
    return (
        (kw("box-shadow") | kw("text-shadow")) +
        pp.Suppress(":") +
        pp.Regex(r"[^;]*")
    ).add_condition(has_neon)


def _make_glass_blur():
    """backdrop-blur-[20px] / blur: 20px 之类的大面积毛玻璃。"""
    return (
        (kw("blur") | kw("backdrop-blur")) +
        pp.Regex(r"[\w-]*") +
        pp.Suppress(pp.Literal(":") | pp.Literal("[")) +
        pp.Regex(r"\d{2,}px")
    )


def _make_rainbow_gradient():
    """青→紫 / 蓝→紫 的彩虹渐变（Tailwind 类名场景）。"""
    return (
        one("bg from to") + pp.Suppress("-") +
        (one("cyan teal sky blue") + pp.Suppress("-") + pp.Regex(r"[456]\d?")) +
        pp.Regex(r"[^\n]*") +
        (one("to from via") + pp.Suppress("-") + one("purple violet fuchsia"))
    )


def _make_neon_border():
    """border: 1px solid #a855f7 / outline: 2px solid #8b5cf6。"""
    return (
        (kw("border") | kw("outline")) +
        pp.Suppress(":") +
        pp.Regex(r"\d+px") +
        kw("solid") +
        one(NEON_HEX)
    )


def _make_tw_gradient_class():
    """bg-gradient / text-gradient / from-gradient 之类的 Tailwind 类。"""
    return (
        one("bg text border from via to") +
        pp.Suppress("-") +
        kw("gradient")
    )


def _make_radial_or_fixed_bg():
    """radial-gradient(...) 或 background-attachment: fixed。"""
    return (
        kw("radial-gradient") |
        (kw("background-attachment") + pp.Suppress(":") + kw("fixed"))
    )


# 图标

def _make_label_emoji():
    """New ✨ / Beta 🚀 / Pro 🔥 之类。"""
    emojis = pp.MatchFirst([pp.Literal(e) for e in "✨🚀🔥⭐💡"])
    return one("New Beta Pro Hot") + emojis


# 文案

def _make_greeting():
    """Welcome back, John! / Hello, Jane! 👋 之类。"""
    phrase = (
        (kw("Welcome") + kw("back")) |
        kw("Hello") | kw("Hi") | kw("Hey")
    )
    return (
        phrase +
        pp.Suppress(pp.Optional(",")) +
        pp.Word(pp.alphas) +
        (pp.Literal("!") | pp.Literal("👋"))
    )


def _make_marketing_words():
    """supercharge / seamless / unlock / magic / revolutionize ..."""
    return pp.MatchFirst([
        one("""
            supercharge seamless unlock unlocking unlocks
            magic magical magically
            cutting-edge next-gen next-generation effortless
        """),
        kw("game-changer"), kw("game-changing"), kw("game-changers"),
        pp.Regex(r"revolutioni[sz]\w*", flags=re.IGNORECASE),
    ])


def _make_ai_powered():
    """"AI-powered" / "AI powered"。"""
    return (
        kw("AI") +
        pp.Suppress(pp.Optional(pp.Literal("-"))) +
        kw("powered")
    )


def _make_social_proof():
    """Loved by 10,000+ teams 之类无法核实的社交证明。"""
    return (
        (kw("Loved") | kw("Trusted") | kw("Used")) +
        kw("by") +
        pp.Regex(r"\d[\d,]*\+?") +
        one("teams users companies customers people")
    )


def _make_hype_number():
    """10x faster / 100x better ..."""
    return one("10x 100x 1000x") + one("faster better easier more")


def _make_multi_bang():
    """!! 或更多感叹号。"""
    return pp.Regex(r"!{2,}")


def _make_placeholder_data():
    """lorem / John Doe / Acme 等明显占位数据。"""
    return pp.MatchFirst([
        one("mock test example placeholder lorem ipsum Acme"),
        kw("John") + kw("Doe"),
        kw("Jane") + kw("Doe"),
    ])


# 字体

def _make_heavy_weight():
    """font-bold / font-extrabold / font-weight: 700~900。"""
    return pp.MatchFirst([
        kw("font") + pp.Suppress("-") + one("bold extrabold black"),
        kw("font-weight") + pp.Suppress(":") +
            (pp.Regex(r"[789]00") | one("bold extrabold black")),
    ])


def _make_negative_tracking():
    """letter-spacing: -0.05em / tracking: -0.05em。"""
    return (
        (kw("letter-spacing") | kw("tracking")) +
        pp.Suppress(pp.Literal(":") | pp.Literal("[")) +
        pp.Suppress("-") +
        pp.Regex(r"[\d.]+")
    )


def _make_wide_tracking():
    """tracking-[wide] / letter-spacing: 0.5em 之类过宽字间距。"""
    return pp.MatchFirst([
        kw("tracking") + pp.Suppress("-") + pp.Suppress("[") +
            one("wide wider widest") + pp.Suppress("]"),
        kw("letter-spacing") + pp.Suppress(":") + pp.Regex(r"0\.[2-9]"),
    ])


def _make_uppercase_label():
    """text-transform: uppercase。"""
    return kw("text-transform") + pp.Suppress(":") + kw("uppercase")


def _make_gradient_text():
    """-webkit-text-fill-color: transparent / color: transparent。"""
    return (
        (kw("-webkit-text-fill-color") | kw("color")) +
        pp.Suppress(":") +
        kw("transparent")
    )


def _make_tw_gradient_text():
    """Tailwind 的 bg-clip-text / text-clip。"""
    return one("bg-clip-text text-clip")


def _make_italic_emphasis():
    """italic / text-italic / font-italic / font-style: italic。"""
    return kw("italic")

# 布局

def _make_centered_stack():
    """同一串 class 里 flex/grid + items-center + justify-center + flex-col + text-center。"""
    return pp.Regex(
        r'(?:flex|grid)[^"]*items-center[^"]*justify-center[^"]*flex-col[^"]*text-center',
        flags=re.IGNORECASE,
    )


def _make_narrow_column():
    """max-w-[400px] mx-auto 之类把 App 收窄成居中窄列。"""
    return (
        kw("max-w") + pp.Suppress("-") + pp.Suppress("[") +
        pp.Regex(r"[2-6]\d{2}px") + pp.Suppress("]") +
        pp.Regex(r"[^\n]*") +
        kw("mx-auto")
    )


# 细节

def _make_big_radius():
    """rounded-full / rounded-3xl / border-radius: 20~99px。"""
    return pp.MatchFirst([
        kw("rounded") + pp.Suppress("-") + one("full 3xl 2xl"),
        kw("border-radius") + pp.Suppress(":") +
            (one("9999 99px") | pp.Regex(r"[2-9]\dpx")),
    ])


def _make_badge_pill():
    """badge / pill / tag 全部 rounded-full 胶囊。"""
    return (
        one("badge pill tag") +
        pp.Regex(r"[^\"]*") +
        kw("rounded-full")
    )


# 视觉

def _make_decorative_nouns():
    """blob / orb / nebula / holo / glow 这类装饰词。"""
    return one("blob orb bubble sphere nebula holo crystal glow")


def _make_purple_bg():
    """bg-purple-500 / bg-indigo-600 之类大面积紫色背景。"""
    return (
        kw("bg") + pp.Suppress("-") +
        one(PURPLE_HUES) + pp.Suppress("-") +
        pp.Regex(r"[1-9]00")
    )


def _make_heavy_blur_filter():
    """filter: blur(20px) 之类大面积装饰模糊。"""
    return (
        kw("filter") + pp.Suppress(":") + kw("blur") +
        pp.Suppress("(") + pp.Regex(r"\d{2,}px") + pp.Suppress(")")
    )


# 动效

def _make_looping_animation():
    """animate-pulse / animate-ping / animate-bounce / animate-float。"""
    return (
        kw("animate") + pp.Suppress("-") +
        one("pulse ping spin bounce float wiggle")
    )


def _make_transition_all():
    """transition-all / transition: all。"""
    return pp.MatchFirst([
        kw("transition-all"),
        kw("transition") + pp.Suppress(":") + kw("all"),
    ])


def _make_hover_scale():
    """hover:scale-105 / :hover { transform: scale(...) }。"""
    return pp.MatchFirst([
        kw("hover") + pp.Suppress(":") + kw("scale") + pp.Suppress("-") +
            pp.Word(pp.nums),
        pp.Regex(r":hover\s*\{[^}]*transform[^}]*scale", flags=re.IGNORECASE),
    ])


def _make_long_animation():
    """"animation: xxx 4s" 里时长 > 3s 的无意义呼吸/浮动。"""
    def over_3s(tokens):
        m = re.search(r"(\d+(?:\.\d+)?)s\b", tokens[-1])
        return bool(m) and float(m.group(1)) > 3
    return (
        kw("animation") + pp.Suppress(":") +
        pp.Regex(r"\w+\s+\d+(?:\.\d+)?s")
    ).add_condition(over_3s)


# 规则表

@dataclass
class Rule:
    name: str
    pattern: pp.ParserElement
    dimension: Dimension
    severity: Severity
    message: str
    suggestion: str


def build_rules():
    """构建审计规则表。"""
    return [
        # --- 间距 ---
        Rule("arbitrary-spacing", _make_arbitrary_spacing(),
             Dimension.SPACING, Severity.MEDIUM,
             "非 4px 网格的自定义间距（如 mt-[13px]）",
             "替换为 4 的倍数: mt-3=12px, mt-4=16px, mt-5=20px"),
        Rule("css-spacing-off-grid", _make_css_spacing(),
             Dimension.SPACING, Severity.MEDIUM,
             "非 4px 网格的 margin/padding",
             "对齐到 4px 网格: 4/8/12/16/20/24/32"),
        Rule("css-gap-off-grid", _make_css_gap(),
             Dimension.SPACING, Severity.LOW,
             "非 4px 网格的 gap 值",
             "使用 4 的倍数作为 gap"),
        Rule("translate-tweak", _make_translate_tweak(),
             Dimension.SPACING, Severity.MEDIUM,
             "用 translate 微调对齐，间距本身没调好",
             "修正容器 padding / gap，而非 translate 补偿"),

        # --- 颜色 ---
        Rule("tw-purple-gradient", _make_tw_purple_gradient(),
             Dimension.COLOR, Severity.CRITICAL,
             "紫色/靛蓝渐变 — AI 生成 UI 最典型的标志",
             "删除渐变，用单色或从产品世界推导的中性色"),
        Rule("css-purple-gradient", _make_linear_gradient_purple(),
             Dimension.COLOR, Severity.CRITICAL,
             "紫色系 linear-gradient",
             "移除 hue 渐变；仅在同一个中性色内部做明度渐变"),
        Rule("colored-shadow", _make_colored_shadow(),
             Dimension.COLOR, Severity.HIGH,
             "彩色阴影/辉光 (glow)",
             "阴影只用中性色低透明度；暗色主题用 surface step"),
        Rule("glass-blur", _make_glass_blur(),
             Dimension.COLOR, Severity.MEDIUM,
             "大面积毛玻璃效果 (glassmorphism)",
             "去掉毛玻璃，用实色 surface + hairline 边框"),
        Rule("rainbow-gradient", _make_rainbow_gradient(),
             Dimension.COLOR, Severity.CRITICAL,
             "青→紫 或 蓝→紫 彩虹渐变 — AI 经典配色",
             "选定一个来自产品世界的 accent，其余用中性色阶"),
        Rule("neon-border", _make_neon_border(),
             Dimension.COLOR, Severity.HIGH,
             "霓虹色边框",
             "边框用文字色 6-10% 透明度做 hairline"),
        Rule("tw-gradient-class", _make_tw_gradient_class(),
             Dimension.COLOR, Severity.HIGH,
             "Tailwind *-gradient 类，常伴随渐变滥用",
             "确认渐变仅限同色明度微差；删除跨 hue 渐变"),
        Rule("radial-or-fixed-bg", _make_radial_or_fixed_bg(),
             Dimension.COLOR, Severity.MEDIUM,
             "radial-gradient 背景装饰，AI 常用来填充",
             "用纯色或极简图案代替"),

        # --- 图标 ---
        Rule("label-emoji", _make_label_emoji(),
             Dimension.ICONS, Severity.CRITICAL,
             '"New ✨ / Beta 🚀 / Pro 🔥" 标签 — AI 最爱',
             "移除 emoji；确有标签需要时用安静的纯文字"),

        # --- 文案 ---
        Rule("greeting", _make_greeting(),
             Dimension.COPY, Severity.HIGH,
             "问候式标题（Welcome back, Name! 👋）",
             "用页面名或时间段做标题，如 'October 2026'"),
        Rule("marketing-words", _make_marketing_words(),
             Dimension.COPY, Severity.HIGH,
             "营销夸张词（supercharge / seamless / unlock / magic ...）",
             "用平实具体的语言描述产品做什么"),
        Rule("ai-powered", _make_ai_powered(),
             Dimension.COPY, Severity.HIGH,
             '"AI-powered" 滥用',
             "只在确实使用了 AI 的地方说明它做了什么"),
        Rule("social-proof", _make_social_proof(),
             Dimension.COPY, Severity.MEDIUM,
             "无法核实的社交证明（Loved by 10,000+ teams）",
             "无法证实则删除；有真实数据才保留"),
        Rule("hype-number", _make_hype_number(),
             Dimension.COPY, Severity.MEDIUM,
             "夸张数字宣称（10x faster）",
             "换成可验证的具体对比"),
        Rule("multi-bang", _make_multi_bang(),
             Dimension.COPY, Severity.MEDIUM,
             "多个感叹号",
             "界面文案去掉感叹号"),
        Rule("placeholder-data", _make_placeholder_data(),
             Dimension.COPY, Severity.MEDIUM,
             "明显的占位/假数据（lorem / John Doe / Acme）",
             "用合理可信的数据替换"),

        # --- 字体 ---
        Rule("heavy-weight", _make_heavy_weight(),
             Dimension.TYPE, Severity.MEDIUM,
             "过重的字重（700-900），层级应靠字号和颜色",
             "层级用字号 + 色阶表达，字重控制在 400-600"),
        Rule("negative-tracking", _make_negative_tracking(),
             Dimension.TYPE, Severity.MEDIUM,
             "负 letter-spacing（收紧字间距），小字上尤其有害",
             "小字需要更大字号或稍宽间距来提升可读性"),
        Rule("wide-tracking", _make_wide_tracking(),
             Dimension.TYPE, Severity.MEDIUM,
             "过宽字间距用于小字/标签",
             "改用 Sentence case，去掉宽间距"),
        Rule("uppercase-label", _make_uppercase_label(),
             Dimension.TYPE, Severity.MEDIUM,
             "全大写标签（NAVIGATION / PAID THIS MONTH）",
             "改为 Sentence case（Navigation / Paid this month）"),
        Rule("gradient-text", _make_gradient_text(),
             Dimension.TYPE, Severity.CRITICAL,
             "渐变文字 (gradient text) — color:transparent",
             "删除，用实色文字表达层级"),
        Rule("tw-gradient-text", _make_tw_gradient_text(),
             Dimension.TYPE, Severity.CRITICAL,
             "Tailwind gradient text（bg-clip-text）",
             "删除，用实色"),
        Rule("italic-emphasis", _make_italic_emphasis(),
             Dimension.TYPE, Severity.LOW,
             "用 italic 做强调",
             "用字号或颜色表达层级，不用斜体强调"),

        # --- 布局 ---
        Rule("centered-stack", _make_centered_stack(),
             Dimension.LAYOUT, Severity.MEDIUM,
             "全居中 + 竖排堆叠布局 — 模板默认样式",
             "考虑不对称分栏: 文字一侧 + 视觉另一侧"),
        Rule("narrow-column", _make_narrow_column(),
             Dimension.LAYOUT, Severity.MEDIUM,
             "App/Dashboard 被收窄成居中窄列",
             "App 应填满视口，sidebar 240-280px，内容区 fluid"),

        # --- 细节 ---
        Rule("big-radius", _make_big_radius(),
             Dimension.DETAILS, Severity.MEDIUM,
             "全部元素都是大圆角/胶囊形",
             "嵌套圆角递减: 按钮 8-10, 卡片 12-16, 面板 14-20"),
        Rule("badge-pill", _make_badge_pill(),
             Dimension.DETAILS, Severity.LOW,
             "Badge 全用 rounded-full 胶囊",
             "改用与控件一致的圆角，或直接用安静文字"),

        # --- 视觉 ---
        Rule("decorative-nouns", _make_decorative_nouns(),
             Dimension.VISUALS, Severity.HIGH,
             "AI 典型装饰词（blob / orb / nebula / holo ...）",
             "删除装饰性填充物，用产品自身内容承载视觉"),
        Rule("purple-bg", _make_purple_bg(),
             Dimension.VISUALS, Severity.MEDIUM,
             "大面积紫色/靛蓝背景色块",
             "背景用中性色阶；色彩只出现在 accent 和 moments 中"),
        Rule("heavy-blur-filter", _make_heavy_blur_filter(),
             Dimension.VISUALS, Severity.MEDIUM,
             "大面积 blur 装饰滤镜",
             "移除模糊装饰层"),

        # --- 动效 ---
        Rule("looping-animation", _make_looping_animation(),
             Dimension.MOTION, Severity.HIGH,
             "循环动画（animate-pulse / ping / bounce / float）",
             "移除无功能意义的循环动画"),
        Rule("transition-all", _make_transition_all(),
             Dimension.MOTION, Severity.MEDIUM,
             "transition-all 全量过渡，性能差且意图不明",
             "明确列出属性: transition-colors / transition-[transform,opacity]"),
        Rule("hover-scale", _make_hover_scale(),
             Dimension.MOTION, Severity.MEDIUM,
             "hover 时 scale 缩放 — AI 常见的过度交互",
             "hover 只做颜色/表面微变，不缩放"),
        Rule("long-animation", _make_long_animation(),
             Dimension.MOTION, Severity.LOW,
             "过长的动画时长（>3s），通常是无意义呼吸/浮动",
             "反馈动画 ≤150ms，进入动画 ≤300ms"),
    ]


RULES = build_rules()

# Emoji 通用扫描（不放在规则表里，因为字符范围用 pyparsing 表达不自然）
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "]",
    re.UNICODE
)

SUPPORTED_EXTS = {".html", ".htm", ".css", ".scss", ".less",
                  ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next",
             "__pycache__", "vendor", ".cache", "venv"}


# 扫描逻辑

def collect_files(target):
    p = Path(target)
    if p.is_file():
        return [str(p)]
    files = []
    for ext in SUPPORTED_EXTS:
        files.extend(str(f) for f in p.rglob("*" + ext))
    files = [f for f in files if not SKIP_DIRS & set(Path(f).parts)]
    return sorted(set(files))


def truncate(s, maxlen=120):
    s = s.strip()
    return (s[:maxlen] + "...") if len(s) > maxlen else s


def _iter_matches(pattern, text):
    """兼容 pyparsing 3.x 的 search_string 与旧版 scan_string。"""
    if hasattr(pattern, "search_string"):
        yield from pattern.search_string(text)
    else:
        yield from pattern.scan_string(text)


def scan_file(filepath, rules=None):
    findings = []
    rules = rules or RULES

    try:
        text = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    lines = text.splitlines()

    for rule in rules:
        try:
            matches = list(_iter_matches(rule.pattern, text))
        except Exception:
            continue
        for tokens, start, end in matches:
            line_no = text[:start].count("\n") + 1
            ctx = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else text[start:end]
            findings.append(Finding(
                file=filepath,
                line=line_no,
                dimension=rule.dimension.value,
                severity=rule.severity.value,
                pattern=rule.name,
                message=rule.message,
                suggestion=rule.suggestion,
                context=truncate(ctx),
            ))

    # Emoji 专项扫描
    for i, line in enumerate(lines, 1):
        hits = EMOJI_RE.findall(line)
        if hits:
            emoji_str = " ".join(hits[:5])
            findings.append(Finding(
                file=filepath, line=i,
                dimension=Dimension.ICONS.value,
                severity=Severity.HIGH.value,
                pattern="emoji-as-icon",
                message="检测到 emoji 装饰字符: " + emoji_str,
                suggestion="替换为统一图标库的线性图标",
                context=truncate(line),
            ))

    return findings


# 评分

SEVERITY_WEIGHT = {
    Severity.CRITICAL.value: 10,
    Severity.HIGH.value:     5,
    Severity.MEDIUM.value:   2,
    Severity.LOW.value:      1,
}


def compute_score(findings, file_count):
    if file_count == 0:
        return 100
    penalty = sum(SEVERITY_WEIGHT.get(f.severity, 1) for f in findings)
    penalty_per_file = penalty / max(file_count, 1)
    score = max(0, int(100 - penalty_per_file * 3))
    return min(score, 100)


# 输出

SEVERITY_ICON = {
    "critical": "[!]",
    "high":     "[!]",
    "medium":   "[~]",
    "low":      "[-]",
}
SEVERITY_LABEL = {
    "critical": "CRITICAL (一眼AI)",
    "high":     "HIGH     (明显AI痕迹)",
    "medium":   "MEDIUM   (需要留意)",
    "low":      "LOW      (轻微问题)",
}


def print_report(report, findings_raw, show_fix_hints=False):
    sep = "=" * 72
    thin = "-" * 72

    print()
    print(sep)
    print("  AI UI Classic Problems Audit Report")
    print(sep)
    print("  Scanned files : %d" % report.scanned_files)
    print("  Total issues  : %d" % report.total_findings)
    if report.score < 40:
        grade = "HEAVY AI flavor"
    elif report.score < 60:
        grade = "Noticeable AI traces"
    elif report.score < 80:
        grade = "Room for improvement"
    else:
        grade = "Fairly restrained"
    print("  Design score  : %d/100  [%s]" % (report.score, grade))
    print(sep)

    # 按维度
    print()
    print("  SUMMARY BY DIMENSION")
    hdr = "  %-14s %5s %5s %5s %5s %6s" % ("Dimension", "CRIT", "HIGH", "MED", "LOW", "Total")
    print(hdr)
    print("  " + thin[:44])
    for dim in [d.value for d in Dimension]:
        items = [f for f in findings_raw if f.dimension == dim]
        if not items:
            continue
        c = sum(1 for f in items if f.severity == "critical")
        h = sum(1 for f in items if f.severity == "high")
        m = sum(1 for f in items if f.severity == "medium")
        l = sum(1 for f in items if f.severity == "low")
        label = "%s (%s)" % (dim, DIM_CN.get(dim, ""))
        print("  %-14s %5d %5d %5d %5d %6d" % (dim, c, h, m, l, len(items)))

    # 按严重程度
    print()
    print("  SUMMARY BY SEVERITY")
    for sev in ["critical", "high", "medium", "low"]:
        cnt = report.by_severity.get(sev, 0)
        if cnt:
            print("  %s %s  %d found" % (SEVERITY_ICON[sev], SEVERITY_LABEL[sev], cnt))

    # 详细列表
    print()
    print(sep)
    print("  DETAILED FINDINGS")
    print(sep)

    by_file = defaultdict(list)
    for f in findings_raw:
        by_file[f.file].append(f)

    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for filepath, fs in sorted(by_file.items()):
        print()
        print("  FILE: %s" % filepath)
        print("  " + "-" * min(len(filepath) + 5, 68))
        for f in sorted(fs, key=lambda x: (sev_order.get(x.severity, 9), x.line)):
            icon = SEVERITY_ICON.get(f.severity, "[?]")
            print("    %s L%-5d [%-12s] %s" % (icon, f.line, f.dimension, f.message))
            print("         code: %s" % f.context)
            if show_fix_hints and f.suggestion:
                print("         fix:  %s" % f.suggestion)
            print()

    print(sep)
    print("  Total: %d issues across %d files" % (report.total_findings, len(by_file)))
    print(sep)
    print()


# 入口

def build_args(argv=None):
    """构建并解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="AI UI Classic Problems Auditor - detect AI-generated UI patterns",
    )
    parser.add_argument("target", help="File or directory to scan")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--fix-hints", action="store_true",
                        help="Show fix suggestions")
    parser.add_argument("--fail-on",
                        choices=["critical", "high", "medium", "low"],
                        help="Exit non-zero if issues >= this severity (CI)")
    return parser.parse_args(argv)


def main(argv=None):
    args = build_args(argv)

    files = collect_files(args.target)
    if not files:
        print("No scannable files found. Supported: " + ", ".join(sorted(SUPPORTED_EXTS)))
        sys.exit(1)

    all_findings = []
    for fpath in files:
        all_findings.extend(scan_file(fpath))

    report = AuditReport(
        scanned_files=len(files),
        total_findings=len(all_findings),
        findings=[asdict(f) for f in all_findings],
    )
    for dim in [d.value for d in Dimension]:
        cnt = sum(1 for f in all_findings if f.dimension == dim)
        if cnt:
            report.by_dimension[dim] = cnt
    for sev in ["critical", "high", "medium", "low"]:
        cnt = sum(1 for f in all_findings if f.severity == sev)
        if cnt:
            report.by_severity[sev] = cnt
    report.score = compute_score(all_findings, len(files))

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print_report(report, all_findings, show_fix_hints=args.fix_hints)

    # CI exit code
    if args.fail_on:
        order = ["low", "medium", "high", "critical"]
        idx = order.index(args.fail_on)
        blocking = [f for f in all_findings
                    if order.index(f.severity) >= idx]
        if blocking:
            print("FAIL: %d issues >= %s" % (len(blocking), args.fail_on))
            sys.exit(2)
        else:
            print("PASS: no issues >= %s" % args.fail_on)


if __name__ == "__main__":
    main()
