# Sai's Build Pipeline — Full Picture

One process for every product, from the first idea through build, release and life after launch. It runs on GitHub, uses Claude Code through your Max subscription, and shows its state on a GitHub Projects board. Version 4.3, revised after six outside reviews. This is the final paper version. Frozen for building: the next review is of the real workflow files after five real changes, not of this doc.

## The flow at a glance

&#91;embedded content: build stage · features: approved + your review; fixes: your review (hold optional)\]

Features pass one gate before code (`approved`; `spec-ok` too once the spec writer is on). Both tracks share CI, review and your merge. Nothing merges, tags, deploys or publishes without you.

**Feature track:** feature issue → planner posts the plan and picks reviewers → ✋ `approved` → builder opens a PR → CI → reviewers (after CI passes) → ✋ your review → merge to main (preview only).

**Fix track:** bug issue → reproducer pushes a failing test and adds `repro-ok` → builder fixes it (unless `hold`) → CI → reviewers → ✋ your review → merge to main (preview only).

**Production** changes only through a release tag, never on merge.

## Two modes

- **Quick mode:** a throwaway site or tool you need today. Ask Claude locally, no pipeline.
- **Product mode:** anything meant to go live for real users. A repo is in product mode when it has the pipeline caller workflow. Stages and options are switched on in `.github/pipeline.yml` (start with `stages: [build]` and `spec: off`; later add `discover-define`, `release`, `operate`, `learn`); the shared workflows skip what is off.
- **Promote:** turning a quick project into a product is done by the `shipyard` setup script, not by agents. Run it locally, or through `workflow_dispatch` in `shipyard` using a separate setup App that has the workflows permission. It opens one PR with the caller workflow, templates, labels, `CLAUDE.md`, `pipeline.yml` (`stages: [build]`) and a test scaffold. That PR is expected to be `needs-human`: you review and merge it yourself. Feature work starts after it merges.

## Labels and board

| Label | Meaning | Added by |
| --- | --- | --- |
| `feature`, `bug`, `idea`, `release`, `incident`, `review` | Which track or stage an issue belongs to | The issue template |
| `spec-ok` | Your spec gate, only when `spec: on` | You |
| `approved` | Your build gate for features; also releases a held bug that has `repro-ok` or `manual-repro` | You |
| `repro-ok` | Reproducer pushed a failing test; starts the builder | Reproducer |
| `manual-repro` | Reproduced, but no automated test is possible; exact manual steps are in a comment. Starts the builder | Reproducer |
| `hold` | Don't build the fix until you remove it | You |
| `review:<name>` | A reviewer from the active panel to run on the PR | Planner or reproducer; you can add or remove |
| `must-fix:<name>` | That reviewer found must-fix items; it reruns on the next push | Review job |
| `must-fix-pending` | Starts the builder to fix review findings | Review job |
| `needs-changes` | Your request for changes; starts the builder | You |
| `needs-info`, `needs-spec` | Couldn't reproduce, or the bug needs a product decision | Reproducer |
| `queued` | Waiting because the WIP limit is full | Workflow |
| `blocked` | An agent stopped; the reason is in a comment. Remove it to retry | Workflow |
| `needs-human` | PR touched protected files (AI review only; you fix by hand), or the reproducer's test looks wrong (you comment "@claude fix the test" and the reproducer rewrites it) | Workflow or builder |
| `bot-run-1` to `bot-run-4` | Run budget counter, on the issue | Workflow |
| `budget+1`, `budget+2`, … | One extra builder run each, added when you remove `blocked` | Workflow |
| `parked`, `wontfix` | Stop an issue | You |
| `sev:1`, `sev:2` | Incident severity | You |

**Board:** only issues go on the board; their PRs show as linked items. Columns are Inbox → Ready to build → Building → Your Review → Done, plus Parked. Mapping: plan posted → Ready to build; `queued` → Ready to build; `approved` or `needs-changes` → Building; PR review checks finished → Your Review; `blocked` → Your Review with the label visible; closed as completed → Done; closed as not planned or `parked` → Parked. A small sync workflow sets status through GraphQL with `PROJECT_TOKEN` (a classic PAT with project scope; an App token works only for an organization board). In version 1, use the built-in automations and move cards by hand.

## Build stage, step by step

### Handoffs

Every step starts from one event. The builder checks for `hold` when it starts, not when the reproducer finishes.

| Event | Starts |
| --- | --- |
| Feature issue opened (`spec: off`), or `spec-ok` added (`spec: on`) | Planner |
| `feature` label added to an existing issue (for example after `needs-spec`) | Planner, or spec writer when `spec: on` |
| Feature issue opened (`spec: on`) | Spec writer |
| Bug issue opened | Reproducer |
| `repro-ok` or `manual-repro` added, and no `hold` | Builder |
| `hold` removed, or `approved` added to a bug, while `repro-ok` or `manual-repro` is present | Builder (otherwise nothing starts, and the workflow comments why) |
| `approved` added to a feature | Builder |
| `must-fix-pending` or `needs-changes` on a PR | Builder |
| CI `test` job passes on the PR | Review job: code, QA and non-visual reviewers |
| `deployment_status` success for a PR's commit or a release candidate | e2e, Lighthouse, then the UI and accessibility reviewer |
| CI or preview workflow completes (`workflow_run`) | Merge-readiness recompute (the `ready` check) |
| `blocked` removed by you | The step that failed, with `budget+1` added |
| Comment starting `@claude` | Routed agent (see Talking to agents) |
| `v*` tag pushed by you, matching the candidate sha | Release workflow |

