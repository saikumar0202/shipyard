"""Shared, dependency-free helpers for the shipyard non-AI steps.

Everything here is plain logic (no network) so it can be unit tested in
tests/. Network calls live in gh_api() and are only used by the scripts.
"""
import json
import os
import re
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = ("planner", "reproducer", "builder", "reviewer")
WRITER_ROLES = ("reproducer", "builder")  # roles that produce a patch


def load_config(name):
    with open(os.path.join(ROOT, "config", name)) as f:
        return json.load(f)


def panel():
    return load_config("panel.json")["panel"]


# ---------------------------------------------------------------- labels

def label_allowlist(role, review_name=None):
    """Labels a role may add/remove through out.json.

    Derived from the 'Added by' column of the labels table: only labels an
    agent adds are accepted. Your gates (approved, spec-ok, hold, ...) and
    workflow labels (blocked, queued, bot-run-*, ...) are never accepted.
    """
    cfg = load_config("labels.json")
    add = {l["name"] for l in cfg["labels"] if role in l["agents"]}
    remove = set()
    if role in cfg["generated"]["review"]["agents"]:
        add |= {"review:" + n for n in panel()}
    if role == "reviewer":
        if review_name not in panel():
            raise ValueError("unknown reviewer %r (not in active panel)" % review_name)
        add.add("must-fix:" + review_name)
        remove.add("must-fix:" + review_name)
    return add, remove


def filter_labels(role, review_name, labels_add, labels_remove):
    """Return (add, remove, rejected). Any rejected label rejects them all."""
    allowed_add, allowed_remove = label_allowlist(role, review_name)
    rejected = [l for l in labels_add if l not in allowed_add]
    rejected += [l for l in labels_remove if l not in allowed_remove]
    if rejected:
        return [], [], rejected
    return sorted(set(labels_add)), sorted(set(labels_remove)), []


def all_label_names():
    cfg = load_config("labels.json")
    names = [l["name"] for l in cfg["labels"]]
    names += ["review:" + n for n in panel()]
    names += ["must-fix:" + n for n in panel()]
    g = cfg["generated"]
    names += ["bot-run-%d" % i for i in range(1, g["bot_run"]["count"] + 1)]
    names += ["budget+%d" % i for i in range(1, g["budget"]["count"] + 1)]
    return names


def owned_check_names(role, review_name=None):
    """Check runs the post job may create. Only reviewers set checks here;
    'ready' is owned by the merge-readiness workflow (phase 2)."""
    if role == "reviewer":
        return {"review/" + review_name}
    return set()


# ---------------------------------------------------------------- paths

PROTECTED_PREFIXES = (".github/", ".claude/")
PROTECTED_FILES = ("pipeline.yml", ".github/pipeline.yml")


def protected_paths(paths):
    """Paths the post job must refuse (docs: .github/, .claude/, pipeline.yml)."""
    bad = []
    for p in paths:
        if p.startswith(PROTECTED_PREFIXES) or p in PROTECTED_FILES or p in (".github", ".claude"):
            bad.append(p)
    return bad


BRANCH_RE = re.compile(r"^issue-[0-9]+$")


# ---------------------------------------------------------------- trigger check

def trigger_check(event_name, event, owner, bot, repo, paused=False, ci_workflows=()):
    """Decide whether this event may start an agent (docs: Guardrails >
    Trigger check by event). Returns a dict:
      allowed: bool, reason: str, can_write_code: bool, mode: str
    'can_write_code' is false for events that may only open issues or only
    review; the post job then refuses to push.
    """
    def deny(reason):
        return {"allowed": False, "reason": reason, "can_write_code": False, "mode": "none"}

    def allow(reason, write, mode="normal"):
        return {"allowed": True, "reason": reason, "can_write_code": write, "mode": mode}

    if paused:
        return deny("PIPELINE_PAUSED is true")
    trusted = {owner, bot}
    sender = (event.get("sender") or {}).get("login", "")

    if event_name in ("issues", "issue_comment"):
        if sender not in trusted:
            return deny("actor %s is not the owner or the pipeline bot" % sender)
        return allow("trusted actor %s" % sender, True)

    if event_name == "pull_request":
        pr = event.get("pull_request") or {}
        head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
        if head_repo != repo:
            return deny("PR head repo %s is not %s (fork PRs never run agents)" % (head_repo, repo))
        author = (pr.get("user") or {}).get("login", "")
        action = event.get("action", "")
        if action in ("labeled", "unlabeled") and sender not in trusted:
            return deny("label changed by %s" % sender)
        if author == "dependabot[bot]":
            return allow("dependabot PR: CI and code reviewer only", False, "dependabot")
        if author not in trusted:
            return deny("PR author %s is not the owner or the pipeline bot" % author)
        if action not in ("opened", "synchronize", "reopened", "labeled", "unlabeled"):
            return deny("pull_request action %s not handled" % action)
        return allow("trusted PR by %s" % author, True)

    if event_name == "deployment_status":
        creator = ((event.get("deployment") or {}).get("creator") or {}).get("login", "")
        if creator != "vercel[bot]":
            return deny("deployment created by %s, not vercel[bot]" % creator)
        # The sha must belong to an open PR from this repo (or a release
        # candidate, added with the Release stage). Checked over the API by
        # trigger_check.py because it needs a lookup.
        return allow("vercel deployment; sha check required", False, "needs_sha_check")

    if event_name == "workflow_run":
        wr = event.get("workflow_run") or {}
        if (wr.get("repository") or {}).get("full_name") != repo:
            return deny("workflow_run from another repo")
        if (wr.get("head_repository") or {}).get("full_name") != repo:
            return deny("workflow_run for a fork")
        if wr.get("name") not in ci_workflows:
            return deny("workflow %s is not a CI or preview workflow" % wr.get("name"))
        return allow("workflow_run of %s" % wr.get("name"), False)

    if event_name in ("schedule", "workflow_dispatch", "repository_dispatch"):
        return allow("%s may only open issues, never write code" % event_name, False, "issues_only")

    return deny("event %s is not handled" % event_name)


