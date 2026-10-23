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

Everything added in #199–#201 (unused-step comment-out in `ai-update`, step
coverage by runtime scope, `closed_scans`, Agent 0 on the cost ledger, test-case
Components, stories in flight, browser turn-taking) passes its unit tests but
has not yet run live: section 2.

---

## 2. Still to run (clubbed so one story run proves several things)

### 2.1 Items to cover

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

### 2.2 The runs

| Run | Stories | Covers | Steps and expected result |
|---|---|---|---|
| **UC-1** Agent 0 batch scan (analysis only, cheapest) | SCRUM-205, SCRUM-204, SCRUM-207 + new H1, H2, H3, H5; SCRUM-187 by dry run | A4, A5, A6, P6, H1–H3, H5 | Label the stories `impact-check`; one full scan. Each report matches the result written down first. Re-run: every story skipped at stage 0, no model call. SCRUM-187 is already coded, so it is checked with `python -m agents.agent0_impact --story SCRUM-187 --dry-run` (report printed, nothing written): expect no review rows. |
| **UC-2** Re-run A2 to the end | SCRUM-229 (2 owners) | E1, E2, E3, E5 or E8, E10, I8 | Review: approve the 7 → hand-over → context-update PR (notes only: E5; inventory: its browser run takes its turn, E8). While the story PR is open, `ai-update` on an owner waits (E10). Close the PR with `closed_scans: 1` → undone on the first scan (E2). Then the owner's `ai-update` deletes a test case → unused step commented out, PR opens (E1). Cost table has the Agent 0 row (E3). Cart tests watched for I8. |
| **UC-3** Two new stories in flight | P1 (labelled `impact-check`), P2 (same page object as P1) | H4, E3, E4, E6, E7, E8, E9 | P1: Agent 0 finds nothing → `ai-ready` (H4), its cost on the table (E3); test cases carry Components (E4); one test case titled as an unmarked scenario on `main` → skipped (E9). While P1's PR is open: P2 with a duplicate test case waits before the plan (E7); remove it → waits after the plan (E6); merge P1 → P2 extends the page object. P2's PR opened next to another PR → its browser run waits (E8). |
| **UC-4** Runs B and C together | a hand-made PR; a manual run with `mode` = `drift` | B, C | The PR's Agent 0 comment lists the tests the changed method and selector reach; the browser runs (runtime file changed). The drift run opens or updates the maintenance story; scan and reconcile skip. |
| **UC-5** After the section 4 fixes | two stories in one Agent 1/2 scan, the first set up to fail | M1–M4, G1, G2 | Each story's cost lands on its own story; the scan finishes inside its timeouts; Agent 3 waits long enough for Agent 4; a cleanup-only page-object edit that another open PR changes makes the story wait (G1); a test case already approved by another change in progress is blocked in the second review (G2). |

Order: UC-1 → UC-2 → UC-3 → UC-4 → section 4 fixes → UC-5.

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
| L12 | Prompt changes for Agents 1–3 | No dedicated prompt-regression eval set; the unit suite pins validators, Agent 4 runs the generated tests | Limit |

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

Then run UC-5.

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
