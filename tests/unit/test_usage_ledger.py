"""
Unit tests for agents.usage_ledger — the cross-agent, per-story
token & cost ledger. No Jira or LLM calls; pure parse/aggregate logic.
"""
import pytest

from agents.usage_ledger import (
    aggregate_story_usage,
    format_e2e_section,
    format_usage_comment,
    parse_usage_comment,
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
