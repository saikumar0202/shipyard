#!/usr/bin/env bash
# Non-AI step after the Claude step (builder and reproducer only).
# 1. Records tamper evidence (.git hooks or config changed by the agent run).
# 2. If clean, commits everything left (git add -A, except .claude/ and
#    .github/) as "issue-<n>: <summary title>" with the pipeline bot as author.
# 3. Writes `git format-patch --binary` from the base commit.
# Git runs with hooks and fsmonitor off so nothing the agent wrote can execute.
# Usage: make_patch.sh <base_sha> <issue> <summary_title> <out_dir>
# Env:   GIT_CONFIG_SHA_BEFORE (sha256 of .git/config before Claude ran)
set -euo pipefail
base="$1"; issue="$2"; title="$3"; out="$4"
G=(git -c core.hooksPath=/dev/null -c core.fsmonitor=false)
mkdir -p "$out"
: > "$out/changes.patch"

hooks=$(find .git/hooks -type f ! -name '*.sample' -printf '%P\n' | sort | paste -sd, -)
cfg_now=$(sha256sum .git/config | cut -d' ' -f1)
cfg_changed=false; [ "$cfg_now" = "${GIT_CONFIG_SHA_BEFORE:-}" ] || cfg_changed=true
ancestor=true; "${G[@]}" merge-base --is-ancestor "$base" HEAD || ancestor=false
protected=$("${G[@]}" status --porcelain=v1 --untracked-files=all -- .github .claude | cut -c4- | paste -sd, -)

jq -n --arg hooks "$hooks" --argjson cfg "$cfg_changed" --argjson anc "$ancestor" --arg prot "$protected" '{
  hooks: ($hooks | split(",") | map(select(. != ""))),
  config_changed: $cfg,
  base_is_ancestor: $anc,
  protected_paths_touched: ($prot | split(",") | map(select(. != "")))
}' > "$out/tamper.json"

if [ -n "$hooks" ] || [ "$cfg_changed" = true ] || [ "$ancestor" = false ]; then
  echo "::warning::git tamper evidence found; no patch produced"
  exit 0
fi

"${G[@]}" add -A -- . ':(exclude).claude' ':(exclude).github'
if ! "${G[@]}" diff --cached --quiet; then
  "${G[@]}" commit --no-verify -q -m "issue-${issue}: ${title:-agent changes}"
fi
"${G[@]}" format-patch --binary --stdout "${base}..HEAD" > "$out/changes.patch"
echo "patch: $(grep -c '^From [0-9a-f]\{40\} ' "$out/changes.patch" || true) commit(s), $(wc -c < "$out/changes.patch") bytes"
