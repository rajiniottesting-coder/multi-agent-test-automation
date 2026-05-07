# CHANGES

This document records substantive changes to the framework in reverse-chronological order.

---

## Hotfix v2 — Self-correcting step coverage repair (2026-05-07)

### What broke

After the v1 hotfix unblocked extension of page objects, the next run of SCRUM-12 hit a different failure mode at the validator stage:

```
Step definition coverage check FAILED with 12 error(s):
  - feature step `Then the products should be sorted by name ascending` has no matching @then() decorator
  - feature step `When I select "Price (low to high)" from the sort dropdown` has no matching @when() decorator
  ... (10 more)
```

The validator was working correctly. The LLM (`gemini-2.5-flash-lite` in CI) had generated 12 Gherkin step phrases in the feature file but didn't write matching `@given/@when/@then` decorators in the step def file. This is the exact pattern from PR #9 — weaker models occasionally skip decorators.

### Why the previous design wasn't enough

The validator design was "validate then abort." When weak models slip up, the entire run is wasted — including the work spent generating other files (feature, page objects). The user has to re-trigger from scratch and pay the full quota cost again.

But the validator already produces structured error messages naming the exact step def file and the exact missing step phrases. That's perfect feedback to give back to the LLM for a second attempt.

### Fix — Self-correcting retry loop

Between Stage 2 generation and final validation, a new repair pass runs. If the coverage validator finds errors, the broken step def file (only that one — not the whole batch) is regenerated with explicit feedback in the prompt:

```
# CRITICAL: Validator Feedback — fix these issues

Your previous attempt at this file was rejected by the automated validator.
The specific problems were:

- Step coverage error: feature step `Then the products should be sorted...` 
  has no matching @then() decorator
- (etc.)

You MUST address every one of these issues...

## Your previous attempt (which had the issues above):
[the broken step def file]
```

The loop is bounded:
- Up to **2 retry attempts** per story (configurable)
- Only the broken file is regenerated (not the whole batch)
- If retries exhaust, the final validator raises clearly so you see the issue

### Why this is reusable across projects

- App-agnostic — the validator already works on any feature/step pair
- Model-agnostic — works whether you're on `-lite`, `-flash`, or `-pro`. Lite needs more retries; flash usually doesn't need any
- Story-agnostic — works for sort, cart, checkout, anything
- Cost-bounded — capped retries, only regenerates the broken file
- No hardcoding — all feedback comes from the validator's own error strings

### Files changed

| File | Change |
|---|---|
| `agents/agent2_coder.py` | New `_attempt_step_coverage_repair()` runs between generation and final validation. New `_group_coverage_errors_by_step_def()` parses validator errors. `generate_file_content()` now accepts optional `validator_feedback` and `previous_attempt` kwargs for repair-mode regeneration. |
| `prompts/agent2_coder_generate.md` | New `{validator_feedback_block}` placeholder. When non-empty, the prompt explicitly asks the LLM to fix specific decorator issues. When empty, no behavior change from v1. |
| `tests/unit/test_step_coverage_repair.py` | **NEW** — 10 unit tests covering: error parsing, no-error-noop, single-retry success, retry exhaustion, targeted-only-broken-files repair, validator-feedback passing, prompt-content verification. |
| `CHANGES.md` | This entry. |

### Test results

- **120 unit tests pass** (was 110 before adding the new tests, 90 before the v1 hotfix)
- **1 unrelated pre-existing failure** unchanged (`test_empty_quoted_value_with_parsers_parse_REJECTED` — was already failing before any of these hotfixes)
- All 10 new repair tests pass, including the regression test that mimics the exact SCRUM-12 failure mode (12 missing decorators all targeting one step def file)
- Verified against real production error data: the 12 errors from your failed run group correctly into 1 repair call

### What you'll see in the next run

```
Step coverage check found 12 missing decorator(s) across 1 file(s).
Attempting repair (attempt 1/2)...
  Repairing 'tests/step_defs/test_inventory_sorting.py' with 12 feedback item(s)...
Stage 2: generating content for tests/step_defs/test_inventory_sorting.py...
  Generated ~7500 chars for tests/step_defs/test_inventory_sorting.py
Step coverage repair succeeded after 1 retry attempt(s). All decorators now match.
```

