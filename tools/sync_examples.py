#!/usr/bin/env python3
# AI 生成 / 辅助创作：DeepSeek V4.1 Flash（未人工审查）
"""把 examples/<name>/<name>.hpappdir 的构建产物同步进 packages/<name>-1.0/。

用法：先在各示例目录 make，然后 `python3 tools/sync_examples.py`，
最后用 nb-pkg 重新生成哈希：`python3 -m nb_pkg hash .. --write`。
"""
import glob
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = (".elf", ".hpapp", ".hpappnote", ".hpappprgm", ".png", ".json")


def main():
    for hp in sorted(glob.glob(os.path.join(ROOT, "examples", "*", "*.hpappdir"))):
        name = os.path.basename(hp)[:-9]
        pkg = os.path.join(ROOT, "packages", "%s-1.0" % name)
        if not os.path.isfile(os.path.join(pkg, "pkg.cfg")):
            print("skip (no package):", name)
            continue
        n = 0
        for f in sorted(os.listdir(hp)):
            if not f.endswith(KEEP):
                continue
            shutil.copy2(os.path.join(hp, f), os.path.join(pkg, f))
            n += 1
        print("sync %-8s -> %s (%d file(s))" % (name, os.path.relpath(pkg, ROOT), n))


if __name__ == "__main__":
    main()
