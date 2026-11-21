#!/usr/bin/env python3
"""Merge readiness (docs/PIPELINE.md > AI review > Merge readiness).

Runs on workflow_run (completed) of the project's CI and preview workflows.
For every open PR whose head is the run's head sha, recomputes from the
check runs on that commit and creates or updates one `ready` check:
  web:   test, e2e, and review/<name> for every review:<name> label on the PR
         (code and qa always)
  other: test and the review/<name> checks only
`ready` fails when any required check failed, stays in progress while any is
missing or running, and succeeds when all passed.

Env: GITHUB_REPOSITORY, APP_TOKEN, GITHUB_EVENT_PATH, PROJECT_TYPE
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

OK = {"success", "skipped", "neutral"}


def required_checks(project_type, pr_labels):
    names = set(lib.load_config("panel.json")["always"])
    names |= {l[len("review:"):] for l in pr_labels if l.startswith("review:") and l[len("review:"):] in lib.panel()}
    req = ["test"] + (["e2e"] if project_type == "web" else [])
    return req + ["review/" + n for n in sorted(names)]


def decide(required, check_runs):
    """check_runs: [{name, status, conclusion, completed_at, started_at}].
    The newest run of each name counts. Returns (status, conclusion, summary)."""
    latest = {}
    for c in check_runs:
        key = c.get("completed_at") or c.get("started_at") or ""
        if c["name"] not in latest or key >= (latest[c["name"]].get("completed_at") or latest[c["name"]].get("started_at") or ""):
            latest[c["name"]] = c
    failed, waiting, passed = [], [], []
    for name in required:
        c = latest.get(name)
        if not c or c.get("status") != "completed":
            waiting.append(name)
        elif c.get("conclusion") in OK:
            passed.append(name)
        else:
            failed.append("%s (%s)" % (name, c.get("conclusion")))
    lines = ["Required: " + ", ".join(required)]
    if failed:
        lines.append("Failed: " + ", ".join(failed))
    if waiting:
        lines.append("Waiting for: " + ", ".join(waiting))
    summary = "\n\n".join(lines)
    if failed:
        return "completed", "failure", summary
    if waiting:
        return "in_progress", None, summary
    return "completed", "success", summary


def main():
    env = os.environ
    repo, token = env["GITHUB_REPOSITORY"], env["APP_TOKEN"]
    with open(env["GITHUB_EVENT_PATH"]) as f:
        wr = json.load(f)["workflow_run"]
    sha = wr["head_sha"]
    _, prs, _ = lib.gh_api("GET", "/repos/%s/commits/%s/pulls" % (repo, sha), token)
    prs = [p for p in (prs or []) if p.get("state") == "open" and p["head"]["sha"] == sha
           and (p["head"].get("repo") or {}).get("full_name") == repo]
    if not prs:
        print("ready: no open PR from this repo has head %s" % sha[:12])
        return
    url = "/repos/%s/commits/%s/check-runs?filter=all&per_page=100" % (repo, sha)
    _, page, _ = lib.gh_api("GET", url, token)
    runs = (page or {}).get("check_runs", [])
    labels = set()
    for p in prs:
        labels |= {l["name"] for l in p.get("labels", [])}
    required = required_checks(env.get("PROJECT_TYPE", "web"), labels)
    st, conclusion, summary = decide(required, [r for r in runs if r["name"] != "ready"])
    body = {"name": "ready", "head_sha": sha, "status": st,
            "output": {"title": {"success": "Ready for your review", "failure": "Not ready: a required check failed"}
                       .get(conclusion, "Waiting for required checks"), "summary": summary}}
    if conclusion:
        body["conclusion"] = conclusion
    mine = [r for r in runs if r["name"] == "ready"]
    if mine:
        lib.gh_api("PATCH", "/repos/%s/check-runs/%d" % (repo, mine[0]["id"]), token, body)
    else:
        lib.gh_api("POST", "/repos/%s/check-runs" % repo, token, body)
    print("ready: %s %s\n%s" % (st, conclusion or "", summary))


if __name__ == "__main__":
    main()
