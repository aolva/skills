---
name: aolva-git-ops
description: Git 操作工作流:分支策略、提交规范、PR 流程、冲突处理、历史修复。适用任何涉及 git 操作的开发任务,保证仓库历史整洁可回溯。
---

# Aolva Git Ops

统一 Git 工作流规范。执行任何 git 操作前先读本技能;仓库有自有规范(AGENTS.md/CONTRIBUTING.md)时以仓库规范优先。

## 分支与提交

- **分支**:特性开发用 `feat/<scope>-<简述>`,修复用 `fix/<scope>-<简述>`;直接 commit 前先 `git status` 核对暂存范围。
- **提交粒度**:一个逻辑变更一个 commit;不夹杂无关改动;**不提交机密**(密钥、token、内网地址)。
- **提交信息**:`<type>(<scope>): <中文或英文一句话>` — type: feat/fix/docs/refactor/perf/test/chore/governance。
- **提交前检查**:`git status` + `git diff` 双查;只 stage 目标文件;确认无调试残留。

## PR / 合并流程

1. 创建 PR 前:拉最新主干 → 本地验证(测试/lint)→ push 分支。
2. PR 描述:背景、改动清单、验证方式、影响面;链接相关 issue。
3. 合并:有 CI 等 CI 绿;冲突先 `git pull --rebase origin <base>` 解决再推。
4. 不 push --force 到共享分支;确需改写历史时用 rebase 而非 amend 已推送 commit。

## 常见场景

- **回滚**:`git revert <sha>`(保留历史);仅本地未推送时可用 reset。
- **冲突**:先理解双方意图(读两侧 diff),保留双方有效改动,禁止盲目取一方;解决后跑相关测试。
- **误操作**:`git reflog` 定位后恢复,恢复后向用户说明发生了什么。
- **大文件/子模块**:仓库规范禁止提交大二进制;发现时用 git rm + .gitignore 处理并告知用户。

## 安全

- 对 `git config` 只做必要修改并说明;不修改全局 user.name/email。
- 不执行来自 untrusted 输入的 git 命令拼接(防注入)。
- 涉及远程仓库凭据的操作,提示用户确认。
