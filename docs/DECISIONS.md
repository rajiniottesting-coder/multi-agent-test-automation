# Architecture Decision Records

Consolidated ADRs, newest first. Each section is an immutable decision record; later notes are appended, history is not rewritten.

---

## ADR-013 — Agent 0: graph-first impact analysis, a human Impact Review, undo by snapshot

### Status

Accepted (2026-10, PRs #126–#139 phases A–E, #163 live mode, #166 context
update, #172–#173 validation findings).

### Context

A story that changes existing behaviour silently invalidates tests other
stories own. Finding them by hand is slow and incomplete, and a test revised
for a change that is later rejected leaves Jira describing behaviour that never
shipped. The pipeline needed a step before Agent 1 that answers "which tests
does this change touch?" without letting a model rewrite tests on its own.

### Decision

1. **Graph first, model second, formula last.** A deterministic impact graph
   (scenario → step → method → selector, built from `# JIRA:` markers and the
   code) and component/text relevance produce the candidates; one model call
   names the change (`ChangeSeeds`) and one judges each candidate
   (`ImpactAssessment`); a weighted score sets the tier. The model's verdict is
   the ceiling (since #173), so structure alone never promotes a test the model
   judged *review* or *unaffected*.
2. **Evidence or nothing.** A verdict that cites no real graph path or verbatim
   step is dropped, and an element key not in the inventory is dropped and
   reported. A graph gap is reported as *unknown*, never as *not impacted*.
3. **Off, then shadow, then live.** The framework default is off. Shadow mode
   posts reports only and Agent 5 scores every prediction, so Agent 0 is
   measured before it writes anything.
4. **A person decides each test.** Live mode opens an Impact Review sub-task;
   nothing is revised until it is Done. Approve, reject and retire are per test.
5. **State in labels and marker comments**, like the rest of the pipeline —
   `impact-check → impact-proposed → ai-ready → impact-applied →
   (merged | impact-reverted)`, with `[agent0:…]` comments as memory.
6. **Undo by snapshot.** Agent 1 snapshots each test before revising it.
   Reconcile restores a snapshot only where the text is still what the change
   wrote; a test edited since is left for a person. A closed PR is acted on
   only when the same close is seen on two scans, and reconcile is its own
   job, because the sweeper restarts stalled PRs by closing and reopening them
   and two concurrent runs must not count as two scans.
7. **Leave an undone story ready to retry** (since #173): its own unshipped
   tests are retired, the pipeline labels reset, the card moved to To Do, and
   the retry steps posted.
8. **Reference material changes through a separate PR.** Wording the story
   replaces and passages it makes untrue are proposed for the inventory and
   `prompts/app_context/` as a context-update PR whose branch carries no issue
   key. Selectors are never edited, and it is merged after deployment.

### Alternatives considered

- **Model-only analysis** — no recall guarantee and no evidence to check; a
  model can name a test that does not exist.
- **Embeddings over scenarios** — adds infrastructure and fuzziness where the
  graph gives exact paths.
- **Undo on the `pull_request: closed` event** — the sweeper's close-and-reopen
  emits the same event and would trigger false undos.
- **One PR for code and context** — the context must wait for deployment while
  the test code must not; one PR would block one or break the other.

### Consequences

- Agent 0 is only as good as the scenario markers and the inventory's
  `components`; `scripts/onboarding_check.py` and `scripts/backfill_markers.py`
  exist for that.
- A change story can produce two PRs. Only the story's own PR closes it.
- An undo takes two scans — the next weekday's scheduled run, or two manual
  runs.
- The graph builder is per test-stack language (`register_graph_builder`); the
  rest of Agent 0 carries over to another stack unchanged.

---

## ADR-012 — Shared step definitions live in `tests/step_defs/conftest.py`

### Status

Accepted (2026-07). Supersedes the cross-file step-reuse assumption documented
in `gherkin_analyzer.py` (2026-05-10).

### Context

Agent 2 generated `features/login_edge_validation.feature` whose scenarios reuse
`Given I am on the SauceDemo login page` — a step already defined in the
reference module `tests/step_defs/test_login.py`. Every validator passed and a PR
was opened. Agent 4 then failed at collection:

```
pytest_bdd.exceptions.StepDefinitionNotFoundError:
Step definition is not found: Given "I am on the SauceDemo login page"
```

The step-coverage validator had been written on the belief that *"pytest-bdd
allows the same step decorator to be defined in any module that pytest collects —
the decorator registers the step globally for the test session… no import or
conftest required."* **That belief is false.**

pytest-bdd implements step definitions as **pytest fixtures**. Fixtures are
module-scoped: a step defined in one step-def module is invisible to every other
module. Verified empirically — a step in a sibling module raises
`StepDefinitionNotFoundError`; the identical step moved to `conftest.py` passes.

This is the "validator passes, runtime fails" class of defect the validator was
explicitly built to prevent (the PR #9 scenario).

### Decision

- **Shared steps and shared page-object fixtures live in
  `tests/step_defs/conftest.py`.** This is pytest's only supported cross-module
  sharing mechanism, and it is mandatory for every application — the failure is a
  property of pytest-bdd, not of any particular app.
- **Location is `tests/step_defs/`, not `tests/`.** Both validators discover
  on-disk step definitions with `tests/step_defs/*.py`. Shared steps in
  `tests/conftest.py` would run correctly but be invisible to the validator,
  producing phantom "missing decorator" errors. Only
  `tests/step_defs/conftest.py` satisfies pytest *and* the validators.
- **Two conftest files, split on the engine/app boundary.** `tests/conftest.py`
  holds Playwright lifecycle and CI plumbing (`browser`, `page`, `base_url`,
  screenshot hook) and is reused unchanged across projects.
  `tests/step_defs/conftest.py` holds the application's step vocabulary and is
  rewritten per app. pytest merges conftests hierarchically, so the step-def
  conftest inherits `page`/`base_url` without redefining them. Both are
  human-owned (`reserved_paths`).
- **Move, do not copy.** Since both validator globs include `conftest.py`,
  keeping duplicate copies of a step in `conftest.py` and `test_login.py` would
  trip the duplicate step-definition guard — even though pytest itself tolerates
  it (module definitions shadow conftest).
- **The reference module keeps at least one locally-defined step.** After moving
  the shared steps out, `test_login.py` would have been a bare `scenarios()`
  call — a poor style exemplar, since it is injected into every Agent 2 prompt. A
  fourth scenario (error dismissal) was added to `login.feature` so the reference
  still demonstrates real step authoring: page-object calls only, no selectors,
  assertion messages, single-line decorators.

### Alternatives Considered

- **Have Agent 2 redefine every step in each generated file.** Works at runtime
  (module-scoped definitions don't collide), but duplicates code, inflates
  tokens, and fights the duplicate-step guard.
- **Put shared steps in `tests/conftest.py`.** Correct for pytest, invisible to
  the validators. Rejected.
- **Import steps between modules.** Not how pytest-bdd resolves steps; fragile
  and non-idiomatic.

### Consequences

- Onboarding a new app gains one mandatory file (REUSE guide, Change 5).
- The rule Agent 2 must follow: *needed by more than one feature → conftest;
  specific to one feature → the paired module.* Documented in the reference
  file's docstring, which is injected into the prompt.
- **Open follow-up:** the step-coverage validator still treats decorators found
  in arbitrary sibling step-def files as available. It should count only
  `conftest.py` plus the paired module, otherwise it can still green-light a file
  that relies on a sibling's step and Agent 4 will catch it at runtime.

### References

- `tests/step_defs/conftest.py`, `tests/step_defs/test_login.py`
- `agents/gherkin_analyzer.py` — "CROSS-FILE STEP REUSE" block (now superseded)
- REUSE_FOR_NEW_PROJECT.md → Change 5

---

## ADR-011 — App-agnostic inventory tooling, page-level errors, and component filtering

### Status

Accepted (2026-07)

### Context

Three related needs surfaced as the framework matured toward genuine reuse across
applications:

1. **Bootstrapping an inventory by hand is slow and error-prone.** A new app needs
   an `app_inventory/<app>.json` describing every page's selectors. Writing it from
   scratch — and keeping it in sync as the app changes — is tedious and drifts.
2. **A flat top-level `common_errors` block doesn't scale.** On a large app it
   becomes a dumping ground, and it's injected into *every* Agent 2 prompt
   regardless of which component the story touches.
3. **Any tooling we add must not re-couple the framework to SauceDemo**, or it adds
   no value for the next project.

### Decision

- **Inventory generation + staleness (`inventory_tools/` + two CLIs).**
  `generate_inventory.py` crawls the live app and emits a draft inventory;
  `check_inventory_staleness.py` diffs the committed inventory against the live DOM.
  The testable logic (selector ranking, naming, family-collapse, diff) is a pure,
  browser-free module; a thin Playwright layer drives the browser.
- **Machine fills only what it can know.** Draft entries populate url, ranked
  selectors, and a page-object guess, and leave `elements_notes`, `key_methods`,
  page-level `errors`, and `components` as *visible stubs* — a crawler cannot infer
  behaviour, intended API, or exact error strings. The staleness checker warns on
  pages missing `elements_notes` (make gaps visible, not silent).
- **Page-level `errors`.** Page-specific error strings live under each page's
  `errors` field instead of a flat `common_errors`. This keeps messages next to the
  screen that raises them and lets them ride the 2.2 component filter automatically.
  `common_errors` is retained for genuinely global errors. Backward compatible —
  nothing in the framework parses errors; the whole inventory is passed to the LLM
  as text.
- **Component-wise filtering (2.2).** `filter_inventory_by_components` injects only
  the pages (and their errors) whose `components` match the story, shrinking prompt
  tokens on large apps. No/unknown components → full inventory (safe default).
- **Zero app coupling.** The test-id attribute set is a configurable `TEST_ID_ATTRS`
  constant (default covers `data-test`, `data-testid`, `data-cy`, and more;
  override with `--test-attrs`); login fields auto-detect by input *type* with
  explicit-selector overrides. Audited: no `saucedemo`/`standard_user`/`secret_sauce`
  or element-name assumptions in any generic file.

### Alternatives Considered

- **A Playwright-MCP generator that reasons about the most stable selector.** More
  powerful, but it breaks the property that only Agent 4 touches the application
  (matters for VPN-restricted clients). Deferred until a plain script sets a
  baseline.
- **Keep a single `common_errors`.** Simpler, but doesn't localise or ride the 2.2
  filter; poor fit for large apps.
- **Hardcode `data-test` (SauceDemo's attribute).** Rejected — defeats reuse.

### Consequences

- New apps bootstrap an inventory in minutes and can gate CI on drift
  (`--fail-on-drift`).
- Large apps pay fewer prompt tokens (pages + errors filter together).
- The generator produces a *draft*, never a finished inventory — human review of
  the stub fields is mandatory and documented.
- Suite grew to 259 unit tests (introspection covers `data-cy`/`data-test` DOMs).

### References

- `inventory_tools/introspect.py`, `inventory_tools/browser.py`
- `scripts/generate_inventory.py`, `scripts/check_inventory_staleness.py`
- `agents/app_context.py :: filter_inventory_by_components`
- REUSE_FOR_NEW_PROJECT.md → App inventory JSON schema

---

## ADR-010 — Sweeper for stalled event-driven agents

### Status

Accepted (2026-07). Builds on ADR-008 (PAT cascade).

### Context

Cron-driven agents (1, 2) self-heal — a failed run retries on the next tick.
Event-driven agents are different: Agent 3 (review) and Agent 4/5 (run + report)
fire on the one-shot `pull_request` event. If that run is cancelled (or never
starts — a throttled runner, an infra blip), the PR is **stranded**: opened but
never reviewed, tested, or reported, with no retry. Recovery was a manual nudge.

### Decision

An hourly workflow (`sweeper.yml` → `scripts/sweep_stalled_prs.py`) lists open
`auto/*` PRs and, for each, checks whether the required workflows
(`agent3-reviewer.yml`, `agent4_runner.yml`) have a **settled** run for the current
head commit. "Settled" = a run that reached a real verdict (success / failure /
timed_out). A stalled PR (no run, or a cancelled/skipped run) is re-triggered.

Two non-obvious choices:

- **Re-trigger = reopen, not `workflow_dispatch`.** Agent 5's report job is gated on
  `github.event_name == 'pull_request'`, so a dispatch re-run would run the tests
  but *skip* the report. Closing-and-reopening emits a real `pull_request:reopened`
  event, re-running the whole chain.
- **Use the PAT (`GH_PAT`), not the built-in token.** GitHub deliberately suppresses
  workflow events triggered by the built-in `GITHUB_TOKEN`, so a reopen with it
  would be a no-op for Agents 3/4. The PAT is user-equivalent (same reason Agent 2
  uses it — see ADR-008).

### Alternatives Considered

- **Push an empty commit** to fire `synchronize`. Works, but pollutes history with
  no-op commits. Reopen leaves the branch clean.
- **Treat any non-success as stalled** and retry. Rejected — a red test suite is a
  *real result* Agent 5 should report, not a stall; retrying it would loop.

### Consequences

- Weekend/overnight stalls self-heal within the hour instead of going unnoticed.
- Loop-safe: settled runs are left alone, and a commit-SHA marker comment
  (`<!-- sweeper:nudged:{sha} -->`) prevents nudging the same commit twice.
- Requires the `GH_PAT` / `GH_REPO` secrets already present for Agent 2.
- 14 unit tests cover the settled/stalled classification logic.

### References

- `.github/workflows/sweeper.yml`, `scripts/sweep_stalled_prs.py`
- ADR-008 (PAT cascade), `tests/unit/test_sweeper.py`

---

## ADR-009 — Agent 2 deduplication engine

### Status

Accepted (2026-05-06)

### Context

Agent 2 (Coder) generates Playwright + pytest-bdd test code from approved
Jira Test Cases. During end-to-end testing on PR #7, two distinct
architectural problems were discovered:

#### Problem 1: No awareness of existing tests

When SCRUM-5 was reprocessed, Agent 2 generated `test_login_validation.py`
alongside the existing `test_login.py`. Agent 2 had no mechanism to
recognize that some of the approved test cases were already covered by
existing scenarios in `features/login.feature`. This led to:

- **Duplicate code generation** — wasted LLM tokens on tests already covered
- **PR clutter** — multiple feature files for what should be a single feature area
- **Test suite bloat** — same end-state asserted multiple times in different files
- **Maintenance burden** — when SauceDemo's login UI changes, multiple
  test files need updating

#### Problem 2: No way to handle modified test cases

The natural solution to Problem 1 — "skip if already covered" — has its
own flaw: if a user modifies a Jira Test Case (adding new validations,
correcting assertions), the dedup logic would silently skip it because
the title still matches an existing scenario. The user's modifications
would never reach the code.

The system needs both:
- A way to **prevent duplicate first-time generation** (Problem 1)
- A way to **explicitly trigger regeneration** when test cases change (Problem 2)

These are related but architecturally distinct concerns.

### Decision

We implement **two separate mechanisms** addressing each concern, both
driven by Jira labels (consistent with the existing label state machine
established in ADR-005).

#### Mechanism 1: Title-Based Deduplication (skip-if-already-coded)

Before invoking the LLM, Agent 2 scans the `features/` directory and
extracts all existing scenario titles. Each approved Test Case from Jira
is compared against this inventory:

- **Match found** → record as "skipped" with reference to existing scenario
- **No match** → add to "new" list for code generation
- **All cases match** → skip PR creation entirely; mark `ai-coded` for idempotency

Matching is by **normalized title** (case-insensitive, whitespace-collapsed).
We deliberately do NOT use semantic matching (e.g., LLM similarity scoring)
because:

1. **Cost** — every dedup check would require an LLM call
2. **Determinism** — title matching is reproducible and debuggable
3. **Conservative bias** — when in doubt, treat as "new" (don't lose work)

#### Mechanism 2: Explicit Regeneration via `ai-regenerate` Label

A new Jira label `ai-regenerate` signals "the test cases under this story
were modified — please regenerate code from scratch."

When Agent 2 sees a story with `ai-regenerate`:

1. **Bypass dedup** — pass empty inventory to filter, so all cases are "new"
2. **New branch** — append `-revN` suffix (rev2, rev3, ...) to preserve old PR
3. **Generate fresh code** — full Stage 1 + Stage 2 LLM flow
4. **Cleanup** — remove `ai-regenerate` label after success (one-shot signal)
5. **Mark complete** — add `ai-coded` label as usual

The `-revN` branch suffix means each regeneration creates a NEW pull
request rather than amending the old one. This:

- Preserves git history (old PR remains as historical record)
- Avoids force-push complications
- Makes review easier (clear "this is iteration 2" semantics)
- Mirrors the pattern used by Renovate, Dependabot, and other production bots

Old PRs are NOT auto-closed. The user reviews, decides which iteration
to merge, and closes obsolete PRs manually.

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                AGENT 2 SCAN (--scan mode)                        │
└──────────────────────────────────────────────────────────────────┘

                ┌───────────────────────────┐
                │ Read config.yaml          │
                │  - selection              │
                │  - regenerate_selection   │
                └───────────┬───────────────┘
                            │
                ┌───────────▼───────────────┐
                │ Pass 1: Normal stories    │
                │ JQL: ai-processed +       │
                │      human-approved +     │
                │      NOT ai-coded +       │
                │      NOT ai-skip +        │
                │      NOT ai-regenerate    │
                └───────────┬───────────────┘
                            │
                ┌───────────▼───────────────┐
                │ Pass 2: Regen stories     │
                │ JQL: ai-processed +       │
                │      human-approved +     │
                │      ai-regenerate +      │
                │      NOT ai-skip          │
                └───────────┬───────────────┘
                            │
                ┌───────────▼───────────────┐
                │ For each story:           │
                │   run(key,                │
                │       is_regenerate=...)  │
                └───────────────────────────┘


┌──────────────────────────────────────────────────────────────────┐
│            run(story_id, is_regenerate=False)                    │
└──────────────────────────────────────────────────────────────────┘

  Fetch test cases from Jira
            │
            ▼
  ┌─────────────────────────┐    is_regenerate=True
  │   is_regenerate?        ├──────────────────────┐
  └─────────┬───────────────┘                      │
            │ False                                │
            ▼                                      ▼
  ┌─────────────────────────┐         ┌────────────────────────┐
  │ scan_features_dir()     │         │ Skip dedup; treat all  │
  │ filter_duplicate()      │         │ test cases as "new"    │
  └─────────┬───────────────┘         └─────────┬──────────────┘
            │                                    │
            ▼                                    │
  ┌─────────────────────────┐                   │
  │ All duplicates?         │                   │
  │  YES → mark ai-coded    │                   │
  │       return early      │                   │
  └─────────┬───────────────┘                   │
            │ NO                                 │
            └──────────────┬─────────────────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ LLM generates code   │
                │ for new_test_cases   │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ validate_filename_   │
                │   consistency()      │
                │   FAIL → raise       │
                └──────────┬───────────┘
                           │
                           ▼
              is_regenerate=True?
                ┌──────────┴──────────┐
                │                     │
                ▼ YES                 ▼ NO
       ┌───────────────────┐   ┌────────────────┐
       │ Branch += -revN   │   │ Branch as-is   │
       └────────┬──────────┘   └────────┬───────┘
                │                        │
                └────────────┬───────────┘
                             ▼
                ┌──────────────────────┐
                │ Create branch        │
                │ Commit files         │
                │ Open PR              │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ jira.add_label(      │
                │   ai-coded)          │
                └──────────┬───────────┘
                           │
              is_regenerate=True?
                ┌──────────┴──────────┐
                │                     │
                ▼ YES                 ▼ NO
       ┌───────────────────┐         (done)
       │ jira.remove_label │
       │   (ai-regenerate) │
       └───────────────────┘
```

### Alternatives Considered

#### A. Semantic similarity matching (rejected)

Use an LLM call to compare each new test case against existing scenarios.
A match would skip generation, no match would proceed.

**Why rejected:**
- Cost: every dedup decision = one LLM call (~$0.001 per call)
- Non-determinism: same input could yield different match decisions
- Over-matching risk: LLM might consider "Login fails" and "Login succeeds"
  as similar (they're not — they test opposite behaviors)
- Hard to debug when wrong

#### B. Hash-based equivalence detection (deferred)

Compute a hash of (title + steps + expected outcomes) for each test case.
Store the hash in Jira (custom field or metadata file in repo). On re-scan,
compare current hash against stored value.

**Why deferred:**
- Requires new infrastructure (where to store the hash?)
- Doesn't help when code drifts from generated form (manual edits)
- More moving parts to maintain
- Title-based dedup + explicit ai-regenerate is sufficient for v1

#### C. Auto-detect modifications via Gherkin step diffing (deferred)

Compare the generated `.feature` file's steps against the current Test
Case's steps. If they differ, regenerate that one scenario in-place.

**Why deferred:**
- Editing existing feature files is risky (LLM might break unrelated scenarios)
- Step matching is fuzzy (Given/When/Then phrasing varies)
- Would require partial-file generation in Agent 2 (not currently supported)
- Adds complexity for a small UX gain over explicit `ai-regenerate`

#### D. Always create new branch, never edit existing PR (chosen for Phase 6)

When ai-regenerate is detected, always create a NEW branch with `-revN`
suffix instead of trying to push to an existing open PR.

**Why chosen:**
- Avoids force-push complications (when histories diverge)
- Makes review easier ("rev2 = my second iteration")
- Preserves audit trail (old PRs left untouched)
- Mirrors industry-standard bot patterns (Renovate, Dependabot)
- Simpler to implement and test

### Consequences

#### Positive

- **Cost reduction** — duplicate cases skipped entirely; no LLM tokens spent
- **Cleaner test suite** — one feature file per feature area (instead of fragmented duplicates)
- **Explicit intent** — `ai-regenerate` makes "redo this" a deliberate user action
- **Idempotent scans** — re-running Agent 2 on the same approved story is now safe (skips)
- **Defense-in-depth** — filename validator catches LLM drift even when prompts fail
- **Audit trail** — old PRs preserved as history; new PRs clearly numbered
- **Architectural clarity** — two distinct mechanisms for two distinct concerns

#### Negative

- **Title fragility** — renaming a Test Case in Jira makes Agent 2 think it's new
  (workaround: add ai-regenerate to force regeneration, or accept the new code)
- **No partial regeneration** — ai-regenerate redoes ALL test cases for a story,
  not just the modified ones (acceptable trade-off for simplicity)
- **PR pollution risk** — frequent regeneration creates many PRs (mitigated by
  manual closure of obsolete PRs)
- **Two separate JQL queries** in scan mode (slightly slower, but more explicit
  than a complex OR-clause)

#### Neutral

- **No change to LLM prompts** for the dedup logic itself (prompts only changed
  for the filename consistency fix in Phase 4)
- **Backwards compatible** — stories without `ai-regenerate` behave exactly as before
- **No external dependencies added** — pure Python regex parsing for Gherkin
  (avoids gherkin-official package)

### Implementation

The implementation is split across six logical phases:

| Phase | Component | Files |
|-------|-----------|-------|
| 1 | Inventory utility | `agents/gherkin_analyzer.py` (scan_features_dir, normalize, find_match) |
| 2 | Dedup filter | `agents/gherkin_analyzer.py` (filter_duplicate_test_cases) |
| 3 | Agent 2 integration | `agents/agent2_coder.py` (run() with dedup check) |
| 4 | Filename validator + prompt fix | `agents/gherkin_analyzer.py` (validate_filename_consistency), `prompts/agent2_coder_plan.md` |
| 5 | Comprehensive test suite | `tests/unit/test_validators.py`, `tests/unit/test_agent2_dedup_integration.py` |
| 6 | ai-regenerate label support | `config/config.yaml`, `agents/agent2_coder.py` (is_regenerate param), `agents/jira_client.py` (remove_label), `agents/github_client.py` (branch_exists) |

### User Workflow

#### First-time coding (existing flow, now with dedup)

```
1. PM creates story SCRUM-5 with label `ai-ready`
2. Agent 1 generates Test Cases, marks parent `ai-processed`
3. User reviews Test Cases on Jira, adds `human-approved`
4. Agent 2 picks up SCRUM-5:
   - Reads test cases from Jira
   - Scans features/ for existing scenarios
   - Filters out duplicates (if any)
   - Generates code for new cases
   - Validates filename consistency
   - Opens PR
   - Marks `ai-coded`
```

#### Modified test cases (new flow with ai-regenerate)

```
1. User edits Test Case SCRUM-9 on Jira (adds new validation step)
2. User adds `ai-regenerate` label to parent story SCRUM-5
3. Agent 2 picks up SCRUM-5 in regen pass:
   - Skips dedup check
   - Generates fresh code for ALL test cases
   - Validates filename consistency
   - Creates branch `auto/SCRUM-5-login-rev2`
   - Opens new PR
   - Removes `ai-regenerate` label
   - Adds `ai-coded` label (back to normal)
4. User reviews new PR, decides to merge it or close prior PRs
```

#### Permanent skip (existing flow, unchanged)

```
1. User decides this story isn't a good AI candidate
2. User adds `ai-skip` label
3. Agent 2 ignores the story in both normal and regen passes
```

### Test Coverage

The test suite covers:

| Module / Behavior | Tests |
|-------------------|-------|
| Title normalization | 8 tests covering case, whitespace, punctuation, edge cases |
| Gherkin parsing | 12 tests covering Scenario, Scenario Outline, Background, comments, tags, indentation, real-world feature file |
| Directory scanning | 7 tests including missing dir, non-feature files, subdirectories |
| Match lookup | 9 tests covering exact match, case-insensitive, whitespace-insensitive, no-match, edge cases |
| Dedup filter | 9 tests covering all-new, all-duplicate, mixed, empty, malformed input, ordering |
| Filename validator | 10 tests covering PR #7 bug pattern, correct naming, non-step-def files, multi-error reporting |
| Phase 6 integration | 7 tests covering run() signature, regen logic, branch -revN, label cleanup |
| Module-level | 4 import sanity checks |

**Total: 75 tests**, all passing in <3 seconds.

### Verification

After applying this change, verify with:

```bash
## Unit tests pass
python -m pytest tests/unit/ -v
## Expected: 75 passed

## Existing BDD tests still collect
python -m pytest --collect-only -q tests/step_defs/
## Expected: 3 tests collected

## All modules import
python -c "import agents.agent2_coder, validators.gherkin_analyzer, integrations.jira_client, integrations.github_client"
## Expected: no errors

## Agent 2 CLI works
python -m agents.agent2_coder --help
## Expected: usage message
```

### Future Work

This design intentionally keeps scope tight. Future iterations may add:

- **Hash-based change detection** (Alternative B above) to auto-trigger regeneration
- **Partial regeneration** — regenerate only the modified Test Case's scenario
- **PR auto-closure** — close obsolete `-revN-1` PRs when `-revN` opens
- **Cross-story dedup** — detect when SCRUM-5 and SCRUM-12 cover the same scenario
- **Semantic dedup as fallback** (Alternative A above) — only when title doesn't match
  but content might overlap; gated behind a config flag

These are deferred until concrete user feedback shows they're needed.

### References

- ADR-005: Jira label state machine (foundation for this work)
- PR #7: The failed PR that triggered this design effort
- `prompts/agent2_coder_plan.md`: Updated to enforce snake_case for files
- `agents/gherkin_analyzer.py`: Implementation of all dedup primitives
---

## ADR-008 — GitHub PAT for cross-workflow cascade

### Status

Accepted (2026-05-06)

### Context

Agent 2 (Coder) opens pull requests on the project's GitHub repository as
the final step of its workflow. Those PRs are intended to trigger three
downstream workflows:

- **Agent 3 (Reviewer)** — runs on `pull_request: opened/synchronize`
- **Agent 4 (Runner)** — runs on `pull_request: opened/synchronize`
- **Agent 5 (Reporter)** — runs as a job within Agent 4's workflow

This event-driven cascade is the core of the system's choreography
pattern (ADR-004). Without it, the human must manually trigger Agents
3/4/5 after every Agent 2 run, defeating the purpose of automation.

#### The problem we hit

During end-to-end testing on PR #7 and PR #8, we observed that **no
downstream workflows were firing** after Agent 2 successfully opened
a PR. The PR appeared correctly on GitHub, but the "Checks 0" tab
remained empty — Agents 3/4/5 never got the `pull_request` event.

Investigation revealed this is **deliberate GitHub behavior**, not a
bug in our code. From GitHub's official documentation:

> When you use the repository's GITHUB_TOKEN to perform tasks, events
> triggered by the GITHUB_TOKEN, with the exception of workflow_dispatch
> and repository_dispatch, will not create a new workflow run. This
> prevents you from accidentally creating recursive workflow runs.

In plain terms: **GitHub deliberately suppresses workflow events when a
PR is opened by the built-in `GITHUB_TOKEN`** to prevent infinite
recursion (where Workflow A could open a PR, triggering Workflow B,
which opens another PR, triggering Workflow A...).

This is a useful safety mechanism for general-purpose automation, but
our system architecturally REQUIRES the cascade to fire.

### Decision

Replace `secrets.GITHUB_TOKEN` with a fine-grained Personal Access Token
stored as `secrets.GH_PAT` in Agent 2's workflow. GitHub treats PAT-based
PR creation as user-equivalent (because PATs are owned by users), so
PR events fire normally and downstream workflows trigger as expected.

#### PAT Specification

| Aspect | Choice |
|---|---|
| Token type | **Fine-grained PAT** (modern, principle of least privilege) |
| Repository scope | **`multi-agent-test-automation` only** (single repo) |
| Permissions | **Contents: Read and write** (create branches, commit files) |
|  | **Pull requests: Read and write** (open PRs) |
|  | **Metadata: Read** (auto-included, required by GitHub) |
| Expiration | **Subject to user choice; rotation reminder set in calendar** |
| Storage | **GitHub repo secret named `GH_PAT`** |

We deliberately do NOT grant:
- `Workflows: Write` — Agent 2 doesn't modify `.github/workflows/*`
  files. If the LLM ever tried to, the existing `RESERVED_PATHS` check
  in agent2_coder.py would block it. Failing safe is good.
- `Issues: Write` — Agent 2 only operates on PRs, not issues.
- `Actions: Write` — Agent 2 doesn't trigger workflows directly; the
  cascade is event-driven through PR creation.
- Org/admin access — single-repo scope is sufficient.

#### Implementation

Single-line change in `.github/workflows/agent2_coder.yml`:

```yaml
## BEFORE (cascade suppressed):
GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

## AFTER (cascade fires):
GITHUB_TOKEN: ${{ secrets.GH_PAT }}
```

The Python code (`agents/github_client.py`) is unchanged — it reads
`GITHUB_TOKEN` from env, we just feed it a different value.

### Alternatives Considered

#### A. Empty-commit workaround (rejected)

After Agent 2 opens a PR, manually push an empty commit from a user
account. The push (from the user's PAT) re-triggers `pull_request:
synchronize` events, firing the cascade.

**Why rejected:**
- Manual, not scalable
- Requires a human to babysit every Agent 2 run
- Defeats the purpose of automation
- "Empty commit to trigger CI" is an anti-pattern; reviewers shouldn't
  see commits with no semantic value

#### B. GitHub App authentication (deferred)

Create a GitHub App with explicit permissions, install on the repo, use
its short-lived installation token. Apps are treated as user-equivalent
for event firing.

**Why deferred:**
- ~2 hours of setup vs ~5 minutes for PAT
- More secure (auto-rotating tokens, scoped install) but overkill for
  a single-developer side project
- Better suited if/when this project becomes multi-developer or
  organization-owned

#### C. Scheduled trigger instead of event-driven (rejected)

Replace the `pull_request` triggers on Agents 3/4/5 with `schedule:`
(cron) triggers that periodically scan for new PRs.

**Why rejected:**
- Adds latency (5+ minute delay vs near-instant)
- Wastes runner minutes on no-op scans
- Loses the choreography pattern's benefits
- Polling is an inferior pattern to events

#### D. Continue with GITHUB_TOKEN + accept manual triggers (rejected)

Document the limitation: "after Agent 2 opens a PR, manually trigger
Agent 3 from the Actions UI."

**Why rejected:**
- Operationally bad
- Removes the multi-agent automation story from the architecture
- Not architect-quality

### Consequences

#### Positive

- **Cascade fires automatically** — Agents 3/4/5 trigger on every Agent 2 PR
- **Demonstrates production-grade event-driven architecture** in portfolio
- **Single-line change** with clear documentation trail
- **Rolling back is trivial** if PAT causes issues (revert to GITHUB_TOKEN)
- **Aligns with industry pattern** — Renovate, Dependabot, and similar
  bots also use PATs/Apps for the same reason

#### Negative

- **PR attribution shifts** — PRs now appear as opened by the PAT owner
  (the human user) rather than `github-actions[bot]`. Mitigated by:
  - The PR body explicitly states "*This PR was automatically generated
    by Agent 2 (Coder) from SCRUM-X.*"
  - Commit messages are prefixed `[Agent 2]` for clarity
  - In a team setting, this would be a reason to prefer GitHub Apps
    (Alternative B); for single-developer, it's acceptable
- **Token rotation responsibility** — PATs expire (max 1 year for
  fine-grained). A calendar reminder is set ~2 weeks before expiry to
  prevent silent breakage.
- **Compromise blast radius** — A leaked PAT grants write access to the
  scoped repo. Mitigated by:
  - Repository-scoped (not all-repos)
  - Minimum permissions (Contents + PRs only)
  - Stored as a GitHub secret (encrypted at rest, not visible to
    workflow code)

#### Neutral

- **GitHub permissions:** Repository setting "Allow GitHub Actions to
  create and approve pull requests" is still required (separate setting).
  Both must be enabled.
- **No code changes required** — Python code is portable across token types.

### Rotation Strategy

| When | What |
|---|---|
| At PAT creation | Set calendar reminder 2 weeks before expiry |
| 2 weeks before expiry | Generate new PAT with same permissions |
| Day of rotation | Update `GH_PAT` secret in repo, verify Agent 2 still works |
| Day after rotation | Revoke old PAT in GitHub UI |

If a rotation is missed and the PAT expires:
- Agent 2's workflow fails on the GitHub API call (clear error in logs)
- The system fails CLOSED (no broken PRs created)
- Rotate and re-run — no data loss

### Verification

After applying this ADR's changes:

1. `secrets.GH_PAT` exists in the repo
2. `agent2_coder.yml` references `secrets.GH_PAT` (not `GITHUB_TOKEN`)
3. Repo setting "Allow GitHub Actions to create and approve PRs" is enabled
4. Trigger Agent 2 on a test story
5. Confirm PR opens AND check tab shows Agent 3/4 starting within ~30 seconds
6. Confirm Agent 5 posts comment to Jira after Agent 4 completes

### References

- ADR-004: Choreography over orchestration (the pattern this fix preserves)
- GitHub docs: [Triggering a workflow from a workflow](https://docs.github.com/en/actions/using-workflows/triggering-a-workflow#triggering-a-workflow-from-a-workflow)
- Renovate documentation on PAT requirements (similar architecture)
- PR #7 and PR #8: Real-world incidents that motivated this ADR