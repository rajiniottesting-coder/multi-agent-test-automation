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
| E9 | A pipeline test case (`[Positive] <title>`) whose scenario exists without a marker → skipped by title | #201 |
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
| E21 | Notes addition (P1-2, F-8): UC-7's new story, merged → Story Done on merge moves it to Done, then one `context-update/<key>-notes` PR adds its rules / messages / test data under its Component module (a new module for a new Component) and an `[agent0:context-addition]` comment; nothing the notes already said is repeated; a second run of the workflow does nothing; the cost is on the story | Context update |
| E22 | Removed element (P1-2, F-11): UC-7's removal change story → its context-update PR declares the element in `removed` (and its note `REMOVED by …`); merged after deployment, the nightly check shows `GONE`, not `STALE`, Agent 0 raises no affected test for it, and once the absence test is retired the next inventory-update PR deletes the key | Context update, inventory |
| E23 | Notes budget (P1-2, F-9): a notes-addition PR that pushes a module over `module_budget_chars` says so in its body and its unit-suite check fails until the module is condensed in the same PR; `scripts.onboarding_check` reports `notes: size` / `notes: repetition` | Context update |

### 2.2 The runs

| Run | Stories | Covers | Steps and expected result |
|---|---|---|---|
| **UC-1** Agent 0 batch scan (analysis only, cheapest) | SCRUM-205, SCRUM-204, SCRUM-207 + new H1, H2, H3, H5; SCRUM-187 by dry run | A4, A5, A6, P6, H1–H3, H5 | Label the stories `impact-check`; one full scan. Each report matches the result written down first. Re-run: every story skipped at stage 0, no model call. SCRUM-187 is already coded, so it is checked with `python -m agents.agent0_impact --story SCRUM-187 --dry-run` (report printed, nothing written): expect no review rows. |
| **UC-2** Re-run A2 to the end | SCRUM-229 (2 owners) | E1, E2, E3, E5 or E8, E10, I8 | Review: approve the 7 → hand-over → context-update PR (notes only: E5; inventory: its browser run takes its turn, E8). While the story PR is open, `ai-update` on an owner waits (E10). Close the PR with `closed_scans: 1` → undone on the first scan (E2). Then the owner's `ai-update` deletes a test case → unused step commented out, PR opens (E1). Cost table has the Agent 0 row (E3). Cart tests watched for I8. |
| **UC-3** Two new stories in flight | P1 (labelled `impact-check`), P2 (same page object as P1) | H4, E3, E4, E6, E7, E8, E9 | P1: Agent 0 finds nothing → `ai-ready` (H4), its cost on the table (E3); test cases carry Components (E4); one test case titled as an unmarked scenario on `main` → skipped (E9). While P1's PR is open: P2 with a duplicate test case waits before the plan (E7); remove it → waits after the plan (E6); merge P1 → P2 extends the page object. P2's PR opened next to another PR → its browser run waits (E8). |
| **UC-4** Runs B and C together | a hand-made PR; a manual run with `mode` = `drift` | B, C | The PR's Agent 0 comment lists the tests the changed method and selector reach; the browser runs (runtime file changed). The drift run opens or updates the maintenance story; scan and reconcile skip. |
| **UC-5** After the section 4 fixes | two stories in one Agent 1/2 scan, the first set up to fail | M1–M4, G1, G2 | Each story's cost lands on its own story; the scan finishes inside its timeouts; Agent 3 waits long enough for Agent 4; a cleanup-only page-object edit that another open PR changes makes the story wait (G1); a test case already approved by another change in progress is blocked in the second review (G2). |
| **UC-6** Retry the removal story | SCRUM-206 after its PR and context-update PR are closed and reconcile has undone it | E11, E12 (E13 with H2 in UC-1) | Remove `impact-reverted`, add `impact-check`; approve the review as before. Agent 1's `[agent1:coverage]` lines name the test asserting the quantity field is gone. Agent 2's PR: that step present and asserted on a loaded page; its browser run fails on exactly that step while the field is still deployed - the expected red (L20). |
| **UC-7** Final consolidated run, after P1-P4 | One new story whose feature is not yet in the inventory or the app notes (a new element on an existing page, ideally a new page too), one change story removing an element, and a drift run | E17, E19-E23 and every item P1-P4 add | Planned once the P1-P4 fixes are merged. The new story exercises the inventory update (its elements arrive through the nightly PR, or a planned entry - P1-4), the context-update addition for a new feature (P1-2), and no silent drop of a test case Agent 2 cannot automate (P1-3); the change story exercises removal in the notes and the inventory (P1-2, F-11); its PR closed once unmerged exercises the reset (P2, F-16); the drift run covers E19 (a)-(g) across nights; any 5xx burst during the runs covers E17. Each item's expected result is written down before the run |

