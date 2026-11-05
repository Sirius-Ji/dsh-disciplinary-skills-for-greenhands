#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HANDOFF 时间戳机器生成器 —— 消除"手写时间戳"这个门禁漏洞的根因。

真实事故：HANDOFF.md 的 updated_at 被手写成 23:45，而文件实际写盘时间是 23:11。
结果 `check_handoff.py --max-age-days` 算出的 age_days 是负数，
`age_days > 30` 永远为假，新鲜度检查永久骗绿。

根因不是断言写错了，是**时间戳来源**错了：人手写的东西没有测量价值。
所以把时间戳从"人要填的字段"改成"工具生成的结果"。

用法：
    python bump_handoff.py                       # 只刷新 ~/.dsh/HANDOFF.md 的 updated_at
    python bump_handoff.py --version v1.1.1      # 同时把 version 改成 v1.1.1
    python bump_handoff.py --root D:\\some\\ws    # 指定其它工作区

行为：
    - updated_at 一律取本机 datetime.now()（带本地时区偏移），不接受 --at 之类的手动值。
    - 只改第一处 `updated_at:` / `version:` 头字段，正文一个字节不动。
    - 保留原文件行尾（本仓库 HANDOFF 是纯 LF），不做行尾翻译。

退出码：
    0  已更新
    2  找不到 HANDOFF.md
    3  找不到 updated_at 字段（头部语法不符合约定）
"""

import argparse
import datetime as _dt
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="HANDOFF.md 时间戳机器生成器")
    ap.add_argument("--root", default=os.getcwd(), help="工作区根目录")
    ap.add_argument("--version", default=None, help="同时改写 version 字段")
    ap.add_argument("--dry-run", action="store_true", help="只打印将写入的值")
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    path = os.path.join(root, "HANDOFF.md")
    if not os.path.isfile(path):
        print("✗ [bump] 找不到 %s" % path)
        sys.exit(2)

    raw = open(path, "rb").read()
    text = raw.decode("utf-8")
    eol = "\r\n" if b"\r\n" in raw else "\n"

    now = _dt.datetime.now().astimezone().replace(microsecond=0)
    now_s = now.isoformat()

    new, n = re.subn(r"(?m)^updated_at:.*$", "updated_at: " + now_s, text, count=1)
    if n == 0:
        print("✗ [bump] 头部没有 `updated_at:` 字段，不要猜，先补字段")
        sys.exit(3)
    if args.version:
        new, n2 = re.subn(r"(?m)^version:.*$", "version: " + args.version, new, count=1)
        if n2 == 0:
            print("✗ [bump] 头部没有 `version:` 字段")
            sys.exit(3)

    if args.dry_run:
        print("[dry-run] updated_at -> %s" % now_s)
        if args.version:
            print("[dry-run] version   -> %s" % args.version)
        sys.exit(0)

    out = new.replace("\r\n", "\n").replace("\n", eol).encode("utf-8")
    try:
        with open(path, "wb") as f:
            f.write(out)
    except OSError as exc:
        print("✗ [bump] 写不进去：%s" % exc)
        print("   常见原因：文件被设成只读、被杀软/编辑器占用、或目录权限不足。")
        print("   处理：attrib -R \"%s\" 后重试；不要绕过它去手改时间戳。" % path)
        sys.exit(4)

    crlf = out.count(b"\r\n")
    bare_lf = out.count(b"\n") - crlf
    print("✓ [bump] %s" % path)
    print("   updated_at -> %s  (机器生成，不是手写)" % now_s)
    if args.version:
        print("   version    -> %s" % args.version)
    print("   bytes=%d  CRLF=%d  bareLF=%d  eol=%s" % (len(out), crlf, bare_lf,
                                                      "CRLF" if eol == "\r\n" else "LF"))
    sys.exit(0)


if __name__ == "__main__":
    main()
