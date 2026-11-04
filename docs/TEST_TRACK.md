# Test track: live validation of everything built

Every implementation is first proven offline (unit tests, sandbox runs against
a fake Jira and repo host, deliberate breaks). This file tracks the second half:
**the live check of each one against the real Jira, GitHub Actions, the model
gateway and the application under test.**

All live testing is done **at the end, after the implementation work, in the
grouped sessions below**, so one story run proves as many items as possible.

**Rules**

1. Every fix or feature adds its rows here when it is built: status ⬜, the PR
   and fix id (`F-n`) in *Built in*. Every merged change is also listed in
   [Every merged change and where it is proven](#every-merged-change-and-where-it-is-proven).
   A unit test (`tests/unit/test_test_track.py`) fails when a fix marked
   **Done** in [VALIDATION_AND_KNOWN_GAPS.md](./VALIDATION_AND_KNOWN_GAPS.md) §4
   has no row, a fix not done is missing from *Not built yet*, or a PR named in
   `CHANGES.md` is missing from the coverage list.
2. Before a session, read each row's expected result; change it first if it
   no longer matches the design - never after the run.
3. Record the result in the row: ✅ with the date and evidence (run link,
   issue key, PR number), or ❌ with the gap id opened for it in
   VALIDATION_AND_KNOWN_GAPS.md §3. A row with sub-checks passes only when all
   of them pass.
4. A failure is fixed like any gap (a fix, its tests, its own rows here), then
   the row is run again.
5. TG-0 re-proves what was already validated live before P1-P4 (V1-V8), so a
   later change that broke it is found. Its rows are checked on the stories the
   other sessions run anyway.

**Status:** ⬜ not run · ✅ passed · ❌ failed (gap id) · ➖ partly (which part)

---

## Validation plan (4 Nov 2026): six runs, one story merged

The rows are grouped into six runs so that one story or one induced failure proves as many rows as possible, **without growing the repository**. 147 rows are open; each is in exactly one run.

**Keeping the repository small**
1. **One new story is merged in the whole plan:** Run C's P1, which adds one feature file, one step-definition file and its page-object methods. Every other story's PR is **closed unmerged**. Change stories describe changes the application under test never deploys, and closing their PRs is itself what E2, R6 and E26 check: reconcile undoes them.
2. Analysis rows run as **Agent 0 only** (no PR) or `--dry-run`.
3. An induced failure is a **throw-away commit**, reverted within its night window, with its branch deleted. A config or secret change is made through a repository variable or a workflow input where possible, and undone right after its row.
4. Held-out Jira stories and their test cases are closed as *Won't do* afterwards.

| **Run** | **When** | **Stories and setup** | **Rows** | **Repo growth** |
|---|---|---|---|---|
| **A** Analysis day | Day 1, about an hour | Label SCRUM-204, SCRUM-205 and SCRUM-207 `impact-check`. Create held-out stories: **H1a/H1b** rename a text that is on several pages, H1a with a Component and H1b without; **H2** a new validation rule on an existing form; **H3** a field removed on another page. One full scan, then a second one. A hand-made PR changing a page-object method and an inventory selector, closed. Agent 0 with `mode` = `drift`, with `dry_run`, with one `story_key`. SCRUM-187 with `--dry-run`. Close every context-update PR unmerged. | A4, A5, A6, H1, H2, H3, P6, B, C, S1-R, E33a-c, R7, E35g, E35i, E44 (change half; the new-feature half is Run C's P1), E5 (H2's notes-only PR), E57 (H1a/H1b) - **19** | none |
| **B** One change story, full cycle | Days 2-3 | H2 (from A) and SCRUM-206 (removes a field) through Agents 1-5. A person edits H2's Impact Review. `ai-update` on an owner while the story PR changes its files. H2 handed over before SCRUM-206 is analysed (G2). Both PRs closed unmerged with `reconcile.closed_scans: 1`. Agent 3 re-run on #211. | E1, E2, E3, E10-E13, E16, E20, E22, R3, R6, G2, E35c, E35d, E35f, E36e - **17** | none |
| **C** New stories in flight | Days 3-6, with D's nights | Four new stories released together. **P1** (merged): a page reached through the menu, live but added as `planned_page`; test cases: one plain, one `[Positive] <title of an unmarked scenario on main>` (E9), one repeating another story's marked title (E24c), one needing an element not in the inventory (E24a, then E24d with `ai-update`). On P1's PR: two reviewers at once plus a line comment from an account without write access (E58); a comment asking to drop an approved check (E52); Approve, then merge while Agent 4 runs (E50). **P2** (closed unmerged): the same page object as P1, a test case whose scenario P1's PR adds, a `planned` element that is not live; `ai-regenerate` once; the day budget set just above the day's spend during its review fix. **P3**: needs a page the inventory lacks; keep `human-approved` over a scheduled Agent 2 run. **P4**: given a partial set of linked test cases (Agent 1 fails it). `max_stories_per_run: 2`. | R2, R4, R10, E6-E9, E21, E23, E24a, E24c-e, E25a, E26, M1-M3, G1, E14, E32b, E32c, E35a, E35b, E35e, E36d, E45a-c, E47, E49-E52, E55, E56, E58 - **37** | P1 only |
| **D** Nights on `main` | The nights of B and C | Mostly nothing: the nightly runs, drift and Inventory Health. Before night 1 you run `tidy_defect_labels`. **Night 1:** one throw-away commit breaking two existing tests (a login reference test and a cart test with an old defect) and adding an unmarked feature file, `defects.max_new_per_run: 1`, pushed twice in a row. **Night 2:** unchanged. **Night 3:** reverted. **Night 4:** one break back, with `MAX_RETRIED_TESTS=1`. **One more night:** a broken report path. Jira's defect type briefly given a required field. Inventory Health once by hand with `BASE_URL` elsewhere. | E19a-g, E25b-f, E30a-c, E31a-e, E31g-k, E37, E39, E40a, E40c, E40d, E41, E42a-d, E46, I8, R8 - **38** | none |
| **E** Operations | One sitting, after B | The health issue, then induced failures one at a time, each undone: failed scheduled runs, refused or expiring credentials, the App's key, the App id emptied, budgets per story and day. A throw-away PR with a syntax error, and one with a wrong `app_under_test.health_check`, both closed. Agent 3's log on the next docs PR. Optionally, the Jira Automation rule. | E27a-k, E32a, E32e-g, E35h, E35k, E36a, E36f, E36g, E38, R9, E29f, E34, E40e, E45d - **26** | none |
| **F** Opportunistic | Throughout | Nothing: read Agent 4's summary whenever a 5xx burst, an outage or a flaky test happens | E15, E17, E28, E28b, E29a-c, E29e, E29g, E40b - **10** | none |

### The runbook: one sequence, with the stories

The stories exist in Jira with no trigger label and the label `validation-2026-11`, so nothing runs until a step labels them. Each step lists what to do and the rows it proves. Every open row is in exactly one step.

| **Step** | **Do** | **Rows** |
|---|---|---|
| **0** Before | Merge the scope fix (notes changes follow the story's pages). Check on the live site that the Test Cases page shows "Feedback for Us"; if it does not, edit SCRUM-293's fourth criterion. Have one more GitHub account with write access and one without (for E58). | - |
| **A1** | `shadow_mode: true`; label SCRUM-296 `impact-check`; one scan; `shadow_mode: false` | R7 (shadow half) |
| **A2** | Label `impact-check`: SCRUM-204, SCRUM-205, SCRUM-207, SCRUM-290 (rename, no Component), SCRUM-291 (subject required), SCRUM-295 (rename, Component Cart), SCRUM-296 again; one full scan in live mode | A4, A5, A6, H1, H2, H3, R7, E35g, E44, E5, E57 |
| **A3** | The same scan once more | S1-R |
| **A4** | Agent 0 by hand: a full scan with `dry_run`; one `story_key`; `mode` = `drift` alone and with a `story_key`; `python -m agents.agent0_impact --story SCRUM-187 --dry-run` | E33a, E33b, E33c, C, P6 |
| **A5** | A hand-made PR changing one page-object method and one inventory selector; read Agent 0's comment; close it | B |
| **A6** | Check the bot's Jira capabilities on SCRUM-291 (`properties`, `update_comment`); delete its cost comment and see the next run post it again. Close every context-update PR of Run A unmerged. | E35i |
| **B1** | SCRUM-291: edit its Impact Review, approve; hand-over; Agent 1's test cases (the rejection step); `human-approved`; Agent 2 opens its PR | E13, E36e, E35f, E3 |
| **B2** | SCRUM-206 analysed after SCRUM-291 was handed over; through Agents 1-2; retried once | G2, E11, E12, E22, R3, E20, E35c |
| **B3** | While SCRUM-291's PR is open: `ai-update` on SCRUM-284 (it owns the contact form) - it waits. After that PR closes: retire SCRUM-289 and `ai-update` SCRUM-284 again; close its PR unmerged and restore SCRUM-289 | E10, E1 |
| **B4** | SCRUM-187 `human-approved`; Agent 2 codes it; close its PR unmerged | E16, E35d |
| **B5** | `reconcile.closed_scans: 1`; close SCRUM-291's and SCRUM-206's PRs unmerged; two scans undo them | E2, R6 |
| **C1** | `plan_inventory page` for the Test Cases page (heading and list - not the feedback section) and `plan_inventory element` for a search box on it that does not exist live; `module_budget_chars` lowered for one merge; Agent 1 and Agent 2 `max_stories_per_run: 2` | E25a |
| **C2** | Label `impact-check`: SCRUM-292, SCRUM-293, SCRUM-294, SCRUM-297. Agent 0 releases them and starts Agent 1; Agent 1 takes two, starts itself for the rest, and refuses SCRUM-297 (it has SCRUM-298 linked already) | E45a, E45b, E45c, R10 |
| **C3** | Before approving SCRUM-293's test cases, rename one to `[Positive] <an unmarked scenario on main>` and one to another story's marked scenario title. Approve SCRUM-292, SCRUM-293 and SCRUM-294 together. Leave SCRUM-292 approved over a scheduled Agent 2 run; run it once with `--dry-run`. `ai-regenerate` SCRUM-294 while SCRUM-293's PR is open. | M1, M2, E49, E55, E24e, E6, E7, E8, M3, G1, E9, E24c, E56, R2 |
| **C4** | On SCRUM-293's PR: the second account and you review at once, the read-only account adds a line comment; one comment asks to drop a check its test case states. During SCRUM-294's review fix, set the day budget just above the day's spend; check again the next day. Read Agent 3 on both PRs (SCRUM-294's red on its search step only) and Agent 5's reports; re-run *Post Results to Jira* once. | E58, E52, E32b, E51, E32c, R4, E14, E35a, E35b, E35e |
| **C5** | Approve SCRUM-293 and merge it while Agent 4 still runs. Its notes addition (no Component; over the lowered budget). Add the feedback section to the inventory; `ai-update` SCRUM-293 (the missing test case is added, the notes proposed again). Count the week's scheduled runs. | E36d, E50, E21, E23, E24a, E24d, E47 |
| **C6** | Close SCRUM-294's PR unmerged; remove the planned search box; restore `module_budget_chars` and `max_stories_per_run` | E26 |
| **D** | The nights of B and C, as in Run D above | E19a-g, E25b-f, E30a-c, E31a-e, E31g-k, E37, E39, E40a, E40c, E40d, E41, E42a-d, E46, I8, R8 |
| **E** | One sitting after B, as in Run E above | E27a-k, E32a, E32e-g, E35h, E35k, E36a, E36f, E36g, E38, R9, E29f, E34, E40e, E45d |
| **F** | Throughout | E15, E17, E28, E28b, E29a-c, E29e, E29g, E40b |
| **After** | Close every `validation-2026-11` story and test case as *Won't do*; delete the throw-away branches | - |

If SCRUM-292's early stop is recorded as blocked rather than `(failed)`, M1 is not proven by C3: note it and take the next story that fails in a scan.

Older rows name the sessions S1-S8 of the first plan: **S1** is Run A, **S2** is Run B, the stories of **S3-S5** are Run C's P1-P4, **S6** is Run D, **S7** is Run E and **S8** is Run F.

---

## TG-0 · Regression: what was proven before P1-P4 still works (Runs A-E)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| R1 | #128, #140, #142, #158, V1 | A new story end to end (S3's P1 or S5's new story) | Agent 1's test cases pass its own check before they are written; Agent 2 extends a committed page object (no method dropped), its PR title names the story; Agents 3-5 run; Story Done on merge moves the story to Done and skips a merged PR that is not a story branch | ✅ | SCRUM-283 (PR #251) and SCRUM-284 (PR #263), 3-4 Nov: Agent 1's coverage comments; #251 extends `product_detail_page.py` and `products_page.py` through the gate; titles name the story; Agents 3-5 ran; Story Done moved both to Done (run 41761453371) and skipped the merged notes PR #261 ("not a story branch", run 41755421332) |
| R2 | #143, #144, #146, #190, #193, #215 | Agent 2's gates on the stories of S3-S5 (the run logs) | Any validator error is routed to the repair loop (none logged as unroutable); a re-defined Then step asserts no more than the committed one; a page-object call no class defines is refused; a scenario that never signs in may claim exact state, a signed-in one may not (unless the quantity rule of #215 applies) | ⬜ | |
| R3 | #187, #188 | S5's removal story: Agent 1's test cases | "No row for 'X'" (a named entry) is accepted; "the cart has no rows" (the whole page) is refused | ⬜ | |
| R4 | #149, #150, #151, #152, #162 | Agent 3 on the PRs of S2-S5 | A review blocks only by naming a concrete failure; a predicted failure is checked against Agent 4 on the same commit; a finding on an unchanged line is shown as *Pre-existing* info, not blocking; one review per PR, from the current reviewer | ⬜ | Partly: one review per PR from the current reviewer on #251 and #263; but #263's first review blocked over a method it could not see in the diff, with no failure named (fixed in #265: E56) |
| R5 | #155 | Agent 5 on any story of S3 | The report counts the story's own tests only (not the whole suite); the Jira comment renders tables, bold and links (no literal separator rows of dashes or `**`) | ✅ | SCRUM-283 "All 3 tests passed" and SCRUM-284 "All 2 tests passed" (4 Nov) while the E2E suite ran 20-22: the story's own tests only; tables, bold and links render |
| R6 | #126-#132, #164-#175, #181, #185, #186, V3-V5 | S2's change stories | A person's edit of the Impact Review is read back (decisions from linked keys); hand-over, splice into the owner's files, orphan step clean-up, undo after a close on two scans, a retry counted as a new attempt; a context-update marker blocks a new proposal only while its PR is open | ⬜ | |
| R7 | #159, #163 | S1 in live mode, one held-out story with `shadow_mode: true` | Live writes the Impact Review; shadow writes only its report and leaves `impact-check` off the story | ⬜ | |
| R8 | #139, #192, sweeper | The schedules around S6 | `artifact_cleanup` deletes artifacts older than 2 days; the nightly drift job uploads `inventory-drift-report` and the next scan reads it; the sweeper re-triggers a PR whose checks never ran (one opened while Actions was busy) | ⬜ | |
| R9 | #134, #135, #136 | The inventory tools by hand | `check_inventory_staleness --compare` lists uncovered live elements; `--propose` writes a proposals file; `apply_inventory_proposals --dry-run` writes nothing; `scripts.onboarding_check` is clean | ⬜ | |
| R10 | #160 | Agent 1 on a story with a partial set of test cases (S3) | The run summary is red and says what to do (delete or retire the linked cases, then `ai-ready` again) | ⬜ | |

## TG-1 · Change stories: Agent 0's analysis (Run A)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| A4 | A-series | SCRUM-205 back-to-top arrow | Nothing affected → `ai-ready`; an unchanged re-run is skipped (stage 0); the no-Component path is reported | ⬜ | |
| A5 | A-series | SCRUM-204 search ignores case and extra spaces | Stays inside one owner; tests that still hold are not must-update | ⬜ | |
| A6 | A-series | SCRUM-207 clearer wrong-password error | Unmarked legacy tests reported for revision by hand; nothing to review | ⬜ | |
| H1 | Held-out | A wording change Agent 0 has never seen (not SCRUM-203) | Matches the result written down before the run | ⬜ | |
| H2 | Held-out | A new validation rule on an existing form | Matches the result written down before the run; E13 is checked on it | ⬜ | |
| H3 | Held-out | A removed field on another page | Matches the result written down before the run | ⬜ | |
| H4 | Held-out | A new feature on a new page (S3's P1) | Nothing affected → `ai-ready` | ✅ | SCRUM-283 and SCRUM-284 (3 Nov): "Affected: 0", released to `ai-ready`, Agent 1 drafted their test cases |
| H5 | Held-out, F-31 | A story with no Component | Whole-suite analysis; the report's *No Component* line carries the advice; no separate `[agent0:no-component]` comment | ✅ | SCRUM-284 (3 Nov 13:22 IST): the report's "No Component: whole-suite analysis ... Add a Component" line; no `[agent0:no-component]` comment |
| P6 | #186 | SCRUM-187 re-analysed (dry run) | No false "review" rows | ⬜ | |
| B | Run B | A PR changing a page-object method and an inventory selector | Agent 0 posts the affected tests on the PR, no model call; the browser runs (runtime file changed) | ⬜ | |
| C | Run C | Agent 0 with `mode` = `drift` | Opens or updates the maintenance story (`inventory-drift`); scan and reconcile are skipped | ⬜ | |
| S1-R | Stage 0 | The S1 scan run a second time | Every story skipped, no model call | ⬜ | |
| E33a | #205 (G3) | A manual full scan with `dry_run` = true | Nothing written to Jira or GitHub, reconcile included; the log shows what would be done | ⬜ | |
| E33b | #205 (G4) | A manual run with one `story_key` | Only that story is reconciled; other `impact-applied` stories untouched | ⬜ | |
| E33c | #205 (L13) | `mode` = `drift` with a `story_key` | Refused with a message; nothing run | ⬜ | |

## TG-2 · Change stories: the full cycle (Run B)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E1 | #199 | An owner's `ai-update` deletes a test case whose scenario held a step's last use | The step function is commented out and listed in the PR; the final gate passes | ⬜ | |
| E2 | #200 | Close the change PR with `reconcile.closed_scans: 1` | Undone on the first scan that sees the close | ⬜ | |
| E3 | #200, F-31 | The change story's cost (its cost comment; Agent 5's table with the comment ledger) | An Agent 0 row (analysis and context update); Agent 1 did not reset it | ⬜ | |
| E5 | #200 | A notes-only context-update PR | Unit suite only, no Agent 5, Agent 3 offers no runner evidence | ⬜ | |
| E10 | #201 | `ai-update` on an owner while the story PR changes its feature or step file | Waits before any model call | ⬜ | |
| E11 | #209 | SCRUM-206 retried (removes a field) | Agent 1's coverage map covers AC1 with a step asserting the field is absent; the revised tests alone are rejected | ⬜ | |
| E12 | #209 | SCRUM-206's PR | The scenario carries the absence step, asserted on a loaded page (`is_loaded() and is_gone(...)`); against the undeployed application exactly that step fails (L20) | ⬜ | |
| E13 | #209 | H2 (a limit or restriction) | The coverage comment lists a rejection step for it | ⬜ | |
| E14 | #212 | A PR red on one scenario only, re-reviewed (Run C: SCRUM-294's PR; PR #211 is closed) | Red on the absence step only; the card-click finding lowered with "scenario ... passed"; review advisory | ⬜ | |
| E18 | #219, #220, #222 | Agent 2's review fix: a bare `/fix` after inline comments on an `ai-regenerate` PR | Fixed on the same branch (the story's own regenerated files too), declined ones with the test-case route, a reply per thread, one summary; a re-run does nothing; `/fix <text>` also takes the inline comments; a skipped event cannot cancel a waiting `/fix` | ✅ | V7: SCRUM-202, PR #221 (26 Oct). The "Request changes" trigger: E36c |
| E20 | F-10, #225 | S5's change story: `[agent0:context-update]` run | Reads only `core.md`, its Component modules and their pages' notes (prompt in the run log); no rewrite of another module in the PR | ⬜ | |
| E22 | F-11, #225 | S5's removal story | Context-update PR declares the element in `removed` (note `REMOVED by …`); after deployment the nightly check shows `GONE`, not `STALE`; Agent 0 raises no affected test for it; once the absence test is retired the next inventory-update PR deletes the key | ⬜ | |

## TG-3 · New stories: Agents 1-5 (Run C)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E4 | #200 | Agent 1's test cases | They carry the story's Components | ✅ | SCRUM-285 to SCRUM-287 carry SCRUM-283's Component (Products); SCRUM-288/289 none, as SCRUM-284 |
| E9 | #201 | A test case `[Positive] <title>` whose scenario exists without a marker | Skipped by title, listed in the PR and the story comment as needing its marker, without `ai-incomplete` | ⬜ | |
| E16 | #215 | SCRUM-187 on the next scan (persistent-state rule) | One `[agent2:blocked]` comment naming the rule, then `[BLOCK]` with no model call on later scans; a new signed-in draft stating a cart quantity is sent back by Agent 1 | ➖ | Coding once step 7 was fixed: V8 |
| E21 | F-8, #225 | S5's new story merged | Story Done on merge moves it to Done; one `context-update/<key>-notes-<hash>` PR adds its facts under its Component module (a new module for a new Component) and one `[agent0:context-addition]` comment; nothing repeated; a second run does nothing; a merged `ai-update` of its test cases proposes again; cost on the story | ⬜ | Partly: SCRUM-283 and SCRUM-284 (4 Nov): Done on merge; one notes PR each (#261 into the Products module; #264, no Component, into core.md and home.md - see #265) and one `[agent0:context-addition]` comment; a repeated line left out on #264; cost on the story. A second run and an `ai-update` re-proposal not seen yet |
| E23 | F-9, #225 | A notes addition that pushes a module over `module_budget_chars` | The PR body says so and its unit-suite check fails until the module is condensed in the same PR; `scripts.onboarding_check` reports `notes: size` / `notes: repetition` | ⬜ | |
| E34 | #225 (G13) | Agent 3 on a PR that edits the large guides (any docs PR) | A review is posted: docs shown as diffs, the changed-files section capped; a review that fails says so on the PR with secrets redacted, not a bare red check | ⬜ | Partly: Agent 3 reviewed #265, which edits the guides (4 Nov; prompt 307,315 characters); docs shown as diffs and the cap not checked in its prompt |
| E24a | F-13, #227 | S5's story: one test case needs an element not in the inventory | The PR opens with the others; the body lists it under *Approved test cases not automated* with the plan's `Skipped:` reason (or "no reason given" - note which); one `[agent2:incomplete]` comment; `ai-incomplete` beside `ai-coded`; the scan summary says `not automated: <KEY>` | ⬜ | |
| E24b | F-13, #227 | The PR's feature file | Each `# JIRA:` marker sits on the scenario that tests that test case (L31) | ✅ | `features/product_reviews.feature` (SCRUM-285 to 287) and `features/contact_us_form.feature` (SCRUM-288, 289): each marker on the scenario that tests it |
| E24c | F-13, #227 | One more test case whose summary repeats another story's marked scenario title on `main` | Listed as a title clash naming that test case; counted as not automated | ⬜ | |
| E24d | F-13, #227 | The element reaches the inventory, the PR merges, then `ai-update` | Only the missing scenario is appended; `ai-incomplete` comes off | ⬜ | |
| E24e | F-13, #227 | A story whose only test case needs a missing element (`--dry-run` is enough) | No PR; an `[agent2:blocked]` comment naming it | ⬜ | |
| E25a | F-12, #229 | Before deployment: `scripts.plan_inventory element ...` (and `page ...`) | The onboarding check is clean; Agent 2 uses the keys and its PR lists *Uses planned elements - not deployed yet*; its browser run is red on exactly those steps | ⬜ | Partly: SCRUM-284 - the contact page planned with `plan_inventory page` (#256); Agent 2 used its keys and PR #263 listed *Uses planned elements - not deployed yet*. The page was already live, so the "red until deployed" part was not shown |
| E26 | F-16, #230 | A new story's PR closed without merging | First scan: one `closed-unmerged` comment, nothing else; reopen → nothing; close again for two scans → `story-reset` comment, `human-approved` / `ai-coded` / `ai-incomplete` / `tests-run` off, `ai-processed` kept, card in To Do, test cases unchanged; not picked by Agent 2; add `human-approved` → coded again in a new PR | ⬜ | |

## TG-4 · Stories in flight and scans (Run C; G2 in Run B)

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

## TG-5 · Inventory and app knowledge, nightly (Run D)

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

## TG-6 · Test runs: retries, outages, flakes (Run F; E29f in Run E)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E15 | #213 | A PR run while the site refuses some CI requests | Retried page loads log `succeeded on attempt N`; a re-run test is listed by *Keep only the final attempt*; Agent 5 counts each test once | ⬜ | |
| E17 | #215 | A PR run during a 5xx burst | A test whose own request was refused fails as `ApplicationUnavailableError` naming it, is re-run, reads "application temporarily unavailable"; a plain assertion failure is not re-run | ⬜ | |
| E28 | F-7, #231 | The same run (still failing after the retries) | Under *Application unavailable (not test failures)* in the summary; Agent 5's *Not judged* warning and section; not an outside failure; verdict `unavailable` when nothing else failed; the check still red; Agent 3 lowers no prediction on it | ⬜ | |
| E28b | F-7, #231 | Every one of the story's tests an outage | Agent 5 posts *Not judged: the application was unavailable* without a model call | ⬜ | |
| E29a | F-19, #231 | A test that fails, then passes on the retry | *Retry failed tests once* re-runs exactly the failures; the run is green; summary and Agent 5 list it under *Passed only on the retry (flaky)* with its first failure; the health issue's *Flaky tests* table counts it, no comment | ⬜ | |
| E29b | F-19, #231 | A test failing twice | The run stays red (*Decide the E2E result*) | ⬜ | |
| E29c | F-19, #231 | More than 10 failures | No retry ("not retrying") | ⬜ | |
| E29d | F-19, #231 | A green run with retry skipped | *Retry* skipped, *Decide* green | ✅ | PR #231 runs and the merge push run 40516210923 (27 Oct) |
| E29e | F-19, #231 | A test that failed on an outage, then passed on the retry | Marked `outage_recovered`: passed, not listed as flaky, not counted on the health issue | ⬜ | |
| E29f | F-19, #231 | pytest interrupted or collecting nothing (a syntax error on a throw-away branch) | *Decide* red, naming the exit code ("no tests collected" / "interrupted"), even with no failed test in the report | ⬜ | |
| E29g | F-19, #231 | A scenario Agent 3 predicted to fail that passed only on the retry | The prediction keeps blocking (log: "passed only on the retry (flaky)") | ⬜ | |
| I8 | Open defect, root cause found (#239) | The live-site add-to-cart flake | Not seen again on the nightly runs since #239 (actions wait for the page to load); if it is, the failure lists the action requests and a pass on the retry is recorded as flaky | ⬜ | Nightly runs 31 Oct - 3 Nov green |

## TG-7 · Runs on `main` and defects (Run D)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E30a | F-21, #231 | The 03:10 IST nightly run | Unit gate and the whole E2E with the retry; artifact; summary; no story report | ⬜ | |
| E30b | F-21, #231 | A PR opened during it / it opened during a PR run | The later one waits its turn | ⬜ | |
| E30c | F-21, #231 | A push to `main` during it | Does not cancel it | ⬜ | |
| E31a | F-22, #231, #242 | A test failing on `main`, and failing again on the retry | One Bug (`ai-defect`, `ai-defect-<hash>`) naming the test, its test case and owning story, cause, fix, failure and run link | ⬜ | |
| E31b | F-22, #231 | The same failure the next night | The same Bug, times 2, no comment | ⬜ | |
| E31c | F-22, #231 | It passes, then fails again | `ai-defect-passing` and one "Suggest closing" comment; then the label off and "Failing again" | ⬜ | |
| E31d | F-22, #231 | An outage night | No Bug; one `application-unavailable-on-main` alert, resolved the next clean night | ⬜ | |
| E31e | F-22, #231 | A flaky pass on `main` | No Bug; recorded as a flake; not "passing again" | ⬜ | |
| E31f | F-22, #231 | A clean run on `main` | Nothing written to Jira | ✅ | Merge push run 40516210923 (27 Oct): E2E and triage green, no issue created |
| E31g | #232 | A push to `main` that cancels the previous push's run | That run's triage skipped; no `main-run-no-report` | ⬜ | |
| E31h | #232 | The tracker refuses a defect (e.g. a required field) | One `defects-not-written` alert; the triage job red; resolved by a run whose writes all succeed | ⬜ | |
| E31i | F-22, #231 | More new failures than `defects.max_new_per_run` (lowered to 1 for one night) | That many Bugs; one `defects-capped` alert naming the rest; resolved by the next run within the cap | ⬜ | |
| E31j | F-22, #231 | A run on `main` that leaves no readable `junit.xml` (a broken report path on a throw-away branch merged and reverted) | One `main-run-no-report` alert; resolved by the next run with a report | ⬜ | |
| E31k | F-22, #231 | Where triage runs | Skipped on a PR run; runs on a manual run of Agent 4 on `main` | ➖ | Skipped on PR #233's run (27 Oct); the manual run on `main` not yet |

## TG-8 · Operations: health issue and budgets (Run E; E32b, E32c in Run C)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E27a | F-23, #231 | Run *Pipeline health* by hand | One issue labelled `pipeline-health` (Task), description "Open alerts (0)"; the team watches it | ⬜ | |
| E27b | F-23, #231 | Three failed scheduled runs of one workflow (induced on a copy) | One `[health:open] workflow-failing:<file>` comment, watchers emailed; later checks post nothing; its next successful scheduled run → one `[health:resolved]` | ⬜ | |
| E27c | F-23, #231 | A refused model key (or a spent key budget) | `credential:model` opens; fixed → resolves | ⬜ | |
| E27d | F-23, #231 | `GH_PAT` expiring within 14 days | `credential-expiry:repo-host` opens; a replaced token → resolves | ⬜ | |
| E27e | F-23, #231 | A wrong `JIRA_API_TOKEN` in the health workflow | The run fails red, GitHub emails the workflow's owner; nothing on the issue | ⬜ | |
| E27f | F-23, #231 | `dry_run` | Findings printed, nothing written | ⬜ | |
| E27g | F-23, #231 | Issue properties written with the bot's token | A flake or spend record appears on the health issue (`property_keys`) - the one Jira capability not yet proven with the pipeline's own credentials | ⬜ | |
| E27h | F-23, #231 | A refused `GH_PAT` (revoked copy in a test secret) | `credential:repo-host` opens; the right token → resolves | ⬜ | |
| E27i | F-23, #231 | A token the provider gives no expiry for | No expiry alert | ⬜ | |
| E27j | F-23, #231 | The induced workflow of E27b deleted while its alert is open | The next check resolves the alert (the workflow is gone) | ⬜ | |
| E27k | F-23, #231 | `pipeline_health.model_check` = `models`, then `off` | `models`: the listing call succeeds with no provider endpoint configured, no completion spent; `off`: no model check, no alert | ⬜ | |
| E32a | F-24, #231 | `budget.per_story_usd` below a story's ledger total, then `ai-regenerate` | Agent 2 stops before its first model call; `budget-hold` and one `[budget:hold]` comment; not picked next scan; label removed → runs again with one more budget | ⬜ | |
| E32b | F-24, #231 | `per_day_usd` just above today's spend | `budget-warn-<day>` at `warn_at`, then `budget-day-<day>`; scans log `[BUDGET]`, end green, defer their stories; Agent 3 posts *Not reviewed: model budget reached*; Agent 5 still reports with code-written prose | ⬜ | |
| E32c | F-24, #231 | The next day | The health check resolves both alerts; the *Model spend* line restarts; records older than `spend_keep_days` gone | ⬜ | |
| E32d | F-24, #231, F-31 | Any story with prices set | Its cost comment ends with the *Story budget* line (Agent 5's table, with the comment ledger) | ✅ | SCRUM-283 "Story budget: $3.56 of $8.00 (45%)" and SCRUM-284 "⚠ Story budget: $4.60 of $8.00 (57%)" closing their cost comments |
| E32e | F-24, #231 | A story held, then reset (`ai-regenerate` or a change-story retry resets its ledger) | Its budget restarts from the reset, not from its first run | ⬜ | |
| E32f | F-19, F-24, #231 | Flake records older than `flaky_tests.window_days` | Pruned by the health check; the *Flaky tests* table no longer counts them | ⬜ | |
| E32g | F-24, #231 | A scan that fails on an error (not its timeout) after model calls | Its spend is still recorded for the day (L36: a run killed by its timeout records nothing) | ⬜ | |

## TG-9 · Story comments: each thing said once (Runs A-E)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E35a | F-31 | S3's new story, start to report | No `[LLM-USAGE]` or `[LEDGER-RESET]` comment; ONE *Model cost for this story* comment, edited after each agent run (its edit history shows it); a row per agent with modes and run counts; Agent 5's report ends with one cost line linking it, no table; the runs are issue properties `llm.usage.*` (`GET issue?properties=*all`) | ⬜ | Partly: SCRUM-283/284 - no `[LLM-USAGE]` or `[LEDGER-RESET]`; one cost comment, edited after each run, a row per agent with modes and run counts; Agent 5's reports end with one cost line linking it. The `llm.usage.*` issue properties not checked |
| E35b | F-31 | The edits of E35a | Watchers not emailed for them when the bot account may switch it off (a project administrator); otherwise the log says once that edits notify. Note which | ⬜ | |
| E35c | F-31 | A new attempt: S2's SCRUM-206 retried, or a story reset to `ai-ready` and drafted again | The old cost comment gets a *Closed ...: a new attempt started (reason)* line and keeps its figures; the next run opens a new one counted from zero; the story budget restarts | ⬜ | |
| E35d | F-31 | A story costed before F-31 (SCRUM-187 or SCRUM-202) on its next run | Its `[LLM-USAGE]` comments after the last `[LEDGER-RESET]` are in the new cost comment's total; no new `[LLM-USAGE]` comment | ⬜ | |
| E35e | F-31 | *Post Results to Jira* re-run on the same commit; then a push | The re-run posts nothing and calls no model (log: "Same commit and the same results"); the push gets a new report | ⬜ | |
| E35f | F-31 | S2's change story PR | Agent 0's outcome is a line of Agent 5's first report on the PR; no `[agent0:outcome]` comment; the next commit's report has no outcome line | ⬜ | |
| E35g | F-31 | Agent 0 on a change story with an Impact Review (S1, S2) | The story's report keeps its table, has no data block and ends "...the data the agents read back, are in <review>"; a re-analysis's delta is the report's second line; S1-R still skips an unchanged story; an undone review (reconcile) still reads as never analysed | ⬜ | |
| E35h | F-31 | A story stopped before Agent 5 (blocked, or held as in E32a) | Its cost comment shows the stopped run, `(failed)` where it raised; after the label is removed the budget line reads "raised after a budget hold" and stays under 100% (L40) | ⬜ | |
| E35i | F-31 | The two new Jira capabilities with the bot's credentials | `properties` (one request) and `update_comment` work; a deleted cost comment is posted again by the next run | ⬜ | |
| E35j | F-31 | S5's new story end to end | Comments on the story counted against a story before F-31 (SCRUM-202: 14 for 3 reports) - expected 3 reports + 1 cost comment; record the numbers | ✅ | SCRUM-283: 7 comments (2 Agent 5 reports, 1 cost comment); SCRUM-284: 8 (2 reports, 1 cost comment, 1 blocked) - against 14 for SCRUM-202's 3 reports |
| E35k | F-31 | `usage_ledger.store: comments` for one story run, then back | The original comments and Agent 5's table return; back on `auto` the story's next cost comment counts both | ⬜ | |

## TG-10 · The agents' identity (F-30) and later fixes (see the plan for each row)

| ID | Built in | Check | Expected result | Status | Evidence |
|---|---|---|---|---|---|
| E36a | F-30 | The App set up (GUIDE → Agent identity), then *Pipeline health* by hand | Its *Agent identity* step says "The agents write as the GitHub App `<name>[bot]`"; no warning; any `credential-expiry:repo-host` alert closes ("created for each run") | ⬜ | |
| E36b | F-30 | The next Agent 2 PR | Opened, committed and labelled by `<name>[bot]`; Agents 3, 4 and 5 run on it (the cascade still fires) | ✅ | PR #251 and PR #263: opened and every commit made by `multi-agent-test-automation[bot]`, review-fix commits included; Agents 3, 4 and 5 ran on each |
| E36c | F-30 | On that PR: inline comments, then **Request changes** | The review fix starts (no `/fix` needed); its thread replies and summary are the App's; those replies start no further run | ✅ | PR #251: Request changes (3 Nov 20:02 IST) started the review fix with no `/fix`; its thread replies and summary are the App's; the runs those replies fired were skipped |
| E36d | F-30 | **Approve** and merge it without a ruleset bypass | Allowed; Story Done on merge runs (its context-addition PR is the App's too) | ⬜ | Partly: the notes PRs #261 and #264 are the App's; #251 and #263 were merged with no Approve review, so "approve and merge without a bypass" not shown |
| E36e | F-30 | The other writers: Agent 0's scan (Impact Review hand-over), code-change comment, drift's inventory-update PR; the sweeper's reopen | Each as `<name>[bot]`; the sweeper's reopen re-fires Agents 3 and 4 | ⬜ | Partly: Agent 0's context-update PR #246 and notes PRs #261/#264 are the App's; the Impact Review hand-over, a code-change comment, a drift PR and the sweeper not seen |
| E36f | F-30 | The App's private key replaced by a wrong one (a copy), then restored | Every agent job fails at *Agent identity* with the reason, never writes as `GH_PAT`; GitHub emails the workflow's owner; restored → green | ⬜ | |
| E36g | F-30 | `GH_APP_CLIENT_ID` emptied for one run (GH_PAT still set) | The run writes as `GH_PAT`'s owner with the warning; restored → the App again | ⬜ | |
| E36h | #235 | A story PR merged (E36d) | Story Done on merge moves the story to Done with the branch read from the environment (the job log shows `--branch "$BRANCH"`) | ✅ | PR #263 merged 4 Nov: Story Done ran `close_merged_story --branch "$BRANCH"` and moved SCRUM-284 to Done (run 41761453371) |
| E37 | #237 | *Inventory Health* run by hand (on the branch, then nightly) | Each `AMBIG` line lists its matches (tag, classes, shown/hidden, text); the login page is reported `(signed out)` with its selectors measured, not "did not render"; no `SyntaxWarning` in the log; an ambiguous contains-match `text=` key shows a `fix:` line with its exact form; the run passes after the inventory fix, with a note (not a failure) listing the keys that could be tightened; the report never advises `multi_match` for a one-element key | ⬜ | |
| E38 | #238 | The next failure note Agent 3 posts on a PR, and the next health alert that quotes an error (or E36f, which makes the App's key fail on purpose) | No token, key block, secret value, `Key=` alias or email appears - `[redacted]` in their place; the rest of the message reads as before | ⬜ | |
| E40a | #242 | A run with failures while the application is up (any PR or night with a real failure) | *Check the application is up* reports it up (pages and elements named); every failed test is run again; a test failing twice is a failure, a pass a flake | ⬜ | |
| E40b | #242 | A night the application is not itself (or a PR run with `BASE_URL` pointed at a page that is not the application, on a throw-away branch) | The check waits `app_health.wait_minutes`, then reports it not up with the URL, title and text it was shown; no retry; every failure *not judged*; on `main` one `application-unavailable-on-main` alert with that finding and no defect | ⬜ | Partly, on a PR: #265's run on 6a39839 (4 Nov) - "the application was not up (health check) ... served without site_logo"; all 22 tests *not judged*. The `main` alert part not seen |
| E40c | #242 | A failure on `main` that fails again on the retry | Its defect is raised (or updated) as before; no `failures-not-retried` alert | ⬜ | |
| E40d | #242 | `MAX_RETRIED_TESTS` lowered to 1 on a throw-away branch merged and reverted, with two failures | No defect for the failure not run again; one `failures-not-retried` alert naming it; resolved by the next run on `main` | ⬜ | |
| E40e | #242 | A wrong `app_under_test.health_check` (a page not in the inventory), on a throw-away branch | The check says `unknown` with the reason; the run retries as before; nothing marked an outage | ⬜ | |
| E41 | #243 | *Inventory Health* on a night the verifier does not pass (or run by hand with `BASE_URL` pointed at a page that is not the application, on a throw-away branch) | *Check the application is up* runs (skipped on a healthy night); an application not up gives "The application is not up — inventory NOT checked" with what was shown; a failed login on an application that is up points at the credentials; `app_probe.json` in the artifact | ⬜ | |
| E42a | #244 | The next defect the triage raises on `main` (or E40c) | It "blocks" its test case (the test case shows "is blocked by") and "relates to" its story; it has the story's components; its description says how it was traced | ⬜ | |
| E42b | #244 | A failing login reference test on `main` (a throw-away branch merged and reverted breaking one) | Its defect relates to SCRUM-282 (`defects.trace_owners`), component Login, no `ai-defect-unmapped` | ⬜ | |
| E42c | #244 | A failing test nothing traces (a throw-away feature file without markers) | `ai-defect-unmapped`, "NOT TRACED" in the description, one `defects-unmapped` alert; adding a marker links it on the next failure and clears both | ⬜ | |
| E42d | #244 | A defect raised before #244 failing again | Its links and components are added on that update | ⬜ | |
| E45a | #248 | The next story Agent 0 sends to ai-ready (a new story labelled `impact-check`, dispatched or on the scan) | Agent 0's job ends with *Start Agent 1 when a story waits for it*: "started agent1_analyst.yml (run 1 in a row)"; an Agent 1 run (event `workflow_dispatch`, `chain` 1) starts within a minute and drafts the story's test cases; its last step finds no story waiting and starts nothing | ⬜ | Not by SCRUM-283/284: released before #248 merged (09:10 UTC, 3 Nov) |
| E45b | #248 | Three or more stories released to ai-ready at once (or labelled by hand, then Agent 1 run once) | Agent 1 takes 2, then starts itself again (`chain` 2) for the rest; no run when none waits | ⬜ | |
| E45c | #248 | An Agent 0 run with nothing released, and an Agent 1 run that fails | "no story waits for it" - nothing started; the failed Agent 1 run has no hand-off step run (the schedule retries) | ⬜ | Partly: "no story waits for it" on idle runs (3-4 Nov); the cap held at 5 - and exposed restarts for a blocked story (#262) |
| E45d | #248 | Optional: the Jira Automation rule on `human-approved` (GUIDE, "Hand-off between agents") | Approving a story starts Agent 2 (event `repository_dispatch`) within a minute, in scan mode | ⬜ | |
| E93 | Run C fixes | A story labelled `ai-ready` in the backlog - no sprint at all (SCRUM-326) - then the next Agent 1 scans | One `[pipeline:not-selected]` comment: "it is not in the sprint '<active sprint>'"; later scans post nothing more | ⬜ | |
| E92 | Run C fixes | Agent 0 with `force` on a story whose earlier context verdict was "no update needed" (SCRUM-207) | The context update runs again (a PR or a new verdict), not `already-proposed`; with its PR open, another forced run proposes nothing | ⬜ | |
| E91 | Run E fixes | `budget.per_day_usd` raised during a day whose budget alerts are open, then *Pipeline health* | Today's `budget-day` alert closes with a note naming the new limit; `budget-warn` closes once the spend is under `warn_at` of it | ⬜ | |
| E90 | Run C fixes | SCRUM-293 run again by key (its steps reach the Test Cases page through a committed page object the plan did not name) | The log says the page object joins the batch; it is repaired first with only the named methods added; the PR opens with it as an extension; no committed method lost | ⬜ | |
| E89 | Run E fixes | *Pipeline health* while the provider still answers small requests but refuses one as large as the agents' (4 Nov 2026: max_tokens 1 and 4,096 answered, 16,384 got HTTP 402) | The probe asks the agents' output room: a `credential:model` alert naming the model; the probe's cost stays a one-word reply | ⬜ | |
| E88 | Run E fixes | *Pipeline health* while the provider refuses one model the agents use (4 Nov 2026: the coding model, HTTP 402) and answers another | A `credential:model` alert naming the refused model; every distinct model in `LLM_MODELS_TO_CHECK` probed once; resolved once it answers | ⬜ | |
| E87 | Run E fixes | The model provider refuses calls for money (HTTP 402 or its budget message - 4 Nov 2026, the gateway key's credit) during an Agent 0, 1 or 2 scan | One `[BUDGET]` line naming the provider refusal (not `per_day_usd`); the scan stops at the first refusal, the rest deferred; the run is red; no story is handed back, held or blocked | ⬜ | |
| E86 | Run C fixes | SCRUM-292 run again by key (its page is not in the app inventory) | A new page object naming another page object's inventory page and using none of its elements is refused by the selector check; the repair names the page it is for, the run stops as a missing page (E49), and the `[agent2:blocked]` comment gives the `plan_inventory page` command | ⬜ | |
| E85 | Run C fixes | A scan with more candidates than `max_stories_per_run` where some are blocked or still waiting (SCRUM-292 blocked, SCRUM-293 waiting, SCRUM-201 `ai-update`) | The blocked and still-waiting stories make no model call and use up no place; SCRUM-201 is taken in the same scan instead of `[DEFER]` | ⬜ | |
| E84 | Run C fixes | Agent 2 run with `story_key` for a story labelled `ai-update` (SCRUM-201), and one labelled `ai-regenerate` | The run logs UPDATE mode (REGENERATE for the other), as a scan would; not "no work needed" in normal mode; both labels at once is refused | ⬜ | |
| E83 | Run C fixes | The second and later scans while a story waits on a file another open PR changes (SCRUM-293 on #286) | "the wait of the last scan still holds - no plan, no model call"; no new `Agent 2 (Coder, waiting)` cost row; an edit to the story or a test case, or the PR merged or closed, and it is planned again | ⬜ | |
| E82 | Run C fixes | SCRUM-292 run again with its key (its page is not in the inventory; its top-menu link needs a method the reserved navigation page object lacks) | The `[agent2:blocked]` comment lists the gate's own errors, not only its summary; it names each reserved-page method needed (`<Class>.<method>` and file) and says a person adds it or rewords the test case - not that the test case asks what the application cannot show; the run log has each refused file folded under *Refused by the final gate* | ⬜ | |
| E81 | Run B fixes | A pull request whose change affects no existing test (a story PR that only adds page-object methods) | Agent 0's report on it says "Affected: 0" with no empty table under it; a report with rows keeps its table | ⬜ | |
| E80 | Run B fixes | Set `reconcile.closed_scans: 1` (or any other Agent 0 value) in config.yaml, as B5 does, and run the unit suite | The suite stays green: the reconcile tests fix the scan count they walk, and the config guard checks every Agent 0 setting is present with the right kind of value, not its value; a misspelt or missing key still fails | ⬜ | |
| E79 | Run C fixes | SCRUM-296 coded again (its page object needs a yes/no check over a cart row) | No *Reader naming error* for a `-> bool` predicate; the PR opens; a reader returning row text under a field's name is still refused | ⬜ | |
| E78 | Run C fixes | A one-story Agent 1 or 2 run started by hand while another run of it is going, then a hand-off start while it waits | The hand-off says "a run ... is already waiting to start" and starts nothing; the one-story run is not cancelled; at its end it starts a scan when stories wait | ⬜ | |
| E77 | Run C fixes | A change story analysed again (`force`) after its context-update PR was closed unmerged (SCRUM-207 after #269) | A new PR on `context-update/<key>-2`; while that one is open, another run proposes nothing | ⬜ | |
| E76 | Run C fixes | A story analysed again (`force`) when the new analysis finds nothing, while its earlier Impact Review is open (SCRUM-295 / SCRUM-300 again) | The review is rewritten with no rows and a *Superseded* line; `impact-proposed` off, `ai-ready` on; Agent 1 then takes the story | ⬜ | |
| E75 | F-32, Run C fixes | SCRUM-296's impact-aware draft run again (7 approved test cases) | Asked with a 26,624-token budget; the draft is written (7 revisions and the absence test), or a stop names reasoning, not a loop | ⬜ | |
| E74 | Run C fixes | The next planned list element (`plan_inventory ... --family`), then a drift run | The key is in `multi_match` beside `planned`; its several live matches confirm it (*Planned elements now live*), never AMBIG | ⬜ | |
| E73 | Run C fixes | A scheduled or dispatched Agent 1 scan that meets a story with a partial set of test cases (SCRUM-297 still `ai-ready`) | The run is red once; `ai-ready` comes off with one `[agent1:stopped]` comment saying to delete or retire the linked test cases first; the next scan does not take it | ⬜ | |
| E72 | Run C fixes | An Agent 1 or 2 run that is red because of one story while others wait (SCRUM-297 beside SCRUM-292/293) | *Start Agent N again while stories wait* still runs and starts the next run; a run that took none of the waiting stories starts nothing | ⬜ | |
| E71 | Run C fixes | SCRUM-294 drafted again (its test case asserted the page "not defined in the Application Under Test") | A test case about the prompt is sent back once ("tests what the prompt describes"); the second draft tests the search box as the story describes it | ⬜ | |
| E70 | Run C fixes | *Pipeline health* on a day the repository host starts none of a workflow's scheduled runs (4 Nov: Agents 1 and 2), then on a day it starts one | One `workflow-not-starting:<file>` alert naming the runs asked for; resolved once a scheduled run starts; a workflow asking for fewer than 3 runs a day is never reported | ⬜ | |
| E69 | Run B fixes | An owner's `ai-update` that removes a test case whose page method only it used, while an open story pull request calls that method (SCRUM-284 after SCRUM-289 is retired, with SCRUM-291's PR open); then the same with no open PR calling it | With the open PR: the log says "kept ... an open pull request calls them", the method stays, the run passes. Without: the method is commented out under `# AI-ORPHAN:` and the page-object check accepts it; listed in the PR (E1) | ⬜ | |
| E68 | Run B fixes | The next wording change Agent 0 analyses (SCRUM-295 or SCRUM-290 again, with `force`) | Each element path shows its selector; no `review` row reasoning "if the step locates it by text" for an element whose selector holds no text | ⬜ | |
| E67 | Run B fixes | The next context-update PR with a passage rewrite | Each *Before* and *After* cell opens at the first difference (`…`) and closes after the last, so the two cells differ | ⬜ | |
| E66 | Run B fixes | The next context update whose rewrite puts in quotes a text the story only describes (SCRUM-207 again, with `force`) | That rewrite is under *Not applied*: "it quotes a text the story does not state"; a quote the story or the notes contain is applied | ⬜ | |
| E65 | Run B fixes | The next pull request changing a page object or inventory selector (Agent 0's code-change comment) | The comment renders: a table with its separator row, the data folded under *Agent 0 data*; an unchanged push posts nothing | ⬜ | |
| E64 | Run B fixes | Agent 0 dispatched with `story_key` SCRUM-187, `force` and `dry_run` | The unchanged story is analysed and its report printed (P6); `--force` without `--story` is refused | ⬜ | |
| E63 | Run B fixes | A story labelled `ai-ready` outside the active sprint; an `ai-update` on a story in Done | One `[pipeline:not-selected]` comment per agent and reason, naming the sprint or the status; later scans post nothing more | ⬜ | |
| E62 | Run B fixes | The next Agent 2 plan naming a page object that needs no change (as SCRUM-291's did) | The file is not committed and the log says so; the PR has a *Planned, but unchanged* section listing it | ⬜ | |
| E61 | Run B fixes | The next story with a criterion an existing scenario already verifies unchanged ("as before") | Agent 1's coverage cites the existing scenario's title; no copy is drafted; a new test titled as an existing scenario is sent back | ⬜ | |
| E60 | Run B fixes | A scheduled Agent 1 scan whose draft runs out of output room or breaks the rules twice | The story's `ai-ready` is removed and one `[agent1:stopped]` comment gives the reason; the next scans skip it; adding `ai-ready` again retries. A network, quota or budget stop leaves the label | ⬜ | |
| E59 | Run B fixes | The next answer that runs out of output room (SCRUM-296's impact-aware draft, run again) | The log shows the output's size, the repetition line (*LIKELY A LOOP* or *no loop seen*), the most repeated piece and the last characters; the cap is then raised or the prompt fixed from that evidence (F-32: reasoning, fixed in #284 - E75) | ⬜ | |
| E58 | #265 | Two people review one of Agent 2's pull requests: one comments `/fix` while a fix runs, the other submits Request changes with a summary text right after (so one waiting run is cancelled); and a line comment by an account without write access | The next fix's summary lists the cancelled request under `also handled:` and acts on its text; the cancelled run, re-run, says it was handled before; the outsider's line comment is not taken and the summary names its author | ⬜ | |
| E57 | #265, #267 | The next notes change on text that is on more than one page: a change story renaming such a text on one page, with a Component, and without one; and the next merged story with no Component whose tests use a page that has no notes module | With the Component: only its pages' own inventory values change; the same text on other pages is listed *not changed*, and notes lines, `core.md` and shared values holding it are listed for review, not changed. Without: the PR says "Agent 0's impact analysis found it changes the inventory page(s) …" and the same happens for those pages only - never a page that merely shares their Component (no seed page: *not applied - found in several parts*, nothing edited). The notes addition goes into a new module for the page's Component and says which pages were read | ⬜ | |
| E56 | #265 | The next story whose test case starts on a page reached through another ("open the home page, then click ..."); and the next Agent 3 review of a step definition calling a page-object method already on `main` | Agent 2's checks pass a first Given/When step that opens a page, or report "Opening step error ... acts before any page is opened" and repair it before the pull request opens; Agent 3's prompt lists the method under *Page-Object Methods Called* and no finding calls it missing; a test that still acts on the empty page fails at once with "No page is open", diagnosed as *no page opened before acting* | ⬜ | |
| E55 | #262 | A scheduled Agent 2 run while a blocked story still has `human-approved` (SCRUM-284 before its re-run) | *Record the stories waiting before the run* lists it; the restart step says "the run took none of the stories that waited when it began"; no workflow_dispatch runs follow | ⬜ | |
| E54 | #260 | Re-run *Post Results to Jira* on PR #251's latest run (or the next report on any story that already has one) | Agent 5 posts (or says "Same commit and the same results ... not posted again"); no PropertyHolder error | ✅ | PR #251, run 41753574787 (4 Nov): Agent 5 read its last-report record and posted "All 3 tests passed" on SCRUM-283 |
| E53 | #259 | PR #251: the reply "compare for equality" in the line-52 thread, then `/fix` | The reply is taken (the thread's first comment is not taken again); Agent 2 answers in that thread; only the step definition changes | ✅ | PR #251, `/fix` 4 Nov 06:26 IST (review-fix run #31): the reply in the line-52 thread taken, answered in that thread, one line changed |
| E52 | #258 | PR #251 after the reset: one line comment on `assert_review_confirmation` ("compare for exact equality"), then `/fix` | Only the step definition changes; the feature file's markers (`hash:` and `owner: SCRUM-283`) and titles are untouched; a comment asking to drop what a test case states would be declined with "update the test case, then ai-regenerate" | ⬜ | Outcome right on PR #251 (4 Nov 06:27 IST: feature file and markers untouched), but the repair did not touch the feature, so the guard itself was not exercised |
| E51 | #257 | PR #251 after the budget reset: comment `/fix` (or re-run the stopped review-fix run) | Both line comments are taken (made with "Add single comment"), Agent 2 pushes, replies in each thread; the earlier budget-stopped summary reads `[agent2:review-fix:not-done]` style from now on | ⬜ | Partly (4 Nov 05:43 IST): `/fix` took both line comments made with "Add single comment". A budget stop's not-done summary not seen live yet |
| E50 | #255 | A pull request merged while its Agent 4 run is still going (merge right after *Run Tests* starts) | *Checkout repository* in both jobs fetches the commit by SHA; *Post Results to Jira* succeeds after the merge | ⬜ | |
| E49 | #254 | Agent 2 with SCRUM-284's key before its page is added (or any story needing a page the inventory lacks) | The run stops after the first validation ("needs page(s) the app inventory does not have"), no repair attempt; the `[agent2:blocked]` comment names the page and the `plan_inventory page` command; a few calls spent, not ~$1.50 | ⬜ | Not by SCRUM-284: its blocked run (3 Nov 11:37 UTC) came before #254 merged (13:15 UTC) |
| E48 | #253 | SCRUM-284 run again once the Contact Us page is in the inventory (Agent 2 with its key) | No "Step coverage", "Unused step-definition" or "Drifted step wording" error for a step wrapped over several lines; the pull request opens | ✅ | SCRUM-284's run of 4 Nov: its wrapped `parsers.re` steps passed every check and PR #263 opened; 22 of 22 E2E passed after the review fix |
| E47 | #252 | The next weekday's runs (Actions, filter by event `schedule`) | Agent 0, 1 and 2 scheduled runs at :02/:32, :07/:37, :12/:42; count how many of the 19 per agent GitHub started (was 4); Agent 0's 30-minute runs run the scan job only, reconcile once (10:45) | ⬜ | Partly: the 30-minute Agent 0 runs skip reconcile (run 41708852255); the count of runs GitHub starts is open |
| E46 | #250 | `python -m scripts.tidy_defect_labels`, then `--apply` (locally with the Jira credentials), then the next defect the nightly triage raises or updates | The listing names each defect and why; after `--apply` Jira's label picker offers no `ai-defect-<code>` (only `ai-defect`, `-passing`, `-unmapped`); a new defect has the label `ai-defect` only; a repeat failure updates its defect, no duplicate | ⬜ | |
| E44 | #247 | The next new-feature story Agent 0 analyses (dispatch with its `story_key`), then a change story (Wave 4) | New feature: the report shows "Change type: new_behaviour"; one "No context update needed ... new_behaviour" comment; no context-update PR; Agent 0's cost two calls lower. Change story: the context update runs as before (wording / passage rewrites proposed) | ⬜ | Not by SCRUM-283/284: their Agent 0 runs (3 Nov ~07:50 UTC) came before #247 merged (08:40 UTC) |
| E43 | #245 | The next pull request's Agent 4 run (and one whose branch is older than a change on main) | *Checkout repository* fetches `refs/pull/<n>/merge`; the tests run on the merge result; an older branch no longer fails on main's workflow | ✅ | PR #247, run 41601050788 (3 Nov): `ref: refs/pull/247/merge` fetched; 3900 unit + 17 E2E passed. The older-branch case not seen yet |
| E39 | #239 | Agent 4 on the next three runs (PRs and the nightly run), then the defects SCRUM-268 to SCRUM-271 | The cart scenarios pass; a step after a click-navigation acts only once the page has loaded (a slow page shows as a longer step, not a lost click); the four defects get the "passing" label and comment; any later row-wait failure lists the page's action requests; a slow page shows as a longer step, never `Page.goto: Timeout ... waiting until "load"`, and a page truly not served is reported as an outage, not a failure | ⬜ | Partly: no cart failure in the nightly run of 4 Nov (20/20), PR #263 (22/22) and PR #265 (22/22, twice); the four defects' "passing" label not checked |

## Not built yet: rows to add when each is built

Everything still to implement, in one place: the planned fixes (from [VALIDATION_AND_KNOWN_GAPS.md](./VALIDATION_AND_KNOWN_GAPS.md) §4), the small backlog found while validating, and the steps that are a person's to take. Each item adds its rows above when it is built, and leaves this section.

### Planned fixes

| Planned | Rows to add when it is built | When (recommended, 4 Nov 2026) |
|---|---|---|
| F-6 snapshot-count validator | A signed-in test asserting a snapshot count or membership is refused by Agent 2's gate (L11) | After Run C - a validator, cheap |
| F-14 story edited after drafting or coding | Edited before coding → a re-draft suggested; after coding → `impact-check` suggested; a comment only | After Run C |
| F-15 test case edited or deleted in Jira | The scheduled comparison comments on the owning story suggesting `ai-update`; nothing applied | After Run C, with F-14 |
| F-17 deployment signal | A change story's failures marked expected until deployment; the context-update reminder | Later - needs a deployment source |
| F-18 tests selected by the graph on a PR | A PR runs the linked tests plus the smoke set; the full suite nightly and before merge | Later - once the suite outgrows a PR run |
| F-20 bug flow | A Bug through the configured flow gets a regression test | Later |
| F-25 stale or conflicting agent PRs | A PR behind or conflicting with `main` gets a comment with the cause and the suggested label; no force-push | After Run C |
| F-26 required Run Tests check | A red story PR cannot merge; a change story before deployment is not blocked (with F-17) | Later, with F-17 |
| F-27 per-run test data, parallel runs | Seeded data per run or worker; parallel run green; turn-taking off | Later |
| F-28 environments and browsers | A run against a second profile; a browser matrix run | Later |
| F-29 metrics report | The scheduled report's pass, flake, coverage, cost and Agent 0 accuracy figures match the sources | Later |

### Small backlog

Done in #267 (see CHANGES.md): the repair shown a feature file as it stands, the two write-access rules explained, the opening step's sort key, the duplicate-step check's unreachable half, one bot rule for review comments, `get_property`'s return type, Gherkin tags as free markers, and the jira library's false link-type warning. Nothing is left in it.

The cart and login flakes need no code: the first attempt's trace is kept in `reports/failure-evidence/` when the retry passes (the retry writes only its own failures). Download it from the next flaky run - Run F, rows I8 and E39.

### A person's steps

| **Step** | **Who** | **Row** |
|---|---|---|
| `python -m scripts.tidy_defect_labels`, then `--apply`, before Run D's first night | Repository owner (local Jira credentials) | E46 |
| Optional: the Jira Automation rule that starts Agent 2 on `human-approved` (GUIDE, *Hand-off between agents*) | Jira administrator | E45d |

## Every merged change and where it is proven

*Proven live* names the run in VALIDATION_AND_KNOWN_GAPS.md §1. *Rows* are
checks above, still to run unless marked. *Offline only* is a change with no
behaviour to see live (documentation, tests, tooling), proven by the unit suite.
Story PRs (generated tests for one story) are not listed: the story's own run
proves them.

| PR | What | Proven live | Rows | Offline only |
|---|---|---|---|---|
| #126, #127, #129, #130, #131, #132 | Agent 0 phases A-D, sandbox, design audit | V3-V5 | R6 | |
| #128 | Story Done skips merged non-story PRs | V1 | R1 | |
| #133, #134, #135, #136 | Inventory compare, proposals, onboarding kit | | R9 | |
| #137, #139 | Uncovered-element hint (off) and its snapshot | | R8 (snapshot) | #137 (off by default, L9) |
| #138, #153 | Generality audit, golden-rule guard | | | ✓ |
| #140, #142, #143, #144, #146, #158 | Page objects extended, Agent 1 checks drafts, repair routing, anonymous state, method resolution, PR title | V1, V2 | R1, R2 | |
| #141 | Agent 1 named "Test Designer" | | | ✓ |
| #147 | Sandbox from the framework baseline | | | ✓ |
| #149, #150, #151, #152, #162 | Agent 3 review invariants | V1-V5 | R4 | |
| #155 | Agent 5 scoped to the story, wiki markup | V1 | R5 | |
| #159, #163 | Agent 0 shadow / live switch | V3 | R7 | |
| #160 | Agent 1 run summary for every outcome | | R10 | |
| #164, #165, #166, #169, #171, #172, #173, #175 | A-series fixes, retry after undo | V3-V5 | R6 | |
| #174, #197, #198, #202, #203, #204, #206 | Documentation | | | ✓ |
| #181, #182, #185, #186 | A3 findings, *using is not changing* | V5 | R6, P6 | |
| #187, #188, #190, #193 | Absence wording, reused-step meaning, every error repaired | V8 (#190, #193: Agent 2's gates on SCRUM-187) | R2, R3 | |
| #192 | Actions storage clean-up | | R8 | |
| #199 | Unused steps commented out on `ai-update` | | E1 | |
| #200 | A-series open items 1-7 | | E2, E3, E4, E5, C | Golden-rule guard on newer prompts |
| #201 | Stories in flight | | E6-E10 | |
| #205 | Manual-run inputs mean what they say | | E33a-c | |
| #209 | Every criterion verified by a test that can fail | | E11-E13 | |
| #212 | A prediction judged on its own scenario | | E14 | |
| #213 | Temporary HTTP errors retried | | E15 | |
| #215 | Signed-in quantity; a refused story stops retrying | V8 (part) | E16, E17 | |
| #219, #220, #222 | Agent 2 review fix | V7 | E18 ✅ | |
| #224 | Nightly inventory update PR | | E19a-g | |
| #225 | Notes follow every story; Agent 3 docs as diffs | | E20-E23, E34 | |
| #227 | No approved test case dropped in silence | | E24a-e | |
| #229 | Planned entries, new pages, shared elements | | E25a-f | |
| #230 | Story state and scans (P2) | | E26, M1-M3, G1, G2 | |
| #231 | Production readiness (P3) | E29d ✅, E31f ✅ | E27-E32, E28b, E29e-g, E31i-k | Bool settings, SDK pin test |
| #232 | Triage false alarm, refused defect writes | | E31g, E31h | |
| #233 | The live test track | | | ✓ (docs and its guard test) |
| #234 | A story says each thing once (F-31, L40) | | E35a-k, E3, E32d, H5 | |
| #235 | The agents' own identity (F-30); a branch name never pasted into a script | | E36a-h, E18 (Request changes) | |
| #236 | The App's settings named `GH_APP_*` | | E36a (the run finds them) | |
| #237 | The nightly inventory check: matches described, login page checked signed out | | E37 | |
| #238 | One redaction rule; App tokens and keys covered | | E38 | |
| #248 | An agent that leaves work for another starts it | | E45a-d | |
| #293 | Today's budget alerts follow a raised limit; a forced re-analysis retries the context update; a labelled story with no sprint is told why it waits | | E91, E92, E93 | |
| #292 | A committed page object the steps need a method on joins the repair | | E90 | |
| #291 | The health probe asks the output room the agents ask | | E89 | |
| #290 | A provider refusing calls for money stops the run, red; the health check probes every model the agents use | | E87, E88 | |
| #289 | A new page object may not borrow another page object's inventory page | | E86 | |
| #288 | Tests own their settings; nothing-affected report without a table; a refused story names the gate's errors and a reserved page's missing method; a still-valid wait costs no plan; a story run by key follows its mode label; a story that did nothing frees its scan place | | E80-E85 | |
| #285 | A start never cancels a run already waiting to start; a yes/no predicate is not a misnamed reader | | E78, E79 | |
| #284 | What validation Run C found: scheduled runs never started are reported, a planned list declared a family, a test case about the prompt sent back, a red run still hands off, a story needing a person handed back | | E70-E77 | |
| #276 | What validation Runs A and B found: truncation evidence, a failed draft handed back, existing scenarios shown, an unchanged planned file not claimed, orphan clean-up vs the page-object contract, labelled stories told why they wait, `force`, markdown PR report, selectors for the judge, no invented quotes, the changed part of a rewrite | | E59-E69 | 13 deliberate breaks, one per fix |
| #267 | A notes change touches only the story's own pages; the small backlog | | E57 | Real-data check of both flows before Run A |
| #265 | A scenario opens a page before it acts on one; Agent 3 sees the page-object methods a pull request calls; a notes change reaches only its page; several reviewers on one pull request | | E56, E57, E58 | Agent 2's check proven on SCRUM-284's branch before and after its fix |
| #262 | The hand-off restarts an agent only after progress; the top menu reaches the contact page | | E55 | |
| #260 | A Jira issue property reads back as the JSON that was stored | | E54 | Real SDK class in the tests |
| #259 | Review fix reads a person's reply in a thread | | E53 | |
| #258 | Review fix keeps scenarios through the repair; declines dropping an approved check | | E52 | |
| #257 | Review fix: earlier line comments; a budget stop records nothing | | E51 | |
| #255 | Agent 4 checks out the event's commit by SHA | | E50 | |
| #254 | A page missing from the inventory stops Agent 2 at once | | E49 | |
| #253 | Step decorators read as Python reads them | | E48 | Regression pinned (patterns alone fail the SCRUM-284 shape) |
| #252 | Agents 0, 1 and 2 every 30 minutes, off :00 and :30 | | E47 | |
| #250 | A raised defect carries no code label | | E46 | |
| #249 | The chain cap warns only when a story is left waiting | | E45b | |
| #247 | A new-behaviour story rewrites no reference note | | E44 | |
| #245 | Agent 4 tests the pull request merged with main | | E43 ✅ | |
| #244 | Every defect linked to its test case and story | | E42a-d | Sandbox (fake Jira) only |
| #243 | Inventory Health asks whether the application was up | | E41 | Old and new summaries compared (unit) |
| #242 | The application health check; every failure retried; a defect only after a failed rerun | | E40a-e, E31a | Health check proven in Chromium (unit) |
| #241 | The nightly inventory proposal, edited: the cart's empty message by its id, the cart section named | Inventory Health (cart page) on the branch, run 41591912714; its Agent 4 run green (3 Nov) | | |
| #239 | Every action waits for the page to load; navigation needs the document, not every resource; row waits name the requests | | E39 | Race and slow load proven in Chromium (unit) |

Cited in `CHANGES.md` but never merged (evidence, not changes): #178 (replaced
by #181), #211, #214, #217, #221, #223 (story PRs used as live evidence, closed
unmerged), #228 (an inventory-update PR, closed by design).
