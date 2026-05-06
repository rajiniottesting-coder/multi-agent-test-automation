# ADR-008: Use Scoped Personal Access Token for Agent 2's GitHub Operations

## Status

Accepted (2026-05-06)

## Context

Agent 2 (Coder) opens pull requests on the project's GitHub repository as
the final step of its workflow. Those PRs are intended to trigger three
downstream workflows:

- **Agent 3 (Reviewer)** — runs on `pull_request: opened/synchronize`
- **Agent 4 (Runner)** — runs on `pull_request: opened/synchronize`
- **Agent 5 (Reporter)** — runs as a job within Agent 4's workflow

This event-driven cascade is the core of the system's choreography
pattern (ADR-004). Without it, the human must manually trigger Agents
3/4/5 after every Agent 2 run, defeating the purpose of automation.

### The problem we hit

During end-to-end testing on PR #7 and PR #8, we observed that **no
downstream workflows were firing** after Agent 2 successfully opened
a PR. The PR appeared correctly on GitHub, but the "Checks 0" tab
remained empty — Agents 3/4/5 never got the `pull_request` event.

Investigation revealed this is **deliberate GitHub behavior**, not a
bug in our code. From GitHub's official documentation:

> When you use the repository's GITHUB_TOKEN to perform tasks, events
> triggered by the GITHUB_TOKEN, with the exception of workflow_dispatch
> and repository_dispatch, will not create a new workflow run. This
> prevents you from accidentally creating recursive workflow runs.

In plain terms: **GitHub deliberately suppresses workflow events when a
PR is opened by the built-in `GITHUB_TOKEN`** to prevent infinite
recursion (where Workflow A could open a PR, triggering Workflow B,
which opens another PR, triggering Workflow A...).

This is a useful safety mechanism for general-purpose automation, but
our system architecturally REQUIRES the cascade to fire.

## Decision

Replace `secrets.GITHUB_TOKEN` with a fine-grained Personal Access Token
stored as `secrets.GH_PAT` in Agent 2's workflow. GitHub treats PAT-based
PR creation as user-equivalent (because PATs are owned by users), so
PR events fire normally and downstream workflows trigger as expected.

### PAT Specification

| Aspect | Choice |
|---|---|
| Token type | **Fine-grained PAT** (modern, principle of least privilege) |
| Repository scope | **`multi-agent-test-automation` only** (single repo) |
| Permissions | **Contents: Read and write** (create branches, commit files) |
|  | **Pull requests: Read and write** (open PRs) |
|  | **Metadata: Read** (auto-included, required by GitHub) |
| Expiration | **Subject to user choice; rotation reminder set in calendar** |
| Storage | **GitHub repo secret named `GH_PAT`** |

We deliberately do NOT grant:
- `Workflows: Write` — Agent 2 doesn't modify `.github/workflows/*`
  files. If the LLM ever tried to, the existing `RESERVED_PATHS` check
  in agent2_coder.py would block it. Failing safe is good.
- `Issues: Write` — Agent 2 only operates on PRs, not issues.
- `Actions: Write` — Agent 2 doesn't trigger workflows directly; the
  cascade is event-driven through PR creation.
- Org/admin access — single-repo scope is sufficient.

### Implementation

Single-line change in `.github/workflows/agent2_coder.yml`:

```yaml
# BEFORE (cascade suppressed):
GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

# AFTER (cascade fires):
GITHUB_TOKEN: ${{ secrets.GH_PAT }}
```

The Python code (`agents/github_client.py`) is unchanged — it reads
`GITHUB_TOKEN` from env, we just feed it a different value.

## Alternatives Considered

### A. Empty-commit workaround (rejected)

