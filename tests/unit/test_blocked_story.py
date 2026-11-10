"""A story the final gate refused is reported once and not retried on unchanged input.

PRJ-187 (validation, 26 Oct 2026): Agent 2's final gate refused the story
after four repair attempts (about $2.50), wrote nothing to Jira, and the
scheduled scan picked it up again every 30 minutes to fail the same way.
core.blocked: one comment carrying a fingerprint of the input; the scan skips
while the fingerprint matches; any edit, or a manual run, tries again.
Generic names only; no network, no model.
"""
import os

for v in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
          "JIRA_PROJECT_KEY", "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ.setdefault(v, "stub")

import pytest

from core import blocked

STORY = {"key": "PROJ-5", "summary": "Shop", "description": "As a shopper ..."}
CASES = [{"key": "PROJ-7", "summary": "Add", "description": "Step 1 ..."},
         {"key": "PROJ-6", "summary": "Remove", "description": "Step 1 ..."}]


class Tracker:
    def __init__(self, comments=()):
        self.comments = list(comments)

    def get_comments(self, key):
        return list(self.comments)

    def add_comment(self, key, body):
        self.comments.append(body)


# ─────────────────────────────────────────────────────────────
# The fingerprint
# ─────────────────────────────────────────────────────────────
def test_the_fingerprint_ignores_order_and_follows_every_edit():
    fp = blocked.fingerprint(STORY, CASES)
    assert fp == blocked.fingerprint(STORY, list(reversed(CASES)))
    edited = [dict(CASES[0], description="Step 1 changed"), CASES[1]]
    assert fp != blocked.fingerprint(STORY, edited)
    assert fp != blocked.fingerprint(dict(STORY, description="changed"), CASES)
    assert fp != blocked.fingerprint(STORY, CASES, [{"key": "PROJ-9", "description": "x"}])


# ─────────────────────────────────────────────────────────────
# The comment
# ─────────────────────────────────────────────────────────────
def test_the_comment_is_posted_once_per_input_and_names_the_rules():
    tracker = Tracker()
    fp = blocked.fingerprint(STORY, CASES)
    errors = ["Persistent state error in 'features/x.feature': ...", "Second rule ..."]
    assert blocked.post_blocked_once(tracker, "PROJ-5", fp, errors)
    assert not blocked.post_blocked_once(tracker, "PROJ-5", fp, errors)
    # the same inputs refused for another reason (a retry by key after a fix)
    assert blocked.post_blocked_once(tracker, "PROJ-5", fp, ["a different rule"])
    assert not blocked.post_blocked_once(tracker, "PROJ-5", fp, ["a different rule"])
    assert blocked.blocked_on(tracker.get_comments("PROJ-5"), fp), "the scan still skips it"
    body = tracker.comments[0]
    assert body.splitlines()[0] == (f"{blocked.BLOCKED_MARKER} inputs: {fp} "
                                    f"reasons: {blocked._reasons_digest(errors)}")
    assert "Persistent state error" in body and "Second rule" in body
    assert blocked.blocked_on(tracker.comments, fp)
    assert not blocked.blocked_on(tracker.comments, blocked.fingerprint(STORY, CASES[:1]))


def test_a_long_error_list_is_capped():
    body = blocked.blocked_comment("PROJ-5", "0" * 16, [f"rule {i} " + "x" * 900 for i in range(9)])
    assert "and 3 more" in body
    assert max(len(line) for line in body.splitlines()) < 450


def test_posting_never_raises():
    class Broken:
        def get_comments(self, key):
            raise RuntimeError("down")
    assert blocked.post_blocked_once(Broken(), "PROJ-5", "0" * 16, ["x"]) is False


# ─────────────────────────────────────────────────────────────
# Agent 2: the scan skips, a manual run does not, a refusal is recorded
# ─────────────────────────────────────────────────────────────
class _Stop(Exception):
    pass


@pytest.fixture
def a2(monkeypatch):
    import agents.agent2_coder as a2
    import agents.agent2_impact as impact

    tracker = Tracker()
    tracker.get_parent_story_key = lambda key: None
    tracker.get_story = lambda key: STORY
    tracker.get_linked_test_cases = lambda key: CASES
    host = type("Host", (), {"find_open_pr_for_story": lambda self, k: None})()
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "get_repo_host", lambda: host)
    class Ctx:
        """Name and URL for the log line; anything else means the run went on
        past the blocked check towards generation - stop there."""
        name, base_url = "App", "https://app.example"

        def __getattr__(self, attr):
            raise _Stop(f"reached generation ({attr})")

    monkeypatch.setattr(a2, "AppContext", type("Load", (), {"load": staticmethod(Ctx)}))
    monkeypatch.setattr(impact, "impacted_for_run", lambda jira, key: ([], []))
    a2._tracker = tracker
    return a2


