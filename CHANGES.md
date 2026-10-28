# CHANGES

This document records substantive changes to the framework in reverse-chronological order.

---

## October 2026 (end) — every action waits for the page to finish loading; a slow resource no longer fails a navigation; a failed row wait names the page's requests (#239)

**Why:** on 28 Oct, 4 of 8 Agent 4 runs failed cart scenarios that had been green for days (defects SCRUM-268 to SCRUM-271 raised by the triage), with no change to the tests. The trace of one (attached by the repository owner) settled it: the product page was reached by a CLICK; its heading was visible at +11.5 s and the test clicked its add button at +11.5 s, but the script that handles the button finished downloading at +19.1 s (the site's scripts took 7 to 10 s each that morning). The click went to a button nothing was listening to: no add request was made, the confirmation never showed, and on the retry a remove click on the cart page failed the same way. `navigate()` never had this gap - `page.goto` waits for the load event - but a page reached by a click was only waited for up to its element. The remove's failure was also triaged "unclassified": a wait for a row to go carried only Playwright's call log, while `wait_visible` already listed the page's action requests.

- `pages/base_page.py`:
  - `_wait_for_page_scripts()`: before driving the browser, every action helper (31 call sites: click, fill, select, check, hover, drag, upload, click_in_row, click_nth, in-frame actions, ...) waits for the document's load event. One round trip when the page is already loaded. Bounded and fail-open: a page that never finishes loading is acted on after the timeout, as before, with a warning, and that document is not waited for again; a page mid-navigation is left to the action's own wait
  - `navigate()` (found by this PR's own Agent 4 run, which then failed `Page.goto: Timeout 30000ms exceeded ... waiting until "load"` on the home page, first try and retry): a page counts as served once its document is parsed (`domcontentloaded`); the load event is then waited for the same bounded, fail-open way, so one slow resource no longer fails a page whose HTML arrived. A page not served in time is retried like a 5xx - the pending navigation cancelled first, since Chromium aborts a second goto to a URL still loading (`net::ERR_ABORTED`, proven) - and if it never is, the error says "was not served in time ... The page did not load": an outage (`core/failure_diagnosis.py`), reported apart and never a defect, not the generic "timed out" reading about an element not actionable
  - `_network_evidence_on_failure()`: `wait_for_row`, `wait_for_any` and `wait_hidden` failures keep Playwright's message first and add the page's action requests and their outcome, as `wait_visible` does
- `tests/unit/test_act_after_page_load.py` (23), including:
  - a guard that fails when a BasePage helper drives the browser without the wait first
  - the race reproduced in a real Chromium against a local page whose script arrives late: without the wait the click is lost (no request); with it the request is made and the confirmation shows
  - in Chromium, a page whose image holds the load event is navigated to and used; a page never served fails as an outage after a retry that reached the server as a fresh request
  - the four fake pages of earlier navigation tests accept `wait_until` (test doubles only)
- Verification: 13 deliberate breaks (click or click_in_row not waiting, the wait never waiting, DOMContentLoaded instead of load, no memo, a navigating page raising, a row wait losing its evidence, Playwright's message dropped; goto waiting for load again, the pending navigation not cancelled, navigate skipping the load wait, the outage rule or the diagnosis missing) - each fails a test. Full unit suite passed.
- Not in this change: the four auto-raised defects stay open until main passes again - the triage then labels them for closing

## October 2026 (end) — the nightly inventory check says what it matched, checks the login page, and fixes a one-element drift by tightening, never by silencing (#237)

**Why:** the pipeline health issue reported *Inventory Health* failing three nights in a row (25-27 Oct). Its report read `AMBIG(2)` for one key and no more, so finding the two elements needed a local reproduction; and it showed the login page as "did not render" every night - the verifier signed in first, a signed-in browser is sent away from the login page, so its selectors had never been checked. The log also began with a `SyntaxWarning: invalid escape sequence '\s'`.

- `scripts/verify_locators.py`: an unexpected multi-match (`AMBIG`, `BACK`) lists up to five matches - tag, id, classes, shown or hidden, text (`_describe_matches`, `_DESCRIBE_JS`; proven in real Chromium on a page with the same shape). The page at the login path is verified signed out, before signing in, and skipped after (`signed_out_pages`); a root that is only a fallback guess is not treated as a login page
- `inventory_tools/browser.py`: the DOM-snapshot JavaScript is a raw string - the same script, no invalid escape (proven byte-for-byte)
- `tests/unit/test_inventory_health_report.py` (12, 8 of which fail on the previous code), including a guard that no source file carries an invalid escape
- GUIDE (*Measure - verify_locators*)
- **The drift itself, and why it would recur (run #90 on the branch named both matches):** the site added a visible `<span>All Products Catalog`; the inventory's `text=All Products` is, in Playwright, a case-insensitive *substring* match, so it caught the span as well as the `<h2>` heading. Worse, the report header and the verifier's suggestion advised declaring such a key `multi_match` - which silences a one-element key instead of fixing it, so the next similar change would slip through the same way. Now:
  - the inventory key uses the exact form `text="All Products"` (proven in Chromium: one match, the h2), with a dated note on why
  - `exact_text_form` + `_count`: for an ambiguous contains-match `text=` key, the report prints a `fix:` line with the exact form when that resolves to one element
  - every run lists, as a note and not a failure, the keys whose contains-match `text=` selector could already be tightened the same way (families and conditional keys are never listed) - so the other 15 such keys are measured before they are changed, not changed blind
  - the family suggestion now leads with "meant to be ONE element? tighten it - never declare it a family to silence it", and leaves out keys with a `fix:` line; the report header, `inventory_readme.md` and the GUIDE say the same
  - tests: 24 in `test_inventory_health_report.py` (12 new)

---

## October 2026 (end) — the agents' GitHub App settings are named GH_APP_*, and its set-up walked through (#236)

**Why:** #235 named them `APP_CLIENT_ID` and `APP_PRIVATE_KEY`, beside the application under test's login secrets `APP_USER_REGISTERED` and `APP_PASSWORD` - a reader could take the App's key for part of the application's credentials. Raised by the repository owner while setting the App up, before either was stored.

- The variable is `GH_APP_CLIENT_ID`, the secret `GH_APP_PRIVATE_KEY` - `GH_` like `GH_PAT` and `GH_REPO`: GitHub's, not the application's. Every workflow, the identity action, the redaction lists, the tests and the docs use the new names; GUIDE says why
- Nothing to migrate: neither had been stored yet
- GUIDE → *Agent identity*: the set-up as a screen-by-screen walkthrough (Parts A-F, 23 steps) written while the owner set the App up - which of the long permission rows to change and which to leave (the "Agent ..." rows, Metadata), where the private key goes (downloaded at once; *Key pairs*, not *Client secrets*), why no bot shows until the App first acts, the ruleset's bypass, how to check the run, and how to undo

---

## October 2026 (end) — the agents write as their own identity: a GitHub App (P4, F-30, #235)

**Why:** the agents wrote to the repository with `GH_PAT`, the reviewer's own token, so the reviewer was the author of every agent pull request (N10, PR #221). GitHub lets no author request changes on or approve their own pull request: the review fix's *Request changes* trigger could never fire (only `/fix` worked), merging needed a ruleset bypass, and a required approval (F-26) was impossible. The token also expired and had to be rotated by hand.

- `.github/actions/agent-identity` (new, a composite action): with the variable `APP_CLIENT_ID` (and the secret `APP_PRIVATE_KEY`) it creates a GitHub App installation token for this repository with `actions/create-github-app-token@v3` - contents, pull requests and issues write, actions read; one hour; revoked at the job's end. Without the App it gives `GH_PAT`, with a warning in the run. A configured App that cannot make a token fails the step (never a silent fallback). Outputs `token` and `kind` (`app` / `personal`)
- Every job that writes as the agents takes its `GITHUB_TOKEN` from it: Agent 0's scan, reconcile, code-change (the step taken from the `base/` checkout, never the pull request's `head/`) and drift; Agent 2 and its review fix; Story Done on merge (now `timeout-minutes: 30`); the pipeline health check; the sweeper. `agents/` is unchanged: the identity is a credential
- `core/health_checks.repo_host_findings(per_run=)`: a token created per run (`REPO_HOST_TOKEN_PER_RUN`, from the step's `kind`) has no expiry to warn about, and an earlier expiry alert closes; a refused token is still an alert
- `APP_PRIVATE_KEY` added to the values Agent 3's failure note and the health alerts redact; `APP_CLIENT_ID` is an identifier (a variable - `test_workflow_secrets.py`)
- Workflow comments no longer say the agents push with `GH_PAT`
- **Security, found by actionlint on the way:** Story Done on merge pasted the pull request's branch name into its shell script; a branch name may hold shell syntax, and the job holds the secrets. It now reaches the script as an environment variable. `tests/unit/test_workflow_injection.py` fails on any `run:` script that pastes contributor-chosen text (branch names, titles, bodies, messages - actionlint's untrusted fields), and runs actionlint itself where it is installed: every workflow passes
- Tests updated: `test_context_additions.py`, `test_inventory_update.py` (the proposal steps take the identity step's token), `test_test_track.py` (the not-built group has a fixed name, *Not built yet*)
- Docs: README (secrets, troubleshooting), GUIDE (new *Agent identity* with the App's set-up steps, Route 2b, branch protection, the environment table, the sweeper, troubleshooting a token not created), TECHNICAL_DEEP_DIVE (9.6, the review fix), REUSE_FOR_NEW_PROJECT (Change 9; the agents' identity on GitLab, Azure DevOps, Bitbucket), DECISIONS ADR-025 (and a note on ADR-008), VALIDATION_AND_KNOWN_GAPS (N10 closed, F-30 done, L47, L48), TEST_TRACK (TG-10: E36a-g)

Pinned by `tests/unit/test_agent_identity.py` (47: every agent job found and wired, no step writing with `GH_PAT` directly, the step only from trusted code, every agent job inside the token's hour, the action's permissions, fallback, warning and failure, the health check's per-run token, the review fix's trigger and its own replies). `test_workflow_injection.py` (13). 15 deliberate breaks, each caught. **Not proven live: the App itself** - it is created by the repository owner (TEST_TRACK E36a-g).

---

## October 2026 (end) — a story says each thing once (P4, F-31, #234)

**Why:** a story's comments were mostly the agents' own bookkeeping (N11). On SCRUM-187, 41 of 71 comments were `[LLM-USAGE]` / `[LEDGER-RESET]`; each agent run posted its cost and every Agent 5 report repeated all of it as a table that grew by one row per run. Agent 0's report on a change story copied the Impact Review's data block; a re-analysis posted its delta and its report as two comments; the no-Component note repeated the report's own line; Agent 0's outcome was a second comment at the moment Agent 5 reported. Watchers were emailed for each. And a story whose budget hold a person released read over 100% of one budget (L40).

- **The property ledger** (`core/usage_ledger.py`): each run is the hidden issue property `llm.usage.<time>.<id>`, a new attempt `llm.reset.<time>.<id>`, a budget hold `llm.hold.<time>.<id>`. The story shows ONE cost comment per attempt, edited in place after every run (`refresh_cost_comment()`, `render_cost_comment()`): a row per agent with its modes and run count, the total, the story budget. Posted again when a person deletes it; never a new comment per run when an edit is refused; a render that missed a concurrent entry renders again. A reset closes the old comment with a line saying why. `story_ledger()` reads either store: a story's `[LLM-USAGE]` comments count until its first property reset. `has_usage()`, `spend_budget.begin_story()` and Agent 5 read through it
- `mode()`: the property ledger when the tracker has issue properties and `update_comment` and `usage_ledger.store` (new, `auto`) is not `comments`; otherwise the comment ledger, unchanged
- **Agent 5:** one cost line linking the cost comment instead of the table (property ledger); Agent 0's outcome measured before the report and shown as its line, kept once as `agent0.outcome.<hash>` (`record_outcome(save=False)`, `save_outcome()`, `outcome_recorded()` - an old `[agent0:outcome]` comment still counts); a re-run on the same commit with the same results posts nothing and calls no model (`report_fingerprint()`, property `agent5.report`), its flakes recorded only when it is another run of the tests
- **Agent 0:** with an Impact Review, the story's report keeps its readable table and points to the review for the data block (`_render_report(data_in=)`); a re-analysis's delta is the report comment's second line (`_with_delta()`), on its own only when an approved review stands; the no-Component advice is in the report's line, no separate comment
- **L40:** `spend_budget.allowance()` shared by the budget and the budget line, which reads "raised after a budget hold" for a released story
- **Tracker capabilities** (optional, `integrations/tracker.py`): `properties(issue, prefix)` (one request, `?properties=*all`) and `update_comment(issue, ref, body)` - Jira edits without notifying where the account may (a project administrator), otherwise with the notification; `LookupError` when the comment is gone. `core/dry_run.py`: the capabilities that only read pass through (`CAPABILITY_READS`)
- Not done, on purpose: the "no update needed" notes stay (the only record of that check); D7 is not needed (the cost comment shows a stopped story's cost)
- Tests updated: `test_usage_per_story.py` (a tracker with the Protocol only), `test_p2_scan_end_to_end.py`, `test_a_series_open_items.py` and `test_spend_budget.py` (both stores), `test_agent0.py` (the delta in the report, the data in the review, no separate no-Component comment, the outcome kept once in either store), `test_test_track.py` (the not-built group is TG-10; a built fix may not stay in it)
- Docs: README, GUIDE (cost tracking, Agent 5 steps, budgets, config, marker table, new hidden-properties table, troubleshooting), TECHNICAL_DEEP_DIVE (Agent 5, the ledger, the capability table), REUSE_FOR_NEW_PROJECT, AI_CONCEPTS (#52), DECISIONS ADR-024, VALIDATION_AND_KNOWN_GAPS (N11, L40 closed; F-31 done; L43-L46), TEST_TRACK (TG-9: E35a-k; E3, E32d, H5)

Pinned by `tests/unit/test_comment_dedup.py` (26: both stores, the cost comment and its edits, a reset, an old story, a deleted or refused comment, a concurrent run, the quiet-edit fallback, L40, Agent 5's line, re-run and outcome, the dry run, a reset of a story costed before, and a whole story - 4 comments where the comment ledger posts 16). 24 deliberate breaks, each caught.

---

## October 2026 (end) — production readiness: health issue, nightly run and defects, outages and flakes, spend budgets (P3)

**Why:** the pipeline could stop or overspend without anyone being told. No run tested `main` unless a PR opened (N1); a test failing on `main` reached nobody (N2); a scheduled agent failing in a row or a refused / expiring credential was only a red run in the Actions tab (N3); nothing limited model spend, and a spent provider budget stopped every agent at once (N4). A failure the application's outage caused read like a test failure (L14), and a failure was final on the first try with no count of flakes (L22).

- **F-23:** `core/pipeline_health.py` - one tracker issue (found by `pipeline-health`, created when first needed, the oldest wins), watched by the team: `[health:open] <id>` / `[health:resolved] <id>` comments only on a change, the description as the current picture, append-only records (one new issue property per record). `core/health_checks.py` + `scripts/pipeline_health_check.py` + `pipeline_health.yml` (08:50, 12:50, 16:50 IST): scheduled workflows read from the workflow files, `consecutive_failures` failed scheduled runs in a row; the repo host token and its expiry (GitHub header); the model endpoint (one-token call, or a free listing); a refused tracker fails the run; an alert for a workflow no longer scheduled closes. Tracker OPTIONAL CAPABILITIES (`create_issue`, issue properties, `check_access`) via `integrations.tracker.capability()` - not in the Protocol, so existing adapters stay valid; JiraClient and FakeJira implement them; `RepoHost` runs may carry `event` / `created_at` / `url`; `GitHubClient.check_access()`. `core/ops_settings.py` reads the four new config blocks over defaults
- **F-7:** `core.failure_diagnosis.is_outage()` (failure text only, never a captured log) and a named diagnosis for a page load refused on every attempt; `scripts/finalise_junit.py` marks `outage` in junit.xml; `core/junit_marks.py` is the one reader. Run summary: own row and section; Agent 5: `TestResult.outage`, *Not judged* warning and section, verdict `unavailable`, never an outside failure, no model call when nothing could be judged; Agent 3: outcome `outage` (no evidence); owners' result lines "not judged"
- **F-19:** the E2E step keeps pytest's exit code; *Retry failed tests once* (`--last-failed`, at most 10); `finalise_junit --retry` merges (`flaky`, `outage_recovered`, `retried`, `first_failure`); *Decide the E2E result* fails the job on what still fails; test job timeout 40. `core/flaky_tests.py` records each flake on the health issue (no comment); the summary and Agent 5 name them; Agent 3 reads green runs too, and a flaky scenario refutes no prediction
- **F-21:** `agent4_runner.yml` nightly on `main` (03:10 IST), its own concurrency group; the wait step lists every event and `scripts/e2e_turn.py` takes turns with `schedule` runs
- **F-22:** `triage` job after every run on `main` (schedule, manual on main, a push that ran the E2E): `scripts/triage_failures.py` + `core/defects.py` - one defect per test and cause (`ai-defect-<hash>`), owner from the marker, repeat updates without a comment, `ai-defect-passing` + one comment when it passes (not on a flaky pass), never closed by the pipeline; `max_new_per_run`; outage, flood and missing-report health alerts
- **F-24:** `core/spend_budget.py` checked in `LLMClient._call_with_quota_check` before every call; `BudgetExceeded(BaseException)`; per story (ledger since the last reset + this run; `budget-hold` label + one `[budget:hold]` comment; removing it allows one more; a ledger reset restarts it), per day (every process's spend recorded at exit as `spend.<day>.<micro-USD>.<unique>` on the health issue; warn and limit alerts; past days' alerts closed and old records pruned by the health check); `llm_client` lifetime counter; scans defer for the day (green) and fail a held story once; Agent 3 *Not reviewed: model budget reached*; Agent 5 code-written prose and a story-budget line; review fix pushes nothing and says why; every selection (config and Agent 0's defaults) excludes `budget-hold`. CI only (`PIPELINE_BUDGET=on/off`); without prices nothing is enforced
- Tests updated: `test_in_flight.py` (the wait step's guard and the runs listing), `test_review_scenario_evidence.py` (a green run's report is read now), `test_impact_handover.py` defaults (Agent 0's selection excludes `budget-hold`)
- Docs: README, GUIDE (Agents 4 and 5, what runs per event, labels, config, cost, CI schedule, test suites, new *Operating the pipeline*, onboarding step 8, troubleshooting), TECHNICAL_DEEP_DIVE (layout, Agent 4 steps and triage job, Agent 5, llm_client, the adapters' optional capabilities, labels, schedules), REUSE_FOR_NEW_PROJECT (Change 8), DECISIONS ADR-023, VALIDATION_AND_KNOWN_GAPS (N1-N4, L14, L22 closed; F-7, F-19, F-21-F-24 done; L35-L41; N11 and F-31 for P4's comment de-duplication; E27-E32 in UC-7; P1-4 / P2 rows now cite #229 / #230)

Pinned by `tests/unit/test_pipeline_health.py` (48), `test_outage_reported_apart.py` (32), `test_flaky_retry.py` (26, one a real pytest run and `--last-failed` retry), `test_defect_triage.py` (23), `test_spend_budget.py` (36) and `test_p3_night_end_to_end.py` (1: two nights on main through the finalise, verdict, triage and health-check scripts) - 166, plus 5 in updated files; 41 deliberate breaks, each failed a test.

---

## October 2026 (end) — story state and scans (P2)

**Why:** running several stories per scan, and several changes at once, left six gaps: a failed story's cost landed on the next (M1); up to six stories in a 10-minute Agent 2 job (M2); a page-object edit no plan named, or a PR opened during generation, unchecked (G1); two change stories revising one test case (G2); Agent 3 giving up on a queued runner result (M3); a new story whose PR closed unmerged left coded and In Review (G8).

- **F-3:** `core.usage_ledger.story_usage()` around every story Agents 0, 1 and 2 run - counter at zero; a failed run posts `<agent> (failed)` on its own story; `has_usage_comments()` reads it as that agent
- **F-1:** `agent2_coder._last_in_flight_check()` - a fresh snapshot of the open PRs against every file the batch commits, after the final gate, in `run()` and `run_update()`
- **F-2:** `_owners_and_blocks()` also blocks by `impact-applied` stories and other open reviews listing the test (`_claimed_by_open_reviews()`); `impact_handover` refuses a test another change is still revising (`_revised_elsewhere()`), so the scan waits and retries
- **F-16:** `impact_reconcile.reconcile_unmerged_story()` / `_reset_unmerged()` / `reconcile_one()` - a coded story's PR closed unmerged on `closed_scans` scans → `reconcile.story_reset_labels` off, `status_workflow.on_close_unmerged` (To Do, `board_status.move_card_on_close_unmerged()`), retry comment; `reconcile_all()` lists only acted-on stories
- **F-4:** `agent2_coder.plan_scan()` - one `max_stories_per_run` budget for the three passes; `scan_deadline_minutes` (12); `[DEFER]`; `agent2_coder.yml` timeout 25
- **F-5:** `agent3_reviewer.RUNNER_WAIT_SECONDS` = `E2E_TURN_CAP_SECONDS` (900) + `E2E_RUN_SECONDS` (480); `agent3-reviewer.yml` timeout 30; M4 burst size documented
- Tests: `test_only_the_normal_scan_pass_skips` checked `main()`'s source text; it now runs the scan
- Docs: README, GUIDE (Agent 3, Agent 0 analysis and hand-over, reconcile, board, config, in-flight, cost, troubleshooting `[DEFER]` / closed PR / hand-over waiting, label table), TECHNICAL_DEEP_DIVE (Agent 3, §9.9, §18.5, config, labels), DECISIONS ADR-022 (+ a later note on ADR-014), VALIDATION_AND_KNOWN_GAPS (G1, G2, G8, M1-M3 closed; M4 documented; L3, L6 updated; F-1-F-5, F-16 done; UC-5 rewritten step by step; E26)

Pinned by `tests/unit/test_usage_per_story.py` (11), `test_last_in_flight_check.py` (7), `test_change_in_progress.py` (10), `test_reconcile_new_story.py` (18), `test_scan_budget.py` (7), `test_runner_wait.py` (4) and `test_p2_scan_end_to_end.py` (1: one Agent 2 scan through the real `run()`) - 58; 30 deliberate breaks, each failed a test.

---

## October 2026 (end) — planned inventory entries, new pages, shared elements listed once (P1-4)

**Why:** the inventory comes from the live crawl and Agent 2 may use inventory keys only, so a test for an element not deployed yet could not be written (L19); a new page was never crawled and nothing said it existed (L25); and the first nightly inventory-update PR (#228) proposed a footer field - already one page's key - again on four other pages (G14).

- **Shared (G14):** the crawl marks other pages' live keys on each page with their owner (`SHARED_ATTR`, `collect_uncovered(shared=)`); `uncovered_entry()` returns them as `shared`; the update lists them (*Not added - already covered on another page*) and never adds them. A new element on every measured page (`inventory_update.layout_min_pages`, 3) is listed once (*Not added - new on every page: a shared section*), not added per page - found by a real-browser run of this change
- **Planned (F-12, L19):** page list `planned`, page flag `planned_page`; `core/inventory_planned.py` + `scripts/plan_inventory.py` add them with the shared refusal rules; `diff_page(declared_planned=)` → `planned_live` / `planned_waiting`, never `missing`; the update never treats a planned key as stale, confirms a live one (not on a held page), skips a planned page until one of its planned keys is live, then adds its live elements (L25); `verify_locators` `PLAN` / `LIVE` / `PLANNED PAGE`; `promote_draft` prunes `planned`; `onboarding` warns on unconfirmable entries; Agent 2's PR lists *Uses planned elements - not deployed yet* (`uses_planned` in the result)
- **Unlisted pages (L25):** `introspect.unlisted_paths()` - same-origin links matching no inventory url or `{template}` - listed in the PR body
- Tests: two fakes of `collect_uncovered` take the new `shared` keyword
- Docs: README, GUIDE (the update's table, planned entries, the inventory fields), TECHNICAL_DEEP_DIVE (layout, inventory update), `inventory_tools/inventory_readme.md`, REUSE_FOR_NEW_PROJECT, DECISIONS ADR-021, VALIDATION_AND_KNOWN_GAPS (L19, L25, G14 closed; F-12 done; L32-L34; E25 for UC-7)

Pinned by `tests/unit/test_inventory_planned_shared.py` (40); 35 deliberate breaks, 34 failed a test (the survivor is equivalent: a same-page filter the next condition also enforces). Validated end to end with a real Chromium against a local site in three phases - before deployment, a placeholder at the planned url, after deployment - running the real crawl, update, `verify_locators` and `plan_inventory`: 37 of 37 checks passed. The browser part is kept as an opt-in test: `INVENTORY_E2E=1 pytest tests/integration/test_inventory_update_local_site.py` (not in CI: it needs a browser).

---

## October 2026 (end) — no approved test case is dropped in silence (P1-3)

**Why:** when Agent 2 could not automate an approved test case, the model left it out and said so in the plan's `notes`, printed only in a dry run; marker injection logged a warning; the story still got `ai-coded`. The duplicate check's title clash and `ai-update`'s unmarked match were logged the same way (G5).

- **`agents/agent2_coverage.py` (F-13):** `missing_from_batch()` - each test case the run was given with no markered scenario, with the plan's `Skipped: <KEY> -- <reason>` line (`notes_about()`), or the cause when its key cannot be held by a marker; `skipped_gaps()` - the dedup's `title_clash` (not covered), `modified` and `legacy` (covered, need a person); `unmarked_scenarios()`; `pr_section()`, `comment()`, `record()` (one `[agent2:incomplete]` comment; `ai-incomplete` set, or cleared - only when present)
- **`run()`:** coverage after marker injection and the change-story splice, over the story's own files; a run covering none of its new test cases (and no change-story work) is refused by the final gate (`GateFailure` → `core.blocked`); the PR body gets the section; the story is told BEFORE `ai-coded`; the no-work path reports a title clash too; dry run prints it; `not_automated` in the result and the scan summary
- **`run_update()`:** the same rule for the file it updates - a generated scenario that lost its marker is missing, an unmarked legacy match is listed, not appended or counted; only unmarked scenarios the update added are listed; the label is cleared when nothing is uncovered (also on a no-op)
- Config: `agents.agent2_coder.incomplete_label: "ai-incomplete"`; `reconcile.reset_labels` adds it (config and `impact_settings.DEFAULTS`). Plan prompt: every test case left out gets a `Skipped: <KEY> -- <reason>` line. `core.blocked`'s comment names both refusals
- Tests: the in-memory tracker of `test_pipeline_tool_agnostic.py` minted keys (`ACME-T1`) no marker can hold - now `ACME-201`; its pipeline run's fake model wrote one scenario for two test cases - now two
- Docs: README, GUIDE (Agent 2 steps, label tables, config, troubleshooting), TECHNICAL_DEEP_DIVE (§5.7, §5.8, §5.11, labels, §11, §16), REUSE_FOR_NEW_PROJECT, DECISIONS ADR-020, VALIDATION_AND_KNOWN_GAPS (G5 closed, F-13 done, L30, L31, E24 (a)-(e) for UC-7; P1-1/P1-2 rows now cite #224/#225)

Pinned by `tests/unit/test_no_silent_drop.py` (24); each rule was broken on purpose (25 mutations), and each break failed a test.

---

## October 2026 (end) — the app notes follow every story, and stay small (P1-2)

**Why:** the context update ran only at a change story's hand-over and could only replace wording or rewrite untrue passages. A new feature never reached `prompts/app_context` (the next story on it was drafted from its own text alone); an element a change story removed stayed in the inventory as "stale" every night after deployment, raising its absence test as affected; the rewrite call read every module whatever the story touched; and nothing measured the notes, which go into every prompt.

- **F-10 - one selection rule:** `core.app_context.select_note_modules()` (core.md + the story's Component modules, all when none match) and `selected_page_names()`; Agent 1 calls it (behaviour unchanged); the change-story rewrite call reads only that scope (`scoped_sources()`, `_notes_block(pages=)`), and a rewrite of a file it was not shown is dropped
- **F-8 - additions at merge:** Story Done on merge runs `scripts/propose_context_addition.py` after moving the card; `propose_addition_for_story()` makes one call (`prompts/agent0_context_additions.md`, `NoteAddition` / `NoteAdditions`) over the story, its test cases, its merged scenarios and its scoped notes; `propose_additions()` places facts under a heading, as a new section or a new Component module, refuses other files and the inventory, and drops every line the notes already state (`near_duplicate()`); PR on `context-update/<key>-notes-<hash>`, `[agent0:context-addition]` marker, once per content of the story and its test cases (an `ai-update` that edits only the test cases is proposed again); cost on the story
- **F-11 - removed elements declared:** `NoteRewrites.removed` (`page.key`, from element keys - never selectors - the call is shown); `_declare_removed()` adds each valid one to the page's `removed` list; `introspect.diff_page(declared_removed=)` reads missing as expected and present as `reappeared` (drift); `verify_locators` `GONE` / `BACK`; Agent 0 seeds only a reappeared one; the inventory update retires a still-gone key no code names (never the row family); `promote_draft` prunes it
- **F-9 - size budget:** `context_update.module_budget_chars` (8000); the unit suite fails on a committed module over it; `notes_report()` lists over-budget modules and repeated sentences in the notes PR; `core.onboarding.notes_checks()` warns; `_paragraphs()` joins hard-wrapped lines so sentences, not fragments, are compared
- Docs: README, GUIDE, TECHNICAL_DEEP_DIVE (§9.7, §18.4, tree), REUSE_FOR_NEW_PROJECT, AGENT0_ONBOARDING (step 6), `inventory_tools/inventory_readme.md`, DECISIONS ADR-019, VALIDATION_AND_KNOWN_GAPS (L15, L16, L17, L18 closed; F-8, F-9, F-10, F-11 done; L27-L29; E20-E23 for UC-7)

- **Found by this PR's own review:** Agent 3 failed on it with no comment - every changed file went into the prompt whole, and the large guides made it ~964,000 characters (~241k tokens). `format_changed_files_for_prompt()` now shows a file no test reads while it runs (`prompts/`, `docs/`, Markdown - `core.test_runtime`) as its diff, and caps the section at 300,000 characters, the largest full contents falling back to their diffs first; this PR's prompt is now ~86k tokens. Test-code PRs are shown exactly as before (byte-for-byte on PRs #214, #217, #221, #223). A review that fails now says so on the PR (`failure_note()`: the error, every configured secret value redacted) instead of leaving a red check and no comment

Pinned by `tests/unit/test_context_scope.py` (16), `test_context_additions.py` (34), `test_removed_elements.py` (21), `test_notes_budget.py` (11) `test_review_prompt_budget.py` (6) and `test_review_failure_note.py` (5); each P1-2 rule was broken on purpose once (26 mutations), and each break failed a test.

---

## October 2026 (end) — the nightly crawl proposes the inventory update as a pull request

**Why:** the drift job measured stale selectors and uncovered live elements every night, but nothing wrote the inventory back. A new feature's elements never reached it - so Agent 2, which may use inventory keys only, left those test cases out - dead keys stayed, and a changed selector waited for someone to run the proposal scripts by hand.

- `core/inventory_update.py` (pure) and `scripts/propose_inventory_update.py`, a new step of the Agent 0 drift job (`if: always()`, `GH_PAT`): one proposal at a time on a dated branch `inventory-update/<date>`. A stale key is **replaced** when the crawl finds the element the generator names the same with a durable selector, **removed** when no code names it - on `main` or on an added line of an open pull request - and it is not the row family (its note and `multi_match` / `conditional` entries too), otherwise **kept** and listed; uncovered live elements are **added** with the generator's declarations (`multi_match`, `conditional`) under the proposals file's refusal rules, at most `max_additions_per_page` per page; elements the generator flags for review (no durable handle, `>> nth=` members, hidden when crawled) are listed, never added; a page with more than `hold_ratio` of its selectors stale is **not edited**. Ambiguous selectors, unreachable pages and untracked test-ids are listed. The file keeps its own JSON format, so the diff is the change
- One proposal: the same findings leave it alone; new findings close an untouched proposal (`RepoHost.close_pull_request`, new; branch deleted best-effort, since a repository may forbid deletion) and open a fresh one on a new dated branch; nothing left closes it; a proposal a person committed to - or any PR on the prefix without the marker - is never touched and no second one opened (one `kept-edited` comment per finding). Nothing is proposed or closed for a crawl that measured no page or a report older than `uncovered_max_age_hours`; no key is removed when the open pull requests cannot be read; `--dry-run` and Agent 0's shadow mode print the PR body; each body table is capped at 60 rows. No model
- `check_inventory_staleness --compare` also writes `new_element_declarations` (`introspect.uncovered_entry()`; `uncovered_elements()` unchanged). `core/inventory_proposals.refusal_reason()`: the one refusal rule for both writers. `RepoHost.close_pull_request` (20 operations; adapter, dry-run classification, both fakes); `list_open_prs(strict=True)` raises a read failure instead of returning a partial list, so the inventory update never mistakes "could not read" for "none open" (the default stays best-effort for its other callers). Settings `agents.agent0_impact.inventory_update` (defaults in `core/impact_settings.py`, equal to the shipped block)
- Docs: README (Agent 0, schedule table, tree, inventory health, RepoHost 20), GUIDE (inventory update section, drift row, config, markers, troubleshooting; the drift section no longer says Inventory Health runs `check_inventory_staleness`), TECHNICAL_DEEP_DIVE §9.6 RepoHost table, §18.1, §18.6 and the file tree (also `acceptance_coverage.py`, `blocked.py`, `collapse_junit_reruns.py`, which were missing), REUSE_FOR_NEW_PROJECT, `inventory_tools/inventory_readme.md`, DECISIONS ADR-018, VALIDATION_AND_KNOWN_GAPS (G12 closed, L18 and F-11 narrowed, L25, L26, E19; G11 credited to #215)

Pinned by `tests/unit/test_inventory_update.py` (50 tests: each rule above, flip-flop prevention, open-PR keys and their failure, report age, file format and the real inventory's byte-for-byte round trip, body limits, the PR's open / same-day / unchanged / superseded / closed / undeletable-branch / person-edited / unmarked / duplicate / failed-write paths, the script's empty, old, dry-run, shadow, no-host and live paths, the workflow step, config = defaults, the new RepoHost write, the adapter's strict listing, no duplicate proposal on an unreadable list) and `tests/unit/test_check_staleness_compare_flag.py::test_compare_records_the_generators_declarations_for_uncovered_elements`. Each rule was broken on purpose once to confirm a test fails.

---

## October 2026 (end) — `/fix <text>` also takes the open inline comments; a skipped event cannot cancel a waiting `/fix`

**Why:** found in the live E18 run on PR #221. `/fix <text>` acted on its text alone, so a reviewer who left inline comments and then wrote `/fix please address these` had every inline comment ignored - Agent 2 answered only the sentence. (In the run the text was an attribution footer the posting tool appended; a person's own words fail the same way.)

- `agents/agent2_review_fix.py` `collect_items()`: a `/fix` comment takes every inline comment no earlier summary lists, then its own text if any; a bare `/fix` is unchanged. A review is unchanged (its own inline comments, then its text). No new reach: a bare `/fix` already read those comments
- `.github/workflows/agent2_review_fix.yml`: the concurrency group moves from the workflow to the job. In the same run, Agent 2's three thread replies each fired a "review submitted" run; at workflow level those runs entered the group although the job's `if` skips them, and each cancelled the one waiting before it. A person's `/fix` posted while a fix was running would have been cancelled by Agent 2's own replies. A skipped job never enters a job-level group (the lesson Agent 4 learned on #178). The other workflows were checked: Agent 0's and Done-on-merge's groups cannot displace a run that matters
- Docs: workflow header, GUIDE (Agent 2), TECHNICAL_DEEP_DIVE §5.10, DECISIONS ADR-017

Pinned by `tests/unit/test_agent2_review_fix.py::test_fix_with_text_takes_the_open_inline_comments_and_the_text` (replaces the text-alone test) and `::test_only_a_job_that_runs_waits_its_turn`.

---

## October 2026 (end) — the review fix edits a regenerated story's own files

**Why:** the review fix took "added by this pull request" to mean "this story's file". An `ai-regenerate` or `ai-update` pull request rewrites the story's existing feature and step files, so they arrive as "modified" - and every comment on them would have been declined as "another story's file", leaving only page objects fixable.

- `agents/agent2_review_fix.py`: `feature_owned_by()` - a feature file is the story's own when every `# JIRA:` marker in it is one of the story's test cases and names no other owner; `owned_by_story()` - such modified feature files and their step files (`tests/step_defs/test_<stem>.py`) become editable. A file holding any other story's scenario (a change story's splice) stays protected; an unreadable file is not owned. Ownership is read from the markers on the PR's branch, never from the file status or a story name
- Docs: GUIDE (Agent 2, Route 2b, troubleshooting), TECHNICAL_DEEP_DIVE §5.10, DECISIONS ADR-017, README troubleshooting. They also note that GitHub does not let a pull request's author request changes: with `GH_PAT` as the reviewer's own account, Agent 2's pull requests are the reviewer's, so `/fix` is the route

Pinned by `tests/unit/test_agent2_review_fix.py` (32 tests; new: a regenerated story's modified files are editable, a feature holding another story's scenario or another owner's marker is not, a step file follows its feature, a comment on a regenerated feature is fixed and pushed).

---

## October 2026 (end) — Agent 2 fixes what a pull request's reviewer asks for

**Why:** no agent read a review comment. A reviewer who wanted one line changed on an Agent 2 pull request fixed it by hand - unchecked by the validators until Agent 4 ran - or added `ai-regenerate` and threw the whole pull request away.

- `agents/agent2_review_fix.py` and `.github/workflows/agent2_review_fix.yml`: a "Request changes" review on an `auto/*` pull request, or a `/fix` comment (`/fix <what to change>`, or a bare `/fix` for every inline comment not handled yet), from a person with write access - never a bot. One model call (`ReviewFixPlan`) decides fix / decline / no_change per comment; Stage 2's generator rewrites each named file in a new review mode (`generate_file_content(review_feedback=...)`: the current file shown whole, whatever its format); the repair loop and the final gate run over every code file of the pull request; the result is pushed to the same branch, so Agents 3, 4 and 5 run again. Each comment gets a reply in its thread and the pull request one `[agent2:review-fix]` summary, which also stops a second run on the same review
- Safeguards: only files the pull request added and page objects it extends (never another story's spliced files, reserved or framework files); a feature file keeps its scenarios, titles and markers; a comment asking to test something the approved test cases do not state is declined with the way to get it (update the test case, then `ai-regenerate`); a degraded regeneration is discarded; a gate failure, or a repair reaching a file that is not editable, pushes nothing; `review_fix.max_files` (6) caps one review
- `RepoHost` gains `get_review_comments` and `reply_to_review_comment` (19 operations; classified for dry runs); schemas `ReviewFixDecision`, `ReviewFixPlan` (24); config `agents.agent2_coder.review_fix`; prompt `prompts/agent2_review_triage.md`; ADR-017
- Docs: README, GUIDE (Agent 2, workflows, events, markers, config, troubleshooting), TECHNICAL_DEEP_DIVE, REUSE_FOR_NEW_PROJECT, VALIDATION_AND_KNOWN_GAPS (E18)

Pinned by `tests/unit/test_agent2_review_fix.py` (28 tests: every safeguard above, the workflow's guards, the generator's review mode, and a gate refusal that names each rule still broken).

---

## October 2026 (end) — the two gates agree on a quantity; a refused story stops retrying

**Why:** SCRUM-187's approved test case expected "a row for '<item>' with quantity 1" after signing in as the inventory's shared account. Agent 1's check let it through (it looked for "exactly", "only", a row count and "empty"); Agent 2's gate refuses an exact value read from a persistent page whenever the scenario signs in, because a run that stopped before cleaning up leaves the same entry behind and the next run reads 2. Four repair attempts failed on the same rule (about $2.50), nothing was written to Jira, and the scheduled scan retried the story every 30 minutes.

- `core/test_case_rules.py`: an exact quantity (`quantity 1`, `a quantity of 2`, `qty: 3`, `3 items`, `a total of 1500`) on a persistent page is rejected in a test case that signs in with a shared account - the inventory's `test_users`, named in the text or the test data. A test case that never signs in keeps its quantities (a fresh session starts empty), exactly where Agent 2's gate draws the line. Agent 1's normal and impact-aware drafts both apply it; without accounts the rule is off, as before
- `core/blocked.py`, Agent 2: when the final gate refuses a story, one `[agent2:blocked] inputs: <fingerprint>` comment lists the rules still broken and what to do. The scheduled scan's normal pass skips a story whose story and test-case text still match the fingerprint - no model call, `[BLOCK]` in the summary. Any edit to them retries on the next scan; a manual run with `story_key` always runs. `GateFailure` (a `ValueError`) carries the remaining errors
- `BasePage.click_in_row()` waits (default timeout) for a row with the text before calling it missing. It counted at once, so the first row action after a navigation - "View Cart", then delete a product's row - could read the page before its rows were drawn (this PR's own Agent 4 run, `test_cart_management`). A row that never appears still fails with the same message
- A failed E2E test names the temporary server errors its own requests met. This PR's next Agent 4 run failed two tests during a burst of HTTP 503: an add-to-cart call and a followed link were refused, and the steps after them failed with "row not found" and "element never appeared". Neither message named an HTTP error, and the re-run rule of #213 (`--only-rerun`) reads only the exception message, so neither was re-run. `pytest_runtest_call` in `tests/conftest.py` now restates a failure as `ApplicationUnavailableError` naming every 5xx/429 the test's action requests met and never recovered from (`BasePage` `unrecovered_server_errors()`, `with_server_errors()`); a request the server later answered (a retried page load) is not named. `core/failure_diagnosis.py` reads it as "application temporarily unavailable"
- Docs: GUIDE (troubleshooting, markers, failure recovery, Agent 4 steps), README troubleshooting, TECHNICAL_DEEP_DIVE §`core/blocked.py` and §7, VALIDATION_AND_KNOWN_GAPS (G11 closed, N4 narrowed, E16, L14 and F-7)

Pinned by `tests/unit/test_signed_in_quantity.py` (both gates on one sentence, signed in and anonymous), `tests/unit/test_blocked_story.py`, `tests/unit/test_click_in_row_waits.py` and `tests/unit/test_server_errors_are_named.py` (the re-run rule read from the workflow itself).

---

## October 2026 (end) — a temporary HTTP error from the application is retried (#213)

**Why:** from CI the application under test answered some requests with HTTP 503 in short bursts while it loaded fine in a browser. One run failed five of seventeen tests that way - four page loads and one add-to-cart request - none for anything the change did (L14).

- `BasePage.navigate()` retries a page load the server answered with a 5xx or 429, after the waits in `browser.navigation_retry_delays_ms` (config, default 3 s then 8 s; `[]` turns it off). A 4xx fails at once, as before; the final message names the attempts
- Agent 4 re-runs a BDD test whose failure names a 5xx or 429 - which covers an action's own request - up to twice, 20 s apart (`pytest-rerunfailures`, pinned; `--only-rerun`). An assertion, a 404 or a timeout is never re-run
- `scripts/collapse_junit_reruns.py` (Agent 4 step, always runs, never fails) keeps only each test's final attempt in `junit.xml`, so Agent 5's counts and Agent 3's per-scenario evidence see one result per test
- Docs: README and GUIDE troubleshooting, GUIDE Agent 4 and config, TECHNICAL_DEEP_DIVE §7, AI_CONCEPTS (#51), VALIDATION_AND_KNOWN_GAPS (L14 partly fixed, F-7 and L22 updated, E15)

Pinned by `tests/unit/test_outage_retry.py` (library application; 7 break-it proofs) and the updated `test_navigation_guard.py`.

---

## October 2026 (end) — Agent 3 judges a prediction on its own scenario (#212)

**Why:** PR #211 (SCRUM-206) stayed blocked on a finding that the add-from-card click would hit two controls in one card. That scenario passed on the commit; the run was red only because another test hit an HTTP 503 from the site - and a change story's PR is red by design before deployment. The helper the finding was about (`click_in_row`) documents that it clicks the visible copy, but the reviewer never saw its docstring.

- A red runner result now refutes each prediction whose own scenario passed: Agent 3 reads the run's `junit.xml` (artifact `pytest-report-<run id>`) and maps the finding to its scenario - the new optional `scenario` field on `ReviewIssue`, or a scenario quoted in its failure scenario. A green run refutes every prediction, as before. No scenario, no match, an unreadable report: the whole run decides, exactly as before. Security and "passes wrongly" findings are never refuted by a pass
- An outline's prediction is refuted only when every example passed
- `RepoHost.get_run_artifact_file()` (17 operations): one file from an artifact a run uploaded; `get_workflow_runs()` dicts carry the run `id`. Classified as a read for dry runs; GitHub adapter fails soft
- Agent 3's prompt lists every BasePage helper the PR's added page-object lines call, with its signature and docstring; a finding about a helper's behaviour must agree with it
- Docs: README, GUIDE, TECHNICAL_DEEP_DIVE (Agent 3, §9.6 adapter table, §9.7 schema table - 22 classes, missed in #209), REUSE, AI_CONCEPTS (#16 updated, #50 new; duplicate #48 from #209 renumbered to #49), ADR-016, VALIDATION_AND_KNOWN_GAPS (E14, G10 closed)

Pinned by `tests/unit/test_review_scenario_evidence.py` (library application; replay of the PR #211 shape; 7 break-it proofs).

---

## October 2026 (end) — every acceptance criterion verified by a test that can fail (#209)

**Why:** validation story SCRUM-206 removed a field; the revised tests stopped using it, nothing asserted it was gone, and every test passed against an application that still had the field (ADR-015).

**Agent 1 (both modes)**
- The acceptance criteria are read from the story text (`core/acceptance_coverage.py`: numbered, bulleted, checklist or Given/When/Then lists under an "Acceptance criteria" heading, wiki markup or markdown) and listed in the prompt as AC1, AC2, ...
- The draft returns a coverage map (`CriterionCoverage`, schema 22): every criterion with the test case(s) that verify it. A missing criterion or an unknown citation sends the draft back once; a second miss writes nothing
- Obligations, from the criterion's wording: removed / replaced / renamed / hidden / "no longer" / "no X is shown" needs a step asserting the old thing is absent, naming it; only X can / Y cannot needs the refusal; a limit or validation rule (at most N, required, valid format) needs the violation rejected
- Impact-aware: a revision counts only if it carries that step; an unchanged existing scenario may be cited for a criterion without an obligation (no duplicate drafted)
- The map is posted on the story (`[agent1:coverage]`) and in the impact-aware gate comment; both prompts carry the obligation table, now with a limit/rule row

**Agent 2**
- Three checks (`validators/absence_claims.py`, gate now 32 checks): a scenario keeps its test case's "is not shown" step; a Then step worded as absence asserts absence (a page-object method that answers absence counts, whatever its name); a new or changed absence predicate on a permanent element proves its page is loaded first (`return self.is_loaded() and self.is_gone(...)`). Committed code is not re-judged
- The single-scenario writer (`ai-update`, change-story splice) is told the test case's absence claims and retries once if it drops one
- Generation prompt: the feature-file rule, a section on proving something was removed, and rule 17 / the absence rule extended for permanent elements

**Docs:** README, GUIDE, TECHNICAL_DEEP_DIVE §4/§14/§19, AI_CONCEPTS (#49), REUSE, ADR-015, VALIDATION_AND_KNOWN_GAPS (E11–E13, UC-6, L24, L18/F-11 amended: keep and mark a removed element instead of deleting it).

All generic, pinned by `tests/unit/test_acceptance_coverage.py` and `tests/unit/test_absence_claims.py` (written for a library application; every guard has a break-it proof). Suite: ~3,080 tests.

---

## October 2026 (second half) — validation fixes after A3

**Agent 0's manual-run inputs mean what they say**
- "Print the report; write nothing" now reaches every job: the full scan (analysis and hand-over), reconcile and drift. The real code runs against tracker and repo-host wrappers that perform no writes and print each one (`core/dry_run.py`; reads are allow-listed, so a new operation is intercepted until classified). Before, a full-scan dry run handed reviews over for real and reconcile always ran live
- A `story_key` scopes reconcile to that story too (it settled every `impact-applied` story)
- `mode` = `drift` with a `story_key` stops with an error instead of ignoring the key
- Inputs reach the reconcile shell as environment variables, not pasted into the script

**Test-lifecycle gaps recorded**
- `docs/VALIDATION_AND_KNOWN_GAPS.md` sections 3.5–3.9 and fixes F-8 to F-20: notes never gain shipped knowledge (L15), size, scope and cleanup of the notes (L16–L18), tests before deployment (L19), an approved test case silently not automated (G5), requirement or test-case edits after coding go unnoticed (G6, G7), a rejected new-story PR leaves the story looking coded (G8), and deployment, suite size, flakes and bug stories (L20–L23); operating the pipeline continuously (N1–N9, fixes F-21 to F-29): no scheduled app-test run on `main`, no failure-to-defect triage, no alert on failing schedules or expiring credentials, no spend budget, stale agent PRs, merging a red PR, shared test data, one environment and browser, no health metrics

**One file for validation and known gaps**
- `docs/VALIDATION_AND_KNOWN_GAPS.md`: what has been validated live, the clubbed validation runs still to do (A4–A6, B, C, held-out stories, the new behaviour from #199–#201), and every known gap (stories in flight, several stories per scan, Agent 0, generation) with its status and planned fix

**Documentation audit (completeness, not only truth)**
- Model calls per story are stated for a change story as well as a new one (README, GUIDE): Agent 0's context update, Agent 2's per-scenario splices and Agent 3's review of the context-update PR were missing from every count
- Docs describe the stories-in-flight guards, the pull-request browser gate and Agent 0 on the cost ledger everywhere they apply (README, GUIDE, TECHNICAL_DEEP_DIVE, AI_CONCEPTS, REUSE_FOR_NEW_PROJECT); "stories are independent, no shared state" corrected, with the open multi-story gaps listed
- TECHNICAL_DEEP_DIVE no longer carries source line numbers or file sizes, which went stale with every pull request; every function is named with its file
- New ADR-014 (stories in flight)

**Stories in flight at the same time**
- Agent 2 never writes a file another open pull request is changing, and never generates a scenario another open PR already adds: the story waits (`waiting_for_open_pr`, `[WAIT]` in the scan summary), labels unchanged, one `[agent2:waiting]` comment per reason, retried on the next scan. Covers normal, regenerate, change-story owner files and `ai-update`. Fails open (`core/in_flight.py`)
- Duplicate detection compares a test case's title without its `[type]` tag (the stored summary is `[Positive] <title>`, the scenario is `<title>`, so the title fallback could never match a case the pipeline created)
- Agent 4's browser runs take turns across pull requests (first come, first served, bounded at 15 minutes, fail-open; `scripts/e2e_turn.py`): every PR tests the same live application with the same accounts

**A-series open items (closed)**
- `reconcile.closed_scans` is honoured: an undo happens after that many scans see the same close (default 2, as before; 1 = immediately)
- `config.yaml`'s `context_update` comment describes both wording changes and note rewrites
- The golden-rule test scans every `prompts/agent*.md` (a glob, so new prompts are covered); `agent0_*.md` and `agent1_impact_aware.md` were missed
- Agent 0's model cost is posted to the story ledger; Agent 1 no longer treats Agent 0's entries as a previous run, and a genuine new attempt still resets
- The drift job can be run on demand (`Run workflow`, `mode` = `drift`)
- Test cases carry their story's Jira Components; a project that rejects them still gets the test case
- A pull request that changes only `prompts/`, `docs/` or Markdown (e.g. a notes-only context update) runs the unit suite but no browser, and posts no Jira report; any other file runs the E2E, and the check fails open. Agent 3 does not read that unit-only green as evidence against a predicted failure. One rule for both: `core/test_runtime.py`

All generic, each pinned by unit tests (suite: ~2,900 tests).

**Agent 0**
- #175 a change story undone by reconcile can be retried as a new attempt; docs no longer claimed Agent 0 posts a cost ledger (it did not then; it does since the A-series items above)
- #185 a context-update marker blocks a new proposal only while its PR is open; a closed PR no longer suppresses the retry's update
- #186 *using is not changing*: a story classified `new_behaviour` (new functionality, or a new journey through existing behaviour) keeps no seeds, and adjudication needs a named difference, not overlap

**Agent 1**
- #185 the story wins over the app notes where they disagree
- #187 → #188 "no row / zero rows" is judged by the entry it names (quoted or test-data value): absence of a named entry is relative, not a row count. #188 replaces #187's word list

**Agent 2**
- #181, #182 orphan step clean-up, Agent 4 visibility of failures, and an absence predicate every gate accepts
- #185 `click_in_row` clicks the visible copy when a row holds two of one control
- #190 new validator `validate_reused_steps_keep_their_meaning` (29 checks): a Then step re-defined for another feature may not assert more than the committed definition; a bare `# JIRA: KEY` marker is completed in place
- #193 every repairable error reaches the repair loop, whatever its wording (`_route_to_generated_file`); the step-definition prompt shows the committed body of every Then step the feature reuses (`committed_then_definitions`)

**Step definitions (supersedes the two Phase 2 entries below)**
- Generated step-definition modules are self-contained: each declares every step its own feature uses. `tests/step_defs/conftest.py` holds fixtures only (page-object fixtures registered automatically, `credentials` by login role from `APP_USER_<ROLE>` / `APP_PASSWORD_<ROLE>`). The duplicate-step check is same-file. Details: ADR-012's 2026-10 note in [DECISIONS.md](./docs/DECISIONS.md)

**CI**
- #192 Actions storage kept inside the quota: `artifact_cleanup.yml` (daily, deletes artifacts older than 2 days, `scripts/cleanup_artifacts.py`); Agent 4 uploads only what Agent 5 needs, kept 3 days

- `ai-update` comments out step functions a removed or modified scenario left unused (`comment_out_step_defs_unused_by()`, as the change-story splice does), so the unused-step gate no longer fails the run; the PR body lists them instead of claiming they were "removed by regeneration"
- The step-coverage check counts only the paired module and applicable `conftest.py` files; a sibling module generated in the same batch no longer counts (runtime cannot see it). Closes ADR-012's follow-up

**Docs**
- #197 README and docs brought in line with `main` after #193
- Line-by-line audit of `docs/` against `main` (`3289394`): the change-story selector wording rule (wording changes may update a selector; note rewrites never do), self-contained step files, login roles, the `main` rulesets, Agent 5 posting a new report on every re-run, `ai-update`'s step-definition splice, current line numbers and counts

---

## October 2026 — Agent 0 (impact analysis) and the change-story pipeline

A sixth agent, Agent 0 (Impact Analyst), runs before Agent 1 for a story that
changes behaviour existing tests rely on. Design record: [ADR-013](./docs/DECISIONS.md);
operator guide: [GUIDE.md → Change stories — Agent 0](./docs/GUIDE.md#change-stories--agent-0).

**Agent 0, built in phases (all PRs merged 10–12 Oct):**
- #126 Phase A — foundations; #127 Phase B — impact graph and marker backfill (`scripts/backfill_markers.py`)
- #130 Phase C — hand-over pipeline: Impact Review, hand-over, Agent 1 impact-aware mode, Agent 2 owner splice, reconcile
- #131 Phase D — Agent 0 itself (seeds, candidates, adjudication, ranking, publish), switched off by default; #132 design-audit fixes
- #134–#139 Phase E — uncovered live elements (`--compare`, inventory proposals), onboarding kit for applications outside this repository (`scripts/onboarding_check.py`, `docs/AGENT0_ONBOARDING.md`), generality audit
- #159 shadow mode on; #163 live mode for a single-story trial
- #164 Impact Review reads decisions from linked keys and refuses an unreadable review; #165 scenarios without a test case are shown
- #166 context-update PR: the wording a story replaces, proposed for the inventory and app notes

**Validation series A1–A3 (real change stories) — generic fixes:**
- #169 Agent 2 splice writers get the same grounding as the full-file writers, plus one corrected retry; `test_splice_grounding.py` fails any ungrounded model writer
- #171 the orphan cleanup's file is committed even when the splice adds no step function
- #172 `core/json_block.py` reads stored review data however Jira re-stores an edited code block
- #173 the model's verdict caps the tier; short evidence per row; a re-analysis that changes nothing says so; the context update also rewrites passages a story makes untrue (`NoteRewrites`); a revision repeating an existing scenario is flagged; new validator `validate_absence_not_asserted_with_waiting_probe` (28 checks); scenario marker placed below the tags; after an undo, reconcile retires the story's unshipped tests, resets its pipeline labels (`reconcile.reset_labels`), moves the card to To Do (`status_workflow.on_label.impact-reverted`) and posts the retry steps

**Rest of the pipeline in the same period:**
- #140 committed page objects are extended automatically and keep their methods (`validate_extended_page_objects_keep_methods`)
- #141 Agent 1 named "Test Designer" (distinct from Agent 0, the Impact Analyst)
- #142 Agent 1 checks drafted test cases (`core/test_case_rules.py`) before writing them; #160 its run summary handles every outcome
- #143 every validator error is routed to the repair loop; #144, #146 new validator rules
- #149–#152, #162 Agent 3 blocks only for a named failure in lines the PR changed, checks a predicted failure against Agent 4 on the same commit, and is always the reviewer on `main`
- #153 golden-rule guard: application names harvested from the inventory and page objects may not appear in framework files
- #155 Agent 5 scopes the report to the story's own tests and renders Jira markup; #158 the PR title names the story

**Docs:** README, GUIDE, TECHNICAL_DEEP_DIVE, AI_CONCEPTS, REUSE_FOR_NEW_PROJECT and AGENT0_ONBOARDING brought up to date with six agents; ADR-013 added.

---

## Phase 2 — Shared step definitions moved to `tests/step_defs/conftest.py` (superseded)

> Superseded in October 2026: step-definition modules are now self-contained and `conftest.py` holds fixtures only. See the top entry and ADR-012's note.

Fixes a runtime failure that every validator passed. Agent 2 generated a feature
reusing `Given I am on the SauceDemo login page` (defined in the reference module
`tests/step_defs/test_login.py`); Agent 4 failed at collection with
`StepDefinitionNotFoundError`.

**Root cause.** pytest-bdd implements step definitions as pytest **fixtures**,
which are **module-scoped**. A step defined in one step-def module is invisible
to every other module. The step-coverage validator had assumed the opposite
("registers the step globally... no conftest required") and so green-lit code
that cannot run — the PR #9 class of defect. Verified empirically: sibling module
-> `StepDefinitionNotFoundError`; same step in `conftest.py` -> passes.

- **NEW `tests/step_defs/conftest.py`** — shared page-object fixtures
  (`login_page`, `inventory_page`) and the five shared step definitions. This is
  pytest's only supported cross-module sharing mechanism. Located under
  `step_defs/` (not `tests/`) because both validators discover on-disk steps with
  `tests/step_defs/*.py`; shared steps in `tests/conftest.py` would run but be
  invisible to the validator.
- **`tests/step_defs/test_login.py`** — shared steps MOVED out (not copied: both
  validator globs include `conftest.py`, so duplicates would trip the
  duplicate-step guard). Retains two feature-specific steps so the reference
  still demonstrates step authoring, plus a docstring stating the rule: *needed
  by more than one feature -> conftest; specific to one feature -> paired module.*
- **`features/login.feature`** — new 4th scenario (error dismissal) exercising
  those local steps via existing `LoginPage.dismiss_error()` /
  `get_error_message()`. No page-object change required.
- **All quoted-value decorators now use `parsers.re` with `[^"]*`** — the `parse`
  library cannot match empty quoted values, which validation scenarios rely on.
  Each pattern is kept on ONE line: the validator reads first-quote to
  last-quote, so multi-line implicit concatenation corrupts the pattern and every
  step using it stops matching.
- Docs: REUSE_FOR_NEW_PROJECT.md gains **Change 5** (mandatory for every new
  app); DECISIONS.md gains **ADR-012**.
- Suite: **270 passing**, unchanged.

**Open follow-up (closed October 2026):** the step-coverage validator treated decorators in
sibling step-def files as available. It now counts only `conftest.py` plus the paired module.


## Phase 2 — Tier 3 follow-up: complex-locator support in the inventory tooling

Extends `inventory_tools/` to handle the controls real-world apps use, still
fully app-agnostic. Suite 259 -> **267 passing** (+8). No agent/config/workflow
change.

- **Custom widgets via ARIA role / tabindex / contenteditable / stable id.** The
  collector no longer captures only native `input/button/select/textarea/a` +
  test-id elements — it now also captures div/span-based widgets that carry an
  interactive role (`combobox`, `listbox`, `switch`, `slider`, `menuitem`, …), a
  `tabindex >= 0`, `contenteditable`, or a **non-generated `id`** (catches
  drag-drop targets like `#draggable`). These get a churn-proof Playwright role
  locator (`role=combobox[name='Country']`, or a nameless `role=slider` when a
  widget has no accessible name) instead of brittle css, and `element_kind`
  names them sensibly (combobox → dropdown, switch → toggle, …).
- **iframe traversal.** `collect_descriptors` now walks every child frame and
  tags each element with its frame-chain selector, emitted with a ` >>> `
  convention: `iframe#pay >>> [data-test='card']` → 
  `page.frame_locator('iframe#pay').locator("[data-test='card']")`. Nested frames
  chain. The staleness checker resolves these via `frame_locator`, and framed
  test-ids are no longer false-flagged as drift.
- **Open shadow DOM.** The collect/test-id JS recurses into open `shadowRoot`s, so
  web-component controls are captured (closed roots remain inaccessible by
  design). role=/css locators pierce open shadow DOM automatically at runtime.
- **Unstable-selector flag.** Any element whose only handle is a fragile css
  fallback (no test-id, role, label, or text) is listed under a page's
  `_unstable_selectors` with guidance to add a `data-test` — drift risks are now
  visible instead of silently shipped as brittle css.

What still needs a human: un-accessible custom controls (a plain `<div onClick>`
with no role/tabindex/id/test-id can't be detected from the DOM), per-row/per-cell
list & table handling (capture the container + a parametrized locator by hand),
and any element the app gives no stable hook — the real fix there is adding a
`data-test` in the app, which no crawler can manufacture. Validated in a real
Chromium against the full control spectrum of a known practice page (native
inputs, radios, checkboxes, single/multi selects, file inputs, jQuery-UI
datepickers & slider, autocomplete, drag-drop, a custom combobox, an iframe, and
an open-shadow-DOM section) — all captured; only data-table rows and the app's
un-hooked elements remained (as expected).

## Phase 2 — Tier 3 follow-up: inventory tooling made fully app-agnostic

The 3.1 inventory tools shipped working but carried a few SauceDemo-shaped
defaults. This pass removes them so the tools are genuinely reusable across
applications. Additive/refactor only — no agent, config, or workflow code
changed. Suite 254 -> **259 passing** (+5 app-agnostic tests).

- **Configurable test-id attributes.** The attribute allowlist (was hardcoded to
  `data-test`/`data-testid`/`data-qa`) is now a `TEST_ID_ATTRS` constant with a
  broad default (`data-test, data-testid, data-test-id, data-qa, data-cy,
  data-automation-id, data-tid`), threaded through selector ranking, element
  naming, family-collapsing, drift detection, and the browser collect JS, and
  overridable per run with `--test-attrs`. Family-collapse now preserves whichever
  attribute the app actually uses (e.g. `[data-cy^='buy-item-']`).
- **Generic login.** Replaced the `username_input`/`password_input`/`login_button`
  + page-key `"login"` assumption with type-based field auto-detection
  (`input[type=password]`, etc.) and explicit `--login-url` /
  `--username-selector` / `--password-selector` / `--submit-selector` overrides.
- **Scrubbed docstrings.** No `SauceDemo` / `standard_user` / `secret_sauce` in
  any generic file; examples use neutral placeholders. Audited: zero app-specific
  keywords remain in `inventory_tools/` or the inventory scripts.
- New tests prove the full generate→staleness pipeline on a `data-cy` app with
  zero SauceDemo assumptions.

## Phase 2 — Tier 3 (3.1 inventory tooling, 3.4 sweeper) + page-level errors

All additive — new packages, scripts, one workflow, and data. No existing agent
code or workflow changed. Suite 218 -> **254 passing** (+36).

### Inventory generation + staleness checker (backlog 3.1)
New `inventory_tools/` package with browser-free, unit-tested logic
(`introspect.py`: selector ranking, element naming, repeated-family collapsing,
draft page assembly, staleness diff) and a thin Playwright layer (`browser.py`).
Two CLIs: `scripts/generate_inventory.py` crawls the live app and emits a DRAFT
inventory (machine-fillable fields populated; `elements_notes` / `key_methods` /
`errors` / `components` left as visible stubs — a machine can't infer behaviour,
intended API, or exact error strings), and `scripts/check_inventory_staleness.py`
diffs the committed inventory against the live DOM, reporting stale selectors
(the dangerous kind), untracked live data-tests, and unreachable pages, warning
on pages with no `elements_notes`, and exiting non-zero under `--fail-on-drift`
for CI gating. 22 tests in `test_inventory_introspect.py`. Requires
`playwright install chromium` to run live.

### Sweeper — stalled-PR backstop (backlog 3.4)
`.github/workflows/sweeper.yml` (hourly cron + dispatch) runs
`scripts/sweep_stalled_prs.py`. Cron agents (1/2) self-heal; event-driven agents
(3 review, 4/5 run+report) don't — a cancelled or missing `pull_request` run
strands a PR. The sweeper finds open `auto/*` PRs whose Agent-3 or Agent-4
workflow has no settled run (success/failure/timed_out) for the current commit
and reopens them to re-fire the event chain. It reuses Agent 2's `GH_PAT`
deliberately: the built-in GITHUB_TOKEN does not re-fire workflows, and Agent 5's
report job is gated on `pull_request`, so a workflow_dispatch re-run would skip
the report — reopening re-runs the whole chain. Loop-safe: a real pass/fail is
left alone, and each nudge drops a commit-SHA marker comment so a PR is nudged at
most once per commit. 14 tests in `test_sweeper.py`.

### Page-level errors (schema)
`app_inventory/saucedemo.json` — page-specific error strings moved from the flat
top-level `common_errors` into each page's new `errors` field (login errors ->
login, checkout errors -> checkout_step_one). This keeps messages next to the
screen that raises them and lets them ride the 2.2 component filter (a Login
story injects only login errors). Backward compatible: nothing parses errors;
`common_errors` is retained for genuinely cross-cutting errors. No code change.

## Phase 2 — Tier 2 (batch 2: 2.2 / 2.3 / 2.4)

Three enhancements, each backward-compatible and each with a safe fallback. Suite
grew 170 -> **218 passing** (+48 tests across three new files).

### Component-wise inventory filtering (backlog 2.2)
`agents/app_context.py` gains `filter_inventory_by_components()` and a
component-aware `load_page_inventory_json(components=None)`. When a story's Jira
Components are passed, only the inventory pages tagged with those components are
injected, plus any page flagged `"always": true` (shared pages such as the menu) —
mirroring the module-wise app-context selection (2.1). Matching is
case/space/hyphen-insensitive; the internal `components` / `always` /
`_inventory_conventions` tagging keys are stripped from the string sent to the LLM.
**Safe defaults:** a no-argument call is byte-identical to before, and a story with
no components — or a component that matches no page — gets the full inventory
(context is never silently dropped).

Wired at Agent 2's two entrypoints (`run` and `run_update`), which already fetch
the story and account for ~92% of input tokens. Agent 3 keeps the full inventory
so a review never false-flags a filtered-out selector.

`app_inventory/saucedemo.json` was completed from login-only to all eight SauceDemo
modules (login, inventory, inventory_item, cart, checkout_step_one/two/complete,
and the shared menu), each tagged with its Jira Component. A Login story now injects
~56% fewer inventory characters. New `tests/unit/test_inventory_filtering.py` (18).

### Error-type-aware repair prompts (backlog 2.3)
`agents/agent2_coder.py` — the repair loop used to answer every validator failure
with the same "add your @given/@when/@then decorator" instruction. It now classifies
each error by its validator prefix (import resolution, method resolution, duplicate
step-def, filename consistency, Gherkin structure, step coverage) and emits a hint
targeted at that class, de-duplicated and in a fixed order, via
`_classify_error()` / `_build_error_type_guidance()`. An import error is no longer
told to add a step decorator. New `tests/unit/test_repair_error_types.py` (14).

### Update-mode step-def splicing (backlog 2.4)
`agents/agent2_coder.py` — ai-update already spliced the feature file
scenario-by-scenario but fully regenerated the step-def file every time.
`_splice_step_defs_incremental()` now works in tiers: **unchanged** (existing file
already covers the spliced feature — kept as-is, zero LLM calls), **spliced** (only
the genuinely new step functions are generated and appended, passing functions
untouched), or **regenerated** (Tier-C fallback to the previous whole-file
regeneration on any ambiguity — no file on main, unparseable, LLM returned nothing
usable, still-uncovered after splice, or a duplicate-step collision). Post-splice
re-validation plus the fallback mean a splice can never ship broken step defs.
The step-def `GeneratedFile` purpose records which mode ran. New
`tests/unit/test_step_def_splicing.py` (16).

## Phase 2 — Tier 2 (app-context token savings)

Both changes are backward-compatible; the SauceDemo app now ships in the module
layout as a worked example.

### Inventory minification (backlog 2.6)
`agents/app_context.py` — `load_page_inventory_json()` minifies the inventory JSON
at injection time (file on disk stays readable; only the prompt string is compacted).
~15% on the SauceDemo inventory, more as inventories grow, zero information loss.
Malformed JSON falls back to raw text with a warning (pre-2.6 behaviour); a missing
file still raises FileNotFoundError.

### Module-wise app context (backlog 2.1)
`agents/agent1_analyst.py` `load_app_context_block()` is now module-aware and
`agents/jira_client.py` `get_story()` returns the story's Jira Components (additive).
If `prompts/app_context/` exists, Agent 1 injects `core.md` (always) + one
`<component>.md` per Jira Component; otherwise the single `prompts/app_context.md`
is used exactly as before. Matching is case/separator-insensitive; a story with no
components (or an unknown one) safely gets all modules.

SauceDemo's `app_context.md` is split into `prompts/app_context/`: `core.md` +
`login.md` / `inventory.md` / `cart.md` / `checkout.md`. A Login story now injects
~49% fewer context tokens than the single file. Tag stories with their Jira
Component to realise the saving; untagged stories are unaffected (safe default).

New `tests/unit/test_app_context_modules.py` — 19 tests (module selection, all safe
defaults, minify round-trip / malformed-fallback / missing-file). Suite: 151 → **170**.

---

## Phase 2 — Cross-file duplicate step-definition guard (SCRUM-54 lesson) (superseded)

> Superseded in October 2026: the duplicate-step check is now same-file, because self-contained modules each resolve their own copy of a step. See the top entry and ADR-012's note.

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