#!/usr/bin/env python3
"""Build the run-time settings file for one agent run.

Starts from settings/<role>.json (in shipyard, pinned by tag), then:
  * for builder/reproducer, adds Bash(<cmd>:*) for each project command from
    the caller's bash_commands input (one per line);
  * repeats the path deny rules with absolute paths for this workspace, so
    they hold however Claude spells the path.
Usage: make_settings.py <role> <workspace> <out-file>   (commands on stdin)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

# A project command is a plain command line: no shell operators, so a caller
# input can never smuggle in "pnpm test; curl ..." or a wildcard.
CMD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/=@+-]*$")


def build(role, workspace, commands):
    with open(os.path.join(lib.ROOT, "settings", role + ".json")) as f:
        s = json.load(f)
    perms = s["permissions"]
    if commands and role not in lib.WRITER_ROLES:
        raise ValueError("bash_commands are only allowed for builder and reproducer")
    for c in commands:
        if not CMD_RE.match(c) or c.startswith("git "):
            raise ValueError("refusing project command %r" % c)
        perms["allow"].append("Bash(%s:*)" % c)
    ws = workspace.rstrip("/")
    for d in (".git", ".github", ".claude"):
        for tool in ("Edit", "Write"):
            perms["deny"].append("%s(/%s/%s/**)" % (tool, ws, d))
    return s


def main():
    role, ws, out = sys.argv[1:4]
    commands = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    s = build(role, ws, commands)
    with open(out, "w") as f:
        json.dump(s, f, indent=2)
    print("settings for %s: allow=%s" % (role, s["permissions"]["allow"]))


if __name__ == "__main__":
    main()