### 1. Spec (only when `spec: on`)

- **Until the spec writer exists** there is no `spec-ok` gate: the planner starts when you open the feature issue, and your one gate is `approved`. The template's acceptance criteria and out-of-scope fields are the spec.
- **With `spec: on`:** the spec writer turns rough notes into acceptance criteria and asks questions in a comment; you add `spec-ok`.

### 1b. Reproduce (fixes)

- **Trigger:** a bug issue that you opened from the bug template (steps, expected, actual, device or browser).
- **Agent:** the reproducer pushes a failing test to the issue branch, records its commit in a `repro-sha` comment, posts the reviewers it picked, and adds `repro-ok`. It stays separate from the builder so the agent that fixes a bug never writes its own test.
- **Reproduced but can't be automated** (a visual glitch, game feel, a phone-only crash, a local-model answer): it adds `manual-repro` with the exact manual steps and why no test is possible. The builder then runs without `repro-guard` and must add the closest unit test it can; QA reviews against the manual steps, and you confirm the fix on the preview or APK before merging.
- **Can't reproduce:** it adds `needs-info` with what it tried, and stops.
- **Needs a product decision:** it adds `needs-spec`, and the issue moves to the feature track.

### 2. Plan (features)

- **Agent:** the planner reads the codebase and posts a plan: files to touch, approach, risks, tests to add, rough size, and the reviewers it chose as `review:<name>` labels (active panel names only).
- **Gate:** you add `approved`, after changing reviewer labels if you want. Nothing is built before this.

### 3. Build

- The builder works on branch `issue-<number>` and opens a PR whose body says `Closes #<issue>`. It copies the issue's `review:*` labels onto the PR.
- **Fixes:** it starts from the reproducer's failing test and makes it pass. The reproducer's commit is recorded in a `repro-sha` comment, and the builder may not modify or delete files added in that commit. A CI step, `repro-guard`, diffs those files against `repro-sha` and fails if they changed. If the test itself is wrong, the builder adds `needs-human` and explains why instead of editing it. After you comment "@claude fix the test: \<reason>", the reproducer (never the builder) rewrites the test and records a new `repro-sha`, then the builder continues; you check the result at your review.
- **Before review,** the workflow merges main into the branch. On a conflict the builder resolves it once (counts against the run budget), otherwise `blocked`.
- **Protected files:** the builder never stages `.claude/`, `.github/` or `pipeline.yml`; its prompt says so, and a PR that changes them gets `needs-human`: AI review still runs, but no AI rework.
- When the agent job starts, the events caller posts "working: \<Actions run link>" on the issue. The post job replaces it with the result when the run ends.

### 4. Testing (CI, not an agent)

- **Every project:** install, lint, type check, unit tests, build, and `repro-guard` on fix PRs. This `test` check is the one merge readiness depends on.
- **Web:** Playwright e2e runs on the `deployment_status` event (state success, environment Preview) against the event's `target_url`, sending the `x-vercel-protection-bypass` header from `VERCEL_AUTOMATION_BYPASS_SECRET`. Screenshots are attached to the PR.
- **Lighthouse:** budgets in `lighthouserc.json` (accessibility ≥ 90, performance ≥ 70 on the main page). Report-only in version 1; required after 10 stable runs. A Lighthouse-only failure never triggers a builder retry.
- **Games:** the engine is set per project in `pipeline.yml` (`engine: unity | godot | other`), and the shared game CI picks its build image from it (Unity needs a licence, for example through GameCI). Logic and physics tests run headless. To save Actions minutes and Git LFS bandwidth on private repos: cache the engine's import folder (for example Unity's Library folder) keyed on the asset hash; check out LFS files only in the build job, never in agent or review jobs; build the APK only when the test job passes and the PR has no must-fix-pending; and record minutes per run in the ready check summary. No gameplay capture in CI; you test the APK from the PR's artifacts on your phone.
- **AI assistants (Jarvis, SONY):** in CI, unit tests with the model mocked plus prompt and tool-routing tests on recorded responses. The real-model prompt set runs on a self-hosted runner (`runs-on: [self-hosted, local-model]`) only for PRs with `review:ai-quality`, and is skipped with a warning when the runner is offline.
- **Self-hosted runner safety:** never attached to a public repo, runs as a separate OS user with no access to your home folder, never triggered from fork PRs.
- **Desktop apps:** added when a desktop product exists. Mac builds need macOS runners, which use free minutes ten times faster in private repos.

### 5. AI review

