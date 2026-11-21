#!/usr/bin/env bash
# Create or update every pipeline label (docs/PIPELINE.md > Labels and board)
# in one repo. Run it yourself, locally, with the GitHub CLI logged in as you:
#   scripts/setup-labels.sh saikumar0202/forher
# Labels come from config/labels.json; review:, must-fix: and missed: labels
# only for the active panel in config/panel.json. Existing labels are updated, none deleted.
set -euo pipefail
repo="${1:?usage: setup-labels.sh <owner/repo>}"
here="$(cd "$(dirname "$0")" && pwd)"
python3 - "$here" <<'PY' | while IFS=$'\t' read -r name color desc; do
import json, os, sys
root = os.path.dirname(sys.argv[1])
cfg = json.load(open(os.path.join(root, "config", "labels.json")))
panel = json.load(open(os.path.join(root, "config", "panel.json")))["panel"]
g = cfg["generated"]
rows = [(l["name"], l["color"], l["description"]) for l in cfg["labels"]]
rows += [("review:" + n, g["review"]["color"], g["review"]["description"]) for n in panel]
rows += [("must-fix:" + n, g["must_fix"]["color"], g["must_fix"]["description"]) for n in panel]
rows += [("missed:" + n, g["missed"]["color"], g["missed"]["description"]) for n in panel]
rows += [("bot-run-%d" % i, g["bot_run"]["color"], g["bot_run"]["description"]) for i in range(1, g["bot_run"]["count"] + 1)]
rows += [("budget+%d" % i, g["budget"]["color"], g["budget"]["description"]) for i in range(1, g["budget"]["count"] + 1)]
for r in rows:
    print("\t".join(r))
PY
  gh label create "$name" --repo "$repo" --color "$color" --description "$desc" --force >/dev/null
  echo "label: $name"
done
