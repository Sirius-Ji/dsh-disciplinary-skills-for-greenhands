#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前本地检查（架构简化后的三项之二，第三项 HANDOFF 门禁在 pre-commit 里）。

  暂存的 SKILL.md / AGENTS.repo.md / AGENTS.md 必须是纯 CRLF、合法 UTF-8
退出码：0 放行；1 阻断
"""
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_NAME = "AGENTS.repo.md"
LIVE_NAME = "AGENTS.md"


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True)


def main():
    r = git(["rev-parse", "--show-toplevel"], None)
    if r.returncode != 0:
        print("[pre] 不在 git 仓库内，跳过")
        return 0
    root = r.stdout.decode("utf-8", "replace").strip()

    staged = git(["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], root)
    names = [n for n in staged.stdout.decode("utf-8", "replace").split("\0") if n]

    # 1) 行尾与编码（仓库不再嵌套在 ~/.dsh 下，双胞胎护栏已过时：
    #    D 盘主库根的 AGENTS.md 只约束本仓库，不会被宿主编进 ~/.dsh）
    targets = [n for n in names
               if n in (REPO_NAME, LIVE_NAME) or n.endswith("/SKILL.md")]
    errs = []
    for n in targets:
        r = git(["cat-file", "blob", ":" + n], root)
        if r.returncode != 0:
            errs.append("%s 读不出暂存内容" % n)
            continue
        b = r.stdout
        try:
            b.decode("utf-8")
        except UnicodeDecodeError as e:
            errs.append("%s 不是合法 UTF-8：%s" % (n, e))
            continue
        crlf = b.count(b"\r\n")
        bare = b.count(b"\n") - crlf
        if bare != 0:
            errs.append("%s 含裸 LF %d 个（必须纯 CRLF）" % (n, bare))
        if crlf == 0:
            errs.append("%s 没有任何 CRLF（疑似被转成 LF）" % n)

    print("[pre] 暂存的纪律/技能文件 %d 个" % len(targets))
    if errs:
        for e in errs:
            print("[pre] ✗ " + e)
        return 1
    print("[pre] ✓ 行尾与编码正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
