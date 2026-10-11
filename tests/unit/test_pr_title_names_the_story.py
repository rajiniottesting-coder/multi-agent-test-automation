"""A pull request title names the story it belongs to, never a test case.

Agent 2 already corrects a branch named after a test-case key. The title came
from the same ambiguous input and was not corrected, so a PR went out titled
after one of its test cases while its branch named the story.
"""
import os

import pytest

for v in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
          "JIRA_PROJECT_KEY", "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ.setdefault(v, "stub")

from agents.agent2_coder import title_for_story


@pytest.mark.parametrize("title,expected", [
    ("Automate the widget flow (ABC-23)", "Automate the widget flow (ABC-2)"),
    ("Automate the widget flow (ABC-1, ABC-23)", "Automate the widget flow (ABC-2)"),
    ("Automate the widget flow [ABC-5/ABC-6]", "Automate the widget flow (ABC-2)"),
    ("ABC-23: automate the widget flow", "automate the widget flow (ABC-2)"),
    ("Automate the widget flow (ABC-2)", "Automate the widget flow (ABC-2)"),
    ("Automate the widget flow", "Automate the widget flow (ABC-2)"),
    ("Automate ABC-2 widget flow", "Automate ABC-2 widget flow"),
])
def test_only_the_story_key_remains(title, expected):
    assert title_for_story(title, "ABC-2") == expected


def test_an_empty_title_becomes_the_story_key():
    assert title_for_story("", "ABC-2") == "ABC-2"
