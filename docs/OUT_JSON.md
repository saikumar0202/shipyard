# out.json

The only thing that passes from an agent job to its post job, apart from the patch. Machine schema: [`schemas/out.schema.json`](../schemas/out.schema.json).

## How it is made

1. **Claude** returns structured output that matches [`schemas/agent-output.schema.json`](../schemas/agent-output.schema.json) (`claude -p --json-schema`). That is all an agent produces besides file edits. Read-only agents (planner, reviewers) have no other way to write anything.
2. **A non-AI step** (`scripts/finalize_out.py`) wraps it with what Claude can't know: exit reason, duration, turns, permission denials and git tamper evidence. It writes `out.json`.
3. For the builder and reproducer, `scripts/make_patch.sh` first commits leftovers and writes `changes.patch` (`git format-patch --binary` from the base commit).
4. Both files are uploaded as the `agent-output-<role>[-<review_name>]` artifact.

The post job trusts nothing in `out.json` except as a *request*: it takes the issue number, branch, base sha and head sha from the run's own trusted inputs, never from `out.json`.

## Fields

| Field | Type | Set by | Meaning |
| --- | --- | --- | --- |
| `schema_version` | `1` | finalize | Format version |
| `role` | `planner` \| `reproducer` \| `builder` \| `reviewer` | finalize | Must match the run's role, or the post job blocks |
| `agent` | string | finalize | Agent file used (e.g. `reviewer-qa`) |
| `review_name` | string \| null | finalize | Reviewer name from the active panel |
| `issue`, `pr` | int, int \| null | finalize | For the log only; the post job uses its own inputs |
| `exit_reason` | see below | finalize | Why the run ended |
| `duration_seconds` | int | finalize | Time in the Claude step |
| `num_turns` | int \| null | finalize | From the CLI result |
| `comment` | markdown | Claude | Comment to post. `<!-- shipyard:... -->` markers are stripped |
| `labels_add`, `labels_remove` | string[] | Claude | Requests, checked against the allowlist below |
| `check` | `{conclusion, title, summary}` \| null | Claude | Reviewers only. `failure` = has must-fix items |
| `summary_title` | string ≤ 72 | Claude | Builder/reproducer commit title: `issue-<n>: <summary_title>` |
| `pr_title`, `pr_body` | string | Claude | Builder: the PR it opens. `Closes #<n>` is appended |
| `has_patch` | bool | finalize | Writer roles: a non-empty, untampered patch exists |
| `permission_denials` | `{tool, input}[]` | finalize | Every tool call the permission settings refused (input truncated to 300 chars) |
| `cli` | object \| null | finalize | Claude's own outcome, kept apart from `exit_reason`: `subtype`, `is_error`, `structured_output` (`result`, `tool_call` or `missing`), `result_excerpt` (first 300 chars of its final text) |
| `tools_available` | string[] \| null | finalize | Tools Claude was offered (stream-json init event) |
| `tool_calls` | `{tool: {ok, error}}` | finalize | Tool calls by result, from the stream-json events |
| `git_tamper` | object \| null | make_patch | `hooks` (non-sample files in `.git/hooks`), `config_changed`, `base_is_ancestor`, `protected_paths_touched` |

### `exit_reason`

| Value | When | Post job |
| --- | --- | --- |
| `success` | Claude finished with valid structured output (and, for writers, a patch) | Applies it |
| `max_turns` | CLI stopped at `--max-turns` | `blocked` |
| `usage_limit` | Max 5-hour or weekly limit hit | `blocked` |
| `cli_error` | CLI error or no JSON result | `blocked` |
| `bad_output` | No structured output | `blocked` |
| `empty_patch` | Builder/reproducer produced no changes ("no changes produced") | `blocked` |
| `tampered` | The agent run wrote a git hook, changed `.git/config`, or rewrote history below the base commit. With only a hook, the existing commits are still written to the patch so the post job can check and report them; it is never pushed | `blocked` |
| `timeout_or_crash` | Set by the post job when no `out.json` arrived (job timeout or crash) | `blocked` |

## What the post job accepts

**Labels**, from the labels table's *Added by* column (`config/labels.json`). Labels added by you, the workflow or a template are never accepted from `out.json`. One refused label refuses all of that run's label changes and blocks the run.

| Role | May add | May remove |
| --- | --- | --- |
| planner | `review:<panel name>` | — |
| reproducer | `repro-ok`, `manual-repro`, `needs-info`, `needs-spec`, `review:<panel name>` | — |
| builder | `needs-human` | — |
| reviewer `<name>` | `must-fix:<name>` (set from its check result) | `must-fix:<name>` (on success) |

Active panel (version 1): `code`, `qa` (`config/panel.json`).

**Check runs:** reviewers create `review/<name>` on the PR head sha. `ready` is owned by the merge-readiness workflow, not by agents. No other names.

**Pushes:** builder and reproducer only, and only when the event may write code (see the trigger check). Every non-empty patch is checked, even on a blocked run, so refusals are reported. Fresh checkout of the base commit, `git am`, then refused if any changed path is under `.github/` or `.claude/`, is `pipeline.yml`, or is LFS-tracked according to the base commit's `.gitattributes`. Pushed as `HEAD:refs/heads/issue-<n>`, never forced.

**Comments:** planner and reproducer keep one sticky comment each (`<!-- shipyard:plan -->`, `<!-- shipyard:repro -->`), reviewers one per name on the PR (`<!-- shipyard:review/<name> -->`). The builder's result replaces the run's "working" comment (`<!-- shipyard:working:<run_id> -->`) when it exists. The reproducer's pushed commit is recorded as a `repro-sha` comment. Every run adds one line to the pinned pipeline-log issue (`PIPELINE_LOG_ISSUE`).

## Example (builder)

```json
{
  "schema_version": 1,
  "role": "builder",
  "agent": "builder",
  "review_name": null,
  "issue": 12,
  "pr": null,
  "exit_reason": "success",
  "duration_seconds": 512,
  "num_turns": 41,
  "comment": "Implemented the plan ... What I need from you: review the PR when its checks finish.",
  "labels_add": [],
  "labels_remove": [],
  "check": null,
  "summary_title": "Add dark mode toggle to settings",
  "pr_title": "Dark mode toggle",
  "pr_body": "Adds ...",
  "has_patch": true,
  "permission_denials": [],
  "git_tamper": {"hooks": [], "config_changed": false, "base_is_ancestor": true, "protected_paths_touched": []}
}
```
