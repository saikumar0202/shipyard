#!/usr/bin/env python3
"""Trigger check (docs: Guardrails > Trigger check by event).

Reads the event from GITHUB_EVENT_PATH and writes step outputs:
  allowed, reason, can_write_code, mode
Never fails the step: a denied event just sets allowed=false so every later
job is skipped.

Env: GITHUB_EVENT_NAME, GITHUB_EVENT_PATH, GITHUB_REPOSITORY,
     PIPELINE_OWNER, PIPELINE_BOT, PIPELINE_PAUSED, CI_WORKFLOWS (comma list),
     GITHUB_TOKEN (read-only; only for the deployment_status sha lookup).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def main():
    env = os.environ
    with open(env["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)
    repo = env["GITHUB_REPOSITORY"]
    res = lib.trigger_check(
        env["GITHUB_EVENT_NAME"], event,
        owner=env["PIPELINE_OWNER"], bot=env.get("PIPELINE_BOT", ""),
        repo=repo, paused=env.get("PIPELINE_PAUSED", "") == "true",
        ci_workflows=[w.strip() for w in env.get("CI_WORKFLOWS", "").split(",") if w.strip()],
    )
    if res["allowed"] and res["mode"] == "needs_sha_check":
        sha = event["deployment"]["sha"]
        status, prs, _ = lib.gh_api("GET", "/repos/%s/commits/%s/pulls" % (repo, sha), env.get("GITHUB_TOKEN"))
        ok = status == 200 and any(
            p.get("state") == "open" and p["head"]["repo"] and p["head"]["repo"]["full_name"] == repo
            and p["head"]["sha"] == sha for p in prs)
        # Release candidates (open release issue's candidate sha) are added
        # with the Release stage; until then only open PRs qualify.
        res = {"allowed": ok, "can_write_code": False, "mode": "review_only" if ok else "none",
               "reason": "sha %s is the head of an open PR from this repo" % sha if ok
               else "sha %s is not the head of an open PR from this repo" % sha}
    for k in ("allowed", "reason", "can_write_code", "mode"):
        lib.set_output(k, str(res[k]).lower() if isinstance(res[k], bool) else res[k])
    print("trigger check: %s (%s)" % ("allowed" if res["allowed"] else "denied", res["reason"]))


if __name__ == "__main__":
    main()
