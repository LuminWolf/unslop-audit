---
name: git
description: git 规范
---

# Git 提交规范

- 未经人类明确要求，不得 `git commit` / `push`。
- 遵循 Conventional Commits：`<type>(<scope>): <subject>`

## 分支模型

- `main`: 经过实车验证后的代码; 保护分支必须走pr流程合并
- `dev`: 只有仿真验证过的代码, 提交可编译;
- `agent`: AI 工作分支。
- 增加功能时使用本地功能分支(ai 管理的分支加 `agent` 前缀), 完成后并回 `agent`, 琐碎提交不灌进 dev。

## 提交流程

1. `git status` 与 `git diff` 确认改动范围。
2. 按类别分组，逐个 `git add <具体文件>`
3. **提交前必须核对暂存区**：`git diff --cached --stat`，确认只含本组文件
4. **跨组操作与 commit 不分离**：`git mv`/`git rm` 做完立刻进入对应提交，不要留到下一次 commit。
5. 每类单独 commit，一次只提交一个逻辑分组。顺序建议：自包含新包 → 相互耦合的包组 → 文档, chore。
6. **同一文件含多个逻辑变更时**：优先按文件/包分组；若确需拆分，可用 `git add -p` 拆 hunk，或在所属 feat 的 message body 中说明 fix/refactor 细节，不要为了“一个文件一笔提交”把无关改动硬塞进同一提交。

## 纯本地分支并入共享分支（整理后重放）

目标: 共享分支上只出现少量干净的普通提交

### 前置检查清单

- 当前在待整理分支，`git status` 干净。
- 摊平期间的 WIP 要进备份

```bash
git commit -am wip
git branch backup/<分支>-wip
```

未跟踪文件 `git stash -u` , 完成后再恢复

- `git log --oneline --graph local origin/shared` 确认待整理提交范围，确认没有遗漏或误包含的提交。
- `git fetch origin` 已执行，`origin/shared` 为最新。

### 远端共享分支

不要重写源分支，改用 squash 重放——从共享分支开重放分支，
把源分支的全部差异摊成工作区后分组提交，远端历史全程不动、无需 force：

```bash
git switch -c <name>-squash origin/shared
git merge --squash local    # 输出 "Squash commit -- not updating HEAD" 属正常
expected=$(git write-tree)  # 记录 squash 后的期望 tree, 作零差异基准
git reset                   # 把 squash 的暂存全部转成未暂存，随后按组 add
```

- `merge --squash` 有冲突时: 逐个解决并 `git add`，**不要 commit**，待 reset 后再分组提交。
- squash 会把 rename 退化成一增一删，分组提交时新旧路径要一起 add。
- 分组提交后做零差异验证: `git diff --exit-code "$expected" HEAD`。基准必须是 `$expected`
   而不是 local tip——local 可能落后于 shared（shared 被他人推进、已推送的 local 不宜 rebase），
   用 local tip 作基准会必然误报。
- 完成后共享分支 `merge --ff-only <name>-squash` 并删除重放分支，源分支保持原样。
   ff 失败说明重放期间 shared 又推进了: 优先删重放分支、从最新 `origin/shared` 重做 squash
   重放；若改 rebase 重放分支，rebase 之后 `$expected` 失效，必须重新记录基准。

### 纯个人分支重写流程

```bash
git switch local
git branch backup/local-old local
# 1) 先把 local 对齐到共享分支最新 tip
#    - local 已包含 origin/shared 时，此步为 no-op
#    - 分叉时执行 rebase；冲突需逐个解决后 git rebase --continue
git rebase origin/shared
# 2) 摊平：HEAD 回到 origin/shared，所有 local 改动进入 index，工作树保持 local tip 内容
kept=$(git rev-parse HEAD)                # 记录对齐后的 tip 作为零差异验证基准
base=origin/shared
git reset --soft "$base"
git reset
```

1. **分组提交**：此时全部改动以未暂存状态在工作区，按"提交流程"第 2~6 步分组
   `git add <具体文件>` + 逐笔 `git commit`（提交范围恰好等于对共享分支的全部差异）。
2. **零差异验证**：`git diff --exit-code "$kept" HEAD` 必须为空——整理只动提交划分，不动内容。
   共享分支推进过时基准用 `$kept`（rebase 对齐后的 tip）
3. **恢复 WIP**：从备份分支cherry pick取回临时提交；确认恢复完成前不删备份。
