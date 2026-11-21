#!/usr/bin/env python3
"""Prompt input filter + run context (docs: Guardrails > Prompt input filter).

Fetches the issue (and PR) with the read-only GITHUB_TOKEN, keeps only the
body and comments written by the owner or the pipeline bot, and writes:
  $OUT_DIR/context.md   what the agent reads
  $OUT_DIR/run.json     trusted run facts (base sha, branch, repro sha, ...)
and step outputs base_sha, head_sha, branch, repro_sha, bot_email.

Env: GITHUB_REPOSITORY, GITHUB_TOKEN, PIPELINE_OWNER, PIPELINE_BOT, ROLE,
     ISSUE, PR (optional), HEAD_SHA (reviewer), OUT_DIR
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def comment_items(raw):
    return [{"login": (c.get("user") or {}).get("login"), "body": c.get("body"),
             "created_at": c.get("created_at")} for c in raw]


def main():
    env = os.environ
    repo, token = env["GITHUB_REPOSITORY"], env.get("GITHUB_TOKEN")
    owner, bot, role = env["PIPELINE_OWNER"], env.get("PIPELINE_BOT", ""), env["ROLE"]
    trusted = {owner, bot}
    issue_no = int(env["ISSUE"])
    pr_no = int(env["PR"]) if env.get("PR") else None
    out_dir = env["OUT_DIR"]
    os.makedirs(out_dir, exist_ok=True)

    status, issue, _ = lib.gh_api("GET", "/repos/%s/issues/%d" % (repo, issue_no), token)
    if status != 200:
        sys.exit("cannot read issue #%d: %s" % (issue_no, issue))
    issue_v = {"number": issue_no, "title": issue["title"], "body": issue.get("body"),
               "login": issue["user"]["login"], "labels": [l["name"] for l in issue["labels"]]}
    comments = comment_items(lib.gh_paginate("/repos/%s/issues/%d/comments" % (repo, issue_no), token))

    pr_v, reviews = None, []
    if pr_no:
        status, pr, _ = lib.gh_api("GET", "/repos/%s/pulls/%d" % (repo, pr_no), token)
        if status != 200:
            sys.exit("cannot read PR #%d: %s" % (pr_no, pr))
        pr_v = {"number": pr_no, "title": pr["title"], "body": pr.get("body"),
                "login": pr["user"]["login"], "base_sha": pr["base"]["sha"], "head_sha": pr["head"]["sha"]}
        if pr_no != issue_no:
            comments += comment_items(lib.gh_paginate("/repos/%s/issues/%d/comments" % (repo, pr_no), token))
        reviews = [{"login": (r.get("user") or {}).get("login"), "body": r.get("body"),
                    "created_at": r.get("submitted_at")}
                   for r in lib.gh_paginate("/repos/%s/pulls/%d/reviews" % (repo, pr_no), token) if r.get("body")]

    text, dropped = lib.render_context(issue_v, comments, trusted, pr_v, reviews)
    with open(os.path.join(out_dir, "context.md"), "w") as f:
        f.write(text)

    # Base commit: writers start from issue-<n> if it exists, else the
    # default branch. Reviewers check out the PR head and diff against base.
    branch = "issue-%d" % issue_no
    if role == "reviewer":
        if not pr_v:
            sys.exit("reviewer runs need PR")
        head_sha = env.get("HEAD_SHA") or pr_v["head_sha"]
        base_sha = pr_v["base_sha"]
    else:
        status, ref, _ = lib.gh_api("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch), token)
        if status == 200:
            base_sha = ref["object"]["sha"]
        else:
            _, meta, _ = lib.gh_api("GET", "/repos/%s" % repo, token)
            _, ref, _ = lib.gh_api("GET", "/repos/%s/git/ref/heads/%s" % (repo, meta["default_branch"]), token)
            base_sha = ref["object"]["sha"]
        head_sha = base_sha

    bot_email = ""
    if bot:
        status, user, _ = lib.gh_api("GET", "/users/%s" % bot, token)
        if status == 200:
            bot_email = "%d+%s@users.noreply.github.com" % (user["id"], bot)

    run = {"issue": issue_no, "pr": pr_no, "branch": branch, "base_sha": base_sha, "head_sha": head_sha,
           "repro_sha": lib.latest_repro_sha(comments, bot) or "", "issue_labels": issue_v["labels"],
           "dropped_items": dropped, "bot_email": bot_email}
    with open(os.path.join(out_dir, "run.json"), "w") as f:
        json.dump(run, f, indent=2)
    for k in ("base_sha", "head_sha", "branch", "repro_sha", "bot_email"):
        lib.set_output(k, run[k])
    print("context built: %d trusted items kept, %d dropped" % (len(comments) + len(reviews) - dropped + 1, dropped))


if __name__ == "__main__":
    main()
