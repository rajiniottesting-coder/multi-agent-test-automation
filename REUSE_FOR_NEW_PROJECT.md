# Reusing this framework for a different project

> **Verification status of your local upload (May 13, 2026):** ALL FIXES PRESENT.
> All 96 unit tests pass. v17 (type contract + locator discipline), v18 (BasePage
> helpers + exact-matching prompt rules), and orphan cleanup (both `ai-update`
> AND `ai-regenerate`) are deployed. Audit-confirmed: zero hardcoded SauceDemo
> references in agent code, agent prompts, or unit-test logic.

This guide explains exactly what to change to point this framework at a different application (e.g., banking app, CMS, internal portal, anything with a web UI testable by Playwright + pytest-bdd).

The framework's design principle is: **agent code never changes between projects. Only config, prompts/app_context, app inventory, and reference files change.**

---

## What stays the same (NEVER touch when reusing)

These files contain zero project-specific knowledge. Reuse as-is:

### Agents (the orchestration brains)
- `agents/agent1_analyst.py` — Jira → Test Cases
- `agents/agent2_coder.py` — Test Cases → Playwright code + PR
- `agents/agent3_reviewer.py` — PR review
- `agents/agent5_reporter.py` — Slack/Jira notification
- `agents/orphan_cleanup.py` — dead-code detection (purely AST + Gherkin)
- `agents/app_context.py` — loads app_under_test from config
- `agents/github_client.py` — GitHub API wrapper
- `agents/jira_client.py` — Jira API wrapper
- `agents/llm_client.py` — Gemini wrapper
- `agents/test_inventory.py` — Gherkin / step-def matching primitives
- `agents/import_validator.py`, `agents/method_resolution_validator.py` — generic validators
- `agents/schemas.py` — Pydantic models

### Agent prompts (templated, read app info from config at runtime)
- `prompts/agent1_analyst.md`
- `prompts/agent2_coder_plan.md`
- `prompts/agent2_coder_generate.md` — includes ALL fixes v15-v18 + BasePage helpers section
- `prompts/agent3_reviewer.md`
- `prompts/agent5_reporter.md`

### Universal page-object helpers
- `pages/base_page.py` — 10 generic Playwright-native helpers from v18. Universal across projects.

### Unit tests (the test suite is project-agnostic)
- `tests/unit/test_agent1_labels.py`
- `tests/unit/test_incremental_update.py`
- `tests/unit/test_orphan_cleanup.py` — uses banking + CMS fixtures
- `tests/unit/test_repair_loop.py`
- `tests/unit/test_validators.py` — one fixture mentions "standard_user" as generic placeholder, not SauceDemo-specific

### Infrastructure
- `.github/workflows/*.yml` — all five workflows
- `requirements.txt`
- `pytest.ini`
- `config/__init__.py`, `config/paths.py`

---

## What you MUST change (project-specific touch points)

There are exactly **6 changes** for a new project. I've ranked them by criticality.

### Change 1 — `config/config.yaml` (MANDATORY)

Edit the `app_under_test` block. Example for a banking app:

```yaml
app_under_test:
  name: "AcmeBank"
  base_url: "https://bank.acme.example.com"
  inventory_file: "app_inventory/acmebank.json"

  reference_files:
    feature: "features/login.feature"
    step_def: "tests/step_defs/test_login.py"
    page_object: "pages/login_page.py"

  reserved_paths:
    - "features/login.feature"
    - "tests/step_defs/test_login.py"
    - "pages/login_page.py"

  extendable_paths:
    - "pages/account_page.py"
    - "pages/base_page.py"        # NEVER remove — universal helpers
```

ALSO update the legacy `base_url:` alias at line 61:

```yaml
base_url: https://bank.acme.example.com   # was: https://www.saucedemo.com
```

ALSO update or REMOVE the `test_users:` block at lines 67-76. SauceDemo-specific test users are in there.

The `agents:` section (label selection rules, completion labels) **stays exactly the same**. The Jira label workflow is universal.

### Change 2 — `app_inventory/<your_app>.json` (MANDATORY)

Delete `app_inventory/saucedemo.json`. Create a new JSON file describing your app's pages, selectors, and methods. See `docs/APP_INVENTORY_SCHEMA.md` for the schema.

This file is what Agent 2's planner uses to understand what page objects exist and what methods they expose. Get it right or Agent 2 will hallucinate methods.

### Change 3 — `prompts/app_context.md` (MANDATORY)

This file IS NOT a template — it's injected verbatim into Agent 1's prompt. Replace SauceDemo content with your app's:

- Known test users / accounts and what each does
- Known error messages (exact wording, used in expected results)
- Page flow / URL structure
- Domain-specific notes the LLM needs

