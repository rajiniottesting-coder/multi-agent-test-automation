"""The small backlog found while validating (November 2026).

Each test pins one fix: a feature file repaired from what it is, one bot rule
for review comments, the jira library's false link-type warning, Gherkin tags
as free markers. Generic names only.
"""
import logging
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]

FEATURE = """Feature: Help

  # JIRA: AB-2 (hash: 1234abcd) owner: AB-1
  @smoke
  Scenario: Reading help
    Given I am on the help page
    Then the help should be shown
"""


# ── a feature file is repaired from what it is ──────────────────────────

@pytest.mark.parametrize("path, content, shown", [
    ("features/help.feature", FEATURE, True),
    ("features/help.feature", "", False),
    ("features/help.feature", "garbage", False),
    ("tests/step_defs/test_help.py", "def broken(:\n", False),
])
def test_which_previous_attempt_a_repair_is_shown(path, content, shown):
    from agents.agent2_coder import _previous_attempt_worth_showing
    assert _previous_attempt_worth_showing(path, content) is shown


def test_a_feature_repair_is_shown_the_file_and_told_to_keep_its_markers():
    import agents.agent2_coder as a2
    from core.app_context import AppContext
    from core.schemas import CodePlan, FilePlan
    seen = {}

    class LLM:
        def invoke_text(self, system_prompt, user_prompt, **kw):
            seen["prompt"] = user_prompt
            return "```gherkin\n" + FEATURE + "```"

    fp = FilePlan(file_path="features/help.feature", file_type="feature", is_new_file=True,
                  purpose="p", related_test_cases=["AB-2"])
    plan = CodePlan(feature_name="f", branch_name="auto/AB-1-help", pr_title="t", pr_body="",
                    files_to_create=[fp])
    ctx = AppContext.load()
    a2.generate_file_content(LLM(), fp, plan, [{"key": "AB-2", "summary": "s", "description": "d"}],
                             ctx.load_reference_files(), "{}", ctx, previous_attempt=FEATURE,
                             validator_feedback=["Step coverage error in 'tests/step_defs/test_help.py': x"])
    prompt = seen["prompt"]
    assert "Your previous attempt" in prompt and "# JIRA: AB-2 (hash: 1234abcd)" in prompt
    assert "`# JIRA:` marker line" in prompt


def test_the_repair_prompt_uses_the_rule_for_every_file_type():
    src = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    assert "_previous_attempt_worth_showing(file_plan.file_path," in src
    assert "if previous_attempt and _looks_like_useful_python(previous_attempt):" not in src


# ── one bot rule for review comments ────────────────────────────────────

def test_a_bots_first_comment_is_left_out_like_its_replies(monkeypatch):
    from integrations.github_client import GitHubClient
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    gh = GitHubClient()

    def c(cid, reply_to=None, login="person", kind="User"):
        return NS(id=cid, in_reply_to_id=reply_to, path="pages/a_page.py", line=3,
                  original_line=3, body=f"b{cid}", user=NS(login=login, type=kind),
                  pull_request_review_id=7, author_association="OWNER")
    pull = NS(get_review_comments=lambda: [c(1), c(2, None, "reviewer[bot]", "Bot"),
                                           c(3, 1), c(4, 1, "agent[bot]", "Bot")])
    gh._repo = NS(get_pull=lambda n: pull)
    assert [g["id"] for g in gh.get_review_comments(5)] == [1, 3]


# ── the jira library's false warning on every link ──────────────────────

def test_the_false_link_type_warning_is_dropped_and_the_link_made(caplog):
    from integrations.jira_client import JiraClient
    lib_log = logging.getLogger("jira.test")
    made = []

    def create_issue_link(type, inwardIssue, outwardIssue):
        lib_log.warning("Warning: Specified issue link type is not present in the list of link types")
        lib_log.warning("something else")
        made.append((type, inwardIssue, outwardIssue))
    client = JiraClient.__new__(JiraClient)
    client._client = NS(log=lib_log, create_issue_link=create_issue_link)
    client._link_type = lambda kind: {"name": "Relates", "from_field": "outwardIssue"}
    with caplog.at_level(logging.WARNING):
        client._create_link("AB-1", "AB-2", "owns")
    assert made == [("Relates", "AB-2", "AB-1")]
    messages = [r.getMessage() for r in caplog.records]
    assert "something else" in messages
    assert not any("link type is not present" in m for m in messages)
    assert not lib_log.filters, "the filter is removed after the call"


# ── the rest ────────────────────────────────────────────────────────────

def test_a_gherkin_tag_is_a_free_marker():
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "ignore::pytest.PytestUnknownMarkWarning" in ini
    assert "--strict-markers" not in ini.split("addopts", 1)[-1].split("\n", 3)[0]


def test_get_property_says_it_returns_plain_json():
    import inspect
    from integrations.jira_client import JiraClient
    ann = inspect.signature(JiraClient.get_property).return_annotation
    assert "dict" in str(ann) and "None" in str(ann)


def test_the_duplicate_step_check_has_no_unreachable_half():
    import inspect
    from validators.gherkin_analyzer import validate_no_duplicate_step_definitions as v
    src = inspect.getsource(v)
    assert "UNREACHABLE" not in src and src.count("return errors") == 1