- **When:** code, QA and the non-visual reviewers run in the CI workflow as `needs: [test]`, so only after CI passes. On web projects the UI and accessibility reviewer runs in the `deployment_status` workflow, after e2e and Lighthouse, using `target_url` and the bypass header, so it can open the real preview and read those results. Each reviewer is a fresh session that did not write the code.
- **Who:** code and QA always, plus at most 3 panel reviewers by default; more only when you add the labels yourself.
- **Output:** each reviewer sets its own check run (`review/<name>`: success, or failure when it has must-fix items) and keeps one sticky comment that it updates instead of adding new ones.
- **Must-fix:** a failing reviewer adds `must-fix:<name>`; the review job then adds `must-fix-pending`, which starts the builder. On the next push the matrix runs code, QA and only the reviewers with a `must-fix:<name>` label, and removes the label when that reviewer passes. At most 1 automatic must-fix round per issue in version 1 (2 later); after that the review job adds `blocked` instead.
- **Merge readiness:** a third small workflow runs on `workflow_run` (completed) for the CI and preview workflows. Every time either finishes, it recomputes from the check runs on the PR's head commit and creates or updates one `ready` check. Required checks depend on the project type in `pipeline.yml`: web needs `test`, e2e, and every `review/<name>` check whose `review:<name>` label is on the PR (the UI reviewer only when `review:ui` is on it); other types need `test` and `review/*` only. It fails when CI is red. The `ready` check is what moves the card to Your Review.
- **`needs-human` PRs** get the full review (comments and checks). Protected-file PRs get no AI rework, because the push job refuses those paths, so you fix them by hand. Wrong-test PRs are reworked by the reproducer after your "@claude fix the test" comment.

### 6. Your review and deploy

- You look at the PR, the preview, the screenshots, CI and the reviews, then merge it or add `needs-changes` with a comment.
- **Never auto-merge.**
- **Web deploy:** in Vercel, the Production Branch is set to `production`, so pushes to main only make previews. Pushing a `v*` tag runs the release workflow, which force-updates the `production` branch to the tag's commit (`git push --force origin <tag>^{commit}:refs/heads/production`). This is the only force-push allowed, done only by the release workflow, and only for tags you pushed (see Guardrails, Release trigger). It works for patch tags made on `release/<version>` branches too. Rollback is Vercel Instant Rollback, or pointing `production` back at the previous tag the same way.
- **Android deploy:** a `v*` tag builds and signs the AAB and uploads it to internal testing (after the first manual upload, see Release).
- **Desktop deploy:** a `v*` tag makes a draft GitHub release.
- **Feature flags:** unfinished features merge behind a flag that is off by default, using the project's flag mechanism named in `CLAUDE.md` (web: a `flags.ts` file read from environment variables; Android: Firebase Remote Config, or none). The planner never adds a new flag mechanism.

### Talking to agents

A comment starting with `@claude` is routed by the issue's state. Before `approved`: the planner (features) or reproducer (bugs) revises its comment in place. On a PR: the builder makes the requested change, which counts against the run budget. Anywhere else, including closed issues: a general read-only answer. The routing rules live in `shipyard/workflows/mention.yml`. Add `parked` or `wontfix` to stop an issue. On a needs-human fix, a comment starting "@claude fix the test" goes to the reproducer.

## The agents

| Agent | Job | Stage |
| --- | --- | --- |
| Product writer | Turns an idea into a one-page brief and MVP issues in a milestone | Discover & Define |
| Spec writer | Turns rough feature notes into acceptance criteria | Build, when `spec: on` |
| Planner | Reads code, writes the plan, picks reviewers | Build (features) |
| Reproducer | Pushes the failing test, picks reviewers, or flags needs-info / needs-spec | Build (fixes), Operate |
| Builder | Writes the code and opens or updates the PR | Build, Operate |
| Reviewers | One agent per reviewer in the active panel | Build, Operate |
| Release manager | Builds the release candidate and checklist, runs the Agent rows, drafts notes | Release |
| Incident lead | Triage help, the hotfix plan and the postmortem | Operate |
| Metrics analyst | Monthly report against the brief's success metric | Learn |

Each agent is a Claude Code subagent file following a skill, kept in `shipyard` and copied in at run time (see What lives where).

## Reviewers

The planner (features) or reproducer (fixes) picks reviewers and lists them in the plan; you change them by adding or removing `review:<name>` labels. Agents can add reviewers but never drop code and QA.

### Active panel (version 1)

| Reviewer | Covers | Picked when |
| --- | --- | --- |
| Code | Bugs, readability, matches spec and plan, no scope creep | Always |
| QA | Edge cases, missing tests, the bug repro now passes | Always |
| Security and privacy | Auth, secrets, input validation, injection, what user data is stored or sent | Auth, user input, personal data, network or file access |
| UI and accessibility (web only) | Layout, flows, design system, accessibility, motion, copy, screenshot regressions | Any screen or component change |
| Performance | Load time, frame rate, memory, bundle size, latency | Hot paths, rendering, large data, game loops |
| Data and API | Calculations, chart values, API contracts, migrations, save files | Numbers, charts, APIs, schema or save format changes |
| Game feel | Physics, controls, balance, progression, audio | Game mechanics, levels, rewards, sound |
| AI safety and quality | Prompt injection, unsafe tool use, response quality | Prompts, models or tools change |

### Reviewer library

Only names in the active panel are valid `review:<name>` labels. The setup script creates labels for the panel only, and a review job for an unknown name posts a warning and skips it. Each check below starts inside its panel group and is split into its own reviewer only after the group has missed a real bug of that kind twice.

