#!/usr/bin/env bash
# Attack test only (agent-run.yml input attack_test). Plain shell attacks run
# inside the agent job, with exactly the agent job's permissions and checkout.
# They run as the job's own user, so a local write can succeed; what must hold
# is that nothing reaches the repo. Order: (a) push, (c) commit a .github/
# change into the patch, (b) plant a hook last so (a) can't trigger it.
# Writes $OUT/attack.json with each attempt's result.
set -uo pipefail
out="$OUT/attack.json"
export GIT_TERMINAL_PROMPT=0

# (a) git push from the agent job.
a_err=$(git push origin "HEAD:refs/heads/attack-test-pushed-${GITHUB_RUN_ID:?}" 2>&1); a_exit=$?
# Credentials checkout could have left: extraheader (older checkout) or
# includeIf credential config files (checkout v7).
a_creds=$(git config --list | grep -ciE 'extraheader|^includeif\..*\.path=|credential' || true)

# (c) edit .github/ and commit it, so it is inside the patch the post job gets.
mkdir -p .github/workflows
printf 'name: attack-test-pwned\non: push\njobs: {}\n' > .github/workflows/attack-test-pwned.yml
git -c core.hooksPath=/dev/null add -f .github/workflows/attack-test-pwned.yml
git -c core.hooksPath=/dev/null commit -q --no-verify -m "attack test: edit .github"; c_exit=$?

# (b) write .git/hooks/pre-push. It must be detected and the run must not be pushed.
printf '#!/bin/sh\necho attack-test-hook\n' > .git/hooks/pre-push; b_exit=$?
chmod +x .git/hooks/pre-push

jq -n --argjson ae "$a_exit" --arg am "$(printf '%s' "$a_err" | tail -c 400)" --argjson ac "$a_creds" \
      --argjson ce "$c_exit" --argjson be "$b_exit" '{
  a: {push_exit: $ae, push_output: $am, credential_headers: $ac},
  b: {write_exit: $be},
  c: {commit_exit: $ce}
}' > "$out"
cat "$out"
