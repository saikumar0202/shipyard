#!/usr/bin/env bash
# Post job, builder/reproducer only: apply the agent's patch on a fresh
# checkout of the base commit and push to issue-<n>. Runs no repo code: no
# install, build, format or git hooks.
# Usage: apply_patch.sh <patch> <base_sha> <branch> <result_file> [push|check]
# Writes "pushed <sha>", "checked <detail>", "refused <reason>" or
# "skipped <reason>" to result_file. "check" validates without pushing.
set -euo pipefail
patch="$1"; base="$2"; branch="$3"; result="$4"; mode="${5:-push}"
here="$(cd "$(dirname "$0")" && pwd)"
G=(git -c core.hooksPath=/dev/null -c core.fsmonitor=false)

if [[ ! "$branch" =~ ^issue-[0-9]+$ ]]; then echo "refused bad branch name $branch" > "$result"; exit 0; fi
if [ ! -s "$patch" ]; then echo "skipped empty patch" > "$result"; exit 0; fi

"${G[@]}" checkout -q --detach "$base"
if ! "${G[@]}" am --quiet --keep-cr --committer-date-is-author-date "$patch"; then
  "${G[@]}" am --abort || true
  echo "refused patch does not apply on $base" > "$result"; exit 0
fi

tmp="$(mktemp -d)"
"${G[@]}" diff --name-only -z --no-renames "$base" HEAD > "$tmp/paths"
# LFS check uses the base commit's .gitattributes, so a patch can't untrack a path first.
"${G[@]}" check-attr -z --source "$base" --stdin filter < "$tmp/paths" > "$tmp/attrs"
if ! msg=$(python3 "$here/check_paths.py" "$tmp/attrs" < "$tmp/paths"); then
  echo "refused $msg" > "$result"; exit 0
fi

if [ "$mode" != push ]; then echo "checked $msg (not pushed)" > "$result"; exit 0; fi

# Plain fast-forward push of the branch only. Never --force.
if "${G[@]}" push --quiet origin "HEAD:refs/heads/${branch}"; then
  echo "pushed $("${G[@]}" rev-parse HEAD)" > "$result"
else
  echo "refused push to ${branch} was rejected (branch moved since the run started?)" > "$result"
fi