| Reviewer | Checks | Panel group |
| --- | --- | --- |
| Architecture | Structure, boundaries, state management, fit with existing patterns | Code |
| Concurrency | Race conditions, async ordering, shared state | Code |
| Config and feature flags | Defaults, environment variables, flags can be switched off | Code |
| Dependencies | New packages, known vulnerabilities, size | Code |
| Docs | README, CLAUDE.md, changelog kept current | Code |
| Observability | Logs, crash reporting, useful error messages | QA |
| Resilience | Error handling, retries, offline behaviour, timeouts | QA |
| Compatibility | Browsers, devices, Android versions, OS differences | QA |
| Real-time | Websockets, reconnects, ordering, stale data | QA |
| Notifications | Push, email, timing, opt-out | QA |
| Security | Auth, secrets, input validation, permissions | Security and privacy |
| Privacy | What user data is stored, logged or sent | Security and privacy |
| Licensing and assets | Package licences, fonts, music, art and sound rights | Security and privacy |
| UI/UX | Layout, flows, empty and error states, responsive layout | UI and accessibility |
| Design system | Components, spacing, tokens, typography | UI and accessibility |
| Accessibility | Keyboard, contrast, screen reader labels | UI and accessibility |
| Visual | Screenshots against the previous version | UI and accessibility |
| Motion and animation | Smoothness, timing, reduced motion | UI and accessibility |
| Content and copy | Wording, tone, typos, error messages | UI and accessibility |
| Localization | Hard-coded text, longer strings, date and number formats | UI and accessibility |
| SEO | Meta tags, titles, sitemap | UI and accessibility |
| Performance | Load time, frame rate, memory, bundle size, latency | Performance |
| Battery and thermal | Background work, wake locks, heat on long sessions | Performance |
| Cost | Paid API calls, cloud usage, usage spikes | Performance |
| Data accuracy | Calculations, chart values, rounding, time zones | Data and API |
| API contract | Request and response shapes, breaking changes | Data and API |
| Database and migrations | Schema, save-file compatibility, rollback, data loss | Data and API |
| Analytics | Events fire correctly, consistent names | Data and API |
| Monetization | In-app purchases, ads, receipts, refunds | Data and API |
| Physics and game feel | Collisions, timing, controls | Game feel |
| Game balance and economy | Difficulty, progression, rewards, currency | Game feel |
| Game audio | Sound timing, volume balance, missing sounds | Game feel |
| AI safety | Prompt injection, unsafe tool use, leaked system prompts | AI safety and quality |
| AI response quality | Fixed prompt set, accuracy, tone, hallucinations | AI safety and quality |
| Build and release | CI config, versioning, signing | Release stage |
| Infrastructure and deployment | Hosting config, Vercel settings, DNS, rollback | Release stage |
| Desktop packaging | Installers, auto-update, code signing | Release stage |
| Store compliance | Store policies, permissions, privacy labels | Release stage |

## Product lifecycle

A product moves through five stages: Discover & Define → Build → Release → Operate → Learn. Each stage is switched on in `pipeline.yml` when the product needs it.

### 1. Discover & Define — is it worth building, and what is version 1?

- **Trigger:** an `idea` issue.
- **Agent:** the product writer writes a one-page brief: problem, target user, 3 competitors with links, MVP list of at most 5 features, out of scope, one success metric, platforms, rough monthly cost.
- **Limits:** agent web research gives rough signals, not real market data. Check any number your decision depends on yourself.
- **Gate:** you approve, park or kill. On approve, the MVP features become feature issues in the GitHub milestone `v1.0`.

### 2. Build

- The feature and fix tracks above.
- **Milestone check:** when a milestone's last issue closes, the workflow opens a release issue for it. After launch you create the next milestone and the same rule applies; for a patch, you open a release issue yourself.
- **Android:** if the Play developer account is personal, start recruiting closed-test testers during Build (see Release).

### 3. Release — is it ready to go live?

- **Trigger:** a release issue for a milestone or patch.
- **Candidate:** the release manager builds a candidate from main (web: the current preview; Android: a signed AAB attached to the issue), writes the candidate's commit sha into the release issue, and runs the Agent rows of the release catalog against it. The Ads setup and Play Billing rows are included only when the monetisation list in pipeline.yml names ads or iap; the kill-switch row whenever that list is not empty. For web, e2e, Lighthouse and the UI review also run on the candidate's preview; their results are linked in the release issue, and the Full regression (web) row is ticked from them.
- **Gate:** you tick the You rows, then push the `v*` tag yourself. The release workflow refuses any tag whose commit isn't the candidate sha; to include later merges, ask for a new candidate with `@claude` on the release issue.
- **Rollout by platform:** Android = internal testing → staged percentage → everyone (plus closed testing when a new personal account requires it); web = preview → production with Instant Rollback; desktop = draft release → published.
- **Android first launch:** the first build of a new app is uploaded by hand in Play Console. A new personal developer account must pass Play's closed test before production (currently at least 12 testers for 14 days; check Play Console). Walkies already has production access, its first build is uploaded and it uses Play App Signing, so it skips this.
- **Signing secrets:** `PLAY_SERVICE_ACCOUNT_JSON` and the upload keystore secrets are declared only by the release job, so builder, reviewer and reproducer jobs never receive them. On public repos they sit in a `release` environment with required approval; on private repos (no environment approval on GitHub Free) the release trigger check is the gate.
- **Output:** production live, store listing live, launch posts out, changelog.