Order: UC-1 → UC-2 → UC-3 → UC-4 → UC-6 → section 4 fixes → UC-5 → **UC-7 last**, after the P1-P4 fixes are merged.

---

## 3. Known gaps and limits

**Status:** *Fix planned* = a bug, fixed in section 4. *Limit* = accepted
behaviour of the design, documented so nobody relies on more. *Open* = cause not
yet known.

### 3.1 Stories in flight at the same time

| ID | Situation | What happens today | Status |
|---|---|---|---|
| G1 | Agent 2 `run()` (regenerate mode, or a change story whose orphan cleanup comments out methods) edits a page object that is **not in the plan** while another open PR changes it | The in-flight check covers the plan's files and the owners' feature and step files only, so that clash is not detected; it surfaces as a merge conflict. `run_update()` already checks such page objects | Fix planned |
| G2 | Two change stories approved for the **same test case** before either has a pull request | `_owners_and_blocks()` blocks a review row only when the other story has an **open PR**, so both can revise the test case in Jira. Partly mitigated: an undo restores a snapshot only if the test still has the text that change wrote, otherwise it names it for a person | Fix planned |
| L1 | Two stories change **different scenarios of one feature file** | The second waits: the guard works per file, not per scenario. Safe, sometimes slower | Limit |
| L2 | Two stories add the **same scenario with different wording** | Both are created: the in-flight check and duplicate detection compare titles | Limit |
| L3 | A person opens a pull request on a file **after** Agent 2's PR, or during the minutes Agent 2 is generating | Nothing stops a person; GitHub reports a merge conflict if the same lines change. Agent 0 lists affected tests on any PR touching `pages/` or `app_inventory/` | Limit |
| L4 | A **semantic clash across different files** (PR A renames an inventory key PR B's new page method uses) | Not detected before merge: the guard compares files, not meaning. Agent 0's code-change comment on PR A covers tests already on `main`, not PR B's; B's tests fail after A merges | Limit |
| L5 | GitHub cannot be read when Agent 2 takes the snapshot | The story proceeds without the guard (fail open), as before #201 | Limit (by design) |
| L6 | A story that waits | Its plan call is spent, recorded as `Agent 2 (Coder, waiting)`, and spent again on the retry | Limit |

### 3.2 Several stories in one scan

| ID | Situation | What happens today | Status |
|---|---|---|---|
| M1 | A story fails part-way in an Agent 1 or Agent 2 scan with more stories | Agents 1 and 2 reset the usage counter only after a success, so the failed story's model cost is charged to the next story | Fix planned |
| M2 | Agent 2 scans its three passes (normal, `ai-regenerate`, `ai-update`) | `max_stories_per_run` (2) applies to each pass, up to 6 stories, but the job timeout is 10 minutes; a kill mid-story wastes it | Fix planned |
| M3 | Agent 3 predicts a test failure on a PR whose browser run is queued behind others | Agent 3 waits 8 minutes for Agent 4; a run waiting its turn can take longer, so the prediction keeps blocking (safe, less accurate) | Fix planned |
| M4 | More than about four PRs want the browser at once | The turn cap is 900 s, so later runs overlap again | Limit (document the burst size) |

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
| L14 | The application under test is briefly unavailable (HTTP 5xx / 429) | Since #213 a page load is retried twice (3 s, 8 s) and a test whose failure names a 5xx/429 is re-run twice, 20 s apart; since #215 a failure names every 5xx/429 its test's own action requests met and never recovered from, so a refused add-to-cart call or followed link is re-run too (on #215's run it surfaced as "row not found" and "element never appeared" and was not); only an outage longer than that still fails the test, with the attempts named. Not yet: reporting such a failure as an outage apart from test failures (F-7). Seen on PR #205 (`/login` HTTP 520) and on #211/#212 (26 Oct 2026: five of seventeen tests, four page loads and one add-to-cart request, HTTP 503, while the site loaded in a browser) | Partly fixed |
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
| L25 | A **new page** (a URL the inventory has no entry for) | The crawl and the inventory-update PR visit the inventory's pages only, so a new page's elements are not proposed; it needs `generate_inventory` and `promote_draft` by hand | Fix planned (with F-12) |
| L26 | A stale key whose element the crawl now names **differently** (a renamed button) | The inventory-update PR replaces a selector only under the same generated name; a renamed element shows as an added key plus a removed or kept old key, and the person merging renames them | Limit |
| L19 | Tests are wanted **before** a feature is deployed | The inventory comes from crawling the live application, so an undeployed page or element is not in it, and Agent 2 may use inventory keys only (generation prompt rule 15: omit the behaviour) | Fix planned |

### 3.6 Traceability: every approved test case becomes a test

| ID | Situation | What happens today | Status |
|---|---|---|---|
| G5 | Agent 2 **cannot automate** an approved test case (e.g. an element is missing from the inventory) | The prompt says to omit it and name it in `notes`, but the plan's notes are printed only in a dry run - not in the PR body, not on Jira; marker injection only logs a warning when scenarios and test cases do not pair. The story still gets `ai-coded`. (A change story's splice does check coverage, `check_coverage()`; a new story's run does not) | Fix planned |

### 3.7 Change detection after coding

| ID | Situation | What happens today | Status |
|---|---|---|---|
| G6 | The **story's own requirement is edited** after Agent 1 drafted it or Agent 2 coded it (a new story, not a change story) | Agent 1's duplicate guard refuses a re-run; Agent 0's repeat check covers `impact-check` stories only. Nothing notices, and the tests keep describing the old requirement | Fix planned |
| G7 | A **test case is edited or deleted in Jira** after coding | The scenario marker carries the test case's hash, but only a manual `ai-update` label compares them | Fix planned |

### 3.8 End of a story's pull request

| ID | Situation | What happens today | Status |
|---|---|---|---|
| G8 | A **new story's PR is closed without merging** | Reconcile acts only on `impact-applied` stories, Story Done on merge ignores a close, and the sweeper handles open PRs only. The story keeps `ai-coded` and In Review, and its test cases stay active | Fix planned |

### 3.9 Running the suite over time

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L20 | A change story's PR before the change is deployed | Its app tests are expected to fail until deployment, and merging the context-update PR after deployment is left to a person; no deployment signal tells expected from real failures | Fix planned |
| L21 | The suite grows | Agent 4 runs the whole suite on every PR; only Agent 5's report is scoped to the story | Fix planned |
| L22 | Flaky or outage-hit tests (I8, L14) | Only a failure naming a temporary HTTP error is re-run (#213); other flakes are not, and there is no flake history or quarantine | Fix planned |
| L23 | A production bug needs a regression test | Every selection uses `issue_type: "Story"`; another type is possible in config but untested, and the prompts are written for stories | Fix planned |

### 3.10 Operating the pipeline continuously

| ID | Situation | What happens today | Status |
|---|---|---|---|
| N1 | **The application regresses with no PR open** (another team deploys) | `agent4_runner.yml` runs on pull requests, framework pushes to `main` and manual dispatch only - it has **no schedule**. The nightly Inventory Health run checks that selectors resolve, not behaviour. A broken feature is found only when someone opens a PR | Fix planned (critical) |
| N2 | **A test fails on `main` or in a scheduled run** | Nothing raises a defect: Agent 5 comments only on the story of a PR. The failure diagnosis and evidence exist but are not routed to a bug or a triage queue | Fix planned (critical) |
| N3 | **A scheduled agent keeps failing, or a credential expires** (`GH_PAT`, Jira token, LLM key) | Each run fails red in Actions and nobody is told; the smoke test is manual. The pipeline can stop quietly | Fix planned |
| N4 | **Model spend runs away** (a bad prompt, repeated retries, a mislabelled batch) | `max_stories_per_run` caps the number of stories, not the cost; no budget per story or per day, no alert. A story Agent 2's gate refused is no longer retried every scan on unchanged input (`[agent2:blocked]`); other failures still are | Fix planned |
| N5 | **An agent's PR goes stale or conflicts** because `main` moved (e.g. a person's PR merged first) | No rebase or regeneration; the sweeper re-triggers only PRs whose checks never ran. The PR waits for a person | Fix planned |
| N6 | **A red PR is merged** | No required status check (a decision recorded in GUIDE → Branch protection), so a story PR with failing tests can be merged and moved to Done | Decision pending |
| N7 | **Test data and isolation** | Every run shares the live application's accounts and saved state; tests run one at a time (no parallel execution). Browser turn-taking avoids collisions but rules out parallelism; no per-run data set-up and tear-down | Fix planned |
| N8 | **More than one environment or browser** | One `base_url` (an environment variable can override it) and Chromium only; no staging/production profiles, no browser matrix | Fix planned |
| N9 | **"How healthy is our testing?"** | Results, cost and Agent 0 recall/precision are posted to Jira per story but never aggregated: no pass-rate, flake-rate, coverage, cost-per-story or Agent 0 accuracy trend | Fix planned |
| N10 | **Agent 2's pull requests are opened under the reviewer's own account** (`GH_PAT`) | GitHub lets no author request changes on or approve their own PR, so the reviewer must use `/fix` instead of "Request changes", and merging needs a ruleset bypass; a required approval or status check (N6) cannot be enforced (seen live on PR #221) | Fix planned (P4) |

---

## 4. Fix backlog

| Fix | Gaps | Change |
|---|---|---|
| F-1 | G1 | One final in-flight check over **every** file in `generated_files` right before the branch is created, so any writer (plan, owner splice, orphan cleanup, future ones) is covered |
| F-2 | G2 | `_owners_and_blocks()` also blocks a row when another impacting story is in progress (`impact-proposed` or `impact-applied`), not only when it has an open PR |
| F-3 | M1 | Reset the usage counter when each story **starts**; a failed story posts its own cost |
| F-4 | M2 | `max_stories_per_run` across all three passes; a deadline-aware scan loop; Agent 2 job timeout sized for it |
| F-5 | M3, M4 | Agent 3's runner wait sized to Agent 4's turn cap; the burst size documented |
| F-6 | L11 | Validator for snapshot-count and snapshot-membership assertions |
| F-7 | L14 | Retry: done in #213 (page loads in `BasePage.navigate()`, tests whose failure names a 5xx/429 re-run by Agent 4; a 4xx still fails at once) and #215 (a failure names the 5xx/429 its own requests met). Still to do: a failure that outlasts the retries is reported as an **outage of the application under test** - separate from test failures in the run summary and Agent 5's report, and never taken by Agent 3 as evidence either way |
| F-8 | L15 | **Done (P1-2)** - when any story's PR merges (Story Done on merge), not only a new feature's. When a new-feature story's PR merges (and for a change story that adds a rule), Agent 0 proposes a **notes addition** for the story's Component module: facts only (rules, limits, test data, flow), a few lines in the module's style, written from the story **and** its merged scenarios, checked against existing text so it repeats nothing; the same reviewed context-update PR, merged after deployment. Later change stories then have a passage to rewrite |
| F-9 | L16 | **Done (P1-2)** - `module_budget_chars` (8000) per module: the unit suite fails over it, the notes-addition PR reports size and repeated sentences, `scripts.onboarding_check` warns. Condensing stays a person's job (L27). |
| F-10 | L17 | **Done (P1-2).** Call 2 of the context update reads only the story's Component modules and those pages' inventory notes, as Agent 1 does (all modules when the story has no Component) |
| F-11 | L18 | **Done (P1-2)** - the hand-over declares the element in the page's `removed` list; every checker reads missing as healthy and present again as drift (`reappeared`, `GONE` / `BACK`); Agent 0 seeds only a reappeared one; the nightly inventory update deletes the key, note and declaration once no code names it. |
| F-12 | L19 | "Planned" inventory entries a person adds from the design, marked unverified (usable by Agent 2, flagged in its PR); the nightly drift check confirms them after deployment, or reports them still missing |
| F-13 | G5 | After generation, check that every approved test case has a markered scenario (new stories too, not only the splice); each missing one, with its reason, goes in the PR body and a Jira comment, and the story is not reported as fully coded |
| F-14 | G6 | Agent 1 records a hash of the story text when it drafts; a scan compares it: edited before coding → suggest a re-draft; edited after coding → suggest `impact-check`. A comment, never an automatic action |
| F-15 | G7 | A scheduled comparison of each scenario marker's hash with its Jira test case (edited, deleted, retired): a comment on the owning story suggesting `ai-update`, never applied automatically |
| F-16 | G8 | Reconcile covers every pipeline story PR, not only `impact-applied`: a close seen on `closed_scans` scans resets the pipeline labels and the card and posts the retry steps |
| F-17 | L20 | An optional deployment signal (config or webhook) that marks a change story's failures as expected until deployment and reminds a person to merge its context-update PR |
| F-18 | L21 | On a PR, run the tests Agent 0's graph links to the change (plus a smoke set); the full suite nightly and before merge |
| F-19 | L22 | Retry a failed test once; record flakes over time; quarantine a test with a review step (extends F-7) |
| F-20 | L23 | A configured bug flow (issue type, prompt template for a regression test), validated live before use |
| F-21 | N1 | A scheduled full app-test run on `main` (outside business hours) with a run summary; no story report. Its failures feed F-22 |
| F-22 | N2 | Failure-to-defect triage: a test failing on `main` or in the scheduled run raises one Jira bug per failing test (deduplicated by test and cause, updated on a repeat, suggested for closing when it passes again), carrying the diagnosed cause, the evidence link and the owning story. Outages (F-7) and known flakes (F-19) are kept out |
| F-23 | N3 | A health check: an alert when a scheduled agent fails several runs in a row, and a scheduled credential check of the tracker, repo host and model endpoint (with an expiry warning where the API gives one) |
| F-24 | N4 | A spend budget per story and per day (config); a run stops before the next model call once it is reached and says why. The ledger already holds the numbers |
| F-25 | N5 | Detect agent PRs that conflict with or fall behind `main`; comment with the cause and suggest `ai-update` or `ai-regenerate`; never force-push silently |
| F-26 | N6 | Decide on requiring Agent 4's Run Tests check once the pipeline is reliably green, with F-17's expected-failure marking so a change story is not blocked before deployment |
| F-27 | N7 | Per-run test data (accounts and fixtures seeded per run or per worker) and then parallel execution; browser turn-taking becomes optional |
| F-28 | N8 | Environment profiles in config (base URL and credentials per environment) and an optional browser matrix in Agent 4 |
| F-29 | N9 | A scheduled metrics report built from the ledger, Agent 5's results and Agent 0's outcomes: pass and flake rates, coverage per story, cost per story, Agent 0 recall and precision over time |
| F-30 | N10 | A separate bot identity for the agents' writes - a machine user or a GitHub App token in `GH_PAT` - so a person can request changes and approve; then the review fix's "Request changes" trigger and N6 work as designed. Needs the repository owner to create the account or App |

**Agreed priority (27 Oct 2026)** - fixes first that keep the agents' knowledge true, then story state, then production readiness:

- **P1 - knowledge stays true:** P1-1 inventory update (G12, PR #224) → P1-2 context update for every story: additions for new features, removals, scoped and size-bounded (F-8, F-11, F-10, F-9) → P1-3 no silent drop of an approved test case (F-13) → P1-4 planned inventory entries and new pages (F-12, L25).
- **P2 - story state and cost:** F-16 (a closed-unmerged PR resets the story), F-1, F-3.
- **P3 - production readiness:** F-21, F-22, F-23.
- **P4 - identity:** F-30 (needs the repository owner).
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
| Step coverage accepting steps from a sibling module | #199 |
| Two open stories conflicting on files, duplicating scenarios, or flaking each other's browser tests | #201 |
| Title-based duplicate detection never matching a pipeline test case | #201 |
| G3: Agent 0 "write nothing" ignored by the full scan (hand-over ran live) and by reconcile | #205 |
| G4: a one-story manual run reconciled every `impact-applied` story | #205 |
| L13: `mode` = `drift` silently ignoring a `story_key` (now refused) | #205 |
| G9: an acceptance criterion verified by no test - a change story removing a field went green against an application that still had it (SCRUM-206, PR #208) | #209 |
| G10: a reviewer's predicted failure kept blocking after its own scenario passed, because another test was red (an HTTP 503 from the site; a change story's expected pre-deployment failure) - PR #211 | #212 |
| G11: Agent 1 approved an exact cart quantity in a signed-in test case that Agent 2's gate then refused on every attempt, and the scan retried the story every 30 minutes (SCRUM-187) | #215 |
| G12: the pipeline never wrote the inventory - a new feature's live elements never reached it (so Agent 2 left those test cases out), dead keys stayed, a changed selector needed a person to run scripts | this change (`core/inventory_update.py`) |
| L17: the context update's rewrite call read every module and every inventory note, not the story's Components (Agent 1 used its own selection rule) | this change (P1-2, F-10) |
| L15: a new feature, or a change story adding a rule, never reached the app notes - the context update could only replace or rewrite, never add | this change (P1-2, F-8) |
| L18: a removed element's key had to stay for its absence test, so after deployment the nightly checks reported it stale every night, the drift job raised that test as affected, and the key was never cleaned up | this change (P1-2, F-11) |
| L16: nothing measured the notes' size or repetition, while every selected module goes into each prompt | this change (P1-2, F-9) |
