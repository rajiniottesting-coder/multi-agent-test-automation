# CHANGES

This document records substantive changes to the framework in reverse-chronological order.

---

## Phase 2 — Cross-file duplicate step-definition guard (SCRUM-54 lesson)

**The failure.** A new login-adjacent feature (`test_login_edge_and_validation.py`)
re-declared `@given("I am on the SauceDemo login page")`, a step the reference
`test_login.py` already defines. pytest-bdd registers step definitions GLOBALLY
across the `tests/step_defs/` package, so two files declaring the same step collide
at collection time. Agent 3 caught it as a Major advisory issue; this change makes it
a permanent, enforced guard so it cannot silently recur.

**The fix — "prompt asks, validator enforces" (the framework's standard pattern):**

1. **Validator** — `validate_no_duplicate_step_definitions()` in
   `agents/gherkin_analyzer.py`. After generation it scans the generated step-def
   files PLUS the on-disk reference for identical decorators across files. It is
   deliberately NARROW to avoid false positives: it flags only a genuine
   `(keyword, parser_type, phrase)` collision across two different files. It does
   NOT flag different phrases, different keywords, a bare string vs a `parsers.parse`
   of the same text, parameterised steps differing only in variable name, or
   duplicates within a single file. A regenerated file supersedes its on-disk copy,
   so `ai-update`/`ai-regenerate` never false-positive against the stale version.
   Wired into `_validate_generated_files()` (final gate) and, in `repair_format`,
   into `_collect_repairable_errors()` so the repair loop can regenerate the
   offending GENERATED file (never the reserved reference) with the feedback baked in.

2. **Prompt rule** — `prompts/agent2_coder_generate.md` gains rule 13 (and a
   reinforcement in the step-def section): do not re-declare a step the reference
   already defines; reuse it, or move a truly shared step into
   `tests/step_defs/conftest.py`. This reduces occurrences; the validator guarantees
   they're caught.

**Verification.** New `tests/unit/test_duplicate_step_defs.py` — 14 tests covering
true positives (new-vs-new, new-vs-reference, parse decorators), every false-positive
guard (different phrase/keyword/parser-type, parameterised varname, within-file dup,
non-step-def files, regenerated-file supersession), and the repair-format contract
(targets the generated file, matches the loop's grouper regex). Confirmed the
validator produces ZERO errors against the current repo's existing step-defs.
Catalogued as lesson #15 in `docs/AI_CONCEPTS.md`. Suite: 156 → **170 passing**.

---

## Phase 2 — Tier 2 (batch 1: low-blast-radius token savings)

Both changes are **fully backward-compatible** — with no new files or folders
added, behaviour is byte-identical to before.

### Inventory minification (backlog 2.6)

`agents/app_context.py` — `load_page_inventory_json()` now minifies the inventory
JSON at injection time (`json.dumps(..., separators=(",",":"))`). The file on disk
stays human-readable; only the string sent to the LLM is compacted, trimming input
tokens on every Agent 2 and Agent 3 call at zero information loss. On the SauceDemo
inventory this is ~15%; the saving grows with inventory size.

**Safety:** if the inventory is not valid JSON, the method logs a warning and returns
the raw text unchanged — identical to the pre-2.6 behaviour, so a malformed file can
never make it start failing. A *missing* file still raises `FileNotFoundError` as
before (only parse errors fall back).

### Module-wise app context (backlog 2.1)

`agents/agent1_analyst.py` — `load_app_context_block()` becomes module-aware, and
`agents/jira_client.py` — `get_story()` now returns the story's Jira Components
(additive; all existing keys unchanged).

Two layouts, chosen automatically from the filesystem:

- **Single file (default, unchanged).** `prompts/app_context.md` — the original
  behaviour. Used whenever `prompts/app_context/` does not exist.
- **Module-wise (opt-in).** Create `prompts/app_context/` with `core.md` plus one
  `<component>.md` per module. Agent 1 then injects `core.md` (always) plus the files
  matching the story's Jira Components, instead of carrying every module's rules on
  every call. For a large app this focuses the prompt and cuts Agent-1 input tokens.

Matching is case- and separator-insensitive ("User Management" → `user_management.md`).
Safe defaults: a story with no components, or a component with no matching file,
injects **all** modules — context is never silently dropped.

**To adopt** (optional, per app): split `prompts/app_context.md` into
`prompts/app_context/core.md` (roles, global errors, auth flow) + one file per Jira
Component, and tag stories with their Component. Until you do, nothing changes.

### Tests

New `tests/unit/test_app_context_modules.py` — 19 tests covering both features:
single-file compatibility, core-always, multi-component, name normalisation,
all safe-default fallbacks, empty/absent folders, and for minify: valid-JSON
round-trip, colons-in-values, unicode, malformed-fallback, and missing-file-still-raises.
Suite: 137 → **156 passing**.

---

## Phase 2 — Tier 1

### Ledger reset boundary — fixes a cost double-count bug (backlog 1.3)

**The bug.** Deleting a story's Test Cases and resetting it to `ai-ready` left the
previous run's `[LLM-USAGE]` comments on the story. Agent 5's next aggregation
summed the discarded run *and* the new one, so the "End-to-end LLM usage & cost"
table reported inflated totals.

**The fix.** `agents/usage_ledger.py` gains a `[LEDGER-RESET]` boundary marker:
`format_reset_comment()` / `post_reset_to_story()` post it (best-effort, never
raises); `_comments_after_last_reset()` returns only comments posted after the most
recent boundary; `aggregate_story_usage()` aggregates just that slice.
**Backward compatible** — with no marker present every comment counts, as before.
`has_usage_comments()` lets an agent ask "has this story been costed since the last
boundary?".

`agents/agent1_analyst.py` posts the boundary when processing a story that already
carries usage entries. Scoped deliberately to Agent 1: `ai-update` and
`ai-regenerate` are rework on the same costed story, so their usage *should*
accumulate into the lifetime total — only a fresh `ai-ready` cycle restarts
accounting. Skipped in `--dry-run`; wrapped in its own try/except so a ledger
failure can never fail a run.

14 new unit tests. Suite: 123 → **137 passing**.

### Model routing (backlog 1.2)

`agent1_analyst.yml` and the Agent-5 job in `agent4_runner.yml` now read
`LLM_MODEL_LIGHT`, falling back to `LLM_MODEL` and then Opus. Agents 2 and 3 always
use `LLM_MODEL`. **No-op until the repo variable is set** — the fallback chain
preserves current behaviour exactly. Set `LLM_MODEL_LIGHT` (e.g.
`claude-sonnet-4-6`) to route test design and report prose to a cheaper tier.

### Gateway probe (new manual tool)

`scripts/gateway_probe.py` — lists the models the LLM gateway exposes and tests
whether Anthropic prompt caching is passed through, trying the `cache_control`
breakpoint on both `system` and `user` message placements. Manual only; not run by
CI. Result on the adesso hub (July 2026): 45 models available; **caching not
passed through** — all cache counters zero on a 2,356-token prefix across both
placements, so backlog item 1.1 is blocked pending a gateway config change.

### Credential hygiene for real-app onboarding (backlog 1.5)

`docs/REUSE_FOR_NEW_PROJECT.md` — the `test_users` step is now a security note.
SauceDemo's public demo credentials are safe to commit; real ones are not, because
`config.yaml` and `app_context.md` are committed permanently *and* `app_context.md`
is injected into every Agent 1 prompt. Documents the env-var pattern.

### Documentation accuracy

- `docs/GUIDE.md` — removed 16 stale references to Google Gemini as the LLM
  (agent descriptions, troubleshooting, and the Mermaid architecture diagrams).
  The framework has run on Claude via an OpenAI-compatible LiteLLM gateway since
  the provider swap; the guide still described the original Gemini build.
- `README.md` — removed the dead `docs/reference/` index row (those files were
  never added to the repo).
- Test-count references updated 123 → 137.

### Already in place

Backlog item 1.4 (move `pages/base_page.py` to `reserved_paths`) was found already
applied in `config/config.yaml` — no change needed.

---

## July 2026 — Accurate story reporting + failure evidence capture

**Report scope fix (unit vs app tests).** Agent 4 previously ran `pytest tests/`
(unit + E2E together) into one junit.xml, so Agent 5's Jira report counted the
123 framework unit tests alongside the story's app tests — inflating and
confusing the numbers. Now split into two steps:
- `pytest tests/unit/` → `reports/junit-unit.xml` — framework self-test gate
  (runs first; failing it signals the framework itself is broken).
- `pytest tests/step_defs/` → `reports/junit.xml` — the app E2E results Agent 5
  reads. Story reports now reflect ONLY the feature's tests. No Agent 5 code
  change (it still reads junit.xml, which is now app-only).

**Failure evidence.** The `page` fixture in tests/conftest.py now records, on
test FAILURE only: a full-page screenshot (`.png`), a video (`.webm`), and a
Playwright trace (`.trace.zip`) into `reports/failure-evidence/`. Passing tests
discard video/trace to keep artifacts small. All three ride along in the
existing `reports/` workflow artifact for human inspection on the PR. A
`pytest_runtest_makereport` hook exposes each test's outcome to the fixture.

---

## July 2026 — LLM token & cost instrumentation + end-to-end story cost ledger

Token usage and cost are now MEASURED, tracked as two separate quantities,
and aggregated per story across all agents.

### Per-run tracking (agents/llm_client.py)

- A usage tracker records input/output tokens for every LLM call (both
  structured and text mode). Per-call log lines show the call's tokens plus
  running totals.
- At the end of each story run, TWO separate summary lines are logged:
  `LLM TOKEN USAGE [...]` (exact, API-reported) and `LLM COST [...]`
  (derived from pricing, split into input + output cost). The summary dict
  is returned in agent results under `llm_usage`.
- Pricing comes from two optional repo Variables (USD per 1M tokens):
  `LLM_PRICE_INPUT_PER_1M`, `LLM_PRICE_OUTPUT_PER_1M` — now exposed in all
  four agent workflows. Unset → tokens still logged, cost shows "n/a".
- Endpoints that don't report `usage_metadata` are counted and flagged as a
  lower bound. Tracking never raises.

### End-to-end story ledger (agents/usage_ledger.py — NEW)

Each agent runs in a separate CI process, so in-memory totals can't span the
pipeline. The Jira story itself is now the ledger:

- After finishing, every LLM-using agent (1, 2, 3, 5) posts one compact,
  machine-parseable comment: `[LLM-USAGE] agent="..." calls=N
  input_tokens=N output_tokens=N input_cost_usd=... output_cost_usd=...
  cost_usd=...` (skipped in dry-run; best-effort, never fails a run).
- Agent 3 derives the story key from the `auto/<KEY>-` branch convention.
- Agent 5 reads all prior usage comments (new `JiraClient.get_comments`),
  adds its own usage, and appends an "End-to-end LLM usage & cost" table to
  its test report — per-agent rows plus a TOTAL row. Partial pricing is
  flagged as a lower bound; token totals are always exact.

### Tests

27 new unit tests (`test_llm_usage.py`, `test_usage_ledger.py`) — suite
grew 96 → 123, all passing. No existing module behavior changed
(gherkin_analyzer, orphan_cleanup, validators, app_context, schemas,
config.yaml all untouched).

---

## July 2026 — Documentation consolidation (11 → 7 files) + stale reference cleanup

### Why

Doc count had grown to 11 standalone markdown files with overlapping scope,
and several still referenced `test_inventory.py` (renamed to
`gherkin_analyzer.py` in June).

### Consolidation map

| Merged file | Now lives in |
|---|---|
| docs/ARCHITECTURE_DIAGRAM.md | docs/GUIDE.md → "Architecture diagrams" |
| docs/STATE_MANAGEMENT.md | docs/GUIDE.md → "State management deep-dive" |
| docs/LESSONS_LEARNED.md | docs/AI_CONCEPTS.md → "Lessons learned" |
| docs/APP_INVENTORY_SCHEMA.md | REUSE_FOR_NEW_PROJECT.md → "App inventory JSON schema" |
| docs/ADR-008-pat_for_cascade.md | docs/DECISIONS.md (ADR content unchanged) |
| docs/ADR-009-deduplication.md | docs/DECISIONS.md (module refs updated) |

Final doc set (7): README.md and CHANGES.md at root; docs/GUIDE.md,
docs/AI_CONCEPTS.md, docs/DECISIONS.md, docs/REUSE_FOR_NEW_PROJECT.md,
docs/TECHNICAL_DEEP_DIVE.md.

### Also in this release

- Fixed all remaining `test_inventory.py` references in markdown
  (CHANGES, TECHNICAL_DEEP_DIVE, ADR-009 content).
- Updated pointers in code/config that referenced merged docs:
  `agents/app_context.py` error message, `config/config.yaml` comment,
  `.github/workflows/agent2_coder.yml` comment, README doc index,
  GUIDE internal links.
- No behavior change; all 96 unit tests pass.

---

## June 2026 — Dynamic sprint scoping, module rename, documentation refresh

### 1. Dynamic sprint scoping (`sprint: "auto"`)

Previous state: `sprint: "Sprint 0"` was hardcoded in four config blocks and
needed manual editing at every sprint boundary.

Now: all four selection blocks use `sprint: "auto"`. At scan time,
`JiraClient.get_active_sprint_name()` resolves the currently active sprint
from Jira via the new **`JIRA_BOARD_ID`** env var (set once in .env / GitHub
secrets; find the ID in your board URL). The result is cached per run so
Agent 2's three scan passes make one API call. Resolution failures degrade
gracefully to an all-sprints scan with a logged warning — the pipeline never
blocks on sprint lookup.

Priority order remains: `--sprint` CLI flag / workflow input > config value >
no filter. Explicit names (`"Sprint 10"`), `"openSprints"`, and omitting the
key all still work as before.

Files: `agents/jira_client.py`, `config/config.yaml`, both agent workflow
files (added `JIRA_BOARD_ID` to env).

### 2. Renamed `agents/test_inventory.py` → `agents/gherkin_analyzer.py`

The old name looked like a pytest test file (`test_*` prefix), which confused
readers and risked accidental pytest collection. The module is the Gherkin /
step-definition analysis engine (scenario inventory, dedup matching, step
coverage validation) — the new name says so. All imports updated across
`agent2_coder.py`, `orphan_cleanup.py`, and the unit test files; zero
behavior change; all 96 unit tests pass. Historical docs (ADR-009) carry a
rename note rather than rewritten history.

### 3. New documentation

- `docs/STATE_MANAGEMENT.md` (since merged into docs/GUIDE.md, July 2026) — how the pipeline tracks progress (label state
  machine, sticky vs one-shot labels, JIRA hash markers, failure recovery).
- `docs/AI_CONCEPTS.md` — which AI concepts are used and deliberately not
  used, the guardrails analysis, and a demo Q&A.
- `docs/LESSONS_LEARNED.md` (since merged into docs/AI_CONCEPTS.md, July 2026) — the failure catalog: all 14 production LLM
  failure modes, root causes, and where each permanent fix lives.

---

## Hotfix v4 — Output token cap, feedback summarization, degraded-output detection (2026-05-07)

### What broke

After hotfix v3 added the import validator, the next CI run with `gemini-2.5-flash` succeeded at planning (correctly added cart_page and product_detail_page to the plan!) but failed at the step-coverage repair stage. The log showed three repair attempts that all produced ~656 chars of unparseable Python, eventually exhausting retries with all 22 step-coverage errors still present.

Root causes (three separate problems compounding):

1. **`max_output_tokens=4096` too small for code generation.** This cap is a sane default for structured review output (Agent 3) but step def files for complex 15-scenario stories legitimately need more. The LLM hit the token cap mid-generation and returned truncated stubs.

2. **22-error feedback prompt overwhelmed the LLM.** Each error string was ~250 chars × 22 errors = 5,500 chars of nearly-identical "step X has no matching @then() decorator" repetition injected into the prompt. Smaller LLMs respond to this by getting confused and producing shorter, worse output instead of more comprehensive output.

3. **No "degraded output" abort.** When the first repair produced a 656-char syntax-broken stub, the loop happily fed it back as "previous attempt" for retry #2, which produced more garbage. Burning quota on each retry.

### Fix

Three changes, all framework code, all app-agnostic:

#### 1. Separate token cap for code generation

`agents/llm_client.py` now distinguishes:
- `DEFAULT_MAX_OUTPUT_TOKENS = 4096` — for structured outputs (CodePlan, ReviewReport)
- `CODE_GENERATION_MAX_OUTPUT_TOKENS = 8192` — for raw text (entire source files)

`invoke_text()` lazily creates a separate `ChatGoogleGenerativeAI` instance with the higher cap, cached on first call. No change needed to structured output paths.

#### 2. Compact validator feedback summary

New `_summarize_validator_feedback()` extracts only the actionable Gherkin step phrases (e.g., `Then the products should be sorted by name ascending`) and bullet-lists them. For >8 errors, shows the first 8 verbatim plus a count of the remaining with one explanatory sentence about the pattern.

Empirical reduction on the SCRUM-12 failure: **3,377 chars → 365 chars (89% smaller)**. The LLM sees the problem clearly without drowning in repetition.

#### 3. Degraded-output detection — abort early

New `_is_degraded_regeneration()` runs after each repair LLM call. If the new content:
- Is shorter than 500 characters, OR
- Fails to parse as Python (syntax error), OR
- Is less than 30% the size of the prior real attempt

then the repair loop aborts immediately and keeps the prior content. The final validator will raise on the original errors, but we don't waste another LLM call producing more garbage.

New `_looks_like_useful_python()` complements this for the "should I show the previous attempt to the LLM?" decision — if the prior is also broken, omitting it from the prompt produces better results than including it.

### Files changed

| File | Change |
|---|---|
| `agents/llm_client.py` | New `CODE_GENERATION_MAX_OUTPUT_TOKENS = 8192`. `invoke_text()` uses a separate cached LLM instance with this higher cap. |
| `agents/agent2_coder.py` | New `_summarize_validator_feedback()`, `_looks_like_useful_python()`, `_is_degraded_regeneration()` helpers. Repair loop checks for degraded output and aborts early. Feedback prompt rewritten to be compact. |
| `tests/unit/test_step_coverage_repair.py` | 11 new tests covering: feedback summarization (verbatim vs summarized), degraded output detection (short, syntax-broken, dramatic shrinkage), early abort behavior, real-content acceptance. Existing tests updated to use realistic Python content (>500 chars, valid syntax) since they were inadvertently testing with stubs that the new detector correctly flags. |
| `CHANGES.md` | This entry. |

### Test results

- **159 unit tests pass** (up from 148)
- **1 unrelated pre-existing failure** still unchanged (`test_empty_quoted_value_with_parsers_parse_REJECTED` — was failing in original code before any of these hotfixes)
- Smoke-tested helpers against the actual SCRUM-12 production failure data — all detection logic works as designed

### Why this is reusable across projects

- **Token caps** are model-level concerns, not app-level. The constants live in `llm_client.py` and apply to any project using this framework.
- **Feedback summarization** operates only on validator-emitted error strings — the regex pattern matches the framework's own output format, agnostic to what app the validator was run against.
- **Degraded-output detection** uses Python AST parsing and content length thresholds. Doesn't care about the app domain.

### What this fix does NOT do

- Does not change the LLM's actual output quality. If `gemini-2.5-flash` can't produce a valid step def for a 15-scenario story, this fix doesn't make it produce one. What it does is **fail clearly and faster** instead of burning quota on bad retries.
- Does not auto-split large stories. If the underlying story is too complex for the LLM to handle in one generation, you'll still see this fail — just without the wasted retries. Splitting that story into 2 smaller stories is the right human-in-the-loop response.

### What to watch for in the next run

The successful path looks like this in the logs:

```
LLM initialized: gemini-2.5-flash (temp=0.2, max_output_tokens=4096)
Code generation LLM ready: gemini-2.5-flash (max_output_tokens=8192)
...
Stage 1 complete: 5 files planned
...
Generated 4500 chars for tests/step_defs/test_inventory_sorting.py
...
Step coverage check: OK
Import resolution check: OK
PR opened
```

If validators still flag issues:

```
Validators found N issue(s) across 1 file(s). Attempting repair (attempt 1/2)...
  Repair mode: N validator error(s) summarized into ~400 chars of feedback...
Generated 5200 chars for tests/step_defs/test_inventory_sorting.py
Validator repair succeeded after 1 retry attempt(s).
```

If the LLM produces garbage on retry, you'll now see this clear abort:

```
Repair produced degraded output for 'tests/...' (656 chars vs prior 4500 chars,
  syntax-valid=False). Aborting repair to avoid wasting more LLM calls.
```

Then the final validator raises with a clear message about what couldn't be fixed.

---

## Hotfix v3 — Import resolution validator (2026-05-07)

### What broke

After hotfix v2 unblocked the step-coverage failure, the next run produced a PR that opened successfully but failed at the Agent 4 (Runner) test-collection stage:

```
ImportError while importing test module 'tests/step_defs/test_inventory_sorting.py'
E   ModuleNotFoundError: No module named 'pages.product_detail_page'
```

The LLM had generated a step def file that imported page object classes from files that **were never planned** and **don't exist on disk**. Agent 3 (Reviewer) caught it correctly and posted a 🛑 verdict listing all the missing classes, but Agent 4 still ran (Agent 3 is advisory — it's the human's job to read the review before merging) and crashed at pytest collection time.

### Why the previous validators didn't catch this

The framework had three validators before v3:
- **Filename consistency** (Phase 4) — passed: feature filename matched step def
- **Step coverage** (Phase 8) — passed: every Gherkin step had a decorator
- **Path policy** (v1 hotfix) — passed: no reserved files were touched

None of them check that **imports inside Python files actually resolve**. The LLM hallucinated `from pages.cart_page import CartPage` and `from pages.product_detail_page import ProductDetailPage` for files that aren't in the repo and weren't planned. All three existing validators happily passed it through.

### Fix — Import resolution validator

A new **fourth validator** parses every generated `.py` file's import statements and checks that each imported module resolves to:

1. **Python standard library** (auto-detected via `sys.stdlib_module_names`)
2. **Third-party package in `requirements.txt`** (auto-parsed; handles dash-to-underscore name normalization)
3. **An existing file in the repo**
4. **A file in this generation batch** (so cross-file imports within the batch work)

If none of these match → the import is broken. The validator emits an error in the same `<type> error in '<path>':` format the existing repair loop's grouper can parse, so the LLM gets a second chance to fix the import.

### Why this is reusable across projects

- **Pure AST analysis** — no project-specific assumptions
- **Auto-discovers stdlib** — `sys.stdlib_module_names` is built into Python
- **Auto-discovers third-party deps** — reads whatever's in `requirements.txt`
- **Handles common naming aliases** — `pyyaml`/`yaml`, `PyGithub`/`github`, etc., as standard Python ecosystem facts (not project-specific)
- **No hardcoded paths or names** — works for any app, any project

### Files changed

| File | Change |
|---|---|
| `agents/import_validator.py` | **NEW** — parses imports via Python's `ast` module, classifies each as stdlib / third-party / repo-internal / planned-in-batch / unresolvable. Emits errors in the format the repair loop already understands. |
| `agents/agent2_coder.py` | Renamed `_group_coverage_errors_by_step_def` → `_group_validator_errors_by_file` (with backward-compat alias) — now matches any `error in '<path>':` prefix. New `_collect_repairable_errors` aggregates output from both step-coverage and import validators. Final validator (`_validate_generated_files`) now runs the import check too. Repair loop now handles both error types in one pass. |
| `tests/unit/test_import_validator.py` | **NEW** — 28 unit tests covering: SCRUM-13 regression scenario, stdlib imports, third-party imports, repo-internal imports, planned-in-batch imports, requirements.txt parsing, dotted module paths, edge cases (malformed source, empty input, relative imports, non-Python files). |
| `CHANGES.md` | This entry. |

### Test results

- **148 unit tests pass** (was 120 before adding 28 new tests)
- **1 unrelated pre-existing failure** still unchanged
- **End-to-end repair simulation against the actual SCRUM-13 failure** verified: validator catches 2 broken imports, repair loop regenerates the step def file, retry produces clean imports, final validation passes

### Cumulative validator coverage now

The framework now defends against four LLM failure modes:

| # | Validator | Catches |
|:-:|---|---|
| 1 | Filename consistency (Phase 4) | kebab/snake mismatches between feature files and `feature_path()` calls |
| 2 | Step coverage (Phase 8) | Gherkin steps without matching `@given/@when/@then` |
| 3 | Path policy (v1 hotfix) | LLM trying to overwrite reserved reference files |
| 4 | Import resolution (v3 hotfix) | Imports referencing modules that don't exist anywhere |

All four feed the same self-correcting repair loop with up to 2 retries. If retries exhaust, you get a clear final error explaining what the LLM couldn't fix.

### Honest assessment

I cannot promise this is the last bug. The repair loop and validators defend against the LLM mistakes I've seen in production failures so far. Tomorrow's story might surface a fifth failure mode I haven't anticipated. What I can say:

- All four validators are app-agnostic — onboarding a new app changes nothing here
- The repair pattern is extensible — adding a fifth validator is one new module + one line in `_collect_repairable_errors`
- The error message format is stable — `<type> error in '<path>':` — so future validators integrate without touching the repair loop

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
- ✅ New `docs/APP_INVENTORY_SCHEMA.md` documents the page-inventory JSON shape *(since merged into REUSE_FOR_NEW_PROJECT.md, July 2026)*
- ✅ Zero unit-test regressions: 90/90 runnable tests pass identically before and after

## Files added

| File | Purpose |
|---|---|
| `agents/app_context.py` | New module — central loader for `app_under_test` config. Exposes `AppContext.load()` with helpers for reference files, page inventory, reserved paths. |
| `prompts/app_context.md` | App-specific context block (test users, error messages, page flow). Injected into Agent 1's prompt at runtime. The single file to edit when onboarding a new app's analyst guidance. |
| `docs/GUIDE.md` | Consolidated guide — replaces ARCHITECTURE.md + BRANCH_NAMING.md + CONFIGURATION.md + HUMAN_APPROVAL_GATE.md. |
| `docs/APP_INVENTORY_SCHEMA.md` *(merged into REUSE_FOR_NEW_PROJECT.md, July 2026)* | Documents the JSON shape of `app_inventory/<app>.json`. |
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

- `agents/gherkin_analyzer.py` (renamed from test_inventory.py, June 2026) — has zero SauceDemo coupling. The file is internally well-organized (953 lines but with clear `# ─── ... ───` section headers separating concerns). It has thorough unit-test coverage. **Splitting it was considered and skipped** because the cost (changing imports across the codebase, risking test breakage) exceeds the benefit (no reusability gain — the file is already app-agnostic).
- `agents/jira_client.py` (mostly) — only `_link_to_story` was tightened. The rest is a clean adapter.
- `agents/github_client.py` — already uses targeted `GithubException`. No broad except patterns to tighten.
- `agents/llm_client.py` — already app-agnostic.
- `agents/schemas.py` — already app-agnostic.
- `config/__init__.py`, `config/paths.py` — already app-agnostic.
- All test files in `tests/unit/` — all 90 runnable tests pass identically before and after the refactor.
- All workflow files in `.github/workflows/` — they delegate to Python modules, no SauceDemo references.
- `app_inventory/saucedemo.json` — kept as the canonical example (schema now documented in REUSE_FOR_NEW_PROJECT.md).
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

- **Splitting `gherkin_analyzer.py` (then named test_inventory.py)** into multiple modules. Considered; deferred. The file is well-organized internally and changing imports across the codebase risks breaking tests for no reusability gain.
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