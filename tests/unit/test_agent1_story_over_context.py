"""Agent 1 is told that the story outranks the application context.

The context notes describe the application as it is - they are updated only
after a change is deployed (the context-update PR). A change story therefore
contradicts them by design. In validation story A3 the model followed the
story, but only because the task wording pointed that way; this pins the
rule in both Agent 1 prompts. No application names.
"""
from pathlib import Path

import pytest

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


@pytest.mark.parametrize("name", ["agent1_analyst.md", "agent1_impact_aware.md"])
def test_both_agent1_prompts_say_the_story_wins(name):
    text = (PROMPTS / name).read_text(encoding="utf-8")
    assert "describes the application BEFORE this story" in text
    assert "the story is the intended behaviour" in text
    # placeholders the loader fills are untouched
    for ph in ("{app_context}", "{story_text}"):
        assert ph in text
