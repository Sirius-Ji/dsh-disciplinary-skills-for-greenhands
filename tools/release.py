#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版门禁 —— 把门禁从"提交级"抬到"发版级"。

为什么需要它：`pre-commit` 只保证"缺 HANDOFF 时不能提交"，但**发版**是另一回事——
提交、打 tag、推送之间没有任何机械点要求 HANDOFF 的版本号与 tag 一致。
本脚本把这条链接上：**先校验 → 再改版本号 → 再提交 → 再打 tag**，任何一步红就整体中止并回滚。

设计约束（都是踩过的坑）：
  1. 校验在改版本号**之前**跑一次、之后**再**跑一次。只在之后跑，等于自己给自己发通行证。
  2. 版本号只由 `bump_handoff.py` 写入（机器时间戳 + 单一来源），本脚本不手改 HANDOFF 字节。
  3. post-check 失败 ⇒ 立刻把 HANDOFF 还原成改动前的字节，不做"先留着"。
  4. tag 已存在 ⇒ 直接拒，绝不覆盖（覆盖 tag 是最难挽回的一类操作）。
  5. 版本号写进仓库的 `VERSION` 文件，否则 tag 指向的提交里**没有任何地方记录这个版本**，
     tag 就只是个标签，不能自证。
  6. 默认**不推送**；推送需要显式 `--push`。发版是人的决定。

用法：
    python tools/release.py --version v1.2.0 --dry-run     # 只体检，不动盘
    python tools/release.py --version v1.2.0               # 提交 + 打 tag（不推送）
    python tools/release.py --version v1.2.0 --push        # 再推送 master 与 tag

退出码：
    0  发版成功
    2  版本号格式非法，或 tag 已存在
    3  发版前门禁未通过（HANDOFF 缺失 / 过期 / 版本不符 / 时间戳在未来）
    4  发版后门禁复验未通过（已回滚 HANDOFF）
    5  工作树在本脚本之外仍有未提交改动（提交后仍不干净）
    6  git 操作失败；或 origin 指向外网/非本机路径（推送机械闸门拦下）
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

_BACKUP = None          # 兜底回滚用：main() 里创建备份后登记到模块级


def say(kind, msg):
    print("%s [release] %s" % (kind, msg))


def die(code, msg, hint=""):
    say("✗", msg)
    if hint:
        print("    修复：%s" % hint)
    sys.exit(code)


