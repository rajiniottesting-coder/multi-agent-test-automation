"""A story the final gate refused is reported once and not retried on unchanged input.

SCRUM-187 (validation, 26 Oct 2026): Agent 2's final gate refused the story
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
    body = tracker.comments[0]
    assert body.splitlines()[0] == f"{blocked.BLOCKED_MARKER} inputs: {fp}"
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


def test_only_the_normal_scan_pass_skips():
    """Regenerate and update are explicit requests; a manual run is a retry."""
    import inspect

    import agents.agent2_coder as a2
    src = inspect.getsource(a2.main)
    assert src.count("skip_if_blocked=True") == 1
    normal = src.split("for story in normal_stories:")[1].split("for story in regen_stories:")[0]
    assert "skip_if_blocked=True" in normal
