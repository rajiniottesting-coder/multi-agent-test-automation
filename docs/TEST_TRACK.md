# Test track: live validation of everything built

Every implementation is first proven offline (unit tests, sandbox runs against
a fake Jira and repo host, deliberate breaks). This file tracks the second half:
**the live check of each one against the real Jira, GitHub Actions, the model
gateway and the application under test.**

All live testing is done **at the end, after the implementation work, in the
grouped sessions below**, so one story run proves as many items as possible.

**Rules**

1. Every fix or feature adds its rows here when it is built: status ⬜, the PR
   and fix id (`F-n`) in *Built in*. A unit test fails if a fix marked
   **Done** in [VALIDATION_AND_KNOWN_GAPS.md](./VALIDATION_AND_KNOWN_GAPS.md) §4
   has no row here.
2. Before a session, read each row's expected result; change it first if it
   no longer matches the design - never after the run.
3. Record the result in the row: ✅ with the date and evidence (run link,
   issue key, PR number), or ❌ with the gap id opened for it in
   VALIDATION_AND_KNOWN_GAPS.md §3. A row with sub-checks passes only when all
   of them pass.
4. A failure is fixed like any gap (a fix, its tests, its own rows here), then
   the row is run again.

**Status:** ⬜ not run · ✅ passed · ❌ failed (gap id) · ➖ partly (which part)

---

## Sessions (in this order)

| Session | Setup | Groups and rows | Notes |
|---|---|---|---|
| **S1** Agent 0 analysis, cheapest first | Label SCRUM-205, SCRUM-204, SCRUM-207 and new held-out stories H1, H2, H3, H5 `impact-check`; one full scan; a hand-made PR touching a page object and an inventory selector; one manual Agent 0 run with `mode` = `drift` | TG-1 | Analysis only: no PRs merged. SCRUM-187 is checked with `python -m agents.agent0_impact --story SCRUM-187 --dry-run` |
| **S2** A change story to the end | SCRUM-229 (2 owners) re-run from its review; then SCRUM-206 retried | TG-2, part of TG-4 | Was UC-2 and UC-6 |
| **S3** Two new stories in flight | P1 (labelled `impact-check`), P2 (same page object as P1) | TG-3 (E4, E9), TG-4 (E6-E8), TG-1 (H4) | Was UC-3 |
| **S4** Several stories in one scan | Three stories eligible in one Agent 1/2 scan (the first set up to fail), a regeneration, two change stories touching one test case, a new story's PR closed | TG-4 (M1-M3, G1, G2), TG-3 (E26) | Was UC-5 |
| **S5** The consolidated run | One new story whose feature is not in the inventory or the notes yet (ideally a new page too), one change story removing an element; the nights around its deployment | TG-3, TG-5, the rest of TG-2 | Was UC-7. Runs over several days: drift nights before and after deployment |
| **S6** Nights on `main` | Nothing to set up - the nightly run; one night with a test broken on purpose on a throw-away branch merged and reverted, or an existing failure | TG-7 | Runs in parallel with S5's nights |
| **S7** Operations | The health issue created by hand first; induced failures one at a time (below); the budget lowered for one story and one day, then restored | TG-8 | Each induced failure is undone right after its row |
| **S8** Opportunistic | Any PR or nightly run during a 5xx burst from the site, or with a flaky test | TG-6 | Checked whenever it happens; I8 watched throughout |

---

