# Reusing this framework for a different project

> **Verification status (July 2026):** ALL FIXES PRESENT. All 137 unit tests
> pass. Deployed: v17/v18 prompt hardening, orphan cleanup (`ai-update` AND
> `ai-regenerate`), dynamic sprint scoping (`sprint: "auto"` via JIRA_BOARD_ID),
> and end-to-end LLM token & cost instrumentation (per-run tracker + per-story
> ledger). Audit-confirmed: zero hardcoded SauceDemo references in agent code,
> agent prompts, or unit-test logic.

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
- `agents/llm_client.py` — provider-agnostic LLM wrapper (OpenAI-compatible) + token/cost tracking
- `agents/usage_ledger.py` — per-story LLM cost ledger (Jira comments) — fully app-agnostic
- `agents/gherkin_analyzer.py` — Gherkin / step-def matching primitives (renamed from test_inventory.py)
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

ALSO update or REMOVE the `test_users:` block. SauceDemo-specific test users are in there.

> **⚠️ Credentials — read before onboarding a REAL application.**
>
> SauceDemo's credentials (`standard_user` / `secret_sauce`) are safe to commit:
> they are printed on the app's own login page, published in Sauce Labs' docs, and
> guard nothing. **Real application credentials are not.** Putting them in
> `config.yaml` or `prompts/app_context.md` means they are:
>
> 1. **Committed to Git permanently** — deleting the line later does not remove it
>    from history; that needs a history rewrite.
> 2. **Sent to the LLM on every Agent 1 call** — `app_context.md` is injected into
>    the prompt. Most client security policies prohibit exactly this.
>
> **The correct pattern — keep the knowledge, move the secret:**
>
> ```yaml
> # config.yaml — usernames and ROLE BEHAVIOUR are fine; passwords are not
> test_users:
>   admin:  { username: "admin_user",  password_env: "TEST_ADMIN_PASSWORD" }
>   viewer: { username: "viewer_user", password_env: "TEST_VIEWER_PASSWORD" }
>   locked: { username: "locked_user", password_env: "TEST_LOCKED_PASSWORD" }
> ```
>
> ```markdown
> <!-- app_context.md — behavioural knowledge, no secrets -->
> | Username | Password | Notes |
> |---|---|---|
> | `admin_user`  | *(env: TEST_ADMIN_PASSWORD)*  | Full permissions; can approve |
> | `locked_user` | *(env: TEST_LOCKED_PASSWORD)* | Receives lockout error on login |
> ```
>
> Step definitions read the real value at runtime: `os.getenv("TEST_ADMIN_PASSWORD")`.
> Passwords live in GitHub Secrets (CI) and `.env` (local, gitignored).
>
> Agent 1 still learns everything it needs — *that* a locked user exists and *what*
> happens when it logs in — which is what drives good test-case design. It never
> needs to know the password.
>
> **The same rule applies to any other secret** that might drift into these files:
> API keys, DB connection strings, tokens. Behavioural knowledge in the prompt;
> secrets in the environment.

The `agents:` section (label selection rules, completion labels) **stays exactly the same**. The Jira label workflow is universal.

### Change 2 — `app_inventory/<your_app>.json` (MANDATORY)

Delete `app_inventory/saucedemo.json`. Create a new JSON file describing your app's pages, selectors, and methods. See `the "App inventory JSON schema" section below` for the schema.

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
| `tests/unit/*.py` | All 137 unit tests | ❌ NEVER |
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
- `LLM_MODEL` — model id (default `claude-opus-4-6`)
- `JIRA_BOARD_ID` — optional; required only for `sprint: "auto"` (active-sprint resolution)
- `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M` — optional; USD per 1M tokens for real cost numbers
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

# 2. Smoke test: connections to Jira / the LLM endpoint / GitHub
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

The 137 unit tests include:
- 27 LLM usage-tracking and cost-ledger tests (app-agnostic by construction)
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
| Unit tests | ✅ 137 passing |
| Hardcoded SauceDemo references in agent code | ✅ Zero (audited) |
| Hardcoded SauceDemo references in agent prompts | ✅ Zero (audited) |

Your local repo is ready to ship and ready to reuse.

---

## App inventory JSON schema

The `app_inventory/<app>.json` file is the LLM's reference for the application under test (AUT) — its pages, selectors, methods, and conventions. This file is interpolated **verbatim** into Agent 2 and Agent 3 prompts, so its quality directly drives the quality of generated tests.

### Where it's used

- **Agent 2 (Coder)** — both Stage 1 (plan) and Stage 2 (per-file generation) prompts include the full inventory JSON. The LLM uses it to pick correct selectors and reference real page objects.
- **Agent 3 (Reviewer)** — uses the inventory to verify selectors in the PR match what the app actually exposes.

### How it's wired in

1. `config.yaml` — `app_under_test.inventory_file` points at the JSON
2. `agents/app_context.py` — `AppContext.load_page_inventory_json()` reads the file as a raw string
3. Agent prompts substitute `{page_inventory_json}` with that string

