"""Agent 4 is always visible on a PR while it waits its turn.

Found on PR #178: two commits pushed a few seconds apart. The second Agent 4
run waited behind the first in a WORKFLOW-level concurrency group, and GitHub
creates no check for a run that has not started - so the PR said "All checks
have passed" (Agent 3 only) with the merge button green, while Agent 4 had not
tested the newest commit at all.

The serialisation is kept (two runs of one PR must not drive the live
application at once), but at JOB level, so the run starts and "Run Tests" is
listed as waiting.
"""
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "agent4_runner.yml"


def _wf():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def test_no_workflow_level_concurrency():
    assert "concurrency" not in _wf(), (
        "a workflow-level group hides a queued Agent 4 run from the PR's checks")


def test_the_test_job_is_still_serialised_per_pr_and_never_cancelled_on_a_pr():
    c = _wf()["jobs"]["test"]["concurrency"]
    assert "pull_request.number" in c["group"]
    assert c["cancel-in-progress"] == "${{ github.event_name == 'push' }}"
