# unslop-audit

把 `ai_ui_audit.py` 修好、并与 **unslop** SKILL.md 对齐后的可直接运行项目。

零第三方依赖（Python 3.8+），解压即可跑。

```
python3 ai_ui_audit.py ./src                     # 写 ai_ui_audit_report.csv，汇总打印到控制台
python3 ai_ui_audit.py ./src --csv report.csv    # 自定义 CSV 路径
python3 ai_ui_audit.py ./src --json > report.json
python3 ai_ui_audit.py ./src --fail-on high      # CI 门禁：exit 2
python3 test_ai_ui_audit.py                     # 101 个 HTML/CSS 用例 + 11 条断言
```

---

## 目录

| 文件 | 说明 |
| --- | --- |
| `ai_ui_audit.py` | 脚本入口：`main()` 定义在这里，包内不导出 `main` / `run` |
| `src/unslop_audit/` | 审计包：`models` / `matching` / `context` / `rules` / `scan` / `reporting` / `cli`（48 条规则 + emoji 兜底，不导出 `main` / `run`） |
| `test_ai_ui_audit.py` | 验收测试：101 个真实 HTML/CSS 片段，全部通过 |
| `sample_slop.html` | 典型 AI 味页面（脏页对照） |
| `sample_clean.html` | 按 SKILL 准则改好的页面（干净页对照） |
| `修复与对齐性报告.md` | 本轮修复清单、对齐结论、验证结果、剩余边界 |
| `reference/SKILL.md` | 对照用的 unslop 原文（CC BY 4.0） |
| `reference/ai_ui_audit.original.py` | 修复前的原始脚本，供 diff 与崩溃复现 |
| `reference/对齐性审计原始报告.md` | 修复前发现的问题清单 |

---

## 修复了什么

**P0 · 运行时崩溃（最严重）**
原脚本把 pyparsing 3.x 的 `search_string()` 当成返回 `(tokens, start, end)`，解包又在
`try/except` 之外 —— 只要有任何一条规则命中就抛异常。实测扫脏页直接崩（`exit=1`），
扫干净页反而返回 0 条 / 100 分，CI 里是假阴性。

此版改为 **`re` 驱动的匹配器**，去掉 pyparsing 依赖：`Matcher`（全文正则 + 语境谓词）、
`ClassMatcher`（只扫 `class="..."` 属性值）、`mask_comments`（等长屏蔽注释、行号不变）。

**P1 · 5 条写了却触发不了的规则**

| 规则 | 原根因 | 现在 |
| --- | --- | --- |
| `arbitrary-spacing` | `as_keyword` 边界导致 `mt-` / `py-` 失配 | `ClassMatcher` 直接匹配 `[mp][trblxy]?-[Npx]` |
| `rainbow-gradient` | `Regex("[^\n]*")` 贪婪不回溯 | class 串内做共存判断 |
| `badge-pill` | 同上 | 同上 |
| `narrow-column` | `kw("max-w")` 后多要一个 `-`，且中间正则不回溯 | 支持 `[400px]` 与 `md/lg/xl` 具名尺度 |
| `neon-border` | `as_keyword` 卡死 `#hex` | 改为颜色声明的色相判断，含 `rgba()` |

**P1 · 补 20+ 条规则，覆盖 SKILL 正文点名但原脚本没查的迹象**
多值与方向后缀的 4px 网格、固定高度、CSS 跨色相渐变、`rgba` 彩色阴影/霓虹边、
纯 CSS 彩色背景、`backdrop-filter`、单个 `!`、尾随句号、`Search anything...`、
无对比对象的 `+12%`、Tailwind `uppercase`/`tracking-widest`、数字格式与 `tabular-nums`、
顺序无关的全居中堆叠、`max-w-md`、多个主按钮、RTL `dir`、图标尺寸/描边一致性、
stat-card sparkline、`bg-purple-50`、自定义循环动画、不限时长的 `infinite`、
`hover:scale-[...]`、`transition: width/height/top/left/margin`、shimmer…

**P1 · 消掉 8 处误报**
2px 微调、`rounded-2xl`（16px）、同色明度渐变（`from-gray-900 to-gray-800`）、
普通英文 `example`/类名 `test`、`::placeholder`、`color: transparent` 的合法用途、
注释里的 `italic`、正文里的产品名 `Glow`（装饰词只在 class/CSS 选择器里查）。

**P2 · 输出**
逐条问题写入 CSV（列：`path,line,problem,fix`，UTF-8 BOM），汇总打印到控制台；
`--csv PATH` 可改文件名，默认 `ai_ui_audit_report.csv`。`--fix-hints` 保留兼容，但 fix 已默认写入 CSV。
`--json` 不再被 `PASS/FAIL` 或汇总污染（改走 stderr）；维度汇总补上中文名；
`--fail-on` 可安全与 `--json` 组合。

---

## 验收结果

```
Ran 11 tests in 0.95s — OK

test_00  CLI 不再崩溃 / test_01  51 个正例全命中 / test_02  8 个允许写法零命中
test_03  28 处原漏检全部命中   / test_04  8 处原误报全部清零
test_05  6 个死规则用例全部触发 / test_06  49 条规则无一条是死规则
test_07  九维度顺序与 SKILL 一致 / test_08  整页评分 / test_09  CI 门禁
test_10  原始脚本仍可复现崩溃（对照）
```

| 整页对照 | findings | score | 维度覆盖 |
| --- | --- | --- | --- |
| `sample_slop.html` | **63**（critical 8 / high 18 / medium 33 / low 4） | **0** | 九维度全有 |
| `sample_clean.html` | **0** | **100** | — |

---

## 定位与边界

这个脚本是 **SKILL 第 2 步 Audit 的粗粒度预筛器 / CI 门禁**，不是"是否符合 unslop
方法论"的验收工具。以下内容靠静态文本扫描做不到，仍需要人或上层流程：

- Step 1 渲染截图判断、Step 3 heavy/light/no slop 的程度判断、Step 4 的 Direction 五行
  （Product / Character / World / Moments / Signature）与"停下来等用户确认方向"
- Step 5–8 的九 pass **顺序修复语义**、渲染复查、报告、story video
- Checklist 的语义项：one bright element / quiet chrome / clear idea、accent 4.5:1 对比度、
  nested radius 计算、table row states、hero 整体构图、chart hierarchy、focus ring、
  signature detail、template check
- 分数（10/5/2/1 × 3）是脚本自定义权重，SKILL 本身没有"分数"概念

另外，SKILL.md 引用的 `references/signs.md`、`tokens.md`、`visuals.md`、`refs.md`、
`effects.md`、`rtl.md` **未随包提供**，所以对齐只针对 SKILL.md 正文；fix hint 里的精确
数值无法与 `tokens.md` 逐项核验。

---

## 许可与署名

对照文本 **unslop** by Damir Sokolovsky（[@heydamir](https://x.com/heydamir)），
CC BY 4.0，<https://heydamir.design/unslop>。`reference/SKILL.md` 保留原文与署名，
`README.md` 与两份报告均注明来源。