If the LLM still misses things on retry 1, attempt 2 fires automatically. If both fail, you'll see a clear final-validator error telling you to upgrade the model — most likely from `gemini-2.5-flash-lite` to `gemini-2.5-flash`.

### Cost impact

- **Best case** (LLM gets it right first try): zero extra calls. Same as before.
- **Typical case** (lite model misses 1-3 decorators): +1 extra call.
- **Worst case** (LLM keeps missing things): +2 extra calls before final failure.

So worst case adds 2 calls per failed story. Much cheaper than the alternative of having to rerun the whole pipeline (which is 4-5+ calls).

---

## Hotfix v1 — Two-tier path policy (2026-05-07)

### What broke

After the Phase A+B+C refactor was deployed, the first end-to-end run against story SCRUM-12 ("Product Sorting on Inventory Page") failed at Agent 2's plan-validation step:

```
ValueError: LLM tried to overwrite reserved reference files: ['pages/inventory_page.py'].
```

The LLM correctly identified that adding sort tests requires new methods on `InventoryPage` (the existing page object had only `is_loaded()` and `get_page_title_text()`). But `pages/inventory_page.py` was on the reserved-paths list — meaning "never modify under any circumstances" — so the validator rejected the plan.

### Why it happened

The original reserved-paths design treated every reference file as completely immutable. That worked for login-validation tests (PR #7, #9 — purely new files, no extension). But page objects in a POM framework legitimately **grow**:

- Adding sort tests → needs `select_sort_option()` on InventoryPage
- Adding cart tests → needs `add_to_cart()` on InventoryPage
- Adding checkout tests → needs new methods on multiple pages

The framework had no way to model "page object that may be extended additively." Both the LLM and the validator were doing the right thing under the wrong design.

### Fix — clean two-tier file policy

| Tier | Behavior | Example |
|---|---|---|
| **RESERVED** | Never modified. Style baseline. | `features/login.feature`, `tests/step_defs/test_login.py`, `pages/login_page.py` |
| **EXTENDABLE** | May be modified to add new methods, but existing methods/signatures must be preserved. Stage 2 receives current file contents. | `pages/inventory_page.py`, `pages/base_page.py` |
| **NEW** | LLM creates from scratch. | Anything else |

The split is config-driven, app-agnostic, and reusable — onboarding any new app means listing your reference triplet in `reserved_paths` and your existing-page-objects-that-may-grow in `extendable_paths`.

### Files changed

| File | Change |
|---|---|
| `config/config.yaml` | Split `reserved_paths` into `reserved_paths` + `extendable_paths` blocks. Reference files stay reserved; page objects move to extendable. |
| `agents/app_context.py` | Added `extendable_paths` field on the `AppContext` dataclass plus a `extendable_paths_normalized()` helper. Updated `load()` to read the new config block. |
| `agents/agent2_coder.py` | Renamed `validate_no_reserved_paths` to `validate_paths_against_policy` with two-tier logic. New `_build_extendable_paths_block()` renders the extendable list for the prompt. New `_read_extendable_file_content()` reads the current file from disk when an extendable file is being modified. Stage 2 prompt rendering now injects `{existing_file_block}` containing the current content for extendable files. |
| `prompts/agent2_coder_plan.md` | Replaced the single "RESERVED — DO NOT TOUCH" section with TIER 1 / TIER 2 / TIER 3 explanation. The LLM now understands when to set `is_new_file=false` to extend a page object. |
| `prompts/agent2_coder_generate.md` | Added `{existing_file_block}` placeholder so when Stage 2 generates content for an extendable file, the LLM sees the current methods and preserves them. |
| `tests/unit/test_path_policy.py` | **NEW** — 14 unit tests covering every scenario including the exact SCRUM-12 case that broke production. Pin down the validator contract so future refactors can't silently regress it. |

### How extendable mode works end-to-end

1. **Stage 1** — LLM is shown the extendable list with the rule: "set `is_new_file: false` for these; do NOT remove existing methods."
2. **Validator** — accepts plan if extendable files are marked `is_new_file=false`; rejects if marked `is_new_file=true` (would wipe existing).
3. **Stage 2** — for each extendable file in the plan, Agent 2 reads the file from disk and injects it under "EXTENDING EXISTING FILE — preserve all methods below" in the prompt.
4. **LLM** outputs the complete new file (existing methods + new methods).
5. **GitHub commit** — `create_or_update_file` already handles both create and update. No client changes needed.

### Verification

- **110 unit tests pass** (was 90 before adding the new tests)
- **1 unrelated pre-existing failure** unchanged (`test_empty_quoted_value_with_parsers_parse_REJECTED` — was already failing in the uploaded code before this fix)
- All 14 new path-policy tests pass, including the regression test that mimics the exact SCRUM-12 scenario
- All prompt placeholders match all `agent.replace()` calls (audited)
- No new hardcoded values — everything app-specific lives in `config.yaml` or `prompts/app_context.md`

### Migration

If you have config.yaml from before this hotfix, update the `app_under_test:` block:

```yaml
# OLD (one big list — broken for extension)
reserved_paths:
  - "features/login.feature"
  - "tests/step_defs/test_login.py"
  - "pages/login_page.py"
  - "pages/inventory_page.py"   # ← problematic: blocks extension
  - "pages/base_page.py"

# NEW (two tiers — reference vs page-object-that-grows)
reserved_paths:
  - "features/login.feature"
  - "tests/step_defs/test_login.py"
  - "pages/login_page.py"

extendable_paths:
  - "pages/inventory_page.py"
  - "pages/base_page.py"
```

### Onboarding a new app — updated guidance

When adding `app_under_test:` for a new app:
- Put your **reference triplet** (the one hand-written test you want the LLM to mimic) in `reserved_paths`.
- Put **page objects that exist already and may need new methods added** in `extendable_paths`.
- Everything else (new features, new page objects) — the LLM creates fresh, no config needed.

---

# Original Phase A+B+C Refactor

(Notes from the initial refactor session preserved below.)

## TL;DR

- ✅ All app-specific knowledge moved to `config.yaml` and `prompts/app_context.md`
- ✅ Agent code now reads AUT info via a new `AppContext` module
- ✅ Documentation consolidated from 4 docs into 1 GUIDE.md
- ✅ README rewritten to reflect actual implementation (no aspirational claims)
- ✅ Empty `orchestrator/` folder and `dry_run_output.txt` removed
- ✅ All agents now fast-fail on missing env vars at startup
- ✅ Silent error swallowing in `JiraClient._link_to_story` replaced with loud, re-raised errors
- ✅ New `docs/APP_INVENTORY_SCHEMA.md` documents the page-inventory JSON shape
- ✅ Zero unit-test regressions: 90/90 runnable tests pass identically before and after

## Files added

| File | Purpose |
|---|---|
| `agents/app_context.py` | New module — central loader for `app_under_test` config. Exposes `AppContext.load()` with helpers for reference files, page inventory, reserved paths. |
| `prompts/app_context.md` | App-specific context block (test users, error messages, page flow). Injected into Agent 1's prompt at runtime. The single file to edit when onboarding a new app's analyst guidance. |
| `docs/GUIDE.md` | Consolidated guide — replaces ARCHITECTURE.md + BRANCH_NAMING.md + CONFIGURATION.md + HUMAN_APPROVAL_GATE.md. |
| `docs/APP_INVENTORY_SCHEMA.md` | Documents the JSON shape of `app_inventory/<app>.json`. |
| `CHANGES.md` | This file. |

## Files modified

### `config/config.yaml`

**New `app_under_test:` block** at the top of the file. This is now THE single source of truth for AUT-specific values:

```yaml
app_under_test:
  name: "SauceDemo"
  base_url: "https://www.saucedemo.com"
  inventory_file: "app_inventory/saucedemo.json"
  reference_files:
    feature: "features/login.feature"
    step_def: "tests/step_defs/test_login.py"
    page_object: "pages/login_page.py"
  reserved_paths:
    - "features/login.feature"
    - "tests/step_defs/test_login.py"
    - "pages/login_page.py"
    - "pages/inventory_page.py"
    - "pages/base_page.py"
```

Previously these values were hardcoded as Python constants in agent files. Now they live in YAML.

### `agents/agent1_analyst.py`

**Before:** Hardcoded prompt assumed SauceDemo (test users, error messages baked into the prompt template).

**After:**
- Loads `AppContext` at run start
- Reads `prompts/app_context.md` (a separate, editable app-specific block)
- Substitutes `{app_name}`, `{app_base_url}`, `{app_context}` into the main prompt template
- Calls `validate_required_env(...)` at startup (fast-fail on missing config)

### `agents/agent2_coder.py`

**Before:**
- Module-level constant `RESERVED_PATHS = {"features/login.feature", ...}` hardcoded
- `load_reference_files()` and `load_page_inventory()` defined inline with hardcoded paths
- One large `run()` function (~270 lines) doing many things

**After:**
- Reserved paths come from `AppContext.reserved_paths_normalized()`
- Reference loading / page inventory loading delegate to `AppContext`
- `run()` extracted into smaller helpers: `_select_new_test_cases`, `_validate_generated_files`, `_print_dry_run_preview`, `_resolve_unused_revision_branch`
- Prompt placeholders now include `{app_name}`, `{reserved_paths_block}`, `{reference_*_path}` (rendered from config)
- `validate_required_env(...)` at startup

### `agents/agent3_reviewer.py`

**Before:** Same hardcoding as Agent 2.

**After:** Same fix — uses `AppContext`. Prompt template now substitutes the configured reference file paths.

### `agents/agent5_reporter.py`

**Before:** No env-var validation at startup; first failure was a deep API error.

**After:** Calls `validate_required_env(REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS)` in `main()`. No structural changes — Agent 5 doesn't touch reference files or app inventory.

### `agents/jira_client.py`

`_link_to_story` previously caught a bare `except Exception` and logged a warning. This silently masked real failures (a missing link means Agent 2 can't find the test cases via `linkedIssues`).

**After:** Catches `JIRAError` specifically, logs at `ERROR` level with status code and response text, and **re-raises** so the caller can decide whether to abort the batch.

### `prompts/agent1_analyst.md`

App-agnostic. App-specific content (SauceDemo users, error messages) moved to `prompts/app_context.md`. Main template uses placeholders:
- `{app_name}` — name from config
- `{app_base_url}` — URL from config
- `{app_context}` — full content of `app_context.md` (or empty string if missing)
- `{story_text}` — the Jira story (unchanged)

### `prompts/agent2_coder_plan.md`

App-agnostic. New placeholders:
- `{app_name}` — for context heading
- `{reserved_paths_block}` — markdown bullet list rendered from config's `reserved_paths`
- `{reference_feature_path}`, `{reference_step_def_path}`, `{reference_page_object_path}` — file paths from config
- `{reference_*_content}` — file contents (unchanged)

The reserved-paths section, which used to hardcode `features/login.feature` etc., now reads from config.

### `prompts/agent2_coder_generate.md`

App-agnostic. Same placeholders as the plan prompt, plus the per-file metadata that was already there. Removed the SauceDemo-specific worked example (now uses generic `valid_user`/`valid_password` placeholder examples).

### `prompts/agent3_reviewer.md`

App-agnostic. Reference file paths now come from config substitution. Removed concrete references to `LoginPage`, `InventoryPage`, `BasePage` — generalized to "page object classes."

### `README.md`

Rewritten. The previous README claimed features that did not exist (e.g., LangGraph orchestration as a load-bearing component). The new README:
- Accurately describes what each agent does
- Explains why Agent 4 has no Python file (it's a workflow file by design)
- Points readers to GUIDE.md for depth
- Has a new "Onboarding a new application" section that walks through the AUT swap

## Files removed

| File | Reason |
|---|---|
| `dry_run_output.txt` | Stale debugging artifact that should never have been committed. |
| `orchestrator/` (folder) | Empty placeholder for future LangGraph wiring. Not load-bearing. Documenting placeholders implies more than is there — better to remove and add later if needed. |
| `docs/ARCHITECTURE.md` | Consolidated into `docs/GUIDE.md`. |
| `docs/BRANCH_NAMING.md` | Consolidated into `docs/GUIDE.md`. |
| `docs/CONFIGURATION.md` | Consolidated into `docs/GUIDE.md`. |
| `docs/HUMAN_APPROVAL_GATE.md` | Consolidated into `docs/GUIDE.md`. |

## Files retained unchanged

- `agents/test_inventory.py` — has zero SauceDemo coupling. The file is internally well-organized (953 lines but with clear `# ─── ... ───` section headers separating concerns). It has thorough unit-test coverage. **Splitting it was considered and skipped** because the cost (changing imports across the codebase, risking test breakage) exceeds the benefit (no reusability gain — the file is already app-agnostic).
- `agents/jira_client.py` (mostly) — only `_link_to_story` was tightened. The rest is a clean adapter.
- `agents/github_client.py` — already uses targeted `GithubException`. No broad except patterns to tighten.
- `agents/llm_client.py` — already app-agnostic.
- `agents/schemas.py` — already app-agnostic.
- `config/__init__.py`, `config/paths.py` — already app-agnostic.
- All test files in `tests/unit/` — all 90 runnable tests pass identically before and after the refactor.
- All workflow files in `.github/workflows/` — they delegate to Python modules, no SauceDemo references.
- `app_inventory/saucedemo.json` — kept as the canonical example (now also documented in `docs/APP_INVENTORY_SCHEMA.md`).
- All ADRs in `docs/` — historical decision records, retained.

## Verification

Unit tests run identically against original and refactored code:

```
Original:    7 failed, 90 passed
Refactored:  7 failed, 90 passed
```

The 7 failures are identical in both — all environmental (PyGithub/jira not installed in this sandbox) plus one pre-existing test that was already broken. **Zero refactor-introduced regressions.**

## How to onboard a new app (post-refactor)

You should not need to touch any Python file. The full procedure is in `docs/GUIDE.md` under "Onboarding a new app." High-level:

1. Edit the `app_under_test:` block in `config/config.yaml`
2. Drop a new `app_inventory/<your-app>.json`
3. Replace `prompts/app_context.md` with your app's analyst guidance
4. Author one reference test (`features/<x>.feature` + `tests/step_defs/test_<x>.py` + `pages/<x>_page.py`)

That's it.

## What's intentionally NOT included in this refactor

- **Splitting `test_inventory.py`** into multiple modules. Considered; deferred. The file is well-organized internally and changing imports across the codebase risks breaking tests for no reusability gain.
- **LangGraph orchestration.** The empty `orchestrator/` folder was removed. Workflows currently orchestrate via GitHub Actions, which works fine for the current scope. LangGraph wiring can be added later as a real implementation, not a placeholder folder.
- **End-to-end smoke test of the refactor.** Requires real Jira + Gemini + GitHub credentials. Verification in this refactor is via unit tests + import smoke checks. The next session is the right place for an E2E run with a fresh Jira story.

## Migration checklist (if you have an existing local clone)

1. Pull the changes (or apply this refactor's files on top of your clone)
2. `git status` — verify the deletions in step 3 below
3. Manually delete the removed files if they're still in your tree:
   - `dry_run_output.txt`
   - `orchestrator/` directory (if empty)
   - `docs/ARCHITECTURE.md`
   - `docs/BRANCH_NAMING.md`
   - `docs/CONFIGURATION.md`
   - `docs/HUMAN_APPROVAL_GATE.md`
4. Verify your `.env` is intact — refactor changes none of the env-var names
5. `pytest tests/unit/ -v` — should pass with the same numbers as before
6. Run a smoke test: `python -m agents.agent1_analyst --story <YOUR-KEY> --dry-run`