You can use any JSON shape you want — the LLM doesn't enforce a schema. The structure below is a **strong convention** that has worked well in practice. Deviating is fine; just make sure the LLM has enough context to reason about your app.

### Recommended structure

```json
{
  "app_name": "string — display name",
  "base_url": "string — root URL",
  "description": "string — 1-2 sentences of context",

  "test_users": {
    "<user_alias>": "string — credentials and notes"
  },

  "pages": {
    "<page_alias>": {
      "url": "string — relative path",
      "page_object_file": "string — path to existing page object .py file",
      "page_object_class": "string — Python class name",
      "elements": {
        "<element_alias>": "string — selector"
      },
      "key_methods": ["array of method signatures already implemented"],
      "implementation_status": "optional string — for partial/missing page objects"
    }
  },

  "common_errors": {
    "<error_alias>": "string — exact error message text"
  },

  "selector_strategy": {
    "preferred": "string — what selector type to use",
    "format": "string — example",
    "avoid": ["array of selector types to avoid"]
  },

  "test_patterns": {
    "framework": "string — e.g., Playwright + pytest-bdd + POM",
    "feature_files_in": "string — directory",
    "step_definitions_in": "string — directory",
    "page_objects_in": "string — directory",
    "naming_convention": {
      "feature_file": "string — pattern",
      "step_file": "string — pattern",
      "page_class": "string — pattern"
    }
  }
}
```

### Field-by-field guidance

#### `app_name`, `base_url`, `description`
Short context the LLM uses to "set the scene." The description should be one or two sentences — enough to know what the app does without bloating the prompt.

#### `test_users`
Map of user aliases to free-form descriptions. Each entry should contain credentials (or how to obtain them) plus any quirks. Examples:

```json
"standard": "standard_user / secret_sauce — normal user, all flows work",
"admin": "admin@test.com / Pass123! — full permissions",
"readonly": "viewer@test.com / Pass123! — cannot edit"
```

The LLM uses these aliases when picking concrete test data.

#### `pages`
The most important section. **Each page is a complete unit** the LLM can reason about. Include:

- **`url`** — relative path. The LLM uses this to know where a page lives.
- **`page_object_file`** — relative path to the page object `.py` file. If the file doesn't exist yet, mark it `"... (NOT YET CREATED)"` so the LLM knows it may need to create one.
- **`page_object_class`** — Python class name (PascalCase).
- **`elements`** — map of semantic alias → selector string. The LLM picks elements by alias; the alias should describe intent (`login_button`), not appearance (`blue_button_top_right`).
- **`key_methods`** — list of method signatures already implemented on the page object. The LLM avoids reinventing these.
- **`implementation_status`** — optional. Use when the page object is partial or absent. Tells the LLM "you may need to extend this" or "you'll need to create this."

#### `common_errors`
The exact error message strings the app produces. The LLM uses these in `Then I should see the error message "..."` assertions. Get them character-perfect — punctuation, capitalization, and trailing periods all matter.

#### `selector_strategy`
Tells the LLM which selector type to use. Crucial for app-specific quirks:

- **SauceDemo:** `[data-test='X']` (stable, always present)
- **A typical SaaS app:** might use `[role='X']` or `text=Submit`
- **Legacy app:** might require XPath as a last resort

The `avoid` list helps the LLM steer clear of brittle selectors.

#### `test_patterns`
Reinforces the project's structural conventions. The LLM uses this section to know where to put new files. Keep the directory paths and naming patterns aligned with what `config.yaml`'s `app_under_test.reference_files` points to.

### Tips for writing a good inventory

1. **Verbose is better than terse.** This file gets sent to the LLM as context — extra detail rarely hurts and often helps disambiguation. The 5–10KB JSON file is well under any token budget concern.

2. **Document what's missing.** If a page object doesn't exist yet, say so. The LLM is much better at "create this from scratch" than at "guess whether this exists."

3. **Use semantic element names.** `submit_button` > `btn_primary` > `[type=submit]`. The element name is the LLM's mental hook.

4. **Include error message text verbatim.** Not paraphrased. The exact string is what tests will assert against.

5. **Update when the app changes.** This file is a contract between you and the LLM. Stale selectors → broken generated tests. Keep it in sync with the real app.

### Validation

There is no JSON schema validator on this file — it's parsed as raw text and embedded in the prompt. The first time you'll catch errors is when generated tests fail. To smoke-test your inventory:

1. Write a single Jira test case that covers a known-working flow
2. Run `agent2_coder.py --story <KEY> --dry-run`
3. Inspect the generated code for selector accuracy
4. If selectors look wrong, the inventory is the most likely culprit

### Examples

The canonical reference is [`app_inventory/saucedemo.json`](../app_inventory/saucedemo.json). Use it as a template when authoring inventory for a new app.