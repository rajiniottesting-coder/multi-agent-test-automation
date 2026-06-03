# Multi-Agent Test Automation Framework — Technical Deep Dive

**Audience:** Senior engineer / SDET / architect peer
**Goal:** Be able to explain, debug, and extend this framework at code level
**Source as of:** May 13, 2026 (multi-agent-test-automation-20260513-111329.zip)

---

## Table of Contents

1. [System overview](#1-system-overview)
2. [Repository layout & line counts](#2-repository-layout--line-counts)
3. [The end-to-end flow](#3-the-end-to-end-flow)
4. [Agent 1 — Analyst (deep)](#4-agent-1--analyst-deep)
5. [Agent 2 — Coder (deep, longest section)](#5-agent-2--coder-deep-longest-section)
6. [Agent 3 — Reviewer (deep)](#6-agent-3--reviewer-deep)
7. [Agent 4 — Runner (CI workflow only)](#7-agent-4--runner-ci-workflow-only)
8. [Agent 5 — Reporter (deep)](#8-agent-5--reporter-deep)
9. [Cross-cutting modules](#9-cross-cutting-modules)
10. [The Jira label state machine — every label explained](#10-the-jira-label-state-machine--every-label-explained)
11. [`ai-update` — what it does, scenario by scenario](#11-ai-update--what-it-does-scenario-by-scenario)
12. [`ai-regenerate` — what it does, scenario by scenario](#12-ai-regenerate--what-it-does-scenario-by-scenario)
13. [Other labels in detail](#13-other-labels-in-detail)
14. [Validators — the safety net](#14-validators--the-safety-net)
15. [Reuse architecture (config-driven design)](#15-reuse-architecture-config-driven-design)
16. [Failure modes and recovery](#16-failure-modes-and-recovery)

---

## 1. System overview

Five specialized LLM agents pipelined together to turn a Jira story into a tested pull request. State persists in three external systems:

- **Jira** — workflow state via labels and Test Case sub-issues
- **GitHub** — code, branches, PRs, review comments
- **Test artifacts** — JUnit XML, pytest-html report

No central orchestrator. Each agent is an independent Python entry point invoked by a GitHub Actions workflow. State transitions are observable from outside the system. Any agent can be re-run after failure because all its inputs come from durable stores.

---

## 2. Repository layout & line counts

```
agents/
  __init__.py                         0 lines
  agent1_analyst.py                 270 lines  ← Story → Test Cases
  agent2_coder.py                 2536 lines  ← Test Cases → PR (the heaviest)
  agent3_reviewer.py                388 lines  ← PR review
  agent5_reporter.py                481 lines  ← Results → Jira/Slack
  app_context.py                    210 lines  ← Config loader (NEW — enables reuse)
  github_client.py                  229 lines  ← PyGithub wrapper
  jira_client.py                    289 lines  ← jira-python wrapper
  llm_client.py                     270 lines  ← google-genai wrapper
  schemas.py                        249 lines  ← All Pydantic models
  test_inventory.py                1136 lines  ← Feature/step matching primitives
  orphan_cleanup.py                 593 lines  ← Dead-code detection (NEW)
  import_validator.py               273 lines
  method_resolution_validator.py    578 lines

config/
  __init__.py                       158 lines
  paths.py                           52 lines

.github/workflows/
  agent1_analyst.yml                       — Agent 1 trigger
  agent2_coder.yml                         — Agent 2 trigger
  agent3-reviewer.yml                      — Agent 3 trigger
  agent4_runner.yml                        — Agent 4 + Agent 5 (combined)
  keep-alive.yml                           — daily nudge so cron keeps firing

prompts/
  agent1_analyst.md             39 lines
  agent2_coder_plan.md         181 lines  ← Stage 1 prompt
  agent2_coder_generate.md     361 lines  ← Stage 2 prompt (v17/v18 rules live here)
  agent3_reviewer.md           174 lines
  agent5_reporter.md            65 lines
  app_context.md                       — APP-SPECIFIC (replace for new project)

features/                              — Gherkin .feature files
tests/step_defs/                       — pytest-bdd step definitions
tests/unit/                            — 96 unit tests (76 baseline + 20 orphan cleanup)
pages/                                 — Page Object Model classes
  base_page.py                  ← 10 generic Playwright helpers (v18)

app_inventory/<app>.json               — APP-SPECIFIC (replace for new project)
config/config.yaml                     — App config + agent selection rules
```

**Total Python:** ~7,700 lines (agents) + ~210 lines (config) + ~2,350 lines (tests) = ~10,260 lines

---

## 3. The end-to-end flow

```
[Human creates Jira story, adds acceptance criteria, sets label 'ai-ready']
              ↓
[Cron every 15 min: Agent 1 polls Jira]
              ↓
[Agent 1 — Analyst]
  - reads story description + ACs
  - LLM produces 3-7 Test Cases (structured JSON via Pydantic)
  - creates each as Jira sub-issue, links to parent story
  - parent gets 'ai-processed' label, 'ai-ready' removed
              ↓
[Human reviews Test Cases in Jira, edits if needed, adds 'human-approved']
              ↓
[Cron every 15 min: Agent 2 polls Jira]
              ↓
[Agent 2 — Coder]
  - reads all approved Test Cases
  - Stage 1: LLM plans which files to create (CodePlan JSON)
  - Validates plan against path policy (reserved/extendable)
  - Stage 2: LLM generates each file (feature → page objects → step defs)
  - Repair loop catches & fixes step coverage errors (up to 4 retries)
  - Injects JIRA marker comments above each scenario
  - Branch: auto/<STORY-KEY>-<feature-name>
  - Commits files, opens PR, adds 'ai-coded' label
              ↓
[GitHub PR opened event]
              ↓
[Agent 3 — Reviewer]
  - fetches PR changed files
  - LLM compares each against reference baseline → ReviewReport
  - dedupes/caps at 8 issues
  - posts review comment on PR
              ↓
[GitHub PR opened/synchronize event — same trigger]
              ↓
[Agent 4 — Runner (pure CI, no Python agent file)]
  - sets up Python 3.13 + Playwright + Chromium
  - runs `pytest tests/ --junit-xml --html`
  - uploads artifacts
              ↓
[Same workflow, second job: Agent 5]
              ↓
[Agent 5 — Reporter]
  - parses JUnit XML
  - LLM drafts a prose summary
  - posts to Jira parent story as comment
  - optional Slack webhook
              ↓
[Human reviews PR + Jira comment + decides merge]
```

**Iteration loops (after initial PR):**

- **Test Case description edited in Jira:** human adds `ai-update` label → Agent 2's `run_update()` does surgical splice
- **Want full rewrite:** human adds `ai-regenerate` label → Agent 2's `run(is_regenerate=True)` rewrites everything on `-rev2` branch

---

## 4. Agent 1 — Analyst (deep)

**File:** `agents/agent1_analyst.py` (270 lines)
**Workflow:** `.github/workflows/agent1_analyst.yml`
**Trigger:** Cron `*/15 9-18 * * 1-5` UTC, or manual `workflow_dispatch`

### Key functions

#### `run(story_id: str, dry_run: bool = False) -> dict` (line 93)

The single-story entry point. Steps:

1. **Validate config** — `assert_valid_jira_env()` from `config/__init__.py` raises if `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN` are missing.
2. **Fetch story** — `JiraClient().get_story(story_id)` returns dict with `summary`, `description`, `acceptance_criteria`, `labels`.
3. **Build prompt** — concatenates:
   - System: `prompts/agent1_analyst.md` (39 lines, generic)
   - App context: `prompts/app_context.md` (the ONLY app-specific prompt file)
   - Story content
4. **Invoke LLM with structured schema** — `LLMClient().invoke_structured(system_prompt, user_prompt, output_schema=TestCaseList)`. This uses Gemini's function-calling mode to force JSON conforming to `TestCaseList` (defined in `schemas.py` line 32) which contains:
   ```python
   class TestCaseList(BaseModel):
       test_cases: list[TestCase]   # each has summary, description, steps, category
   ```
   No string parsing. If the LLM returns invalid JSON, Pydantic raises.
5. **Create Jira Test Cases** — for each TC: `JiraClient().create_test_case(tc, parent_story_key=story_id)` which calls `_format_test_case_description()` to format as Jira ADF (Atlassian Document Format) and then `_link_to_story()` to add the "is tested by" link.
6. **Label transitions** — `jira.add_label(story_id, "ai-processed")` then `jira.remove_label(story_id, "ai-ready")`. Order matters: add first (so even if remove fails, the idempotency marker is set).

#### `--scan` mode (in `main()`, line 196)

Calls `JiraClient().find_stories_to_process(selection_config)` which JQL-queries Jira:
```
project = SCRUM AND issuetype = Story AND status in ("To Do", "In Progress")
  AND labels = "ai-ready" AND labels NOT IN ("ai-processed", "ai-skip")
```

Then loops over results, calling `run(story_id)` for each. Capped at `max_stories_per_run: 2` (from config) so a mislabel disaster is bounded.

### Why a Pydantic schema, not free text

- Eliminates JSON parsing brittleness
- Forces consistent Test Case structure (each TC has exactly: summary, description, ordered steps, category)
- LLM can't "forget" the schema mid-output
- A schema violation is a hard error (LLMClient raises), not a silent bug

---

## 5. Agent 2 — Coder (deep, longest section)

**File:** `agents/agent2_coder.py` (2536 lines — the heaviest)
**Workflow:** `.github/workflows/agent2_coder.yml`
**Trigger:** Cron (same schedule as Agent 1) or `workflow_dispatch`

This is where the framework's complexity lives. Three entry points based on Jira labels:

| Mode | Entry function (line) | When |
|---|---|---|
| Normal (first-time) | `run(is_regenerate=False)` (1978) | First time a story is coded |
| Regenerate (full rewrite) | `run(is_regenerate=True)` (1978) | Story has `ai-regenerate` label |
| Update (surgical splice) | `run_update()` (1645) | Story has `ai-update` label |

`main()` (line 2385) dispatches to the correct entry based on labels found during `--scan`.

### 5.1 Feature-file parsing primitives (lines 100-310)

These are the foundations everything else builds on.

#### `_JIRA_MARKER_RE` (line 100)

```python
_JIRA_MARKER_RE = re.compile(
    r"^\s*#\s*JIRA:\s*([A-Z][A-Z0-9_]*-\d+)\s*\(hash:\s*([0-9a-f]{8})\s*\)\s*$"
)
```

Parses marker comments like `# JIRA: SCRUM-29 (hash: a4f9c2e1)`. Strict 8-char hex hash, strict Jira key format. Strict to prevent false matches.

#### `compute_description_hash(description: str) -> str` (line 115)

```python
return hashlib.sha256(description.encode()).hexdigest()[:8]
```

First 8 chars of SHA-256. Used to detect when a Jira Test Case description has been edited. Stored in the feature file marker so we can compare without calling Jira again.

#### `class ScenarioBlock` (line 147)

```python
class ScenarioBlock:
    kind: str               # 'header' | 'background' | 'scenario'
    lines: list[str]        # raw lines including newlines
    jira_key: Optional[str] # parsed from preceding marker comment
    jira_hash: Optional[str]
    def text(self) -> str:  # rejoin lines into a string
```

The atomic unit of feature-file surgery. Each scenario block remembers its Jira identity.

#### `parse_feature_file(content: str) -> tuple[list[str], list[ScenarioBlock]]` (line 222)

The most critical parser in the file. Walks the content line by line:

1. Collects header lines (everything before the first `Scenario:` or `Background:`)
2. For each new block start (`Background:` or `Scenario:`), looks at the previous lines for `# JIRA:` marker
3. Builds `ScenarioBlock` objects with `jira_key`, `jira_hash` populated if marker found

Used by `classify_test_cases`, `splice_scenario`, `_regenerate_step_defs_whole`, and the orphan cleanup module.

#### `splice_scenario(original, jira_key, new_scenario_text, new_hash)` (line 248)

Surgical replacement. Finds the block whose `jira_key` matches; replaces its text with `new_scenario_text` (which must itself contain a marker for the same key); raises if the new text claims a different key (defense against LLM scrambling identities). All OTHER blocks are preserved byte-for-byte (newlines, indentation, comments, blank lines).

#### `remove_scenario(content, jira_key)` (line 300)

Removes the block AND its preceding marker comment in one pass. Returns content with the gap closed.

#### `classify_test_cases(test_cases, feature_content)` (line 310)

The brain of the `ai-update` flow. For each Jira Test Case and each scenario block:

```python
return {
    "unchanged":   [...],  # marker present AND hash matches
    "modified":    [...],  # marker present AND hash differs (description edited)
    "new":         [...],  # Jira has TC, feature has no block with this key
    "orphan_keys": [...],  # feature has block with key, Jira no longer has TC
}
```

`orphan_keys` is what drives both feature-file removal AND orphan code cleanup.

### 5.2 Path policy validator (line 357)

#### `validate_paths_against_policy(plan: CodePlan, ctx: AppContext)` (line 357)

Two-tier file rule enforced post-Stage-1:

| Tier | Definition | Plan rule |
|---|---|---|
| **Reserved** | `app_under_test.reserved_paths` (reference files) | NEVER appear in plan |
| **Extendable** | `app_under_test.extendable_paths` (page objects + base_page) | May appear, MUST have `is_new_file=False` |
| **New** | Everything else | May appear, `is_new_file=True` for fresh files |

Raises `ValueError` with explicit guidance if Gemini hallucinates "let me rewrite login_page.py from scratch." This is the gate that protects your gold-standard reference files from being overwritten.

### 5.3 Cross-file context injection (line 519)

#### `_build_sibling_page_object_context(target_file, already_generated)` (line 519)

Critical for cross-file consistency. When generating `test_inventory.py` (a step def file), the page object `inventory_page.py` has typically already been generated in the same run. This function:

1. Walks `already_generated` for files matching `pages/*.py`
2. `ast.parse()` each one
3. Extracts class names and method signatures (e.g., `sort_products_by(option_label: str) -> None`)
4. Returns a markdown block listing them

Injected into the Stage 2 prompt as "the following page-object classes were generated earlier in this run." Without this, the LLM hallucinates method names — `click_logout()` when the page object actually defined `click_logout_link()`.

#### `_sort_files_for_generation(files_to_create)` (line 599)

Reorders the plan so page objects come BEFORE step definitions. Sequence matters because of the context injection above. New feature files come first too.

### 5.4 The two-stage LLM design

#### Stage 1 — `build_plan(test_cases, ctx, references, page_inventory)` (line 736)

Inputs:
- `test_cases` — the Jira Test Cases (from `load_test_cases_for_story`)
- `ctx` — `AppContext` with app name, paths
- `references` — dict of reference file contents (loaded once)
- `page_inventory` — raw JSON string from `app_inventory/<app>.json`

Calls `LLMClient.invoke_structured(prompt, schema=CodePlan)`. Returns a `CodePlan` (defined in `schemas.py:57`):

```python
class CodePlan(BaseModel):
    feature_name: str          # kebab-case slug for branch
    branch_name: str           # full branch e.g. "auto/SCRUM-29-product-sorting"
    pr_title: str
    pr_body: str
    files_to_create: list[FilePlan]
    notes: str

class FilePlan(BaseModel):
    file_path: str
    file_type: str             # 'feature' | 'step_definitions' | 'page_object'
    purpose: str               # human-readable
    is_new_file: bool
```

The plan is a contract. Path policy validation runs immediately after this.

#### Stage 2 — `generate_file_content(llm, file_plan, plan, test_cases, references, page_inventory, ctx, already_generated)` (line 784)

Called once per file in the plan. Returns the file's content as a string. Internally:

1. Loads the right prompt template (`agent2_coder_generate.md`)
2. Fills placeholders: `{app_name}`, `{file_path}`, `{purpose}`, `{reference_block}`, `{page_inventory_block}`, `{sibling_context_block}`, `{reserved_block}`, `{extendable_block}`, `{test_cases_block}`, `{plan_notes}`
3. For extendable files, reads the existing content from disk so the LLM can ADD methods without losing existing ones
4. Calls `LLMClient.invoke_text(system, user)` — text mode (not structured) because output is Python/Gherkin source
5. `extract_code_from_response()` (line 443) strips markdown fences. Includes the v12e fix:
   ```python
   response_text = re.sub(r"`{4,}", "```", response_text)
   ```
   Pro occasionally emits 6-backtick fences; this normalizes to 3 so the code-extraction regex doesn't fail.

### 5.5 The repair loop (line 1163)

#### `_attempt_step_coverage_repair(generated_files, llm, plan, ...)` (line 1163)

After Stage 2 finishes, validators run. If `validate_step_definitions_complete` reports missing decorators, this function gives the LLM up to 4 retries:

1. Run validators on `generated_files`
2. Collect step-coverage errors via `_collect_repairable_errors()`
3. If errors exist:
   - Build a feedback prompt: "your output had these specific issues, fix them"
   - Call `generate_file_content()` AGAIN — only for the broken file
   - Replace the broken file in `generated_files` with the new output
   - Run validators again
4. Cap at `max_retries=4` (default)

The repair loop is cheap because only the broken file is regenerated, not the full plan. It catches Pro's occasional miss on `parsers.parse` placement or And/But inheritance.

### 5.6 JIRA marker injection (line 1353)

#### `_ensure_jira_markers_on_feature_files(generated_files, test_cases)` (line 1353)

Runs after Stage 2 completes. The LLM is unreliable at consistent comment placement, so markers are inserted post-hoc.

#### `_inject_markers_into_feature(content, test_cases)` (line 1429)

The matching algorithm:

1. Parse the generated feature into `ScenarioBlock`s
2. For each Test Case, find its matching scenario by:
   - Token-overlap similarity (`_title_similarity` at line 1413) between Jira TC summary and Gherkin scenario title
   - Falls back to positional matching if titles diverge (LLM paraphrased)
3. Insert `# JIRA: KEY (hash: 8char)` comment line on top of each matched scenario, preserving indentation
4. Idempotent: if a marker already exists for that key, skip

### 5.7 The `run()` flow (line 1978) — normal + regenerate mode

```python
def run(story_id, dry_run=False, is_regenerate=False) -> dict:
    # 1. INPUT — load Jira story + Test Cases
    # 1b. DEDUP — skipped in regenerate mode
    # 2. CONTEXT — load reference files, page inventory, prompts
    # 3. STAGE 1: PLAN — build_plan() → CodePlan
    # 3b. PATH POLICY — validate_paths_against_policy()
    # 4. STAGE 2: GENERATE — loop over plan.files_to_create
    #    - _sort_files_for_generation() orders page_objects before step_defs
    #    - generate_file_content() per file with already_generated context
    # 4b. SELF-CORRECTING REPAIR — _attempt_step_coverage_repair() up to 4 retries
    # 4d. INJECT JIRA MARKERS — _ensure_jira_markers_on_feature_files()
    # 4e. ORPHAN CLEANUP (regenerate mode only) — cleanup_orphans_after_removal()
    # 4c. FINAL VALIDATION — _validate_generated_files()
    # 5. ACT:
    #    - If regenerate: _resolve_unused_revision_branch() picks auto/...-rev2/rev3
    #    - create branch from main
    #    - create_or_update_file() for each generated file
    #    - open PR with body + footer
    #    - jira.add_label('ai-coded')
    #    - if regenerate: jira.remove_label('ai-regenerate')  # one-shot
```

### 5.8 The `run_update()` flow (line 1645) — surgical splice

```python
def run_update(story_id, dry_run=False) -> dict:
    # 1. Find feature file via _locate_feature_file_for_story() — scans
    #    features/*.feature for any file containing any of the Jira keys
    # 2. Read existing content from main via gh.get_file_content()
    # 3. classify_test_cases() → unchanged/modified/new/orphan_keys
    # 4. If everything unchanged AND no orphans: no-op, exit
    # 5. Splice the feature:
    #    - For each orphan_key: remove_scenario()
    #    - For each modified TC: _generate_single_scenario() then splice_scenario()
    #    - For each new TC: _generate_single_scenario() then append_scenario()
    # 6. Regenerate the step_def file whole: _regenerate_step_defs_whole()
    #    - Builds a CodePlan with just the step_def file
    #    - Calls generate_file_content() with the spliced feature
    # 7. Orphan cleanup: cleanup_orphans_after_removal()
    #    - Reads all step_def files via gh.list_files_in_directory()
    #    - Reads page object files from extendable_paths
    #    - Comments out dead page methods with # AI-ORPHAN: banners
    # 8. Validate, branch (-updateN suffix via _find_unused_update_branch),
    #    commit, open PR
    # 9. jira.remove_label('ai-update')  # one-shot consumed
```

### 5.9 Auxiliary helpers

| Function | Line | Purpose |
|---|---|---|
| `_find_unused_update_branch()` | 1528 | Walks `auto/<story>-<feat>-update1`, `-update2`, etc. until finding one that doesn't exist on GitHub |
| `_resolve_unused_revision_branch()` | 1338 | Same logic but for `-rev2`, `-rev3` (regenerate mode). Preserves the original PR as historical record. |
| `_locate_feature_file_for_story()` | 1536 | For update mode: scans `features/` for a file whose markers reference the Jira keys. Returns the file path. |
| `_generate_single_scenario()` | 1560 | Smaller-scoped LLM call for `run_update`'s modified/new scenarios. Returns ONE scenario block's text with marker. |
| `_regenerate_step_defs_whole()` | 1596 | The whole step-def file is regenerated from scratch based on the spliced feature. This is why orphan step-def FUNCTIONS naturally disappear (LLM doesn't see them in the new feature). |
| `_print_dry_run_preview()` | 1303 | Prints planned actions without committing. Used by `--dry-run` flag. |

### 5.10 Tests for Agent 2

| Test file | Tests | Covers |
|---|---|---|
| `tests/unit/test_incremental_update.py` | 34 | All ScenarioBlock parsing, splice/append/remove, classify_test_cases, marker injection, v12e backtick normalization |
| `tests/unit/test_repair_loop.py` | 8 | The repair loop logic with mocked validators |
| `tests/unit/test_orphan_cleanup.py` | 20 | Orphan detection across banking + CMS domains |
| `tests/unit/test_validators.py` | 31 | All validators (filename consistency, feature structure, step completeness, imports, method resolution) |

96 tests total, all passing in ~2 seconds.

---

## 6. Agent 3 — Reviewer (deep)

**File:** `agents/agent3_reviewer.py` (388 lines)
**Workflow:** `.github/workflows/agent3-reviewer.yml`
**Trigger:** GitHub `pull_request` event (opened, synchronize) — NOT Jira-driven

### Key functions

#### `run(pr_number: int, dry_run: bool = False) -> dict` (line 246)

1. **Fetch PR metadata** via `gh.get_pr_metadata(pr_number)`: returns dict with `title`, `body`, `head_branch`, `base_branch`, `author`
2. **Fetch changed files** via `gh.get_pr_changed_files(pr_number)`: list of dicts with `filename`, `status` (added/modified/removed), `patch` (unified diff), `additions`, `deletions`
3. **Filter** — keep only `.py` and `.feature` files. Skip removed files, generated artifacts, lockfiles.
4. **Build prompt** — concatenates:
   - System: `prompts/agent3_reviewer.md`
   - PR metadata
   - Reference files block (from `ctx.load_reference_files()`)
   - `format_changed_files_for_prompt(files)` (line 152) — renders each file's name, status, patch as a markdown section
5. **Invoke LLM with structured schema**:
   ```python
   report = llm.invoke_structured(prompt, schema=ReviewReport)
   ```
   `ReviewReport` (schemas.py:136) contains:
   ```python
   class ReviewReport(BaseModel):
       summary: str
       issues: list[ReviewIssue]   # severity, file, line, description, suggestion
   ```
6. **Dedupe & cap** via `dedupe_and_cap_issues(report, max_issues=8)` (line 115). Normalizes each issue's `description` via `_normalize_description()` (lowercase, strip punctuation) and deduplicates. Caps at 8 to keep the PR comment readable.
7. **Format as markdown** via `format_review_as_markdown(report)` (line 174). Issues grouped by severity (high/medium/low/info), each with file:line link.
8. **Post comment** via `gh.post_pr_comment(pr_number, markdown)`. Idempotent: if a comment with the same header already exists, edit it in place (not duplicate).

### Why structured output

A free-form text review is a wall of unstructured prose that can't be deduplicated, capped, or filtered. The `ReviewReport` schema gives:
- Programmatic dedup
- Severity sorting
- Per-issue file:line attribution
- Consistent rendering across runs

### `resolve_pr_number(cli_arg_pr)` (line 65)

Looks for the PR number in this priority order:
1. CLI `--pr` arg
2. `GITHUB_EVENT_PATH` env var (CI mode — workflow exposes this)
3. Latest open PR on the branch (fallback for local dev)

---

## 7. Agent 4 — Runner (CI workflow only)

**File:** None — pure CI workflow
**Workflow:** `.github/workflows/agent4_runner.yml`
**Trigger:** GitHub `pull_request` event (same as Agent 3)

No Python agent file. The "intelligence" is the test code Agent 2 wrote; Agent 4 is the proof step.

### Workflow steps

1. **Checkout PR branch** via `actions/checkout@v4`
2. **Setup Python 3.13** via `actions/setup-python@v5`
3. **Install deps**: `pip install -r requirements.txt && playwright install --with-deps chromium`
4. **Run tests**:
   ```bash
   pytest tests/ -v \
     --html=reports/pytest-report.html \
     --self-contained-html \
     --junit-xml=reports/junit.xml \
     --tb=short
   ```
   Note: `tests/` includes BOTH `tests/unit/` (no browser) AND `tests/step_defs/` (Playwright BDD)
5. **Upload artifacts** via `actions/upload-artifact@v4`: pytest-html + junit.xml
6. **Inline Python step** parses `junit.xml` and writes a markdown table to `$GITHUB_STEP_SUMMARY` — appears on the PR check page
7. **Job 2: Agent 5** — separate job in same workflow, with `needs: run-tests`

### Why combined Agent 4 + Agent 5 in one workflow

Performance: Agent 5 needs Agent 4's JUnit XML. Combining them avoids artifact upload + re-download between separate workflow runs. The two appear as separate "checks" on the PR.

---

## 8. Agent 5 — Reporter (deep)

**File:** `agents/agent5_reporter.py` (481 lines)
**Workflow:** Same as Agent 4 (second job)
**Trigger:** `needs: run-tests` in `agent4_runner.yml`

### Key functions

#### `parse_junit_xml(junit_path: Path) -> RunReport` (line 64)

Parses pytest's JUnit XML output. Returns a `RunReport` (schemas.py:210):

```python
class RunReport(BaseModel):
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_seconds: float
    tests: list[TestResult]   # name, status, duration, failure_message
    pr_number: Optional[int]
    pr_branch: Optional[str]
    commit_sha: Optional[str]
```

Handles classic xunit format AND pytest's extension (skipped, errors as separate elements).

#### `gather_ci_context(report, cli_pr)` (line 145)

Fills in `pr_number`, `pr_branch`, `commit_sha` from env vars set by the workflow (`GITHUB_REF`, `GITHUB_HEAD_REF`, `GITHUB_SHA`).

#### `resolve_story_key(cli_arg, pr_branch)` (line 254)

Extracts the Jira key from the PR branch name. Branch format: `auto/<KEY>-<feature>-<suffix?>`. Regex: `r"auto/([A-Z][A-Z0-9_]*-\d+)-"`. Falls back to CLI arg.

#### `run(story_key, reports_dir, dry_run, cli_pr)` (line 325)

1. Parse JUnit XML
2. Gather CI context
3. Load `prompts/agent5_reporter.md`
4. Invoke LLM with structured schema `JiraCommentDraft` (schemas.py:231):
   ```python
   class JiraCommentDraft(BaseModel):
       summary_line: str       # one-line summary
       prose_body: str         # 2-3 paragraph narrative
       severity: str           # 'all_pass' | 'minor' | 'major'
   ```
5. Compose final comment via `build_final_comment(prose_body, report)` (line 210). Appends a deterministic test-result table to the LLM's prose.
6. Post to Jira parent story via `jira.add_comment(story_key, comment)`. Idempotent: checks existing comments for matching header signature.

### Idempotency design

A workflow can rerun multiple times (manual rerun, retry on transient failures). Agent 5 detects its own previous comment by a unique header signature: `🤖 Agent 5 — Test Run Report (PR #<N>)`. If found, it skips (doesn't post a duplicate).

---

## 9. Cross-cutting modules

### 9.1 `agents/app_context.py` (210 lines) — the reuse enabler

#### `class AppContext` (line 50)

Frozen dataclass holding the `app_under_test` block from config.yaml:

```python
@dataclass(frozen=True)
class AppContext:
    name: str
    base_url: str
    inventory_file: str
    reference_feature: str
    reference_step_def: str
    reference_page_object: str
    reserved_paths: tuple[str, ...]
    extendable_paths: tuple[str, ...]
```

#### Key methods

- `load(cls, config_path=None)` (line 74) — class method that reads config.yaml, validates required fields, returns an AppContext
- `reference_file_paths` (line 144) — returns `{'feature': Path, 'step_def': Path, 'page_object': Path}`
- `inventory_path` (line 152) — Path object for the inventory JSON
- `reserved_paths_normalized()` (line 156) — `set[str]` of paths with forward slashes for portable comparison
- `extendable_paths_normalized()` (line 161) — same for extendable paths
- `load_reference_files()` (line 174) — reads all three reference files, returns `{'feature': str, 'step_def': str, 'page_object': str}`
- `load_page_inventory_json()` (line 196) — reads inventory JSON file, returns raw string for prompt injection

This is the single point where app config is loaded. Every agent calls `AppContext.load()` once.

### 9.2 `agents/test_inventory.py` (1136 lines) — feature/step matching engine

The hardest computation in the codebase. Used by:
- Agent 2's repair loop and final validation
- Agent 2's deduplication (`filter_duplicate_test_cases`)
- Orphan cleanup's step matching

#### `_extract_feature_steps(feature_content) -> list[tuple[str, str]]` (line 598)

Walks a Gherkin file and returns `[(keyword, phrase), ...]` for every step. Handles:

- `And`/`But` keyword inheritance — resolves to the previous concrete keyword (Given/When/Then) since pytest-bdd dispatches that way
- Background steps included (they need step defs too)
- Scenario Outline `Examples:` tables stripped (they're data, not steps)
- Comments and blank lines skipped

#### `_extract_decorator_phrases(step_def_content) -> list[tuple[str, str, str]]` (line 655)

Walks a Python step-def file and returns `[(kind, phrase, parser_type), ...]`:

- `kind` ∈ `'given'`, `'when'`, `'then'`
- `parser_type` ∈ `'string'` (bare string decorator), `'parse'` (parsers.parse), `'cfparse'` (parsers.cfparse), `'re'` (parsers.re)

Uses regex `_DECORATOR_PARSER_PATTERN` and `_DECORATOR_STRING_PATTERN`. Critical: when a `parsers.parse(...)` is found, the bare-string pattern is skipped at that location (so the same decorator isn't counted twice).

#### `_phrase_matches(feature_phrase, decorator_phrase, parser_type) -> bool` (line 695)

THE matching function. Uses pytest-bdd's actual runtime backends:

- `'string'`: exact equality after `.strip()`
- `'parse'` / `'cfparse'`: the `parse` library (`from parse import parse`)
- `'re'`: Python `re.fullmatch`

This closes the gap that caused PR #9: an earlier validator was permissive about empty quoted values, but the `parse` library refuses to match them at runtime. By using the SAME backend pytest-bdd uses, the validator's verdict matches runtime behavior exactly.

#### `validate_step_definitions_complete(generated_files, project_root=None)` (line 857)

The cross-file step coverage validator. For every step in every generated feature file:
1. Is there a matching `@given/@when/@then` decorator in the paired step def file?
2. If not, is there one in any OTHER pre-existing step def file? (pytest-bdd allows cross-file step reuse)
3. If still not, return an error string with diagnostic info (which file, which step, what decorator was almost-matching)

Returns `list[str]` of errors. Empty list = all good.

#### `validate_filename_consistency(generated_files)` (line 331)

Catches the PR #7 regression: `features/sort-products.feature` paired with `tests/step_defs/test_sort_products.py` — kebab-case feature filename vs snake_case step-def filename. The feature_path() call in step_defs assumes the snake_case form.

Includes `_try_autocorrect_feature_name()` (line 481) which can fix simple mismatches automatically in-flight.

#### `validate_feature_file_structure(generated_files)` (line 752)

Catches orphan Given/When/Then lines outside any Scenario block. pytest-bdd would fail at collection time with a cryptic error; this validator catches it pre-commit with a clear message.

### 9.3 `agents/orphan_cleanup.py` (593 lines) — dead code detection

Implements the cleanup described in §5.8/§5.7. Detailed earlier; key functions:

| Function | Line | Purpose |
|---|---|---|
| `extract_steps_in_removed_scenarios()` | 77 | Returns `[(kw, phrase), ...]` for steps inside deleted Jira Test Cases' scenario blocks. Uses lazy import of `parse_feature_file` to avoid circular dep. |
| `find_orphan_step_defs()` | 114 | AST walks each step def file. For each function with a step decorator: matches a removed step? matches a surviving step? → returns OrphanStepDef list |
| `find_orphan_page_methods()` | 293 | Two-pass AST walk. Pass 1: collect method names called from orphan step defs. Pass 2: collect method names called from surviving step defs. Orphans = pass1 \ pass2. Excludes private methods (`_*`), excludes reserved files (`pages/base_page.py`). |
| `comment_out_orphan_page_methods()` | 420 | Walks file lines, prefixes orphan func lines with `# `, prepends `# AI-ORPHAN:` banner with the removed Jira keys |
| `cleanup_orphans_after_removal()` | 502 | Top-level orchestrator. Called from both `run_update()` (line 1769) AND `run()` regenerate mode (line ~2120). Both wrapped in try/except so cleanup failure doesn't block the PR. |

Tests: 20 unit tests in `tests/unit/test_orphan_cleanup.py` using banking AND CMS fixtures (zero SauceDemo content) to prove app-agnosticism.

### 9.4 `agents/llm_client.py` (270 lines)

#### `class LLMClient` (line 79)

Wraps any OpenAI-compatible LLM API via `langchain-openai`. Configuration from env vars: `OPENAI_API_KEY`, `OPENAI_API_BASE`, `LLM_MODEL`.

#### Key methods

- `invoke_structured(system, user, output_schema)` (line 112) — function-calling mode, returns instance of `output_schema` (a Pydantic class). Internally uses `response_mime_type="application/json"` and `response_schema=output_schema` from genai SDK. Raises `pydantic.ValidationError` if output doesn't match.
- `invoke_text(system, user)` (line 151) — plain text generation. Returns raw string. Used for code generation where output is Python/Gherkin source.
- `_call_with_quota_check()` (line 95) — wraps SDK calls. Detects quota-exceeded errors via `_is_quota_error()` (line 66) and raises `QuotaExhaustedError` with a clear message.

#### `_code_gen_max_output_tokens(model_name)` (line 57)

Returns max output tokens based on model name. Pro 2.5 supports 65k output. Critical for large step_def file generation; insufficient tokens cause truncation mid-file.

### 9.5 `agents/jira_client.py` (289 lines)

Wraps the `jira` Python SDK. Methods:

| Method | Line | Purpose |
|---|---|---|
| `get_story(issue_key)` | 55 | Returns dict with summary, description, AC, labels |
| `find_stories_to_process(selection_config)` | 67 | Builds JQL from config dict, returns matching stories |
| `create_test_case(test_case, parent_story_key)` | 121 | Creates Jira sub-issue. Uses `_format_test_case_description` to render structured ADF |
| `_link_to_story(test_case_key, story_key)` | 138 | Adds "is tested by" link (Atlassian link type) |
| `add_label(issue_key, label)` | 196 | Idempotent — checks existing labels before adding |
| `remove_label(issue_key, label)` | 207 | Idempotent — skips if label not present |
| `add_comment(issue_key, body)` | 226 | Plain markdown comment |
| `get_parent_story_key(issue_key)` | 246 | For Test Case → parent Story lookup |

### 9.6 `agents/github_client.py` (229 lines)

Wraps PyGithub. Methods used across agents:

| Method | Line | Purpose |
|---|---|---|
| `create_branch(name, from_branch)` | 46 | Creates from main, idempotent (logs if exists) |
| `branch_exists(name)` | 61 | Used by `_find_unused_update_branch` and `_resolve_unused_revision_branch` |
| `create_or_update_file()` | 84 | Single-file commit. Detects new vs existing via try/except. Used in commit loops. |
| `get_file_content(path, branch)` | 114 | Reads file content for incremental update flow |
| `list_files_in_directory(path, branch)` | 119 | NEW — for orphan cleanup to find sibling step_def files. Returns repo-relative paths, empty list on failure (defensive). |
| `open_pull_request()` | 139 | Idempotent — if a PR exists for the branch, returns its URL instead of erroring |
| `get_pr_metadata(pr_number)` | 169 | Used by Agent 3 |
| `get_pr_changed_files(pr_number)` | 183 | Used by Agent 3 — includes the unified diff patches |
| `post_pr_comment(pr_number, body)` | 219 | Idempotent via header signature matching |

### 9.7 `agents/schemas.py` (249 lines) — every Pydantic model

| Class | Used by | Purpose |
|---|---|---|
| `TestStep` | Agent 1 | One step inside a Test Case (Given/When/Then text) |
| `TestCase` | Agent 1 | Single test case (summary, description, steps, category) |
| `TestCaseList` | Agent 1 | Wrapper — the LLM returns a list of these |
| `FilePlan` | Agent 2 | One file in the plan (path, type, is_new_file, purpose) |
| `CodePlan` | Agent 2 | Stage 1 output — list of FilePlans + branch/PR metadata |
| `GeneratedFile` | Agent 2 | A generated file (path, content, is_new_file, purpose) — runtime, not from LLM |
| `CodeGenerationOutput` | Agent 2 | Container for final generated files + plan metadata |
| `ReviewIssue` | Agent 3 | One issue in the review (severity, file, line, description, suggestion) |
| `ReviewReport` | Agent 3 | Container for issues + summary |
| `TestResult` | Agent 5 | One test result from JUnit |
| `RunReport` | Agent 5 | Container — totals + tests + CI context |
| `JiraCommentDraft` | Agent 5 | LLM-drafted comment (summary, prose, severity) |

---

## 10. The Jira label state machine — every label explained

Configuration source: `config/config.yaml` → `agents.agent1_analyst` and `agents.agent2_coder`.

### Label flow diagram (text version)

```
Initial state (story freshly created): no labels
       │
       │  human adds
       ▼
   [ai-ready]                           ← Agent 1's cron will pick this up
       │
       │  Agent 1 runs:
       │  - creates Test Case issues in Jira
       │  - adds 'ai-processed'
       │  - removes 'ai-ready'
       ▼
   [ai-processed]                       ← human-review phase
       │
       │  human reviews Test Cases, edits any descriptions in Jira
       │  human adds 'human-approved'
       ▼
   [ai-processed, human-approved]       ← Agent 2's cron will pick this up
       │
       │  Agent 2 runs (normal mode):
       │  - LLM plans + generates feature, step_defs, page_objects
       │  - commits, opens PR
       │  - adds 'ai-coded'
       │  - Agents 3, 4, 5 fire on the PR
       ▼
   [ai-processed, human-approved, ai-coded]       ← terminal state for "happy path"

──────────── Iteration paths from here ────────────

If a Test Case description was edited in Jira AFTER initial coding:
       │
       │  human adds 'ai-update'
       ▼
   [ai-processed, human-approved, ai-coded, ai-update]
       │
       │  Agent 2 runs run_update():
       │  - surgical splice of feature file
       │  - regenerates step_def file
       │  - orphan cleanup on page objects
       │  - opens NEW PR on -update1 branch
       │  - removes 'ai-update' (one-shot)
       ▼
   [ai-processed, human-approved, ai-coded]       ← back to terminal

If you want a FULL rewrite (e.g., framework changes, major redesign):
       │
       │  human adds 'ai-regenerate'
       ▼
   [ai-processed, human-approved, ai-coded, ai-regenerate]
       │
       │  Agent 2 runs run(is_regenerate=True):
       │  - skips dedup
       │  - regenerates EVERYTHING
       │  - branch with -rev2 suffix (preserves original PR)
       │  - removes 'ai-regenerate' (one-shot)
       ▼
   [ai-processed, human-approved, ai-coded]       ← back to terminal

To opt out a story permanently:
       │  human adds 'ai-skip'
       ▼
   [..., ai-skip]                       ← Agent 1 + Agent 2 will skip this story forever
```

### Complete label reference

| Label | Set by | Removed by | Lifecycle | Effect |
|---|---|---|---|---|
| `ai-ready` | Human | Agent 1 (on success) | One-shot trigger | Tells Agent 1's `--scan` to process this story |
| `ai-processed` | Agent 1 | Never (sticky) | Permanent idempotency marker | Tells Agent 1 "already done"; required by Agent 2 selection |
| `human-approved` | Human | Never (sticky) | Permanent approval gate | Required by Agent 2 — proves human reviewed Test Cases |
| `ai-coded` | Agent 2 | Never (sticky) | Permanent idempotency marker | Tells Agent 2 normal mode to skip; required (implicitly) for ai-update/ai-regenerate to make sense |
| `ai-update` | Human | Agent 2 (on success) | One-shot trigger | Causes Agent 2 to run `run_update()` instead of `run()` |
| `ai-regenerate` | Human | Agent 2 (on success) | One-shot trigger | Causes Agent 2 to run `run(is_regenerate=True)` |
| `ai-skip` | Human | Human | Permanent opt-out | Excluded by ALL agents — story is invisible |

---

## 11. `ai-update` — what it does, scenario by scenario

**Entry point:** `agents/agent2_coder.py::run_update()` at line 1645

**Selection (from `config.yaml`):**
```yaml
update_selection:
  required_labels: ['ai-processed', 'human-approved', 'ai-update']
  excluded_labels: ['ai-skip', 'ai-regenerate']
```

**Prerequisites:**
- Story has been coded before (typically has `ai-coded`)
- Feature file exists on `main` with JIRA marker comments (`# JIRA: KEY (hash: xxx)`)
- If no marker exists, Agent 2 exits with status `"no_markered_file"` — the story must go through normal mode or `ai-regenerate` first to get markers

**Six scenarios — what `ai-update` does in each:**

### Scenario A — All Test Cases unchanged (no Jira edits since last code-gen)

- `classify_test_cases()` returns `{unchanged: all, modified: [], new: [], orphan_keys: []}`
- `run_update()` exits with no changes — no PR opened
- Labels: `ai-update` is still consumed (removed) to prevent re-trigger loops
- **Why:** prevents pointless PRs that would say "no changes"

### Scenario B — One Test Case description was edited in Jira

- `classify_test_cases()` finds the hash mismatch
- `modified` contains that TC
- Flow: `_generate_single_scenario()` creates the new scenario text → `splice_scenario()` replaces just that block
- The step_def file is regenerated WHOLE (the LLM sees the new scenario, omits old step defs if they're only used by removed/modified content)
- Other scenarios in the feature: byte-for-byte preserved (whitespace, comments, indentation untouched)
- PR body: `**Modified scenarios:** SCRUM-29`
- Branch: `auto/<story>-<feat>-update1` (or `-update2` if `-update1` already exists)

### Scenario C — A new Test Case was added to the story

- `classify_test_cases()` puts it in `new`
- Flow: `_generate_single_scenario()` → `append_scenario()` appends to end of feature file
- Step_def file regenerated whole
- Orphan cleanup: no orphans (nothing was removed)
- PR body: `**New scenarios:** SCRUM-32`

### Scenario D — A Test Case was DELETED in Jira

- `classify_test_cases()` puts its key in `orphan_keys`
- Flow:
  1. `remove_scenario()` deletes the block + its marker
  2. Step_def file regenerated whole (LLM doesn't see the deleted scenario → omits its step defs)
  3. **Orphan cleanup runs:**
     - `cleanup_orphans_after_removal()` reads all step_def files + extendable page objects
     - Detects step def functions only referenced by removed scenarios → reported but NOT physically commented out (because the step_def file was regenerated anyway)
     - Detects page-object methods only called from those orphan step defs → commented out with `# AI-ORPHAN: this page-object method appears to no longer be used after scenario(s) SCRUM-31 were removed from Jira. Review before deleting.`
- PR body:
  ```
  **Removed scenarios (no longer in Jira):** SCRUM-31
  **Orphan step definitions detected and removed by regeneration:** `click_recovery_email`, `verify_recovery_sent`
  **Orphan page methods (commented out for human review):** `LoginPage.click_forgot_password`, `LoginPage.is_recovery_email_visible`

  > ⚠️ Review the page object diffs — if a method might be useful for upcoming scenarios, uncomment it. Otherwise delete in a follow-up commit.
  ```

### Scenario E — Mixed: some modified, some new, some deleted

All three operations applied in sequence within a single `run_update()` execution:
1. Removals first (so they don't confuse the LLM about which steps exist)
2. Modifications (in-place splices)
3. Additions (appends)
4. Step_def regeneration once (operates on the fully-spliced feature)
5. Orphan cleanup once

Single PR with all three sections in the body.

### Scenario F — Test Case description edit added a step that needs a new page method

- `modified` contains the TC
- New scenario is generated with the new step
- Step_def file is regenerated → has a new `@when/@then` for the new step
- **BUT page object files are NOT regenerated in `ai-update` mode**
- Result: the new step def will call a page method that doesn't exist
- The final validator (`validate_method_calls_resolvable`) catches this and the PR fails final validation
- **Workaround:** use `ai-regenerate` instead — that DOES regenerate page objects

This is a known limitation. Documented in the PR body: *"If new page-object methods are needed for surviving scenarios, use the `ai-regenerate` label for a full regeneration."*

---

## 12. `ai-regenerate` — what it does, scenario by scenario

**Entry point:** `agents/agent2_coder.py::run()` with `is_regenerate=True` at line 1978

**Selection:**
```yaml
regenerate_selection:
  required_labels: ['ai-processed', 'human-approved', 'ai-regenerate']
  excluded_labels: ['ai-skip', 'ai-update']   # if both set, ai-regenerate wins
```

**Differences from normal mode:**

1. **Dedup bypassed** — `_select_new_test_cases(test_cases, is_regenerate=True)` returns ALL test cases as "new" without checking if they're already covered. Normal mode would skip them as duplicates.
2. **Branch naming** — `_resolve_unused_revision_branch()` adds `-rev2`/`-rev3` suffix. The original PR is preserved as a historical record.
3. **Orphan cleanup ENABLED** — even though normal mode skips it, regenerate mode runs `cleanup_orphans_after_removal()` (block at line 2118) to handle deleted Test Cases.
4. **Label consumption** — `ai-regenerate` removed after success.

**Six scenarios:**

### Scenario A — Same Test Cases as before, just want a fresh rewrite

- All TCs go through full Stage 1 → Stage 2 → validators → commit cycle
- Branch: `auto/<story>-<feat>-rev2`
- New PR opens; old PR stays open (until you close/merge it)
- Orphan cleanup runs but finds nothing (no removed scenarios)
- PR body: standard CodePlan-generated body

### Scenario B — Some Test Cases were deleted in Jira before regen

- LLM doesn't see deleted TCs → doesn't write scenarios for them
- New feature file has only the surviving scenarios
- Step def file rewritten → orphan funcs naturally absent
- **Orphan cleanup runs (new from May 13 fix):**
  - Compares OLD feature (from `main`) with NEW feature
  - Identifies removed Jira keys via `classify_test_cases()`
  - Comments out page methods uniquely used by deleted scenarios
- PR body has an "Orphan code cleanup (regenerate mode)" section at bottom

### Scenario C — Test Cases significantly edited

- LLM rewrites everything based on new descriptions
- Page objects MAY get new methods (LLM is asked to extend, not just preserve)
- Step defs match the new feature exactly
- This is the right mode if descriptions changed a lot and `ai-update` would do too much partial work

### Scenario D — Framework primitives changed (e.g., new base_page helpers added)

- Regenerate causes the LLM to use the new helpers
- Old tests written against old patterns get rewritten to the new patterns
- This is the migration path after a framework upgrade

### Scenario E — Both `ai-update` and `ai-regenerate` set

- Config rule: `update_selection.excluded_labels: ['ai-regenerate']` means update mode won't pick this up
- `regenerate_selection.excluded_labels: ['ai-update']` means regen WILL pick this up (excluded_labels only prevents triggering when ai-update is the ONLY mode — but with regenerate present, regenerate wins)

Wait, let me re-read config:
```yaml
regenerate_selection:
  excluded_labels: [..., 'ai-update']
```
Actually this is the OPPOSITE — regenerate ALSO excludes ai-update. So if both are set:
- `update_selection` excludes the story (ai-regenerate present)
- `regenerate_selection` excludes the story (ai-update present)
- Story is processed by NEITHER mode

**Correct behavior: if you set both, neither runs.** Remove one of them first. This is a config-driven safety against ambiguous intent. (I misstated this in earlier conversation; this is the accurate read of `config.yaml`.)

### Scenario F — Story has multiple feature files (multi-feature story)

- Regenerate mode treats the whole story as a single planning unit
- Stage 1 may produce multiple `FilePlan` entries for multiple feature files
- All regenerated in the same PR
- Branch name uses the first feature name; PR title mentions the story

---

## 13. Other labels in detail

### `ai-ready`

- **Set by:** human, manually in Jira UI
- **Read by:** `agent1_analyst.find_stories_to_process()` via JQL `labels = "ai-ready"`
- **Removed by:** Agent 1 on success (line in `run()`: `jira.remove_label(story_id, "ai-ready")`)
- **Effect:** Triggers Agent 1's analysis flow
- **Idempotency:** Removed after success → won't re-trigger. Manual re-add to re-process.
- **Config:** `agents.agent1_analyst.selection.required_labels: ["ai-ready"]`

### `ai-processed`

- **Set by:** Agent 1 on success
- **Read by:** Agent 2's all three selection modes (`required_labels`)
- **Removed by:** Never (sticky)
- **Effect:** Marker that Agent 1 has completed; prerequisite for Agent 2 to process
- **Idempotency role:** Excluded from Agent 1's `selection.excluded_labels` so it won't re-process

### `human-approved`

- **Set by:** human after reviewing Test Cases in Jira
- **Read by:** Agent 2's all three selection modes
- **Removed by:** Never (sticky)
- **Effect:** Approval gate. Without it, Agent 2 will NOT process the story regardless of other labels.
- **Why mandatory:** Test Cases may be wrong (LLM hallucination, missing edge cases). Human gate prevents bad inputs from cascading into code.

### `ai-coded`

- **Set by:** Agent 2 on success (any mode — normal, update, regenerate)
- **Read by:** Agent 2's NORMAL selection (`excluded_labels: ["ai-coded"]`)
- **Removed by:** Never (sticky)
- **Effect:** Tells normal-mode Agent 2 "already done; don't process again." Implicitly required for `ai-update`/`ai-regenerate` to be meaningful.

### `ai-skip`

- **Set by:** human
- **Read by:** Excluded by ALL agents
- **Removed by:** human (manually)
- **Effect:** Permanent opt-out for a story. Use case: story was created experimentally and shouldn't be auto-processed.

### Cron schedules in workflows

```yaml
# .github/workflows/agent1_analyst.yml
schedule:
  - cron: '*/15 9-18 * * 1-5'   # Every 15 min, Mon-Fri 9-18 UTC

# .github/workflows/agent2_coder.yml
schedule:
  - cron: '*/15 9-18 * * 1-5'   # Same schedule, aligned

# .github/workflows/keep-alive.yml
schedule:
  - cron: '0 2 * * *'           # Daily at 02:00 UTC
```

**Why keep-alive:** GitHub Actions cron is "best effort" on free personal accounts — silently stops firing if the repo has been quiet. Daily nudge re-registers the scheduler.

---

## 14. Validators — the safety net

All validators run in `_validate_generated_files()` (line 1003) before the PR opens. Order matters: cheaper validators first, so expensive AST walks only run if basic checks pass.

| Validator | File | Catches |
|---|---|---|
| `validate_filename_consistency` | test_inventory.py:331 | Kebab-vs-snake_case feature/step_def filename mismatch |
| `validate_feature_file_structure` | test_inventory.py:752 | Orphan Given/When/Then outside any Scenario block |
| `validate_step_definitions_complete` | test_inventory.py:857 | Every feature step has a matching `@given/@when/@then` decorator (cross-file aware) |
| `validate_paths_against_policy` | agent2_coder.py:357 | Reserved path overwrite, extendable misclassification |
| `validate_imports_resolvable` | import_validator.py | `from pages.X import Y` where X or Y doesn't exist |
| `validate_method_calls_resolvable` | method_resolution_validator.py | `page.foo()` where page object class has no `foo` method |

If any validator returns errors, the repair loop (`_attempt_step_coverage_repair`) kicks in for repairable categories (currently: step coverage). For non-repairable errors, the run fails with a detailed error message and the LLM output gets logged for human debugging.

---

## 15. Reuse architecture (config-driven design)

The single biggest design decision in this codebase. **All app-specific knowledge is isolated to 6 files. Zero agent code or unit tests change between projects.**

### Layer 1 — `AppContext` (singleton config loader)

`agents/app_context.py::AppContext.load()` reads `config/config.yaml`, validates, and returns an immutable dataclass. Every agent calls this once at startup.

### Layer 2 — Prompts with placeholders

Agent prompts (`prompts/agent2_coder_plan.md`, `prompts/agent2_coder_generate.md`, etc.) use placeholders like `{app_name}`, `{reference_block}`, `{page_inventory_block}`, `{reserved_block}`, `{extendable_block}`. These are substituted at runtime via Python's `.format()` against the AppContext.

### Layer 3 — App-specific files

| File | Purpose | Touch on new project? |
|---|---|---|
| `config/config.yaml` (`app_under_test` block) | App config | YES |
| `app_inventory/<app>.json` | Pages/selectors catalog | YES |
| `prompts/app_context.md` | Known users, error messages, flows | YES |
| Reference triplet (1 feature + 1 step_def + 1 page_object) | LLM's style baseline | YES |
| `README.md` / `CHANGES.md` | Narrative docs | Optional |

### Layer 4 — Agent files (NEVER touch)

| File | Project-specific? |
|---|---|
| `agents/*.py` (all 11 files) | NO |
| `prompts/agent*.md` (5 files) | NO |
| `pages/base_page.py` | NO (universal helpers) |
| `tests/unit/*.py` (96 tests) | NO |
| `.github/workflows/*.yml` (5 workflows) | NO |

This isolation is enforced by code, not just convention:
- Path policy validator rejects plans touching reserved files
- Prompts use placeholders (config substitution happens before LLM sees it)
- Unit tests use generic fixtures (banking, CMS) — they'd fail if any code had a SauceDemo assumption

---

## 16. Failure modes and recovery

### LLM returns malformed JSON in Stage 1

- `LLMClient.invoke_structured()` raises `pydantic.ValidationError`
- No retry — Stage 1 is short enough that a retry is unlikely to fix structural problems
- The full LLM response is logged. Human debugs.

### LLM hallucinated a non-existent page in the plan

- `validate_paths_against_policy()` doesn't catch this (it only knows reserved/extendable)
- `validate_imports_resolvable` catches it post-Stage-2
- No automatic repair; final validation fails with clear error

### Step coverage validator finds missing decorators

- Repair loop kicks in (up to 4 retries)
- Each retry regenerates ONLY the broken step_def file
- If still failing after 4: PR fails final validation, human debugs

### GitHub branch creation fails (e.g., branch already exists from a manual push)

- `gh.create_branch()` logs warning, doesn't raise
- Commits go to the existing branch
- PR opens on top — may include unexpected pre-existing commits
- Detection: PR base != latest main → flag for human review

### Gemini quota exceeded

- `LLMClient._call_with_quota_check()` raises `QuotaExhaustedError`
- Workflow fails with clear message
- Agent's labels are NOT consumed (since the action didn't complete)
- Next cron run will retry. If quota is daily, retry happens next day.

### Workflow timeout (GitHub Actions 6-hour limit)

- Rare — typical Agent 2 run is 2-5 minutes
- If it happens, partial commits may exist on the branch
- No PR opens (Stage 5 didn't run)
- Recovery: human deletes the partial branch, re-triggers

### `ai-update` triggered but feature file has no markers

- `_locate_feature_file_for_story()` returns None
- `run_update()` returns `{"status": "no_markered_file", "files_generated": 0}`
- `ai-update` label is consumed regardless (prevents re-trigger loops)
- Human guidance in logs: "use `ai-regenerate` to bootstrap markers"

### Both `ai-update` and `ai-regenerate` set

- `update_selection.excluded_labels` includes `ai-regenerate`
- `regenerate_selection.excluded_labels` includes `ai-update`
- Story matches neither → nothing happens
- Cron silently skips
- Human guidance: remove one of the labels

### Test Case description hash collision (cosmically unlikely)

- 8-char SHA-256 → 2^32 hash space → collision probability ~2^-32 per pair
- If it happens: `classify_test_cases()` would think a modified TC is unchanged
- No automated recovery. Use `ai-regenerate` to bypass classification entirely.

---

## Closing notes

This framework is the result of about 6 weeks of iterative refinement against real Gemini 2.5 Pro output. Versions v12 through v18 each fixed a specific LLM failure mode observed in production:

- v12 — JSON parsing brittleness in Stage 1 (Pydantic mode introduced)
- v12e — backtick-fence normalization
- v13/v14 — step coverage validator + repair loop
- v15 — cross-file step reuse (validator was too strict)
- v17 — type contract awareness + locator discipline
- v18 — BasePage helpers + exact phrase matching + parsers.parse quote handling
- May 13 — orphan code cleanup for ai-update AND ai-regenerate

Each was a real production failure, debugged from CI logs, fixed at the prompt or validator level. The 96 unit tests are the regression net. The Pydantic schemas are the type contract. The two-stage LLM call with cross-file context injection is the central engineering decision.

If someone asks you "why is this framework production-grade rather than a demo," the answer is: every line was added because something went wrong, and the test that proves it works is checked in alongside it.