def run(args, cwd, capture=True):
    """调用 git / python。capture=False 时直接透传输出（给人看的命令用）。

    注意 encoding：Windows 上 text=True 默认按 GBK 解码子进程输出，
    而本项目的工具一律输出 UTF-8 ⇒ 必须显式指定，否则第一批中文就炸。
    """
    p = subprocess.run(args, cwd=cwd, text=True,
                       encoding="utf-8", errors="replace",
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    return p.returncode, (p.stdout or "").strip() if capture else ""


# ---- 推送机械闸门（注释拦不住脚本，只有这道闸门能把外网堵死）----
EXTERNAL_MARKERS = ("http://", "https://", "git@")
LOCAL_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def assert_local_origin(repo):
    """只允许把代码推到本机绝对路径的 origin；任何外网形态一律中止。

    判定（全部满足才放行）：
      1. 能读到 origin；
      2. 不含 http:// / https:// / git@ 任意外网特征；
      3. 是 Windows 本地绝对路径（形如 D:\\ 或 C:/）。
    其余情况一律 fail-closed —— 包括读不到 origin、相对路径、ssh://、file://。
    """
    rc, origin = run(["git", "remote", "get-url", "origin"], repo)
    origin = origin.strip() if rc == 0 else ""
    blocked = (not origin) or any(m in origin for m in EXTERNAL_MARKERS) \
        or not LOCAL_ABS_RE.match(origin)
    if blocked:
        print("Error: 绝对禁止向任何外网仓库执行 push！", file=sys.stderr)
        print("  origin = %s" % (origin or "<读取失败或未配置>"), file=sys.stderr)
        print("  只允许本机绝对路径，例如 D:\\xxx.git 或 C:\\xxx.git", file=sys.stderr)
        sys.exit(6)
    say("✓", "origin 是本机路径，放行：%s" % origin)


def main():
    ap = argparse.ArgumentParser(description="发版门禁：校验 → 改版本 → 提交 → 打 tag")
    ap.add_argument("--version", required=True, help="目标版本号，如 v1.2.0")
    ap.add_argument("--root", default=None, help="工作区根（默认为本仓库的上一级）")
    ap.add_argument("--repo", default=None, help="技能仓库路径（默认本脚本所在仓库）")
    ap.add_argument("--note", default="", help="额外写进提交说明的一句话")
    ap.add_argument("--push", action="store_true", help="推送 master 与该 tag（默认不推）")
    ap.add_argument("--dry-run", action="store_true", help="只做体检，不写盘、不提交、不打 tag")
    args = ap.parse_args()

    ver = args.version.strip()
    if not VERSION_RE.match(ver):
        die(2, "版本号格式非法：%r（应形如 v1.2.0）" % ver)

    repo = os.path.abspath(args.repo or os.path.join(os.path.dirname(__file__), ".."))
    root = os.path.abspath(args.root or os.path.dirname(repo))
    tools = os.path.join(repo, "tools")
    handoff = os.path.join(root, "HANDOFF.md")
    print("=" * 62)
    say("·", "仓库   : %s" % repo)
    say("·", "工作区 : %s" % root)
    say("·", "目标   : %s%s" % (ver, "   （dry-run）" if args.dry_run else ""))
    print("=" * 62)

    if not os.path.isfile(handoff):
        die(3, "找不到 %s —— 第 18 条：不存在也必须创建" % handoff)

    # --- 0. 分支与 tag 前置检查（在动任何东西之前）---
    rc, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    if rc != 0:
        die(6, "无法读取当前分支")
    if branch != "master":
        die(2, "当前分支是 %r，发版只允许在 master 上进行" % branch)

    rc, existing = run(["git", "tag", "-l", ver], repo)
    if existing.strip():
        die(2, "tag %s 已存在 —— 拒绝覆盖（覆盖 tag 最难挽回）" % ver,
            "换一个版本号，或确认后手工 `git tag -d %s` 再重跑。" % ver)

    # --- 1. 发版前门禁（改版本号之前）---
    rc, out = run([sys.executable, os.path.join(tools, "check_handoff.py"),
                   "--root", root, "--quiet"], repo)
    if rc != 0:
        die(3, "发版前门禁未通过（exit %d）：\n%s" % (rc, out),
            "先修好 HANDOFF.md 再来发版；发版不能成为绕过门禁的手段。")
    say("✓", "发版前门禁通过")

    if args.dry_run:
        rc, _ = run(["git", "status", "--porcelain"], repo)
        say("·", "dry-run：将把 version 改为 %s、写 VERSION、提交并打 tag，本次不动盘" % ver)
        say("·", "dry-run：当前未提交改动数量 = %d"
            % len([l for l in run(["git", "status", "--porcelain"], repo)[1].splitlines() if l]))
        sys.exit(0)

    # --- 2. 备份 HANDOFF，改版本号 ---
    backup = handoff + ".pre-release.bak"
    shutil.copy2(handoff, backup)
    global _BACKUP
    _BACKUP = backup
    rc, out = run([sys.executable, os.path.join(tools, "bump_handoff.py"),
                   "--root", root, "--version", ver], repo)
    print(out)
    if rc != 0:
        shutil.copy2(backup, handoff)
        die(3, "写版本号失败，HANDOFF 已还原：%s" % out)

    # --- 3. 发版后门禁复验（必须带 --version，否则等于没验）---
    rc, out = run([sys.executable, os.path.join(tools, "check_handoff.py"),
                   "--root", root, "--version", ver], repo)
    if rc != 0:
        shutil.copy2(backup, handoff)
        die(4, "发版后复验未通过（exit %d），HANDOFF 已还原：\n%s" % (rc, out))
    print(out)
    say("✓", "发版后门禁复验通过（version 与 tag 已对齐）")

    # --- 4. VERSION 文件：让 tag 指向的提交能自证版本 ---
    vf = os.path.join(repo, "VERSION")
    with open(vf, "w", encoding="utf-8", newline="\n") as f:
        f.write(ver + "\n")
    say("✓", "已写 %s" % vf)

    # --- 5. 提交 ---
    run(["git", "add", "-A"], repo)
    rc, staged = run(["git", "diff", "--cached", "--name-only"], repo)
    if staged.strip():
        files = [l for l in staged.splitlines() if l]
        msg = "release: %s\n\n- HANDOFF.md version -> %s\n- VERSION -> %s\n- 涉及文件：%d 个" \
              % (ver, ver, ver, len(files))
        if args.note:
            msg += "\n- " + args.note
        rc, out = run(["git", "commit", "-m", msg], repo, capture=False)
        if rc != 0:
            shutil.copy2(backup, handoff)
            die(6, "git commit 失败（门禁可能拦下了这次提交），HANDOFF 已还原")
        say("✓", "已提交")
    else:
        say("·", "工作树无改动，跳过提交（只打 tag）")

    rc, dirty = run(["git", "status", "--porcelain"], repo)
    if dirty.strip():
        die(5, "提交后工作树仍不干净：\n%s" % dirty)

    # --- 6. 打 tag ---
    rc, head = run(["git", "rev-parse", "--short", "HEAD"], repo)
    tag_msg = "%s — HANDOFF version 同步，VERSION 文件记录" % ver
    rc, out = run(["git", "tag", "-a", ver, "-m", tag_msg], repo)
    if rc != 0:
        die(6, "打 tag 失败：%s" % out)
    say("✓", "已打 tag %s @ %s（annotated）" % (ver, head))

    # ★ 绝对禁止向任何外网/公网执行 git push。本地的裸库、工作区互相同步属于本地开发日常，不受此限。
    #   --push 只会推给 origin；执行前先 `git remote -v` 确认 origin 是本地路径（不是 GitHub/Gitee）。
    # --- 7. 推送（默认不做）---
    if args.push:
        assert_local_origin(repo)          # 闸门：外网 origin 直接中止
        rc, out = run(["git", "push", "origin", "master"], repo)
        if rc != 0:
            die(6, "推送 master 失败：%s" % out)
        rc, out = run(["git", "push", "origin", ver], repo)
        if rc != 0:
            die(6, "推送 tag 失败：%s" % out)
        say("✓", "已推送 master 与 tag %s" % ver)
    else:
        say("·", "未推送。要发到远端请执行（仅限本地裸库；外网/公网一律禁止）：")
        print("    cd %s" % repo)
        print("    # 绝对禁止向任何外网/公网执行 git push。本地的裸库、工作区互相同步属于本地开发日常，不受此限。")
        print("    git push origin master")
        print("    git push origin %s" % ver)

    os.remove(backup) if os.path.exists(backup) else None
    print("=" * 62)
    say("✓", "发版完成：%s @ %s ；工作树干净" % (ver, head))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:                     # noqa: BLE001 —— 兜底回滚，宁可报错也不留半成品
        say("✗", "未预期异常：%s: %s" % (type(exc).__name__, exc))
        if _BACKUP and os.path.exists(_BACKUP):
            shutil.copy2(_BACKUP, os.path.join(os.path.dirname(_BACKUP), "HANDOFF.md"))
            say("·", "已从备份还原 HANDOFF.md")
        sys.exit(4)