After Agent 2 opens a PR, manually push an empty commit from a user
account. The push (from the user's PAT) re-triggers `pull_request:
synchronize` events, firing the cascade.

**Why rejected:**
- Manual, not scalable
- Requires a human to babysit every Agent 2 run
- Defeats the purpose of automation
- "Empty commit to trigger CI" is an anti-pattern; reviewers shouldn't
  see commits with no semantic value

### B. GitHub App authentication (deferred)

Create a GitHub App with explicit permissions, install on the repo, use
its short-lived installation token. Apps are treated as user-equivalent
for event firing.

**Why deferred:**
- ~2 hours of setup vs ~5 minutes for PAT
- More secure (auto-rotating tokens, scoped install) but overkill for
  a single-developer side project
- Better suited if/when this project becomes multi-developer or
  organization-owned

### C. Scheduled trigger instead of event-driven (rejected)

Replace the `pull_request` triggers on Agents 3/4/5 with `schedule:`
(cron) triggers that periodically scan for new PRs.

**Why rejected:**
- Adds latency (5+ minute delay vs near-instant)
- Wastes runner minutes on no-op scans
- Loses the choreography pattern's benefits
- Polling is an inferior pattern to events

### D. Continue with GITHUB_TOKEN + accept manual triggers (rejected)

Document the limitation: "after Agent 2 opens a PR, manually trigger
Agent 3 from the Actions UI."

**Why rejected:**
- Operationally bad
- Removes the multi-agent automation story from the architecture
- Not architect-quality

## Consequences

### Positive

- **Cascade fires automatically** — Agents 3/4/5 trigger on every Agent 2 PR
- **Demonstrates production-grade event-driven architecture** in portfolio
- **Single-line change** with clear documentation trail
- **Rolling back is trivial** if PAT causes issues (revert to GITHUB_TOKEN)
- **Aligns with industry pattern** — Renovate, Dependabot, and similar
  bots also use PATs/Apps for the same reason

### Negative

- **PR attribution shifts** — PRs now appear as opened by the PAT owner
  (the human user) rather than `github-actions[bot]`. Mitigated by:
  - The PR body explicitly states "*This PR was automatically generated
    by Agent 2 (Coder) from SCRUM-X.*"
  - Commit messages are prefixed `[Agent 2]` for clarity
  - In a team setting, this would be a reason to prefer GitHub Apps
    (Alternative B); for single-developer, it's acceptable
- **Token rotation responsibility** — PATs expire (max 1 year for
  fine-grained). A calendar reminder is set ~2 weeks before expiry to
  prevent silent breakage.
- **Compromise blast radius** — A leaked PAT grants write access to the
  scoped repo. Mitigated by:
  - Repository-scoped (not all-repos)
  - Minimum permissions (Contents + PRs only)
  - Stored as a GitHub secret (encrypted at rest, not visible to
    workflow code)

### Neutral

- **GitHub permissions:** Repository setting "Allow GitHub Actions to
  create and approve pull requests" is still required (separate setting).
  Both must be enabled.
- **No code changes required** — Python code is portable across token types.

## Rotation Strategy

| When | What |
|---|---|
| At PAT creation | Set calendar reminder 2 weeks before expiry |
| 2 weeks before expiry | Generate new PAT with same permissions |
| Day of rotation | Update `GH_PAT` secret in repo, verify Agent 2 still works |
| Day after rotation | Revoke old PAT in GitHub UI |

If a rotation is missed and the PAT expires:
- Agent 2's workflow fails on the GitHub API call (clear error in logs)
- The system fails CLOSED (no broken PRs created)
- Rotate and re-run — no data loss

## Verification

After applying this ADR's changes:

1. `secrets.GH_PAT` exists in the repo
2. `agent2_coder.yml` references `secrets.GH_PAT` (not `GITHUB_TOKEN`)
3. Repo setting "Allow GitHub Actions to create and approve PRs" is enabled
4. Trigger Agent 2 on a test story
5. Confirm PR opens AND check tab shows Agent 3/4 starting within ~30 seconds
6. Confirm Agent 5 posts comment to Jira after Agent 4 completes

## References

- ADR-004: Choreography over orchestration (the pattern this fix preserves)
- GitHub docs: [Triggering a workflow from a workflow](https://docs.github.com/en/actions/using-workflows/triggering-a-workflow#triggering-a-workflow-from-a-workflow)
- Renovate documentation on PAT requirements (similar architecture)
- PR #7 and PR #8: Real-world incidents that motivated this ADR