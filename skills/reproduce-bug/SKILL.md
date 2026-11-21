---
name: reproduce-bug
description: How the shipyard reproducer turns a bug report into a failing test, or into manual-repro, needs-info or needs-spec.
---
# Reproduce a bug

1. Read the report in the run context: steps, expected, actual, device or browser. Read `CLAUDE.md` and the code on the failing path.
2. Decide which case this is:
   - **Reproducible with a test** → write the smallest test that fails for the reported reason (not for a typo or missing import). Put it where the project's tests live, named after the behaviour. Run the project's test command and confirm it fails, and that it fails on the assertion that captures the bug. Commit it with `git add` and `git commit`. Add `repro-ok`.
   - **Reproduced, but no automated test is possible** (visual glitch, game feel, phone-only crash, local-model answer) → write no test. Add `manual-repro`. In the comment give exact manual steps, what you saw in the code that confirms the bug, and why no automated test is possible.
   - **Can't reproduce** → add `needs-info`, say what you tried and what information would let you reproduce it. Stop.
   - **Needs a product decision** (the "bug" is really missing or disputed behaviour) → add `needs-spec`, say which decision is needed. Stop.
3. Never fix the bug. Don't change application code, only add test files (and test fixtures if needed).
4. For `repro-ok` and `manual-repro`, also pick reviewers: `review:code`, `review:qa`, plus at most 3 others from the active panel (version 1: `code`, `qa` only).
5. `summary_title`: e.g. "Add failing test for <bug>" (max 72 chars).
6. The comment: the case you chose, the test file and the failing output (short), the reviewers and why, then what you need from the owner (normally nothing: the builder starts unless `hold` is set).
