# Multi-Agent Test Automation Framework — Technical Deep Dive

**Audience:** Senior engineer / SDET / architect peer
**Goal:** Be able to explain, debug, and extend this framework at code level
**Source as of:** main at `3289394` (21 October 2026). Line numbers below are the
`def` lines at that commit; they drift as the code changes, so search by name.

---

## Table of Contents

1. [System overview](#1-system-overview)
2. [Repository layout & line counts](#2-repository-layout--line-counts)
3. [The end-to-end flow](#3-the-end-to-end-flow)
4. [Agent 1 — Test Designer (deep)](#4-agent-1--test-designer-deep)
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
17. [Later additions — sprint scoping & cost instrumentation](#17-later-additions--sprint-scoping--cost-instrumentation)
18. [Agent 0 — Impact Analyst (deep)](#18-agent-0--impact-analyst-deep)
19. [Change stories in Agents 1, 2 and 5](#19-change-stories-in-agents-1-2-and-5)
20. [The Protocols — Tracker and RepoHost](#20-the-protocols--tracker-and-repohost)

---

## 1. System overview

Six agents pipelined together to turn a Jira story into a tested pull request. Agents 1–5 handle every story; Agent 0 (Impact Analyst) runs first for a change story, finding the existing tests it affects (§18). State persists in three external systems:

- **Jira** — workflow state via labels, Test Case issues linked to their story, and marker comments
- **GitHub** — code, branches, PRs, review comments
- **Test artifacts** — JUnit XML, pytest-html report

No central orchestrator. Each agent is an independent Python entry point invoked by a GitHub Actions workflow. State transitions are observable from outside the system. Any agent can be re-run after failure because all its inputs come from durable stores.

---

## 2. Repository layout & line counts

```
agents/
  agent0_impact.py                    685 lines
  agent1_analyst.py                   579 lines
  agent1_impact.py                    248 lines
  agent2_coder.py                    5127 lines
  agent2_impact.py                    246 lines
  agent3_reviewer.py                  924 lines
  agent5_reporter.py                  749 lines

core/
  allure_meta.py                      281 lines
  allure_steps.py                     157 lines
  app_context.py                      394 lines
  board_status.py                     184 lines
  context_update.py                   485 lines
  failure_diagnosis.py                652 lines
  impact_analysis.py                  556 lines
  impact_graph.py                     520 lines
  impact_handover.py                  144 lines
  impact_reconcile.py                 275 lines
  impact_results.py                   162 lines
  impact_review.py                    122 lines
  impact_settings.py                   71 lines
  impact_trace.py                     149 lines
  inventory_proposals.py              106 lines
  json_block.py                        46 lines
  llm_client.py                       829 lines
  onboarding.py                       248 lines
  schemas.py                          361 lines
  test_case_rules.py                  222 lines
  usage_ledger.py                     284 lines

integrations/
  github_client.py                    361 lines
  jira_client.py                      733 lines
  jira_markup.py                       86 lines
  repo_host.py                        222 lines
  tracker.py                          342 lines

validators/
  gherkin_analyzer.py                1908 lines
  import_validator.py                 274 lines
  method_resolution_validator.py     4801 lines
  orphan_cleanup.py                   710 lines
  page_object_contract.py             108 lines

inventory_tools/
  browser.py                          683 lines
  introspect.py                      1562 lines

config/
  __init__.py                         198 lines
  paths.py                             53 lines

scripts/
  agent0_backtest.py                  186 lines
  apply_inventory_proposals.py         84 lines
  backfill_markers.py                 343 lines
  check_inventory_staleness.py        273 lines
  cleanup_artifacts.py                126 lines
  close_merged_story.py               113 lines
  gateway_probe.py                    252 lines
  generate_inventory.py               325 lines
  impact_handover.py                   86 lines
  impact_reconcile.py                  50 lines
  onboarding_check.py                  70 lines
  promote_draft.py                    220 lines
  smoke_test.py                       145 lines
  sweep_stalled_prs.py                181 lines
  verify_locators.py                  629 lines

prompts/
  agent0_adjudicate.md                 24 lines
  agent0_context_notes.md              21 lines
  agent0_seeds.md                      21 lines
  agent0_wording.md                    14 lines
  agent1_analyst.md                    49 lines
  agent1_impact_aware.md               37 lines
  agent2_coder_generate.md           1145 lines
  agent2_coder_plan.md                182 lines
  agent3_reviewer.md                  214 lines
  agent5_reporter.md                   66 lines

pages/base_page.py                 1654 lines  ← BasePage: 86 public helpers injected into the prompt
features/  tests/step_defs/                      — generated and reference tests
tests/unit/                                      — ~2,900 offline framework tests
app_inventory/<app>.json                         — APP-SPECIFIC (pages, selectors, notes, components)
config/config.yaml                               — app config, agent selection rules, Agent 0, board
.github/workflows/                               — 9 workflows: agents 0–5 (Agent 4 + 5 share one), artifact cleanup, inventory health, story-done-on-merge, sweeper
```

**Total Python:** 194 tracked files, about 63,200 lines — about 24,400 in `agents/`, `core/`, `integrations/` and `validators/`, and about 30,900 in `tests/`.

---

## 3. The end-to-end flow

```
[Human creates Jira story, adds acceptance criteria, sets label 'ai-ready']
              ↓
[Cron every 30 min, weekdays 10:00–19:00 IST: Agent 1 polls Jira]
              ↓
[Agent 1 — Test Designer]
  - reads story description + ACs
  - duplicate guard: refuses if the story already owns linked Test Cases
  - LLM produces the fewest Test Cases that cover it (structured JSON via Pydantic)
  - rule check (core/test_case_rules.py), one corrective retry
  - creates each as a Jira Test Case issue, linked to the story (`owns`)
  - parent gets 'ai-processed' label, 'ai-ready' removed
              ↓
[Human reviews Test Cases in Jira, edits if needed, adds 'human-approved']
              ↓
[Same cron window: Agent 2 polls Jira]
              ↓
[Agent 2 — Coder]
  - reads all approved Test Cases
  - Stage 1: LLM plans which files to create (CodePlan JSON)
  - Validates plan against path policy (reserved/extendable)
  - Stage 2: LLM generates each file (feature → page objects → step defs)
  - 29 static checks; the repair loop regenerates only broken files (up to 4 attempts)
  - Injects JIRA marker comments above each scenario
  - Branch: auto/<STORY-KEY>-<feature-name>
  - Commits files, opens PR, adds 'ai-coded' label
              ↓
[GitHub PR opened event]
              ↓
[Agent 3 — Reviewer]
  - fetches PR changed files
  - LLM compares each against reference baseline → ReviewReport
  - dedupes/caps at 10 issues; findings on unchanged lines only advise
  - blocks only for a named failure scenario; a green Agent 4 run refutes it
  - posts review comment on PR
              ↓
[GitHub PR opened/synchronize event — same trigger]
              ↓
[Agent 4 — Runner (pure CI, no Python agent file)]
  - sets up Python 3.13 + Playwright + Chromium
  - runs `pytest tests/unit/` (→ reports/junit-unit.xml), then
    `pytest tests/step_defs/` (→ reports/junit.xml, HTML report, Allure results)
  - uploads artifacts
              ↓
[Same workflow, second job: Agent 5]
              ↓
[Agent 5 — Reporter]
  - parses JUnit XML, scopes it to the step files this PR changed
  - lists failures outside the story separately (verdict follows the PR check)
  - LLM drafts a prose summary; Python adds the facts and the cost table
  - posts to Jira parent story as comment, adds 'tests-run'
  - change story: one result line per owning story + Agent 0 prediction score
              ↓
[Human reviews PR + Jira comment + decides merge]
```

**Iteration loops (after initial PR):**

- **Test Case description edited in Jira:** human adds `ai-update` label → Agent 2's `run_update()` does surgical splice
- **Want full rewrite:** human adds `ai-regenerate` label → Agent 2's `run(is_regenerate=True)` rewrites everything on `-rev2` branch
- **Story changes existing behaviour:** human adds `impact-check` → Agent 0 (§18), an Impact Review, then Agents 1/2 revise the owners' tests (§19)

---

## 4. Agent 1 — Test Designer (deep)

**File:** `agents/agent1_analyst.py` (578 lines); impact-aware mode in `agents/agent1_impact.py` (§19)
**Workflow:** `.github/workflows/agent1_analyst.yml`
**Trigger:** Cron every 30 min, weekdays 10:00–19:00 IST (04:30–13:30 UTC), or manual `workflow_dispatch`

### Key functions

#### `run(story_id: str, dry_run: bool = False) -> dict` (line 209)

The single-story entry point. Steps:

1. **Validate config** — `validate_required_env()` from `config/__init__.py` raises `MissingEnvVarError` naming every missing variable (`JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, …). Then the **duplicate guard**: if the story already owns linked Test Cases, the run refuses and says whether the last run finished or was interrupted.
2. **Fetch story** — `JiraClient().get_story(story_id)` returns a dict with `key`, `summary`, `description`, `status`, `labels` and `components` (acceptance criteria live in the description).
3. **Build prompt** — concatenates:
   - System: `prompts/agent1_analyst.md` (48 lines, generic)
   - App context: `prompts/app_context/core.md` plus the module for each of the story's Jira Components (all modules when none match)
   - Story content
4. **Invoke LLM with structured schema** — `LLMClient().invoke_structured(system_prompt, user_prompt, output_schema=TestCaseList)`. This injects the Pydantic JSON schema into the prompt and validates the reply (provider-agnostic structured output) to force JSON conforming to `TestCaseList` (defined in `core/schemas.py`, line 32) which contains:
   ```python
   class TestCaseList(BaseModel):
       story_summary: str
       test_cases: list[TestCase]   # each: title, description, priority, test_type,
                                    # preconditions, steps, expected_outcome, test_data
   ```
   No string parsing. If the LLM returns invalid JSON, it gets one repair attempt with the error fed back, then `ValueError`. The draft is then checked against `core/test_case_rules.py`; a failing draft goes back once with the problems listed, and a second failure writes nothing.
5. **Create Jira Test Cases** — for each TC: `JiraClient().create_test_case(tc, parent_story_key=story_id, components=...)` — the story's Jira Components carried over when it has some (a project that rejects them still gets the test case, created without them) — which calls `_format_test_case_description()` to format it as Jira wiki markup and then `_link_to_story()` to add the ownership link (`link_types.owns` in config).
6. **Label transitions** — `jira.add_label(story_id, "ai-processed")` then `jira.remove_label(story_id, "ai-ready")`. Order matters: add first (so even if remove fails, the idempotency marker is set).

#### `--scan` mode (in `main()`, line 471)

Calls `JiraClient().find_stories_to_process(selection_config)` which JQL-queries Jira:
```
project = SCRUM AND issuetype = Story AND status in ("To Do", "In Progress")
  AND labels = "ai-ready" AND labels NOT IN ("ai-processed", "ai-skip",
  "impact-check", "impact-proposed") [AND sprint scope, when configured]
```

Then loops over results, calling `run(story_id)` for each. Capped at `max_stories_per_run: 2` (from config) so a mislabel disaster is bounded.

### Why a Pydantic schema, not free text

- Eliminates JSON parsing brittleness
- Forces consistent Test Case structure (each TC has exactly: title, description, priority, type, preconditions, ordered steps, expected outcome, optional test data)
- LLM can't "forget" the schema mid-output
- A schema violation is a hard error (LLMClient raises), not a silent bug

---

## 5. Agent 2 — Coder (deep, longest section)

**File:** `agents/agent2_coder.py` (5127 lines — the heaviest); change-story splice in `agents/agent2_impact.py` (§19)
**Workflow:** `.github/workflows/agent2_coder.yml`
**Trigger:** Cron (same schedule as Agent 1) or `workflow_dispatch`

This is where the framework's complexity lives. Three entry points based on Jira labels:

| Mode | Entry function (line) | When |
|---|---|---|
| Normal (first-time) | `run(is_regenerate=False)` (4267) | First time a story is coded |
| Regenerate (full rewrite) | `run(is_regenerate=True)` (4267) | Story has `ai-regenerate` label |
| Update (surgical splice) | `run_update()` (3841) | Story has `ai-update` label |

`main()` (line 4929) dispatches to the correct entry based on labels found during `--scan`.

### 5.1 Feature-file parsing primitives (from line 145)

These are the foundations everything else builds on.

#### `_JIRA_MARKER_RE` (line 149)

```python
_KEY = r"[A-Z][A-Z0-9_]*-\d+"
_JIRA_MARKER_RE = re.compile(
    rf"^\s*#\s*JIRA:\s*({_KEY})\s*\(hash:\s*([0-9a-f]{{8}})\s*\)"
    rf"(?:\s+owner:\s*({_KEY}))?"
    rf"(?:\s+impacted-by:\s*({_KEY}(?:\s*,\s*{_KEY})*))?\s*$",
    re.IGNORECASE,
)
```

Parses marker comments like `# JIRA: PROJ-29 (hash: a4f9c2e1)`, optionally followed by `owner: PROJ-12` and `impacted-by: PROJ-40,PROJ-41` (Agent 0 change stories). Strict 8-char hex hash and Jira key format, to prevent false matches; markers without the optional parts parse exactly as before. `format_marker()` writes them.

#### `compute_description_hash(description: str) -> str` (line 166)

```python
normalized = re.sub(r"\s+", " ", description).strip()
return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
```

First 8 chars of SHA-256 of the whitespace-normalised description, so extra blank lines or trailing spaces in Jira do not count as an edit. Used to detect when a Jira Test Case description has been edited. Stored in the feature file marker so we can compare without calling Jira again.

#### `class ScenarioBlock` (line 223)

```python
class ScenarioBlock:
    kind: str               # 'header' | 'background' | 'scenario'
    lines: list[str]        # raw lines including newlines
    jira_key: Optional[str] # parsed from preceding marker comment
    jira_hash: Optional[str]
    marker_line_index: Optional[int]
    owner: Optional[str]    # optional marker field (change stories)
    impacted_by: tuple      # optional marker field (change stories)
    def text(self) -> str:  # rejoin lines into a string
```

The atomic unit of feature-file surgery. Each scenario block remembers its Jira identity.

#### `parse_feature_file(content: str) -> tuple[list[str], list[ScenarioBlock]]` (line 358)

The most critical parser in the file. Walks the content line by line:

1. Collects header lines (everything before the first `Scenario:` or `Background:`)
2. For each new block start (`Background:` or `Scenario:`), looks at the previous lines for `# JIRA:` marker
3. Builds `ScenarioBlock` objects with `jira_key`, `jira_hash` populated if marker found

Used by `classify_test_cases`, `splice_scenario`, the step-def splice in `run_update`, and the orphan cleanup module.

#### `splice_scenario(original, jira_key, new_scenario_text, new_hash)` (line 394)

Surgical replacement. Finds the block whose `jira_key` matches; replaces its text with `new_scenario_text` (which must itself contain a marker for the same key); raises if the new text claims a different key (defense against LLM scrambling identities). All OTHER blocks are preserved byte-for-byte (newlines, indentation, comments, blank lines).

#### `remove_scenario(content, jira_key)` (line 474)

Removes the block AND its preceding marker comment in one pass. Returns content with the gap closed.

#### `classify_test_cases(test_cases, feature_content)` (line 490)

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

### 5.2 Path policy validator

#### `validate_paths_against_policy(plan, ctx, protected_files=None)` (line 682)

Two-tier file rule enforced post-Stage-1:

| Tier | Definition | Plan rule |
|---|---|---|
| **Reserved** | `app_under_test.reserved_paths` (reference files) | NEVER appear in plan |
| **Extendable** | `app_under_test.extendable_paths` plus every committed page object found under `pages/` (`auto_extend_page_objects: true`, the default) | May appear, MUST have `is_new_file=False` |
| **New** | Everything else | May appear, `is_new_file=True` for fresh files |

A change-story run also passes `protected_files` — feature and step-definition files other stories own — and the plan may not generate those (they are edited only by splicing). Raises `ValueError` with explicit guidance if the LLM hallucinates "let me rewrite login_page.py from scratch." This is the gate that protects your gold-standard reference files from being overwritten.

### 5.3 Cross-file context injection

#### `_build_sibling_page_object_context(already_generated)` (line 1210)

Critical for cross-file consistency. When generating a step-def file (e.g. `tests/step_defs/test_product_sorting.py`), the page object `inventory_page.py` has typically already been generated in the same run. This function:

1. Walks `already_generated` for files matching `pages/*.py`
2. `ast.parse()` each one
3. Extracts class names and method signatures (e.g., `sort_products_by(option_label: str) -> None`)
4. Returns a markdown block listing them

Injected into the Stage 2 prompt as "the following page-object classes were generated earlier in this run." Without this, the LLM hallucinates method names — `click_logout()` when the page object actually defined `click_logout_link()`.

#### `_sort_files_for_generation(files_to_create)` (line 1290)

Reorders the plan so page objects come BEFORE step definitions. Sequence matters because of the context injection above. New feature files come first too.

### 5.4 The two-stage LLM design

#### Stage 1 — `build_plan(test_cases, ctx, references, page_inventory)` (line 1711)

Inputs:
- `test_cases` — the Jira Test Cases (from `load_test_cases_for_story`)
- `ctx` — `AppContext` with app name, paths
- `references` — dict of reference file contents (loaded once)
- `page_inventory` — raw JSON string from `app_inventory/<app>.json`

Calls `LLMClient.invoke_structured(prompt, schema=CodePlan)`. Returns a `CodePlan` (defined in `schemas.py:134`):

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
    file_type: str             # 'feature' | 'step_definitions' | 'page_object' | 'other'
    purpose: str               # human-readable
    is_new_file: bool
    related_test_cases: list[str]  # Jira keys this file addresses
```

The plan is a contract. Path policy validation runs immediately after this.

#### Stage 2 — `generate_file_content(llm, file_plan, plan, test_cases, references, page_inventory, ctx, validator_feedback, previous_attempt, already_generated, existing_page_objects)` (line 2004)

Called once per file in the plan. Returns the file's content as a string. Internally:

1. Loads the right prompt template (`agent2_coder_generate.md`)
2. Fills placeholders with `str.replace` (not `.format()`, so braces in code samples are safe): `{app_name}`, `{file_path}`, `{file_type}`, `{file_purpose}`, `{feature_name}`, `{existing_file_block}`, `{validator_feedback_block}`, `{sibling_page_objects_block}`, `{authoritative_steps_block}`, `{base_page_helpers_block}`, `{starting_state_block}`, the three reference paths and contents, `{page_inventory_json}` and `{test_cases_text}` (only this file's related Test Cases)
3. For extendable files, reads the existing content from disk so the LLM can ADD methods without losing existing ones
4. Calls `LLMClient.invoke_text(system, user)` — text mode (not structured) because output is Python/Gherkin source
5. `extract_code_from_response()` (line 764) strips markdown fences. Includes the v12e fix:
   ```python
   response_text = re.sub(r"`{4,}", "```", response_text)
   ```
   Pro occasionally emits 6-backtick fences; this normalizes to 3 so the code-extraction regex doesn't fail.

### 5.5 The repair loop

#### `_attempt_step_coverage_repair(generated_files, llm, plan, ...)` (line 2767)

After Stage 2 finishes, the repairable checks run. The name is historical: the loop covers 25 repairable checks (step coverage, imports, method resolution, selectors, duplicate steps and the other rules in `_collect_repairable_errors()`, line 2647), not only step coverage. Up to `max_retries=4` attempts:

1. Collect errors via `_collect_repairable_errors(generated_files)`
2. Route each error to the generated file it names — `_route_to_generated_file()` (line 2741). An error that names no file in the batch is never dropped silently (#193); `tests/unit/test_every_repairable_error_is_routed.py` checks every rule's message format routes
3. For each broken file: call `generate_file_content()` again with `validator_feedback` and `previous_attempt`; keep the new content unless `_is_degraded_regeneration()` says it is a truncated stub
4. Loop

Early stops, so a non-converging model does not burn tokens:
- **No progress** — the error set comes back verbatim
- **Not converging** — from attempt 3, the count did not fall *and* the same rule is still firing (a different rule at the same count is progress)
- Quota or truncation errors re-raise rather than being retried

The repair loop is cheap because only the broken file is regenerated, not the full plan. Whatever remains goes to the final gate (§14).

### 5.6 JIRA marker injection

#### `_ensure_jira_markers_on_feature_files(generated_files, test_cases)` (line 3064)

Runs after Stage 2 completes. The LLM is unreliable at consistent comment placement, so markers are inserted post-hoc.

#### `_inject_markers_into_feature(content, test_cases)` (line 3189)

The matching algorithm:

1. Parse the generated feature into `ScenarioBlock`s
2. For each Test Case, find its matching scenario by:
   - Token-overlap similarity (`_title_similarity`) between Jira TC summary and Gherkin scenario title
   - Falls back to positional matching if titles diverge (LLM paraphrased)
3. Insert `# JIRA: KEY (hash: 8char)` comment line on top of each matched scenario, preserving indentation
4. Idempotent: if a marker already exists for that key, skip

### 5.7 The `run()` flow (line 4267) — normal + regenerate mode

```python
def run(story_id, dry_run=False, is_regenerate=False) -> dict:
    # 1. INPUT — load Jira story + Test Cases
    # 1b. DEDUP — skipped in regenerate mode
    # 1c. IN FLIGHT — core/in_flight.snapshot(); a scenario another open PR
    #     already adds → _wait_for_in_flight() (status waiting_for_open_pr)
    # 2. CONTEXT — load reference files, page inventory, prompts
    # 3. STAGE 1: PLAN — build_plan() → CodePlan
    # 3b. PATH POLICY — validate_paths_against_policy()
    #     IN FLIGHT, files — a file the plan writes that another open PR
    #     changes → _wait_for_in_flight(); nothing generated, labels kept
    # 4. STAGE 2: GENERATE — loop over plan.files_to_create
    #    - _sort_files_for_generation() orders page_objects before step_defs
    #    - generate_file_content() per file with already_generated context
    # 4b. SELF-CORRECTING REPAIR — _attempt_step_coverage_repair() up to 4 retries
    # 4d. INJECT JIRA MARKERS — _ensure_jira_markers_on_feature_files()
    # 4d-bis. CHANGE-STORY SPLICE — approved scenarios spliced into the
    #         owners' feature files (change stories only, §19)
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

### 5.8 The `run_update()` flow (line 3841) — surgical splice

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
    # 6. Update the step_def file: _splice_step_defs_incremental()
    #    - "unchanged": existing functions already cover the feature (0 calls)
    #    - "spliced": only the new step functions are written and appended,
    #      checked against the real page objects
    #    - "regenerated": falls back to _regenerate_step_defs_whole() on any
    #      ambiguity
    # 7. Orphan cleanup: cleanup_orphans_after_removal()
    #    - Reads all step_def files via gh.list_files_in_directory()
    #    - Reads page object files from extendable_paths (incl. auto-discovered)
    #    - Comments out dead page methods with # AI-ORPHAN: banners
    # 7b. comment_out_step_defs_unused_by() — step functions this update
    #    left unused (removed or modified scenarios)
    # 8. Validate, branch (-updateN suffix via _find_unused_update_branch),
    #    commit, open PR
    # 9. jira.remove_label('ai-update')  # one-shot consumed
```

### 5.9 Auxiliary helpers

| Function | Line | Purpose |
|---|---|---|
| `_find_unused_update_branch()` | 3356 | Walks `auto/<story>-<feat>-update1`, `-update2`, etc. until finding one that doesn't exist on GitHub |
| `_resolve_unused_revision_branch()` | 3049 | Same logic but for `-rev2`, `-rev3` (regenerate mode). Preserves the original PR as historical record. |
| `_locate_feature_file_for_story()` | 3364 | For update mode: scans `features/` for a file whose markers reference the Jira keys. Returns the file path. |
| `_generate_single_scenario()` | 3391 | Smaller-scoped LLM call for `run_update`'s modified/new scenarios. Returns ONE scenario block's text with marker. |
| `_splice_step_defs_incremental()` | 3696 | `run_update`'s step-def update: appends only the new step functions, keeping passing ones byte-for-byte; returns `(content, mode)` |
| `_regenerate_step_defs_whole()` | 3440 | Fallback when the splice is ambiguous: the whole step-def file is regenerated from the spliced feature. |
| `_print_dry_run_preview()` | 3014 | Prints planned actions without committing. Used by `--dry-run` flag. |

### 5.10 Tests for Agent 2

| Test file | Tests | Covers |
|---|---|---|
| `tests/unit/test_incremental_update.py` | 38 | All ScenarioBlock parsing, splice/append/remove, classify_test_cases, marker injection, v12e backtick normalization |
| `tests/unit/test_repair_loop.py` | 37 | The repair loop logic with mocked validators |
| `tests/unit/test_orphan_cleanup.py` | 20 | Orphan detection across banking + CMS domains |
| `tests/unit/test_validators.py` | 120 | All validators (filename consistency, feature structure, step completeness, imports, method resolution) |

215 tests in these four files. The whole unit suite (~2,900 tests, about 2 minutes, fully offline) covers much more — splice grounding (`test_splice_grounding.py`), the validator gate, Agent 0 and the Protocols among them.

---

## 6. Agent 3 — Reviewer (deep)

**File:** `agents/agent3_reviewer.py` (923 lines)
**Workflow:** `.github/workflows/agent3-reviewer.yml`
**Trigger:** GitHub `pull_request` event (opened, synchronize, reopened) — NOT Jira-driven. The workflow checks out the BASE branch, so the reviewer code, prompt and references are always those on `main`.

### Key functions

#### `run(pr_number: int, dry_run: bool = False) -> dict` (line 745)

1. **Fetch PR metadata** via `gh.get_pr_metadata(pr_number)`: returns dict with `number`, `title`, `body`, `state`, `head_branch`, `base_branch`, `author`, `url`
2. **Fetch changed files** via `gh.get_pr_changed_files(pr_number)`: list of dicts with `filename`, `status` (added/modified/removed/renamed), `additions`, `deletions`, `patch` (unified diff) and `content` (full file, fetched for every file not removed)
3. **No type filter** — every changed file goes to the model, with its full content and its patch.
4. **Build prompt** — concatenates:
   - System: `prompts/agent3_reviewer.md`
   - PR metadata
   - Reference files block (from `ctx.load_reference_files()`)
   - `format_changed_files_for_prompt(files)` (line 643) — renders each file's name, status, patch as a markdown section
5. **Invoke LLM with structured schema**:
   ```python
   report = llm.invoke_structured(prompt, schema=ReviewReport)
   ```
   `ReviewReport` (`core/schemas.py`, line 244) contains:
   ```python
   class ReviewReport(BaseModel):
       pr_number: int
       overall_verdict: Literal["approve", "request_changes", "comment"]
       summary: str
       issues: list[ReviewIssue]   # severity, file_path, line_number, issue_type, description,
                                   # suggested_fix, failure_scenario, test_outcome
       style_compliance: bool
       type_hints_present: bool
       no_hardcoded_waits: bool
       pom_compliant: bool
       coverage_complete: bool
   ```
6. **Post-process** via `postprocess_review()`: `dedupe_and_cap_issues(report, max_issues=MAX_ISSUES)` (line 124, `MAX_ISSUES = 10`) normalizes and deduplicates descriptions and caps the list; unsubstantiated findings are withdrawn; findings on lines this PR did not change are lowered to advice; the verdict is derived from what remains. A blocking finding needs a named failure scenario. When the only blocker is a predicted test failure, the review waits (up to 8 minutes) for Agent 4's result on the same commit, and a green run lowers the block.
7. **Format as markdown** via `format_review_as_markdown(report)` (line 665). Issues grouped by severity (blocking/major/minor/info), each with file:line link.
8. **Post comment** via `gh.post_pr_comment(pr_number, markdown)`. Each run posts a new conversation comment; a new push re-runs the review, so the latest comment is the current one.

### Why structured output

A free-form text review is a wall of unstructured prose that can't be deduplicated, capped, or filtered. The `ReviewReport` schema gives:
- Programmatic dedup
- Severity sorting
- Per-issue file:line attribution
- Consistent rendering across runs

### `resolve_pr_number(cli_arg_pr)` (line 74)

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
3b. **Wait for earlier PRs' browser runs** (pull request only): `scripts/e2e_turn.py` lists unfinished runs of OTHER PRs with a lower run id; the step polls every 30 s, up to `MAX_WAIT_SECONDS` (900), then proceeds; it never waits if the runs cannot be read. A shared concurrency group is not used because GitHub cancels a pending run when a newer one queues, and the sweeper reads a cancelled run as a stalled PR. The job's timeout is 30 minutes to allow for the wait.
4. **Run tests** — two steps:
   ```bash
   pytest tests/unit/ --junit-xml=reports/junit-unit.xml -v        # framework gate, no browser
   pytest tests/step_defs/ -v \
     --html=reports/pytest-report.html --self-contained-html \
     --junit-xml=reports/junit.xml                                 # app E2E (Playwright BDD)
   ```
   The E2E step runs `if: always()`, so a failed unit gate still yields E2E signal on a PR. On a framework-only `push` to `main`, the unit step is the whole job. On a pull request, the `pr_changes` step skips the browser (and the report job) when every changed file is one no test reads — `prompts/`, `docs/`, Markdown (`core/test_runtime.py`, fail-open); Agent 3 then takes no runner result as evidence. Only `reports/junit.xml` (the app tests) reaches Agent 5.
5. **Upload artifacts** via `actions/upload-artifact@v4`: pytest-html, junit XML, Allure results
6. **Inline Python step** parses `junit.xml` and writes a markdown table to `$GITHUB_STEP_SUMMARY` — appears on the PR check page
7. **Job 2: Agent 5** — the `report` job in the same workflow, with `needs: test`

### Why combined Agent 4 + Agent 5 in one workflow

Performance: Agent 5 needs Agent 4's JUnit XML. Combining them avoids artifact upload + re-download between separate workflow runs. The two appear as separate "checks" on the PR.

---

## 8. Agent 5 — Reporter (deep)

**File:** `agents/agent5_reporter.py` (748 lines)
**Workflow:** Same as Agent 4 (second job)
**Trigger:** `needs: test` in `agent4_runner.yml` (job `report`)

### Key functions

#### `parse_junit_xml(junit_path: Path) -> RunReport` (line 74)

Parses pytest's JUnit XML output. Returns a `RunReport` (`core/schemas.py`, line 321):

```python
class RunReport(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    results: list[TestResult]  # name, classname, status, duration_seconds, failure_message
    pr_number: Optional[int]
    pr_url: Optional[str]
    workflow_run_url: Optional[str]
    html_report_url: Optional[str]
    commit_sha: Optional[str]
```

Handles classic xunit format AND pytest's extension (skipped, errors as separate elements).

#### `gather_ci_context(report, cli_pr)` (line 171)

Fills in `pr_number`, `pr_url`, `workflow_run_url`, `html_report_url` and `commit_sha` from the workflow's env vars (`GITHUB_REPOSITORY`, `GITHUB_RUN_ID`, `GITHUB_SHA`, the PR from `GITHUB_EVENT_PATH` or `PR_NUMBER`), keeping any value the report already has.

#### `resolve_story_key(cli_arg, pr_branch)` (line 431)

Priority: the `--story` CLI arg, then `JIRA_STORY_KEY`, then the first Jira key in the PR branch name (`config.extract_jira_key`, any prefix). A key that turns out to be a Test Case is escalated to its parent Story. Raises if nothing resolves.

#### `run(story_key, reports_dir, dry_run, cli_pr)` (line 502)

1. Parse JUnit XML
2. Gather CI context
3. Load `prompts/agent5_reporter.md`
4. Scope the report to the step-def modules this PR added or changed; failures outside that scope are kept and listed separately, and the verdict is `failed` unless everything on the branch passed, so the comment agrees with the PR check.
5. Invoke LLM with structured schema `JiraCommentDraft` (`core/schemas.py`, line 342) — `title` and `body_markdown` — for the prose about the story's own tests only.
6. Compose final comment via `build_final_comment(prose_body, report)` (line 239). Appends the deterministic test-result table, the outside failures and the end-to-end cost table.
7. Post to Jira parent story via `jira.add_comment(story_key, comment)` and add `tests-run`. No duplicate check: a re-run posts another comment.
8. Change story: `core.impact_results.post_owner_results()` puts one result line on each story owning a revised test, and `record_prediction_outcome()` scores Agent 0's prediction against what changed and failed (shadow mode too).

### Idempotency design

There is none, by design (see the module docstring): a re-run of the workflow posts a second report. Each report is tied to its run and commit, so a duplicate is visible and harmless, and a skipped report on a real re-run would be worse. `add_label` itself is idempotent.

---

## 9. Cross-cutting modules

### 9.1 `core/app_context.py` (393 lines) — the reuse enabler

#### `class AppContext` (line 189)

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

- `load(cls, config_path=None)` (line 209) — class method that reads config.yaml, validates required fields, returns an AppContext
- `reference_file_paths` (line 286) — returns `{'feature': Path, 'step_def': Path, 'page_object': Path}`
- `inventory_path` (line 294) — Path object for the inventory JSON
- `reserved_paths_normalized()` (line 298) — `set[str]` of paths with forward slashes for portable comparison
- `extendable_paths_normalized()` (line 303) — same for extendable paths
- `load_reference_files()` (line 316) — reads all three reference files, returns `{'feature': str, 'step_def': str, 'page_object': str}`
- `load_page_inventory_json()` (line 338) — reads inventory JSON file, returns raw string for prompt injection

`extendable_paths` holds the configured list plus every committed page object discovered under `pages/` (unless `auto_extend_page_objects: false`), minus reserved files. This is the single point where app config is loaded. Every agent calls `AppContext.load()` once.

### 9.2 `validators/gherkin_analyzer.py` (1907 lines) — feature/step matching engine (renamed from test_inventory.py)

The hardest computation in the codebase. Used by:
- Agent 2's repair loop and final validation
- `filter_duplicate_test_cases` (title-overlap helper). Agent 2's own dedup is marker first, title second: `classify_against_index()` in `agents/agent2_coder.py`
- Orphan cleanup's step matching

#### `_extract_feature_steps(feature_content) -> list[tuple[str, str]]` (line 603)

Walks a Gherkin file and returns `[(keyword, phrase), ...]` for every step. Handles:

- `And`/`But` keyword inheritance — resolves to the previous concrete keyword (Given/When/Then) since pytest-bdd dispatches that way
- Background steps included (they need step defs too)
- Scenario Outline `Examples:` tables stripped (they're data, not steps)
- Comments and blank lines skipped

#### `_extract_decorator_phrases(step_def_content) -> list[tuple[str, str, str]]` (line 660)

Walks a Python step-def file and returns `[(kind, phrase, parser_type), ...]`:

- `kind` ∈ `'given'`, `'when'`, `'then'`
- `parser_type` ∈ `'string'` (bare string decorator), `'parse'` (parsers.parse), `'cfparse'` (parsers.cfparse), `'re'` (parsers.re)

Uses regex `_DECORATOR_PARSER_PATTERN` and `_DECORATOR_STRING_PATTERN`. Critical: when a `parsers.parse(...)` is found, the bare-string pattern is skipped at that location (so the same decorator isn't counted twice).

#### `_phrase_matches(feature_phrase, decorator_phrase, parser_type) -> bool` (line 708)

THE matching function. Uses pytest-bdd's actual runtime backends:

- `'string'`: exact equality after `.strip()`
- `'parse'` / `'cfparse'`: the `parse` library (`from parse import parse`)
- `'re'`: Python `re.fullmatch`

This closes the gap that caused PR #9: an earlier validator was permissive about empty quoted values, but the `parse` library refuses to match them at runtime. By using the SAME backend pytest-bdd uses, the validator's verdict matches runtime behavior exactly.

#### `validate_step_definitions_complete(generated_files, project_root=None)` (line 1124)

The cross-file step coverage validator. For every step in every generated feature file:
1. Is there a matching `@given/@when/@then` decorator in the paired step def file?
2. If not, it accepts a match only in a `conftest.py` that applies to the module (`tests/step_defs/conftest.py`, `tests/conftest.py`; the batch's copy wins over disk). Sibling step-def modules — committed or in the same batch — never count, because pytest-bdd step definitions are module-scoped: exactly what runtime resolves
3. If still not, return an error string with diagnostic info (which file, which step, what decorator was almost-matching)

Returns `list[str]` of errors. Empty list = all good.

#### `validate_filename_consistency(generated_files)` (line 334)

Catches the PR #7 regression: `features/sort-products.feature` paired with `tests/step_defs/test_sort_products.py` — kebab-case feature filename vs snake_case step-def filename. The feature_path() call in step_defs assumes the snake_case form.

Includes `_try_autocorrect_feature_name()` (line 484) which can fix simple mismatches automatically in-flight.

#### `validate_feature_file_structure(generated_files)` (line 1019)

Catches orphan Given/When/Then lines outside any Scenario block. pytest-bdd would fail at collection time with a cryptic error; this validator catches it pre-commit with a clear message.

### 9.3 `validators/orphan_cleanup.py` (710 lines) — dead code detection

Implements the cleanup described in §5.8/§5.7. Detailed earlier; key functions:

| Function | Line | Purpose |
|---|---|---|
| `extract_steps_in_removed_scenarios()` | 77 | Returns `[(kw, phrase), ...]` for steps inside deleted Jira Test Cases' scenario blocks. Uses lazy import of `parse_feature_file` to avoid circular dep. |
| `find_orphan_step_defs()` | 114 | AST walks each step def file. For each function with a step decorator: matches a removed step? matches a surviving step? → returns OrphanStepDef list |
| `find_orphan_page_methods()` | 293 | Two-pass AST walk. Pass 1: collect method names called from orphan step defs. Pass 2: collect method names called from surviving step defs. Orphans = pass1 \ pass2. Excludes private methods (`_*`), excludes reserved files (`pages/base_page.py`). |
| `comment_out_orphan_page_methods()` | 420 | Walks file lines, prefixes orphan func lines with `# `, prepends `# AI-ORPHAN:` banner with the removed Jira keys |
| `comment_out_orphan_step_defs()` | 399 | Same banner approach for step functions no surviving scenario uses |
| `cleanup_orphans_after_removal()` | 502 | Top-level orchestrator. Called from `run_update()`, `run()` regenerate mode and the change-story owner splice (`agents/agent2_impact.py`); a file the cleanup changed is committed even when no step was added. Both wrapped in try/except so cleanup failure doesn't block the PR. |
| `comment_out_step_defs_unused_by()` | 615 | Comments out step functions that a given feature no longer uses, matching with the same parser backends as runtime |

Tests: 20 unit tests in `tests/unit/test_orphan_cleanup.py` using banking AND CMS fixtures (no content from any real application) to prove app-agnosticism.

### 9.4 `core/llm_client.py` (828 lines)

#### `class LLMClient` (line 549)

Wraps any OpenAI-compatible LLM API via `langchain-openai`. Configuration from env vars: `OPENAI_API_KEY`, `OPENAI_API_BASE`, `LLM_MODEL`; `LLM_MODEL_LIGHT` (optional) is a cheaper model the workflows give Agents 1 and 5.

#### Key methods

- `invoke_structured(system, user, output_schema)` (line 592) — returns an instance of `output_schema` (a Pydantic class). Provider-agnostic: the model's JSON schema is appended to the prompt and the raw reply is parsed with Pydantic — no tool-calling or `response_format` needed. One repair retry with the validation error fed back (`structured-repair:<Schema>`), then `ValueError`.
- `invoke_text(system, user, cache_prefix=False)` (line 719) — plain text generation for code. With `cache_prefix`, the static system text is sent as a cacheable prefix; `_record_usage()` logs cache writes and reads.
- `_call_with_quota_check()` (line 577) — wraps SDK calls. Detects quota-exceeded errors via `_is_quota_error()` (line 67) and raises `QuotaExhaustedError` with a clear message.

#### `_code_gen_max_output_tokens(model_name)` (line 52)

Returns the output-token cap for code generation: `LLM_CODE_GEN_MAX_TOKENS` if set, else 16,384. A reply that hits the cap raises `OutputTruncatedError` rather than committing half a file.

### 9.5 `integrations/jira_client.py` (732 lines) — the Jira adapter of the `Tracker` Protocol

Wraps the `jira` Python SDK. Methods:

| Method | Line | Purpose |
|---|---|---|
| `get_story(issue_key)` | 133 | Returns dict with key, summary, description, status, labels, components |
| `find_stories_to_process(selection_config)` | 152 | Builds JQL from config dict, returns matching stories |
| `create_test_case(test_case, parent_story_key)` | 252 | Creates a `Test Case` issue. Uses `_format_test_case_description` to render Jira wiki markup |
| `_link_to_story(test_case_key, story_key)` | 287 | Adds the ownership link (`link_types.owns` in config); a failed link is re-raised, because Agent 2 finds test cases by link |
| `add_label(issue_key, label)` | 450 | Idempotent — checks existing labels before adding |
| `remove_label(issue_key, label)` | 461 | Idempotent — skips if label not present |
| `add_comment(issue_key, body)` | 508 | Plain markdown comment |
| `get_parent_story_key(issue_key)` | 696 | For Test Case → parent Story lookup |

### 9.6 `integrations/github_client.py` (360 lines) — the GitHub adapter of the `RepoHost` Protocol

Wraps PyGithub. Methods used across agents:

| Method | Line | Purpose |
|---|---|---|
| `create_branch(name, from_branch)` | 46 | Creates from main, idempotent (logs if exists) |
| `branch_exists(name)` | 192 | Used by `_find_unused_update_branch` and `_resolve_unused_revision_branch` |
| `create_or_update_file()` | 215 | Single-file commit. Detects new vs existing via try/except. Used in commit loops. |
| `get_file_content(path, branch)` | 245 | Reads file content for incremental update flow |
| `list_files_in_directory(path, branch)` | 250 | For orphan cleanup to find sibling step_def files. Returns repo-relative paths, empty list on failure (defensive). |
| `open_pull_request()` | 270 | Idempotent — if a PR exists for the branch, returns its URL instead of erroring |
| `get_pr_metadata(pr_number)` | 300 | Used by Agent 3 |
| `get_pr_changed_files(pr_number)` | 314 | Used by Agent 3 — unified diff patches plus full content |
| `post_pr_comment(pr_number, body)` | 350 | Posts a new conversation comment each call |

### 9.7 `core/schemas.py` (360 lines) — every Pydantic model (21 classes)

| Class | Used by | Purpose |
|---|---|---|
| `TestStep` | Agent 1 | One step inside a Test Case (Given/When/Then text) |
| `TestCase` | Agent 1 | Single test case (title, description, priority, test_type, preconditions, steps, expected_outcome, test_data) |
| `TestCaseList` | Agent 1 | Wrapper — story_summary plus the list of test cases |
| `TestCaseRevision` | Agent 1 (impact-aware) | A revised existing test case with a one-line change note |
| `ImpactAwareDraft` | Agent 1 (impact-aware) | Revisions plus new test cases for a change story |
| `ChangeSeeds` | Agent 0 | change_type, behaviours, element_keys, components extracted from the story |
| `WordingChange` / `WordingChanges` | Agent 0 | Inventory wording updates proposed by the context update |
| `NoteRewrite` / `NoteRewrites` | Agent 0 | Inventory note rewrites proposed by the context update |
| `CandidateAssessment` | Agent 0 | The model's verdict on one candidate test |
| `ImpactAssessment` | Agent 0 | The batch of candidate assessments |
| `FilePlan` | Agent 2 | One file in the plan (path, type, is_new_file, purpose, related_test_cases) |
| `CodePlan` | Agent 2 | Stage 1 output — list of FilePlans + branch/PR metadata |
| `GeneratedFile` | Agent 2 | A generated file (path, content, is_new_file, purpose) — runtime, not from LLM |
| `CodeGenerationOutput` | Agent 2 | Container for final generated files + plan metadata |
| `ReviewIssue` | Agent 3 | One issue (severity, file_path, line_number, issue_type, description, suggested_fix, failure_scenario, test_outcome) |
| `ReviewReport` | Agent 3 | Container for issues + summary |
| `TestResult` | Agent 5 | One test result from JUnit |
| `RunReport` | Agent 5 | Container — totals + tests + CI context |
| `JiraCommentDraft` | Agent 5 | LLM-drafted comment (title, body_markdown) |

### 9.8 `inventory_tools/` + `scripts/` inventory & sweeper tooling

Two capabilities added in Tier 3, both app-agnostic (no assumptions about any one application):

**Inventory generation + staleness (3.1).** `inventory_tools/introspect.py` holds
the pure, browser-free logic and is fully unit-tested: `rank_selector` (test-id
attr → role + name → label → aria-label → placeholder → alt → title → stable id/name →
nameless role → text → css path; never XPath), `derive_element_name`,
`collapse_repeated_families` (buckets repeated test-ids like `buy-item-*` into one
`[<attr>^='buy-item-']`, preserving whichever attribute the app uses),
`build_page_entry` (assembles a draft page; fills machine-knowable fields, stubs the
human ones), and `diff_page`/`summarize_drift` (staleness). The test-id attribute set
is the configurable `TEST_ID_ATTRS` constant. `inventory_tools/browser.py` is a thin
Playwright layer (lazy import): `collect_descriptors`, `resolve_selectors`, and a
generic `do_login` that takes explicit selectors (type-based defaults). Four CLIs wrap
it: `scripts/generate_inventory.py` (crawl → draft), `scripts/promote_draft.py`
(merge drafts, strip third-party embeds), `scripts/verify_locators.py` (measure
every selector against the live page) and `scripts/check_inventory_staleness.py`
(diff live DOM, `--fail-on-drift` for CI).

The crawler MEASURES rather than predicts: every selector it derives is resolved
against the page it came from before being written, so a locator matching zero
is reported at crawl time instead of surfacing days later. That change came
from four separate bug classes with one cause — ranking inferred what Playwright
would do from DOM properties, and the accessibility tree does not follow them.
CSS `text-transform` changes the rendered text but not the accessible name; a
`::before` icon glyph joins the name but is invisible to `textContent`; a hidden
element is absent from the a11y tree entirely; an `<a>` without `href` has no
link role. The page is open at that moment, so the guess is now a measurement.

**Sweeper (3.4).** `scripts/sweep_stalled_prs.py` has a pure core —
`workflow_settled(runs)` and `classify_pr(...)` — plus a PyGithub I/O shell reusing
`GitHubClient`. `.github/workflows/sweeper.yml` runs it hourly on weekdays, 10:05–19:05 IST. It reopens `auto/*`
PRs whose Agent-3/Agent-4 workflow has no settled run for the head commit, using the
PAT so the reopen re-fires the `pull_request` chain (see ADR-010). Loop-safe via a
commit-SHA marker comment.

These interact with existing modules: page `components` drive
`app_context.filter_inventory_by_components` (2.2), and page-level `errors` ride that
same filter. Neither adds a hard dependency to the agents — the inventory tools are
standalone CLIs, and the sweeper operates purely on GitHub state.

---

## 10. The Jira label state machine — every label explained

Configuration source: `config/config.yaml` → `agents.agent1_analyst`, `agents.agent2_coder` and `agents.agent0_impact.labels`. The labels Agent 0 adds for a change story are in §18.

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
       │  - splices new step functions into the step_def file
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
| `tests-run` | Agent 5 | Reconcile on undo | Marker | Results reported on the story |
| `impact-check` | Human | Agent 0 | One-shot trigger | Agent 0 analyses the change story |
| `impact-proposed` | Agent 0 | Hand-over | Gate marker | An Impact Review waits for a person; Agents 1/2 exclude the story |
| `impact-applied` | Agent 1 (impact-aware) | Reconcile | Marker | Approved tests revised; reconcile watches the PR |
| `impact-reverted` | Reconcile | Human (to retry) | Terminal marker | The change was undone; card moves to To Do |
| `ai-retired` | Hand-over / reconcile | Reconcile on undo | Test-case marker | The test case is retired |

---

## 11. `ai-update` — what it does, scenario by scenario

**Entry point:** `agents/agent2_coder.py::run_update()` at line 3841

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
- The step_def file goes through `_splice_step_defs_incremental()`: unchanged if existing functions already cover the edited scenario (0 LLM calls), otherwise only the missing step functions are written and appended; any ambiguity falls back to whole regeneration
- Other scenarios in the feature: byte-for-byte preserved (whitespace, comments, indentation untouched)
- PR body: `**Modified scenarios:** PROJ-29`
- Branch: `auto/<story>-<feat>-update1` (or `-update2` if `-update1` already exists)

### Scenario C — A new Test Case was added to the story

- `classify_test_cases()` puts it in `new`
- Flow: `_generate_single_scenario()` → `append_scenario()` appends to end of feature file
- Step_def file: only the new step functions are spliced in
- Orphan cleanup: no orphans (nothing was removed)
- PR body: `**New scenarios:** PROJ-32`

### Scenario D — A Test Case was DELETED in Jira

- `classify_test_cases()` puts its key in `orphan_keys`
- Flow:
  1. `remove_scenario()` deletes the block + its marker
  2. Step_def file goes through the splice. Nothing new to define, so the file is kept as it is — including any step function only the deleted scenario used
  3. **Orphan cleanup runs:**
     - `cleanup_orphans_after_removal()` reads all step_def files + extendable page objects (including auto-discovered ones)
     - Detects step def functions only referenced by removed scenarios (used to find their page methods)
     - Detects page-object methods only called from those orphan step defs → commented out with `# AI-ORPHAN: this page-object method appears to no longer be used after scenario(s) PROJ-31 were removed from Jira. Review before deleting.`
  4. **Unused step functions commented out:** `comment_out_step_defs_unused_by()` comments out every step decorator the feature used before this update and no longer uses (a removal or a modification can take a step's last use), with an `# AI-ORPHAN:` banner. Same rule as the final unused-step check, applied deterministically, so the gate passes. A function that keeps one used decorator loses only the unused lines. Runs after the orphan cleanup, which still needs those functions to find their page methods
- PR body:
  ```
  **Removed scenarios (no longer in Jira):** PROJ-31
  **Step definitions left unused (commented out for review):** `click_recovery_email`, `verify_recovery_sent`
  **Orphan page methods (commented out for human review):** `LoginPage.click_forgot_password`, `LoginPage.is_recovery_email_visible`

  > ⚠️ Review the page object diffs — if a method might be useful for upcoming scenarios, uncomment it. Otherwise delete in a follow-up commit.
  ```

### Scenario E — Mixed: some modified, some new, some deleted

All three operations applied in sequence within a single `run_update()` execution:
1. Removals first (so they don't confuse the LLM about which steps exist)
2. Modifications (in-place splices)
3. Additions (appends)
4. Step_def splice once (operates on the fully-spliced feature)
5. Orphan cleanup once, then unused step functions commented out once

Single PR with all three sections in the body.

### Scenario F — Test Case description edit added a step that needs a new page method

- `modified` contains the TC
- New scenario is generated with the new step
- The splice writes a new `@when/@then` for the new step, grounded in the real page objects; a call to a method that does not exist is corrected once with the validator's feedback, then falls back to whole regeneration against the same page objects
- **BUT page object files are NOT extended in `ai-update` mode**
- Result: if the step genuinely needs a new page method, nothing can supply it
- The final validator (`validate_method_resolution`) catches this and the PR fails final validation
- **Workaround:** use `ai-regenerate` instead — that DOES regenerate page objects

This is a known limitation. Documented in the PR body: *"If new page-object methods are needed for surviving scenarios, use the `ai-regenerate` label for a full regeneration."*

---

## 12. `ai-regenerate` — what it does, scenario by scenario

**Entry point:** `agents/agent2_coder.py::run()` with `is_regenerate=True` at line 4267

**Selection:**
```yaml
regenerate_selection:
  required_labels: ['ai-processed', 'human-approved', 'ai-regenerate']
  excluded_labels: ['ai-skip', 'ai-update']   # if both set, neither runs
```

**Differences from normal mode:**

1. **Dedup bypassed** — `_select_new_test_cases(test_cases, is_regenerate=True)` returns ALL test cases as "new" without checking if they're already covered. Normal mode would skip them as duplicates.
2. **Branch naming** — `_resolve_unused_revision_branch()` adds `-rev2`/`-rev3` suffix. The original PR is preserved as a historical record.
3. **Orphan cleanup ENABLED** — even though normal mode skips it, regenerate mode runs `cleanup_orphans_after_removal()` to handle deleted Test Cases.
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

The two selections exclude each other:
- `update_selection.excluded_labels` contains `ai-regenerate`, so update mode skips the story
- `regenerate_selection.excluded_labels` contains `ai-update`, so regenerate mode skips it too

**If you set both, neither runs.** Remove one of them first. This is a config-driven safety against ambiguous intent.

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
# .github/workflows/agent1_analyst.yml and agent2_coder.yml (UTC; IST = UTC+5:30)
schedule:
  - cron: "30 4 * * 1-5"        # 10:00 IST
  - cron: "0,30 5-12 * * 1-5"   # 10:30 - 18:00 IST, every 30 min
  - cron: "0,30 13 * * 1-5"     # 18:30 and 19:00 IST

# .github/workflows/agent0_impact.yml
schedule:
  - cron: "15 5 * * 1-5"        # scan + reconcile, 10:45 IST, weekdays
  - cron: "45 1 * * *"          # nightly drift, 07:15 IST

# .github/workflows/inventory_health.yml
  - cron: '30 2 * * *'          # 08:00 IST
# .github/workflows/artifact_cleanup.yml
  - cron: "30 20 * * *"         # 02:00 IST daily
# .github/workflows/sweeper.yml
  - cron: "35 4-12 * * 1-5"     # 10:05 - 18:05 IST
  - cron: "35 13 * * 1-5"       # 19:05 IST
```

**Note on scheduler liveness:** GitHub Actions cron is "best effort" on free
personal accounts and disables after ~60 days of repo inactivity. A daily
keep-alive workflow existed for this but was removed in July 2026 — regular
agent activity (PRs, commits) keeps the scheduler alive, and its direct
pushes to main conflicted with branch protection (GH013).

---

## 14. Validators — the safety net

29 distinct checks: `validate_paths_against_policy` on the plan, 10 hard gates in
`_validate_generated_files()` (line 2324, run in order, cheapest first, so an
expensive AST walk only runs if the basic checks pass), and 25 validator calls
in `_collect_repairable_errors()` — the set the repair loop uses — of which 7
are also hard gates. `validate_page_object_methods()` wraps further page-object
checks.

| # | Validator | Defined at | Runs in |
|---|---|---|---|
| 1 | `validate_paths_against_policy` | `agents/agent2_coder.py:682` | plan |
| 2 | `validate_filename_consistency` | `validators/gherkin_analyzer.py:334` | gate |
| 3 | `validate_feature_file_structure` | `validators/gherkin_analyzer.py:1019` | gate + repair |
| 4 | `validate_extended_page_objects_keep_methods` | `validators/page_object_contract.py:78` | gate + repair |
| 5 | `validate_step_definitions_complete` | `validators/gherkin_analyzer.py:1124` | gate |
| 6 | `validate_no_duplicate_step_definitions` | `validators/gherkin_analyzer.py:776` | gate + repair |
| 7 | `validate_imports_resolvable` | `validators/import_validator.py:194` | gate + repair |
| 8 | `validate_method_resolution` | `validators/method_resolution_validator.py:603` | gate + repair |
| 9 | `validate_page_object_selectors` | `validators/method_resolution_validator.py:1444` | gate + repair |
| 10 | `validate_no_unused_step_definitions` | `validators/gherkin_analyzer.py:1415` | gate |
| 11 | `validate_fixtures_exist` | `validators/gherkin_analyzer.py:1555` | gate + repair |
| 12 | `validate_row_scoped_selectors` | `validators/method_resolution_validator.py:3936` | repair |
| 13 | `validate_helper_return_types_are_respected` | `validators/method_resolution_validator.py:3835` | repair |
| 14 | `validate_row_index_is_not_a_cell_index` | `validators/method_resolution_validator.py:3709` | repair |
| 15 | `validate_examples_hold_data_not_placeholders` | `validators/gherkin_analyzer.py:958` | repair |
| 16 | `validate_fills_confirm_their_page` | `validators/method_resolution_validator.py:3619` | repair |
| 17 | `validate_page_object_methods` | `validators/method_resolution_validator.py:4374` | repair |
| 18 | `validate_absence_not_asserted_with_waiting_probe` | `validators/method_resolution_validator.py:2268` | repair |
| 19 | `validate_readiness_probe` | `validators/method_resolution_validator.py:1814` | repair |
| 20 | `validate_no_selectors_in_step_defs` | `validators/method_resolution_validator.py:2351` | repair |
| 21 | `validate_persistent_state_assertions` | `validators/method_resolution_validator.py:2984` | repair |
| 22 | `validate_step_parameter_types` | `validators/method_resolution_validator.py:4532` | repair |
| 23 | `validate_persistent_pages_can_be_cleared` | `validators/method_resolution_validator.py:3483` | repair |
| 24 | `validate_readers_return_what_they_name` | `validators/method_resolution_validator.py:4095` | repair |
| 25 | `validate_annotated_returns_are_reachable` | `validators/method_resolution_validator.py:1885` | repair |
| 26 | `validate_confirm_arrival_targets_this_page` | `validators/method_resolution_validator.py:4229` | repair |
| 27 | `validate_step_claims_are_verified` | `validators/method_resolution_validator.py:3355` | repair |
| 28 | `validate_step_coverage` | `validators/gherkin_analyzer.py:1867` | repair |
| 29 | `validate_reused_steps_keep_their_meaning` | `validators/method_resolution_validator.py:4764` | repair |

Repairable failures go to the repair loop (`_attempt_step_coverage_repair`),
routed to the file they name (`_route_to_generated_file()`); only the broken files are regenerated, with the
validator's words as feedback (`_ERROR_TYPE_RULES` adds targeted guidance per
error type). What survives four attempts, or a non-repairable failure, stops
the run before a branch exists. What each check catches is described in
GUIDE.md → The validator gate.

---

## 15. Reuse architecture (config-driven design)

The single biggest design decision in this codebase. **All app-specific knowledge is isolated to configuration and data files. No agent, core, integration or validator code — and no unit test — changes between projects.**

### Layer 1 — `AppContext` (singleton config loader)

`core/app_context.py::AppContext.load()` reads `config/config.yaml`, validates, and returns an immutable dataclass. Every agent calls this once at startup.

### Layer 2 — Prompts with placeholders

Agent prompts (`prompts/agent2_coder_plan.md`, `prompts/agent2_coder_generate.md`, etc.) use placeholders like `{app_name}`, `{reserved_paths_block}`, `{extendable_paths_block}`, `{reference_feature_content}`, `{page_inventory_json}`, `{test_cases_text}`. They are substituted at runtime with chained `str.replace()` calls (not `.format()`, so literal braces in code samples are safe), using values from the AppContext.

### Layer 3 — App-specific files

| File | Purpose | Touch on new project? |
|---|---|---|
| `config/config.yaml` (`app_under_test` block) | App config | YES |
| `app_inventory/<app>.json` | Pages/selectors catalog | YES |
| `prompts/app_context/` (`core.md` + one module per Jira Component) | Known users, data, flows, module behaviour | YES |
| Reference triplet (1 feature + 1 step_def + 1 page_object) | LLM's style baseline | YES |
| `README.md` / `CHANGES.md` | Narrative docs | Optional |

### Layer 4 — Agent files (NEVER touch)

| File | Project-specific? |
|---|---|
| `agents/`, `core/`, `integrations/`, `validators/`, `inventory_tools/` | NO |
| `prompts/agent*.md` (10 files) | NO |
| `pages/base_page.py` | NO (universal helpers) |
| `tests/unit/*.py` | NO |
| `.github/workflows/*.yml` (9 workflows) | NO |

This isolation is enforced by code, not just convention:
- Path policy validator rejects plans touching reserved files
- Prompts use placeholders (config substitution happens before LLM sees it)
- Unit tests use generic, synthetic fixtures (banking, CMS, a fake tracker and repo host) rather than the application under test

---

## 16. Failure modes and recovery

### LLM returns malformed JSON in Stage 1

- `LLMClient.invoke_structured()` sends the validation error back once (`structured-repair:CodePlan`)
- A second failure raises `ValueError`; the run stops before any branch exists
- The full LLM response is logged. The trigger label is not consumed, so the next tick retries.

### LLM hallucinated a non-existent page in the plan

- `validate_paths_against_policy()` doesn't catch this (it only knows reserved/extendable)
- `validate_imports_resolvable` catches it post-Stage-2; it is repairable, so the repair loop regenerates the file with the error as feedback
- If it survives the repair attempts, final validation fails with a clear error

### Step coverage validator finds missing decorators

- Repair loop kicks in (up to 4 attempts, with the early stops in §5.5)
- Each attempt regenerates ONLY the broken file
- If still failing: the run stops at final validation before a branch exists; a human debugs

### GitHub branch creation fails (e.g., branch already exists from a manual push)

- A partial branch with no PR (an interrupted earlier run) is discarded and rebuilt from `main`
- If a PR already exists for the story's branch, the work landed: only the `ai-coded` label is repaired
- A branch under `auto/` should never be created by hand — the sweeper and Agent 5 read story keys from it

### LLM quota / rate limit exceeded

- `LLMClient._call_with_quota_check()` raises `QuotaExhaustedError`
- Workflow fails with clear message
- Agent's labels are NOT consumed (since the action didn't complete)
- Next cron run will retry. If quota is daily, retry happens next day.

### Workflow timeout (GitHub Actions 6-hour limit)

- Rare — typical Agent 2 run is 2-5 minutes
- If it happens, partial commits may exist on the branch and no PR opens
- Recovery is automatic: the next run discards the partial branch and rebuilds it

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

## 17. Later additions — sprint scoping & cost instrumentation

Two features added after the sections above were written; full operator docs
live in GUIDE.md, summarized here for completeness:

**Dynamic sprint scoping.** Every scan JQL now carries a sprint clause.
`config.yaml` sets `sprint: "auto"` in all four selection blocks;
`JiraClient.get_active_sprint_name()` resolves the currently active sprint via
the `JIRA_BOARD_ID` env var (cached per run; degrades to an all-sprints scan
with a warning if unresolvable). Priority: `--sprint` CLI/workflow input >
config value > no filter. Zero config edits at sprint boundaries.

**LLM token & cost instrumentation.** `llm_client.py` hosts a process-lifetime
`_UsageTracker`: every call records API-reported input/output tokens; each
story run ends with two separate log lines — `LLM TOKEN USAGE [...]` (exact)
and `LLM COST [...]` (derived from the `LLM_PRICE_INPUT_PER_1M` /
`LLM_PRICE_OUTPUT_PER_1M` repo variables). Cross-agent story cost:
`core/usage_ledger.py` — each LLM-using agent (Agent 0 included, for a change
story) posts a machine-parseable
`[LLM-USAGE]` comment on the story (Agent 3 derives the key from the
`auto/<KEY>-` branch); Agent 5 reads them back (`JiraClient.get_comments`),
adds its own usage, and appends an "End-to-end LLM usage & cost" table
(per-agent rows + TOTAL) to its test report. Posting/reading is best-effort
and can never fail a run; missing pricing flags totals as a lower bound
(token counts stay exact).

## 18. Agent 0 — Impact Analyst (deep)

**Files:** `agents/agent0_impact.py` (685 lines) and `core/impact_*.py`, `core/context_update.py`, `core/json_block.py`
**Workflow:** `.github/workflows/agent0_impact.yml` — four jobs: scan, reconcile, code change (PR), nightly drift. A `gate` job reads `agents.agent0_impact.enabled`; reconcile is not gated (it only acts on `impact-applied` stories).
**CLI:** `python -m agents.agent0_impact --scan | --story KEY | --code-change --base DIR --head DIR --pr N | --drift-report FILE [--dry-run]`

### 18.1 Settings (`core/impact_settings.py`)

`agents.agent0_impact` in `config.yaml` is merged over `DEFAULTS` (which keep
Agent 0 off). Key settings: `enabled`, `shadow_mode`, `selection`, `labels`,
`review` (sub-task type, summary prefix, done status), `weights`
(`structural 0.45, component 0.15, semantic 0.15, adjudicated 0.25`),
`thresholds` (`must_update 0.6, review 0.3`), `max_candidates` (300),
`reconcile` (`closed_scans`, `no_pr_days`, `reset_labels`) and `context_update` (`enabled`,
`branch_prefix`).

### 18.2 The analysis

`agents/agent0_impact.analyse_and_publish(tracker, story_key, llm, settings, root, host)` drives `core/impact_analysis.py`:

1. **Repeat check** — the story's requirement hash is compared with the last report; an unchanged story is skipped. A changed one is re-analysed and the review updated in place (`_post_delta` says when nothing changed in the affected tests or tiers).
2. **Seeds** — `ChangeSeeds` (one structured call, `prompts/agent0_seeds.md`): `change_type` (`new_behaviour`, `changed_behaviour`, `removed_behaviour`, `mixed`), `behaviours`, `element_keys`, `components`. `validate_requirement_seeds()` drops element keys not in the inventory (reported), and a `new_behaviour` story keeps no element seeds and no changed behaviours (#186) — using an element is not changing it.
3. **Candidates** — `core/impact_graph.py` builds scenario → step → method → selector edges from `# JIRA:` markers, step decorators and page-object ASTs. Layer 1 (`structural_candidates()`) is every scenario the graph connects to a seed; layer 2 (`semantic_candidates()`) is the scenarios in the story's components. `shortlist()` always judges layer 1 and fills the rest of `max_candidates` (300) from layer 2 by text relevance; anything left over is reported as not judged, never hidden.
4. **Adjudication** — `ImpactAssessment` (one call per batch of `max_candidates`, so normally one call, `prompts/agent0_adjudicate.md`). `checked_assessments()` drops a verdict that cites no real graph path or verbatim step; a *review* verdict must name what the scenario does that the change makes different.
5. **Rank** — `rank()` combines the weights; the tier is the score's tier capped by the model's verdict (`_TIER_ORDER`). `short_evidence()` (in `agents/agent0_impact.py`) gives each row its reason and the elements involved.
6. **Publish** — shadow: a report comment (`(shadow mode)` in the title). Live: nothing to review → `ai-ready` plus the context update; otherwise an Impact Review sub-task (`core/impact_review.py`) and `impact-proposed`.

### 18.3 Review and hand-over

The review stores its rows as a JSON code block. `core/json_block.read_json_block()`
reads it back however Jira re-stored it after a person's edit
(`{code:json}…{code}` included, and a `{code}` inside the JSON). `scan()` first
analyses `impact-check` stories, then `hand_over_decided()` takes stories labelled
`impact-proposed` whose review is Done: `decisions_from_review()` reads the
Decision column and `core/impact_handover.handover()` adds the Impacts links,
`ai-retired`, the *will-revise* trace on owners (`core/impact_trace.py`, skipped
where `already_posted`), and swaps the labels. `HandoverRefused` (unreadable or
undecided review) leaves the story waiting.

### 18.4 Context update (`core/context_update.py`)

`propose_for_story()` runs at hand-over (and when there is nothing to review):
`extract_changes()` (`WordingChanges`, `prompts/agent0_wording.md`) and
`extract_note_rewrites()` (`NoteRewrites`, `prompts/agent0_context_notes.md`).
`propose()` applies exact wording replacements to the inventory's string values
— which can include a text-based selector, flagged "verify after deployment" —
and the context notes, then `_apply_rewrites()` replaces each untrue passage
found verbatim; anything not found is dropped and reported. Note rewrites touch
NOTE values only, so a selector is never rewritten by them. Code mentioning the old text is listed, not
edited. `open_pull_request()` uses `branch_for()` — the story key in lower case,
or a hash, so the branch never carries an issue key — and the
`[agent0:context-update]` marker makes it idempotent. A marker that opened a
pull request stands only while that PR is open (#185), so a closed proposal
does not suppress a retry's update.

### 18.5 Reconcile (`core/impact_reconcile.py`, `scripts/impact_reconcile.py`)

`reconcile_all()` → `reconcile_story()` per `impact-applied` story: open PR →
wait; merged → *merged* trace on owners, label off; closed unmerged → a
`closed-unmerged pr: N updated: …` marker on each scan that sees the close
until `reconcile.closed_scans` scans have (default 2, so one marker), then
`_revert()`: snapshot restore where the current hash
equals the snapshot's new hash, un-retire, unlink, *restored* trace on owners,
`impact-reverted`; then `_settle_story()` retires the story's own test cases not
on `main` (`_unautomated()`, which never guesses when `main` cannot be read),
removes `reconcile.reset_labels`, moves the card via `status_workflow`, and posts
the retry steps. No PR after `no_pr_days` → one *ask-a-person* comment.

### 18.6 Code change and drift

Usage: `_post_usage()` puts each story's analysis and context-update cost on
its ledger as `Agent 0 (Impact Analyst)`; when entries from later agents are
already there (a new attempt), it posts a ledger reset first. Agent 1 ignores
Agent 0's entries when deciding whether to reset.

`--code-change` compares the page objects and inventory of base and head
checkouts (no model) and posts the affected tests on the PR. `--drift-report`
(nightly, or on demand: dispatch with `mode` = `drift`) takes the staleness check's JSON and, in live mode, opens or updates one
maintenance story (label `inventory-drift`).

## 19. Change stories in Agents 1, 2 and 5

- **Agent 1 — `agents/agent1_impact.py`.** `run_impact_aware()` runs instead of the normal draft when the story has approved impacted cases. One `ImpactAwareDraft` call (`prompts/agent1_impact_aware.md`); `validate_draft()` requires every approved key revised exactly once and no new case repeating a revised case or an existing scenario, and flags a revision near an existing scenario (`PURPOSE_KEPT`). A snapshot comment holds each old text and the old/new hashes before `update_test_case`. Labels: `ai-processed`, `impact-applied` on; `ai-ready` off. Re-running is safe.
- **Agent 2 — `agents/agent2_impact.py`.** `splice_owner_files()` splices each revised scenario into its owner's feature (marker placed below the tags), removes retired ones (their marker and block, not commented out), and regenerates only the step functions the owner file is missing via `_splice_step_defs_incremental()`, which receives this run's page objects (`batch_files`), checks method resolution and corrects once with the validator's words. After the splice, every step function the revisions and retirements left unused is commented out (`comment_out_step_defs_unused_by()`, the unused-step check's own rule, applied deterministically), and files the cleanup changed are committed.
- **Agent 5.** `post_owner_results()` and `record_prediction_outcome()` (§8).

## 20. The Protocols — Tracker and RepoHost

`integrations/tracker.py` declares `Tracker` (23 members, including
`project_key`) and `integrations/repo_host.py` declares `RepoHost` (16). Agents
receive an adapter from `get_tracker()` / `get_repo_host()` (new ones are added with `register_adapter()`) and never import Jira
or GitHub directly. `tests/unit/test_pipeline_tool_agnostic.py` runs the agents'
real `run()` functions against an in-memory tracker that has no JQL and no issue
types; `scripts/onboarding_check.py` checks a new adapter declares every
operation.

## Closing notes

This framework is the result of iterative refinement against real production LLM output — initially Gemini 2.5 Pro, later a model behind an OpenAI-compatible gateway (the provider swap needed zero agent-code changes). Versions v12 through v18 each fixed a specific LLM failure mode observed in production:

- v12 — JSON parsing brittleness in Stage 1 (Pydantic mode introduced)
- v12e — backtick-fence normalization
- v13/v14 — step coverage validator + repair loop
- v15 — cross-file step reuse (validator was too strict)
- v17 — type contract awareness + locator discipline
- v18 — BasePage helpers + exact phrase matching + parsers.parse quote handling
- May 13 — orphan code cleanup for ai-update AND ai-regenerate

Each was a real production failure, debugged from CI logs, fixed at the prompt or validator level. The unit suite is the regression net. The Pydantic schemas are the type contract. The two-stage LLM call with cross-file context injection is the central engineering decision.

If someone asks you "why is this framework production-grade rather than a demo," the answer is: every line was added because something went wrong, and the test that proves it works is checked in alongside it.