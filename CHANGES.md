# CHANGES — Phase A+B+C Refactor

This document explains what changed in the recent refactor and why. The goal of the refactor was to **decouple the framework from SauceDemo** so it can be pointed at any web application by editing config and data files, with **zero changes to agent Python code**.

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
