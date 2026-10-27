# Validation and known gaps

One file for three questions: **what has been proven live**, **what is still to
be run**, and **what the framework does not handle yet**. Unit tests prove the
logic offline; this file tracks the live runs against Jira, GitHub and the
application under test, and every known gap, so nothing lives only in a chat or
a checkpoint.

The validation records below are for this deployment (project `SCRUM`, the
Automation Exercise application). A new application keeps sections 3–5 and
writes its own sections 1–2.

**Rules**
- Write the expected result of a run **before** running it, then record what happened.
- A gap is closed only by a merged fix with tests; move it to section 5 with the PR number.
- Update this file in the same PR as the change that affects it.

---

## 1. Validated live

| # | Run | Date | What it proved |
|---|---|---|---|
| V1 | Test bed: SCRUM-111, SCRUM-200, SCRUM-201, SCRUM-202 | 11 Oct 2026 | New stories end to end: Agent 1 test cases, human approval, Agent 2 PR (an existing page object extended, not regenerated), Agents 3–5; PRs merged, stories Done |
| V2 | SCRUM-187 (shopping session, login to logout) | 11–15 Oct 2026 | A journey story through Agents 1–5 (`ai-coded`, `tests-run`; PR in review). Its Agent 0 run exposed 10 false "review" rows, fixed by #186 — see P6 |
| V3 | A1 – SCRUM-203: rename "Add to cart" | 12 Oct 2026 | Shadow report scored PASS (7 affected, all review tier; 10 correctly unaffected); live Impact Review (SCRUM-227), hand-over, wording context update |
| V4 | A2 – SCRUM-229: adding a product goes straight to the cart | 12 Oct 2026 | 7 of 7 must-update correct; an edited story re-analysed and its review updated in place; hand-over clean; context update "none". Run to step 3, then reset |
| V5 | A3 – SCRUM-206: remove the quantity choice | 12–14 Oct 2026 | The full change cycle: review (approve, reject, retire), hand-over, context-update PR, Agent 1 impact-aware revision with snapshots, Agent 2 splice into the owner's files, Agents 3–5, owner traces, prediction outcome; undo after a close seen on two scans; retry as a new attempt (must-update 220/221/222 only, after #186). Reset |
| V6 | PR #202 and PR #203 (documentation only) | 22–23 Oct 2026 | The pull-request browser gate: unit suite only, browser run and Agent 5 skipped, Agent 3 reviewed |
| V7 | E18 - Agent 2 review fix on an `ai-regenerate` PR (SCRUM-202, PR #221) | 26 Oct 2026 | A bare `/fix` after three inline comments: two fixed on the same branch (one on the story's own regenerated feature file), one declined with the test-case route, a reply in every thread, one summary; Agents 3 and 4 green on the fix; a re-run on the same `/fix` did nothing; cost on the story. Found and fixed on the way: #220 (a regenerated story's own files), #222 (`/fix <text>` dropped the inline comments; a skipped event could cancel a waiting `/fix`). PR closed unmerged as planned |
| V8 | SCRUM-187 regenerated after SCRUM-260 step 7 dropped "with quantity 1" (PR #223) | 26 Oct 2026 | The second half of E16: the gates now agree, the regenerated code asserts only relative cart state, Agent 3 found nothing, Agent 4 and Agent 5 green (3 of 3). PR closed unmerged on purpose |

Everything added in #199–#201 (unused-step comment-out in `ai-update`, step
coverage by runtime scope, `closed_scans`, Agent 0 on the cost ledger, test-case
Components, stories in flight, browser turn-taking) passes its unit tests but
has not yet run live: section 2.

---

## 2. Still to run (clubbed so one story run proves several things)

### 2.1 Items to cover

New features and gap fixes from the priority plan (section 4: P1-P4) are
validated **together, at the end**, in one consolidated run (UC-7 below), so
one story run proves as much as possible. Each one adds its item here when it
is built (E19 onwards) and is listed in UC-7.

| ID | Item | Source |
|---|---|---|
| A4 | SCRUM-205 back-to-top arrow: nothing affected → `ai-ready`; unchanged re-run skipped (stage 0); no-Component path | A-series |
| A5 | SCRUM-204 search ignores case and extra spaces: stays inside one owner; tests that still hold are not must-update | A-series |
| A6 | SCRUM-207 clearer wrong-password error: unmarked legacy tests reported for revision by hand; nothing to review expected | A-series |
| B | A pull request changing a page-object method and an inventory selector → Agent 0 posts the affected tests, no model | Run B |
| C | Drift on demand (`mode` = `drift`) → maintenance story (`inventory-drift`); scan and reconcile skipped | Run C |
| H1–H5 | Stories Agent 0 has never seen, expected result written first: H1 a wording change (not SCRUM-203), H2 a new validation rule on an existing form, H3 a removed field on another page, H4 a new feature on a new page (nothing affected), H5 a story with no Component | Held-out check |
| E1 | `ai-update` that removes a scenario holding a step's last use → step function commented out, listed in the PR, final gate passes | #199 |
| E2 | Undo with `reconcile.closed_scans: 1` → on the first scan that sees the close | #200 |
| E3 | Agent 5's cost table has an Agent 0 row (analysis + context update); Agent 1 did not reset it | #200 |
| E4 | Agent 1's test cases carry the story's Components | #200 |
| E5 | A notes-only context-update PR → unit suite only, no Agent 5, Agent 3 offers no runner evidence (docs-only part already V6) | #200 |
| E6 | Two stories writing one page object: the second waits after the plan, one `[agent2:waiting]` note across scans, then extends the file after the first merges | #201 |
| E7 | A test case whose scenario another open PR adds → waits before the plan, no model call | #201 |
| E8 | Two PRs open at once → the later browser run waits its turn (cap 900 s) | #201 |
| E9 | A pipeline test case (`[Positive] <title>`) whose scenario exists without a marker → skipped by title (since P1-3 also listed in the PR and the story comment as needing its marker, without `ai-incomplete`) | #201 |
| E10 | `ai-update` while another open PR changes its feature or step file → waits before any model call | #201 |
| I8 | The live-site add-to-cart flake: still seen with turn-taking? failure messages now list the action requests | Open defect |
| P6 | SCRUM-187 re-analysed by Agent 0 after #186: expect no false "review" rows | Re-check |
| E11 | A change story that removes a field (SCRUM-206, retried): Agent 1's map covers AC1 with a step asserting the field is not present; the revised tests alone are rejected | Coverage fix |
| E12 | The same story's PR: the scenario carries the absence step, its step definition asserts `is_<field>_absent()` built on `is_loaded() and is_gone(...)`; against the undeployed application that step FAILS (L20) and nothing else does | Coverage fix |
| E13 | A new story with a limit or a restriction (held-out H2 fits): the coverage comment lists a rejection step for it | Coverage fix |
| E14 | PR #211 re-reviewed after #212 (push a commit or re-run Agent 3): the run is red on the absence step only; the card-click finding is lowered with "scenario ... passed", and the review is advisory | #212 |
| E15 | Any PR run while the site refuses some CI requests: retried page loads log `succeeded on attempt N`; a re-run test is listed by the `Keep only the final attempt` step; Agent 5's table counts each test once | #213 |
| E16 | SCRUM-187 on the next scan: one `[agent2:blocked]` comment naming the persistent-state rule, then `[BLOCK]` with no model call on later scans; a new signed-in draft stating a cart quantity is sent back by Agent 1. (The story coding once step 7 was fixed: V8) | Gates agree |
| E17 | Any PR run during a burst of 5xx from the site: a test whose add-to-cart call or followed link was refused fails as `ApplicationUnavailableError` naming the request, is listed by the `Keep only the final attempt` step as re-run, and its reading is "application temporarily unavailable"; a plain assertion failure is not re-run | #215 |
| E19 | Inventory update (P1-1, PR #224), on one drift run (`mode` = `drift`, or the 07:15 IST night) and the nights after: **(a)** something applicable → one `inventory-update/<date>` PR with replaced / added / removed tables and the kept, held, no-durable-selector and refused lists; Agents 3 and 4 green on it. **(b)** Same findings next night → the PR is left alone. **(c)** New findings → the old PR closed with a comment, a new dated PR opened (old branch deleted, or left if the ruleset forbids it). **(d)** Commit to the PR's branch → never replaced, one `kept-edited` comment, no second PR. **(e)** A stale key an open story PR names → kept, not removed. **(f)** An added hidden element or family carries `conditional` / `multi_match` and is not undone the next night. **(g)** Shadow mode or `dry_run` → the body printed, no PR | Inventory update |
| E20 | Context update scope (P1-2, F-10): the change story's `[agent0:context-update]` run reads only `core.md`, its Component modules and their pages' notes (the model's prompt in the run log); a rewrite of another module never appears in the PR | Context update |
| E21 | Notes addition (P1-2, F-8): UC-7's new story, merged → Story Done on merge moves it to Done, then one `context-update/<key>-notes-<hash>` PR adds its rules / messages / test data under its Component module (a new module for a new Component) and an `[agent0:context-addition]` comment; nothing the notes already said is repeated; a second run of the workflow does nothing, while an `ai-update` of its test cases, merged, proposes again; the cost is on the story | Context update |
| E22 | Removed element (P1-2, F-11): UC-7's removal change story → its context-update PR declares the element in `removed` (and its note `REMOVED by …`); merged after deployment, the nightly check shows `GONE`, not `STALE`, Agent 0 raises no affected test for it, and once the absence test is retired the next inventory-update PR deletes the key | Context update, inventory |
| E23 | Notes budget (P1-2, F-9): a notes-addition PR that pushes a module over `module_budget_chars` says so in its body and its unit-suite check fails until the module is condensed in the same PR; `scripts.onboarding_check` reports `notes: size` / `notes: repetition` | Context update |
| E24 | No silent drop (P1-3, F-13, PR #227), on UC-7's new story; write each expected result down before the run. **(a) Partial:** one approved test case needs an element not in the inventory yet → the PR opens with the others; its body lists that test case under *Approved test cases not automated* with the plan's `Skipped:` reason (or "no reason given" - note which); one `[agent2:incomplete]` story comment; `ai-incomplete` beside `ai-coded`; the scan summary line says `not automated: <KEY>`. **(b) Markers are right:** open the PR's feature file - each `# JIRA:` marker sits on the scenario that tests that test case (L31: the check proves a marker exists, not that it is on the right scenario). **(c) Title clash:** one more test case whose summary repeats the title of another story's marked scenario on `main` → listed as a title clash naming that test case, counted as not automated. **(d) Gap filled:** after the element reaches the inventory and the PR is merged, add `ai-update` → only the missing scenario is appended, and `ai-incomplete` comes off. **(e) Nothing automated:** a story whose only test case needs a missing element (`--dry-run` is enough) → no PR, an `[agent2:blocked]` comment naming it | Agent 2 |
| E25 | Planned entries, new pages, shared elements (P1-4, F-12, L25, G14), on UC-7's new story and the nights around its deployment; write each expected result down first. **(a)** Before deployment: `python -m scripts.plan_inventory element ...` (and `page ...` for a new page) for what the story needs → the onboarding check is clean; Agent 2 uses the keys and its PR lists *Uses planned elements - not deployed yet*; its browser run is red on exactly those steps. **(b)** Nights before deployment: `verify_locators` shows `PLAN` / `PLANNED PAGE`; the drift report has no stale or unreachable entry for them; the inventory-update PR only lists them under *Planned, not live yet*. **(c)** First night after deployment: the PR confirms them (*Planned elements now live*), drops `planned_page`, and adds the new page's other live elements. **(d)** The footer field of PR #228 is listed under *Not added - already covered on another page* with `home.subscribe_email_input`, on every page, and never added; a header or footer element no key covers yet is listed once under *new on every page*, not added per page. **(e)** The PR lists pages the application links to that the inventory lacks. **(f)** A placeholder answering at a planned page's url (no planned element on it) → that page is not changed | Inventory update |
| E26 | A new story's PR closed without merging (P2, F-16): first scan after the close → one `closed-unmerged` comment, nothing else changes; reopen it → nothing; close it again and leave it two scans → `story-reset` comment, `human-approved` / `ai-coded` / `ai-incomplete` / `tests-run` off, `ai-processed` kept, card in To Do, test cases unchanged; Agent 2's next scan does not pick it; add `human-approved` → Agent 2 codes it again in a new PR | Reconcile |
| E27 | Pipeline health (P3, F-23): run *Pipeline health* by hand → one issue labelled `pipeline-health` (Task) is created, description shows "Open alerts (0)"; the team watches it. **(a)** Disable a scheduled workflow's secret (e.g. a wrong `LLM_MODEL` on a copy) or wait for three failed scheduled runs of one → one `[health:open] workflow-failing:<file>` comment and an email to watchers; the next checks post nothing; its next successful scheduled run → one `[health:resolved]`. **(b)** A refused model key (or a spent key budget, with `model_check: completion`) → `credential:model` opens; fixed → resolves. **(c)** `GH_PAT` with an expiry within 14 days → `credential-expiry:repo-host`. **(d)** A wrong `JIRA_API_TOKEN` in the workflow → the run fails red and GitHub emails the workflow's owner; nothing on the issue. **(e)** `--dry-run` → findings printed, nothing written | Health |
| E28 | Outage reported apart (P3, F-7), on any PR run during a burst of 5xx from the site (E17's run): a test that still fails is under *Application unavailable (not test failures)* in the run summary, not under *Failures*; Agent 5's comment has the *Not judged* warning and section and is not counted as failing outside the story; with nothing else failing its verdict is `unavailable`; the check is still red; Agent 3 lowers no prediction on that scenario | Agent 4, 5, 3 |
| E29 | Retry once and flakes (P3, F-19): a PR run where one test fails then passes on the retry (the add-to-cart flake I8 is a candidate) → *Retry failed tests once* re-runs exactly the failures, the run is green, the summary and Agent 5's report list it under *Passed only on the retry (flaky)* with its first failure, and the health issue's *Flaky tests* table counts it (no comment). A test failing twice keeps the run red; more than 10 failures → no retry ("not retrying") | Agent 4, 5 |
| E30 | Nightly run on `main` (P3, F-21): the 03:10 IST run runs the unit gate and the whole E2E with the retry, uploads the artifact, writes the summary, posts no story report; a PR opened during it waits its turn (and it waits for an earlier PR run); a push to `main` during it does not cancel it | Agent 4 |
| E31 | Defects (P3, F-22), on the nightly runs: write the expected results first. **(a)** A test failing on `main` → one Bug (`ai-defect`, `ai-defect-<hash>`) naming the test, its test case and owning story, cause, fix, failure and run link. **(b)** Next night, same failure → the same Bug, times 2, no comment. **(c)** It passes → `ai-defect-passing` and one "Suggest closing" comment; a later failure → label off, "Failing again". **(d)** An outage night → no Bug, one `application-unavailable-on-main` alert, resolved the next clean night. **(e)** A flaky pass → no Bug, recorded | Triage |
| E32 | Spend budgets (P3, F-24), with the `LLM_PRICE_*` variables set: **(a)** set `budget.per_story_usd` below a story's ledger total, then add `ai-regenerate` → Agent 2 stops before its first model call, the story gets `budget-hold` and one `[budget:hold]` comment, the scan's next run does not pick it; remove the label → it runs again with one more budget. **(b)** Set `per_day_usd` just above today's spend → a `budget-warn-<day>` alert at `warn_at`, then `budget-day-<day>`; scans log `[BUDGET]`, end green and defer their stories; a PR's Agent 3 posts *Not reviewed: model budget reached*; Agent 5 still reports with code-written prose. **(c)** The next day: the health check resolves both alerts; the health issue's *Model spend* line shows yesterday's records gone after `spend_keep_days`. **(d)** Agent 5's cost table ends with the *Story budget* line | Budget |

### 2.2 The runs

| Run | Stories | Covers | Steps and expected result |
|---|---|---|---|
| **UC-1** Agent 0 batch scan (analysis only, cheapest) | SCRUM-205, SCRUM-204, SCRUM-207 + new H1, H2, H3, H5; SCRUM-187 by dry run | A4, A5, A6, P6, H1–H3, H5 | Label the stories `impact-check`; one full scan. Each report matches the result written down first. Re-run: every story skipped at stage 0, no model call. SCRUM-187 is already coded, so it is checked with `python -m agents.agent0_impact --story SCRUM-187 --dry-run` (report printed, nothing written): expect no review rows. |
| **UC-2** Re-run A2 to the end | SCRUM-229 (2 owners) | E1, E2, E3, E5 or E8, E10, I8 | Review: approve the 7 → hand-over → context-update PR (notes only: E5; inventory: its browser run takes its turn, E8). While the story PR is open, `ai-update` on an owner waits (E10). Close the PR with `closed_scans: 1` → undone on the first scan (E2). Then the owner's `ai-update` deletes a test case → unused step commented out, PR opens (E1). Cost table has the Agent 0 row (E3). Cart tests watched for I8. |
| **UC-3** Two new stories in flight | P1 (labelled `impact-check`), P2 (same page object as P1) | H4, E3, E4, E6, E7, E8, E9 | P1: Agent 0 finds nothing → `ai-ready` (H4), its cost on the table (E3); test cases carry Components (E4); one test case titled as an unmarked scenario on `main` → skipped (E9). While P1's PR is open: P2 with a duplicate test case waits before the plan (E7); remove it → waits after the plan (E6); merge P1 → P2 extends the page object. P2's PR opened next to another PR → its browser run waits (E8). |
| **UC-4** Runs B and C together | a hand-made PR; a manual run with `mode` = `drift` | B, C | The PR's Agent 0 comment lists the tests the changed method and selector reach; the browser runs (runtime file changed). The drift run opens or updates the maintenance story; scan and reconcile skip. |
| **UC-5** After the P2 fixes | three stories in one Agent 1/2 scan, the first set up to fail; a regeneration; two change stories touching one test case; a new story's PR closed | M1–M4, G1, G2, E26 | Write the expected results down first. **(M1)** The failing story's ledger shows `Agent 2 (Coder, initial) (failed)` with its calls; the next story's comment shows only its own. **(M2)** With three stories eligible and `max_stories_per_run: 2`, the scan runs two and shows the third `[DEFER]`; the next scan takes it; the job ends inside 25 minutes. **(M3)** A PR whose only blocking finding is a predicted failure, queued behind another PR's browser run: Agent 3 still reads Agent 4's result (log: "waiting up to 1380s"). **(G1)** A regeneration whose orphan cleanup edits a page object another open PR changes: `[WAIT]` naming that file, no branch. **(G2)** Change story A handed over (no PR yet) and change story B analysed after: B's row for the shared test reads "blocked by A"; B's hand-over of an approved row waits with "being revised by another change in progress" until A's PR merges or is undone. **(G8)** E26. |
| **UC-6** Retry the removal story | SCRUM-206 after its PR and context-update PR are closed and reconcile has undone it | E11, E12 (E13 with H2 in UC-1) | Remove `impact-reverted`, add `impact-check`; approve the review as before. Agent 1's `[agent1:coverage]` lines name the test asserting the quantity field is gone. Agent 2's PR: that step present and asserted on a loaded page; its browser run fails on exactly that step while the field is still deployed - the expected red (L20). |
| **UC-7** Final consolidated run, after P1-P4 | One new story whose feature is not yet in the inventory or the app notes (a new element on an existing page, ideally a new page too), one change story removing an element, and a drift run | E17, E19-E32 and every item P1-P4 add | Planned once the P1-P4 fixes are merged. The new story exercises the inventory update (its elements arrive through the nightly PR, or a planned entry - P1-4), the context-update addition for a new feature (P1-2), no silent drop of a test case Agent 2 cannot automate (P1-3, E24), and planned entries before its deployment (P1-4, E25); the change story exercises removal in the notes and the inventory (P1-2, F-11); its PR closed once unmerged exercises the reset (P2, F-16); the drift run covers E19 (a)-(g) across nights; any 5xx burst during the runs covers E17 and E28; the nights around it cover the nightly run, defects and flakes (E29-E31, P3); the health check runs throughout (E27); E32 needs the budget set low on purpose for one story and one day, then restored. Each item's expected result is written down before the run |

Order: UC-1 → UC-2 → UC-3 → UC-4 → UC-6 → section 4 fixes → UC-5 → **UC-7 last**, after the P1-P4 fixes are merged.

---

## 3. Known gaps and limits

**Status:** *Fix planned* = a bug, fixed in section 4. *Limit* = accepted
behaviour of the design, documented so nobody relies on more. *Open* = cause not
yet known.

### 3.1 Stories in flight at the same time

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L1 | Two stories change **different scenarios of one feature file** | The second waits: the guard works per file, not per scenario. Safe, sometimes slower | Limit |
| L2 | Two stories add the **same scenario with different wording** | Both are created: the in-flight check and duplicate detection compare titles | Limit |
| L3 | A person opens a pull request on a file **after** Agent 2's PR is open | Nothing stops a person; GitHub reports a merge conflict if the same lines change. Agent 0 lists affected tests on any PR touching `pages/` or `app_inventory/`. (One opened while Agent 2 is generating is caught by the last in-flight check, F-1: the story waits.) | Limit |
| L4 | A **semantic clash across different files** (PR A renames an inventory key PR B's new page method uses) | Not detected before merge: the guard compares files, not meaning. Agent 0's code-change comment on PR A covers tests already on `main`, not PR B's; B's tests fail after A merges | Limit |
| L5 | GitHub cannot be read when Agent 2 takes the snapshot | The story proceeds without the guard (fail open), as before #201 | Limit (by design) |
| L6 | A story that waits | Its plan call is spent - or, when the last check before the branch finds the clash (F-1), its generation calls too - recorded as `Agent 2 (Coder, waiting)`, and spent again on the retry | Limit |

### 3.2 Several stories in one scan

| ID | Situation | What happens today | Status |
|---|---|---|---|
| M4 | More than about four PRs want the browser at once | The turn cap is 900 s; a run is about 4 minutes (median), so about four queued runs fit before later ones overlap again. Agent 3's wait (F-5) covers one turn plus one run | Limit (burst size documented) |

### 3.3 Agent 0

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L7 | A scenario without a `# JIRA:` marker, or an inventory page without `components` | Agent 0 reports the scenario but has no test case to revise; a page without components widens layer 2 to the whole suite. Gaps are reported as unknown, never as unaffected | Limit (`scripts.backfill_markers`, onboarding check) |
| L8 | Seeds wider than the change (unchanged elements of the same page seeded) | Analysed after A2 and kept for recall; the model's verdict caps the tier, so it cannot promote a test | Limit |
| L9 | `uncovered_hint` | Off until a backtest with and without it is compared | Limit |
| L10 | Agent 3's review of a context-update PR | Its branch carries no story key, so the cost is not on the story's ledger, only in that run's log | Limit |

### 3.4 Generation, tests and evaluation

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L11 | Persistent-state assertions shaped as a snapshot count or snapshot membership | Not yet rejected by the Agent 2 gate (noted 13 Oct) | Fix planned (validator) |
| I8 | Add-to-cart on the live site occasionally fails | Root cause unknown; failure messages now list the page's action requests. Check whether browser turn-taking removed it (UC-2) | Open |
| L41 | A real failure in a test whose own request also met an unrecovered 5xx/429 | Reported as an outage (not judged, no defect), the same rule that re-runs it (#215): the failure text is restated to name the 5xx. The next run, without the outage, shows the real failure | Limit |
| L12 | Prompt changes for Agents 1–3 | No dedicated prompt-regression eval set; the unit suite pins validators, Agent 4 runs the generated tests | Limit |
| L24 | An acceptance criterion that removes or restricts something without saying so in plain words ("the field goes away", "members lose renewals") | Every criterion must still be mapped to a test that verifies it, but the absence / refusal / rejection obligation is read from the wording (`obligation()` in `core/acceptance_coverage.py`), so such a criterion is checked only for being mapped. Writing criteria in the plain form ("no longer offers", "only X can", "at most N") makes them checked; the reviewer reads the `[agent1:coverage]` comment for the rest | Limit |

### 3.5 Knowledge lifecycle: the app notes and the inventory

Agent 1 learns the application from `prompts/app_context/` (`core.md` plus the
story's Component modules); Agents 2 and 3 from the inventory. Agent 0 reads the
code, the scenario markers and the inventory, not the notes.

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L27 | A module over budget, or two modules repeating a fact | Reported (unit suite fails on size; the notes PR and the onboarding check list both), never condensed automatically: no model rewrites a whole module unreviewed | Limit |
| L28 | A change story's notes addition (at merge) while its context-update PR (from the hand-over) is still open | Both are built from `main` and may edit the same module, so the second to merge can conflict. Merge the context-update PR first (it is due after deployment, before the story's PR merges); otherwise close the notes PR and re-run Story Done on merge for the story | Limit |
| L29 | A key declared `removed` is still offered to Agent 2 | With its `removed` declaration and `REMOVED by` note in the payload, so the model sees it is gone; nothing else stops a new test from using it as if present - the reviewer and Agent 4's red run do | Limit |
| L32 | A **new page** nothing in the inventory points to | Since P1-4 the nightly PR lists same-origin pages the crawled pages link to that no inventory url matches, and crawls a page once a person adds its entry (or a `planned_page`); a page nothing links to is not found, and a listed one is not crawled until its entry exists | Limit |
| L26 | A stale key whose element the crawl now names **differently** (a renamed button) | The inventory-update PR replaces a selector only under the same generated name; a renamed element shows as an added key plus a removed or kept old key, and the person merging renames them | Limit |
| L33 | A **planned** element whose deployed selector differs from the design's | It never reads as live, so it stays `planned` (listed every night) and the tests using it stay red; a person corrects the selector in the inventory. Nothing compares a planned key with a similar live element | Limit |
| L34 | A **shared** element (header, footer) under ONE page's key | Since P1-4 it is no longer added again on every page; a page object of another page still cannot reach it (`sel()` reads its own page) until it is moved to a page declared `always` - a person's change | Limit |

### 3.6 Traceability: every approved test case becomes a test

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L30 | A test case Agent 2 cannot automate is **reported, not automated** | Since F-13 it is named with its reason in the PR and on the story (`ai-incomplete`); generating it still needs its cause fixed by a person, then `ai-update`. The reason is only as good as the plan's `Skipped:` line - a test case the model drops without one is reported with "no reason given" | Limit |
| L31 | The coverage check proves a scenario **carries the test case's marker**, not that it tests what the test case says | Markers are placed by title pairing: greedy best match with a 0.3 similarity floor, and a lone scenario paired with the first test case unconditionally (existing behaviour). A scenario paired with the wrong test case counts as covering it, and the right one is reported as missing or not at all. Agent 3's review and E24 (b) are the check today | Limit |

### 3.7 Change detection after coding

| ID | Situation | What happens today | Status |
|---|---|---|---|
| G6 | The **story's own requirement is edited** after Agent 1 drafted it or Agent 2 coded it (a new story, not a change story) | Agent 1's duplicate guard refuses a re-run; Agent 0's repeat check covers `impact-check` stories only. Nothing notices, and the tests keep describing the old requirement | Fix planned |
| G7 | A **test case is edited or deleted in Jira** after coding | The scenario marker carries the test case's hash, but only a manual `ai-update` label compares them | Fix planned |

### 3.8 End of a story's pull request

| ID | Situation | What happens today | Status |
|---|---|---|---|

### 3.9 Running the suite over time

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L20 | A change story's PR before the change is deployed | Its app tests are expected to fail until deployment, and merging the context-update PR after deployment is left to a person; no deployment signal tells expected from real failures | Fix planned |
| L21 | The suite grows | Agent 4 runs the whole suite on every PR; only Agent 5's report is scoped to the story | Fix planned |
| L35 | A test that **flakes often** | Retried once, counted, listed on the health issue (F-19) - not quarantined: a person decides to fix or skip it | Limit |
| L37 | One defect per test **and cause** | A test failing with a new cause raises a second defect; the first stays open until a person closes it. A defect is never closed by the pipeline, and only runs on `main` raise them (a PR's failures go to its story) | Limit |
| L39 | Agent 3's wait for Agent 4 (turn + 480 s) | A run with a retry of up to 10 tests can finish after it: the prediction then keeps blocking (the safe side), and a re-run of the review reads the result | Limit |
| L23 | A production bug needs a regression test | Every selection uses `issue_type: "Story"`; another type is possible in config but untested, and the prompts are written for stories | Fix planned |

### 3.10 Operating the pipeline continuously

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L36 | **The daily budget sees finished runs only** | Each run records its spend when it ends; a run reads the day's total at its first model call. Runs going on at the same time can pass the limit by what each spends; a run killed by its timeout records nothing. `scripts/smoke_test.py` and local runs (unless `PIPELINE_BUDGET=on`) are not counted | Limit |
| L38 | **The tracker's own credentials fail** | No alert can be posted on the tracker: the health check's run fails and GitHub notifies the workflow's owner - the one alert outside the health issue | Limit |
| L40 | **A story allowed more budget** (its `budget-hold` removed) | Agent 5's budget line compares the total with one `per_story_usd`, so it reads over 100% | Limit |
| N5 | **An agent's PR goes stale or conflicts** because `main` moved (e.g. a person's PR merged first) | No rebase or regeneration; the sweeper re-triggers only PRs whose checks never ran. The PR waits for a person | Fix planned |
| N6 | **A red PR is merged** | No required status check (a decision recorded in GUIDE → Branch protection), so a story PR with failing tests can be merged and moved to Done | Decision pending |
| N7 | **Test data and isolation** | Every run shares the live application's accounts and saved state; tests run one at a time (no parallel execution). Browser turn-taking avoids collisions but rules out parallelism; no per-run data set-up and tear-down | Fix planned |
| N8 | **More than one environment or browser** | One `base_url` (an environment variable can override it) and Chromium only; no staging/production profiles, no browser matrix | Fix planned |
| N9 | **"How healthy is our testing?"** | Results, cost and Agent 0 recall/precision are posted to Jira per story but never aggregated: no pass-rate, flake-rate, coverage, cost-per-story or Agent 0 accuracy trend | Fix planned |
| N10 | **Agent 2's pull requests are opened under the reviewer's own account** (`GH_PAT`) | GitHub lets no author request changes on or approve their own PR, so the reviewer must use `/fix` instead of "Request changes", and merging needs a ruleset bypass; a required approval or status check (N6) cannot be enforced (seen live on PR #221) | Fix planned (P4) |
| N11 | **Most story comments are bookkeeping** | On six recent stories, 54 of 70 comments (77%) were `[LLM-USAGE]` / `[LEDGER-RESET]` / `[agent0:outcome]` entries the agents read back, not information for people; Agent 5's cost table repeats them, grows by one row per agent run, and a re-run of the same commit posts the same report again. Watchers are emailed for each | Fix planned (P4, F-31) |

---

## 4. Fix backlog

| Fix | Gaps | Change |
|---|---|---|
| F-1 | G1 | **Done (P2)** - `_last_in_flight_check()`: a fresh snapshot of the open PRs against every file a run commits, right before the branch, in `run()` and `run_update()` |
| F-2 | G2 | **Done (P2)** - a row is also blocked by an `impact-applied` story and by another open Impact Review listing the test; the hand-over refuses a test another change is still revising |
| F-3 | M1 | **Done (P2)** - `story_usage()` around every story (Agents 0, 1, 2): counter at zero at the start; a failed story posts `<agent> (failed)` on itself |
| F-4 | M2 | **Done (P2)** - one budget for the three passes (`plan_scan`), `scan_deadline_minutes` (12), job timeout 25; the rest `[DEFER]` |
| F-5 | M3, M4 | **Done (P2)** - wait = turn cap 900 s + one run 480 s; Agent 3 job timeout 30; burst size documented (M4) |
| F-6 | L11 | Validator for snapshot-count and snapshot-membership assertions |
| F-7 | L14 | **Done (P3)** - retry in #213 and #215; a failure that outlasts the retries is marked `outage` in junit.xml (`core.failure_diagnosis.is_outage`, failure text only) and reported apart in the run summary and Agent 5's report (*not judged*, verdict `unavailable`), never evidence for Agent 3, never a defect |
| F-8 | L15 | **Done (P1-2)** - when any story's PR merges (Story Done on merge), not only a new feature's. When a new-feature story's PR merges (and for a change story that adds a rule), Agent 0 proposes a **notes addition** for the story's Component module: facts only (rules, limits, test data, flow), a few lines in the module's style, written from the story **and** its merged scenarios, checked against existing text so it repeats nothing; the same reviewed context-update PR, merged after deployment. Later change stories then have a passage to rewrite |
| F-9 | L16 | **Done (P1-2)** - `module_budget_chars` (8000) per module: the unit suite fails over it, the notes-addition PR reports size and repeated sentences, `scripts.onboarding_check` warns. Condensing stays a person's job (L27). |
| F-10 | L17 | **Done (P1-2).** Call 2 of the context update reads only the story's Component modules and those pages' inventory notes, as Agent 1 does (all modules when the story has no Component) |
| F-11 | L18 | **Done (P1-2)** - the hand-over declares the element in the page's `removed` list; every checker reads missing as healthy and present again as drift (`reappeared`, `GONE` / `BACK`); Agent 0 seeds only a reappeared one; the nightly inventory update deletes the key, note and declaration once no code names it. |
| F-12 | L19, L25 | **Done (P1-4)** - `planned` elements and `planned_page` pages a person adds from the design (`scripts.plan_inventory`); Agent 2 may use them and its PR names them; every checker reads them as not live yet; the nightly update confirms them once live and crawls a confirmed planned page like any other. The same PR lists pages the application links to that the inventory lacks, and stops re-adding an element another page's key covers (G14) |
| F-13 | G5 | **Done (P1-3)** - after generation every approved test case must have a markered scenario, read from the files (new stories, regenerations and `ai-update`, not only the change-story splice); each missing one, with the plan's reason, goes in the PR body and one `[agent2:incomplete]` story comment, and the story gets `ai-incomplete` beside `ai-coded` until a run fills the gap. The duplicate check's title clash counts as missing; a run that automates none of the new test cases opens no PR (blocked) |
| F-14 | G6 | Agent 1 records a hash of the story text when it drafts; a scan compares it: edited before coding → suggest a re-draft; edited after coding → suggest `impact-check`. A comment, never an automatic action |
| F-15 | G7 | A scheduled comparison of each scenario marker's hash with its Jira test case (edited, deleted, retired): a comment on the owning story suggesting `ai-update`, never applied automatically |
| F-16 | G8 | **Done (P2)** - reconcile also settles every coded story: its newest PR closed unmerged on `closed_scans` scans → `story_reset_labels` off (approval included), card to `on_close_unmerged`, retry steps |
| F-17 | L20 | An optional deployment signal (config or webhook) that marks a change story's failures as expected until deployment and reminds a person to merge its context-update PR |
| F-18 | L21 | On a PR, run the tests Agent 0's graph links to the change (plus a smoke set); the full suite nightly and before merge |
| F-19 | L22 | **Done (P3)** - every failure retried once (`--last-failed`, at most 10); a pass is `flaky` (passed, named, counted on the health issue) or `outage_recovered`; the job is decided after the retry. Quarantine stays a person's decision (L35) |
| F-20 | L23 | A configured bug flow (issue type, prompt template for a regression test), validated live before use |
| F-21 | N1 | **Done (P3)** - `agent4_runner.yml` nightly on `main` (03:10 IST): the whole suite with the retry, summary and artifact, no story report; its own concurrency group; it takes turns with PR runs |
| F-22 | N2 | **Done (P3)** - the `triage` job after every run on `main`: one defect per test and cause (`core/defects.py`), updated without a comment, flagged once when it passes again (a person closes it); outages and flakes kept out; at most `max_new_per_run` new per run |
| F-23 | N3 | **Done (P3)** - one watched pipeline health issue (`core/pipeline_health.py`): a comment when an alert opens and when it closes; `pipeline_health.yml` checks every scheduled workflow (failed `consecutive_failures` scheduled runs in a row), the repo host token and its expiry, the model endpoint; a refused tracker fails the run (L38) |
| F-24 | N4 | **Done (P3)** - `budget` per story and per day, checked before every model call (`core/spend_budget.py`); a held story by label, the day in append-only records on the health issue; every model call counts |
| F-25 | N5 | Detect agent PRs that conflict with or fall behind `main`; comment with the cause and suggest `ai-update` or `ai-regenerate`; never force-push silently |
| F-26 | N6 | Decide on requiring Agent 4's Run Tests check once the pipeline is reliably green, with F-17's expected-failure marking so a change story is not blocked before deployment |
| F-27 | N7 | Per-run test data (accounts and fixtures seeded per run or per worker) and then parallel execution; browser turn-taking becomes optional |
| F-28 | N8 | Environment profiles in config (base URL and credentials per environment) and an optional browser matrix in Agent 4 |
| F-29 | N9 | A scheduled metrics report built from the ledger, Agent 5's results and Agent 0's outcomes: pass and flake rates, coverage per story, cost per story, Agent 0 recall and precision over time |
| F-30 | N10 | A separate bot identity for the agents' writes - a machine user or a GitHub App token in `GH_PAT` - so a person can request changes and approve; then the review fix's "Request changes" trigger and N6 work as designed. Needs the repository owner to create the account or App |
| F-31 | N11 | Comment de-duplication, proposed 27 Oct 2026 (nothing a person reads is lost; every machine-read marker keeps working): **D1** the cost ledger and its reset boundary as hidden issue properties, one per run (no race between Agents 3 and 5), the old comments still read; **D2** Agent 5's cost table one row per agent with run counts; **D3** Agent 0's prediction outcome as one line in Agent 5's report; **D4** Agent 5 skips a re-run of the same commit with the same results; **D5** Agent 0 posts a summary and the Impact Review link, not a second copy of the table, and only the "no change" note for an unchanged re-analysis; **D6** no "no update needed" notes (the run-once flag hidden); **D7** a cost line on the comments a stopped story already gets. Expected: SCRUM-187's 20 comments → 4, SCRUM-202's 14 → 3 |

**Agreed priority (27 Oct 2026)** - fixes first that keep the agents' knowledge true, then story state, then production readiness:

- **P1 - knowledge stays true:** P1-1 inventory update (G12, PR #224) → P1-2 context update for every story: additions for new features, removals, scoped and size-bounded (F-8, F-11, F-10, F-9, PR #225) → P1-3 no silent drop of an approved test case (F-13, PR #227) → P1-4 planned inventory entries and new pages (F-12, L25, G14, PR #229).
- **P2 - story state and cost:** F-16 (a closed-unmerged PR resets the story), F-1, F-3, with F-2, F-4, F-5 (PR #230).
- **P3 - production readiness:** F-21, F-22, F-23, with F-7, F-19 and F-24 (this change).
- **P4 - identity and noise:** F-30 (needs the repository owner), F-31 comment de-duplication (D1-D7).
- Then the rest in the order below. All of it is validated together in UC-7.

Order of the rest (before the priority plan): F-1 to F-7 (then run UC-5) with the correctness fixes F-13 and F-16; then continuous running - F-21 and F-22; then operational safety - F-23, F-24, F-25; then change detection - F-14, F-15; then the notes lifecycle together - F-8 with F-9 and F-10, then F-11, F-12; then scale - F-17, F-18, F-19, F-27, F-29, F-28, F-20; F-26 when the pipeline is reliably green. Each fix gets a validation run added to section 2 when it is built.

---

## 5. Closed

Gaps found earlier and fixed, for reference (details in [AI_CONCEPTS.md → failure catalogue](./AI_CONCEPTS.md#lessons-learned--the-failure-catalog)):

| Gap | Fixed by |
|---|---|
| `reconcile.closed_scans` configured but never read | #200 |
| Agent 0's cost missing from the story's table | #200 |
| Test cases without the story's Components | #200 |
| A notes-only PR failing on a live-site flake it could not cause | #200 |
| The golden-rule guard missing newer prompts | #200 |
| Drift runnable only on its schedule | #200 |
| `ai-update` failing on step functions it left unused | #199 |
| G1: an edit no plan named (orphan cleanup) or a PR opened during generation was not checked against other open PRs | #230 (P2, F-1) |
| G2: two change stories could revise one test case before either had a PR | #230 (P2, F-2) |
| M1: a failed story's model cost landed on the next story in the scan | #230 (P2, F-3) |
| M2: up to 6 stories in a 10-minute Agent 2 job | #230 (P2, F-4) |
| M3: Agent 3 gave up on a runner result still queued for the browser | #230 (P2, F-5) |
| G8: a new story whose PR closed unmerged stayed ai-coded and In Review | #230 (P2, F-16) |
| Step coverage accepting steps from a sibling module | #199 |
| Two open stories conflicting on files, duplicating scenarios, or flaking each other's browser tests | #201 |
| Title-based duplicate detection never matching a pipeline test case | #201 |
| G3: Agent 0 "write nothing" ignored by the full scan (hand-over ran live) and by reconcile | #205 |
| G4: a one-story manual run reconciled every `impact-applied` story | #205 |
| L13: `mode` = `drift` silently ignoring a `story_key` (now refused) | #205 |
| G9: an acceptance criterion verified by no test - a change story removing a field went green against an application that still had it (SCRUM-206, PR #208) | #209 |
| G10: a reviewer's predicted failure kept blocking after its own scenario passed, because another test was red (an HTTP 503 from the site; a change story's expected pre-deployment failure) - PR #211 | #212 |
| G11: Agent 1 approved an exact cart quantity in a signed-in test case that Agent 2's gate then refused on every attempt, and the scan retried the story every 30 minutes (SCRUM-187) | #215 |
| G12: the pipeline never wrote the inventory - a new feature's live elements never reached it (so Agent 2 left those test cases out), dead keys stayed, a changed selector needed a person to run scripts | #224 (`core/inventory_update.py`) |
| L17: the context update's rewrite call read every module and every inventory note, not the story's Components (Agent 1 used its own selection rule) | #225 (P1-2, F-10) |
| L15: a new feature, or a change story adding a rule, never reached the app notes - the context update could only replace or rewrite, never add | #225 (P1-2, F-8) |
| L18: a removed element's key had to stay for its absence test, so after deployment the nightly checks reported it stale every night, the drift job raised that test as affected, and the key was never cleaned up | #225 (P1-2, F-11) |
| L16: nothing measured the notes' size or repetition, while every selected module goes into each prompt | #225 (P1-2, F-9) |
| G13: Agent 3 sent every changed file whole; a PR editing the large guides made a ~241k-token prompt and the review failed with no comment (PR #225) | #225 (documentation as diffs, a changed-files budget) |
| G5: an approved test case Agent 2 could not automate was left out with a word only in the dry-run notes - not in the PR, not on the story, which still got `ai-coded`; the duplicate check's title clash and `ai-update`'s unmarked match were logged only | #227 (P1-3, F-13, `agents/agent2_coverage.py`) |
| G14: the nightly inventory update added a footer field - already in the inventory as one page's key - to four other pages under a new name (PR #228, closed) | #229 (P1-4: other pages' keys marked by owner) |
| L19: tests could not be written before a feature was deployed (the inventory comes from the live crawl) | #229 (P1-4, F-12: planned entries) |
| L25: a new page's elements were never proposed; nothing said the page existed | #229 (P1-4: planned pages; unlisted pages listed) |
| N1: no run tested `main` unless a pull request opened - an application regression with no PR open was found by the next PR | this change (P3, F-21) |
| N2: a test failing on `main` reached nobody | this change (P3, F-22) |
| N3: a scheduled agent failing run after run, or a refused / expiring credential, showed only as red runs nobody was told about | this change (P3, F-23) |
| N4: nothing limited model spend; a spent provider budget stopped every agent at once | this change (P3, F-24) |
| L14: a failure that outlasted the retries read as a failed test in the summary and Agent 5's report | this change (P3, F-7) |
| L22: a failure was final on the first try (only a named 5xx/429 was re-run) and flakes were never counted | this change (P3, F-19) |
