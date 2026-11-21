#!/usr/bin/env python3
"""Refuse protected and LFS-tracked paths in a patch (post job).
Reads NUL-separated changed paths on stdin; argv[1] is a file with
`git check-attr -z filter` output for those paths, evaluated against the
BASE commit's .gitattributes. Exits 1 and prints the reason if refused."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def lfs_paths(check_attr_z):
    parts = check_attr_z.split("\0")
    out = []
    for i in range(0, len(parts) - 2, 3):
        path, attr, value = parts[i:i + 3]
        if attr == "filter" and value == "lfs":
            out.append(path)
    return out


def main():
    paths = [p for p in sys.stdin.read().split("\0") if p]
    with open(sys.argv[1]) as f:
        lfs = lfs_paths(f.read())
    bad = lib.protected_paths(paths)
    msgs = []
    if bad:
        msgs.append("protected paths (.github/, .claude/, pipeline.yml): " + ", ".join(bad))
    if lfs:
        msgs.append("LFS-tracked paths (asset changes are yours): " + ", ".join(lfs))
    if msgs:
        print("; ".join(msgs))
        sys.exit(1)
    print("paths ok: %d file(s)" % len(paths))


if __name__ == "__main__":
    main()