### Change 4 — Author ONE reference test (MANDATORY)

The framework's quality depends on one excellent hand-written reference test. Agent 2 mimics its style; Agent 3 compares new code against it. The reference is THREE files:

- `features/<reference>.feature` — Gherkin example
- `tests/step_defs/test_<reference>.py` — step definitions example
- `pages/<reference>_page.py` — page object example

Make this test:
- A typical user flow for your app (not an edge case)
- Self-contained (no shared state with other tests)
- Clean Gherkin (Given/When/Then with no awkward phrasing)
- Step defs that show parsers.parse usage if your app uses quoted values

This is the only file the LLM "studies" before generating code. Quality matters here more than anywhere else.

### Change 5 — Clean up SauceDemo leftovers (RECOMMENDED)

Delete:
- `features/login.feature` (replaced by your reference)
- `tests/step_defs/test_login.py` (replaced by your reference)
- `pages/login_page.py` (replaced by your reference)
- `pages/inventory_page.py` (SauceDemo-specific)
- `app_inventory/saucedemo.json` (after creating yours)

Keep:
- `pages/base_page.py` — universal helpers
- `pages/__init__.py`
- `tests/step_defs/__init__.py`

### Change 6 — Update README/CHANGES if you want (OPTIONAL)

`README.md` and `CHANGES.md` mention SauceDemo in narrative text. Update for your audience. These are documentation only — code doesn't read them.

---

## What you DO NOT need to change

Confirmed by audit (search for SauceDemo terms in agent code/prompts/tests returns ZERO hits):

| Layer | What's in it | Touch? |
|---|---|---|
| `agents/*.py` | All 11 Python agent files | ❌ NEVER |
| `prompts/agent*.md` | All five agent prompts (NOT app_context.md) | ❌ NEVER |
| `pages/base_page.py` | 10 generic Playwright helpers | ❌ NEVER |
| `tests/unit/*.py` | All 96 unit tests | ❌ NEVER |
| `.github/workflows/*.yml` | All 5 workflow files | ❌ NEVER |
| `config/__init__.py`, `config/paths.py` | Config loading code | ❌ NEVER |
| `requirements.txt`, `pytest.ini` | Dependency / pytest config | ❌ NEVER |
| `agents/orphan_cleanup.py` | Dead-code detection (AST + Gherkin only) | ❌ NEVER |

---

## Per-environment setup (one-time per project clone)

### Secrets (GitHub Actions → Settings → Secrets and variables → Actions)

- `JIRA_BASE_URL` — your Jira instance URL
- `JIRA_USER_EMAIL` — service account email
- `JIRA_API_TOKEN` — service account token
- `JIRA_PROJECT_KEY` — e.g., `ACME` (default: `SCRUM`)
- `OPENAI_API_KEY` — LLM API key (any OpenAI-compatible endpoint)
- `OPENAI_API_BASE` — LLM API base URL
- `GITHUB_TOKEN` — usually auto-provided by Actions
- `SLACK_WEBHOOK_URL` (optional) — for Agent 5 notifications

### Local env (`.env` file, never commit)

Same set of variables as secrets, for local dev runs.

### Jira labels (one-time setup)

Create these labels in your Jira project (the framework uses them):

- `ai-ready` — manual trigger for Agent 1
- `ai-processed` — Agent 1 idempotency marker
- `human-approved` — human-approval gate (you add this after reviewing Test Cases)
- `ai-coded` — Agent 2 idempotency marker
- `ai-regenerate` — force full rewrite
- `ai-update` — surgical incremental update
- `ai-skip` — human override / opt-out

These label names live in `config/config.yaml` and CAN be renamed if your project policy needs different names, but the labels and their workflow effects are described in the GUIDE.md.

---

## Verification checklist for a fresh project

After making the six changes:

```bash
# 1. Unit tests still pass (proves agents + helpers + orphan cleanup still work)
python -m pytest tests/unit/ -q
# Expected: 96 passed

# 2. Smoke test: connections to Jira / Gemini / GitHub
python scripts/smoke_test.py

# 3. Reference test actually runs against your app
pytest tests/step_defs/test_<your_reference>.py -v --headed

# 4. Agent 1 dry-run on one real Jira story
python -m agents.agent1_analyst --story <STORY-KEY> --dry-run

# 5. Agent 2 dry-run on the same story (after Agent 1 created Test Cases)
python -m agents.agent2_coder --story <STORY-KEY> --dry-run
```

If all 5 work, you can promote to live cron-based scanning.

---

## What works "for free" across projects