# ---------------------------------------------------------------- prompt input filter

MAX_ITEM = 20000
MAX_TOTAL = 150000


def filter_items(items, trusted):
    """Keep only items written by a trusted login. Each item: {login, body, ...}."""
    return [i for i in items if i.get("login") in trusted]


def render_context(issue, comments, trusted, pr=None, reviews=()):
    """Build the markdown context an agent sees. Anything not written by the
    owner or the pipeline bot is dropped before the prompt is built."""
    out = []
    dropped = 0

    def clip(s):
        s = s or ""
        return s if len(s) <= MAX_ITEM else s[:MAX_ITEM] + "\n\n[truncated]"

    out.append("# Issue #%d: %s" % (issue["number"], issue.get("title", "")))
    out.append("Labels: " + ", ".join(issue.get("labels", [])))
    if issue.get("login") in trusted:
        out.append("\n## Issue body (by %s)\n\n%s" % (issue["login"], clip(issue.get("body"))))
    else:
        dropped += 1
        out.append("\n## Issue body\n\n[dropped: not written by the owner or the pipeline bot]")
    if pr:
        out.append("\n# Pull request #%d: %s" % (pr["number"], pr.get("title", "")))
        if pr.get("login") in trusted:
            out.append("\n## PR body\n\n" + clip(pr.get("body")))
        else:
            dropped += 1
    kept = filter_items(list(comments) + list(reviews), trusted)
    dropped += len(comments) + len(reviews) - len(kept)
    kept.sort(key=lambda c: c.get("created_at", ""))
    if kept:
        out.append("\n## Comments (owner and pipeline bot only, oldest first)")
    for c in kept:
        out.append("\n### %s at %s\n\n%s" % (c["login"], c.get("created_at", ""), clip(c.get("body"))))
    text = "\n".join(out)
    if len(text) > MAX_TOTAL:
        text = text[:MAX_TOTAL] + "\n\n[context truncated]"
    return text, dropped


REPRO_SHA_RE = re.compile(r"<!-- shipyard:repro-sha -->\s*repro-sha:\s*`?([0-9a-f]{40})`?")


def latest_repro_sha(comments, bot):
    sha = None
    for c in sorted(comments, key=lambda c: c.get("created_at", "")):
        if c.get("login") != bot:
            continue
        m = REPRO_SHA_RE.search(c.get("body") or "")
        if m:
            sha = m.group(1)
    return sha


# ---------------------------------------------------------------- out.json

EXIT_REASONS = ("success", "max_turns", "usage_limit", "cli_error", "bad_output",
                "empty_patch", "tampered", "timeout_or_crash")


def classify_result(result, cli_exit, role, patch_empty, tamper):
    """Map the Claude CLI JSON result to an exit_reason (docs: Failure path)."""
    if tamper:
        return "tampered"
    if not isinstance(result, dict):
        return "cli_error"
    subtype = result.get("subtype", "")
    text = str(result.get("result", "")) + " " + " ".join(map(str, result.get("errors", []) or []))
    if subtype == "error_max_turns":
        return "max_turns"
    if result.get("is_error") or cli_exit != 0 or subtype.startswith("error"):
        if re.search(r"usage limit|rate limit|limit reached|out of extra usage|429", text, re.I):
            return "usage_limit"
        return "cli_error"
    if not isinstance(result.get("structured_output"), dict):
        return "bad_output"
    if role in WRITER_ROLES and patch_empty:
        return "empty_patch"
    return "success"


# ---------------------------------------------------------------- GitHub API

def gh_api(method, path, token, body=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else "https://api.github.com" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "shipyard-pipeline")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), r.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"message": raw.decode(errors="replace")}
        return e.code, payload, e.headers


def gh_paginate(path, token):
    items, url = [], path + ("&" if "?" in path else "?") + "per_page=100"
    while url:
        status, page, headers = gh_api("GET", url, token)
        if status != 200:
            raise RuntimeError("GET %s -> %s %s" % (url, status, page))
        items += page
        url = None
        for part in (headers.get("Link") or "").split(","):
            if 'rel="next"' in part:
                url = part[part.index("<") + 1:part.index(">")]
    return items


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            if "\n" in str(value):
                f.write("%s<<__EOF__\n%s\n__EOF__\n" % (name, value))
            else:
                f.write("%s=%s\n" % (name, value))
    else:
        print("%s=%s" % (name, value))
