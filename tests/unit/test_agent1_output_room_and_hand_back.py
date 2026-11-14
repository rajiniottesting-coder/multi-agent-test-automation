"""When a model answer runs out of room, and when Agent 1 gives a story back:
a truncated answer is shown with its evidence and names the config key that
raises the cap; a failure the next run would only repeat (or a story that
needs a person) is handed back - trigger label removed, one comment saying
why - instead of being drafted again every scan.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from core.schemas import TestCase, TestCaseList, TestStep


ROOT = Path(__file__).resolve().parents[2]


def _tc(title, *expected):
    return TestCase(title=title, description="d", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)], expected_outcome="done")


def test_a_loop_is_named_and_large_content_is_not():
    from core.llm_client import truncation_evidence
    loop = "\n".join(['  "expected_result": "The item is shown in the list again and again",'] * 60)
    lines = truncation_evidence(loop)
    assert any("LIKELY A LOOP" in x for x in lines) and any("most repeated  : x60" in x for x in lines)
    varied = "\n".join(f'  "action": "step number {i} does a different thing entirely here",'
                       for i in range(60))
    lines = truncation_evidence(varied)
    assert any("no loop seen" in x for x in lines)
    assert lines[-1].startswith("  last characters:") and "step number 59" in lines[-1]


@pytest.mark.parametrize("content", [None, "", [{"type": "text", "text": "abc"}], 42])
def test_the_evidence_never_raises(content):
    from core.llm_client import truncation_evidence
    assert truncation_evidence(content)


def test_the_truncation_report_logs_the_evidence(caplog):
    from core.llm_client import OutputTruncatedError, _check_output_not_truncated
    response = NS(response_metadata={"finish_reason": "length"},
                  usage_metadata={"output_tokens": 10}, content="x " * 500)
    with caplog.at_level(logging.ERROR), pytest.raises(OutputTruncatedError):
        _check_output_not_truncated(response, label="structured:Thing", cap=10, knob="k")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "repetition     :" in text and "last characters:" in text


def test_a_truncation_names_the_config_key_that_raises_the_cap(monkeypatch):
    """An agent whose cap is a config.yaml value names that key, so raising
    it is a config change, not a code change."""
    from pydantic import BaseModel
    from core import llm_client
    from core.llm_client import LLMClient, OutputTruncatedError
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class Thing(BaseModel):
        x: int

    truncated = NS(response_metadata={"finish_reason": "length"},
                   usage_metadata={"output_tokens": 10}, content="{")
    for setting, named in (("agents.agent1_analyst.max_output_tokens",
                            "raise agents.agent1_analyst.max_output_tokens in config/config.yaml"),
                           (None, "raise max_output_tokens in the LLMClient(...) call")):
        client = LLMClient(max_output_tokens=10, cap_setting=setting)
        monkeypatch.setattr(client, "_call_with_quota_check", lambda fn, msgs: truncated)
        monkeypatch.setattr(llm_client, "_record_usage", lambda *a, **k: None)
        with pytest.raises(OutputTruncatedError, match=named.replace("(", r"\(").replace(
                ")", r"\)").replace(".", r"\.")):
            client.invoke_structured("s", "u", Thing)


def test_the_stop_comment_names_a_setting_never_a_code_change():
    from agents.agent1_analyst import hand_back
    from core.llm_client import OutputTruncatedError

    class T:
        def __init__(self):
            self.comments = []

        def remove_label(self, key, label):
            pass

        def add_comment(self, key, body):
            self.comments.append(body)

    t = T()
    hand_back(t, "AB-1", OutputTruncatedError(
        "x: output truncated at the 9-token cap. To re-run with more room: raise a.b in "
        "config/config.yaml (currently 9)", setting="a.b"), {"selection": {"required_labels": ["go"]}})
    assert "raise a.b in config.yaml" in t.comments[0] and "To re-run" not in t.comments[0]


def test_agent1_reads_its_output_room_from_config():
    import yaml
    shipped = yaml.safe_load(Path("config/config.yaml").read_text())
    # The value is a project's to tune (lowered for a validation, say): the
    # test checks it is usable, never what it is (E95).
    cap = shipped["agents"]["agent1_analyst"]["max_output_tokens"]
    assert isinstance(cap, int) and cap > 0
    source = Path("agents/agent1_analyst.py").read_text()
    assert 'cap_setting="agents.agent1_analyst.max_output_tokens"' in source
    assert "max_output_tokens=12288)" not in source, "the cap is read from config, not fixed"


def test_which_failures_stop_retrying():
    from agents.agent1_analyst import stops_retrying
    from core.llm_client import OutputTruncatedError
    from core.spend_budget import BudgetExceeded
    from core.test_case_rules import DraftRejected
    assert stops_retrying(OutputTruncatedError("x")) and stops_retrying(DraftRejected("x"))
    assert not stops_retrying(ValueError("x")) and not stops_retrying(ConnectionError("x"))
    assert not stops_retrying(BudgetExceeded("day", "x"))
    assert issubclass(DraftRejected, ValueError), "callers catching ValueError still do"


class _Tracker:
    def __init__(self):
        self.removed, self.comments = [], []

    def remove_label(self, key, label):
        self.removed.append((key, label))

    def add_comment(self, key, body):
        self.comments.append((key, body))


def test_hand_back_removes_the_trigger_and_says_why():
    from agents.agent1_analyst import STOPPED, hand_back
    from core.llm_client import OutputTruncatedError
    t = _Tracker()
    err = OutputTruncatedError("structured:Draft: output truncated at the 9-token cap. "
                               "To re-run with more room: raise it")
    removed = hand_back(t, "AB-1", err, {"selection": {"required_labels": ["go"]}})
    assert removed == ["go"] and t.removed == [("AB-1", "go")]
    (key, body), = t.comments
    assert key == "AB-1" and body.startswith(STOPPED)
    assert "output truncated at the 9-token cap" in body and "To re-run" not in body
    assert "Add `go` again to retry" in body


def test_the_scan_hands_back_only_such_failures_and_never_in_a_dry_run():
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert "if stops_retrying(e) and not args.dry_run:" in src


def test_a_draft_broken_twice_raises_draft_rejected(monkeypatch):
    from agents import agent1_analyst
    from core.test_case_rules import DraftRejected
    monkeypatch.setattr("core.test_case_rules.load_persistent_pages", lambda: {})
    bad = TestCaseList(story_summary="s", test_cases=[_tc("A", "continues the same session")])

    class LLM:
        def invoke_structured(self, **kw):
            return bad
    with pytest.raises(DraftRejected):
        agent1_analyst._draft_test_cases(LLM(), "PROMPT")


# ── a partial set is handed back; the impact-aware draft has room to answer ───

def test_a_partial_set_is_handed_back_with_what_to_do():
    from agents.agent1_analyst import NEEDS_A_PERSON_WHY, STOPPED, hand_back

    class T:
        def __init__(self):
            self.removed, self.comments = [], []

        def remove_label(self, k, label):
            self.removed.append(label)

        def add_comment(self, k, body):
            self.comments.append(body)
    t = T()
    why = NEEDS_A_PERSON_WHY["partial_test_cases"].format(n=1)
    assert hand_back(t, "AB-1", why, {"selection": {"required_labels": ["go"]}}) == ["go"]
    (body,) = t.comments
    assert body.startswith(STOPPED) and "take a place another story waits for" in body
    assert "1 test case(s) are linked" in body and "Add `go` again to retry" in body
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    # R1 (14 Nov 2026): a story not ready is handed back the same way.
    assert 'if result.get("status") in (_NEEDS_A_PERSON | _NOT_READY) and not args.dry_run:' in src


def test_the_budget_grows_with_the_approved_cases():
    from agents.agent1_impact import BASE_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS, output_budget
    assert output_budget(0) == BASE_OUTPUT_TOKENS
    assert output_budget(7) > 2 * BASE_OUTPUT_TOKENS > output_budget(1)
    assert output_budget(100) == MAX_OUTPUT_TOKENS
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert "max_output_tokens=output_budget(len(impacted))" in src


def test_an_empty_truncated_answer_is_named_as_reasoning():
    from core.llm_client import truncation_evidence
    lines = truncation_evidence("", {"output_token_details": {"reasoning": 12288}})
    assert "the answer never began" in lines[0] and "12,288 tokens" in lines[1]
    assert "not a loop" in truncation_evidence(None)[1]
