#!/usr/bin/env python3
"""Write out.json from the Claude CLI result (docs: out.json, see docs/OUT_JSON.md).

Claude itself only produces the structured_output part (comment, labels,
check, titles). This non-AI step adds what Claude can't know: exit reason,
duration, turns, permission denials and tamper evidence.
Usage: finalize_out.py <events.jsonl> <cli_exit> <duration_s> <out_dir>
(events.jsonl is claude -p --output-format stream-json --verbose output)
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


def parse_events(path):
    """Return (result, tools_available, tool_calls) from the stream-json events."""
    result, tools, calls, names = None, None, {}, {}
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return None, None, {}
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            tools = ev.get("tools")
        elif ev.get("type") == "result":
            result = ev
        for item in ((ev.get("message") or {}).get("content") or []) if isinstance(ev.get("message"), dict) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use":
                names[item.get("id")] = item.get("name")
            elif item.get("type") == "tool_result":
                name = names.get(item.get("tool_use_id"), "?")
                c = calls.setdefault(name, {"ok": 0, "error": 0})
                c["error" if item.get("is_error") else "ok"] += 1
    return result, tools, calls


def build(result, cli_exit, duration, out_dir, env, tools=None, calls=None):
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
        "tools_available": tools,
        "tool_calls": calls or {},
        "permission_denials": denials,
        "git_tamper": tamper or None,
    }


def main():
    events_path, cli_exit, duration, out_dir = sys.argv[1:5]
    result, tools, calls = parse_events(events_path)
    out = build(result, int(cli_exit), float(duration), out_dir, os.environ, tools, calls)
    # A tampered run keeps its patch file so the post job can check and report
    # it; has_patch=false means it is never pushed.
    with open(os.path.join(out_dir, "out.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("out.json: exit_reason=%s duration=%ss denials=%d" % (out["exit_reason"], out["duration_seconds"], len(out["permission_denials"])))


if __name__ == "__main__":
    main()
