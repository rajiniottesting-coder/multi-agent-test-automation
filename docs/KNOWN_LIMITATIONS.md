# Known limitations

Accepted behaviour of the current design, written down so nobody relies on
more than the framework does. Each is a deliberate trade-off, not a bug; the
gaps still to be fixed are in [BACKLOG.md](./BACKLOG.md), and the live checks
still open are in [TEST_TRACK.md](./TEST_TRACK.md).

IDs (L-, M-) are stable: code comments, tests and older pull requests refer to
them. A limitation that a later change removes is deleted here in that change.

## Stories in flight at the same time

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L1 | Two stories change **different scenarios of one feature file** | The second waits: the guard works per file, not per scenario. Safe, sometimes slower | Limit |
| L2 | Two stories add the **same scenario with different wording** | Both are created: the in-flight check and duplicate detection compare titles | Limit |
| L3 | A person opens a pull request on a file **after** Agent 2's PR is open | Nothing stops a person; GitHub reports a merge conflict if the same lines change. Agent 0 lists affected tests on any PR touching `pages/` or `app_inventory/`. (One opened while Agent 2 is generating is caught by the last in-flight check, F-1: the story waits.) | Limit |
| L4 | A **semantic clash across different files** (PR A renames an inventory key PR B's new page method uses) | Not detected before merge: the guard compares files, not meaning. Agent 0's code-change comment on PR A covers tests already on `main`, not PR B's; B's tests fail after A merges | Limit |
| L5 | GitHub cannot be read when Agent 2 takes the snapshot | The story proceeds without the guard (fail open), as before #201 | Limit (by design) |
| L6 | A story that waits | Its plan call is spent - or, when the last check before the branch finds the clash (F-1), its generation calls too - recorded as `Agent 2 (Coder, waiting)`, and spent again on the retry | Limit |

## Several stories in one scan

| ID | Situation | What happens today | Status |
|---|---|---|---|
| M4 | More than about four PRs want the browser at once | The turn cap is 900 s; a run is about 4 minutes (median), so about four queued runs fit before later ones overlap again. Agent 3's wait (F-5) covers one turn plus one run | Limit (burst size documented) |

## Agent 0

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L7 | A scenario without a `# JIRA:` marker, or an inventory page without `components` | Agent 0 reports the scenario but has no test case to revise; a page without components widens layer 2 to the whole suite. Gaps are reported as unknown, never as unaffected | Limit (`scripts.backfill_markers`, onboarding check) |
| L8 | Seeds wider than the change (unchanged elements of the same page seeded) | Analysed after A2 and kept for recall; the model's verdict caps the tier, so it cannot promote a test | Limit |
| L9 | `uncovered_hint` | Off until a backtest with and without it is compared | Limit |
| L10 | Agent 3's review of a context-update PR | Its branch carries no story key, so the cost is not on the story's ledger, only in that run's log | Limit |

## Generation, tests and evaluation

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L49 | **The health check is only as good as its setting** | It checks the pages and elements in `app_under_test.health_check`. An application down in a way those pages do not show (one feature's back end) is not found down: its failures are retried and, failing twice, become defects. A framework change that breaks `BasePage.navigate` would make the check fail too and read as an outage - Agent 4's unit gate runs first and catches that; the outage alert names what the check saw, so a person can tell | Limit |
| L50 | **A rerun right after the first run** | The retry runs as soon as the application is found up, minutes after the first run; a failure caused by an application problem that lasts longer than the check's wait but looks up on its pages fails twice and is raised. The next night's pass flags it `passing` | Limit |
| L52 | **A defect traced through its feature file** | An unmarked scenario takes the one story every marked scenario of its file shares - right when a file belongs to one story, which is how Agent 2 writes them; a file shared by two stories traces no unmarked scenario (unmapped, alerted). A reserved file is traced only through `defects.trace_owners`, which a person keeps | Limit |
| L51 | **An HTTP error with no body** | Chromium refuses it on a page load (`net::ERR_HTTP_RESPONSE_CODE_FAILURE`) instead of returning the status, so `BasePage.navigate` cannot retry it as a 5xx and the failure is not read as an outage by its text. The health check still finds such an application down. Found by #242's tests | Limit |
| L41 | A real failure in a test whose own request also met an unrecovered 5xx/429 | Reported as an outage (not judged, no defect), the same rule that re-runs it (#215): the failure text is restated to name the 5xx. The next run, without the outage, shows the real failure | Limit |
| L12 | Prompt changes for Agents 1–3 | No dedicated prompt-regression eval set; the unit suite pins validators, Agent 4 runs the generated tests | Limit |
| L24 | An acceptance criterion that removes or restricts something without saying so in plain words ("the field goes away", "members lose renewals") | Every criterion must still be mapped to a test that verifies it, but the absence / refusal / rejection obligation is read from the wording (`obligation()` in `core/acceptance_coverage.py`), so such a criterion is checked only for being mapped. Writing criteria in the plain form ("no longer offers", "only X can", "at most N") makes them checked; the reviewer reads the `[agent1:coverage]` comment for the rest | Limit |

## Knowledge lifecycle: the app notes and the inventory

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L27 | A module over budget, or two modules repeating a fact | Reported (unit suite fails on size; the notes PR and the onboarding check list both), never condensed automatically: no model rewrites a whole module unreviewed | Limit |
| L28 | A change story's notes addition (at merge) while its context-update PR (from the hand-over) is still open | Both are built from `main` and may edit the same module, so the second to merge can conflict. Merge the context-update PR first (it is due after deployment, before the story's PR merges); otherwise close the notes PR and re-run Story Done on merge for the story | Limit |
| L29 | A key declared `removed` is still offered to Agent 2 | With its `removed` declaration and `REMOVED by` note in the payload, so the model sees it is gone; nothing else stops a new test from using it as if present - the reviewer and Agent 4's red run do | Limit |
| L32 | A **new page** nothing in the inventory points to | Since P1-4 the nightly PR lists same-origin pages the crawled pages link to that no inventory url matches, and crawls a page once a person adds its entry (or a `planned_page`); a page nothing links to is not found, and a listed one is not crawled until its entry exists | Limit |
| L26 | A stale key whose element the crawl now names **differently** (a renamed button) | The inventory-update PR replaces a selector only under the same generated name; a renamed element shows as an added key plus a removed or kept old key, and the person merging renames them | Limit |
| L33 | A **planned** element whose deployed selector differs from the design's | It never reads as live, so it stays `planned` (listed every night) and the tests using it stay red; a person corrects the selector in the inventory. Nothing compares a planned key with a similar live element | Limit |
| L34 | A **shared** element (header, footer) under ONE page's key | Since P1-4 it is no longer added again on every page; a page object of another page still cannot reach it (`sel()` reads its own page) until it is moved to a page declared `always` - a person's change | Limit |

## Traceability: every approved test case becomes a test

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L30 | A test case Agent 2 cannot automate is **reported, not automated** | Since F-13 it is named with its reason in the PR and on the story (`ai-incomplete`); generating it still needs its cause fixed by a person, then `ai-update`. The reason is only as good as the plan's `Skipped:` line - a test case the model drops without one is reported with "no reason given" | Limit |
| L31 | The coverage check proves a scenario **carries the test case's marker**, not that it tests what the test case says | Markers are placed by title pairing: greedy best match with a 0.3 similarity floor, and a lone scenario paired with the first test case unconditionally (existing behaviour). A scenario paired with the wrong test case counts as covering it, and the right one is reported as missing or not at all. Agent 3's review and E24 (b) are the check today; since #298 Agent 2's coverage audit names each expected result a scenario does not check (a model's judgement, advice to a person) | Limit |

## Running the suite over time

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L35 | A test that **flakes often** | Retried once, counted, listed on the health issue (F-19) - not quarantined: a person decides to fix or skip it | Limit |
| L37 | One open defect per test | A test failing under a new diagnosed cause updates its open defect, which lists the causes seen (#328; it used to raise a second defect). Only a closed defect makes the next failure a new one, and that new defect does not link the closed one. A defect is never closed by the pipeline, and only runs on `main` raise them (a PR's failures go to its story) | Limit |
| L42 | Three runs on `main` finishing close together | The triage jobs run one at a time (`defect-triage`); GitHub keeps one pending job per group, so the middle run's triage is replaced by the newest one's and its failures are triaged only if they fail again. Pushes to `main` are rare and the nightly run is one a day | Limit |
| L39 | Agent 3's wait for Agent 4 (turn + 480 s) | A run with a retry of up to 10 tests can finish after it: the prediction then keeps blocking (the safe side), and a re-run of the review reads the result | Limit |

## Operating the pipeline continuously

| ID | Situation | What happens today | Status |
|---|---|---|---|
| L36 | **The daily budget sees finished runs only** | Each run records its spend when it ends; a run reads the day's total at its first model call. Runs going on at the same time can pass the limit by what each spends; a run killed by its timeout records nothing. `scripts/smoke_test.py` and local runs (unless `PIPELINE_BUDGET=on`) are not counted | Limit |
| L38 | **The tracker's own credentials fail** | No alert can be posted on the tracker: the health check's run fails and GitHub notifies the workflow's owner - the one alert outside the health issue | Limit |
| L43 | **Two cost comments for one attempt** | The cost comment is posted by the attempt's first entry; two runs recording the first entries at the same moment both post one (the ledger keeps one reference). Both are correct; the one not referenced is no longer brought up to date | Limit (F-31; rare - an attempt starts with one agent) |
| L44 | **The comment ledger** (`usage_ledger.store: comments`, or a tracker without issue properties and comment editing) | The original behaviour: one `[LLM-USAGE]` comment per run, the table in every Agent 5 report, `[agent0:outcome]` as a comment, and a re-run of Agent 5 on the same commit reported again | Limit (by design: the fallback) |
| L45 | **A re-run with the same results is not reported** | Its run link is not on the story (the PR's checks show it); its flakes are recorded only when it is another run of the tests | Limit (F-31, D4) |
| L46 | **Agent 0's report on a change story keeps its table** | Only the data block moved to the Impact Review: the review shows no scenario titles and no tests left unjudged, so the story's table still repeats the review's key, owner, tier and score columns | Limit (F-31) |
| L47 | **The agents' GitHub App not set up yet** (`GH_APP_CLIENT_ID` empty) | The agents write with `GH_PAT`, as its owner, who cannot request changes on or approve their pull requests (N10's behaviour); every run's identity step warns | Limit (until the App is set up, GUIDE → Agent identity) |
| L48 | **A job longer than an hour** | An App's token lasts one hour, so a longer job would lose its later writes. Every agent job ends within 30 minutes; a test fails a job allowed more than 55 | Limit |
| L53 | **Removing another story's scenarios is flagged, not stopped** | Agent 2 can no longer produce such a PR (#314). Agent 3 lists every scenario of another story a pull request removes (#328) - advisory, not blocking, because a change story may retire one on purpose. Agent 0 still reports no affected test for a deleted scenario | Limit |
| L54 | **The coverage audit is the model's reading** | It can list a result a step checks indirectly (a section checked through its link); the note says to check the scenario first. It never blocks | Limit (#298, #312) |
