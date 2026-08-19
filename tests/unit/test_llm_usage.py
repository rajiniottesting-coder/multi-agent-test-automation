"""
Unit tests for core.llm_client: usage tracking, cost estimation, and the
one-shot repair that structured output falls back on.

No LLM calls are made — these test the accumulator and cost math directly,
plus _record_usage() against a fake LangChain-style response object.
"""
import pytest

from core import llm_client
from core.llm_client import (
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



# ─────────────────────────────────────────────────────────────────────────
# Structured-output repair
#
# 31 Jul 2026: Agent 3 came back with five well-formed review issues and the
# required `issue_type` enum missing from every one. invoke_structured()
# validated once and raised, so the whole agent died, the PR got no review,
# and the tokens were already spent. Agent 2 had had a repair loop for months;
# structured output had none. These lock in the fix.
# ─────────────────────────────────────────────────────────────────────────
import json

from pydantic import BaseModel

from core.llm_client import LLMClient
from core.schemas import ReviewIssue


class _Reply:
    """Minimal stand-in for a LangChain AIMessage."""
    def __init__(self, content: str):
        self.content = content
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        self.response_metadata = {}


class _Model(BaseModel):
    name: str
    kind: str


def _client(replies):
    """An LLMClient wired to a scripted sequence of replies. No network."""
    client = object.__new__(LLMClient)
    client.model_name = "test-model"
    client.max_output_tokens = 8192
    sent = []

    class _FakeLLM:
        def invoke(self, messages):
            sent.append(messages)
            return _Reply(replies[len(sent) - 1])

    client.llm = _FakeLLM()
    return client, sent


def _call(client):
    return client.invoke_structured(
        system_prompt="sys", user_prompt="usr", output_schema=_Model
    )


class TestStructuredRepair:

    def test_valid_first_response_makes_no_second_call(self):
        client, sent = _client([json.dumps({"name": "a", "kind": "b"})])
        result = _call(client)
        assert (result.name, result.kind) == ("a", "b")
        assert len(sent) == 1, "a good response must never cost a repair call"

    def test_missing_field_is_repaired_on_the_retry(self):
        client, sent = _client([
            json.dumps({"name": "a"}),                       # `kind` missing
            json.dumps({"name": "a", "kind": "b"}),          # repaired
        ])
        result = _call(client)
        assert (result.name, result.kind) == ("a", "b")
        assert len(sent) == 2

    def test_repair_prompt_carries_the_error_and_the_bad_output(self):
        client, sent = _client([
            json.dumps({"name": "a"}),
            json.dumps({"name": "a", "kind": "b"}),
        ])
        _call(client)
        repair_text = sent[1][-1].content
        assert "kind" in repair_text, "the failing field must be named"
        assert "VALIDATION ERRORS" in repair_text
        assert '"name": "a"' in repair_text, "prior output must be echoed back"

    def test_repair_is_attempted_exactly_once(self):
        client, sent = _client([
            json.dumps({"name": "a"}),
            json.dumps({"name": "a"}),        # still wrong
        ])
        with pytest.raises(ValueError, match="invalid JSON"):
            _call(client)
        assert len(sent) == 2, "one retry, never a loop"

    def test_original_error_is_the_one_raised(self):
        """The first failure is what a human needs to read, not the retry's."""
        client, _ = _client([json.dumps({"name": "a"}), json.dumps({"name": "a"})])
        with pytest.raises(ValueError) as excinfo:
            _call(client)
        assert "kind" in str(excinfo.value)

    def test_repair_call_is_counted_in_the_cost_ledger(self):
        client, _ = _client([
            json.dumps({"name": "a"}),
            json.dumps({"name": "a", "kind": "b"}),
        ])
        _call(client)
        assert get_usage_summary()["llm_calls"] == 2, "a repair is paid for; count it"

    def test_a_crashing_repair_call_still_raises_the_original(self):
        client = object.__new__(LLMClient)
        client.model_name = "test-model"
        client.max_output_tokens = 8192

        class _FlakyLLM:
            def __init__(self):
                self.n = 0

            def invoke(self, messages):
                self.n += 1
                if self.n == 1:
                    return _Reply(json.dumps({"name": "a"}))
                raise RuntimeError("gateway exploded")

        client.llm = _FlakyLLM()
        with pytest.raises(ValueError, match="invalid JSON"):
            _call(client)

    def test_unparseable_first_response_is_also_repairable(self):
        client, sent = _client([
            "I think the answer is probably fine, honestly.",
            json.dumps({"name": "a", "kind": "b"}),
        ])
        result = _call(client)
        assert result.kind == "b"
        assert len(sent) == 2


class TestReviewIssueDefault:
    """The backstop behind the repair: an omitted category must never be able
    to void an entire review."""

    def test_issue_type_defaults_instead_of_failing_validation(self):
        issue = ReviewIssue(
            severity="major",
            file_path="tests/step_defs/test_x.py",
            description="d",
            suggested_fix="f",
        )
        assert issue.issue_type == "best_practice"

    def test_an_explicit_issue_type_is_still_honoured(self):
        issue = ReviewIssue(
            severity="blocking",
            file_path="p",
            issue_type="functional_bug",
            description="d",
            suggested_fix="f",
        )
        assert issue.issue_type == "functional_bug"

    def test_the_other_required_fields_are_still_required(self):
        """Defaulting one enum must not quietly loosen the whole schema."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ReviewIssue(severity="major", file_path="p", description="d")

# ─────────────────────────────────────────────────────────────────────────
# Cache reporting must distinguish "off" from "ignored"
#
# A whole CI run produced not one cache line. That was indistinguishable from
# caching being disabled - so the obvious reading, "we just aren't using it",
# was wrong: the breakpoint WAS sent and the gateway dropped it. Every call
# billed the full ~9,800-token static prefix and nothing said so.
#
# Silence is not a measurement.
# ─────────────────────────────────────────────────────────────────────────

class _CacheReply:
    def __init__(self, **usage):
        self.usage_metadata = {"input_tokens": 1000, "output_tokens": 100, **usage}


def test_a_cache_hit_is_reported(caplog):
    from core.llm_client import _record_usage
    with caplog.at_level("INFO"):
        _record_usage(_CacheReply(input_token_details={"cache_read": 9800}),
                      "text:code-gen", cache_requested=True)
    assert "LLM cache" in caplog.text
    assert "read=9,800" in caplog.text


def test_a_requested_but_unreported_cache_says_so(caplog):
    """The case that cost a run: breakpoint sent, nothing reported back."""
    from core.llm_client import _record_usage
    with caplog.at_level("INFO"):
        _record_usage(_CacheReply(), "text:code-gen", cache_requested=True)
    assert "requested but NOT reported" in caplog.text
    assert "gateway" in caplog.text, "name the likely cause"
    assert "in=" in caplog.text, "tell the reader how to confirm it themselves"


def test_no_cache_line_when_no_prefix_was_sent(caplog):
    """Agents 1, 3 and 5 make one call each - there is nothing to reuse, so a
    cache line there would be noise."""
    from core.llm_client import _record_usage
    with caplog.at_level("INFO"):
        _record_usage(_CacheReply(), "structured:CodePlan", cache_requested=False)
    assert "LLM cache" not in caplog.text


def test_usage_is_still_logged_either_way(caplog):
    from core.llm_client import _record_usage
    with caplog.at_level("INFO"):
        _record_usage(_CacheReply(), "text:code-gen", cache_requested=True)
    assert "LLM usage" in caplog.text
    assert "in=1000" in caplog.text and "out=100" in caplog.text