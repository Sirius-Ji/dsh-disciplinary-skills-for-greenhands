---
name: git-remote-disaster-recovery
description: Use when a force-push overwrote history, when a repository was renamed and the local remote still points at the old name, when a hook or config change silently has no effect, or when a repository's .git is a pointer file rather than a directory — recover from reflog and the bare hub, and always identify which copy is actually executed. Git 强推覆盖、仓库改名、钩子不生效、gitdir 指针、远端恢复.
---

# SKILL：Git 远端事故恢复

## 快速判断（30 秒）

| 症状 | 去读 |
| --- | --- |
| 推送失败、或推到了错误的分支/仓库 | §2 |
| 提交历史被强推覆盖了 | §1 |
| **改了配置或钩子，但行为一点没变** | §3（最常见，先看这节） |
| `.git` 不是目录 | §4 |

## 核心原则

**先冻结现场，再动手。**
所有"删掉重建"的冲动，都是把最后一点残骸也抹掉。
在动任何恢复命令之前，先把远端仓整个复制一份（`cp -r hub.git hub.git.bak-<时间戳>`）。

> **★ 推送红线**：**绝对禁止向任何外网/公网执行 git push。本地的裸库、工作区互相同步属于本地开发日常，不受此限。**
> 本文里所有 `git push` / `git push -f` 步骤，都只对**本地裸库**成立。

## 1. 强推覆盖：先分类"丢了什么"

三种损失，恢复手段完全不同：

1. **远端引用被改写**（最常见）——对象通常还在裸库里，`git fsck --lost-found`、reflog 都能捞；
2. **别人的工作树被覆盖**——只能靠对方本地 reflog / 备份，远端帮不上忙；
3. **本地未推送的提交**——`git reflog`，几乎总能找回。

**恢复顺序**：

```
冻结现场 → git reflog / git fsck --lost-found 找悬空提交
        → 确认对象存在（git cat-file -t <sha>）
        → 重建引用（git branch rescue <sha> / git reset --hard <sha>）
        → 再做一次验证（git log、关键文件哈希）
```

### 真实案例（2026-11-04）：仓库改名 + 强推覆盖

**经过**：把代码推到 `example-backupdemo` 时推送失败——远端仓库已经**改过名**，
而本地 `origin` 的 URL 还指着旧名字。修正动作是 `git remote set-url origin <新地址>`，
之后用 `git push -f` 强推（**仅限本地裸库**；外网/公网一律禁止），把远端那段**错误的历史**覆盖掉。

**这里其实同时发生了两件事**，值得分开看：

1. **改名不同步**：仓库改名后，本地 remote 配置**不会自动更新**。
   所以每次"推不上去"的第一反应应该是 `git remote -v`，而不是 `git push -f`（同样仅限本地裸库）。
2. **强推覆盖**：`-f` 会**不可逆地改写远端引用**。这次是刻意的（远端历史是错的），
   但同样的动作用在别人的分支上就是灾难。

**事后看的正确顺序**：

```
① git remote -v                      ← 先确认推去哪儿
② git ls-remote origin <branch>      ← 再确认远端当前是什么
③ git log --oneline origin/main..HEAD ← 确认本地多出什么、会不会覆盖别人的提交
④ 备份远端（裸库整目录复制）
⑤ 才允许 git push -f              ← 仅限本地裸库；外网/公网一律禁止
```

**教训**：`-f` 之前必须先能回答"我要覆盖掉的这些提交，还有没有别的副本"。
答不上来就先备份——裸库复制成本约等于零。

## 2. 推送失败的三类原因（别一上来就 `-f`）

| 现象 | 先查 |
| --- | --- |
| `Repository not found` / 404 | 仓库改名、或凭据失效：`git remote -v` + `git ls-remote` |
| `non-fast-forward` / `rejected` | 远端有新提交：`git fetch` 后看差异，**不要直接 `-f`** |
| `Permission denied` | 凭据 / 部署密钥 / 分支保护规则 |

**判断标准**：只有"我明确知道要丢弃远端哪些提交"时，才用 `-f`。

## 3. 改了但没生效：先问"被执行的是哪一份"

这是**假绿**里最隐蔽的一种：改动没错，错在改错了对象。

| 你以为在改 | 实际生效的 |
| --- | --- |
| 仓库里的 `.hooks/pre-commit` | `$GIT_DIR/hooks/pre-commit` |
| 本地 `.git/config` 里的某项 | 全局 `~/.gitconfig` 或工作区级配置 |
| 多副本派生的某一端 | 程序真正读取的那一端 |

**30 秒自查清单**：

```sh
git config --show-origin --get core.hooksPath   # 看来源文件，不是看值
git rev-parse --absolute-git-dir                # 和 <repo>/.git 是不是同一个地方
git ls-files -s <path>                          # 这个文件真的被跟踪吗
```

如果 `git rev-parse --git-common-dir` 返回的不是 `.git`，
或者 `.git` 是一个**文件**（内容 `gitdir: <绝对路径>`），
那么仓库里所有"看起来像配置"的东西都可能只是副本。

**根治方式**：让**被跟踪的文件成为唯一权威**。

```sh
git config core.hooksPath .hooks          # 指向仓库内被跟踪的钩子
```

再把 `$GIT_DIR/hooks/pre-commit` 降级成转发器，防止 `hooksPath` 被清空后静默回落：

```sh
#!/bin/sh
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
exec "$ROOT/.hooks/pre-commit" "$@"
```

**验证要求**：改完必须看它**打印了什么**（运行时证据），而不是看文件内容变了。

## 4. `.git` 是指针文件时

- `.git` 是几十字节的文本 `gitdir: <绝对路径>` ⇒ 这是 worktree / linked checkout；
- 任何 `os.path.isdir('.git')` 的判断都会失败，脚本会走进错误的 else 分支；
- **备份时不能只拷仓库目录**，必须跟着拷真实 gitdir，否则等于没备份；
- 迁移/打包时 `.git` 指针里是**绝对路径**，换机器必然失效。

## 反模式

- ❌ 强推之后先 `git reset --hard` —— 把最后的残骸也抹掉了；
- ❌ 把"配置写进去了"当成"生效了"；
- ❌ 用截图或口述证明钩子在工作，而不是看它的输出；
- ❌ 两个仓库挂同一个裸库，却指望它们互相隔离；
- ❌ 仓库改名后不去核对 remote，直接开始怀疑网络或权限。

## 边界

- **能证明**：引用与对象是否还在、哪份文件是权威、钩子是否真的执行；
- **不能证明**：覆盖掉的提交在别处是否还有副本——这只能靠搜索（别人机器 / 备份 / 远端镜像）；
- **需要人工裁决**：要不要强推、强推会不会影响协作者。

## 一句话

**恢复的前提是"先别删"；生效的前提是"找对那一份"。**
这两句话能省掉绝大多数事故。
