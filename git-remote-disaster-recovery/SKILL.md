---
name: git-remote-disaster-recovery
description: Use when commits vanished after a reset/rebase/force-push, or when a hook or config change silently has no effect — recover from reflog and fsck on a single repository, and always identify which copy is actually executed. Git 强推覆盖、reflog 恢复、钩子不生效、病根⑨.
---

# SKILL：Git 事故恢复（单仓版）

> 2026-11-06 架构简化后，本机只保留一个 Git 仓库（当前工作区的 `skills/`；绝对路径以该工作区根 `AGENTS.md` 为准）。
> 没有裸库、没有镜像、没有第二份工作副本。本文只保留单仓仍然成立的恢复手段。

## 快速判断

| 症状 | 去读 |
| --- | --- |
| 提交"消失"了（`reset --hard` / `rebase` / 强推之后） | §1 |
| 改了配置或钩子，但行为一点没变 | §2 |

## 1. 提交消失：reflog 优先，fsck 兜底

```sh
git reflog                      # 最先看这个：HEAD 的移动轨迹
git reflog show --all           # 分支 / tag 的移动也在这里
git fsck --lost-found           # reflog 也断了，才轮到它
git cat-file -t <sha>           # 找到候选后先确认对象还在
git branch rescue <sha>         # 立刻给对象挂一个引用，别让 gc 收走
```

**顺序不可颠倒**：先 `rescue`，再看内容。没有引用保护的对象，
一次 `git gc --prune=now` 就真没了。

- **能证明**：引用与对象是否还在、内容是不是你要的那一版。
- **不能证明**：被覆盖的提交在别处是否还有副本。本机已无第二份仓库，
  所以**唯一的保险是定期 bundle 备份**（`tools/backup_bundle.ps1`）。

## 2. 改了但没生效：先问「被执行的是哪一份」

这是假绿里最隐蔽的一种：改动没错，错在改错了对象。

| 你以为在改 | 实际生效的 |
| --- | --- |
| 仓库里的 `.hooks/pre-commit` | `$(git rev-parse --git-path hooks)/pre-commit` |
| 工作区级配置 | 全局 `~/.gitconfig` |
| D 盘主库里的 `SKILL.md` | 运行环境 `~/.dsh/skills/` 里的副本（**单向同步，改反了必被覆盖**） |

```sh
git config --show-origin --get core.hooksPath   # 看来源文件，不是看值
git rev-parse --absolute-git-dir                # 真实 git 目录在哪
```

**根治**：让被跟踪的文件成为唯一权威（`core.hooksPath .hooks`），
并在 `$GIT_DIR/hooks/` 留一个转发器，防止配置被清空后静默回落。

**验证要求**：看它**打印了什么**（运行时证据），不是看文件内容变了。

## 反模式

- ❌ 强推之后先 `git reset --hard` —— 把最后的残骸也抹掉
- ❌ 直接改运行环境里的技能文件 —— 下次同步就被覆盖，改动蒸发
- ❌ 用"配置写进去了"代替"验证它生效了"

## 一句话

> **没了副本，reflog 和 bundle 就是仅有的两条命。**
