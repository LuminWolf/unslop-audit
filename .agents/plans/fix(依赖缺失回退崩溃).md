# fix(依赖缺失回退崩溃) · 修复计划（已修复并复验通过）

## 1. 问题

- 现象：模拟 `tree_sitter` 依赖缺失时，`scan_file()` 抛 `ModuleNotFoundError`，CLI 崩溃，违背「依赖缺失均回退且不污染 stdout」的验收标准。
- 复现：`.agents/tmp/scripts/verify_missing_dep.py`，日志 `.agents/tmp/verify_missing_dep.log` 记录 `结果: 抛出异常 ModuleNotFoundError: No module named 'tree_sitter' (simulated)`。
- 影响：TSX/JSX 文件在依赖不可用时无法降级为文本视图；CI 门禁脚本会中断。

## 2. 根因

`src/unslop_audit/views.py` 的 `ScanView.from_tsx()` 中：

```python
from .tsx import build_tsx_view
return build_tsx_view(text)
```

- `from .tsx import ...` 是延迟导入，位于 `build_tsx_view()` 内部 try/except 之外。
- `tsx.py` 顶层 `import tree_sitter` / `import tree_sitter_typescript`，依赖缺失时导入即抛 `ModuleNotFoundError`。
- 异常经 `from_tsx()` → `scan_file()` 一路逃逸；现有 `scan_file()` 只处理 `view is None` 的回退，未捕获构造视图时的异常。

## 3. 修复方案

### 3.1 主方案（推荐）：在 `views.py` 的 `from_tsx()` 内兜住延迟导入

把延迟导入与调用一起放进 try/except；任何异常（含 `ImportError` / `ModuleNotFoundError`）都返回 `None`，直接复用 `scan_file()` 现有的 `if view is None` 回退链路。

```python
@classmethod
def from_tsx(cls, text: str) -> ScanView | None:
    try:
        from .tsx import build_tsx_view
        return build_tsx_view(text)
    except Exception:
        return None
```

- 优点：单点改动，职责清晰（「视图构造失败 → 返回 None 让调用方回退」），不新增分支逻辑。
- 说明：`build_tsx_view()` 内部已有 try/except 处理解析异常；此处只补上「导入阶段」的保护，两者互补。

### 3.2 配套文案调整（推荐）：`scan.py` 的 WARNING 改为通用表述

把 `WARNING: TSX AST 解析失败，回退到文本视图` 改为 `WARNING: TSX AST 视图不可用，回退到文本视图`，使解析失败与依赖缺失两种回退都能准确描述。

### 3.3 可选强化：`scan.py` 分派处加一层兜底

在 `view = ScanView.from_tsx(text)` 外包 try/except，作为防御性第二层。仅在 3.1 验收仍出现逃逸时采用；不默认实施，避免过度扩大捕获范围。

### 3.4 可选回归测试：新增依赖缺失自动化用例

在 `tests/test_ai_ui_audit.py` 新增一条测试，用 `builtins.__import__` 拦截 `tree_sitter` 导入，断言 `scan_file()` 不抛异常。属「改测试」环节，需单独批准。

## 4. 不做什么

- 不改规则表、维度顺序、`RULES` 与匹配器行为。
- 不改变 TSX AST 视图的正常路径与虚拟片段生成逻辑。
- 不新增第三方依赖，不改 `pyproject.toml` / `uv.lock`。
- 不删除根目录旧 `test_ai_ui_audit.py`。

## 5. 验收标准

1. `.agents/tmp/scripts/verify_missing_dep.py` 输出「依赖缺失被安全回退」，`scan_file()` 不抛异常。
2. 依赖缺失时 CLI exit 0、stdout 仍为纯 JSON、stderr 含 WARNING。
3. `uv run python tests/test_ai_ui_audit.py` 保持 `OK (skipped=1)`；若加入 3.4 则相应测试数增加且全通过。
4. `.agents/tmp/scripts/verify_tsx_cli.py` 全部通过：单 fixture JSON 行号=3、CSV 表头与行号、`--fail-on high` exit 2、混合目录 TSX finding>0、语法错误回退正常。
5. 回退后的文本视图允许结果降级（例如 `// padding: 13px` 注释不再被 AST 屏蔽而可能误报）；本修复只保证「不崩溃、不污染 stdout」，不要求降级结果与 AST 视图等价。

## 6. 风险与对策

| 风险 | 对策 |
| --- | --- |
| `except Exception` 过宽，掩盖真实代码缺陷 | 仅包住延迟导入与 `build_tsx_view()` 调用；`build_tsx_view()` 内部已有独立 try/except；回退时输出 WARNING 便于发现 |
| 每次 TSX 文件都重试失败的导入 | 失败导入不缓存，但代价可忽略；若成为瓶颈再考虑进程级缓存 |
| 回退结果降级被误判为修复失败 | 在验收标准 5 明确降级是预期行为 |

## 7. 文件改动清单与分步点

| 步骤 | 文件 | 改动 | 前置 |
| --- | --- | --- | --- |
| F1 | `src/unslop_audit/views.py` | `from_tsx()` 延迟导入纳入 try/except，异常返回 `None` | 批准改源码 |
| F2 | `src/unslop_audit/scan.py` | WARNING 文案改为通用表述 | 批准改源码 |
| F3 | `.agents/plans/status/tsx-tree-sitter.md` | 更新 DEFECT-1 状态与验收结论 | F1/F2 |
| F4 | 验证脚本 + 单测 | 重跑 `verify_missing_dep.py`、`verify_tsx_cli.py`、`tests/test_ai_ui_audit.py` | 批准运行验证 |
| F5（可选） | `tests/test_ai_ui_audit.py` | 新增依赖缺失回归测试 | 批准改测试 |
| F6（可选） | `src/unslop_audit/scan.py` | 分派处第二层 try/except 兜底 | F4 仍有逃逸 |

## 8. 审批门

规划阶段已完成。实施需分别批准：

1. 改源码（F1/F2）。
2. 运行验证与单测（F4）。
3. 改测试（F5，如采用）。

## 9. 实施结果（已完成）

- 用户批准修复后实施 F1 + F2：`views.py` 的 `from_tsx()` 用 try/except 包住延迟导入与调用，异常返回 `None`；`scan.py` WARNING 改为「TSX AST 视图不可用，回退到文本视图」。F3 可选强化未采用（F4 复验无逃逸）。
- 复验：`.agents/tmp/scripts/verify_missing_dep.py` 输出「依赖缺失被安全回退」；`verify_tsx_cli.py` 全部通过；单元测试 17 项 OK (skipped=1)；新增集成测试 8 项 OK。
- 缺陷关闭。
