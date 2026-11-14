"""Which runs belong to a story's current attempt on the usage ledger: Agent 0's
model cost reaches a change story's ledger and Agent 1 does not discard it as a
"previous run"; a failed Agent 1 run is the same attempt; a genuine new
attempt still resets.
"""

from unittest.mock import MagicMock, patch
import pytest
from core.usage_ledger import (
    IMPACT_ANALYST,
    RESET_MARKER,
    format_usage_comment,
    has_usage_comments,
)


USAGE = {"llm_calls": 2, "input_tokens": 1000, "output_tokens": 100,
         "input_cost_usd": 0.01, "output_cost_usd": 0.002, "estimated_cost_usd": 0.012}


def _entry(agent):
    return format_usage_comment(agent, USAGE)


class FakeTracker:
    def __init__(self, comments=()):
        self.comments = list(comments)

    def get_comments(self, key):
        return list(self.comments)

    def add_comment(self, key, body):
        self.comments.append(body)


class TestLedgerIgnoringAgents:
    def test_only_agent0_entries_do_not_count_as_costed(self):
        assert not has_usage_comments([_entry(IMPACT_ANALYST)], ignore_agents=(IMPACT_ANALYST,))

    def test_a_downstream_entry_still_counts(self):
        comments = [_entry(IMPACT_ANALYST), _entry("Agent 2 (Coder)")]
        assert has_usage_comments(comments, ignore_agents=(IMPACT_ANALYST,))

    def test_default_behaviour_is_unchanged(self):
        assert has_usage_comments([_entry(IMPACT_ANALYST)])
        assert not has_usage_comments([_entry("Agent 1 (Test Designer)"), RESET_MARKER])


class TestAFailedAgent1RunIsTheSameAttempt:
    """Observation O3 (11 Nov 2026, a validation story): Agent 1 ran out of room, wrote
    nothing; `ai-ready` added again opened a NEW attempt and its cost dropped
    out of the story's total. A failed Agent 1 run is the same attempt."""

    FAILED = "Agent 1 (Test Designer) (failed)"

    def test_only_failed_agent1_runs_are_not_a_previous_attempt(self):
        from core.usage_ledger import TEST_DESIGNER
        comments = [_entry(IMPACT_ANALYST), _entry(self.FAILED), _entry(self.FAILED)]
        assert not has_usage_comments(comments, ignore_agents=(IMPACT_ANALYST,),
                                      same_attempt_if_failed=(TEST_DESIGNER,))

    def test_a_successful_draft_or_a_later_agent_still_starts_a_new_attempt(self):
        from core.usage_ledger import TEST_DESIGNER
        for other in ("Agent 1 (Test Designer)", "Agent 2 (Coder) (failed)"):
            comments = [_entry(self.FAILED), _entry(other)]
            assert has_usage_comments(comments, ignore_agents=(IMPACT_ANALYST,),
                                      same_attempt_if_failed=(TEST_DESIGNER,)), other

    def test_agent1_passes_its_own_failed_runs(self):
        from pathlib import Path
        src = Path("agents/agent1_analyst.py").read_text(encoding="utf-8")
        assert "same_attempt_if_failed=(TEST_DESIGNER,)" in src

    def test_other_callers_are_unchanged(self):
        assert has_usage_comments([_entry(self.FAILED)], ignore_agents=(IMPACT_ANALYST,))


class TestAgent0PostsItsUsage:
    def _post(self, tracker, usage=USAGE):
        import agents.agent0_impact as a0
        with patch("core.llm_client.log_usage_summary", return_value=dict(usage)), \
             patch("core.llm_client.reset_usage") as reset:
            a0._post_usage(tracker, "PROJ-1")
        return reset

    def test_a_fresh_story_gets_one_entry(self):
        t = FakeTracker()
        reset = self._post(t)
        assert len(t.comments) == 1 and f'agent="{IMPACT_ANALYST}"' in t.comments[0]
        reset.assert_called_once()                      # next story starts from zero

    def test_reanalysis_in_one_attempt_accumulates(self):
        t = FakeTracker([_entry(IMPACT_ANALYST)])
        self._post(t)
        assert not any(RESET_MARKER in c for c in t.comments)
        assert sum(IMPACT_ANALYST in c for c in t.comments) == 2

    def test_a_new_attempt_after_downstream_agents_resets_first(self):
        t = FakeTracker([_entry(IMPACT_ANALYST), _entry("Agent 1 (Test Designer)"),
                         _entry("Agent 2 (Coder)")])
        self._post(t)
        assert RESET_MARKER in t.comments[-2] and IMPACT_ANALYST in t.comments[-1]

    def test_no_model_call_posts_nothing(self):
        t = FakeTracker()
        self._post(t, dict(USAGE, llm_calls=0))
        assert t.comments == []

    def test_a_tracker_failure_never_fails_agent0(self):
        t = FakeTracker()
        t.get_comments = MagicMock(side_effect=RuntimeError("jira down"))
        self._post(t)                                    # no exception


def test_agent1_keeps_agent0s_entry_on_a_change_story(tmp_path, monkeypatch):
    """End to end in the sandbox: Agent 0's entry is on the story when Agent 1
    drafts it; Agent 1 must not post a reset that would drop it."""
    from tests.unit.test_agent2_impact import _hand_over_and_draft, world
    fake, jira, _root = world.__wrapped__(tmp_path, monkeypatch)
    fake.comments.setdefault("SBX-5", []).append(_entry(IMPACT_ANALYST))
    _hand_over_and_draft(jira, {"SBX-11": "approve"})
    bodies = jira.get_comments("SBX-5")
    assert not any(RESET_MARKER in b for b in bodies)
    assert any(IMPACT_ANALYST in b for b in bodies)


@pytest.mark.parametrize("store", ["comments", "auto"])
def test_agent1_still_resets_when_the_story_was_costed_downstream(tmp_path, monkeypatch, store):
    """Both ledger stores: the reset is a [LEDGER-RESET] comment, or a hidden
    reset entry after which the old entries no longer count (F-31)."""
    import core.usage_ledger as ul
    from tests.unit.test_agent2_impact import _hand_over_and_draft, world
    monkeypatch.setattr(ul, "_store_setting", lambda: store)
    fake, jira, _root = world.__wrapped__(tmp_path, monkeypatch)
    fake.comments.setdefault("SBX-5", []).append(_entry("Agent 2 (Coder)"))
    _hand_over_and_draft(jira, {"SBX-11": "approve"})
    if store == "comments":
        assert any(RESET_MARKER in b for b in jira.get_comments("SBX-5"))
    else:
        assert any(k.startswith(ul.PROP_RESET + ".") for k in fake.properties.get("SBX-5", {}))
        assert not any(RESET_MARKER in b for b in jira.get_comments("SBX-5"))
    assert all(e["agent"] != "Agent 2 (Coder)"
               for e in ul.story_ledger("SBX-5", jira)["entries"]), "the old run no longer counts"
