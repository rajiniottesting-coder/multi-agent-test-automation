# Backlog

Everything still to build, in one place, agreed with the owner on 12 Nov 2026
after the live validation (271 checks, 254 proven). Accepted behaviour that is
*not* planned to change is in [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

**Rules**
- An item is built in a pull request with its unit tests, and adds its live
  check rows to [TEST_TRACK.md](./TEST_TRACK.md) (*Built in* names the item ID).
- Status: *Open* -> *Done (#PR)* when merged; the item stays here until its
  live check passes, then it is removed (the PR keeps the history).
- *Was* gives the older gap or fix ID (L-, N-, G-, F-) that code comments and
  earlier pull requests use.
- Cost group (model spend to build and prove it): **A** no model at runtime
  (PR reviews and one light run), **B** light agent runs (Agents 0, 1, 5),
  **C** code generation by Agent 2.

## Readiness

Ready for a pilot on one ongoing project: a web application tested through the
browser, with Jira and GitHub and one environment. The P1 items below come
before a real project; P2 and P3 before a wider rollout.

## Items

### Reporting and metrics

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| RP5 | AI metrics: cost per story and agent, first-attempt success of generated code, refusals, review findings, Agent 0 precision and recall | Posted per story, never aggregated | P2 | B | N9, F-29 | Open |
| RP6 | Management PDF (ReportLab) after the nightly run and at sprint end: totals, pass %, trend chart, open defects by severity, risks | None | P2 | A | | Done (#464) |
| RP8 | Allure severity (from smoke / critical tags) and links to the story and test case (from the `# JIRA:` marker) | Allure's severity and requirement views are empty | P2 | A | | Done (#464) |
| RP11 | A *Latest run* page (the site's landing page): what failed, flaked or could not be judged in the newest run, with its error, story and test case; the dashboard becomes *History* | The latest run was one line on the dashboard | P2 | A | | Done (#465) |
| RP12 | Defect trend (opened, closed, open per day), time to close, density per module and per sprint on *History* and the PDF | Open defects by age only | P2 | A | | Done (#478) |

### Security

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| S1 | Block `subprocess`, `os.environ`, `socket` and network calls in generated test code (an import and call deny list in the validators) | Story text is untrusted; a PR's tests run before a person reviews them, with the app login available; the import validator allows every standard-library module | P1 | C | | Open |

### Defects

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| D1 | Before raising, look for open Bugs from any reporter linked to the test or story; link and comment instead of raising | Only `ai-defect` Bugs are read, so a tester's Bug for the same failure gets a duplicate | P1 | B | | Open |
| D2 | When a person's Bug is resolved, re-run its linked tests and comment pass or fail | Nothing re-tests a fixed Bug | P2 | B | | Open |
| D3 | Bug flow: a production bug gets a regression test | Only Stories start Agents 1 and 2 | P2 | C | L23, F-20 | Open |
| D4 | A recurring failure's new defect links the closed one | New defect, unlinked | P2 | B | L37 | Open |
| D5 | AI defects carry priority (story priority or smoke tag), environment and commit | None set | P2 | B | | Open |
| D6 | A `raise-defect` label on a PR files a real application bug a new test found | A PR's failures go to its story only (by design) | P3 | B | | Open |
| D7 | Defect history on the results store (`defects.json`, `sprints/`): every defect's last known state, reopenings, deletions kept | The reports read open defects only, live; a closed or deleted defect left no trace (13 Nov 2026: 24 deleted) | P1 | A | | Done (#478) |
| D8 | A defect's module: tracker component, else `reporting.modules` over its feature file | The project has no components; no defect had a module | P2 | A | | Done (#478) |
| D9 | A closed defect's category (app, test, environment, duplicate, not-a-bug) from a close label or the resolution; the density counts product defects | Test fixes would count as product defects | P2 | A | | Done (#478) |
| D10 | Delete only closed issues labelled `test-data` | Any closed issue could be deleted, real defects included | P1 | A | | Done (#478) |

### Requirements lifecycle

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| R1 | Readiness check: a story without acceptance criteria gets one comment to the product owner and no draft | Agent 1 drafts anyway | P1 | B | | Open |
| R2 | A story edited after drafting or coding is noticed: Agent 1 records a hash of the story text; edited before coding -> suggest a re-draft, after coding -> suggest `impact-check` (a comment, never automatic) | Not noticed | P2 | B | G6, F-14 | Open |
| R3 | A test case edited or deleted in Jira is noticed: a scheduled comparison of each scenario marker's hash with its test case comments on the owning story suggesting `ai-update` | Only a manual `ai-update` compares them | P2 | B | G7, F-15 | Open |
| R4 | A deleted or cancelled story retires its test cases and flags its scenarios and defects | They stay orphaned | P1 | B | | Open |
| R5 | Only an allowed role or group can approve (`human-approved`) | Anyone who can edit labels starts coding | P1 | B | | Open |

### Execution and scale

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| X1 | A PR runs the tests Agent 0's graph links to the change plus a smoke set; the full suite nightly and before merge | The whole suite on every PR | P2 | B | L21, F-18 | Open |
| X2 | Per-run test data (accounts and fixtures seeded per run or worker), then parallel execution; browser turn-taking becomes optional | Shared accounts, one test at a time | P3 | C | N7, F-27 | Open |
| X3 | Environment profiles in config (base URL and credentials per environment) and an optional browser matrix in Agent 4 | One base URL, Chromium only | P3 | C | N8, F-28 | Open |
| X4 | An optional deployment signal (config or webhook) that marks a change story's failures as expected until deployment and reminds a person to merge its context-update PR | Pre-deployment failures look real | P3 | B | L20, F-17 | Open |
| X5 | Detect agent PRs that conflict with or fall behind `main`; comment with the cause and suggest `ai-update` or `ai-regenerate`; never force-push | The PR waits silently | P2 | B | N5, F-25 | Open |
| X6 | Require Agent 4's Run Tests check before merge, with X4's expected-failure marking so a change story is not blocked before deployment | A red PR can be merged | P3 | A | N6, F-26 | Open |

### Operations

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| X8 | Alert when a scheduled run does not start, or trigger the critical schedules from outside GitHub | 11-12 Nov: no scheduled Agent 1 run for 17 hours | P1 | A | | Done (#466) |
| X9 | Inventory Health probes the application and retries once; an unreachable application raises an app-unavailable alert instead of a red run | 12 Nov 10:03 UTC: red because the login form was slow; the re-run was green | P2 | A | | Done (#466) |

### Coverage

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| C1 | API, accessibility, visual and performance tests, chosen per project | UI tests only | P3 | C | | Open |
| C2 | Validator for snapshot-count and snapshot-membership assertions in signed-in tests | Not rejected by Agent 2's gate | P3 | A | L11, F-6 | Done (#468) |
| C3 | A fixed set of stories replayed when the prompts of Agents 1-3 change | No prompt regression set | P3 | C | L12 | Open |

### Live browser (Playwright CLI)

Our agents learn the application from the pre-built inventory, not by driving
a browser, which keeps a story at about $1.70. A live-browser step pays off in
two places; Playwright's CLI costs about a quarter of Playwright MCP's tokens
(about 27k against 114k per test in published benchmarks).

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| PW1 | Explore a page missing from the inventory live (Playwright CLI) and propose its inventory entry, instead of refusing the story | A story needing an unknown page is refused until a person adds the page | P2 | B | | Open |
| PW2 | Heal step before raising a defect: when a failure looks like a changed selector, check the live page (Playwright CLI) and propose the corrected selector in a PR | Raised as a defect, or found by the nightly inventory check | P2 | B | | Open |

### Rollout

| ID | Item | Today (gap) | Priority | Cost | Was | Status |
|---|---|---|---|---|---|---|
| P1 | Package the framework (a versioned package or submodule) separately from a project's content | Framework and the application's tests share one repository; a fix does not reach another project | P1 when more than one project uses it | A | | Open |
| P3 | Adapters for other trackers and repository hosts, when a project needs one | Jira and GitHub only (the adapter pattern is in place) | P3 | A | | Open |

## Estimated model spend to build and prove it

Built and proven live on 13 Nov 2026 (removed above; the pull requests keep
the history): RP1, RP2, RP3, RP4 (#464, #467), RP7, RP9, RP10 (#465), X7
(#468). The estimate below is the one of 12 Nov.

Added and built on 13 Nov 2026 at the owner's request (group A, no model
spend): D7, D8, D9, D10, RP12 (#478) - the defect history, trend and density.

At the pipeline's configured price ($5 per million input tokens, $25 per
million output; scale if the model's real price differs). Calibrated on 3-12
Nov 2026: $182 for about 105 fixes and 250 live checks; a clean story costs
about $1.70 end to end, an Agent 2 code run $1.10, a PR review $0.18.

| Group | Items | Range | Likely |
|---|---|---|---|
| A - no model at runtime | RP1-RP4, RP6-RP11, X6-X9, P1, P3, C2 (17) | $15-40 | $24 |
| B - light agent runs | R1-R5, D1, D2, D4-D6, X1, X4, X5, RP5, PW1, PW2 (16) | $30-85 | $50 |
| C - code generation | S1, D3, X2, X3, C1, C3 (6) | $64-118 | $88 |
| **Total** | **39 items** | **$109-243** | **about $162** |

C1 and C3 are the largest; without them about $62-158, likely about $97. The $100 daily budget
covers the work over 2-3 working days; keep the model key's own credit above
about $250.

## Suggested order

1. RP1 + RP2 + RP8 (results store, published Allure, severity and links); RP3-RP7 read RP1.
2. The P1 safety items: S1, D1, R1, R4, R5, X8 (and P1 before a second project).
3. RP3 + RP4 (dashboard, traceability matrix), then the P2 items, PW1 and PW2 with them.
