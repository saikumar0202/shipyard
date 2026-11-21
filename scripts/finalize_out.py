#!/usr/bin/env python3
"""Write out.json from the Claude CLI result (docs: out.json, see docs/OUT_JSON.md).

Claude itself only produces the structured_output part (comment, labels,
check, titles). This non-AI step adds what Claude can't know: exit reason,
duration, turns, permission denials and tamper evidence.
Usage: finalize_out.py <result.json> <cli_exit> <duration_s> <out_dir>
Env: ROLE, AGENT, REVIEW_NAME, ISSUE, PR
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def build(result, cli_exit, duration, out_dir, env):
    role = env["ROLE"]
    tamper = load(os.path.join(out_dir, "tamper.json")) or {}
    tampered = bool(tamper.get("hooks") or tamper.get("config_changed") or tamper.get("base_is_ancestor") is False)
    patch_path = os.path.join(out_dir, "changes.patch")
    patch_empty = not (os.path.exists(patch_path) and os.path.getsize(patch_path) > 0)
    reason = lib.classify_result(result, cli_exit, role, patch_empty, tampered)
    so = (result or {}).get("structured_output") if isinstance(result, dict) else None
    so = so if isinstance(so, dict) else {}
    denials = []
    for d in ((result or {}).get("permission_denials") or []) if isinstance(result, dict) else []:
        denials.append({"tool": d.get("tool_name"), "input": json.dumps(d.get("tool_input"))[:300]})
    return {
        "schema_version": 1,
        "role": role,
        "agent": env.get("AGENT", role),
        "review_name": env.get("REVIEW_NAME") or None,
        "issue": int(env["ISSUE"]),
        "pr": int(env["PR"]) if env.get("PR") else None,
        "exit_reason": reason,
        "duration_seconds": int(duration),
        "num_turns": (result or {}).get("num_turns") if isinstance(result, dict) else None,
        "comment": so.get("comment", ""),
        "labels_add": so.get("labels_add", []),
        "labels_remove": so.get("labels_remove", []),
        "check": so.get("check"),
        "summary_title": so.get("summary_title", ""),
        "pr_title": so.get("pr_title", ""),
        "pr_body": so.get("pr_body", ""),
        "has_patch": role in lib.WRITER_ROLES and not patch_empty and not tampered,
        "permission_denials": denials,
        "git_tamper": tamper or None,
    }


def main():
    result_path, cli_exit, duration, out_dir = sys.argv[1:5]
    out = build(load(result_path), int(cli_exit), float(duration), out_dir, os.environ)
    if not out["has_patch"] and os.path.exists(os.path.join(out_dir, "changes.patch")):
        open(os.path.join(out_dir, "changes.patch"), "w").close()
    with open(os.path.join(out_dir, "out.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("out.json: exit_reason=%s duration=%ss denials=%d" % (out["exit_reason"], out["duration_seconds"], len(out["permission_denials"])))


if __name__ == "__main__":
    main()