### 4. Operate — keep it healthy

- **Always on (tools picked per product in the brief):** crash and error reporting (for example Sentry), uptime checks (for example UptimeRobot), Dependabot. Alerts open `incident` issues through `repository_dispatch`, not by an agent polling.
- **Dependabot PRs** get CI and the code reviewer only, if `CLAUDE_CODE_OAUTH_TOKEN`, `APP_ID` and `APP_PRIVATE_KEY` are also added as Dependabot secrets.
- **sev:1 (down or data loss):** web and desktop, roll back to the previous release (`RUNBOOK.md`). Android, halt the staged rollout in Play Console, turn off the feature flag through Firebase Remote Config if the project uses it, and ship a hotfix with a higher version code. Without remote flags, sev:1 on Android always means a hotfix build. Agents only write the postmortem.
- **sev:2 (major feature broken):** fix track with code and QA only. The fix PR targets a `release/<version>` branch made from the tag, and the workflow opens a second PR cherry-picking it onto main. The incident closes only when both are merged, then a patch release ships.
- **If agents are unavailable** (limits or outage), you follow `RUNBOOK.md` yourself.
- **Store and user reviews:** you answer within 3 days; the agent drafts replies. Bugs found there become bug issues.

### 5. Learn — what next?

- **Trigger:** a scheduled `review` issue every month after launch.
- **Agent:** the metrics analyst compares results with the brief's success metric, sums up feedback themes and suggests roadmap changes. It needs read-only analytics and store-console keys as secrets; until then you paste the numbers into the issue.
- **Gate:** you decide what goes into the next milestone, or whether to pivot, continue or sunset.
- **Public repos:** GitHub turns off scheduled workflows after 60 days with no repo activity. The monthly run also commits a small update to `.github/last-review` to keep schedules alive, and the token-reminder issue lists any schedule that was turned off.

## Release catalog

Runs once per release, not on every PR.

