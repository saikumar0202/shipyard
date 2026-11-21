# shipyard

Shared GitHub Actions pipeline that runs Claude Code agents to plan, build, review and ship changes in Sai's other repos. The spec is [docs/PIPELINE.md](docs/PIPELINE.md) (v4.3).

## Layout

| Path | What |
| --- | --- |
| `.github/workflows/agent-run.yml` | Reusable agent run: context job (trigger check, prompt filter) → agent job (`claude -p`, read-only) → post job (App token, all writes) |
| `.github/workflows/attack-test.yml` | Guardrail test: an agent with builder permissions tries five forbidden actions; a non-AI job verifies all were refused |
| `.github/workflows/self-test.yml` | Unit tests for the scripts |
| `agents/` | Subagent files: planner, reproducer, builder, reviewer-code, reviewer-qa |
| `skills/` | The skill each agent follows |
| `settings/` | Per-agent Claude Code permission settings (`--settings`) |
| `schemas/` | Agent structured output and `out.json` schemas |
| `scripts/` | Non-AI steps: trigger check, prompt filter, patch, post job, label setup |
| `config/` | Labels table and active reviewer panel |
| `docs/OUT_JSON.md` | The `out.json` format and what the post job accepts |
| `docs/ADDING-A-REPO.md` | How to connect a repo, step by step |

Run the tests locally with `python3 -m unittest discover -s tests`.
