# TSX Tree-sitter 支持实现计划

## 1. 总体设计

保持规则表 `RULES` 不变，给扫描层引入「扫描视图」：HTML/CSS 继续走原文本视图；TSX/JSX 走 AST 视图。AST 视图把代码结构转换成规则能消费的文本片段，并记录每个片段到源文件的偏移映射，最终仍输出统一的 `Finding(file, line, ...)`。

### 1.1 新增 `ScanView`

建议新增 `src/unslop_audit/views.py`：

- `text`：长度与源文件一致（或至少保持行号基准），非 UI 区域按等长空格屏蔽，换行保留；允许在末尾追加「虚拟片段」。
- `offset_map`：`text` 每个字符对应的源文件偏移；原样保留区为恒等映射，虚拟片段映射到产生它的 AST 节点起点。
- `source_span(index)`：把扫描命中偏移转换成源文件行号。
- `from_source(text)`：HTML/CSS 的简单实现，等价于现有 `mask_comments`。
- `from_tsx(text)`：AST 实现，见下节。

`scan_file()` 改为：`suffix in {".tsx", ".jsx"}` 时优先构造 AST 视图，失败则回退到原正则视图（不崩溃，stderr 输出 WARNING，不污染 JSON stdout）。

### 1.2 Tree-sitter 解析与节点收集

建议新增 `src/unslop_audit/tsx.py`，使用 `tree-sitter` + `tree-sitter-typescript` 的 TSX grammar。首轮只覆盖 TSX/JSX，`.js/.ts/.vue/.svelte` 暂不改行为。

对 AST 做一次遍历，生成三类内容：

1. **保留区**：JSX 文本节点、`<style>` 内的 CSS 文本。其余 JS/TS 代码按等长空格屏蔽。
2. **屏蔽区**：所有注释节点（JS `//`、`/* */`、JSX 注释、模板字符串中的注释形态）按等长空格屏蔽，保留换行；这是修复误报的关键。
3. **虚拟片段**：把 AST 解析出的 UI 值规范化成规则已有的输入形态，追加到 `text` 末尾并登记 `offset_map`：
   - `class="..."` 形态的虚拟属性，喂给现有 `ClassMatcher`；
   - `property: value;` 形态的虚拟 CSS 声明，喂给现有 `Matcher`；
   - JSX 表达式解析出的界面文本，喂给全文规则与 Emoji 兜底。

### 1.3 表达式解析（解决动态值跳过）

实现 `resolve_expr(node)`，按有限深度、带环检测的保守策略解析：

- `string` / `template_string`：静态字面量直接取值；模板中的 `${...}` 递归解析后拼接。
- `identifier`：在当前文件内查 `const`/`let`/`var` 的字符串初始化；找不到视为未知并跳过。
- `call_expression`：识别 `cx` / `clsx` / `classnames` 及其常见别名，扁平化参数。
- `array`：扁平化元素；`binary_expression` 的 `+`：仅拼接可解析的字符串。
- `parenthesized_expression` / `jsx_expression`：透传。
- `conditional_expression` / `logical_expression`：收集各分支可解析字符串的并集，避免漏检；如后续出现误报再收紧。
- 成员表达式、props、import 绑定、函数调用结果：未知，跳过但不误伤。

映射策略：虚拟片段的源偏移优先指向 JSX 使用点（如 `className={stack}` 的表达式节点），这样报告行号落在界面代码处；常量定义只作为取值来源，不作为首报位置。

### 1.4 样式对象规范化

`style={{ gap: 13 }}` 等对象写法转换规则：

- camelCase 属性名转 kebab-case：`backgroundColor` → `background-color`。
- 数字字面量对 spacing/height 类属性补 `px`：`gap: 13` → `gap: 13px`；`0` 保持 `0`。
- 字符串字面量原样保留；颜色、渐变、动画等规则复用现有 Matcher。
- 每个声明生成独立虚拟片段，映射到对应 `pair` 节点起点，行号准确且可去重。

### 1.5 匹配器兼容

`Matcher.find()` 与 `ClassMatcher.find()` 保持接受 `str` 的旧行为；新增接受 `ScanView` 的分支，内部在 `view.text` 上做同样的正则匹配。`scan_file()` 用 `view.source_span(start)` 计算行号，并按 `(rule.name, source_start, source_end)` 去重，防止同一 AST 节点被多次命中重复上报。

## 2. 验收标准

- 17 个 TSX fixture 均命中对应规则，且每条只命中一次。
- `css-spacing-off-grid/case.tsx` 的 `// padding: 13px` 注释不产生 finding，只有 `style={{ padding: 13 }}` 产生。
- 动态 `className` 的四种写法（模板字符串、`cx`、标识符、多参数 `cx`）均能命中。
- 原 HTML/CSS 101 个用例与 CLI 11 条断言全部通过。
- TSX 的 `--json` stdout 仍是纯 JSON；WARNING/错误只走 stderr。
- 不新增死规则；规则表与维度顺序不变。

## 3. 风险与对策

| 风险 | 对策 |
| --- | --- |
| Tree-sitter grammar 节点名与预期不符 | P1 先用探针脚本确认，再写提取逻辑 |
| 虚拟片段导致行号漂移 | 保存源偏移映射，测试中断言行号 |
| 条件表达式取并集造成误报 | 首轮只针对 fixture 覆盖的字符串分支；后续用负面用例约束 |
| 依赖安装改变「零依赖」定位 | README 单独阶段更新；CI 明确需要 `uv sync` |
| 旧文件被 AST 路径影响 | 严格按后缀分派，HTML/CSS 不进入 AST 路径 |