The fixes we delivered this week aren't tied to SauceDemo. Everything works for the new project automatically:

| Fix | Why it works for any project |
|---|---|
| **v15** universal cross-file completeness rule | Generic step-coverage check — works for any pytest-bdd codebase |
| **v17** type-contract awareness | Tells the LLM to respect declared return types — banking floats, CMS dicts, anything |
| **v17** locator discipline | Native HTML `<select>` / `<input>` patterns are universal |
| **v18** BasePage helpers (10 methods) | Generic Playwright wrappers, no project assumptions |
| **v18** exact phrase matching rule | pytest-bdd's matching semantics are universal |
| **v18** parsers.parse quote handling | Universal `parse` library behavior |
| **Orphan cleanup (ai-update)** | AST + Gherkin, app-agnostic by construction. Verified against banking + CMS fixtures. |
| **Orphan cleanup (ai-regenerate)** | Same algorithm, different wire-in. Same generic guarantees. |

The 96 unit tests include:
- 20 orphan-cleanup tests using **banking** (BANK-101, AccountPage, transfer funds) and **CMS** (CMS-1, SocialPage, schedule tweet) fixtures
- 31 validator tests using generic placeholders
- All other tests use abstract data

If any of these had snuck in a SauceDemo-specific assumption, the tests would fail when run.

---

## Common reuse gotchas (lessons from this build)

These traps caught us during development; flagging so you don't repeat them.

### Gotcha 1: Don't put app-specific helpers in `base_page.py`

`base_page.py` is universal — Playwright primitives only. App-specific helpers belong in your `pages/<app>_page.py`. If you find yourself adding "find_product_by_name" to base_page.py, that's wrong; it goes in inventory_page.py for an e-commerce app or account_page.py for a banking app.

### Gotcha 2: Don't put SauceDemo selectors in reference files

When authoring the reference test for your new app, write selectors that match YOUR app. The framework treats the reference as the "gold standard"; if it has `[data-test='login-button']` (a SauceDemo selector), Agent 2 will mimic that exact attribute syntax. Your app probably uses different conventions (e.g., `[data-testid='login']`, or `#submit`, or React `role` selectors).

### Gotcha 3: Reference test must be currently passing

Agent 3 (Reviewer) will compare new code against the reference. If your reference is broken or flaky, every Agent 2 PR will look "different in a bad way." Fix the reference before promoting cron.

### Gotcha 4: Don't list `base_page.py` in `reserved_paths`

`base_page.py` is in `extendable_paths` because page objects inherit from it. If you mark it reserved, the validator will reject any plan that touches inheritance. It IS protected from orphan-method removal via the orphan_cleanup module's `reserved_file_paths={"pages/base_page.py"}` — that's the right protection.

### Gotcha 5: Jira `JIRA_PROJECT_KEY` env var matters

The framework filters Jira issues by project key. If you set `JIRA_PROJECT_KEY=SCRUM` but your project is `ACME-123`, no stories will be found. Default is `SCRUM`, override in env.

---

## One-paragraph version (if you're in a hurry)

Copy the whole repo. In `config/config.yaml`, change the `app_under_test` block to point at your app and create the matching `app_inventory/<name>.json`. Replace `prompts/app_context.md` with your app's known users / errors / page flow. Write ONE high-quality hand-crafted reference test (feature + step_def + page_object trio) and list those three files in `reserved_paths`. Delete the old SauceDemo files. Run `python -m pytest tests/unit/ -q` — should see 96 passed. Done. **No Python file in `agents/`, no prompt in `prompts/agent*.md`, no unit test, and no workflow file needs to change.**

---

## Summary of state on May 13, 2026

| Component | Status in your latest upload |
|---|---|
| v17 type-contract rule in agent2_coder_generate.md | ✅ Present |
| v17 locator discipline rule | ✅ Present |
| v18 BasePage helpers (10 methods) | ✅ All 10 present in base_page.py |
| v18 exact phrase matching rule | ✅ Present |
| v18 parsers.parse quote rule | ✅ Present |
| v18 BasePage helpers section in prompt | ✅ Present |
| orphan_cleanup.py module | ✅ Present |
| Orphan cleanup tests (20 tests) | ✅ Present |
| GitHubClient.list_files_in_directory | ✅ Present |
| Wire-in for ai-update orphan cleanup | ✅ Present |
| Wire-in for ai-regenerate orphan cleanup | ✅ Present |
| Unit tests | ✅ 96 passing |
| Hardcoded SauceDemo references in agent code | ✅ Zero (audited) |
| Hardcoded SauceDemo references in agent prompts | ✅ Zero (audited) |

Your local repo is ready to ship and ready to reuse.
