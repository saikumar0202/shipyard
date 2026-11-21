#!/usr/bin/env python3
"""repro-guard (docs/PIPELINE.md > Build > Fixes): on a fix PR, the files the
reproducer added in its repro-sha commit must be unchanged at the PR head.

Runs in the project's CI `test` job, in a full-history checkout of the PR.
The issue comes from "Closes #n" in the PR body; the repro-sha from the
latest pipeline-bot comment on that issue. No repro-sha -> not a fix PR with
an automated test (feature, or manual-repro) -> passes.

Env: GITHUB_REPOSITORY, GITHUB_TOKEN (issues: read), GITHUB_EVENT_PATH,
     PIPELINE_BOT
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)


def linked_issue(pr_body):
    m = CLOSES_RE.search(pr_body or "")
    return int(m.group(1)) if m else None


def git(*args):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args],
                          capture_output=True, text=True, check=True).stdout


def guard(repro_sha, head="HEAD"):
    """Return the list of problems (empty = pass)."""
    added = [p for p in git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
                            "--diff-filter=A", "--root", repro_sha).split("\0") if p]
    if not added:
        return ["repro-sha %s adds no files" % repro_sha[:12]]
    changed = [p for p in git("diff", "--name-only", "-z", "--no-renames", repro_sha, head, "--", *added).split("\0") if p]
    return ["%s was modified or deleted after repro-sha %s" % (p, repro_sha[:12]) for p in changed]


def main():
    env = os.environ
    with open(env["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)
    issue = linked_issue((event.get("pull_request") or {}).get("body"))
    if not issue:
        print("repro-guard: PR has no 'Closes #n'; nothing to guard")
        return
    comments = lib.gh_paginate("/repos/%s/issues/%d/comments" % (env["GITHUB_REPOSITORY"], issue), env.get("GITHUB_TOKEN"))
    items = [{"login": (c.get("user") or {}).get("login"), "body": c.get("body"), "created_at": c.get("created_at")}
             for c in comments]
    sha = lib.latest_repro_sha(items, env.get("PIPELINE_BOT", ""))
    if not sha:
        print("repro-guard: issue #%d has no repro-sha; nothing to guard" % issue)
        return
    problems = guard(sha)
    if problems:
        for p in problems:
            print("::error::repro-guard: %s" % p)
        sys.exit(1)
    print("repro-guard: files from repro-sha %s are unchanged" % sha[:12])


if __name__ == "__main__":
    main()
