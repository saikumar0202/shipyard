---
name: build-change
description: How the shipyard builder implements an approved plan, fixes a bug against the reproducer's test, or addresses review findings.
---
# Build a change

1. Read the run context. Work out why you were started:
   - **Feature** (`approved`): the plan is the planner's comment (marked as the plan). Build exactly that plan.
   - **Fix** (`repro-ok`): make the reproducer's failing test pass. The `repro-sha` comment names its commit. You may not modify or delete any file added in that commit — CI (`repro-guard`) fails if you do.
   - **Fix** (`manual-repro`): no test exists. Fix the bug following the manual steps, and add the closest unit test you can.
   - **Review findings** (`must-fix-pending`) or **owner changes** (`needs-changes`, `@claude` on the PR): address every must-fix item or requested change, nothing else.
2. Read `CLAUDE.md`. Follow existing patterns. Put unfinished or risky features behind the project's existing flag mechanism, off by default.
3. Make the change. Add or update tests for each acceptance criterion.
4. Run the project's install, lint, build and test commands that are allowed to you. Fix what fails. If a command isn't allowed, don't look for another way to run it; note it in the comment.
5. If the reproducer's test is wrong (it tests the wrong thing or can never pass for a correct fix): don't edit it. Add `needs-human` and explain exactly why; the owner will ask the reproducer to rewrite it.
6. Commit with `git add` and `git commit` (or leave changes uncommitted; the pipeline commits leftovers). Never touch `.github/`, `.claude/`, `pipeline.yml` or LFS assets.
7. Output:
   - `summary_title` — the commit title (max 72 chars).
   - `pr_title` — short and specific.
   - `pr_body` — what changed and why, how it was tested, anything the owner should check on the preview. `Closes #n` is added for you.
   - `comment` — what you did, test results, and what you need from the owner (normally: review the PR when its checks finish).
