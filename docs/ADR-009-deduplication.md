# ADR-009: Test Code Deduplication and Regeneration

## Status

Accepted (2026-05-06)

## Context

Agent 2 (Coder) generates Playwright + pytest-bdd test code from approved
Jira Test Cases. During end-to-end testing on PR #7, two distinct
architectural problems were discovered:

### Problem 1: No awareness of existing tests

When SCRUM-5 was reprocessed, Agent 2 generated `test_login_validation.py`
alongside the existing `test_login.py`. Agent 2 had no mechanism to
recognize that some of the approved test cases were already covered by
existing scenarios in `features/login.feature`. This led to:

- **Duplicate code generation** — wasted LLM tokens on tests already covered
- **PR clutter** — multiple feature files for what should be a single feature area
- **Test suite bloat** — same end-state asserted multiple times in different files
- **Maintenance burden** — when SauceDemo's login UI changes, multiple
  test files need updating

### Problem 2: No way to handle modified test cases

The natural solution to Problem 1 — "skip if already covered" — has its
own flaw: if a user modifies a Jira Test Case (adding new validations,
correcting assertions), the dedup logic would silently skip it because
the title still matches an existing scenario. The user's modifications
would never reach the code.

The system needs both:
- A way to **prevent duplicate first-time generation** (Problem 1)
- A way to **explicitly trigger regeneration** when test cases change (Problem 2)

These are related but architecturally distinct concerns.

## Decision

We implement **two separate mechanisms** addressing each concern, both
driven by Jira labels (consistent with the existing label state machine
established in ADR-005).

### Mechanism 1: Title-Based Deduplication (skip-if-already-coded)

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

### Mechanism 2: Explicit Regeneration via `ai-regenerate` Label

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

## Architecture Diagram

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

## Alternatives Considered

### A. Semantic similarity matching (rejected)

Use an LLM call to compare each new test case against existing scenarios.
A match would skip generation, no match would proceed.

**Why rejected:**
- Cost: every dedup decision = one LLM call (~$0.001 per call)
- Non-determinism: same input could yield different match decisions
- Over-matching risk: LLM might consider "Login fails" and "Login succeeds"
  as similar (they're not — they test opposite behaviors)
- Hard to debug when wrong

### B. Hash-based equivalence detection (deferred)

Compute a hash of (title + steps + expected outcomes) for each test case.
Store the hash in Jira (custom field or metadata file in repo). On re-scan,
compare current hash against stored value.

**Why deferred:**
- Requires new infrastructure (where to store the hash?)
- Doesn't help when code drifts from generated form (manual edits)
- More moving parts to maintain
- Title-based dedup + explicit ai-regenerate is sufficient for v1

### C. Auto-detect modifications via Gherkin step diffing (deferred)

Compare the generated `.feature` file's steps against the current Test
Case's steps. If they differ, regenerate that one scenario in-place.

**Why deferred:**
- Editing existing feature files is risky (LLM might break unrelated scenarios)
- Step matching is fuzzy (Given/When/Then phrasing varies)
- Would require partial-file generation in Agent 2 (not currently supported)
- Adds complexity for a small UX gain over explicit `ai-regenerate`

### D. Always create new branch, never edit existing PR (chosen for Phase 6)

When ai-regenerate is detected, always create a NEW branch with `-revN`
suffix instead of trying to push to an existing open PR.

**Why chosen:**
- Avoids force-push complications (when histories diverge)
- Makes review easier ("rev2 = my second iteration")
- Preserves audit trail (old PRs left untouched)
- Mirrors industry-standard bot patterns (Renovate, Dependabot)
- Simpler to implement and test

## Consequences

### Positive

- **Cost reduction** — duplicate cases skipped entirely; no LLM tokens spent
- **Cleaner test suite** — one feature file per feature area (instead of fragmented duplicates)
- **Explicit intent** — `ai-regenerate` makes "redo this" a deliberate user action
- **Idempotent scans** — re-running Agent 2 on the same approved story is now safe (skips)
- **Defense-in-depth** — filename validator catches LLM drift even when prompts fail
- **Audit trail** — old PRs preserved as history; new PRs clearly numbered
- **Architectural clarity** — two distinct mechanisms for two distinct concerns

### Negative

- **Title fragility** — renaming a Test Case in Jira makes Agent 2 think it's new
  (workaround: add ai-regenerate to force regeneration, or accept the new code)
- **No partial regeneration** — ai-regenerate redoes ALL test cases for a story,
  not just the modified ones (acceptable trade-off for simplicity)
- **PR pollution risk** — frequent regeneration creates many PRs (mitigated by
  manual closure of obsolete PRs)
- **Two separate JQL queries** in scan mode (slightly slower, but more explicit
  than a complex OR-clause)

### Neutral

- **No change to LLM prompts** for the dedup logic itself (prompts only changed
  for the filename consistency fix in Phase 4)
- **Backwards compatible** — stories without `ai-regenerate` behave exactly as before
- **No external dependencies added** — pure Python regex parsing for Gherkin
  (avoids gherkin-official package)

## Implementation

The implementation is split across six logical phases:

| Phase | Component | Files |
|-------|-----------|-------|
| 1 | Inventory utility | `agents/test_inventory.py` (scan_features_dir, normalize, find_match) |
| 2 | Dedup filter | `agents/test_inventory.py` (filter_duplicate_test_cases) |
| 3 | Agent 2 integration | `agents/agent2_coder.py` (run() with dedup check) |
| 4 | Filename validator + prompt fix | `agents/test_inventory.py` (validate_filename_consistency), `prompts/agent2_coder_plan.md` |
| 5 | Comprehensive test suite | `tests/unit/test_test_inventory.py`, `tests/unit/test_agent2_dedup_integration.py` |
| 6 | ai-regenerate label support | `config/config.yaml`, `agents/agent2_coder.py` (is_regenerate param), `agents/jira_client.py` (remove_label), `agents/github_client.py` (branch_exists) |

## User Workflow

### First-time coding (existing flow, now with dedup)

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

### Modified test cases (new flow with ai-regenerate)

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

### Permanent skip (existing flow, unchanged)

```
1. User decides this story isn't a good AI candidate
2. User adds `ai-skip` label
3. Agent 2 ignores the story in both normal and regen passes
```

## Test Coverage

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

## Verification

After applying this change, verify with:

```bash
# Unit tests pass
python -m pytest tests/unit/ -v
# Expected: 75 passed

# Existing BDD tests still collect
python -m pytest --collect-only -q tests/step_defs/
# Expected: 3 tests collected

# All modules import
python -c "import agents.agent2_coder, agents.gherkin_analyzer, agents.jira_client, agents.github_client"
# Expected: no errors

# Agent 2 CLI works
python -m agents.agent2_coder --help
# Expected: usage message
```

## Future Work

This design intentionally keeps scope tight. Future iterations may add:

- **Hash-based change detection** (Alternative B above) to auto-trigger regeneration
- **Partial regeneration** — regenerate only the modified Test Case's scenario
- **PR auto-closure** — close obsolete `-revN-1` PRs when `-revN` opens
- **Cross-story dedup** — detect when SCRUM-5 and SCRUM-12 cover the same scenario
- **Semantic dedup as fallback** (Alternative A above) — only when title doesn't match
  but content might overlap; gated behind a config flag

These are deferred until concrete user feedback shows they're needed.

## References

- ADR-005: Jira label state machine (foundation for this work)
- PR #7: The failed PR that triggered this design effort
- `prompts/agent2_coder_plan.md`: Updated to enforce snake_case for files
- `agents/gherkin_analyzer.py`: Implementation of all dedup primitives