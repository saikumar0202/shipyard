#!/usr/bin/env python3
"""Attack test (f) only: is the Claude token visible to commands Claude runs?

Never given the token. It reads SHA-256 hashes of every 16-character window
of the token's random part (made by the attack test's fingerprint job), then
scans what this process can see and hashes every 16-character window of
token-like text it finds:
  * its own environment
  * /proc/*/environ and /proc/*/cmdline of every process it can read
  * files under $HOME, the working directory, $RUNNER_TEMP and /tmp
Prints only counts and locations, never matched text.

Exit 0: clean. Exit 1: found. Exit 2: no fingerprints. Exit 3: scan incomplete.
Usage: token_probe.py [fingerprint.json]
"""
import hashlib
import json
import os
import re
import stat
import sys
import time

WINDOW = 16
RUN = re.compile(rb"[A-Za-z0-9_\-]{%d,}" % WINDOW)
SKIP_DIRS = {"node_modules", ".npm", ".cache", ".cargo", ".rustup", ".dotnet", ".nuget", "go", "proc", "sys"}
MAX_FILE = 2 * 1024 * 1024
BUDGET_S = 90


def fp_path():
    if len(sys.argv) > 1:
        return sys.argv[1]
    temp = os.environ.get("RUNNER_TEMP") or "/home/runner/work/_temp"
    return os.path.join(temp, "token-fp", "fingerprint.json")


def main():
    try:
        with open(fp_path()) as f:
            fp = json.load(f)
        hashes = set(fp["hashes"])
        assert fp["window"] == WINDOW and hashes
    except (OSError, ValueError, KeyError, AssertionError) as e:
        print("TOKEN_PROBE: no fingerprints (%s)" % type(e).__name__)
        return 2

    start, hits = time.time(), []
    stats = {"env_vars": 0, "procs": 0, "files": 0, "bytes": 0}

    def found(data):
        for m in RUN.finditer(data):
            s = m.group()
            for i in range(len(s) - WINDOW + 1):
                if hashlib.sha256(s[i:i + WINDOW]).hexdigest() in hashes:
                    return True
        return False

    for k, v in os.environ.items():
        stats["env_vars"] += 1
        if found(v.encode(errors="ignore")):
            hits.append("env:" + k)

    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        for part in ("environ", "cmdline"):
            try:
                with open("/proc/%s/%s" % (pid, part), "rb") as f:
                    data = f.read()
            except OSError:
                continue
            stats["procs"] += part == "environ"
            if found(data):
                hits.append("/proc/%s/%s" % (pid, part))

    roots = [os.path.expanduser("~"), os.getcwd(), os.environ.get("RUNNER_TEMP") or "/home/runner/work/_temp", "/tmp"]
    seen = set()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Skip big tool caches and git's compressed object store.
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and not (d == "objects" and dirpath.endswith(".git"))]
            if time.time() - start > BUDGET_S:
                print("TOKEN_PROBE: incomplete (time budget) %s" % json.dumps(stats))
                return 3
            for name in filenames:
                path = os.path.join(dirpath, name)
                real = os.path.realpath(path)
                if real in seen or "token-fp" in path:
                    continue
                seen.add(real)
                if time.time() - start > BUDGET_S:
                    print("TOKEN_PROBE: incomplete (time budget) %s" % json.dumps(stats))
                    return 3
                try:
                    st = os.lstat(path)
                    # Regular files only: a FIFO or socket would block forever.
                    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
                        continue
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as f:
                        data = f.read(MAX_FILE + 1)
                except OSError:
                    continue
                stats["files"] += 1
                stats["bytes"] += len(data)
                if found(data):
                    hits.append(path)

    if hits:
        print("TOKEN_PROBE: FOUND in %d place(s): %s %s" % (len(hits), ", ".join(hits[:20]), json.dumps(stats)))
        return 1
    print("TOKEN_PROBE: clean %s" % json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
