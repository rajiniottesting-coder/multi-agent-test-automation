"""
Unit tests for agents.usage_ledger — the cross-agent, per-story
token & cost ledger. No Jira or LLM calls; pure parse/aggregate logic.
"""
import pytest

from agents.usage_ledger import (
    RESET_MARKER,
    aggregate_story_usage,
    format_e2e_section,
    format_reset_comment,
    format_usage_comment,
    has_usage_comments,
    parse_usage_comment,
    post_reset_to_story,
    post_usage_to_story,
)


def usage(calls=5, inp=48213, out=9877, in_cost=0.144639, out_cost=0.148155):
    total = None if in_cost is None or out_cost is None else in_cost + out_cost
    return {
        "llm_calls": calls,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "input_cost_usd": in_cost,
        "output_cost_usd": out_cost,
        "estimated_cost_usd": total,
        "calls_without_usage": 0,
    }


class TestFormatParseRoundTrip:

    def test_round_trip_with_cost(self):
        body = format_usage_comment("Agent 2 (Coder)", usage())
        parsed = parse_usage_comment(body)
        assert parsed["agent"] == "Agent 2 (Coder)"
        assert parsed["calls"] == 5
        assert parsed["input_tokens"] == 48213
        assert parsed["output_tokens"] == 9877
        assert parsed["input_cost_usd"] == pytest.approx(0.144639)
        assert parsed["output_cost_usd"] == pytest.approx(0.148155)
        assert parsed["cost_usd"] == pytest.approx(0.292794)

    def test_round_trip_without_pricing(self):
        body = format_usage_comment("Agent 1 (Analyst)", usage(in_cost=None, out_cost=None))
        assert "cost_usd=n/a" in body
        parsed = parse_usage_comment(body)
        assert parsed["cost_usd"] is None
        assert parsed["input_cost_usd"] is None
        # tokens still exact
        assert parsed["input_tokens"] == 48213

    def test_unreported_calls_note_included(self):
        u = usage()
        u["calls_without_usage"] = 2
        body = format_usage_comment("Agent 3 (Reviewer)", u)
        assert "2 call(s) did not report" in body
        # note must not break parsing
        assert parse_usage_comment(body) is not None


class TestParseRobustness:

    def test_non_usage_comment_returns_none(self):
        assert parse_usage_comment("Test run passed! 12/12 green.") is None

    def test_malformed_marker_returns_none(self):
        assert parse_usage_comment("[LLM-USAGE] agent=broken no fields here") is None

    def test_none_and_empty_are_safe(self):
        assert parse_usage_comment("") is None
        assert parse_usage_comment(None) is None


class TestAggregation:

    def test_sums_across_agents(self):
        comments = [
            "some human comment",
            format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=5000, out=2000, in_cost=0.015, out_cost=0.03)),
            format_usage_comment("Agent 2 (Coder, initial)", usage(calls=5, inp=48000, out=10000, in_cost=0.144, out_cost=0.15)),
            format_usage_comment("Agent 3 (Reviewer)", usage(calls=1, inp=20000, out=1500, in_cost=0.06, out_cost=0.0225)),
        ]
        agg = aggregate_story_usage(comments)
        assert agg["agent_runs"] == 3
        assert agg["total_calls"] == 7
        assert agg["total_input_tokens"] == 73000
        assert agg["total_output_tokens"] == 13500
        assert agg["total_tokens"] == 86500
        assert agg["total_cost_usd"] == pytest.approx(0.015 + 0.03 + 0.144 + 0.15 + 0.06 + 0.0225)
        assert agg["cost_complete"] is True

    def test_extra_entries_included(self):
        comments = [format_usage_comment("Agent 2 (Coder, initial)", usage(calls=4, inp=40000, out=8000))]
        own = usage(calls=1, inp=3000, out=800, in_cost=0.009, out_cost=0.012)
        own["agent"] = "Agent 5 (Reporter)"
        agg = aggregate_story_usage(comments, extra_entries=[own])
        assert agg["agent_runs"] == 2
        assert agg["total_input_tokens"] == 43000
        agents = [e["agent"] for e in agg["entries"]]
        assert "Agent 5 (Reporter)" in agents

    def test_partial_pricing_flags_incomplete(self):
        comments = [
            format_usage_comment("Agent 1 (Analyst)", usage(in_cost=None, out_cost=None)),
            format_usage_comment("Agent 2 (Coder, initial)", usage(in_cost=0.10, out_cost=0.05)),
        ]
        agg = aggregate_story_usage(comments)
        assert agg["cost_complete"] is False
        assert agg["total_cost_usd"] == pytest.approx(0.15)  # lower bound
        assert agg["total_tokens"] == 2 * (48213 + 9877)     # tokens always exact

    def test_empty_story(self):
        agg = aggregate_story_usage([])
        assert agg["agent_runs"] == 0
        assert agg["total_cost_usd"] is None
        assert format_e2e_section(agg) == ""


class TestE2ESection:

    def test_renders_table_with_total(self):
        comments = [
            format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=5000, out=2000, in_cost=0.015, out_cost=0.03)),
            format_usage_comment("Agent 2 (Coder, initial)", usage(calls=5, inp=48000, out=10000, in_cost=0.144, out_cost=0.15)),
        ]
        section = format_e2e_section(aggregate_story_usage(comments))
        assert "End-to-end LLM usage & cost" in section
        assert "Agent 1 (Analyst)" in section
        assert "Agent 2 (Coder, initial)" in section
        assert "TOTAL (2 agent runs)" in section
        assert "$0.3390" in section

    def test_lower_bound_note_when_pricing_partial(self):
        comments = [
            format_usage_comment("Agent 1 (Analyst)", usage(in_cost=None, out_cost=None)),
            format_usage_comment("Agent 2 (Coder, initial)", usage()),
        ]
        section = format_e2e_section(aggregate_story_usage(comments))
        assert "lower bound" in section


