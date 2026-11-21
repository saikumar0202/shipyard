#!/usr/bin/env python3
"""Route an issue event to an agent (docs/PIPELINE.md > Handoffs).

Pure decision in route(); main() reads the event and writes step outputs
agent (builder | none), issue, reason.

Version 1 (Build order step 4) routes the builder only:
  * `approved` added to a feature
  * `repro-ok` or `manual-repro` added to a bug, and no `hold`
  * `hold` removed, or `approved` added to a bug, while repro-ok/manual-repro is present
Planner, reproducer, @claude, must-fix and retry routes arrive with step 5.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

STOP = {"parked", "wontfix"}
REPRO = {"repro-ok", "manual-repro"}


def route(event_name, event):
    none = lambda reason: {"agent": "none", "issue": "", "reason": reason}
    if event_name != "issues":
        return none("event %s has no route yet" % event_name)
    issue = event.get("issue") or {}
    if "pull_request" in issue:
        return none("labels on pull requests have no route yet")
    if issue.get("state") != "open":
        return none("issue is closed")
    labels = {l["name"] for l in issue.get("labels", [])}
    if labels & STOP:
        return none("issue is parked or wontfix")
    action, label = event.get("action"), (event.get("label") or {}).get("name", "")
    n = str(issue["number"])
    builder = lambda reason: {"agent": "builder", "issue": n, "reason": reason}

    if action == "labeled" and label == "approved" and "feature" in labels:
        return builder("approved added to a feature")
    if "bug" in labels:
        has_repro = bool(labels & REPRO)
        if action == "labeled" and label in REPRO:
            if "hold" in labels:
                return none("%s added but the bug is on hold" % label)
            return builder("%s added" % label)
        if action == "labeled" and label == "approved" and has_repro:
            return builder("approved releases a held bug")
        if action == "unlabeled" and label == "hold" and has_repro:
            return builder("hold removed")
    return none("no route for %s %s" % (action, label))


def main():
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)
    r = route(os.environ["GITHUB_EVENT_NAME"], event)
    for k in ("agent", "issue", "reason"):
        lib.set_output(k, r[k])
    print("route: %s (%s)" % (r["agent"], r["reason"]))


if __name__ == "__main__":
    main()
