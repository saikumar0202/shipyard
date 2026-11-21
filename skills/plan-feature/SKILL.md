---
name: plan-feature
description: How the shipyard planner turns a feature issue into a build plan and picks reviewers.
---
# Plan a feature

1. Read the run context: issue title, body (acceptance criteria and out-of-scope fields are the spec), and the owner's comments. If the owner asked for a revision with `@claude`, revise the whole plan; don't append.
2. Read `CLAUDE.md` for project rules, project type and the flag mechanism. Read the code the change will touch. Find existing patterns and follow them.
3. Write the plan as the `comment`, with these headings:
   - **Goal** — one or two sentences, in the issue's terms.
   - **Files to touch** — paths, and one line each on what changes. New files marked *(new)*.
   - **Approach** — the steps in order. Reuse existing code; name it.
   - **Risks** — what could break, and how the change limits it.
   - **Tests to add** — unit tests (and e2e for web journeys) that prove each acceptance criterion.
   - **Feature flag** — if the change ships unfinished or is risky, put it behind a flag that is off by default using the mechanism named in `CLAUDE.md`. Never add a new flag mechanism.
   - **Size** — S (under an hour of agent work), M, or L. If L, propose how to split it into issues.
   - **Reviewers** — `code` and `qa` always, plus at most 3 others from the active panel, each with one line of why.
   - **Questions** — only real blockers. If something is ambiguous, say what you assumed.
4. `labels_add`: `review:code`, `review:qa`, plus the extra reviewers you chose. Use only active panel names (version 1: `code`, `qa`). Never drop code or QA.
5. The plan must not touch `.github/`, `.claude/` or `pipeline.yml`. If the feature needs that, say so: the owner makes those changes by hand.
6. Finish with: what you did, and "Add `approved` to build this."