class TestPostUsageDefensive:

    def test_never_raises_without_jira_env(self, monkeypatch):
        for var in ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]:
            monkeypatch.delenv(var, raising=False)
        # JiraClient() would raise RuntimeError; ledger must swallow it
        assert post_usage_to_story("SCRUM-1", "Agent 3 (Reviewer)", usage()) is False

    def test_skips_on_empty_story_key(self):
        assert post_usage_to_story("", "Agent 1 (Analyst)", usage()) is False

    def test_posts_via_supplied_client(self):
        class FakeJira:
            def __init__(self): self.posted = []
            def add_comment(self, key, body): self.posted.append((key, body)); return "url"
        fj = FakeJira()
        assert post_usage_to_story("SCRUM-9", "Agent 2 (Coder, initial)", usage(), jira=fj) is True
        assert fj.posted[0][0] == "SCRUM-9"
        assert "[LLM-USAGE]" in fj.posted[0][1]


# ─────────────────────────────────────────────────────────────
# Ledger reset boundary (Phase 2 — backlog item 1.3)
#
# Scenario the boundary fixes: a story is fully processed (agents post usage
# comments), then the human deletes the test cases and resets the story to
# `ai-ready`. The old comments remain. Without a boundary, the next run's
# aggregation sums the discarded run + the new run → inflated cost report.
# ─────────────────────────────────────────────────────────────

class _FakeJira:
    def __init__(self):
        self.comments = []

    def add_comment(self, key, body):
        self.comments.append((key, body))


def test_format_reset_comment_contains_marker():
    body = format_reset_comment("story reprocessed from ai-ready")
    assert RESET_MARKER in body
    assert "story reprocessed from ai-ready" in body


def test_format_reset_comment_without_reason():
    body = format_reset_comment()
    assert RESET_MARKER in body
    assert "reason=" not in body


def test_post_reset_to_story_posts_once():
    jira = _FakeJira()
    assert post_reset_to_story("SCRUM-20", "restart", jira=jira) is True
    assert len(jira.comments) == 1
    assert RESET_MARKER in jira.comments[0][1]


def test_post_reset_to_story_no_key_is_noop():
    jira = _FakeJira()
    assert post_reset_to_story("", "restart", jira=jira) is False
    assert jira.comments == []


def test_post_reset_to_story_never_raises():
    class Broken:
        def add_comment(self, *a, **kw):
            raise RuntimeError("jira down")
    assert post_reset_to_story("SCRUM-20", "restart", jira=Broken()) is False


def test_aggregate_ignores_usage_before_reset():
    """The core fix: pre-reset usage must not inflate the total."""
    discarded = format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=5000, out=2000))
    boundary = format_reset_comment("story reprocessed from ai-ready")
    current = format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=3000, out=1000))

    agg = aggregate_story_usage([discarded, boundary, current])

    assert agg["agent_runs"] == 1
    assert agg["total_input_tokens"] == 3000
    assert agg["total_output_tokens"] == 1000


def test_aggregate_honours_only_the_last_reset():
    """Two restarts: only usage after the most recent boundary counts."""
    bodies = [
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=9999, out=9999)),
        format_reset_comment("first restart"),
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=8888, out=8888)),
        format_reset_comment("second restart"),
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=1000, out=500)),
        format_usage_comment("Agent 2 (Coder)", usage(calls=3, inp=2000, out=700)),
    ]
    agg = aggregate_story_usage(bodies)

    assert agg["agent_runs"] == 2
    assert agg["total_input_tokens"] == 3000
    assert agg["total_output_tokens"] == 1200


def test_aggregate_without_reset_is_unchanged():
    """Backward compatibility: no boundary → every comment counts (old behaviour)."""
    bodies = [
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=1000, out=500)),
        format_usage_comment("Agent 2 (Coder)", usage(calls=3, inp=2000, out=700)),
    ]
    agg = aggregate_story_usage(bodies)

    assert agg["agent_runs"] == 2
    assert agg["total_input_tokens"] == 3000


def test_aggregate_reset_with_no_usage_after_is_empty():
    """Reset posted, run then aborted before any usage — totals are zero, not stale."""
    bodies = [
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=5000, out=2000)),
        format_reset_comment("restart"),
    ]
    agg = aggregate_story_usage(bodies)

    assert agg["agent_runs"] == 0
    assert agg["total_input_tokens"] == 0
    assert agg["cost_complete"] is False


def test_reset_boundary_ignores_unrelated_comments():
    """Human comments interleaved with the ledger must not confuse the boundary."""
    bodies = [
        "Looks good to me, approving.",
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=5000, out=2000)),
        format_reset_comment("restart"),
        "Deleted the old test cases, re-running.",
        format_usage_comment("Agent 1 (Analyst)", usage(calls=1, inp=1234, out=567)),
    ]
    agg = aggregate_story_usage(bodies)

    assert agg["agent_runs"] == 1
    assert agg["total_input_tokens"] == 1234


def test_has_usage_comments_true_when_costed():
    assert has_usage_comments([format_usage_comment("Agent 1 (Analyst)", usage())]) is True


def test_has_usage_comments_false_when_only_human_comments():
    assert has_usage_comments(["Please add a negative case.", "Approved."]) is False


def test_has_usage_comments_false_after_reset_with_no_new_usage():
    """Already reset and nothing since — Agent 1 must not post a second boundary."""
    bodies = [
        format_usage_comment("Agent 1 (Analyst)", usage()),
        format_reset_comment("restart"),
    ]
    assert has_usage_comments(bodies) is False


def test_has_usage_comments_empty_list():
    assert has_usage_comments([]) is False