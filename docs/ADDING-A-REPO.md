# Adding a repo to the pipeline

How to connect a project repo to shipyard, step by step. Steps 1–3 happen once; steps 4–11 happen for every repo. Nothing here is automated yet; the Promote setup script comes later (docs/PIPELINE.md > Build order step 10).

Status: phase 1 (shipyard core) is built. The caller workflows in step 10 arrive with phase 2 (the `forher` pilot).

## Once

### 1. Create the pipeline GitHub App

GitHub → Settings → Developer settings → GitHub Apps → New GitHub App.

- **Name:** e.g. `sai-shipyard` (its bot login becomes `sai-shipyard[bot]`).
- **Homepage URL:** the shipyard repo URL.
- **Webhook:** turn off (untick Active).
- **Repository permissions:**
  - Contents: Read and write (push `issue-<n>` branches)
  - Issues: Read and write (labels, comments)
  - Pull requests: Read and write (open the builder's PR, PR labels)
  - Checks: Read and write (`review/<name>` and `ready` checks)
  - Metadata: Read-only (required)
  - **Workflows: No access.** The App must never be able to change `.github/workflows`.
- **Where can this app be installed:** Only on this account.
- Create it, note the **Client ID** (on the App's General page), then **Generate a private key** (downloads a `.pem`).
- **Install** it on `shipyard` and on each project repo (Only select repositories).

### 2. Make the Claude token

On your computer: `claude setup-token`. Copy the token. It lasts a year: open a reminder issue in shipyard due in 11 months. Never add an `ANTHROPIC_API_KEY` secret anywhere next to it: an API key takes priority and would bill the API instead of your Max plan.

### 3. Shipyard repo settings

- Settings → Actions → General → Workflow permissions: **Read repository contents** (the default token stays read-only; every write uses the App token).
- Same page: leave **Allow GitHub Actions to create and approve pull requests** off.
- Same page, Fork pull request workflows: **Require approval for all outside collaborators**.
- Add the secrets from step 4 to shipyard too (the attack test runs here).
- Tags: shipyard changes reach a project only through a new tag (`v0.1.0`, ...). Projects pin a tag in `uses:` and pass the same tag as `shipyard_ref`.

## For every repo

### 4. Secrets (Settings → Secrets and variables → Actions → Secrets)

| Secret | Value |
| --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | Token from step 2 |
| `APP_PRIVATE_KEY` | Full contents of the `.pem` file |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | Web only: Vercel → Project → Settings → Deployment Protection → Protection Bypass for Automation |

Dependabot PRs get the code reviewer only if `CLAUDE_CODE_OAUTH_TOKEN` and `APP_PRIVATE_KEY` are also added under **Dependabot** secrets.

The design doc lists an `APP_ID` secret; the pipeline uses the App's Client ID instead, as the repo variable `APP_CLIENT_ID` (`actions/create-github-app-token` deprecated `app-id`).

### 5. Variables (same page → Variables)

| Variable | Value |
| --- | --- |
| `APP_CLIENT_ID` | The App's Client ID from step 1 (not a secret) |
| `PIPELINE_BOT` | The App's bot login, e.g. `shipyard-sai[bot]` |
| `PIPELINE_OWNER` | Optional; defaults to the repo owner (`saikumar0202`) |
| `PIPELINE_LOG_ISSUE` | Number of the pipeline-log issue from step 7 |
| `PIPELINE_PAUSED` | `true` to stop every pipeline workflow at once; delete or set `false` to resume |

### 6. Labels

With the GitHub CLI logged in as you, from a shipyard checkout:

```bash
scripts/setup-labels.sh saikumar0202/<repo>
```

It creates or updates every label in the labels table, `review:` and `must-fix:` labels for the active panel only (`code`, `qa`), `bot-run-1`…`bot-run-4` and `budget+1`…`budget+4`. It deletes nothing.

### 7. Pipeline-log issue

Open an issue titled **Pipeline log**, pin it, and put its number in `PIPELINE_LOG_ISSUE`. Each agent run adds one line (agent, issue, exit reason, duration, run link).

### 8. Actions settings

As in step 3: read-only default token, Actions may not approve PRs, approval required for fork PR workflows.

### 9. Branch and tag rules (public repos only on GitHub Free)

Settings → Rules → Rulesets:

- **main:** restrict deletions, block force pushes, require a pull request with 1 approval, require status check `test`. Add yourself to the bypass list.
- **Tags `v*`:** restrict creation, update and deletion to you (bypass list: you only).

Private repos have no rulesets on GitHub Free; they rely on the agent-job/post-job split and the `ready` check.

### 10. Project files (phase 2)

Added by a PR you review and merge yourself (the App can't touch `.github/`):

- `.github/workflows/pipeline-events.yml` and the other callers, which call `saikumar0202/shipyard/.github/workflows/agent-run.yml@<tag>`
- `.github/pipeline.yml` (`stages: [build]`, `spec: off`, `type`, ...)
- `.github/ISSUE_TEMPLATE/feature.yml`, `bug.yml`
- `CLAUDE.md` (project rules, project type, flag mechanism)
- Test scaffold; `lighthouserc.json` for web

A caller passes the builder's Bash commands, one per line, for example:

```yaml
jobs:
  build:
    uses: saikumar0202/shipyard/.github/workflows/agent-run.yml@v0.1.0
    permissions: { contents: read, issues: read, pull-requests: read }
    with:
      shipyard_ref: v0.1.0
      role: builder
      issue: ${{ github.event.issue.number }}
      bash_commands: |
        pnpm install --frozen-lockfile
        pnpm lint
        pnpm build
        pnpm test
        pnpm e2e
    secrets:
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      APP_PRIVATE_KEY: ${{ secrets.APP_PRIVATE_KEY }}
```

### 11. Vercel (web)

- Project → Settings → Git → **Production Branch: `production`**, so pushes to `main` only make previews.
- Deployment Protection → **Protection Bypass for Automation**: create the secret (step 4). If it isn't available on the free plan, turn off Vercel Authentication for this project's previews and keep preview links unshared.
