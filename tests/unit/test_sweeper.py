"""Unit tests for backlog 3.4 sweeper decision logic (no network).

Covers workflow_settled() and classify_pr() — the pure core that decides which
open PRs are genuinely stalled vs. legitimately finished.
"""
from scripts.sweep_stalled_prs import workflow_settled, classify_pr


def _run(status, conclusion):
    return {"status": status, "conclusion": conclusion}


# ── workflow_settled ──────────────────────────────────────────

def test_settled_on_success():
    assert workflow_settled([_run("completed", "success")]) is True


def test_settled_on_failure():
    # A red suite is a REAL result the pipeline reported — not a stall.
    assert workflow_settled([_run("completed", "failure")]) is True


def test_not_settled_on_cancelled():
    assert workflow_settled([_run("completed", "cancelled")]) is False


def test_not_settled_on_skipped():
    assert workflow_settled([_run("completed", "skipped")]) is False


def test_not_settled_on_in_progress():
    assert workflow_settled([_run("in_progress", None)]) is False


def test_not_settled_on_no_runs():
    assert workflow_settled([]) is False


def test_settled_if_any_run_settled():
    runs = [_run("completed", "cancelled"), _run("completed", "success")]
    assert workflow_settled(runs) is True


# ── classify_pr ───────────────────────────────────────────────

AUTO = "auto/SCRUM-5-login"
SHA = "abc1234def"


def test_skip_non_auto_branch():
    d = classify_pr(SHA, "feature/manual", {}, None)
    assert d["action"] == "skip" and "auto/" in d["reason"]


def test_skip_when_all_settled():
    wf = {
        "agent3-reviewer.yml": [_run("completed", "success")],
        "agent4_runner.yml": [_run("completed", "failure")],
    }
    d = classify_pr(SHA, AUTO, wf, None)
    assert d["action"] == "skip" and d["reason"] == "all workflows settled"


def test_nudge_when_one_workflow_missing():
    wf = {
        "agent3-reviewer.yml": [_run("completed", "success")],
        "agent4_runner.yml": [],  # never ran
    }
    d = classify_pr(SHA, AUTO, wf, None)
    assert d["action"] == "nudge"
    assert d["stalled"] == ["agent4_runner.yml"]


def test_nudge_when_cancelled():
    wf = {
        "agent3-reviewer.yml": [_run("completed", "cancelled")],
        "agent4_runner.yml": [_run("completed", "success")],
    }
    d = classify_pr(SHA, AUTO, wf, None)
    assert d["action"] == "nudge"
    assert d["stalled"] == ["agent3-reviewer.yml"]


def test_no_double_nudge_same_commit():
    wf = {"agent3-reviewer.yml": [], "agent4_runner.yml": []}
    d = classify_pr(SHA, AUTO, wf, already_nudged_sha=SHA)
    assert d["action"] == "skip"
    assert "already nudged" in d["reason"]


def test_nudge_again_after_new_commit():
    wf = {"agent3-reviewer.yml": [], "agent4_runner.yml": []}
    # nudged an OLD sha; this PR is now on a new commit -> nudge again
    d = classify_pr(SHA, AUTO, wf, already_nudged_sha="oldsha000")
    assert d["action"] == "nudge"


def test_both_stalled_lists_both():
    wf = {"agent3-reviewer.yml": [], "agent4_runner.yml": [_run("completed", "skipped")]}
    d = classify_pr(SHA, AUTO, wf, None)
    assert set(d["stalled"]) == {"agent3-reviewer.yml", "agent4_runner.yml"}