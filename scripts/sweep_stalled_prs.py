#!/usr/bin/env python3
"""Sweep stalled event-driven PRs and re-trigger them (backlog 3.4).

Agents 1 and 2 are cron-driven and self-heal (a failed tick retries next tick).
Agents 3 (review) and 4/5 (run + report) are fired by the one-shot `pull_request`
event; if that run is cancelled or never starts, the PR stalls silently — opened
but never reviewed/tested/reported. This sweeper runs on its own hourly cron,
finds open `auto/*` PRs whose Agent-3 or Agent-4 workflow has no settled run for
the current commit, and re-fires them.

Re-trigger = **reopen** the PR (close→reopen), which emits a real `pull_request`
(reopened) event. That matters: Agent 5's report job is gated on
`github.event_name == 'pull_request'`, so a `workflow_dispatch` re-run would run
the tests but SKIP the report — reopening re-runs the whole event chain.

Loop-safety: a settled run means the workflow reached a real verdict
(success / failure / timed_out) — a red result is a real result, NOT a stall, so
it is left alone. Only cancelled / skipped / missing runs count as stalled. And
each nudge drops a marker comment keyed to the commit SHA, so a PR is nudged at
most once per commit.

Usage:
    python -m scripts.sweep_stalled_prs                 # act
    python -m scripts.sweep_stalled_prs --dry-run       # report only
Needs GITHUB_TOKEN + GITHUB_REPO (same as the agents).

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m scripts.sweep_stalled_prs --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Workflows that are event-driven and can strand a PR. Agent 5 lives inside the
# agent4 workflow, so checking agent4 covers both the run and the report.
REQUIRED_WORKFLOWS = ["agent3-reviewer.yml", "agent4_runner.yml"]

# A run in one of these states reached a genuine verdict → the pipeline did its
# job; do NOT re-trigger (a failing test suite is a real result to report).
_SETTLED_CONCLUSIONS = {"success", "failure", "timed_out", "neutral"}

AUTO_BRANCH_PREFIX = "auto/"
_MARKER = "<!-- sweeper:nudged:{sha} -->"


# ─────────────────────────────────────────────────────────────
# Pure decision logic (unit-tested; no network)
# ─────────────────────────────────────────────────────────────

# A run that has not finished yet. Something IS already working on this commit,
# so the PR is not stalled - nudging it now would restart a healthy run.
_ACTIVE_STATUSES = {"in_progress", "queued", "requested", "waiting", "pending"}


def workflow_active(runs_for_sha: list[dict]) -> bool:
    """True if a run for this commit is still executing or waiting to start.

    Without this the sweeper races Agent 2: a PR opened moments earlier has no
    SETTLED run yet (Agent 3/4 are mid-flight), so it looked stalled and got
    reopened - cancelling healthy work and re-running the whole chain. The
    window is small but real, and it widens as the agent cron gets busier.
    """
    return any(r.get("status") in _ACTIVE_STATUSES for r in runs_for_sha)


def workflow_settled(runs_for_sha: list[dict]) -> bool:
    """True if any run for this commit reached a real verdict."""
    return any(
        r.get("status") == "completed" and r.get("conclusion") in _SETTLED_CONCLUSIONS
        for r in runs_for_sha
    )


def classify_pr(head_sha: str, head_ref: str, wf_runs: dict[str, list[dict]],
                already_nudged_sha: str | None) -> dict:
    """Decide what to do with one PR. Returns {'action': 'nudge'|'skip', ...}."""
    if not head_ref.startswith(AUTO_BRANCH_PREFIX):
        return {"action": "skip", "reason": "not an auto/* PR"}
    # Something is still running for this commit -> not stalled, leave it alone.
    # This is what stops the sweeper racing a PR Agent 2 has just opened.
    active = [wf for wf, runs in wf_runs.items() if workflow_active(runs)]
    if active:
        return {"action": "skip",
                "reason": f"still running: {', '.join(sorted(active))}"}
    stalled = [wf for wf, runs in wf_runs.items() if not workflow_settled(runs)]
    if not stalled:
        return {"action": "skip", "reason": "all workflows settled"}
    if already_nudged_sha == head_sha:
        return {"action": "skip",
                "reason": "already nudged this commit; awaiting result",
                "stalled": stalled}
    return {"action": "nudge",
            "reason": "stalled workflow(s): " + ", ".join(stalled),
            "stalled": stalled}


# ─────────────────────────────────────────────────────────────
# I/O shell — goes through the repo-host adapter, never PyGithub
#
# This used to call PyGithub directly (repo.get_workflow, pr.edit(state=...),
# pr.create_issue_comment). That made the sweeper GitHub-only even though its
# decision logic is generic: "has CI settled for this commit, and have we
# already nudged it?" is true of GitLab pipelines and Azure Repos builds too.
# Everything provider-specific now sits behind agents/github_client.py.
# ─────────────────────────────────────────────────────────────

def _runs_for_sha(host, workflow_file: str, head_ref: str, head_sha: str) -> list[dict]:
    """CI runs for THIS commit only. Older commits' runs are irrelevant - the
    question is always whether *this* commit has been processed."""
    return [r for r in host.get_workflow_runs(workflow_file, head_ref)
            if r.get("head_sha") == head_sha]


def _already_nudged_sha(host, pr_number: int) -> str | None:
    """SHA from the hidden marker comment, or None. The marker is what stops
    the hourly cron nudging the same commit forever."""
    for body in host.get_pr_comments(pr_number):
        if "<!-- sweeper:nudged:" in body:
            try:
                return body.split("sweeper:nudged:")[1].split(" ")[0].rstrip("->").strip()
            except Exception:
                continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-trigger stalled auto/* PRs.",
        epilog=("examples:\n  report only, change nothing   --dry-run\n  live (what the hourly cron does)\n\nonly touches auto/* PRs, and nudges each commit at most once."),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Report only; take no action.")
    args = ap.parse_args()

    from integrations.repo_host import get_repo_host
    host = get_repo_host()

    open_prs = host.list_open_prs(branch_prefix=AUTO_BRANCH_PREFIX)
    print(f"Sweeper: {len(open_prs)} open auto/* PR(s) to inspect "
          f"({'DRY-RUN' if args.dry_run else 'live'}).")

    nudged = 0
    for pr in open_prs:
        head_ref, head_sha, number = pr["head_ref"], pr["head_sha"], pr["number"]
        wf_runs = {wf: _runs_for_sha(host, wf, head_ref, head_sha)
                   for wf in REQUIRED_WORKFLOWS}
        decision = classify_pr(head_sha, head_ref, wf_runs,
                               _already_nudged_sha(host, number))
        tag = f"PR #{number} ({head_ref} @ {head_sha[:7]})"
        if decision["action"] == "skip":
            print(f"  skip  {tag}: {decision['reason']}")
            continue
        print(f"  NUDGE {tag}: {decision['reason']}")
        if not args.dry_run:
            try:
                host.reopen_pull_request(number)
                host.post_pr_comment(
                    number,
                    _MARKER.format(sha=head_sha) +
                    f"\n🧹 Sweeper re-triggered this PR — it was stalled "
                    f"({decision['reason']}). Agents 3–5 should re-run."
                )
                nudged += 1
            except Exception as e:
                print(f"    ! failed to reopen #{number}: {type(e).__name__}: {e}",
                      file=sys.stderr)

    print(f"Sweeper done: {nudged} PR(s) re-triggered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())