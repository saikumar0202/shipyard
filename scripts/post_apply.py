#!/usr/bin/env python3
"""Post job (no AI). Applies out.json and, for builder/reproducer, the patch.

Every write uses the pipeline App token. It accepts only labels from the
labels table that the role may add (config/labels.json), only check names
the role owns, and pushes only to issue-<n>. Anything else -> blocked.

Env:
  GITHUB_REPOSITORY, APP_TOKEN, ROLE, REVIEW_NAME, ISSUE, PR, HEAD_SHA,
  BASE_SHA, BRANCH, OUT_DIR (holds out.json, changes.patch), AGENT_JOB_RESULT,
  CAN_WRITE_CODE, RUN_URL, RUN_ID, PIPELINE_LOG_ISSUE, BOT_LOGIN, DRY_RUN
"""
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STICKY = {"planner": "plan", "reproducer": "repro"}  # reviewer: review/<name>


def marker(key):
    return "<!-- shipyard:%s -->" % key


def clean(text):
    # Agents may not forge shipyard markers (they select which comment we edit).
    return re.sub(r"<!--\s*shipyard:[^>]*-->", "", text or "")


class GitHub:
    def __init__(self, repo, token, dry_run=False):
        self.repo, self.token, self.dry = repo, token, dry_run
        self.calls = []

    def __call__(self, method, path, body=None):
        path = path.replace("{repo}", self.repo)
        self.calls.append((method, path, body))
        if self.dry:
            return 200, [] if method == "GET" else {}, {}
        status, data, _ = lib.gh_api(method, path, self.token, body)
        if status >= 400 and not (method == "DELETE" and status == 404):
            print("::warning::%s %s -> %s %s" % (method, path, status, (data or {}).get("message")))
        return status, data, _

    def comments(self, number):
        if self.dry:
            return []
        return lib.gh_paginate("/repos/%s/issues/%d/comments" % (self.repo, number), self.token)


def decide(out, env):
    """Pure decision: what to write. Returns dict with problems + actions."""
    role, review = env["ROLE"], env.get("REVIEW_NAME") or None
    problems = []
    if out is None:
        out = {"exit_reason": "timeout_or_crash", "labels_add": [], "labels_remove": [], "comment": ""}
        problems.append("agent job ended without out.json (job result: %s; timeout or crash)" % env.get("AGENT_JOB_RESULT"))
    elif out.get("exit_reason") != "success":
        problems.append("agent exit reason: %s" % out.get("exit_reason"))
    if out.get("role", role) != role:
        problems.append("out.json role %r does not match run role %r" % (out.get("role"), role))
    add, remove, rejected = lib.filter_labels(role, review, out.get("labels_add") or [], out.get("labels_remove") or [])
    if rejected:
        problems.append("refused labels not allowed for %s: %s" % (role, ", ".join(rejected)))
    check = None
    if role == "reviewer":
        c = out.get("check") or {}
        if c.get("conclusion") in ("success", "failure") and not problems:
            check = {"name": "review/" + review, "conclusion": c["conclusion"],
                     "title": str(c.get("title", ""))[:200], "summary": clean(c.get("summary", ""))[:60000]}
            # must-fix label follows the check result, whatever the agent listed.
            mf = "must-fix:" + review
            add = [l for l in add if l != mf] + ([mf] if c["conclusion"] == "failure" else [])
            remove = [l for l in remove if l != mf] + ([mf] if c["conclusion"] == "success" else [])
        else:
            if not problems:
                problems.append("reviewer gave no check result")
            check = {"name": "review/" + review, "conclusion": "failure",
                     "title": "Reviewer did not finish", "summary": "; ".join(problems) or "no check result"}
    push = None
    if role in lib.WRITER_ROLES and not problems:
        if not out.get("has_patch"):
            problems.append("no changes produced (empty patch)")
        elif env.get("CAN_WRITE_CODE") != "true":
            problems.append("this event may not write code; patch not pushed")
        else:
            push = True
    return {"out": out, "problems": problems, "add": add, "remove": remove, "check": check, "push": push}


def run_push(env, push=True):
    res = os.path.join(env["OUT_DIR"], "push-result.txt")
    subprocess.run([os.path.join(HERE, "apply_patch.sh"), os.path.join(env["OUT_DIR"], "changes.patch"),
                    env["BASE_SHA"], env["BRANCH"], res, "push" if push else "check"], check=True)
    with open(res) as f:
        kind, _, detail = f.read().strip().partition(" ")
    return kind, detail


def upsert_comment(gh, number, key, body, bot):
    for c in gh.comments(number):
        if (c.get("user") or {}).get("login") == bot and marker(key) in (c.get("body") or ""):
            gh("PATCH", "/repos/{repo}/issues/comments/%d" % c["id"], {"body": body})
            return c["id"]
    gh("POST", "/repos/{repo}/issues/%d/comments" % number, {"body": body})


