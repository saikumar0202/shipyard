---
name: review-qa
description: How the shipyard QA reviewer reviews a PR's tests and edge cases.
---
# QA review

Covers: edge cases, missing tests, the bug repro now passes. Inside this group also check observability (useful errors, logs), resilience (error handling, timeouts, offline), compatibility, real-time and notifications when relevant.

1. Read the run context (acceptance criteria, plan or bug report, `repro-sha` or manual-repro steps) and the diff file.
2. Check:
   - Each acceptance criterion has a test that would fail without the change.
   - On a fix: the reproducer's test is unchanged and now passes (CI shows it), or, for `manual-repro`, the change addresses the manual steps and the builder added the closest unit test it could.
   - Edge cases: empty, very large, invalid input, errors from the network or disk, double submits, time zones.
   - Tests are not weakened (no skipped tests, loosened assertions or deleted cases).
3. Must-fix: a missing test for an acceptance criterion, an unhandled edge case that will happen in real use, a weakened test. Everything else is a suggestion.
4. Output:
   - `check.conclusion`: `failure` if there is at least one must-fix item, else `success`. `check.title`: one line. `check.summary`: the must-fix list.
   - `comment`: headings **Must-fix**, **Suggestions**, **Checked**, then what you need from the owner (for manual-repro: "confirm the fix on the preview or APK before merging").
   - `labels_add`: empty.
