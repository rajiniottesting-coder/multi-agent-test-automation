# 📖 Project Guide

Everything you need to operate, configure, extend, and onboard new apps to this framework — in one place.

## Table of Contents

1. [Architecture](#architecture)
2. [The 5 agents in depth](#the-5-agents-in-depth)
3. [The human-approval gate](#the-human-approval-gate)
4. [Branch naming](#branch-naming)
5. [Configuration](#configuration)
6. [Running the pipeline](#running-the-pipeline)
7. [Onboarding a new app](#onboarding-a-new-app)
8. [Troubleshooting](#troubleshooting)

---

## Architecture

```mermaid
flowchart TB
    Story["📋 Jira Story<br/>label: ai-ready"]
    A1["🤖 Agent 1: Analyst"]
    H1{{"🛑 Human: review<br/>label: human-approved"}}
    A2["🤖 Agent 2: Coder"]
    PR["🔀 GitHub PR"]
    A3["🤖 Agent 3: Reviewer"]
    H2{{"🛑 Human: PR review + merge"}}
    A4["🤖 Agent 4: Runner<br/>(GitHub Actions)"]
    A5["🤖 Agent 5: Reporter"]
    Result["📊 Jira comment<br/>label: tests-run"]

    Story --> A1
    A1 -->|"Test Cases<br/>+ ai-processed"| H1
    H1 --> A2
    A2 -->|"code +<br/>ai-coded"| PR
    PR --> A3
    A3 -->|"AI review comment"| PR
    PR --> H2
    H2 --> A4
    A4 -->|"junit.xml"| A5
    A5 --> Result

    classDef agent fill:#4a90e2,stroke:#2c5aa0,color:#fff
    classDef human fill:#f5a623,stroke:#b07415,color:#fff
    class A1,A2,A3,A4,A5 agent
    class H1,H2 human
```

For more diagrams — component view, Agent 2 sequence, and the labels-as-state-machine — see the "Architecture diagrams" section at the end of this guide.

### Key principles

- **Agents communicate via Pydantic schemas.** No raw JSON or freeform strings between agents. See `agents/schemas.py`.
- **Each agent stops at a checkpoint.** A human reviews before the next agent runs. See [the human-approval gate](#the-human-approval-gate).
- **Idempotency via Jira labels.** `ai-processed` (Agent 1 done), `ai-coded` (Agent 2 done), `tests-run` (Agent 5 done). Re-running an agent against an already-processed story is a no-op.
- **Config-driven, not code-driven.** App-specific knowledge (URL, reference files, page inventory) lives in `config.yaml` and `app_inventory/`. Agent code is app-agnostic.
- **Defensive validators.** Between Agent 2's LLM output and the PR, two validators run: filename consistency (matches feature filename to `feature_path()` calls) and step-def coverage (every Gherkin step has a matching `@given/@when/@then`). These catch LLM drift before it reaches a PR.

---

## The 5 agents in depth

### Agent 1: Analyst (`agents/agent1_analyst.py`)

**Role analogy:** Business Analyst / QA Lead.

**What it does:**
1. Reads a Jira story (description + acceptance criteria) — manual mode (`--story KEY`) or scan mode (`--scan` reads selection criteria from config).
2. Calls Gemini with a prompt template (`prompts/agent1_analyst.md` + `prompts/app_context.md`) and a Pydantic schema (`TestCaseList`).
3. For each generated test case, creates a "Test Case" issue in Jira linked to the parent story.
4. Tags the parent story with `ai-processed` (idempotency).

**Inputs:** Jira story key, or JQL-driven scan.
**Outputs:** Jira "Test Case" issues + `ai-processed` label on parent.

**Why this design:**
- Pydantic validation makes malformed LLM JSON fail loudly, not silently.
- Dry-run mode (`--dry-run`) lets you preview without writing to Jira — essential while iterating on prompts.
- The `prompts/app_context.md` block is the ONE place app-specific guidance lives. The main prompt template is app-agnostic.

### Agent 2: Coder (`agents/agent2_coder.py`)

**Role analogy:** SDET (Software Development Engineer in Test).

**What it does:**
1. Reads approved Test Cases from Jira (filtered by `ai-processed` AND `human-approved` labels).
2. Optional dedup check: if any test cases are already covered by existing scenarios, skip them. (`ai-regenerate` label bypasses this.)
3. **Stage 1 (Plan):** Calls Gemini with a Pydantic schema (`CodePlan`) — gets file paths, types, branch name, PR title. NO code yet.
4. **Stage 2 (Generate):** For EACH file in the plan, calls Gemini in text mode to generate the file's content.
5. **Validators:** Checks filename consistency (Phase 4) and step-def coverage (Phase 8). Fails loudly if either is wrong.
6. Creates a branch (`auto/<JIRA-KEY>-<feature-name>`), commits files, opens a PR.
7. Tags the parent story with `ai-coded`.

**Two-stage approach (rationale):**
Asking the LLM for both structure AND large code bodies in one call has high failure rates — the model truncates, hallucinates, or returns malformed JSON. Splitting into a structured "plan" + per-file "text generation" is dramatically more reliable.

**Defensive features:**
- **Reserved paths guard.** Reads `app_under_test.reserved_paths` from config. If the LLM plans to overwrite a reserved file, the run aborts. Prevents the LLM from clobbering your reference test.
- **Branch-name validator.** Every branch must contain a Jira key (so Agent 5 can map back). Validated before pushing.
- **Filename consistency.** If the LLM generates `features/login-validation.feature` but writes `feature_path("login_validation")` (snake/kebab mismatch), Agent 2 auto-corrects (logs the fix) or fails loudly if the correction is ambiguous. See [DECISIONS.md → ADR-009](./DECISIONS.md) for details.
- **Step-def coverage.** Pairs each generated `.feature` with its `tests/step_defs/test_*.py` and verifies every Gherkin step has a matching `@given/@when/@then`. Hard-fails if any step is uncovered.

**Regeneration mode:**
Add label `ai-regenerate` to a parent story. Agent 2 will:
- Skip the dedup check
- Create a branch with `-rev2/-rev3/...` suffix
- Open a fresh PR
- Remove `ai-regenerate` after success (one-shot signal)
- The original PR stays open as historical record (close it manually)

### Agent 3: Reviewer (`agents/agent3_reviewer.py`)

**Role analogy:** Senior Engineer doing code review.

**What it does:**
1. Reads PR metadata + changed files via PyGithub.
2. Calls Gemini with a rigorous review prompt (`prompts/agent3_reviewer.md`) plus the reference files for style baseline.
3. Post-processes the response: deduplicates issues (Gemini sometimes loops on low-content PRs) and caps at 10 issues.
4. Posts a markdown comment on the PR.

**Triggers:**
- Local: `python -m agents.agent3_reviewer --pr <N>`
- CI: `.github/workflows/agent3-reviewer.yml` runs on PR open/synchronize/reopen

**Why post-process instead of constraining the schema?**
Pydantic's `max_length=10` translates to JSON Schema `maxItems`, which Gemini's constrained-decoding engine cannot compile on complex object arrays (it errors with "too many states for serving"). So we let the LLM produce an unbounded list and trim it deterministically in Python after.

**Anti-hallucination guardrails (built into the prompt):**
- Every issue must quote a specific line from the diff
- "When unsure, approve" — false positives erode trust
- Never speculate about caller behavior you can't see in the diff
- Never flag exception-raising as a bug unless the caller is in the diff and fails to handle it

### Agent 4: Runner

**Implementation:** `.github/workflows/agent4_runner.yml` (no Python module).

**Why no `.py` file?** Agent 4's job is "run pytest, parse junit.xml, upload artifacts." Zero LLM calls, zero API decisions. Wrapping shell commands in Python would be needless indirection. The workflow file is Agent 4 — full stop.

**What the workflow does:**
1. Checks out the PR branch
2. Installs Python deps and Playwright (with browser caching for speed)
3. Runs `pytest` with JUnit XML + HTML output
4. Uploads `reports/` as a workflow artifact (so Agent 5 can read it in the next job)
5. Writes a markdown test summary to the GitHub Actions job summary page

**Triggers:** PR opened, synchronized (new commits), reopened. Plus manual `workflow_dispatch`.

**Why combined with Agent 5 in one workflow?** GitHub Actions has a quirk: workflows triggered by `workflow_run` (cross-workflow) don't appear as PR checks. Combining Agent 4 + Agent 5 into one workflow with two jobs gives both visibility on the PR. Trade-off: Agent 5's check shows as "Agent 4 - Runner / Post Results to Jira" instead of "Agent 5 - Reporter / Post Results to Jira" — cosmetic only.

### Agent 5: Reporter (`agents/agent5_reporter.py`)

**Role analogy:** QA Lead writing a test results summary.

**What it does:**
1. Parses `reports/junit.xml` (produced by Agent 4) into a `RunReport`.
2. Enriches with CI context: PR URL, workflow run URL, commit SHA, link to artifact download.
3. Calls Gemini with a structured schema (`JiraCommentDraft`) to produce ONLY the prose summary (Python adds the deterministic links/metadata after).
4. Posts the comment to the parent Jira story (resolved from PR branch name).
5. Tags the story with `tests-run`.

**Why Python builds the deterministic parts:**
LLMs are bad at conditional rendering (`if PR_URL exists, include link`). Even with explicit instructions, they include "View PR (None)" or similar when fields are unavailable. Splitting prose (LLM) from facts (Python) eliminates this entire class of bugs.

**Story key resolution priority:**
1. `--story` CLI arg (explicit)
2. `JIRA_STORY_KEY` env var
3. Parsed from PR branch name (any `PROJ-123` pattern, regardless of prefix)
4. Skip cleanly (exit 0) if no key found — non-AI PRs don't get reports

---

## The human-approval gate

The architectural answer to "AI is fast but imperfect — how do we keep humans in control of cost and quality without slowing the system to a crawl?"

### End-to-end flow

```
[1] Parent Story (e.g., SCRUM-5 "Login functionality")
       label: ai-ready
              ↓
[2] Agent 1 reads it
       - Generates 5–8 manual test cases
       - Creates linked Jira "Test Case" issues
       - Marks parent story:  label: ai-processed
              ↓
[3] HUMAN REVIEW  ← THE GATE
       - You open the parent story on Jira
       - Read each linked Test Case issue
       - Approve, edit descriptions, or reject (label: ai-skip)
       - When happy:        label: human-approved   (one click)
              ↓
[4] You click "Run workflow" on `Agent 2 - Coder` in GitHub Actions
       (OR scheduled trigger fires later)
              ↓
[5] Agent 2 runs (in CI)
       - Selects: stories with ai-processed AND human-approved
                  AND NOT ai-coded AND NOT ai-skip
       - For each: reads linked Test Cases → generates Playwright code
       - Opens PR
       - Marks parent story:  label: ai-coded
              ↓
[6] Agents 3 (Reviewer) + 4 (Runner) + 5 (Reporter) cascade
       (already automated via workflow files)
```

### Why a gate at all?

Test cases are where the most expensive bad decisions happen. A bad test case → wasted LLM tokens on Agent 2 → broken PR → engineer time debugging. Cost of catching a bad test case BEFORE Agent 2 runs: 1 minute of human review. Cost AFTER: ~30 minutes of code review + cleanup.

The gate is between Agents 1 and 2 specifically because that's the highest-leverage checkpoint. Catching errors earlier is cheaper than catching them later.

### Label semantics

| Label | Meaning | Set by |
|---|---|---|
| `ai-ready` | "Process this story with Agent 1" | Human |
| `ai-processed` | "Agent 1 finished, Test Cases created" | Agent 1 |
| `human-approved` | "I reviewed the Test Cases and approve" | Human |
| `ai-skip` | "Don't process this story (override)" | Human |
| `ai-coded` | "Agent 2 finished, PR is open" | Agent 2 |
| `ai-regenerate` | "Regenerate code for this story — full rewrite (one-shot)" | Human |
| `ai-update` | "Surgically update code for changed/added/deleted Test Cases (one-shot)" | Human |
| `tests-run` | "Agent 5 posted test results" | Agent 5 |

For the full lifecycle view (sticky vs one-shot semantics, who removes what),
see the "Label semantics table" in the State management deep-dive below.

---

## Branch naming

Agent 2 generates branches in the form:

```
auto/<JIRA-KEY>-<feature-name>
```

Examples:
- `auto/SCRUM-5-login-validation`
- `auto/PROJ-123-cart-checkout`

### Why this convention

The Jira key in the branch name is **load-bearing**: Agent 5 extracts it via regex to know which Jira story to post results to. Without a key, Agent 5 can't close the loop — so it skips (gracefully, not as an error).

The regex is in `config/__init__.py`:
```python
JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_]*-\d+)\b")
```

Works for any project prefix: `SCRUM-1`, `PROJ-123`, `MOBILE-42`, `BACKEND-5678`, etc.

### What the validator enforces

`config.assert_valid_branch_for_pipeline(branch_name)` raises `InvalidBranchNameError` if no key is found. Agent 2 calls this before pushing — better to fail BEFORE creating a branch than to discover the gap downstream.

For ad-hoc human branches without a key (e.g., `feature/foo`): Agent 5 detects the missing key, logs a warning, and exits 0. The PR still gets normal CI but no Jira comment.

---

## Configuration

### Environment variables (`.env`)

| Variable | Required | Used by | Notes |
|---|---|---|---|
| `JIRA_URL` | yes | All Jira-touching agents | e.g., `https://yoursite.atlassian.net` |
| `JIRA_EMAIL` | yes | Same | Your Jira account email |
| `JIRA_API_TOKEN` | yes | Same | Create at id.atlassian.com → Security → API tokens |
| `JIRA_PROJECT_KEY` | yes | Same | e.g., `SCRUM`, `PROJ` |
| `JIRA_BOARD_ID` | no* | Agents 1, 2 (scan) | Numeric board ID. *Required only when config.yaml uses `sprint: "auto"`. Find it in the board URL: `.../boards/<ID>` |
| `LLM_PRICE_INPUT_PER_1M` | no | All LLM agents | USD per 1M **input** tokens (repo **Variable**, not secret — e.g. `3.00`). Enables real cost numbers in logs and the story cost ledger. Unset → tokens still logged, cost shows "n/a". |
| `LLM_PRICE_OUTPUT_PER_1M` | no | All LLM agents | USD per 1M **output** tokens (e.g. `15.00`). Set both or neither. |
| `OPENAI_API_KEY` | yes | All agents (LLM) | Your LLM provider's API key |
| `OPENAI_API_BASE` | yes | Same | Base URL of your OpenAI-compatible API endpoint |
| `LLM_MODEL` | no | Same | Defaults to `claude-opus-4-6`. Set to your model name |
| `GITHUB_TOKEN` | yes | Agents 2, 3 | PAT with `repo` scope |
| `GITHUB_REPO` | yes | Same | `<owner>/<repo>` format |
| `BASE_URL` | no | Tests at runtime | Override `config.yaml`'s base_url |
| `PLAYWRIGHT_HEADLESS` | no | conftest | `true`/`false` — overrides config.yaml |
| `JIRA_STORY_KEY` | no | Agent 5 | Manual override for story resolution |
| `PR_NUMBER` | no | Agents 3, 5 | Manual override for PR detection |

Validation: every agent calls `validate_required_env(...)` at startup. Missing vars produce a clear `MissingEnvVarError` listing ALL missing names — not just the first.

### `config.yaml` structure

```yaml
app_under_test:        # The application being tested (the SINGLE decoupling point)
  name: ...
  base_url: ...
  inventory_file: ...
  reference_files:     # files Agent 2/3 use as the style baseline
    feature: ...
    step_def: ...
    page_object: ...
  reserved_paths:      # files Agent 2 must NEVER overwrite
    - ...

browser:               # Playwright settings (headless, viewport, timeout, slow_mo)

base_url: ...          # Legacy alias for tests/conftest.py

test_users: ...        # SauceDemo-specific test data (move/remove for other apps)

agents:
  agent1_analyst:
    selection: { ... } # JQL filter for --scan mode
    completion_label: ...
    max_stories_per_run: ...

  agent2_coder:
    selection: { ... }
    regenerate_selection: { ... }   # for ai-regenerate flow
    completion_label: ...
    regenerate_label: ...
    max_stories_per_run: ...
```

### Sprint scoping

Every scan (Agent 1 and all three Agent 2 passes) is scoped to a sprint via
the `sprint:` key present in each selection block:

| Value | Behavior |
|---|---|
| `"auto"` *(default, recommended)* | Resolves the currently **active** sprint from Jira at runtime via `JIRA_BOARD_ID`. **Zero config changes at sprint boundaries** — when your Scrum master starts Sprint 11, the scans follow automatically. Degrades gracefully: if the board ID is missing or no sprint is active, a warning is logged and the scan spans all sprints. |
| `"openSprints"` | Uses Jira's `sprint in openSprints()` JQL alias. Same effect as auto but needs no board ID; the resolved sprint name won't appear in logs. |
| `"Sprint 10"` | Exact sprint name — pin scans to one specific sprint (useful for retro analysis or parallel-sprint boards). |
| *(key omitted)* | No sprint filter; scans across all sprints (pre-sprint-scoping behavior). |

One-off overrides without editing config: `--sprint "Sprint 10"` on the CLI
(`python -m agents.agent1_analyst --scan --sprint "Sprint 10"`), or the
`sprint` input in the GitHub Actions "Run workflow" dialog. Priority:
CLI/workflow input > config.yaml > no filter.

Finding your board ID: open your board in Jira; the URL contains
`.../jira/software/projects/<KEY>/boards/<ID>` — that number is `JIRA_BOARD_ID`.

### CI secrets

For GitHub Actions, set the same names listed above under repo Settings → Secrets and variables → Actions. The workflows reference them via `${{ secrets.NAME }}`. Add `JIRA_BOARD_ID` as a secret if using `sprint: "auto"`. The two `LLM_PRICE_*` values go on the **Variables** tab (they're not sensitive).

### LLM token & cost tracking

Token usage and cost are tracked as two separate quantities. Tokens are
exact (reported by the API per call); cost is derived from the
`LLM_PRICE_*` variables above.

- **Per run:** every LLM call logs its own tokens plus running totals; each
  story run ends with two lines in the Actions log — `LLM TOKEN USAGE [...]`
  and `LLM COST [...]` (input + output cost shown separately).
- **Per story, end to end:** each LLM-using agent (1, 2, 3, 5) posts a
  machine-parseable `[LLM-USAGE]` comment on the Jira story after it
  finishes. Agent 5 aggregates every entry and appends an
  **"End-to-end LLM usage & cost"** table to its final test report — one
  row per agent run plus a TOTAL row. That table is the actual measured
  cost of taking the story from `ai-ready` to a tested, reported PR.
- Dry runs never post ledger comments. Posting and reading are
  best-effort: a Jira hiccup can't fail a pipeline run. If some runs had
  no pricing configured, the total is marked as a lower bound (token
  totals remain exact).

#### What gets tracked when a story goes through the pipeline

Cost tracking is fully automatic — no per-story action is ever needed.
For a fresh story (e.g. SCRUM-25) the lifecycle looks like this:

| Stage | You do | Tracked automatically |
|---|---|---|
| 1. Create story, add `ai-ready` | manual | — |
| 2. Agent 1 picks it up (cron) | nothing | Actions log: per-call tokens + `LLM TOKEN USAGE` / `LLM COST` summaries; posts `[LLM-USAGE] agent="Agent 1 (Analyst)" ...` comment on the story |
| 3. Review TCs, add `human-approved` | manual | — |
| 4. Agent 2 generates code, opens PR | nothing | Summary lines + `[LLM-USAGE] agent="Agent 2 (Coder, initial)"` comment |
| 5. Agent 3 reviews the PR | nothing | Derives the story key from the `auto/<KEY>-` branch, posts `[LLM-USAGE] agent="Agent 3 (Reviewer)"` |
| 6. Agent 4 runs the tests | nothing | No LLM calls — correctly contributes $0 (nothing posted) |
| 7. Agent 5 reports results | nothing | Reads all prior `[LLM-USAGE]` comments, adds its own usage, appends the **End-to-end LLM usage & cost** table (per-agent rows + TOTAL) to its report, then posts its own usage comment |

When the pipeline completes, the story itself carries the answer: Agent 5's
report shows the actual measured cost of that story — total calls, exact
input/output tokens, and dollars at the configured rates.

Rework is included in the lifetime total: a later `ai-update` or
`ai-regenerate` run posts another ledger entry (e.g. `Agent 2 (Coder,
incremental update)`), and the next Agent 5 report's table includes it —
so the TOTAL reflects the story's true lifetime cost, not just the first
pass.

Prerequisites for full numbers (one-time): the two `LLM_PRICE_*`
variables are set, runs are real (not `--dry-run`), and the pipeline
reaches Agent 5 (the aggregate table is built by the last agent; before
that, the individual `[LLM-USAGE]` comments are already visible on the
story one by one).

---

## Running the pipeline

### Local dev (one story at a time)

```bash
# 1. Generate test cases
python -m agents.agent1_analyst --story SCRUM-5 --dry-run    # preview
python -m agents.agent1_analyst --story SCRUM-5              # commit to Jira

# 2. Approve in Jira (add label: human-approved)

# 3. Generate code + open PR
python -m agents.agent2_coder --story SCRUM-5 --dry-run      # preview
python -m agents.agent2_coder --story SCRUM-5                # opens real PR

# 4. Agents 3, 4, 5 run automatically when the PR opens (via GitHub Actions)
#    Or trigger manually:
python -m agents.agent3_reviewer --pr 12 --dry-run
python -m agents.agent5_reporter --story SCRUM-5 --reports-dir reports/ --dry-run
```

### Scan mode (production)

```bash
python -m agents.agent1_analyst --scan        # processes all stories with ai-ready label
python -m agents.agent2_coder --scan          # processes all approved stories
```

Selection rules come from `config.yaml`'s `agents.<name>.selection` block.

### CI cascade

Once you merge the PAT cascade setup (see [DECISIONS.md → ADR-008](./DECISIONS.md)), pushing a `human-approved` label to a story can auto-trigger Agent 2 in CI. Otherwise, you trigger Agent 2 manually via "Run workflow" on the Actions tab.

---

### Test suites — what runs when

Three distinct test layers exist; they have different triggers and purposes:

| Suite | Trigger | Touches network? | Purpose |
|---|---|---|---|
| `tests/unit/` (123 tests) | Every PR — Agent 4 runs `pytest tests/`, which includes them. Also run manually (`python -m pytest tests/unit/ -q`) before committing any framework change. | No — fully offline (no Jira/GitHub/LLM) | Framework correctness: validators, markers, orphan cleanup, usage tracking, ledger |
| `tests/step_defs/` (generated E2E) | Every PR — same Agent 4 run | Yes — drives a real browser against the app under test | Does the application work |
| `scripts/smoke_test.py` | **Manual only** — run on first setup, after credential/`.env` changes, on a new machine, or when onboarding a new app | Yes — live Jira login, one real LLM call, one browser hit on the app's `base_url` (config-driven) | Is the *environment* wired correctly |

Notes:
- Because Agent 4 runs the whole `tests/` tree, framework unit tests execute
  on every pipeline pass — the framework self-tests on every PR, and a broken
  unit test turns Agent 4's check red just like an app-test failure would.
  (If you ever prefer PR reports to show only app tests, narrow the workflow
  command to `pytest tests/step_defs/` and keep unit tests as the manual
  pre-commit gate.)
- The `smoke:` marker in `pytest.ini` is unrelated to `scripts/smoke_test.py`
  — it's a tag for flagging individual generated tests as quick health checks
  (`pytest -m smoke`).
- The smoke test is deliberately not scheduled: it verifies *setup*, not
  *code*, makes live calls (small LLM cost), and setup doesn't change per
  commit.

---

## Onboarding a new app

The whole point of the recent refactor: **no Python code changes** to point this at a different application. Here's the full step-by-step.

### Step 1: Edit `config/config.yaml` — `app_under_test` block

```yaml
app_under_test:
  name: "MyShopApp"
  base_url: "https://myshop.example.com"
  inventory_file: "app_inventory/myshop.json"
  reference_files:
    feature: "features/cart.feature"            # your reference test
    step_def: "tests/step_defs/test_cart.py"
    page_object: "pages/cart_page.py"
  reserved_paths:
    - "features/cart.feature"
    - "tests/step_defs/test_cart.py"
    - "pages/cart_page.py"
    - "pages/base_page.py"
    # Add any other "do not touch" files
```

### Step 2: Create `app_inventory/myshop.json`

Describes the pages, selectors, and methods of your app. Use `app_inventory/saucedemo.json` as the example. The schema is documented in [REUSE_FOR_NEW_PROJECT.md → App inventory JSON schema](./REUSE_FOR_NEW_PROJECT.md).

### Step 3: Replace `prompts/app_context.md`

Put your app's known users, error messages, page flow notes, and anything else the analyst should know. This file gets injected into Agent 1's prompt.

### Step 4: Author one reference test

Write ONE high-quality, hand-crafted Playwright + pytest-bdd test for a representative flow in your app. This becomes the "style baseline" for Agent 2 (mimic) and Agent 3 (compare against).

The reference triplet is:
- `features/<reference>.feature` — Gherkin
- `tests/step_defs/test_<reference>.py` — step definitions
- `pages/<reference>_page.py` — page object

### Step 5: Optional — clean up SauceDemo leftovers

If you want a pristine repo for your app (no SauceDemo files):
- Delete `app_inventory/saucedemo.json`
- Delete `features/login.feature`, `tests/step_defs/test_login.py`, `pages/login_page.py`, `pages/inventory_page.py`
- Update `config.yaml`'s `test_users:` block (or remove it)
- Update `config.yaml`'s `base_url:` legacy alias

### Step 6: Test locally

```bash
python scripts/smoke_test.py           # verifies env + Jira + the LLM endpoint + Playwright
pytest tests/step_defs/test_<your_reference>.py -v   # runs your reference test

# Then with a real Jira story:
python -m agents.agent1_analyst --story <YOUR-KEY> --dry-run
```

If the dry-run output looks good for your app, you're ready to go.

### What you do NOT need to change

- ❌ Any Python file in `agents/`
- ❌ `config/__init__.py` or `config/paths.py`
- ❌ Any prompt template (`prompts/agent*.md`) — those use `{app_name}` and `{reference_*}` placeholders that read from config
- ❌ Any GitHub Actions workflow file
- ❌ Any test in `tests/unit/`

If the refactor was done correctly, app-onboarding is purely a config/data exercise.

---

## Troubleshooting

### `MissingEnvVarError: Missing required environment variable(s): ...`

You forgot to fill in `.env` (or in CI, set the secret). Fix by copying `.env.example` to `.env` and filling in real values. The error message lists every missing name at once — fix all of them in one go.

### `RuntimeError: JiraClient: missing required env var(s): JIRA_URL, ...`

Same as above but raised by `JiraClient` directly. Means the env-var validation didn't run before the agent reached `JiraClient`. Should not happen with the refactored code, but can if you call `JiraClient()` directly without going through `main()`.

### `QuotaExhaustedError: LLM API rate limit / quota exhausted...`

Your LLM provider's rate limit or quota has been reached. Options:
1. Wait for the rate limit to reset
2. Switch `LLM_MODEL` in `.env` to a different model
3. Check your API plan limits with your provider

### Jira `enhanced_search_issues` not found

You're on an old `jira` package version. Atlassian removed the legacy `/rest/api/2/search` endpoint. Upgrade:
```bash
pip install --upgrade jira
```
Requires `jira>=3.10.5`.

### `StepDefinitionNotFoundError` at test collection

Agent 2's coverage validator should catch this BEFORE the PR is created. If a PR still slips through with this error:
- Check the Agent 2 logs for "Step definition coverage check FAILED"
- Look for an empty quoted value in a Gherkin scenario without a matching `parsers.re()` decorator
- The validator can occasionally miss edge cases — file an issue with the failing scenario

### Filename mismatch (`FileNotFoundError` for a `.feature` file at collection)

Same as above — Agent 2's filename validator catches most of these. If one slips through, check Agent 2 logs for "Auto-correcting filename mismatch" or "Filename consistency error".

### Agent 5 doesn't post a comment

Most common cause: PR branch doesn't contain a Jira key. Agent 5 extracts the story key from the branch name (e.g., `auto/SCRUM-5-foo` → `SCRUM-5`). Branches without a key cause Agent 5 to skip cleanly with a warning log. Manual fix: pass `--story KEY` explicitly, or rename the branch.

### `LLM returned None — could not produce valid <Schema>`

Gemini's structured-output mode failed. Two common causes:
1. A safety filter blocked the response (rare with code/test content)
2. The Pydantic schema has a feature Gemini can't compile (e.g., regex pattern, complex `maxItems`)

Check the schema for any constraints beyond the basics (Literal, default, min_length on lists). Per `agents/schemas.py` notes, avoid `max_length` on lists of complex objects.

---

## Architecture diagrams

This file renders natively on GitHub when viewed in the browser. The Mermaid source is also valuable on its own — paste it into [mermaid.live](https://mermaid.live) to edit.

### Pipeline overview

```mermaid
flowchart TB
    subgraph JIRA["🎫 Jira Cloud"]
        Story["📋 Story<br/>label: ai-ready"]
        TC["📝 Test Cases<br/>(linked issues)"]
    end

    subgraph PIPELINE["🔄 Pipeline"]
        A1["🤖 Agent 1: Analyst<br/>agent1_analyst.py"]
        H1{{"🛑 Human Gate<br/>label: human-approved"}}
        A2["🤖 Agent 2: Coder<br/>agent2_coder.py"]
        PR["🔀 GitHub PR<br/>auto/KEY-feature-name"]
        A3["🤖 Agent 3: Reviewer<br/>agent3_reviewer.py"]
        H2{{"🛑 Human Gate<br/>PR review + merge"}}
        A4["🤖 Agent 4: Runner<br/>agent4_runner.yml"]
        A5["🤖 Agent 5: Reporter<br/>agent5_reporter.py"]
    end

    subgraph LLM["🧠 LLM"]
        Gemini["Google Gemini 2.5 Flash<br/>+ Pydantic structured output"]
    end

    Story -->|"reads requirement"| A1
    A1 -->|"creates 5–8 issues"| TC
    A1 -->|"label: ai-processed"| Story
    TC --> H1
    H1 -->|"approved"| A2
    A2 -->|"generates code,<br/>opens PR"| PR
    A2 -->|"label: ai-coded"| Story
    PR --> A3
    A3 -->|"posts review<br/>comment"| PR
    PR --> H2
    H2 -->|"merged"| A4
    A4 -->|"junit.xml +<br/>HTML report"| A5
    A5 -->|"summary comment +<br/>label: tests-run"| Story

    A1 <-.->|"prompt +<br/>structured output"| Gemini
    A2 <-.->|"plan + per-file<br/>generation"| Gemini
    A3 <-.->|"review prompt"| Gemini
    A5 <-.->|"summary prompt"| Gemini

    classDef agent fill:#4a90e2,stroke:#2c5aa0,color:#fff
    classDef human fill:#f5a623,stroke:#b07415,color:#fff
    classDef jira fill:#0052cc,stroke:#003d99,color:#fff
    classDef llm fill:#34a853,stroke:#1e7733,color:#fff
    classDef artifact fill:#9b9b9b,stroke:#666,color:#fff

    class A1,A2,A3,A4,A5 agent
    class H1,H2 human
    class Story,TC jira
    class Gemini llm
    class PR artifact
```

### Component view

```mermaid
flowchart LR
    subgraph CFG["⚙️ Configuration Layer"]
        CY["config.yaml<br/>app_under_test, agents, browser"]
        ENV[".env<br/>secrets"]
        AC["AppContext<br/>app_context.py"]
        CY --> AC
        ENV --> AC
    end

    subgraph DATA["📦 Data Layer"]
        INV["app_inventory/<app>.json<br/>pages, selectors, methods"]
        REF["features/<ref>.feature<br/>tests/step_defs/test_<ref>.py<br/>pages/<ref>_page.py"]
        ACMD["prompts/app_context.md<br/>app-specific analyst guidance"]
    end

    subgraph PROMPTS["📝 Prompts Layer<br/>(app-agnostic + placeholders)"]
        P1["agent1_analyst.md"]
        P2P["agent2_coder_plan.md"]
        P2G["agent2_coder_generate.md"]
        P3["agent3_reviewer.md"]
        P5["agent5_reporter.md"]
    end

    subgraph AGENTS["🤖 Agents Layer<br/>(app-agnostic)"]
        AG1["agent1_analyst.py"]
        AG2["agent2_coder.py"]
        AG3["agent3_reviewer.py"]
        AG5["agent5_reporter.py"]
    end

    subgraph CLIENTS["🔌 External Adapters"]
        JC["jira_client.py<br/>Jira API"]
        GC["github_client.py<br/>GitHub API"]
        LC["llm_client.py<br/>Gemini + retry/quota"]
    end

    AC --> AG1
    AC --> AG2
    AC --> AG3
    INV -.uses.-> AC
    REF -.uses.-> AC
    ACMD -.uses.-> AG1

    AG1 --> P1
    AG2 --> P2P
    AG2 --> P2G
    AG3 --> P3
    AG5 --> P5

    AG1 --> JC
    AG1 --> LC
    AG2 --> JC
    AG2 --> GC
    AG2 --> LC
    AG3 --> GC
    AG3 --> LC
    AG5 --> JC
    AG5 --> LC

    classDef cfg fill:#e8f4f8,stroke:#4a90e2
    classDef data fill:#fef5e7,stroke:#f5a623
    classDef prompt fill:#e8f5e9,stroke:#34a853
    classDef agent fill:#e3f2fd,stroke:#2c5aa0
    classDef client fill:#f3e5f5,stroke:#8e24aa

    class CY,ENV,AC cfg
    class INV,REF,ACMD data
    class P1,P2P,P2G,P3,P5 prompt
    class AG1,AG2,AG3,AG5 agent
    class JC,GC,LC client
```

### Agent 2 internal flow (two-stage generation)

```mermaid
sequenceDiagram
    participant U as User / Scan
    participant A2 as Agent 2 (Coder)
    participant J as Jira
    participant L as LLM (Gemini)
    participant V as Validators
    participant G as GitHub

    U->>A2: --story SCRUM-5
    A2->>A2: AppContext.load()
    A2->>J: get linked Test Cases
    J-->>A2: list of test cases
    A2->>A2: dedup against<br/>existing scenarios

    Note over A2,L: STAGE 1 — Plan
    A2->>L: prompt + CodePlan schema
    L-->>A2: CodePlan (file paths,<br/>branch name, PR title)
    A2->>A2: validate_no_reserved_paths

    Note over A2,L: STAGE 2 — Per-file generation
    loop for each file in plan
        A2->>L: prompt + file metadata
        L-->>A2: file content (text)
        A2->>A2: extract from markdown fences
    end

    Note over A2,V: Hard validators
    A2->>V: validate_filename_consistency
    V-->>A2: errors / corrections
    A2->>V: validate_step_definitions_complete
    V-->>A2: errors / OK

    Note over A2,G: Push & open PR
    A2->>G: create branch
    A2->>G: commit each file
    A2->>G: open PR
    G-->>A2: PR URL
    A2->>J: label parent ai-coded
```

### State / labels lifecycle

```mermaid
stateDiagram-v2
    [*] --> ai_ready: Human creates story
    ai_ready --> ai_processed: Agent 1 runs

    state human_review <<choice>>
    ai_processed --> human_review: Human reviews TCs
    human_review --> human_approved: ✅ Approve
    human_review --> ai_skip: ❌ Reject
    human_review --> ai_processed: Edit & retry

    human_approved --> ai_coded: Agent 2 runs

    state pr_state <<choice>>
    ai_coded --> pr_state: Human reviews PR
    pr_state --> tests_run: Merge → Agent 4+5 run
    pr_state --> ai_regenerate: Request changes

    ai_regenerate --> ai_coded: Agent 2 runs<br/>(rev2 branch)

    tests_run --> [*]
    ai_skip --> [*]: Story closed (skipped)
```

### Updating this diagram

1. Edit the Mermaid blocks above directly in this `.md` file
2. Preview on [mermaid.live](https://mermaid.live) to verify rendering
3. GitHub renders Mermaid natively in `.md` files — no extra build step

The `README.md` and `docs/GUIDE.md` link to this file. If you change the high-level pipeline, update both:
- `README.md` — the ASCII art under "Architecture"
- `docs/GUIDE.md` — the ASCII art under "Architecture"
- This file — the Mermaid source

---

## State management deep-dive

There is **no database, no orchestrator process, and no in-memory state**.
All pipeline state lives in two external systems the agents read and write:

1. **Jira labels** — workflow position of every story
2. **GitHub** — code state (branches, commits, PRs, JIRA markers inside files)

Any agent, at any time, can reconstruct exactly where a story is by reading
these two sources. That's what makes the pipeline crash-safe: a workflow can
die mid-run and the next cron tick resumes correctly, because nothing was
"in flight" in memory — every completed step already persisted its marker.

### The label state machine

```
(no labels)
    │ human adds ai-ready
    ▼
[ai-ready] ──Agent 1 runs──► [ai-processed]            ai-ready REMOVED (one-shot consumed)
    │                            │ human reviews Test Cases, adds human-approved
    │                            ▼
    │                    [ai-processed, human-approved]
    │                            │ Agent 2 runs (normal mode)
    │                            ▼
    │            [ai-processed, human-approved, ai-coded]   ← happy-path terminal
    │                            │
    │              ┌─────────────┴──────────────┐
    │              │ TC edited/deleted in Jira  │ want full rewrite
    │              │ human adds ai-update       │ human adds ai-regenerate
    │              ▼                            ▼
    │      run_update() splices          run(is_regenerate=True) rewrites
    │      ai-update REMOVED             ai-regenerate REMOVED
    │              └─────────────┬──────────────┘
    │                            ▼
    │            [ai-processed, human-approved, ai-coded]   ← back to terminal
```

#### Label semantics table

| Label | Type | Set by | Removed by | Meaning |
|---|---|---|---|---|
| `ai-ready` | one-shot trigger | human | Agent 1 on success | "Agent 1, process this" |
| `ai-processed` | sticky marker | Agent 1 | never | "Agent 1 is done" — Agent 1 excludes it (idempotency); Agent 2 requires it (prerequisite) |
| `human-approved` | sticky gate | human | never | "a human reviewed the test cases" — Agent 2 requires it |
| `ai-coded` | sticky marker | Agent 2 | never | "code exists, PR opened" — normal-mode Agent 2 excludes it |
| `ai-update` | one-shot trigger | human | Agent 2 on success | "do a surgical incremental update" |
| `ai-regenerate` | one-shot trigger | human | Agent 2 on success | "do a full rewrite on a -revN branch" |
| `ai-skip` | permanent opt-out | human | human | invisible to all agents |
| `tests-run` | sticky marker | Agent 5 | never | "test results reported on the story" |

**Sticky vs one-shot is the core design idea.** Sticky labels are facts
("this happened") and provide idempotency — cron can fire every 15 minutes
and re-scanning is harmless because completed stories are excluded by their
own markers. One-shot labels are commands ("do this once") and are consumed
on success so they can't re-trigger.

### How each agent knows its next step

No agent decides "what's next" for the pipeline. Each agent independently
answers one question — "is there work matching MY selection rules?" — via a
JQL query built from config.yaml:

- **Agent 1**: `labels = ai-ready AND labels != ai-processed AND labels != ai-skip`
- **Agent 2 normal**: `labels = ai-processed AND labels = human-approved AND labels != ai-coded ...`
- **Agent 2 regen**: `... AND labels = ai-regenerate`
- **Agent 2 update**: `... AND labels = ai-update`
- **Agent 3 / 4 / 5**: not Jira-driven at all — they react to GitHub PR
  events (opened / synchronize). The PR's existence IS their trigger state.

The "handoff" between agents is simply: Agent N's completion label is part
of Agent N+1's required-label set. The pipeline order is emergent from the
label algebra, not coded anywhere as a sequence.

### Fine-grained state: JIRA markers inside feature files

Labels track story-level state. Scenario-level state (which Test Case maps
to which code, and whether it changed) lives in the feature files themselves:

```gherkin
## JIRA: SCRUM-29 (hash: a4f9c2e1)
Scenario: Verify default sort order
```

- The **key** ties a scenario to a Jira Test Case permanently.
- The **hash** (SHA-256 of the Jira description, first 8 chars) detects
  edits: `classify_test_cases()` compares file hashes against live Jira and
  buckets every TC as unchanged / modified / new / orphan. This is how
  `ai-update` knows exactly which scenarios to touch.

### What each store is authoritative for

| Question | Authoritative source |
|---|---|
| Has Agent 1 processed this story? | Jira: `ai-processed` label |
| May Agent 2 run? | Jira: `human-approved` present |
| Does code exist for this story? | Jira: `ai-coded` + GitHub: `auto/<KEY>-*` branch |
| Which scenario belongs to which TC? | GitHub: `# JIRA:` markers in .feature files |
| Did a TC change since coding? | Hash in marker vs live Jira description |
| Was the PR reviewed? | GitHub: Agent 3's PR comment exists |
| Did tests pass? | GitHub: Agent 4 check status + JUnit artifact |
| Was the result reported? | Jira: Agent 5's comment (header-signature idempotency) |

### Failure recovery

Because every step persists before the next begins, recovery is trivial:

- Agent 1 dies after creating 2 of 4 Test Cases → `ai-processed` was not yet
  added, so next cron re-runs the story. (Duplicate TC creation is the known
  cost; rare in practice.)
- Agent 2 dies before opening the PR → `ai-coded` not added → next cron
  retries; branch creation is idempotent.
- Agent 5 workflow re-runs → it finds its own comment header and skips.
- Quota exhaustion mid-run → labels not consumed → automatic retry next tick.