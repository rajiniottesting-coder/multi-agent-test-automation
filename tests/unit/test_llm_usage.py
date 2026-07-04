"""
Unit tests for LLM usage tracking and cost estimation in agents.llm_client.

No LLM calls are made — these test the accumulator and cost math directly,
plus _record_usage() against a fake LangChain-style response object.
"""
import pytest

from agents import llm_client
from agents.llm_client import (
    _UsageTracker,
    _record_usage,
    get_usage_summary,
    log_usage_summary,
    reset_usage,
)


class FakeResponse:
    """Mimics a LangChain AIMessage with usage_metadata."""
    def __init__(self, usage_metadata):
        self.usage_metadata = usage_metadata
        self.content = "irrelevant"


@pytest.fixture(autouse=True)
def clean_tracker(monkeypatch):
    """Reset global tracker and pricing env before/after each test."""
    monkeypatch.delenv("LLM_PRICE_INPUT_PER_1M", raising=False)
    monkeypatch.delenv("LLM_PRICE_OUTPUT_PER_1M", raising=False)
    reset_usage()
    yield
    reset_usage()


class TestUsageTracker:

    def test_accumulates_across_calls(self):
        t = _UsageTracker()
        t.add(1000, 200)
        t.add(500, 300)
        assert t.calls == 2
        assert t.input_tokens == 1500
        assert t.output_tokens == 500
        assert t.total_tokens == 2000

    def test_cost_is_none_without_pricing_env(self):
        t = _UsageTracker()
        t.add(1_000_000, 1_000_000)
        assert t.cost_usd() is None
        assert "n/a" in t.cost_str()

    def test_cost_math_with_pricing(self, monkeypatch):
        monkeypatch.setenv("LLM_PRICE_INPUT_PER_1M", "3.00")
        monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_1M", "15.00")
        t = _UsageTracker()
        t.add(1_000_000, 200_000)  # 1M in, 0.2M out
        # 1.0 * 3.00 + 0.2 * 15.00 = 3.00 + 3.00 = 6.00
        assert t.cost_usd() == pytest.approx(6.00)
        assert t.cost_str() == "$6.0000"

    def test_non_numeric_pricing_degrades_to_none(self, monkeypatch):
        monkeypatch.setenv("LLM_PRICE_INPUT_PER_1M", "three dollars")
        monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_1M", "15.00")
        t = _UsageTracker()
        t.add(1000, 1000)
        assert t.cost_usd() is None

    def test_reset_clears_everything(self):
        t = _UsageTracker()
        t.add(100, 50)
        t.add_unreported()
        t.reset()
        assert t.calls == 0
        assert t.total_tokens == 0
        assert t.calls_without_usage == 0

    def test_unreported_counts_call_but_no_tokens(self):
        t = _UsageTracker()
        t.add_unreported()
        assert t.calls == 1
        assert t.total_tokens == 0
        assert t.calls_without_usage == 1


class TestRecordUsage:

    def test_records_from_response_metadata(self):
        _record_usage(FakeResponse({"input_tokens": 800, "output_tokens": 150}), "test")
        s = get_usage_summary()
        assert s["llm_calls"] == 1
        assert s["input_tokens"] == 800
        assert s["output_tokens"] == 150
        assert s["total_tokens"] == 950

    def test_missing_usage_metadata_is_non_fatal(self):
        _record_usage(FakeResponse(None), "test")
        s = get_usage_summary()
        assert s["llm_calls"] == 1
        assert s["calls_without_usage"] == 1
        assert s["total_tokens"] == 0

    def test_partial_usage_metadata_counts_as_unreported(self):
        _record_usage(FakeResponse({"input_tokens": 800}), "test")  # no output_tokens
        s = get_usage_summary()
        assert s["calls_without_usage"] == 1
        assert s["total_tokens"] == 0

    def test_never_raises_on_weird_response(self):
        _record_usage(object(), "test")  # no usage_metadata attribute at all
        s = get_usage_summary()
        assert s["llm_calls"] == 1  # counted as unreported


class TestSummary:

    def test_log_usage_summary_returns_dict(self, monkeypatch):
        monkeypatch.setenv("LLM_PRICE_INPUT_PER_1M", "2.50")
        monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_1M", "10.00")
        _record_usage(FakeResponse({"input_tokens": 40_000, "output_tokens": 8_000}), "a")
        _record_usage(FakeResponse({"input_tokens": 35_000, "output_tokens": 6_000}), "b")
        s = log_usage_summary("story TEST-1")
        assert s["llm_calls"] == 2
        assert s["input_tokens"] == 75_000
        assert s["output_tokens"] == 14_000
        # 0.075 * 2.50 + 0.014 * 10.00 = 0.1875 + 0.14 = 0.3275
        assert s["estimated_cost_usd"] == pytest.approx(0.3275)

    def test_reset_between_stories_gives_per_story_numbers(self):
        _record_usage(FakeResponse({"input_tokens": 1000, "output_tokens": 100}), "s1")
        reset_usage()
        _record_usage(FakeResponse({"input_tokens": 2000, "output_tokens": 200}), "s2")
        s = get_usage_summary()
        assert s["input_tokens"] == 2000  # only story 2
