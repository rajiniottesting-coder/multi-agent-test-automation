"""F-3 (M1): each story's model cost lands on that story, a failed one included.

Before: in a scan, the usage counter was reset only after a story SUCCEEDED.
A story that failed part-way left its calls in the counter; the next story's
usage comment carried them, and the failed story's ledger showed nothing.

Now `core.usage_ledger.story_usage` wraps every story an agent runs (Agents 0,
1 and 2, scan and single-story): the counter starts at zero, and whatever the
run did not post is posted to that story - "<agent> (failed)" when it raised.
Generic names only.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

from core import llm_client
from core import usage_ledger as ul


def _spend(calls=1, tokens=100):
    for _ in range(calls):
        llm_client._tracker.add(tokens, tokens // 2)


@pytest.fixture(autouse=True)
def clean_counter():
    llm_client.reset_usage()
    yield
    llm_client.reset_usage()


def _posted(jira):
    return [(c.args[0], c.args[1]) for c in jira.add_comment.call_args_list]


def test_the_counter_starts_at_zero_for_each_story():
    _spend(3)                                   # left over from something else
    jira = MagicMock()
    with ul.story_usage("AB-1", "Agent X", jira=jira):
        assert llm_client.get_usage_summary()["llm_calls"] == 0
        _spend(2)
    (key, body), = _posted(jira)
    assert key == "AB-1" and 'agent="Agent X"' in body and "calls=2" in body
    assert llm_client.get_usage_summary()["llm_calls"] == 0


def test_a_failed_story_posts_its_own_cost_and_the_error_is_kept():
    jira = MagicMock()
    with pytest.raises(ValueError, match="gate"):
        with ul.story_usage("AB-1", "Agent X", jira=jira):
            _spend(4)
            raise ValueError("gate")
    (key, body), = _posted(jira)
    assert key == "AB-1" and 'agent="Agent X (failed)"' in body and "calls=4" in body
    assert llm_client.get_usage_summary()["llm_calls"] == 0, "the next story starts clean"


def test_a_run_that_posted_its_own_cost_adds_nothing():
    jira = MagicMock()
    with ul.story_usage("AB-1", "Agent X", jira=jira):
        _spend(2)
        llm_client.reset_usage()                # the run posted and reset itself
    assert _posted(jira) == []


def test_no_model_call_no_comment_and_dry_run_posts_nothing():
    jira = MagicMock()
    with ul.story_usage("AB-1", "Agent X", jira=jira):
        pass
    with pytest.raises(RuntimeError):
        with ul.story_usage("AB-2", "Agent X", jira=jira, dry_run=True):
            _spend(1)
            raise RuntimeError("x")
    assert _posted(jira) == []
    assert llm_client.get_usage_summary()["llm_calls"] == 0


def test_bookkeeping_never_hides_the_runs_own_error():
    jira = MagicMock()
    jira.add_comment.side_effect = OSError("tracker down")
    with pytest.raises(KeyError):
        with ul.story_usage("AB-1", "Agent X", jira=jira):
            _spend(1)
            raise KeyError("real")


def test_an_agents_failed_run_is_still_that_agent_for_the_reset_boundary():
    failed = ul.format_usage_comment("Agent 0 (Impact Analyst) (failed)", {"llm_calls": 1})
    other = ul.format_usage_comment("Agent 2 (Coder, initial)", {"llm_calls": 1})
    assert ul.has_usage_comments([failed], ignore_agents=(ul.IMPACT_ANALYST,)) is False
    assert ul.has_usage_comments([failed, other], ignore_agents=(ul.IMPACT_ANALYST,)) is True


def test_the_cost_table_counts_a_failed_run():
    rows = [ul.format_usage_comment("Agent 2 (Coder, initial) (failed)",
                                    {"llm_calls": 3, "input_tokens": 10, "output_tokens": 5,
                                     "estimated_cost_usd": 0.5}),
            ul.format_usage_comment("Agent 2 (Coder, initial)",
                                    {"llm_calls": 2, "input_tokens": 10, "output_tokens": 5,
                                     "estimated_cost_usd": 0.25})]
    agg = ul.aggregate_story_usage(rows)
    assert agg["agent_runs"] == 2 and agg["total_calls"] == 5 and agg["total_cost_usd"] == 0.75


# ── wired into every scan loop ───────────────────────────────────────────

def _scan_agent2(monkeypatch, run, run_update=None):
    import agents.agent2_coder as a2
    tracker = MagicMock()
    tracker.find_stories_to_process.side_effect = [
        [{"key": "AB-1"}, {"key": "AB-2"}], [], []]
    monkeypatch.setattr(a2, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a2, "validate_required_env", lambda *a: None)
    monkeypatch.setattr(a2, "run", run)
    monkeypatch.setattr(a2, "_print_scan_summary", lambda r: None)
    monkeypatch.setattr(ul, "post_usage_to_story",
                        lambda key, agent, usage, jira=None: posted.append((key, agent,
                                                                            usage["llm_calls"])))
    posted = []
    monkeypatch.setattr(sys, "argv", ["agent2", "--scan"])
    with pytest.raises(SystemExit):
        a2.main()
    return posted


def test_agent2_scan_charges_a_failed_story_to_itself_not_the_next(monkeypatch):
    def run(key, **kw):
        _spend(5 if key == "AB-1" else 1)
        if key == "AB-1":
            raise ValueError("gate refused")
        from core.llm_client import log_usage_summary, reset_usage
        posted.append((key, "Agent 2 (Coder, initial)", log_usage_summary(key)["llm_calls"]))
        reset_usage()
        return {"story_id": key, "status": "pr_opened"}
    posted = []
    posted += _scan_agent2(monkeypatch, run)
    assert ("AB-1", "Agent 2 (Coder, initial) (failed)", 5) in posted
    assert ("AB-2", "Agent 2 (Coder, initial)", 1) in posted, "AB-2 pays only its own call"


def test_agent1_scan_charges_a_failed_story_to_itself(monkeypatch):
    import agents.agent1_analyst as a1
    tracker = MagicMock()
    tracker.find_stories_to_process.return_value = [
        {"key": "AB-1", "status": "To Do", "summary": "s"},
        {"key": "AB-2", "status": "To Do", "summary": "s"}]
    monkeypatch.setattr(a1, "get_tracker", lambda: tracker)
    monkeypatch.setattr(a1, "validate_required_env", lambda *a: None)
    posted = []
    monkeypatch.setattr(ul, "post_usage_to_story",
                        lambda key, agent, usage, jira=None: posted.append((key, agent,
                                                                            usage["llm_calls"])))

    def run(key, dry_run=False):
        _spend(2 if key == "AB-1" else 0)
        if key == "AB-1":
            raise RuntimeError("model refused")
        return {"story_id": key, "status": "tests_drafted", "story_summary": "s",
                "test_cases_generated": 1, "test_case_keys": ["AB-9"]}
    monkeypatch.setattr(a1, "run", run)
    monkeypatch.setattr(sys, "argv", ["agent1", "--scan"])
    try:
        a1.main()
    except SystemExit:
        pass
    assert posted == [("AB-1", "Agent 1 (Test Designer) (failed)", 2)]


def test_agent0_scan_charges_a_failed_story_to_itself(monkeypatch):
    import agents.agent0_impact as a0
    tracker = MagicMock()
    tracker.find_stories_to_process.return_value = [{"key": "AB-1"}]
    posted = []
    monkeypatch.setattr(ul, "post_usage_to_story",
                        lambda key, agent, usage, jira=None: posted.append((key, agent)))

    def boom(*a, **k):
        _spend(1)
        raise RuntimeError("analysis failed")
    monkeypatch.setattr(a0, "analyse_and_publish", boom)
    settings = {"enabled": True, "shadow_mode": True, "selection": {}}
    out = a0.scan(tracker, None, None, settings, root=".")
    assert out[0]["action"] == "error"
    assert posted == [("AB-1", "Agent 0 (Impact Analyst) (failed)")]


def test_the_scans_post_through_their_own_tracker(monkeypatch):
    """Found by the end-to-end scan: without it, posting a failed story's cost
    built a second tracker client instead of using the agent's own."""
    import agents.agent1_analyst as a1
    import agents.agent2_coder as a2
    seen = []
    monkeypatch.setattr(ul, "post_usage_to_story",
                        lambda key, agent, usage, jira=None: seen.append(jira))
    for mod, argv, stories in ((a2, ["agent2", "--scan"], [[{"key": "AB-1"}], [], []]),
                               (a1, ["agent1", "--scan"],
                                [[{"key": "AB-1", "status": "To Do", "summary": "s"}]])):
        tracker = MagicMock()
        tracker.find_stories_to_process.side_effect = stories
        monkeypatch.setattr(mod, "get_tracker", lambda t=tracker: t)
        monkeypatch.setattr(mod, "validate_required_env", lambda *a: None)

        def boom(key, **kw):
            _spend(1)
            raise RuntimeError("x")
        monkeypatch.setattr(mod, "run", boom)
        if mod is a2:
            monkeypatch.setattr(a2, "_print_scan_summary", lambda r: None)
        monkeypatch.setattr(sys, "argv", argv)
        try:
            mod.main()
        except SystemExit:
            pass
        assert seen[-1] is tracker
