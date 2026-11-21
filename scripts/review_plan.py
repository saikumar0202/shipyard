#!/usr/bin/env python3
"""Which reviewers run on this PR, and which issue it belongs to
(docs/PIPELINE.md > AI review > Who). No AI, no network.

code and qa always, plus every review:<name> label on the PR whose name is
in the active panel; other names get a warning and are skipped. The issue is
the one in "Closes #n" (the builder writes it), else the PR itself.
Writes step outputs: names (JSON list), issue.
Env: GITHUB_EVENT_PATH (a pull_request event)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402
from repro_guard import linked_issue  # noqa: E402


def plan(pr):
    names = list(lib.load_config("panel.json")["always"])
    skipped = []
    for label in sorted(l["name"] for l in pr.get("labels", [])):
        if not label.startswith("review:"):
            continue
        name = label[len("review:"):]
        if name in lib.panel():
            if name not in names:
                names.append(name)
        else:
            skipped.append(name)
    return names, linked_issue(pr.get("body")) or pr["number"], skipped


def main():
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        pr = json.load(f)["pull_request"]
    names, issue, skipped = plan(pr)
    for s in skipped:
        print("::warning::review:%s is not in the active panel; skipped" % s)
    lib.set_output("names", json.dumps(names))
    lib.set_output("issue", str(issue))
    print("reviewers: %s; issue #%s" % (", ".join(names), issue))


if __name__ == "__main__":
    main()
