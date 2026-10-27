"""Whose turn is it to run the browser tests? First come, first served.

The app E2E of every pull request logs in to the SAME live application with
the SAME test accounts, and some of what a test does persists (a cart, saved
items). Two pull requests running their E2E at once can therefore change each
other's results - a flaky failure neither PR caused.

Agent 4 already serialises runs of ONE pull request (its job-level
concurrency group). Across pull requests it cannot use a shared group: GitHub
keeps only one pending run per group and CANCELS any earlier pending one, and
a cancelled run is exactly what the sweeper reads as a stalled PR. So each run
waits here instead, for every run of a DIFFERENT pull request that started
before it (a lower run id) and has not finished. The lowest waits for nobody,
so the queue always moves; the workflow also caps the wait and then proceeds.

Standard library only. Usage: the workflow-runs JSON list on stdin
(`gh api .../runs --jq .workflow_runs`); prints the run ids still ahead of
this one, space-separated - nothing when it is this run's turn.

    python3 scripts/e2e_turn.py --me <run id> --branch <this run's branch>
"""
import argparse
import json
import sys

# A run in any of these states has not finished, so it may still be driving
# the live application (or is about to).
ACTIVE = {"queued", "in_progress", "waiting", "requested", "pending"}

# Runs that drive the live application in turn: pull requests, and the nightly
# run on main (F-21). A push to main runs the unit suite and only rarely the
# E2E; it does not hold anybody up.
TURN_EVENTS = {"pull_request", "schedule"}


def runs_ahead(me: int, branch: str, runs: list) -> list[int]:
    """Unfinished runs of other pull requests (or the nightly run) that
    started before this one."""
    return sorted(int(r["id"]) for r in runs or []
                  if r.get("id") and int(r["id"]) < me
                  and r.get("status") in ACTIVE
                  and r.get("event", "pull_request") in TURN_EVENTS
                  and r.get("head_branch") != branch)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--me", type=int, required=True, help="this run's id")
    ap.add_argument("--branch", required=True, help="this pull request's head branch")
    args = ap.parse_args(argv)
    ahead = runs_ahead(args.me, args.branch, json.load(sys.stdin))
    print(" ".join(map(str, ahead)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
