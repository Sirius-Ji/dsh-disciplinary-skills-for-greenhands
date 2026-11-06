#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 D 盘主库与运行环境是否一致（同步后跑；只读）。

判定：
  A. 12 个 SKILL.md 与主库逐字节相同
  B. ~/.dsh/skills/AGENTS.repo.md 与主库相同
  C. ~/.dsh/AGENTS.md 与主库 AGENTS.repo.md 相同
  D. 运行环境里没有多余目录（只允许 12 个技能目录 + AGENTS.repo.md）
退出码：0 一致；1 有差异
"""
import hashlib
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def rd(p):
    with open(p, "rb") as f:
        return f.read()


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    home = os.path.expanduser("~")
    dsh = os.path.join(home, ".dsh")
    runtime = os.path.join(dsh, "skills")
    live = os.path.join(dsh, "AGENTS.md")

    errs = []
    names = []
    for name in sorted(os.listdir(repo)):
        p = os.path.join(repo, name, "SKILL.md")
        if os.path.isfile(p):
            names.append(name)

    for name in names:
        src = os.path.join(repo, name, "SKILL.md")
        dst = os.path.join(runtime, name, "SKILL.md")
        if not os.path.isfile(dst):
            errs.append("运行时缺 %s/SKILL.md" % name)
        elif sha(rd(src)) != sha(rd(dst)):
            errs.append("%s/SKILL.md 内容不一致" % name)

    agents = os.path.join(repo, "AGENTS.repo.md")
    ab = rd(agents)
    if not os.path.isfile(live) or rd(live) != ab:
        errs.append("~/.dsh/AGENTS.md 不一致")

    if os.path.isdir(runtime):
        allowed = set(names)
        extra = [d for d in os.listdir(runtime) if d not in allowed]
        if extra:
            errs.append("运行时有多余条目：" + ", ".join(sorted(extra)))

    print("=" * 64)
    print("技能 %d 个；AGENTS sha256=%s" % (len(names), sha(ab)[:16].upper()))
    if errs:
        for e in errs:
            print("  ✗ " + e)
        print("结论：不一致（请重跑 tools/sync-to-runtime.py）")
        return 1
    print("  ✓ 12 个 SKILL.md 逐字节相同")
    stray = []
    if os.path.isdir(runtime):
        for e in os.listdir(runtime):
            p = os.path.join(runtime, e)
            if os.path.isfile(p) and e.lower().endswith(".md"):
                stray.append(e)
    if stray:
        errs.append("运行端根目录散落 .md：" + ", ".join(sorted(stray)))
    else:
        print("  ✓ 运行端根目录无散落 .md")
    print("  ✓ ~/.dsh/AGENTS.md 相同")
    print("  ✓ 运行时无多余目录")
    print("结论：主库与运行环境完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
