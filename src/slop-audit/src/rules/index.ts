import {
  createRule,
  regex,
  type RuleDefinition,
} from "../helpers/rules.js";

const definitions: RuleDefinition[] = [
  {
    name: "arbitrary-spacing",
    message: "非 4px 网格的自定义间距",
    suggestion: "替换为 4 的倍数：mt-3=12px, mt-4=16px, mt-5=20px",
    source: "class",
    check: {
      regex: regex("\\b[mp][trblxy]?-\\[\\s*(\\d+)px\\s*\\]"),
      guard: (_value, match) => {
        const amount = Number(match[1]);
        return amount % 4 !== 0 && amount !== 2;
      },
    },
  },
  {
    name: "tw-purple-gradient",
    message: "紫色/靛蓝渐变是 AI 生成 UI 的典型标志",
    suggestion: "删除渐变，用单色或中性色阶",
    source: "class",
    check: {
      regex: regex("\\b(?:from|to|via)-(?:purple|violet|fuchsia|indigo)-\\d+\\b"),
    },
  },
  {
    name: "rainbow-gradient",
    message: "青→紫 / 蓝→紫 彩虹渐变",
    suggestion: "选定一个来自产品世界的 accent，其余用中性色阶",
    source: "class",
    check: {
      regex: regex("\\b(?:from|to|via)-(?:cyan|teal|sky|blue)-\\d+\\b"),
      require: [regex("\\b(?:from|to|via)-(?:purple|violet|fuchsia)-\\d+\\b")],
    },
  },
  {
    name: "tw-gradient-class",
    message: "Tailwind 渐变类常伴随跨色相渐变滥用",
    suggestion: "确认渐变仅限同色明度微差；删除跨 hue 渐变",
    source: "class",
    check: {
      regex: regex("\\b(?:bg|text|border|from|via|to)-gradient\\b|\\bbg-gradient-to-\\w+"),
      guard: (value) => {
        const from = /\bfrom-([a-z]+)-\d+\b/i.exec(value);
        const to = /\bto-([a-z]+)-\d+\b/i.exec(value);
        return !(from && to && from[1].toLowerCase() === to[1].toLowerCase());
      },
    },
  },
  {
    name: "label-emoji",
    message: '"New ✨ / Beta 🚀 / Pro 🔥" 标签是 AI 最爱',
    suggestion: "移除 emoji；确有标签需要时用安静的纯文字",
    source: "text",
    check: { regex: regex("\\b(?:New|Beta|Pro|Hot)\\b\\s*(?:✨|🚀|🔥|⭐|💡|👋)") },
  },
  {
    name: "greeting",
    message: "问候式标题（Welcome back, Name! 👋）",
    suggestion: "用页面名或时间段做标题",
    source: "text",
    check: { regex: regex("(?:Welcome\\s+back|Hello|Hi|Hey)\\s*,?\\s*[A-Za-z]+\\s*(?:!|👋)") },
  },
  {
    name: "marketing-words",
    message: "营销夸张词（supercharge / seamless / unlock / magic ...）",
    suggestion: "用平实具体的语言描述产品做什么",
    source: "text",
    check: {
      regex: regex(
        "\\b(?:supercharge|seamless|unlock(?:ing|s)?|magic(?:al|ally)?|cutting-edge|next-gen(?:eration)?|effortless|game-chang(?:er|ing|ers)|revolutioni[sz]\\w*)\\b",
      ),
    },
  },
  {
    name: "ai-powered",
    message: '"AI-powered" 滥用',
    suggestion: "只在确实使用了 AI 的地方说明它做了什么",
    source: "text",
    check: { regex: regex("\\bAI[\\s-]*powered\\b") },
  },
  {
    name: "social-proof",
    message: "无法核实的社交证明",
    suggestion: "无法证实则删除；有真实数据才保留",
    source: "text",
    check: {
      regex: regex(
        "\\b(?:Loved|Trusted|Used)\\s+by\\s+\\d[\\d,]*\\+?\\s+(?:teams|users|companies|customers|people)\\b",
      ),
    },
  },
  {
    name: "hype-number",
    message: "夸张数字宣称（10x faster）",
    suggestion: "换成可验证的具体对比",
    source: "text",
    check: { regex: regex("\\b(?:10x|100x|1000x)\\s+(?:faster|better|easier|more)\\b") },
  },
  {
    name: "placeholder-data",
    message: "明显的占位/假数据",
    suggestion: "用合理可信的数据替换",
    source: "text",
    check: {
      regex: regex(
        "\\b(?:lorem ipsum|John Doe|Jane Doe|Acme(?:\\s+Corp)?|\\[X\\]|123,456)\\b|\\bmockData\\b|\\bplaceholderData\\b",
      ),
    },
  },
  {
    name: "multi-bang",
    message: "界面文案里的感叹号",
    suggestion: "界面文案不用感叹号，更不要连续感叹号",
    source: "text",
    check: { regex: regex("!+") },
  },
  {
    name: "emoji-as-icon",
    message: "检测到 emoji 装饰字符",
    suggestion: "替换为统一图标库的线性图标",
    source: "text",
    check: {
      regex: regex(
        "[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}\\u{2B00}-\\u{2BFF}\\uFE0F]",
        "iu",
      ),
    },
  },
  {
    name: "heavy-weight",
    message: "过重的字重（700-900）",
    suggestion: "层级用字号 + 色阶表达，字重控制在 400-600",
    source: "class",
    check: { regex: regex("\\bfont-(?:bold|extrabold|black)\\b") },
  },
  {
    name: "negative-tracking",
    message: "负 letter-spacing，小字上尤其有害",
    suggestion: "小字需要更大字号或稍宽间距来提升可读性",
    source: "class",
    check: { regex: regex("\\btracking-\\[-[\\d.]+\\]") },
  },
  {
    name: "wide-tracking",
    message: "过宽字间距用于小字/标签",
    suggestion: "改用 Sentence case，去掉宽间距",
    source: "class",
    check: { regex: regex("\\btracking-(?:wide|wider|widest)\\b") },
  },
  {
    name: "uppercase-label",
    message: "全大写标签",
    suggestion: "改为 Sentence case",
    source: "class",
    check: { regex: regex("\\buppercase\\b") },
  },
  {
    name: "gradient-text",
    message: "渐变文字依赖透明文字色",
    suggestion: "删除，用实色文字表达层级",
    source: "class",
    check: {
      regex: regex("\\btext-transparent\\b"),
      require: [regex("\\bbg-clip-text\\b|\\btext-clip\\b")],
    },
  },
  {
    name: "tw-gradient-text",
    message: "Tailwind gradient text（bg-clip-text）",
    suggestion: "删除，用实色",
    source: "class",
    check: { regex: regex("\\bbg-clip-text\\b|\\btext-clip\\b") },
  },
  {
    name: "italic-emphasis",
    message: "用 italic 做强调",
    suggestion: "用字号或颜色表达层级，不用斜体强调",
    source: "class",
    check: { regex: regex("\\b(?:text-italic|font-italic|italic)\\b") },
  },
  {
    name: "centered-stack",
    message: "全居中 + 竖排堆叠布局是模板默认样式",
    suggestion: "考虑不对称分栏：文字一侧 + 视觉另一侧",
    source: "class",
    check: {
      regex: regex("\\b(?:flex|grid)\\b"),
      require: [
        regex("\\bitems-center\\b"),
        regex("\\bjustify-center\\b"),
        regex("\\bflex-col\\b"),
        regex("\\btext-center\\b"),
      ],
    },
  },
  {
    name: "narrow-column",
    message: "App/Dashboard 被收窄成居中窄列",
    suggestion: "App 应填满视口，内容区 fluid",
    source: "class",
    check: {
      regex: regex("\\bmax-w-(?:\\[?[2-6]\\d{2}px\\]?|sm|md|lg|xl)\\b"),
      require: [regex("\\bmx-auto\\b")],
    },
  },
  {
    name: "big-radius",
    message: "全部元素都是大圆角/胶囊形",
    suggestion: "嵌套圆角递减：按钮 8-10，卡片 12-16，面板 14-20",
    source: "class",
    check: { regex: regex("\\brounded-(?:full|3xl)\\b") },
  },
  {
    name: "badge-pill",
    message: "Badge 全用 rounded-full 胶囊",
    suggestion: "改用与控件一致的圆角，或直接用安静文字",
    source: "class",
    check: {
      regex: regex("\\b(?:badge|pill|tag)\\b"),
      require: [regex("\\brounded-full\\b")],
    },
  },
  {
    name: "stat-decoration",
    message: "Stat card 里塞 sparkline / mini bars 等装饰",
    suggestion: "Stat cards 应只放数字，不放迷你图表凑装饰",
    source: "class",
    check: { regex: regex("\\b(?:sparkline|mini-bar|miniBar|tally)\\b") },
  },
  {
    name: "decorative-nouns",
    message: "AI 典型装饰词（blob / orb / nebula / holo ...）",
    suggestion: "删除装饰性填充物，用产品自身内容承载视觉",
    source: "class",
    check: { regex: regex("\\b(?:blob|orb|bubble|sphere|nebula|holo|crystal|glow)\\b") },
  },
  {
    name: "looping-animation",
    message: "循环动画（animate-pulse / ping / shimmer / float）",
    suggestion: "移除无功能意义的循环动画",
    source: "class",
    check: {
      regex: regex(
        "\\banimate-(?:pulse|ping|spin|bounce|float|wiggle)\\b|\\banimate-\\[[^\\]]*(?:float|pulse|shimmer|infinite)[^\\]]*\\]",
      ),
    },
  },
  {
    name: "transition-all",
    message: "transition-all 全量过渡，性能差且意图不明",
    suggestion: "明确列出属性：transition-colors / transition-[transform,opacity]",
    source: "class",
    check: { regex: regex("\\btransition-all\\b") },
  },
  {
    name: "hover-scale",
    message: "hover 时 scale 缩放是过度交互",
    suggestion: "hover 只做颜色/表面微变，不缩放",
    source: "class",
    check: { regex: regex("\\bhover:scale-(?:\\d+|\\[[^\\]]+\\])") },
  },
  {
    name: "long-animation",
    message: "过长或无限循环动画",
    suggestion: "反馈动画 ≤150ms，进入动画 ≤300ms",
    source: "class",
    check: {
      regex: regex("\\banimate-\\[[^\\]]*(?:infinite|shimmer)[^\\]]*\\]"),
    },
  },
];

export const rules: Record<string, any> = Object.fromEntries(
  definitions.map((definition) => [definition.name, createRule(definition)]),
);