def test_the_scan_skips_a_refused_story_before_any_model_call(a2):
    fp = blocked.fingerprint(STORY, CASES)
    a2._tracker.comments.append(blocked.blocked_comment("PROJ-5", fp, ["rule"]))
    result = a2.run("PROJ-5", skip_if_blocked=True)
    assert result["status"] == "blocked"


def test_a_manual_run_always_runs(a2):
    fp = blocked.fingerprint(STORY, CASES)
    a2._tracker.comments.append(blocked.blocked_comment("PROJ-5", fp, ["rule"]))
    with pytest.raises(_Stop):
        a2.run("PROJ-5")


def test_an_edited_story_is_tried_again_by_the_scan(a2):
    old = blocked.fingerprint(STORY, [dict(CASES[0], description="old"), CASES[1]])
    a2._tracker.comments.append(blocked.blocked_comment("PROJ-5", old, ["rule"]))
    with pytest.raises(_Stop):
        a2.run("PROJ-5", skip_if_blocked=True)


def test_the_final_gate_carries_its_errors():
    e = a2_gate_failure = __import__("agents.agent2_coder", fromlist=["GateFailure"]).GateFailure(
        "Validation failed", errors=["one", "two"])
    assert isinstance(a2_gate_failure, ValueError) and e.errors == ["one", "two"]


def test_the_scan_summary_shows_a_blocked_story():
    from agents.agent2_coder import _scan_summary_lines
    lines = _scan_summary_lines([{"story_id": "PROJ-5", "status": "blocked"}])
    assert any(line.startswith("[BLOCK] PROJ-5") for line in lines)


def test_every_scan_pass_skips_a_refused_input(monkeypatch):
    """E135: every scan pass skips a story the gate refused on unchanged input.
    Only the normal pass did: a refused `ai-regenerate` story keeps its label,
    so every scan generated it again until its budget ran out (10 Nov 2026,
    $8 on one story). A manual run is still the retry. Checked by running the
    scan, not by reading its source."""
    import sys
    from unittest.mock import MagicMock

    import agents.agent2_coder as a2
    tracker = MagicMock()
    tracker.find_stories_to_process.side_effect = [
        [{"key": "PROJ-1"}], [{"key": "PROJ-2"}], [{"key": "PROJ-3"}]]
    calls = []
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "load_agent_config", lambda: {
        "selection": {"x": 1}, "regenerate_selection": {"x": 1}, "update_selection": {"x": 1},
        "max_stories_per_run": 5})
    monkeypatch.setattr(a2, "run", lambda key, **kw: calls.append(
        (key, kw.get("skip_if_blocked", False), kw.get("is_regenerate"))) or
        {"story_id": key, "status": "pr_opened"})
    monkeypatch.setattr(a2, "run_update", lambda key, **kw: calls.append(
        (key, "update", kw.get("skip_if_blocked", False))) or
                        {"story_id": key, "status": "update_pr_opened"})
    monkeypatch.setattr(a2, "_print_scan_summary", lambda r: None)
    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    a2.main()
    assert calls == [("PROJ-1", True, False), ("PROJ-2", True, True), ("PROJ-3", "update", True)]


def test_a_step_standing_in_for_a_control_points_at_the_inventory():
    """E133: a refusal on 'Action step error' (a click step that clicks
    nothing) is almost always a control the inventory lacks - the comment says
    so and gives the command, instead of the generic 'reword the test case'."""
    from core.blocked import blocked_comment
    err = ("Action step error in 'tests/step_defs/test_x.py': the step `When I click the "
           "control` says the user clicks, but its definition clicks nothing: ...")
    text = blocked_comment("AB-1", "0" * 16, [err])
    assert "plan_inventory element" in text and "retires the test case" in text
    assert "A rule that survives every repair" not in text


def test_an_update_refused_before_on_the_same_input_is_skipped(monkeypatch):
    """E135: run_update reads the same [agent2:blocked] fingerprint as run()."""
    from unittest.mock import MagicMock

    import agents.agent2_coder as a2
    from core import blocked
    tracker = MagicMock()
    story = {"key": "PROJ-5", "summary": "s", "description": "d"}
    cases = [{"key": "PROJ-6", "summary": "t", "description": "x"}]
    tracker.get_story.return_value = story
    tracker.get_comments.return_value = [blocked.blocked_comment(
        "PROJ-5", blocked.fingerprint(story, cases), ["Some error in 'x': y"])]
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "load_test_cases_for_story", lambda j, k: cases)
    out = a2.run_update("PROJ-5", skip_if_blocked=True)
    assert out["status"] == "blocked" and out["free"]
    tracker.get_comments.return_value = []
    monkeypatch.setattr(a2, "_locate_feature_file_for_story", lambda *a: None)
    monkeypatch.setattr(a2, "build_marker_index", lambda *a: {})
    assert a2.run_update("PROJ-5", skip_if_blocked=True)["status"] != "blocked"