## TG-1 · Change stories: Agent 0's analysis (S1)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| A4 | A-series | SCRUM-205 back-to-top arrow | Nothing affected → `ai-ready`; an unchanged re-run is skipped (stage 0); the no-Component path is reported | ⬜ | |
| A5 | A-series | SCRUM-204 search ignores case and extra spaces | Stays inside one owner; tests that still hold are not must-update | ⬜ | |
| A6 | A-series | SCRUM-207 clearer wrong-password error | Unmarked legacy tests reported for revision by hand; nothing to review | ⬜ | |
| H1 | Held-out | A wording change Agent 0 has never seen (not SCRUM-203) | Matches the result written down before the run | ⬜ | |
| H2 | Held-out | A new validation rule on an existing form | Matches the result written down before the run; E13 is checked on it | ⬜ | |
| H3 | Held-out | A removed field on another page | Matches the result written down before the run | ⬜ | |
| H4 | Held-out | A new feature on a new page (S3's P1) | Nothing affected → `ai-ready` | ⬜ | |
| H5 | Held-out | A story with no Component | Whole-suite analysis, the no-Component comment once | ⬜ | |
| P6 | #186 | SCRUM-187 re-analysed (dry run) | No false "review" rows | ⬜ | |
| B | Run B | A PR changing a page-object method and an inventory selector | Agent 0 posts the affected tests on the PR, no model call; the browser runs (runtime file changed) | ⬜ | |
| C | Run C | Agent 0 with `mode` = `drift` | Opens or updates the maintenance story (`inventory-drift`); scan and reconcile are skipped | ⬜ | |
| S1-R | Stage 0 | The S1 scan run a second time | Every story skipped, no model call | ⬜ | |

## TG-2 · Change stories: the full cycle (S2, S5)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E1 | #199 | An owner's `ai-update` deletes a test case whose scenario held a step's last use | The step function is commented out and listed in the PR; the final gate passes | ⬜ | |
| E2 | #200 | Close the change PR with `reconcile.closed_scans: 1` | Undone on the first scan that sees the close | ⬜ | |
| E3 | #200 | Agent 5's cost table on the change story | An Agent 0 row (analysis and context update); Agent 1 did not reset it | ⬜ | |
| E5 | #200 | A notes-only context-update PR | Unit suite only, no Agent 5, Agent 3 offers no runner evidence | ⬜ | |
| E10 | #201 | `ai-update` on an owner while the story PR changes its feature or step file | Waits before any model call | ⬜ | |
| E11 | #209 | SCRUM-206 retried (removes a field) | Agent 1's coverage map covers AC1 with a step asserting the field is absent; the revised tests alone are rejected | ⬜ | |
| E12 | #209 | SCRUM-206's PR | The scenario carries the absence step, asserted on a loaded page (`is_loaded() and is_gone(...)`); against the undeployed application exactly that step fails (L20) | ⬜ | |
| E13 | #209 | H2 (a limit or restriction) | The coverage comment lists a rejection step for it | ⬜ | |
| E14 | #212 | PR #211 re-reviewed (push or re-run Agent 3) | Red on the absence step only; the card-click finding lowered with "scenario ... passed"; review advisory | ⬜ | |
| E20 | F-10, #225 | S5's change story: `[agent0:context-update]` run | Reads only `core.md`, its Component modules and their pages' notes (prompt in the run log); no rewrite of another module in the PR | ⬜ | |
| E22 | F-11, #225 | S5's removal story | Context-update PR declares the element in `removed` (note `REMOVED by …`); after deployment the nightly check shows `GONE`, not `STALE`; Agent 0 raises no affected test for it; once the absence test is retired the next inventory-update PR deletes the key | ⬜ | |

## TG-3 · New stories: Agents 1-5 (S3, S4, S5)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E4 | #200 | Agent 1's test cases | They carry the story's Components | ⬜ | |
| E9 | #201 | A test case `[Positive] <title>` whose scenario exists without a marker | Skipped by title, listed in the PR and the story comment as needing its marker, without `ai-incomplete` | ⬜ | |
| E16 | #215 | SCRUM-187 on the next scan (persistent-state rule) | One `[agent2:blocked]` comment naming the rule, then `[BLOCK]` with no model call on later scans; a new signed-in draft stating a cart quantity is sent back by Agent 1 | ➖ | Coding once step 7 was fixed: V8 |
| E21 | F-8, #225 | S5's new story merged | Story Done on merge moves it to Done; one `context-update/<key>-notes-<hash>` PR adds its facts under its Component module (a new module for a new Component) and one `[agent0:context-addition]` comment; nothing repeated; a second run does nothing; a merged `ai-update` of its test cases proposes again; cost on the story | ⬜ | |
| E23 | F-9, #225 | A notes addition that pushes a module over `module_budget_chars` | The PR body says so and its unit-suite check fails until the module is condensed in the same PR; `scripts.onboarding_check` reports `notes: size` / `notes: repetition` | ⬜ | |
| E24a | F-13, #227 | S5's story: one test case needs an element not in the inventory | The PR opens with the others; the body lists it under *Approved test cases not automated* with the plan's `Skipped:` reason (or "no reason given" - note which); one `[agent2:incomplete]` comment; `ai-incomplete` beside `ai-coded`; the scan summary says `not automated: <KEY>` | ⬜ | |
| E24b | F-13, #227 | The PR's feature file | Each `# JIRA:` marker sits on the scenario that tests that test case (L31) | ⬜ | |
| E24c | F-13, #227 | One more test case whose summary repeats another story's marked scenario title on `main` | Listed as a title clash naming that test case; counted as not automated | ⬜ | |
| E24d | F-13, #227 | The element reaches the inventory, the PR merges, then `ai-update` | Only the missing scenario is appended; `ai-incomplete` comes off | ⬜ | |
| E24e | F-13, #227 | A story whose only test case needs a missing element (`--dry-run` is enough) | No PR; an `[agent2:blocked]` comment naming it | ⬜ | |
| E25a | F-12, #229 | Before deployment: `scripts.plan_inventory element ...` (and `page ...`) | The onboarding check is clean; Agent 2 uses the keys and its PR lists *Uses planned elements - not deployed yet*; its browser run is red on exactly those steps | ⬜ | |
| E26 | F-16, #230 | A new story's PR closed without merging | First scan: one `closed-unmerged` comment, nothing else; reopen → nothing; close again for two scans → `story-reset` comment, `human-approved` / `ai-coded` / `ai-incomplete` / `tests-run` off, `ai-processed` kept, card in To Do, test cases unchanged; not picked by Agent 2; add `human-approved` → coded again in a new PR | ⬜ | |

## TG-4 · Stories in flight and scans (S3, S4)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E6 | #201 | P2 writes the page object P1's open PR changes | P2 waits after the plan; one `[agent2:waiting]` note across scans; extends the file after P1 merges | ⬜ | |
| E7 | #201 | A P2 test case whose scenario P1's open PR adds | Waits before the plan, no model call | ⬜ | |
| E8 | #201 | Two PRs open at once | The later browser run waits its turn (cap 900 s) | ⬜ | |
| M1 | F-3, #230 | Three stories in one scan, the first set up to fail | The failing story's ledger shows `Agent 2 (Coder, initial) (failed)` with its calls; the next story's comment shows only its own | ⬜ | |
| M2 | F-4, #230 | Three eligible, `max_stories_per_run: 2` | Two run, the third `[DEFER]` and taken by the next scan; the job ends inside 25 minutes | ⬜ | |
| M3 | F-5, #230 | A PR whose only blocking finding is a predicted failure, queued behind another PR's browser run | Agent 3 still reads Agent 4's result (log: "waiting up to 1380s") | ⬜ | |
| G1 | F-1, #230 | A regeneration whose orphan cleanup edits a page object another open PR changes | `[WAIT]` naming that file, no branch | ⬜ | |
| G2 | F-2, #230 | Change story A handed over (no PR yet), change story B analysed after | B's row for the shared test reads "blocked by A"; B's hand-over of an approved row waits ("being revised by another change in progress") until A's PR merges or is undone | ⬜ | |

## TG-5 · Inventory and app knowledge, nightly (S5)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E19a | G12, #224 | A drift run with something applicable | One `inventory-update/<date>` PR with replaced / added / removed tables and the kept, held, no-durable-selector and refused lists; Agents 3 and 4 green on it | ⬜ | |
| E19b | #224 | The same findings the next night | The PR is left alone | ⬜ | |
| E19c | #224 | New findings | The old PR closed with a comment, a new dated PR (old branch deleted, or left if the ruleset forbids it) | ⬜ | |
| E19d | #224 | A commit to the PR's branch | Never replaced; one `kept-edited` comment; no second PR | ⬜ | |
| E19e | #224 | A stale key an open story PR names | Kept, not removed | ⬜ | |
| E19f | #224 | An added hidden element or family | Carries `conditional` / `multi_match`; not undone the next night | ⬜ | |
| E19g | #224 | Shadow mode or `dry_run` | The body printed, no PR | ⬜ | |
| E25b | F-12, #229 | Nights before deployment | `verify_locators` shows `PLAN` / `PLANNED PAGE`; no stale or unreachable entry for them in the drift report; the update PR lists them only under *Planned, not live yet* | ⬜ | |
| E25c | F-12, #229 | First night after deployment | The PR confirms them (*Planned elements now live*), drops `planned_page`, adds the new page's other live elements | ⬜ | |
| E25d | G14, #229 | Shared elements | The footer field of PR #228 listed under *Not added - already covered on another page* (`home.subscribe_email_input`), never added; a header/footer element no key covers is listed once under *new on every page* | ⬜ | |
| E25e | L25, #229 | Unlisted pages | The PR lists pages the application links to that the inventory lacks | ⬜ | |
| E25f | F-12, #229 | A placeholder at a planned page's url (no planned element on it) | That page is not changed | ⬜ | |

## TG-6 · Test runs: retries, outages, flakes (S8)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E15 | #213 | A PR run while the site refuses some CI requests | Retried page loads log `succeeded on attempt N`; a re-run test is listed by *Keep only the final attempt*; Agent 5 counts each test once | ⬜ | |
| E17 | #215 | A PR run during a 5xx burst | A test whose own request was refused fails as `ApplicationUnavailableError` naming it, is re-run, reads "application temporarily unavailable"; a plain assertion failure is not re-run | ⬜ | |
| E28 | F-7, #231 | The same run (still failing after the retries) | Under *Application unavailable (not test failures)* in the summary; Agent 5's *Not judged* warning and section; not an outside failure; verdict `unavailable` when nothing else failed; the check still red; Agent 3 lowers no prediction on it | ⬜ | |
| E29a | F-19, #231 | A test that fails, then passes on the retry | *Retry failed tests once* re-runs exactly the failures; the run is green; summary and Agent 5 list it under *Passed only on the retry (flaky)* with its first failure; the health issue's *Flaky tests* table counts it, no comment | ⬜ | |
| E29b | F-19, #231 | A test failing twice | The run stays red (*Decide the E2E result*) | ⬜ | |
| E29c | F-19, #231 | More than 10 failures | No retry ("not retrying") | ⬜ | |
| E29d | F-19, #231 | A green run with retry skipped | *Retry* skipped, *Decide* green | ✅ | PR #231 runs and the merge push run 40516210923 (27 Oct) |
| I8 | Open defect | The live-site add-to-cart flake | Still seen with turn-taking? The failure lists the action requests; with F-19 a pass on the retry is recorded as flaky | ⬜ | |

## TG-7 · Runs on `main` and defects (S6)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E30a | F-21, #231 | The 03:10 IST nightly run | Unit gate and the whole E2E with the retry; artifact; summary; no story report | ⬜ | |
| E30b | F-21, #231 | A PR opened during it / it opened during a PR run | The later one waits its turn | ⬜ | |
| E30c | F-21, #231 | A push to `main` during it | Does not cancel it | ⬜ | |
| E31a | F-22, #231 | A test failing on `main` | One Bug (`ai-defect`, `ai-defect-<hash>`) naming the test, its test case and owning story, cause, fix, failure and run link | ⬜ | |
| E31b | F-22, #231 | The same failure the next night | The same Bug, times 2, no comment | ⬜ | |
| E31c | F-22, #231 | It passes, then fails again | `ai-defect-passing` and one "Suggest closing" comment; then the label off and "Failing again" | ⬜ | |
| E31d | F-22, #231 | An outage night | No Bug; one `application-unavailable-on-main` alert, resolved the next clean night | ⬜ | |
| E31e | F-22, #231 | A flaky pass on `main` | No Bug; recorded as a flake; not "passing again" | ⬜ | |
| E31f | F-22, #231 | A clean run on `main` | Nothing written to Jira | ✅ | Merge push run 40516210923 (27 Oct): E2E and triage green, no issue created |
| E31g | #232 | A push to `main` that cancels the previous push's run | That run's triage skipped; no `main-run-no-report` | ⬜ | |
| E31h | #232 | The tracker refuses a defect (e.g. a required field) | One `defects-not-written` alert; the triage job red; resolved by a run whose writes all succeed | ⬜ | |

## TG-8 · Operations: health issue and budgets (S7)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E27a | F-23, #231 | Run *Pipeline health* by hand | One issue labelled `pipeline-health` (Task), description "Open alerts (0)"; the team watches it | ⬜ | |
| E27b | F-23, #231 | Three failed scheduled runs of one workflow (induced on a copy) | One `[health:open] workflow-failing:<file>` comment, watchers emailed; later checks post nothing; its next successful scheduled run → one `[health:resolved]` | ⬜ | |
| E27c | F-23, #231 | A refused model key (or a spent key budget) | `credential:model` opens; fixed → resolves | ⬜ | |
| E27d | F-23, #231 | `GH_PAT` expiring within 14 days | `credential-expiry:repo-host` opens; a replaced token → resolves | ⬜ | |
| E27e | F-23, #231 | A wrong `JIRA_API_TOKEN` in the health workflow | The run fails red, GitHub emails the workflow's owner; nothing on the issue | ⬜ | |
| E27f | F-23, #231 | `dry_run` | Findings printed, nothing written | ⬜ | |
| E27g | F-23, #231 | Issue properties written with the bot's token | A flake or spend record appears on the health issue (`property_keys`) - the one Jira capability not yet proven with the pipeline's own credentials | ⬜ | |
| E32a | F-24, #231 | `budget.per_story_usd` below a story's ledger total, then `ai-regenerate` | Agent 2 stops before its first model call; `budget-hold` and one `[budget:hold]` comment; not picked next scan; label removed → runs again with one more budget | ⬜ | |
| E32b | F-24, #231 | `per_day_usd` just above today's spend | `budget-warn-<day>` at `warn_at`, then `budget-day-<day>`; scans log `[BUDGET]`, end green, defer their stories; Agent 3 posts *Not reviewed: model budget reached*; Agent 5 still reports with code-written prose | ⬜ | |
| E32c | F-24, #231 | The next day | The health check resolves both alerts; the *Model spend* line restarts; records older than `spend_keep_days` gone | ⬜ | |
| E32d | F-24, #231 | Any Agent 5 report with prices set | The cost table ends with the *Story budget* line | ⬜ | |

## TG-9 · To be added when built (P4)

| Planned | Rows to add when it is built |
|---|---|
| F-30 bot identity | A person requests changes on and approves an agent PR; the review-fix "Request changes" trigger fires |
| F-31 comment de-duplication (D1-D7) | Per D-item: the comments that go away, what replaces each, every machine-read marker still working (cost table, reset, run-once checks), on a story run end to end |
