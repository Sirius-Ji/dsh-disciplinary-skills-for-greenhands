#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 D 盘主库单向同步到运行环境 ~/.dsh（禁止反向）。

架构（2026-11-06 定案）：
  唯一 Git 主库 : 本仓库（<你的主库路径>/skills）
  纯运行环境    : ~/.dsh/skills/  +  ~/.dsh/AGENTS.md
  同步方向      : D 盘 -> C 盘，永远单向；运行环境是只读产物

白名单（只搬这些，其余一个字节都不进运行时）：
  <技能名>/SKILL.md   （12 个）
  AGENTS.repo.md      （再改名复制成 ~/.dsh/AGENTS.md）

为什么不用「整目录改名」：Windows 上 ~/.dsh/skills 常被宿主占用，
os.rename(directory) 会直接 WinError 5。所以改成逐文件：
写 .tmp -> os.replace() 原子替换单个文件，不碰目录本身。
失败时按记录的原内容回滚，运行环境保持原样。
退出码：0 成功；1 失败（已回滚）
"""
import hashlib
import os
import shutil
import sys
import time

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
    ts = time.strftime("%Y%m%d-%H%M%S")

    print("=" * 64)
    print("源   : " + repo)
    print("目标 : " + runtime)
    print("     : " + live)

    agents_src = os.path.join(repo, "AGENTS.repo.md")
    if not os.path.isfile(agents_src):
        print("✗ 主库缺少 AGENTS.repo.md")
        return 1

    skills = {}
    for name in sorted(os.listdir(repo)):
        p = os.path.join(repo, name, "SKILL.md")
        if os.path.isfile(p):
            skills[name] = p
    if len(skills) != 12:
        print("! 注意：技能数 = %d（预期 12）" % len(skills))

    for e in os.listdir(dsh):
        if e.startswith("skills.new-") or e.startswith("skills.old-"):
            shutil.rmtree(os.path.join(dsh, e), ignore_errors=True)
            print("· 清掉残留临时目录 " + e)

    os.makedirs(runtime, exist_ok=True)

    plan = []
    for name, src in skills.items():
        plan.append((src, os.path.join(runtime, name, "SKILL.md")))
    # 运行端不再保留 AGENTS.repo.md（2026-11-06 用户裁定）：只留 ~/.dsh/AGENTS.md
    plan.append((agents_src, live))

    originals = {}
    written = []
    try:
        for src, dst in plan:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            originals[dst] = rd(dst) if os.path.isfile(dst) else None
            tmp = dst + ".tmp-" + ts
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            written.append(dst)
    except OSError as e:
        print("✗ 写入失败：%s" % e)
        for dst in reversed(written):
            old = originals.get(dst)
            try:
                if old is None:
                    if os.path.isfile(dst):
                        os.remove(dst)
                else:
                    with open(dst, "wb") as f:
                        f.write(old)
            except OSError:
                pass
        print("  已按原内容回滚")
        return 1

    allowed = set(skills)
    removed = []
    for e in sorted(os.listdir(runtime)):
        if e in allowed:
            continue
        p = os.path.join(runtime, e)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            removed.append(e)
        except OSError as ex:
            print("! 删除多余条目失败：%s（%s）" % (e, ex))

    fails = []
    for name, src in skills.items():
        dst = os.path.join(runtime, name, "SKILL.md")
        if not os.path.isfile(dst) or sha(rd(dst)) != sha(rd(src)):
            fails.append(name + "/SKILL.md")
    if not os.path.isfile(live) or sha(rd(live)) != sha(rd(agents_src)):
        fails.append("~/.dsh/AGENTS.md")

    if fails:
        print("✗ 复验失败：" + ", ".join(fails))
        return 1

    print("-" * 64)
    print("✓ 同步完成 " + ts)
    print("  技能 %d 个 -> %s" % (len(skills), runtime))
    print("  AGENTS.repo.md -> AGENTS.md  %d B  sha256=%s"
          % (len(rd(agents_src)), sha(rd(agents_src))[:16].upper()))
    if removed:
        print("  清掉运行环境多余条目：" + ", ".join(removed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
