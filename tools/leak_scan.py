#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前脱敏扫描器 —— 正/反斜杠双写，专治「只认反斜杠」的瞎眼扫描。

为什么非有它不可（2026-11-06 事故）：发布前复扫的模式只写了反斜杠形态
（盘符 + 反斜杠 + 目录），漏掉同一路径的正斜杠写法；两处真实本机路径被发进
开源仓，还被「0 命中」假绿骗过整整一轮。教训不是「手滑」，是**测量只对一半样本敏感**。

  BLOCK 真实身份 / 本机路径：当前用户名、主机名、本机主库路径（正反斜杠都算）、主库目录名
  WARN  其它盘符绝对路径：列出供人工判断；加 --strict 即视为失败

用法（把 <发布仓路径> 换成本机目录）：
    python tools/leak_scan.py --root <发布仓路径>
    python tools/leak_scan.py --root . --strict
    python tools/leak_scan.py --selftest              # 自检：喂伪造样本，必须全抓到
    python tools/leak_scan.py --root . --block "内部项目名,备份目录名"

退出码：0 干净 / 1 有 BLOCK（或 --strict 下有 WARN）/ 2 参数或路径错 / 3 自检失败

注意：本文件**不含任何真实用户名、主机名、项目名**——全部在运行时从环境与自身路径推导，
所以它可以原样发布到开源仓；扫描时对它只做 BLOCK 判定、不做 WARN 判定（见扫描循环）。
"""

import argparse
import getpass
import os
import re
import socket
import sys

sys.stdout.reconfigure(encoding="utf-8")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}
SELF_NAME = "leak_scan.py"
ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/]")
# 占位符 / 通用系统路径 / 案发现场证据：出现绝对路径但属正常写法，不算 WARN。
# 这里刻意只用**不含盘符**的纯文本标记，免得本文件自己被自己的正则命中。
PLACEHOLDER_HINTS = (
    "<你的", "某项目", "某个项目", "path\\to", "path/to", "$Recycle", "HKLM:",
    "Program Files", "Windows\\system32", "texlive", "miniconda", "Users\\<", "Users/<",
    "你的名字", "Pro;ram", "some\\\\ws", "Fake/TestProj", "Fake\\TestProj",
    "faketestuser", "fakehost01", "ram Files", ".Bin ---", "判据一句话",
)


def auto_block_patterns():
    """从运行环境推导本机敏感串，保证源码里不出现真实身份。"""
    pats = []
    for fn in (getpass.getuser, socket.gethostname):
        try:
            v = fn()
        except Exception:
            v = ""
        if v and len(v) >= 3:
            pats.append(v)
    # 自身路径 = 所在仓库根（主库里是 skills/，发布仓里是 skills/），正反两种写法都拦
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pats.append(root.replace("\\", "/"))
    pats.append(root.replace("/", "\\"))
    # 仓库的上级目录名（主库里就是私有主库目录名），单靠名字即可拦两种斜杠
    name = os.path.basename(os.path.dirname(root))
    if name and len(name) >= 3:
        pats.append(name)
    return sorted(set(p for p in pats if p))


def classify(line, block_pats, allow_warn=True):
    """返回 (level, hit_pattern)；level 为 BLOCK / WARN / None。"""
    for p in block_pats:
        if p in line:
            return "BLOCK", p
    if not allow_warn:
        return None, None
    m = ABS_PATH_RE.search(line)
    if m and not any(h in line for h in PLACEHOLDER_HINTS):
        return "WARN", m.group(0)
    return None, None


def scan(root, block_pats, strict):
    blocked = warned = 0
    files = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root).replace("\\", "/")
            try:
                text = open(p, "rb").read().decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            files += 1
            allow_warn = fn != SELF_NAME  # 扫描器自身只做 BLOCK 判定
            for i, line in enumerate(text.splitlines(), 1):
                level, pat = classify(line, block_pats, allow_warn)
                if level == "BLOCK":
                    blocked += 1
                    print("  BLOCK %s:%d  [%s]  %s" % (rel, i, pat, line.strip()[:96]))
                elif level == "WARN":
                    warned += 1
                    print("  WARN  %s:%d  [%s]  %s" % (rel, i, pat, line.strip()[:96]))
    print("\n扫描 %d 个文件  BLOCK=%d  WARN=%d  模式=%d 条"
          % (files, blocked, warned, len(block_pats)))
    if blocked:
        print("✗ 有 BLOCK 命中：不许发布")
        return 1
    if warned and strict:
        print("✗ --strict：WARN 也算失败")
        return 1
    print("✓ 通过")
    return 0


def selftest():
    """喂伪造样本：正/反斜杠两种写法、用户名、主机名都必须被抓到；占位符必须放行。"""
    fake_root = "D:/Fake/TestProj/skills"
    pats = [fake_root, fake_root.replace("/", "\\"), "TestProj", "faketestuser", "fakehost01"]
    must_block = [
        "路径是 " + fake_root + "/tools",
        "路径是 " + fake_root.replace("/", "\\"),
        "C:/Users/faketestuser/x.py",
        "C:\\Users\\faketestuser\\x.py",
        "host=fakehost01",
    ]
    must_pass = ["<你的主库路径>/skills", "C:\\Program Files\\Git\\cmd", "D:\\path\\to\\file.pdf"]
    bad = 0
    for s in must_block:
        lv, _ = classify(s, pats)
        if lv != "BLOCK":
            print("  ✗ 漏抓: %s（判成 %s）" % (s, lv))
            bad += 1
    for s in must_pass:
        lv, _ = classify(s, pats)
        if lv == "BLOCK":
            print("  ✗ 误杀: %s" % s)
            bad += 1
    # 自指测试：本文件绝不能含真实身份（用当前环境推导的 BLOCK 模式反打自己）
    self_bad = 0
    for line in open(os.path.abspath(__file__), "rb").read().decode("utf-8").splitlines():
        lv, pat = classify(line, auto_block_patterns(), allow_warn=False)
        if lv == "BLOCK":
            print("  ✗ 自指泄漏: [%s] %s" % (pat, line.strip()[:80]))
            self_bad += 1
    print("自检：%d 条必拦 + %d 条必放 + 自指扫描，失败 %d 条"
          % (len(must_block), len(must_pass), bad + self_bad))
    return 0 if bad + self_bad == 0 else 3


def main():
    ap = argparse.ArgumentParser(description="发布前脱敏扫描器（正/反斜杠双写）")
    ap.add_argument("--root", default=".", help="要扫描的目录")
    ap.add_argument("--block", default="", help="附加拦截词，逗号分隔")
    ap.add_argument("--strict", action="store_true", help="WARN 也算失败")
    ap.add_argument("--selftest", action="store_true", help="只跑自检")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("✗ 目录不存在：%s" % root)
        sys.exit(2)

    pats = auto_block_patterns()
    pats += [x.strip() for x in args.block.split(",") if x.strip()]
    print("扫描根：%s" % root)
    print("BLOCK 模式 %d 条（含本机用户名 / 主机名 / 仓库路径两种写法）" % len(pats))
    sys.exit(scan(root, pats, args.strict))


if __name__ == "__main__":
    main()
