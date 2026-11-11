"""Agent 5 end to end: the story's own tests, rendered in the tracker's markup.

Every existing scoping test handed _scope_to_story a report that already had
a PR number. In CI the number only arrives from the event payload, which
gather_ci_context read AFTER scoping - so the scope never ran and each story
was told "All N tests passed" for the whole session. These tests drive run()
the way CI does: the PR number comes from GITHUB_EVENT_PATH.

The comment is Markdown; Jira's REST v2 renders wiki markup, where a table
separator becomes a row of dashes. The Jira adapter converts; a tracker
without that capability receives the Markdown as written.

Generic module names only; no network, no model.
"""
import json
from unittest.mock import MagicMock

import pytest

import agents.agent5_reporter as a5
from core.schemas import JiraCommentDraft
from integrations.jira_markup import markdown_to_jira_wiki

JUNIT = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="4" failures="0" errors="0" skipped="0" time="4.0">
<testcase classname="tests.step_defs.test_story_module" name="test_a" time="1.0"/>
<testcase classname="tests.step_defs.test_story_module" name="test_b" time="1.0"/>
<testcase classname="tests.step_defs.test_other_module" name="test_c" time="1.0"/>
<testcase classname="tests.step_defs.test_other_module" name="test_d" time="1.0"/>
</testsuite></testsuites>"""


@pytest.fixture
def ci(tmp_path, monkeypatch):
    (tmp_path / "junit.xml").write_text(JUNIT, encoding="utf-8")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 9}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.delenv("PR_NUMBER", raising=False)
    llm = MagicMock()
    llm.invoke_structured.return_value = JiraCommentDraft(
        title="t", body_markdown="✅ **All tests passed**")
    monkeypatch.setattr(a5, "LLMClient", lambda *a, **k: llm)
    return tmp_path


def _pr_touches(monkeypatch, *paths):
    monkeypatch.setattr(a5, "get_repo_host", lambda: type("H", (), {
        "get_pr_changed_files": staticmethod(lambda n: [{"filename": p} for p in paths])})())


def test_the_pr_number_from_the_event_scopes_the_report(ci, monkeypatch, capsys):
    _pr_touches(monkeypatch, "tests/step_defs/test_story_module.py")
    result = a5.run("X-1", ci, dry_run=True)
    assert (result["total"], result["passed"]) == (2, 2), "only the story's own two tests"
    assert "Scope: all" not in capsys.readouterr().out


def test_an_unscoped_report_says_so(ci, monkeypatch, capsys):
    _pr_touches(monkeypatch, "pages/some_page.py")          # no step-def module
    result = a5.run("X-1", ci, dry_run=True)
    assert result["total"] == 4
    assert "Scope: all 4 tests in this run" in capsys.readouterr().out


def test_the_tracker_renders_the_comment_when_it_can(ci, monkeypatch):
    _pr_touches(monkeypatch, "tests/step_defs/test_story_module.py")
    tracker = MagicMock()
    tracker.get_comments.return_value = []
    tracker.render_markdown.side_effect = lambda md: "RENDERED:" + md
    monkeypatch.setattr(a5, "get_tracker", lambda: tracker)
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story", lambda *a, **k: True)
    a5.run("X-1", ci, dry_run=False)
    body = tracker.add_comment.call_args.args[1]
    assert body.startswith("RENDERED:")


def test_a_tracker_without_the_capability_gets_markdown(ci, monkeypatch):
    _pr_touches(monkeypatch, "tests/step_defs/test_story_module.py")

    class Plain:
        def __init__(self):
            self.posted = []

        def get_comments(self, key):
            return []

        def add_comment(self, key, body):
            self.posted.append(body)
            return "url"

        def add_label(self, key, label):
            pass

    tracker = Plain()
    monkeypatch.setattr(a5, "get_tracker", lambda: tracker)
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story", lambda *a, **k: True)
    a5.run("X-1", ci, dry_run=False)
    assert "**All tests passed**" in tracker.posted[0]


# ── the converter ────────────────────────────────────────────────────────────

def test_a_table_has_one_header_and_no_dash_row():
    md = "| A | B |\n|---|---|\n| 1 | **2** |"
    assert markdown_to_jira_wiki(md) == "||A||B||\n|1|*2*|"


def test_inline_markup():
    out = markdown_to_jira_wiki("**Run details:** see [the PR](https://x.example/pr/9) at `abc123`")
    assert out == "*Run details:* see [the PR|https://x.example/pr/9] at {{abc123}}"


def test_lists_headings_quotes_rules():
    md = "## Title\n- one\n  - two\n> note\n---"
    assert markdown_to_jira_wiki(md) == "h2. Title\n* one\n** two\nbq. note\n----"


def test_machine_markers_and_plain_text_are_untouched():
    text = '[LLM-USAGE] agent="Agent 1" calls=2\n[agent1:impact-draft] Revised 1'
    assert markdown_to_jira_wiki(text) == text


def test_code_fences_and_code_spans_are_not_rewritten():
    md = "```\n**x** | a |\n|---|\n```\nuse `**literal**`"
    # A code span shows its characters: wiki markup would read `**` inside
    # {{...}} as bold, so they are escaped (11 Nov 2026, a step pattern).
    assert markdown_to_jira_wiki(md) == "{code}\n**x** | a |\n|---|\n{code}\nuse {{\\*\\*literal\\*\\*}}"


def test_a_code_span_shows_a_step_pattern_exactly():
    out = markdown_to_jira_wiki('the step `Then I see "(?P<msg>[^"]*)"` and `a\\d+`')
    assert out == 'the step {{Then I see "(\\?P<msg>\\[\\^"\\]\\*)"}} and {{a&#92;d\\+}}'
    assert "!" not in out


def test_markdown_comments_reach_the_tracker_rendered():
    """Every Markdown notice goes through one helper that renders it."""
    from pathlib import Path as P
    from integrations.tracker import add_markdown_comment

    class T:
        posted = []

        def render_markdown(self, md):
            return "R:" + md

        def add_comment(self, key, body):
            self.posted.append(body)
            return "url"

    class Plain:
        posted = []

        def add_comment(self, key, body):
            self.posted.append(body)
            return "url"
    t, plain = T(), Plain()
    add_markdown_comment(t, "AB-1", "x `y`")
    add_markdown_comment(plain, "AB-1", "x `y`")
    assert t.posted == ["R:x `y`"] and plain.posted == ["x `y`"]
    for path in ["core/blocked.py", "agents/agent2_coder.py", "core/in_flight.py", "core/spend_budget.py",
                 "core/selection_notice.py", "agents/agent2_coverage.py",
                 "agents/agent1_analyst.py"]:
        assert "add_markdown_comment(" in P(path).read_text(encoding="utf-8"), path


def test_the_real_usage_table_converts_cleanly():
    from core.usage_ledger import format_e2e_section
    section = format_e2e_section({
        "entries": [{"agent": "Agent 1", "calls": 1, "input_tokens": 10, "output_tokens": 2,
                     "cost_usd": 0.1}],
        "agent_runs": 1, "total_calls": 1, "total_input_tokens": 10,
        "total_output_tokens": 2, "total_cost_usd": 0.1, "cost_complete": True})
    out = markdown_to_jira_wiki(section)
    assert "||Agent run||Calls||Input tokens||Output tokens||Cost (USD)||" in out
    assert "---|" not in out and "|---" not in out