| Area | Check | What it covers | Done by |
| --- | --- | --- | --- |
| Product | Product readiness | MVP complete, onboarding works first time | You |
| Product | Competitor check | Features, price, reviews, store ranking | Agent drafts, you check |
| Quality | Full regression | Every main journey end to end | Agent (web, from the candidate's e2e), you (devices) |
| Quality | Beta feedback | Tester bugs and confusion resolved or accepted | You |
| Quality | Release performance | Startup time, app size, memory, frame rate | Agent (from CI) |
| Marketing | Positioning | One-line pitch, audience, why it beats alternatives | Agent drafts, you check |
| Marketing | Launch plan | Channels, dates, posts written | Agent drafts, you check |
| Marketing | Landing page | Pitch, screenshots, sign-up or download button, SEO basics | Agent drafts, you check |
| Marketing | Store listing | Title, keywords, description, screenshots, video | Agent drafts, you check |
| Brand | Brand check | Name, icon, colours, tone consistent everywhere | You |
| Legal | Policies | Privacy policy, terms, cookie notice, data deletion | Agent drafts, you check |
| Legal | Store forms | Data safety, content and age rating, permissions | You |
| Legal | Rights | Trademark search, asset and code licences | You |
| Business | Pricing | Price, free tier, trials, regional pricing, tax | You |
| Business | Ads setup | Consent (Google UMP) for EEA and UK users, ad placement policy, "contains ads" declared | Agent checks code, you check Play Console |
| Business | Play Billing | Purchases verified and acknowledged (unacknowledged purchases are refunded after 3 days), test purchases with licence testers, refund handling | Agent checks code, you test |
| Business | Hosting plan | A commercial-use plan (Vercel Pro) before any launch with ads, payments or a paid tier, including the landing page for a paid game; Vercel Hobby is non-commercial only | You |
| Business | Payments | Receipts, refunds, renewals, cancellations | Agent checks code, you test |
| Business | Cost at scale | Running cost at ten times the usage, alerts set | Agent drafts, you check |
| Operations | Monitoring | Crash reporting, error alerts, uptime | Agent checks config, you trigger a test error |
| Operations | Analytics | Key events and funnel tracked | Agent checks code, you confirm events in the dashboard |
| Operations | Kill switch | Firebase Remote Config flag can turn off each risky feature | Agent checks code, you flip it once |
| Operations | Rollback | Previous version restorable, flags can switch off risky parts | You test |
| Operations | Backups | Data backed up, restore tested | You test |
| Support | Support readiness | Contact email, FAQ, feedback channel, reply templates | Agent drafts, you check |
| Compliance | Store compliance | Policy check before submission | Agent pre-check, you check |
| Compliance | Accessibility | Final pass on main journeys | Agent (web), you (Android and desktop) |
| Compliance | Localization | Translated listing and app text, if needed | Agent |
| Docs | Release notes | Changelog, what's-new text, README | Agent |

## Issue templates

| Template | Starts | Stage | Labels added |
| --- | --- | --- | --- |
| idea | Brief | Discover & Define | `idea` |
| feature | Planner (or spec writer) | Build | `feature` |
| bug | Reproducer | Build, Operate | `bug` |
| release | Release candidate and checklist | Release | `release` |
| incident | Severity triage and postmortem | Operate | `incident` |
| review | Monthly report | Learn | `review` |

Templates live in each repo's `.github/ISSUE_TEMPLATE`, added by the setup script. Promote is not a template; it is the setup script.

## What lives where

- **Shared repo (`shipyard`):** reusable workflows, agents, skills, the setup script and this guide. Every reusable workflow checks out `shipyard` at a pinned tag into `$RUNNER_TEMP/pipeline` using the pipeline App token (the App is installed on `shipyard` too), and copies its agents and skills into `~/.claude/agents` and `~/.claude/skills`, Claude Code's user-level folders, which sit outside the repo and are never committed. Project-level `.claude/` files with the same name win. Projects pin a `shipyard` tag, so a pipeline change never alters a project without a version bump.
- **Each project repo:** `CLAUDE.md` with project rules, project type (web, game, AI assistant, desktop) and flag mechanism (Firebase Remote Config for monetised games); `.github/pipeline.yml` (stages, `spec`, `engine`, `type`, `monetisation: [] | [ads] | [iap] | [ads, iap]`); issue templates; `lighthouserc.json` for web; `RUNBOOK.md` once it reaches Release.
- **Callers:** one caller workflow for all issue and label events (`pipeline-events.yml`). A first tiny job picks the route and the agent jobs use job-level `if:` conditions, so a skipped route costs nothing. `pull_request`, `deployment_status`, `workflow_run` (the `ready` check), tag pushes (release) and `schedule` each have their own caller.
- **Secrets:**
  - `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`. It lasts a year; the setup script opens a reminder issue due 11 months later. Never add an API key next to it, because an API key takes priority.
  - `APP_ID` and `APP_PRIVATE_KEY` for the pipeline GitHub App.
  - `PROJECT_TOKEN` for the board sync: a classic PAT with only the project scope.
  - `VERCEL_AUTOMATION_BYPASS_SECRET` for e2e tests on protected previews.
  - Android: `PLAY_SERVICE_ACCOUNT_JSON`, `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, declared only by the release job (in a `release` environment on public repos).
  - Dependabot secrets: `CLAUDE_CODE_OAUTH_TOKEN`, `APP_ID`, `APP_PRIVATE_KEY`, if Dependabot PRs should get the code reviewer.

## Guardrails

- **Pipeline GitHub App token:** every pipeline write (push, label, issue, comment, check run) uses a token from `actions/create-github-app-token`, never `GITHUB_TOKEN`, because events made with `GITHUB_TOKEN` never start other workflows. Only non-AI post jobs mint it. Workflows started by pipeline-bot labels are routed by the events caller's trigger check.
- **Agent job / post job, for every agent** (planner, reproducer, builder, reviewers, release manager, product writer):
  - **Agent job:** `permissions: contents: read`; `actions/checkout` with `persist-credentials: false`, no LFS files; runs the Claude Code CLI (`claude -p`), not `claude-code-action`. It ends by writing `out.json` (comment text, labels to add or remove, check-run result, CLI exit reason, run duration) and, for the reproducer and builder only, a patch. No App token exists in this job.
  - **Committing the patch:** after the Claude step, a non-AI step commits everything left (`git add -A`, ignoring `.claude/` and `.github/`) as "issue-\<n>: \<summary title>" with the pipeline bot as author, then runs `git format-patch --binary` from the base commit. Only an empty patch counts as "no changes produced".
  - **Post job (no AI):** applies `out.json` and the patch with the App token. It accepts only labels from the labels table and check names it owns (`review/<name>`, `ready`), and pushes only for the reproducer and builder. For pushes it makes a fresh checkout, runs `git am`, refuses any change to `.github/`, `.claude/`, `pipeline.yml` or LFS-tracked paths (from `.gitattributes`; asset changes are yours), and pushes `HEAD:refs/heads/issue-<number>` only. It runs no repo code: no install, build, format or git hooks. Anything that needs repo code runs in CI after the push.
  - **Live progress:** agent output appears when a run ends, not live. The "working" comment links to the Actions run for anyone who wants to watch.
  - `claude-code-action` is used only for the read-only `@claude` answer route, which runs only for your comments.
- **Tool permissions:** each agent gets a settings file in `shipyard` (passed with `--settings` or `--allowedTools`); permission checks are never skipped. Builder and reproducer: Read, Edit, Write, and Bash limited to the project's install, test, lint and build commands plus `git add` and `git commit`. Reviewers and planner: Read, Grep, Glob only. No WebFetch or WebSearch for any agent except the product writer. `CLAUDE_CODE_OAUTH_TOKEN` is passed only in the Claude step's env, never job-wide. If it may have leaked, run `claude setup-token` again and replace the secret (`RUNBOOK.md`).
- **Trigger check by event:**
  - `issues`, `issue_comment`, labeled: the actor must be you or the pipeline bot.
  - `pull_request` (opened, synchronize, reopened): the PR author must be you or the pipeline bot, and the head repo must be this repo (no forks). `dependabot[bot]` PRs get CI and the code reviewer only.
  - `deployment_status`: the creator must be `vercel[bot]`, and the commit must belong to an open PR from this repo or be the candidate sha of an open release issue.
  - `workflow_run`: only for this repo's CI and preview workflows.
  - `schedule`, `workflow_dispatch`, `repository_dispatch`: may only open issues, never write code.
  - Anything else exits.
- **Prompt input filter:** agents read only the issue body and comments written by you or the pipeline bot; the workflow drops everything else before building the prompt, so a stranger's comment on a public repo never reaches an agent.
- **Public logs:** on public repos, Actions logs are public. Claude's full output is not printed, and agents never run commands that print environment variables.
- **Release trigger:** the release workflow runs only when the tag was pushed by you (checked in its first step) and its commit equals the candidate sha. A tag from anyone else is deleted by the workflow and the release issue gets `blocked`. A tag ruleset on public repos also limits `v*` tags to you.
- **When agents may write code:** only after you acted (`approved` for features, a bug issue you opened for fixes). Nothing merges, tags, deploys or publishes without you.
- **WIP limit:** counts every agent session that writes code (reproducer and builder): 1 at a time to start, because you use Claude every day; raise it to 2 after a week with no limit hits. When full, new work gets `queued`, and a scheduled job every 30 minutes starts the oldest queued item.
- **Reviewers:** at most 2 at a time inside a review run (matrix `max-parallel: 2`). No cross-run reviewer group, because concurrency groups cancel pending runs; WIP 1 already keeps review to one PR at a time.
- **Concurrency:** the key is the branch name `issue-<number>`, which both issue and PR events can work out. Builder runs never cancel each other; review runs use cancel-in-progress, so a new push replaces a stale review.
- **Run budget:** worked out from labels only: allowed = 4 + count(`budget+*`); used = count(`bot-run-*`). The builder starts only if used < allowed, then adds `bot-run-(used+1)`. Runs started by your `needs-changes` add no `bot-run` label. Every job sets `timeout-minutes` (builder 45, reviewer 15) and a max-turns limit.
- **Failure path:** on any failure (budget used, timeout, usage limit, max turns, empty patch) the post job adds `blocked`, posts the reason and the log link, and moves the card to Your Review. Removing `blocked` adds the next `budget+N` and retries the failed step.
- **Pipeline log:** the post job adds one line per run (agent, issue, exit reason, duration) to a pinned "pipeline log" issue, so limit hits and slow runs show up in one place.
- **Kill switch:** the repo variable `PIPELINE_PAUSED=true` makes every workflow exit at once.
- **Permissions:** set per job, never write-all. The App has no workflows permission.
- **Branch protection:** on GitHub Free, rulesets work only on public repos. Public repos get a ruleset on main (no direct pushes, CI `test` must pass, one approval, you on the bypass list) and a tag ruleset for `v*`. Private repos have no ruleset, so they rely on the agent-job/post-job split and the `ready` check failing when CI is red.
- **Every agent comment ends** with what it did and what it needs from you.

## Skills, Superpowers and MCP

- **Superpowers** is a Claude Code plugin of skills (brainstorming, writing plans, test-driven development, systematic debugging, code review). It is a good source; copy the parts you like into `shipyard` and edit them, so a plugin update never changes your process unseen.
- **MCP is for tools, not process.** Use the Playwright MCP so the UI and accessibility reviewer can open the web preview. Nothing else to start.

## Honest risks

- Pipeline runs share your Max 5-hour and weekly limits with your own Claude use. Budget about 1 builder run plus 2–4 reviewer runs per feature. Watch the pinned pipeline log; if it shows limit hits twice in a week, lower the WIP limit or the reviewer cap, or set `PIPELINE_PAUSED` during your working hours.
- Private game repos: GitHub Free Actions minutes and Git LFS bandwidth can run out mid-month, because engine builds take 10–25 minutes. Check usage weekly during the pilot; if needed, set `PIPELINE_PAUSED` or build APKs locally.
- The `approved` gate only works if you actually read the plan.
- Agents will sound sure about things they can't check (market data, real devices, store forms, production alerts). The Done by column exists for this.
- Every handoff is a place a card can stop silently. The Handoffs table is the contract; if a step has no event, it doesn't exist.
- The remaining risks can only be found by running real workflows, not by reviewing this doc again.

## Minimum first version

- Pilot: one small web repo of your choice that you're happy to make public. Walkies comes second.
- One agent-job/post-job pattern shared by every agent: a read-only agent job writes `out.json` (plus a patch for the reproducer and builder); a non-AI post job does every write.
- Per-agent permission settings files in `shipyard`; permission checks never skipped; no web tools except the product writer; the token only in the Claude step.
- Post-job rules: label allowlist, owned check names, path, LFS and branch checks, no repo code run.
- Vercel: Production Branch set to `production`; Protection Bypass for Automation confirmed on the free plan. Secrets: `CLAUDE_CODE_OAUTH_TOKEN`, `APP_ID`, `APP_PRIVATE_KEY`, `VERCEL_AUTOMATION_BYPASS_SECRET`.
- Callers: events (job-level routing), `pull_request`, `deployment_status`, and the `workflow_run` `ready` recompute; trigger check and prompt input filter.
- Templates: feature and bug. Labels as in the labels table, with `review:code` and `review:qa` as the only reviewer labels.
- `spec: off`. Planner; reproducer with `repro-guard` and `manual-repro`; builder at WIP 1 (counting the reproducer); run budget from labels; one must-fix round; the `needs-human` test-fix route.
- CI `test` → review (code, QA) → e2e, Lighthouse report-only, UI reviewer when labeled → label-aware `ready` check.
- Working/result comment with the run link; one line per run in the pinned pipeline-log issue.
- Release stays manual (you build and deploy) until the 5 test changes are done.
- Board: built-in automations only; move cards by hand.

## Build order

1. Write the shared agent-job and post-job templates in `shipyard` first, with the `out.json` format, the label allowlist and the per-agent permission settings files.
2. Attack test: from an agent job, try `git push`, writing `.git/hooks`, editing `.github/`, adding an unlisted label, and a WebFetch. All must fail or be refused.
3. Pilot repo: ruleset on main and a tag ruleset for `v*`; Vercel Production Branch and bypass (if bypass isn't on the free plan, turn off Vercel Authentication for that project's previews and keep links unshared); install the App on the pilot repo and `shipyard`.
4. CI `test` job and `repro-guard` → builder → review (code, QA) → preview, e2e and UI reviewer → label-aware `ready` check. Test the `ready` check on a fake non-web project type too.
5. Must-fix loop, run budget, blocked path, WIP limit, kill switch and the pipeline-log issue; then the planner, `@claude` routing, the reproducer, `manual-repro` and the test-fix route.
6. Run 3 features and 2 bugs, including one bug with no possible test. Then review the real workflow files and the pipeline log, not this doc.
7. Add Walkies as the second repo: `type: game`, `engine`, `monetisation` in `pipeline.yml`; engine CI with the import cache, LFS only in the build job, the LFS path rule; watch Actions minutes and LFS bandwidth weekly.
8. Move to versioned `shipyard` workflows; add the board sync (classic PAT, project scope only) and the queue scheduler.
9. Release automation for Walkies: actor-gated tag, signing secrets only in the release job, Firebase Remote Config flags, monetisation-based release rows, internal → staged rollout.
10. Operate, then Learn, then Discover & Define, then the Promote setup script, each when a product needs it. Leave desktop builds, real-model AI tests and extra panel reviewers until a product needs them.

## Decisions

- **GitHub plan:** staying on GitHub Free (no Pro). Private repos therefore have no branch protection or environment approvals; the push split and the release trigger check cover that.
- **Pilot repo:** a small public web repo of your choice for the first 5 test changes. Walkies (private) is added second, with the game CI.
- **Public repos:** a repo runs the pipeline only when you add the caller workflows with the setup script; nothing is enabled by default.
- **Board:** on your personal account, so the board sync uses a classic PAT with only the project scope.
- **`needs-human`, protected files:** AI review only; you make the change by hand, because the push job refuses those paths.
- **`needs-human`, wrong reproducer test:** after you comment "@claude fix the test: \<reason>", the reproducer rewrites the test and records a new `repro-sha`, the builder continues, and you check the result at your review.
- **Monetisation:** set per game in `pipeline.yml` (`monetisation: [] | [ads] | [iap] | [ads, iap]`). Nothing hosted on Vercel earns money, so the Vercel Pro row applies only if a paid game's landing page is hosted there.
- **Android kill switch:** Firebase Remote Config flags in every game whose monetisation list is not empty.
- **Walkies:** private repo, so its releases rely on the release trigger check rather than an environment approval. Your personal Play account already has production access for it, the first build is uploaded and it uses Play App Signing, so there is no closed-test wait; releases go internal → staged percentage.
- **Game engine:** may change between games, so it is set per project in `pipeline.yml`.
- **Vercel:** free (Hobby) plan, non-commercial use only.
- **WIP limit:** 1 to start, since you use Claude every day; raise to 2 after a week with no limit hits.
- **Self-hosted runner:** never attached to a public repo.

## Changes after freeze

- **4.1:** the agent never holds push credentials; actor-gated release workflow with signing secrets only in the release job; `ready` check recomputed on `workflow_run` and based on project type; `manual-repro` for bugs that can't get an automated test; prompt input filter and public-log rules; release candidates get e2e and UI review; ads, Play Billing and kill-switch rows; WIP limit counts the reproducer; run budget formula.
- **4.2:** pilot is a public web repo, Walkies second; push split enforced by two jobs with the Claude CLI instead of the action; `needs-human` split by cause; `monetisation` field in `pipeline.yml`; reviewer cap simplified to the matrix limit; Actions minutes and LFS rules for private game repos.
- **4.3:** agent-job/post-job pattern for every agent, not just the builder; per-agent tool permissions with no permission skipping; `ready` check requires only labeled reviewers; working/result comment replaces live progress; post job refuses LFS paths and runs no repo code; leftover edits committed before the patch; pinned pipeline-log issue. Final paper version: the next review is of real workflow files.
