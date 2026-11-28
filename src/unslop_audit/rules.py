"""审计规则表。

规则骨架对照 Damir Sokolovsky 的 unslop（CC BY 4.0）：
https://heydamir.design/unslop
"""

import re
from dataclasses import dataclass

from .context import (
    has_chroma,
    has_class,
    has_neon,
    icon_inconsistent_guard,
    in_pseudo_element,
    is_text_node_bang,
    number_format_guard,
    off_grid_guard,
    rtl_guard,
    same_hue_class_guard,
    too_many_actions_guard,
    trailing_period_guard,
    unqualified_change_guard,
)
from .matching import ClassMatcher, Matcher
from .models import Dimension, Severity


@dataclass
class Rule:
    name: str
    matchers: list
    dimension: Dimension
    severity: Severity
    message: str
    suggestion: str


def make_rule(name, matchers, dimension, severity, message, suggestion):
    if not isinstance(matchers, (list, tuple)):
        matchers = [matchers]
    return Rule(name, list(matchers), dimension, severity, message, suggestion)


def build_rules():
    dim_spacing = Dimension.SPACING
    dim_color = Dimension.COLOR
    dim_icons = Dimension.ICONS
    dim_copy = Dimension.COPY
    dim_type = Dimension.TYPE
    dim_layout = Dimension.LAYOUT
    dim_details = Dimension.DETAILS
    dim_visuals = Dimension.VISUALS
    dim_motion = Dimension.MOTION

    severity_critical = Severity.CRITICAL
    severity_high = Severity.HIGH
    severity_medium = Severity.MEDIUM
    severity_low = Severity.LOW

    return [
        # Spacing
        make_rule(
            "arbitrary-spacing",
            ClassMatcher(
                r"\b[mp][trblxy]?-\[\s*(\d+)px\s*\]",
                lambda class_value, match: (
                    int(match.group(1)) % 4 != 0 and int(match.group(1)) != 2
                ),
            ),
            dim_spacing,
            severity_medium,
            "非 4px 网格的自定义间距（如 mt-[13px]）",
            "替换为 4 的倍数: mt-3=12px, mt-4=16px, mt-5=20px",
        ),
        make_rule(
            "css-spacing-off-grid",
            Matcher(
                r"\b(?:margin|padding)(?:-[a-z]+)?\s*:\s*([^;}]+)", guard=off_grid_guard
            ),
            dim_spacing,
            severity_medium,
            "非 4px 网格的 margin/padding（含多值、方向后缀）",
            "对齐到 4px 网格: 4/8/12/16/20/24/32；2px 微调可保留",
        ),
        make_rule(
            "css-gap-off-grid",
            Matcher(
                r"\b(?:row-gap|column-gap|gap)\s*:\s*([^;}]+)", guard=off_grid_guard
            ),
            dim_spacing,
            severity_low,
            "非 4px 网格的 gap 值（含多值）",
            "使用 4 的倍数作为 gap",
        ),
        make_rule(
            "fixed-height-off-grid",
            Matcher(
                r"\b(?:height|min-height|max-height)\s*:\s*([^;}]+)",
                guard=off_grid_guard,
            ),
            dim_spacing,
            severity_low,
            "非 4px 网格的固定高度",
            "SKILL §1 要求 fixed heights 也在 4px 网格上",
        ),
        make_rule(
            "translate-tweak",
            Matcher(r"\btranslate[XY]\(\s*[1-9]px\s*\)"),
            dim_spacing,
            severity_medium,
            "用 translate 微调对齐，间距本身没调好",
            "修正容器 padding / gap，而非 translate 补偿",
        ),
        # Color
        make_rule(
            "tw-purple-gradient",
            ClassMatcher(r"\b(?:from|to|via)-(?:purple|violet|fuchsia|indigo)-\d+\b"),
            dim_color,
            severity_critical,
            "紫色/靛蓝渐变 — AI 生成 UI 最典型的标志",
            "删除渐变，用单色或从产品世界推导的中性色",
        ),
        make_rule(
            "css-purple-gradient",
            Matcher(
                r"\blinear-gradient\s*\(([^)]*)\)",
                guard=lambda text, match: has_chroma(match.group(1)),
            ),
            dim_color,
            severity_critical,
            "跨色相 linear-gradient（含 hex / rgba / 命名色）",
            "移除 hue 渐变；仅在同一个中性色内部做明度渐变",
        ),
        make_rule(
            "colored-shadow",
            Matcher(
                r"\b(?:box-shadow|text-shadow)\s*:\s*([^;}]+)",
                guard=lambda text, match: has_neon(match.group(1)),
            ),
            dim_color,
            severity_high,
            "彩色阴影/辉光 (glow)",
            "阴影只用中性色低透明度；暗色主题用 surface step",
        ),
        make_rule(
            "glass-blur",
            [
                ClassMatcher(r"\bbackdrop-blur-\[?\d+px\]?"),
                Matcher(r"\bbackdrop-filter\s*:\s*blur\(\s*\d+px\s*\)"),
                Matcher(r"(?<![\w-])blur\s*:\s*\d{2,}px"),
            ],
            dim_color,
            severity_medium,
            "大面积毛玻璃效果 (glassmorphism)",
            "去掉毛玻璃，用实色 surface + hairline 边框",
        ),
        make_rule(
            "rainbow-gradient",
            ClassMatcher(
                r"\b(?:from|to|via)-(?:cyan|teal|sky|blue)-\d+\b",
                lambda class_value, match: bool(
                    re.search(
                        r"\b(?:to|from|via)-(?:purple|violet|fuchsia)-\d+\b",
                        class_value,
                        re.IGNORECASE,
                    )
                ),
            ),
            dim_color,
            severity_critical,
            "青→紫 / 蓝→紫 彩虹渐变 — AI 经典配色",
            "选定一个来自产品世界的 accent，其余用中性色阶",
        ),
        make_rule(
            "neon-border",
            Matcher(
                r"\b(?:border(?:-[a-z]+)?|outline)\s*:\s*([^;}]+)",
                guard=lambda text, match: has_neon(match.group(1)),
            ),
            dim_color,
            severity_high,
            "霓虹色边框（含 rgba 写法）",
            "边框用文字色 6-10% 透明度做 hairline",
        ),
        make_rule(
            "tw-gradient-class",
            ClassMatcher(
                r"\b(?:bg|text|border|from|via|to)-gradient\b|\bbg-gradient-to-\w+",
                same_hue_class_guard,
            ),
            dim_color,
            severity_high,
            "Tailwind *-gradient 类，常伴随渐变滥用",
            "确认渐变仅限同色明度微差；删除跨 hue 渐变",
        ),
        make_rule(
            "radial-or-fixed-bg",
            Matcher(r"\bradial-gradient\s*\(|\bbackground-attachment\s*:\s*fixed\b"),
            dim_color,
            severity_medium,
            "radial-gradient 背景装饰 / 视差固定背景",
            "用纯色或极简图案代替",
        ),
        # Icons
        make_rule(
            "label-emoji",
            Matcher(r"\b(?:New|Beta|Pro|Hot)\b\s*(?:✨|🚀|🔥|⭐|💡|👋)"),
            dim_icons,
            severity_critical,
            '"New ✨ / Beta 🚀 / Pro 🔥" 标签 — AI 最爱',
            "移除 emoji；确有标签需要时用安静的纯文字",
        ),
        make_rule(
            "icon-inconsistent",
            Matcher(r"<svg\b[^>]*>", guard=icon_inconsistent_guard),
            dim_icons,
            severity_medium,
            "图标尺寸或描边不统一",
            "SKILL §3: one size and one stroke everywhere（16/18px, 1.5 stroke）",
        ),
        # Copy
        make_rule(
            "greeting",
            Matcher(r"(?:Welcome\s+back|Hello|Hi|Hey)\s*,?\s*[A-Za-z]+\s*(?:!|👋)"),
            dim_copy,
            severity_high,
            "问候式标题（Welcome back, Name! 👋）",
            "用页面名或时间段做标题，如 'October 2026'",
        ),
        make_rule(
            "marketing-words",
            Matcher(
                r"\b(?:supercharge|seamless|unlock(?:ing|s)?|magic(?:al|ally)?|"
                r"cutting-edge|next-gen(?:eration)?|effortless|"
                r"game-chang(?:er|ing|ers)|revolutioni[sz]\w*)\b"
            ),
            dim_copy,
            severity_high,
            "营销夸张词（supercharge / seamless / unlock / magic ...）",
            "用平实具体的语言描述产品做什么",
        ),
        make_rule(
            "ai-powered",
            Matcher(r"\bAI[\s-]*powered\b"),
            dim_copy,
            severity_high,
            '"AI-powered" 滥用',
            "只在确实使用了 AI 的地方说明它做了什么",
        ),
        make_rule(
            "social-proof",
            Matcher(
                r"\b(?:Loved|Trusted|Used)\s+by\s+\d[\d,]*\+?\s+"
                r"(?:teams|users|companies|customers|people)\b"
            ),
            dim_copy,
            severity_medium,
            "无法核实的社交证明（Loved by 10,000+ teams）",
            "无法证实则删除；有真实数据才保留，并在报告里问用户确认",
        ),
        make_rule(
            "hype-number",
            Matcher(r"\b(?:10x|100x|1000x)\s+(?:faster|better|easier|more)\b"),
            dim_copy,
            severity_medium,
            "夸张数字宣称（10x faster）",
            "换成可验证的具体对比",
        ),
        make_rule(
            "multi-bang",
            Matcher(r"!+", guard=is_text_node_bang),
            dim_copy,
            severity_medium,
            "界面文案里的感叹号（单个 ! 也算）",
            "SKILL §4: No exclamation marks in interface text, and never !!",
        ),
        make_rule(
            "placeholder-data",
            Matcher(
                r"\b(?:lorem ipsum|John Doe|Jane Doe|Acme(?:\s+Corp)?|"
                r"\[X\]|123,456)\b|\bmockData\b|\bplaceholderData\b"
            ),
            dim_copy,
            severity_medium,
            "明显的占位/假数据（lorem / John Doe / Acme）",
            "用合理可信的数据替换；不要误伤普通英文单词与 CSS 伪类",
        ),
        make_rule(
            "trailing-period",
            Matcher(
                r"<(?:button|label|h[1-6]|span|a|li)\b[^>]*>\s*([^<>.!?]{1,40}\.)\s*<",
                guard=trailing_period_guard,
            ),
            dim_copy,
            severity_low,
            "短字符串尾随句号",
            "SKILL §4: 标题/标签/按钮/说明结尾不加句号",
        ),
        make_rule(
            "long-label",
            Matcher(r"<label\b[^>]*>\s*([^<]*\.{3})\s*</label>"),
            dim_copy,
            severity_low,
            "冗长占位式标签（Search anything...）",
            "短标签：Search，不是 Search anything...",
        ),
        make_rule(
            "unqualified-change",
            Matcher(r"[+-]\d+(?:\.\d+)?%", guard=unqualified_change_guard),
            dim_copy,
            severity_medium,
            "变化幅度缺少对比对象（+12%）",
            "写成 +12% vs last month / 3 fewer vs last month",
        ),
        # Type
        make_rule(
            "heavy-weight",
            [
                ClassMatcher(r"\bfont-(?:bold|extrabold|black)\b"),
                Matcher(r"\bfont-weight\s*:\s*(?:[789]00|bold|extrabold|black)\b"),
            ],
            dim_type,
            severity_medium,
            "过重的字重（700-900），层级应靠字号和颜色",
            "层级用字号 + 色阶表达，字重控制在 400-600",
        ),
        make_rule(
            "negative-tracking",
            [
                Matcher(r"\bletter-spacing\s*:\s*-\s*[\d.]+"),
                Matcher(r"\btracking\s*:\s*-\s*[\d.]+"),
                ClassMatcher(r"\btracking-\[-[\d.]+\]"),
            ],
            dim_type,
            severity_medium,
            "负 letter-spacing（收紧字间距），小字上尤其有害",
            "小字需要更大字号或稍宽间距来提升可读性",
        ),
        make_rule(
            "wide-tracking",
            [
                ClassMatcher(r"\btracking-(?:\[?(?:wide|wider|widest)\]?)\b"),
                Matcher(r"\bletter-spacing\s*:\s*0\.[2-9]"),
            ],
            dim_type,
            severity_medium,
            "过宽字间距用于小字/标签（含 Tailwind 具名类）",
            "改用 Sentence case，去掉宽间距",
        ),
        make_rule(
            "uppercase-label",
            [
                Matcher(r"\btext-transform\s*:\s*uppercase\b"),
                ClassMatcher(r"\buppercase\b"),
            ],
            dim_type,
            severity_medium,
            "全大写标签（NAVIGATION / PAID THIS MONTH）",
            "改为 Sentence case（Navigation / Paid this month）",
        ),
        make_rule(
            "gradient-text",
            Matcher(
                r"\b(?:-webkit-text-fill-color|color)\s*:\s*transparent\b",
                guard=lambda text, match: not in_pseudo_element(text, match),
            ),
            dim_type,
            severity_critical,
            "渐变文字 (gradient text) — color:transparent",
            "删除，用实色文字表达层级",
        ),
        make_rule(
            "tw-gradient-text",
            ClassMatcher(r"\bbg-clip-text\b|\btext-clip\b"),
            dim_type,
            severity_critical,
            "Tailwind gradient text（bg-clip-text）",
            "删除，用实色",
        ),
        make_rule(
            "italic-emphasis",
            [
                Matcher(r"\bfont-style\s*:\s*italic\b"),
                ClassMatcher(r"\b(?:text-italic|font-italic|italic)\b"),
            ],
            dim_type,
            severity_low,
            "用 italic 做强调",
            "用字号或颜色表达层级，不用斜体强调",
        ),
        make_rule(
            "number-format",
            Matcher(r"\$\s*\d[\d,]*(?:\.\d+)?", guard=number_format_guard),
            dim_type,
            severity_medium,
            "数字格式不统一或未启用 tabular-nums",
            "SKILL §5: Numbers use tabular-nums and one format across the screen",
        ),
        # Layout
        make_rule(
            "centered-stack",
            ClassMatcher(
                r"^(?=.*\b(?:flex|grid)\b)(?=.*\bitems-center\b)"
                r"(?=.*\bjustify-center\b)(?=.*\bflex-col\b)"
                r"(?=.*\btext-center\b).*$"
            ),
            dim_layout,
            severity_medium,
            "全居中 + 竖排堆叠布局 — 模板默认样式（顺序无关）",
            "考虑不对称分栏: 文字一侧 + 视觉另一侧",
        ),
        make_rule(
            "narrow-column",
            ClassMatcher(
                r"\bmax-w-(?:\[?[2-6]\d{2}px\]?|sm|md|lg|xl)\b",
                lambda class_value, match: has_class(class_value, "mx-auto"),
            ),
            dim_layout,
            severity_medium,
            "App/Dashboard 被收窄成居中窄列（含具名尺度）",
            "App 应填满视口，sidebar 240-280px，内容区 fluid",
        ),
        make_rule(
            "too-many-actions",
            Matcher(r"<button\b", guard=too_many_actions_guard),
            dim_layout,
            severity_medium,
            "首屏并排多个主按钮",
            "SKILL §6: one primary action and at most one secondary action",
        ),
        make_rule(
            "rtl-missing",
            Matcher(r'<html\b[^>]*\blang="(?:ar|fa|ur|he)"', guard=rtl_guard),
            dim_layout,
            severity_high,
            'RTL 语言缺少 dir="rtl"',
            "SKILL Checklist: dir 与 lang 都要设置，布局镜像、方向图标翻转",
        ),
        # Details
        make_rule(
            "big-radius",
            [
                ClassMatcher(r"\brounded-(?:full|3xl)\b"),
                Matcher(r"\bborder-radius\s*:\s*(?:9999px?|[2-9]\dpx)\b"),
            ],
            dim_details,
            severity_medium,
            "全部元素都是大圆角/胶囊形",
            "嵌套圆角递减: 按钮 8-10, 卡片 12-16, 面板 14-20",
        ),
        make_rule(
            "badge-pill",
            ClassMatcher(
                r"\b(?:badge|pill|tag)\b",
                lambda class_value, match: has_class(class_value, "rounded-full"),
            ),
            dim_details,
            severity_low,
            "Badge 全用 rounded-full 胶囊",
            "改用与控件一致的圆角，或直接用安静文字",
        ),
        make_rule(
            "stat-decoration",
            ClassMatcher(r"\b(?:sparkline|mini-bar|miniBar|tally)\b"),
            dim_details,
            severity_medium,
            "Stat card 里塞 sparkline / mini bars 等装饰",
            "SKILL §7: Stat cards are numbers — 不放迷你图表去凑装饰",
        ),
        # Visuals
        make_rule(
            "decorative-nouns",
            [
                ClassMatcher(
                    r"\b(?:blob|orb|bubble|sphere|nebula|holo|crystal|glow)\b"
                ),
                Matcher(
                    r"(?m)^\s*[.#](?:blob|orb|bubble|sphere|nebula|holo|crystal|glow)\b"
                ),
            ],
            dim_visuals,
            severity_high,
            "AI 典型装饰词（blob / orb / nebula / holo ...）",
            "删除装饰性填充物，用产品自身内容承载视觉",
        ),
        make_rule(
            "purple-bg",
            [
                ClassMatcher(r"\bbg-(?:purple|violet|fuchsia|indigo)-\d+\b"),
                Matcher(
                    r"\bbackground(?:-color)?\s*:\s*([^;}]+)",
                    guard=lambda text, match: has_chroma(match.group(1)),
                ),
            ],
            dim_visuals,
            severity_medium,
            "大面积紫色/靛蓝背景色块（含纯 CSS 与浅色档）",
            "背景用中性色阶；色彩只出现在 accent 和 moments 中",
        ),
        make_rule(
            "heavy-blur-filter",
            Matcher(
                r"(?<![-\w])filter\s*:\s*blur\(\s*(\d+)px\s*\)",
                guard=lambda text, match: int(match.group(1)) >= 20,
            ),
            dim_visuals,
            severity_medium,
            "大面积 blur 装饰滤镜",
            "移除模糊装饰层",
        ),
        # Motion
        make_rule(
            "looping-animation",
            [
                ClassMatcher(
                    r"\banimate-(?:pulse|ping|spin|bounce|float|wiggle)\b|"
                    r"\banimate-\[[^\]]*(?:float|pulse|shimmer|infinite)[^\]]*\]"
                ),
                Matcher(r"\banimation\s*:\s*[^;}]*\binfinite\b"),
            ],
            dim_motion,
            severity_high,
            "循环动画（animate-pulse / ping / shimmer / float，不限时长）",
            "移除无功能意义的循环动画",
        ),
        make_rule(
            "transition-all",
            [
                ClassMatcher(r"\btransition-all\b"),
                Matcher(r"\btransition\s*:\s*all\b"),
            ],
            dim_motion,
            severity_medium,
            "transition-all 全量过渡，性能差且意图不明",
            "明确列出属性: transition-colors / transition-[transform,opacity]",
        ),
        make_rule(
            "transition-layout",
            Matcher(
                r"\btransition\s*:\s*(?:width|height|top|left|right|bottom|margin[\w-]*)\b"
            ),
            dim_motion,
            severity_high,
            "过渡了布局属性（width/height/top/left/margin）",
            "SKILL §9: Never animate width, height, top, left, margins or large blurs",
        ),
        make_rule(
            "hover-scale",
            [
                ClassMatcher(r"\bhover:scale-(?:\d+|\[[^\]]+\])"),
                Matcher(r":hover\s*\{[^}]*transform[^}]*scale", re.IGNORECASE),
            ],
            dim_motion,
            severity_medium,
            "hover 时 scale 缩放 — AI 常见的过度交互",
            "hover 只做颜色/表面微变，不缩放",
        ),
        make_rule(
            "long-animation",
            Matcher(
                r"\banimation\s*:\s*\w+\s+(\d+(?:\.\d+)?)s\b|"
                r"\banimation\s*:\s*[^;}]*\binfinite\b",
                guard=lambda text, match: bool(
                    (match.group(1) and float(match.group(1)) > 3)
                    or "infinite" in match.group(0).lower()
                ),
            ),
            dim_motion,
            severity_low,
            "过长的动画时长（>3s）或无限循环呼吸/浮动",
            "反馈动画 ≤150ms，进入动画 ≤300ms",
        ),
    ]


RULES = build_rules()

# Emoji 兜底扫描：包含 U+2B00-2BFF（⭐ 等）与变体选择符。
EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U00002300-\U000023ff"
    "\u2b00-\u2bff"
    "\U0001f900-\U0001f9ff"
    "\ufe0f"
    "]",
    re.UNICODE,
)
