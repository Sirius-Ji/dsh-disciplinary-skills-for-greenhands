#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""make_release_zip.py —— 把发布仓打成 GitHub Release 用的 zip。

为什么用 `git ls-files` 而不是 os.walk：发布包的内容应该**恰好等于仓库追踪的内容**。
walk 会把 .git/、__pycache__/、编辑器临时文件、别人丢进来的 .zip 一起兜进去，
再靠黑名单去删——迟早漏一个。ls-files 从定义上就不可能有这些。

包内统一加一层 `<仓库名>-<版本>/` 根目录，模仿 GitHub 自动生成包的形状，
解压后不会把一堆目录直接糊在当前文件夹里。

用法：
    python tools/make_release_zip.py                       # 默认：打包脚本所在仓库 -> <仓库>/release
    python tools/make_release_zip.py --repo <发布仓路径> --out-dir <输出目录>
    python tools/make_release_zip.py --no-prefix           # 不要顶层目录（内容直接在根）
    python tools/make_release_zip.py --list                # 只打印会打进去的文件，不生成

默认值刻意用「脚本自身所在仓库」推导，不写死任何本机绝对路径——
主库里跑就打主库，发布仓里跑就打发布仓，脚本本身可以原样开源。

退出码：0 成功 / 2 参数或路径错 / 3 仓库没有任何追踪文件 / 4 版本文件缺失
"""

import argparse
import hashlib
import os
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

EXCLUDE_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}


def tracked_files(repo):
    """返回仓库里被 Git 追踪的相对路径（正斜杠）。失败则返回 None。"""
    try:
        out = subprocess.run(["git", "-C", repo, "ls-files", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [p for p in out.decode("utf-8").split("\0") if p]


def walk_files(repo):
    """没装 Git 时的兜底：走目录，但同样剔除已知垃圾目录。"""
    res = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_PARTS]
        for fn in filenames:
            if fn.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, fn)
            res.append(os.path.relpath(full, repo).replace("\\", "/"))
    return sorted(res)


def main():
    ap = argparse.ArgumentParser(description="把发布仓打成 Release zip")
    default_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--repo", default=default_repo, help="默认 = 脚本所在的仓库根")
    ap.add_argument("--out-dir", default=None, help="默认 = <repo>/release")
    ap.add_argument("--name", default="dsh-disciplinary-skills")
    ap.add_argument("--version", default=None, help="默认读仓库根的 VERSION 文件")
    ap.add_argument("--no-prefix", action="store_true", help="不加顶层目录")
    ap.add_argument("--list", action="store_true", dest="only_list")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        print("✗ 仓库目录不存在：%s" % repo)
        return 2
    out_dir = args.out_dir or os.path.join(repo, "release")

    version = args.version
    if not version:
        vp = os.path.join(repo, "VERSION")
        if not os.path.isfile(vp):
            print("✗ 缺少 VERSION 文件，且没给 --version")
            return 4
        version = open(vp, "rb").read().decode("utf-8").strip()
    stem = "%s-%s" % (args.name, version)

    files = tracked_files(repo)
    source = "git ls-files"
    if files is None:
        files = walk_files(repo)
        source = "os.walk（未找到 Git，已剔除 .git/__pycache__）"
    files = [f for f in files if not (set(f.split("/")) & EXCLUDE_PARTS)]
    if not files:
        print("✗ 仓库没有任何追踪文件：%s" % repo)
        return 3

    if args.only_list:
        print("来源：%s，共 %d 个文件" % (source, len(files)))
        for f in files:
            print("  " + f)
        return 0

    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, stem + ".zip")
    raw_total = 0
    prefix = "" if args.no_prefix else stem + "/"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in files:
            full = os.path.join(repo, rel.replace("/", os.sep))
            zf.write(full, arcname=prefix + rel)
            raw_total += os.path.getsize(full)

    size = os.path.getsize(zip_path)
    sha = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
    print("✓ 已生成：%s" % zip_path)
    print("  来源      : %s" % source)
    print("  文件数    : %d（原始 %d B = %.1f KB）" % (len(files), raw_total, raw_total / 1024.0))
    print("  压缩后    : %d B = %.2f KB（压缩率 %.1f%%）"
          % (size, size / 1024.0, 100.0 * size / raw_total if raw_total else 0))
    print("  sha256    : %s" % sha)
    print("  包内根目录: %s" % (prefix or "（无，内容直接在根）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