def main():
    env = dict(os.environ)
    role, issue = env["ROLE"], int(env["ISSUE"])
    pr = int(env["PR"]) if env.get("PR") else None
    bot = env.get("BOT_LOGIN", "")
    gh = GitHub(env["GITHUB_REPOSITORY"], env.get("APP_TOKEN"), env.get("DRY_RUN") == "1")
    out_path = os.path.join(env["OUT_DIR"], "out.json")
    out = json.load(open(out_path)) if os.path.exists(out_path) else None
    d = decide(out, env)
    out, problems = d["out"], d["problems"]

    # Every writer patch is checked (git am + path rules), even when the run is
    # already blocked, so refusals are reported. It is pushed only if d["push"].
    pushed_sha = None
    patch = os.path.join(env["OUT_DIR"], "changes.patch")
    if role in lib.WRITER_ROLES and os.path.exists(patch) and os.path.getsize(patch) > 0:
        kind, detail = run_push(env, push=bool(d["push"]))
        if kind == "pushed":
            pushed_sha = detail
        elif kind != "checked":
            problems.append("patch %s: %s" % (kind, detail))

    footer = "\n\n---\n<sub>shipyard %s%s · %s · %ss · [run log](%s)</sub>" % (
        role, (":" + env["REVIEW_NAME"]) if env.get("REVIEW_NAME") else "",
        out.get("exit_reason"), out.get("duration_seconds", "?"), env.get("RUN_URL", ""))
    working_key = "working:%s" % env.get("RUN_ID", "")

    if problems:
        reason = "; ".join(problems)
        gh("POST", "/repos/{repo}/issues/%d/labels" % issue, {"labels": ["blocked"]})
        body = (marker(working_key) + "\n**Blocked.** %s\n\nWhat I need from you: read the run log, fix the cause, "
                "then remove `blocked` to retry.%s" % (reason, footer))
        upsert_comment(gh, issue, working_key, body, bot)
        if d["check"]:
            target_sha = env["HEAD_SHA"]
            gh("POST", "/repos/{repo}/check-runs", {"name": d["check"]["name"], "head_sha": target_sha,
               "status": "completed", "conclusion": "failure",
               "output": {"title": "Reviewer did not finish", "summary": reason}})
    else:
        target = pr if (role == "reviewer" and pr) else issue
        if role == "builder":
            target = open_or_find_pr(gh, env, out, issue) or issue
        if d["add"]:
            gh("POST", "/repos/{repo}/issues/%d/labels" % target, {"labels": d["add"]})
        for name in d["remove"]:
            gh("DELETE", "/repos/{repo}/issues/%d/labels/%s" % (target, urllib.parse.quote(name, safe="")))
        if d["check"]:
            c = d["check"]
            gh("POST", "/repos/{repo}/check-runs", {"name": c["name"], "head_sha": env["HEAD_SHA"],
               "status": "completed", "conclusion": c["conclusion"],
               "output": {"title": c["title"] or c["name"], "summary": c["summary"] or c["conclusion"]}})
        body = clean(out.get("comment")) + footer
        sticky = STICKY.get(role) or ("review/" + env["REVIEW_NAME"] if role == "reviewer" else None)
        if sticky:
            upsert_comment(gh, target, sticky, marker(sticky) + "\n" + body, bot)
        else:
            upsert_comment(gh, issue, working_key, marker(working_key) + "\n" + body, bot)
        if role == "reproducer" and pushed_sha:
            gh("POST", "/repos/{repo}/issues/%d/comments" % issue,
               {"body": "%s\nrepro-sha: `%s`\n\nThe builder may not modify or delete files added in this commit "
                        "(checked by `repro-guard`).%s" % (marker("repro-sha"), pushed_sha, footer)})

    log_line(gh, env, out, issue, problems)
    if env.get("DRY_RUN") == "1":
        json.dump({"problems": problems, "calls": gh.calls}, sys.stdout, indent=2)
    print("\npost job: %s" % ("BLOCKED: " + "; ".join(problems) if problems else "applied"))


def open_or_find_pr(gh, env, out, issue):
    """Builder: open the PR for issue-<n> if none is open; copy review:* labels."""
    owner = env["GITHUB_REPOSITORY"].split("/")[0]
    status, prs, _ = gh("GET", "/repos/{repo}/pulls?state=open&head=%s:%s" % (owner, env["BRANCH"]))
    if status == 200 and prs:
        return prs[0]["number"]
    status, iss, _ = gh("GET", "/repos/{repo}/issues/%d" % issue)
    title = (out.get("pr_title") or (iss or {}).get("title") or env["BRANCH"])[:120]
    body = clean(out.get("pr_body")) + "\n\nCloses #%d" % issue
    _, meta, _ = gh("GET", "/repos/{repo}")
    status, created, _ = gh("POST", "/repos/{repo}/pulls", {"title": title, "head": env["BRANCH"],
                            "base": (meta or {}).get("default_branch", "main"), "body": body})
    if status != 201:
        return None
    reviewers = [l["name"] for l in (iss or {}).get("labels", []) if l["name"].startswith("review:")
                 and l["name"][7:] in lib.panel()]
    if reviewers:
        gh("POST", "/repos/{repo}/issues/%d/labels" % created["number"], {"labels": reviewers})
    return created["number"]


def log_line(gh, env, out, issue, problems):
    n = env.get("PIPELINE_LOG_ISSUE")
    if not n:
        print("::notice::PIPELINE_LOG_ISSUE not set; skipping pipeline log line")
        return
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = "`%s` · %s%s · #%d · %s · %ss · [run](%s)%s" % (
        now, env["ROLE"], (":" + env["REVIEW_NAME"]) if env.get("REVIEW_NAME") else "", issue,
        out.get("exit_reason"), out.get("duration_seconds", "?"), env.get("RUN_URL", ""),
        " · **blocked**" if problems else "")
    gh("POST", "/repos/{repo}/issues/%d/comments" % int(n), {"body": line})


if __name__ == "__main__":
    main()
