# Human-Approval Gate (Agent 1 → Agent 2)

> **Status:** Implemented
> **Files touched:** `config/config.yaml`, `agents/agent2_coder.py`,
> `.github/workflows/agent2_coder.yml`

## What this is

A human-in-the-loop checkpoint between Agent 1 (Analyst) and Agent 2
(Coder). Agent 1 proposes test cases as Jira issues; you review them on
Jira; only after you explicitly approve does Agent 2 generate code.

The gate is the architectural answer to "AI is fast but imperfect — how
do we keep humans in control of cost and quality without slowing the
system to a crawl?"

## End-to-end flow

```
[1] Parent Story (e.g., SCRUM-5 "Login functionality")
       label: ai-ready
              ↓
[2] Agent 1 reads it
       - Generates 5–8 manual test cases (Positive / Negative / Edge)
       - Creates linked Jira "Test Case" issues (SCRUM-7, 8, 9...)
       - Marks parent story:  label: ai-processed
              ↓
[3] HUMAN REVIEW  ← THE GATE
       - You open the parent story on Jira
       - Read each linked Test Case issue
       - Approve, edit descriptions, or reject (label: ai-skip)
       - When happy:        label: human-approved   (one click)
              ↓
[4] You click "Run workflow" on `Agent 2 - Coder` in GitHub Actions
       (OR scheduled trigger fires later — not yet implemented)
              ↓
[5] Agent 2 runs (in CI)
       - Selects: stories with ai-processed AND human-approved
                  AND NOT ai-coded AND NOT ai-skip
       - For each: reads linked Test Cases → generates Playwright code
       - Opens PR
       - Marks parent story:  label: ai-coded
              ↓
[6] Agents 3 (Reviewer) + 4 (Runner) + 5 (Reporter) cascade
       (already automated via `agent3-reviewer.yml` and `agent4_runner.yml`)
```

## Why this design

### Why a gate at all?

LLMs are non-deterministic and occasionally produce nonsense. The
question is *where* to put the human check, not *whether*.

Three places we considered:

| Gate position | Cost of a mistake caught here | Verdict |
|---|---|---|
| Before Agent 1 (review story before LLM sees it) | $0 | Misses LLM-specific errors |
| **Between Agent 1 and Agent 2** (review test cases) | **~$0.005 in tokens** | **Chosen — highest leverage** |
| Before merging the PR | ~$0.05 in tokens + reviewer time | Too late — code is already written |

The middle position catches LLM mistakes at the cheapest point — before
Agent 2 spends tokens generating code from a flawed test case.

### Why labels (and not Jira workflow status)?

Three options were considered:

- **Jira labels** — simple, visible, no Jira admin permissions needed
- **Jira workflow status transitions** — more formal, but Jira Cloud Free
  has limited workflow customization
- **Custom field** — requires schema changes; brittle in the free tier

Labels won on portability and simplicity. The pattern (`ai-ready`,
`ai-processed`, `ai-coded`, `ai-skip`, `human-approved`) is consistent
across all agents and visible in the Jira UI without clicking into the
issue.

### Why this completion label naming?

- `ai-ready` — human says: "this story is ready for AI processing"
- `ai-processed` — Agent 1 finished (test cases now exist on Jira)
- `human-approved` — human says: "I reviewed the test cases, ship the code"
- `ai-coded` — Agent 2 finished (PR exists on GitHub)
- `ai-skip` — human override: "stop, don't process this story"

Each label is owned by one writer and read by everyone. The state
machine progresses left-to-right and only moves when the right party
takes action.

### Why manual workflow trigger and not a schedule?

A schedule (e.g., every 15 minutes) would feel more "automated" but
introduces real risks:

- **Cost runaway:** A misplaced label fires expensive runs immediately
- **Unintended side effects:** Schedules fire in the middle of the
  night — when you can't react if something goes wrong
- **Harder to debug:** "Why did Agent 2 just open three random PRs?"
  vs. "I clicked Run because I wanted these three"

Manual trigger gives you the same automation benefit (Agent 2 in CI,
not on your laptop) without giving up control. A scheduled poll is a
safe future enhancement once the labels prove reliable.

## Configuration reference

In `config/config.yaml`:

```yaml
agents:
  agent2_coder:
    selection:
      issue_type: "Story"
      allowed_statuses:
        - "To Do"
        - "In Progress"
      required_labels:
        - "ai-processed"     # Agent 1 finished
        - "human-approved"   # You approved on Jira
      excluded_labels:
        - "ai-coded"         # Agent 2 already produced a PR
        - "ai-skip"          # human opt-out
    completion_label: "ai-coded"
    max_stories_per_run: 5   # cost-cap
```

To skip a story permanently, add the `ai-skip` label on Jira. Agent 2
will never pick it up again, even if `human-approved` is added later.

## Operating modes

Agent 2 supports three execution modes:

| Mode | Command | When to use |
|---|---|---|
| Single story | `python -m agents.agent2_coder --story SCRUM-13` | Debugging or one-off |
| Scan (local) | `python -m agents.agent2_coder --scan` | Local batch run during dev |
| Scan (CI) | "Run workflow" button on `Agent 2 - Coder` workflow | Production trigger |

All three respect the same selection criteria. Single-story mode does
NOT bypass the labels — if you pass `--story` for a story that doesn't
have `human-approved`, it will still process (the `--story` flag is for
explicit override). Use `--dry-run` to preview without opening a PR.

## What this is NOT

- **Not a webhook trigger.** A Jira automation rule that fires on label
  change → GitHub `repository_dispatch` is feasible (~12 hours of work
  with proper safety controls) but deferred. See the design notes in
  prior architectural discussions.
- **Not multi-user.** This pattern works for a single approver. Real
  teams need RBAC: who can add `human-approved`? That's left to Jira
  permissions today; future work would introduce a "approvers" group.
- **Not a quality gate.** `human-approved` means "I read and accept";
  it doesn't enforce that the test cases are good. The quality bar
  comes from Agent 1's prompt (in `prompts/agent1_analyst.md`).

## Failure modes

| What goes wrong | What happens | What you do |
|---|---|---|
| LLM generates bad test cases (Agent 1) | You see them on Jira | Add `ai-skip` label; run Agent 1 again with refined prompt |
| You forget to add `human-approved` | Agent 2 scan shows "0 stories to process" | Add the label; click Run again |
| Agent 2 fails partway through scan | Already-processed stories are tagged `ai-coded`; failed ones are not | Re-click Run — Agent 2 skips completed, retries failed |
| Network blip during Agent 2 run | Story may be tagged `ai-coded` without a PR existing | Manual cleanup: remove `ai-coded` label, retry |

The last row is a known idempotency edge case: the label is added
*after* PR creation, so the only way to be in "labeled but no PR" state
is if the network died between the GitHub create-PR API call succeeding
and the Jira add-label API call succeeding. This is rare. A future
improvement is to make the label-add part of a transaction or use a
"reconcile" check that runs on a schedule.