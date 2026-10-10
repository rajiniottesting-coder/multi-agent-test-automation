"""End-to-end proof that the pipeline runs on a NON-Jira tracker.

The Protocol and signature tests prove the CONTRACT is right. These run the
agents' actual `run()` functions against a tracker that has no JQL, no issue
types and completely different internals - which is the only way to prove the
whole flow works, not just that the method names line up.

Covers the four operations a client cares about:
    scan stories -> write test cases -> read test cases -> write comments
plus the label state machine that drives the pipeline.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pathlib import Path as _P

_PROJ_ROOT = _P(__file__).resolve().parents[2]

from core.schemas import (CodePlan, FilePlan, JiraCommentDraft,
                            TestCase, TestCaseList, TestStep)

# pytest tries to COLLECT any class named Test*; these are Pydantic schemas,
# not test classes. Tell it to leave them alone.
TestCase.__test__ = False
TestCaseList.__test__ = False
TestStep.__test__ = False
from integrations.tracker import Tracker


class MemoryTracker:
    """A tracker backed by dicts. Deliberately NOT Jira-shaped."""

    project_key = "ACME"

    def __init__(self):
        self.stories = {"ACME-1": {"key": "ACME-1", "summary": "User can log in",
                                   "description": "As a user...",
                                   "labels": ["ai-ready"], "components": ["Login"]}}
        self.test_cases: dict = {}
        self.links: dict = {}
        self.impacts: dict = {}
        self.comments: dict = {}
        self._n = 0

    def get_story(self, issue_key): return dict(self.stories[issue_key])

    def find_stories_to_process(self, selection_config, max_results=5,
                                sprint_override=None):
        req = set(selection_config.get("required_labels") or [])
        exc = set(selection_config.get("excluded_labels") or [])
        return [{"key": k, "summary": s["summary"]}
                for k, s in self.stories.items()
                if req <= set(s["labels"]) and not (exc & set(s["labels"]))][:max_results]

    def get_parent_story_key(self, issue_key):
        for story, tcs in self.links.items():
            if issue_key in tcs:
                return story
        return None

    def create_test_case(self, test_case, parent_story_key):
        self._n += 1
        key = f"ACME-T{self._n}"
        self.test_cases[key] = {"key": key,
                                "summary": getattr(test_case, "title", "tc"),
                                "description": "steps"}
        self.links.setdefault(parent_story_key, []).append(key)
        return MagicMock(key=key)

    def get_linked_test_cases(self, story_key):
        return [self.test_cases[k] for k in self.links.get(story_key, [])]

    def count_linked_test_cases(self, story_key):
        return len(self.links.get(story_key, []))

    # Agent 0 operations: impact links live apart from ownership links.
    def get_all_test_cases(self):
        owner = {tc: story for story, tcs in self.links.items() for tc in tcs}
        return [dict(tc, owner=owner.get(k)) for k, tc in sorted(self.test_cases.items())]

    def get_impacted_test_cases(self, story_key, include_retired=False):
        out = [self.test_cases[k] for k in self.impacts.get(story_key, [])
               if k in self.test_cases]
        return [dict(tc, retired=False) for tc in out] if include_retired else out

    def create_subtask(self, parent_key, summary, description):
        self._n += 1
        key = f"ACME-S{self._n}"
        self.stories[key] = {"key": key, "summary": summary, "description": description,
                             "labels": [], "status": "To Do", "parent": parent_key}
        return key

    def get_subtasks(self, parent_key):
        return [{"key": k, "summary": v["summary"], "status": v["status"],
                 "description": v["description"]}
                for k, v in self.stories.items() if v.get("parent") == parent_key]

    def set_description(self, issue_key, description):
        self.stories[issue_key]["description"] = description

    def update_test_case(self, issue_key, test_case):
        self.test_cases[issue_key]["summary"] = getattr(test_case, "title", "tc")

    def link_issues(self, from_key, to_key, kind):
        table = self.links if kind == "owns" else self.impacts
        if to_key not in table.setdefault(from_key, []):
            table[from_key].append(to_key)

    def unlink_issues(self, from_key, to_key, kind):
        table = self.links if kind == "owns" else self.impacts
        if to_key in table.get(from_key, []):
            table[from_key].remove(to_key)

    def create_story(self, summary, description, components, labels):
        self._n += 1
        key = f"ACME-{100 + self._n}"
        self.stories[key] = {"key": key, "summary": summary, "description": description,
                             "labels": list(labels), "components": list(components)}
        return key

    def add_label(self, issue_key, label):
        self.stories[issue_key]["labels"].append(label)

    def remove_label(self, issue_key, label):
        if label in self.stories[issue_key]["labels"]:
            self.stories[issue_key]["labels"].remove(label)

    def add_comment(self, issue_key, body):
        self.comments.setdefault(issue_key, []).append(body)
        return f"memory://{issue_key}"

    def get_comments(self, issue_key): return self.comments.get(issue_key, [])

    def transition_status(self, issue_key, status):
        """Board column. This tracker has no workflow rules, so it always
        succeeds - proving the pipeline works on a tracker with a completely
        different status model."""
        self.stories[issue_key]["status"] = status
        return True


@pytest.fixture
def tracker(monkeypatch):
    for var in ("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "OPENAI_API_KEY",
                "OPENAI_API_BASE", "GITHUB_TOKEN", "GITHUB_REPO"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "ACME")
    return MemoryTracker()


def _tc(title):
    return TestCase(title=title, description="d", priority="High",
                    test_type="Positive", preconditions=["p"],
                    steps=[TestStep(step_number=1, action="a", expected_result="e")],
                    expected_outcome="ok", test_data=None)


def test_memory_tracker_satisfies_the_protocol(tracker):
    assert isinstance(tracker, Tracker)


def test_agent1_writes_test_cases_to_a_non_jira_tracker(tracker):
    """SCAN story -> WRITE test cases -> move state marker."""
    import agents.agent1_analyst as a1
    drafted = TestCaseList(story_summary="Login",
                           test_cases=[_tc("[Positive] Login"), _tc("[Negative] Bad password")])
    with patch.object(a1, "get_tracker", return_value=tracker), \
         patch.object(a1, "LLMClient") as LLM:
        LLM.return_value.invoke_structured.return_value = drafted
        result = a1.run("ACME-1")

    assert result["status"] == "tests_drafted"
    assert len(tracker.test_cases) == 2                  # WRITE worked
    assert "ai-processed" in tracker.stories["ACME-1"]["labels"]   # state moved
    assert "ai-ready" not in tracker.stories["ACME-1"]["labels"]   # trigger consumed
    assert tracker.comments["ACME-1"]                     # ledger comment posted


def test_agent2_reads_test_cases_and_marks_coded(tracker):
    """READ test cases -> generate -> move state marker."""
    import agents.agent2_coder as a2
    tracker.test_cases = {"ACME-T1": {"key": "ACME-T1", "summary": "Login",
                                      "description": "steps"}}
    tracker.links = {"ACME-1": ["ACME-T1"]}
    tracker.stories["ACME-1"]["labels"] = ["ai-processed", "human-approved"]

    plan = CodePlan(feature_name="login", branch_name="auto/ACME-1-login",
                    pr_title="t", pr_body="b", notes="n",
                    files_to_create=[FilePlan(file_path="features/login_acme.feature",
                                              file_type="feature", purpose="p",
                                              is_new_file=True)])
    gh = MagicMock()
    gh.find_open_pr_for_story.return_value = None
    gh.branch_exists.return_value = False
    gh.open_pull_request.return_value = "https://example/pull/1"

    with patch.object(a2, "get_tracker", return_value=tracker), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient") as LLM, \
         patch.object(a2, "_validate_generated_files"), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g):
        LLM.return_value.invoke_structured.return_value = plan
        LLM.return_value.invoke_text.return_value = (
            "Feature: Login\n\n  Scenario: Login\n    Given I am on the login page\n")
        result = a2.run("ACME-1")

    assert result["status"] == "pr_opened"
    assert "ai-coded" in tracker.stories["ACME-1"]["labels"]


def test_agent2_run_passes_the_repo_host_to_existing_page_object_lookup(tracker):
    """Regression: run() assigned `gh` only AFTER the Stage-2 block that uses
    it, so `gh` was an unbound local there. The UnboundLocalError was caught
    by the block's own `except Exception` and logged at DEBUG, and the
    existing-page-object context never reached a single prompt."""
    import agents.agent2_coder as a2
    tracker.test_cases = {"ACME-T1": {"key": "ACME-T1", "summary": "Login",
                                      "description": "steps"}}
    tracker.links = {"ACME-1": ["ACME-T1"]}
    tracker.stories["ACME-1"]["labels"] = ["ai-processed", "human-approved"]
    plan = CodePlan(feature_name="login", branch_name="auto/ACME-1-login",
                    pr_title="t", pr_body="b", notes="n",
                    files_to_create=[FilePlan(file_path="features/login_acme.feature",
                                              file_type="feature", purpose="p",
                                              is_new_file=True)])
    gh = MagicMock()
    gh.find_open_pr_for_story.return_value = None
    gh.branch_exists.return_value = False
    gh.open_pull_request.return_value = "https://example/pull/1"

    with patch.object(a2, "get_tracker", return_value=tracker), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient") as LLM, \
         patch.object(a2, "_validate_generated_files"), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_existing_page_objects_on_main", return_value=[]) as lookup:
        LLM.return_value.invoke_structured.return_value = plan
        LLM.return_value.invoke_text.return_value = (
            "Feature: Login\n\n  Scenario: Login\n    Given I am on the login page\n")
        a2.run("ACME-1")

    lookup.assert_called_once()
    assert lookup.call_args.args[0] is gh


def test_agent5_writes_the_run_report_to_a_non_jira_tracker(tracker, tmp_path):
    """READ junit.xml -> WRITE comment -> move state marker."""
    import agents.agent5_reporter as a5
    (tmp_path / "junit.xml").write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="p" tests="2" '
        'failures="1" errors="0" skipped="0" time="2.0">'
        '<testcase classname="c" name="ok" time="1.0"/>'
        '<testcase classname="c" name="bad" time="1.0">'
        '<failure message="AssertionError">boom</failure></testcase>'
        '</testsuite></testsuites>')

    with patch.object(a5, "get_tracker", return_value=tracker), \
         patch.object(a5, "LLMClient") as LLM, \
         patch("integrations.github_client.GitHubClient"):
        LLM.return_value.invoke_structured.return_value = JiraCommentDraft(
            title="Run summary", body_markdown="1 of 2 scenarios passed.")
        result = a5.run(story_key="ACME-1", reports_dir=Path(tmp_path),
                        dry_run=False, cli_pr=None)

    assert result["status"] == "comment_posted"
    assert any("scenarios passed" in c for c in tracker.comments["ACME-1"])
    assert "tests-run" in tracker.stories["ACME-1"]["labels"]


# ── Full pipeline on a fake tracker AND a fake repo host ─────

class SourceHub:
    """A code host that is NOT GitHub. Plain dicts, no PyGithub objects."""

    def __init__(self):
        self.branches, self.files, self.prs, self.pr_comments = set(), {}, {}, {}

    def create_branch(self, branch_name, from_branch="main"):
        self.branches.add(branch_name)
    def branch_exists(self, branch_name): return branch_name in self.branches
    def delete_branch(self, branch_name):
        self.branches.discard(branch_name); return True
    def create_or_update_file(self, path, content, commit_message, branch):
        self.files[(branch, path)] = content
    def get_file_content(self, path, branch="main"):
        return self.files.get((branch, path), "")
    def list_files_in_directory(self, path, branch="main"): return []
    def open_pull_request(self, title, body, head_branch, base_branch="main"):
        n = len(self.prs) + 1
        self.prs[n] = {"number": n, "head_ref": head_branch, "head_sha": "sha1",
                       "url": f"hub://mr/{n}", "title": title}
        return self.prs[n]["url"]
    def find_open_pr_for_story(self, story_id, branch_prefix="auto/"):
        want = f"{branch_prefix}{story_id}-"
        return next((p for p in self.prs.values()
                     if p["head_ref"].startswith(want)), None)
    def list_open_prs(self, branch_prefix=""):
        return [p for p in self.prs.values() if p["head_ref"].startswith(branch_prefix)]
    def get_pr_metadata(self, pr_number):
        p = self.prs[pr_number]
        return {"number": p["number"], "title": p["title"], "body": "b",
                "head_branch": p["head_ref"], "base_branch": "main",
                "state": "open", "author": "bot", "url": p["url"]}
    def get_pr_changed_files(self, pr_number):
        return [{"filename": "features/x.feature", "status": "added",
                 "additions": 5, "deletions": 0, "patch": "+Scenario"}]
    def reopen_pull_request(self, pr_number): pass
    def post_pr_comment(self, pr_number, body):
        self.pr_comments.setdefault(pr_number, []).append(body)
    def get_pr_comments(self, pr_number): return self.pr_comments.get(pr_number, [])
    def get_workflow_runs(self, workflow_file, branch, limit=20): return []


def test_full_pipeline_runs_on_neither_jira_nor_github(tracker, tmp_path):
    """Agents 1 -> 2 -> 3 -> 5 against a fake tracker AND a fake host.

    This is the claim that matters: the whole flow works when NEITHER provider
    is the one it was built against.
    """
    from integrations.repo_host import RepoHost
    import agents.agent1_analyst as a1
    import agents.agent2_coder as a2
    import agents.agent3_reviewer as a3
    import agents.agent5_reporter as a5
    from core.schemas import ReviewReport

    hub = SourceHub()
    assert isinstance(hub, RepoHost)

    # Agent 1 — draft test cases onto the board
    with patch.object(a1, "get_tracker", return_value=tracker), \
         patch.object(a1, "LLMClient") as LLM:
        LLM.return_value.invoke_structured.return_value = TestCaseList(
            story_summary="Login", test_cases=[_tc("[Positive] Login"),
                                               _tc("[Negative] Bad password")])
        assert a1.run("ACME-1")["status"] == "tests_drafted"
    assert len(tracker.test_cases) == 2
    tracker.add_label("ACME-1", "human-approved")          # the human gate

    # Agent 2 — read them back, generate, open a PR on the fake host
    plan = CodePlan(feature_name="login", branch_name="auto/ACME-1-login",
                    pr_title="t", pr_body="b", notes="n",
                    files_to_create=[FilePlan(file_path="features/login_acme.feature",
                                              file_type="feature", purpose="p",
                                              is_new_file=True)])
    with patch.object(a2, "get_tracker", return_value=tracker), \
         patch.object(a2, "get_repo_host", return_value=hub), \
         patch.object(a2, "LLMClient") as LLM, \
         patch.object(a2, "_validate_generated_files"), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g):
        LLM.return_value.invoke_structured.return_value = plan
        LLM.return_value.invoke_text.return_value = (
            "Feature: Login\n\n  Scenario: Login\n    Given I am on the login page\n")
        r2 = a2.run("ACME-1")
    assert r2["status"] == "pr_opened"
    assert r2["pr_url"].startswith("hub://")               # NOT a github.com URL
    assert ("auto/ACME-1-login", "features/login_acme.feature") in hub.files
    assert "ai-coded" in tracker.stories["ACME-1"]["labels"]

    # Agent 3 — review the PR on the fake host
    with patch.object(a3, "get_repo_host", return_value=hub), \
         patch.object(a3, "LLMClient") as LLM:
        LLM.return_value.invoke_structured.return_value = ReviewReport(
            pr_number=1, overall_verdict="approve", summary="ok", issues=[],
            style_compliance=True, type_hints_present=True,
            no_hardcoded_waits=True, pom_compliant=True, coverage_complete=True)
        assert a3.run(pr_number=1)["status"] == "review_posted"
    assert hub.pr_comments[1]                              # review landed on the host

    # Agent 5 — report results back to the board
    (tmp_path / "junit.xml").write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="p" tests="2" failures="0" '
        'errors="0" skipped="0" time="3.0"><testcase classname="c" name="a" time="1"/>'
        '<testcase classname="c" name="b" time="2"/></testsuite></testsuites>')
    with patch.object(a5, "get_tracker", return_value=tracker), \
         patch.object(a5, "LLMClient") as LLM, \
         patch("integrations.github_client.GitHubClient"):
        LLM.return_value.invoke_structured.return_value = JiraCommentDraft(
            title="Run", body_markdown="All 2 scenarios passed.")
        assert a5.run(story_key="ACME-1", reports_dir=Path(tmp_path),
                      dry_run=False, cli_pr=None)["status"] == "comment_posted"

    # end state: full label machine walked, cost table posted
    assert tracker.stories["ACME-1"]["labels"] == [
        "ai-processed", "human-approved", "ai-coded", "tests-run"]
    assert any("End-to-end LLM usage" in c for c in tracker.comments["ACME-1"])
    # the card followed the work across the board, not just the labels
    assert tracker.stories["ACME-1"]["status"] == "In Review"


def test_repo_host_dict_keys_are_exactly_as_documented():
    """A missing key is a KeyError inside an agent, not a soft failure.
    agent3_reviewer reads `head_branch`; agent2 reads `head_ref`."""
    hub = SourceHub()
    hub.open_pull_request("t", "b", "auto/S-1-x")
    assert set(hub.get_pr_metadata(1)) == {
        "number", "title", "body", "head_branch", "base_branch",
        "state", "author", "url"}
    assert set(hub.find_open_pr_for_story("S-1")) == {
        "number", "head_ref", "head_sha", "url", "title"}


# =========================================================================
# THE BRANCH MUST NAME THE STORY, NOT ONE OF ITS TEST CASES
#
# A story about a shopping session produced the branch
# `auto/<TESTCASE>-shopping-session` while the story itself was a different
# key. Three places then disagreed about who owned the work: the branch said
# one issue, the pull-request body another, the board a third.
#
# Agent 5 reads the BRANCH to decide where to post the run cost, so the usage
# comment landed on a test case and the story's own page had no record of what
# it cost. Nothing failed; the number was simply somewhere nobody looks.
#
# The plan prompt said `auto/<jira-key>-<feature>` without saying WHICH key,
# and the test cases appear first in the model's input.
# =========================================================================

def test_a_branch_named_after_a_test_case_is_corrected_to_the_story():
    """Corrected, not rejected.

    The model picked a reasonable key from an ambiguous instruction. Failing
    the story over a name would throw away a generation that is otherwise
    fine, and the repair loop cannot fix a branch name - it regenerates files.
    """
    from config import assert_valid_branch_for_pipeline

    story = "PROJ-100"
    branch = "auto/PROJ-207-shopping-session"        # a test case of that story

    key = assert_valid_branch_for_pipeline(branch)
    assert key != story, "the sample must actually be wrong, or this proves nothing"

    corrected = branch.replace(key, story, 1)
    assert corrected == "auto/PROJ-100-shopping-session"
    assert assert_valid_branch_for_pipeline(corrected) == story


def test_a_branch_already_naming_the_story_is_left_alone():
    """Break the thing the guard guards. Rewriting a correct branch would
    churn every story for nothing."""
    from config import assert_valid_branch_for_pipeline

    story = "PROJ-100"
    branch = "auto/PROJ-100-shopping-session"
    assert assert_valid_branch_for_pipeline(branch) == story


def test_the_correction_is_wired_into_the_run():
    """The comparison has to happen where story_id is in scope. A helper that
    nothing calls is the shape this project has been bitten by repeatedly."""
    source = (_PROJ_ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    body = " ".join(source.split())

    assert "branch_key = assert_valid_branch_for_pipeline(" in body, (
        "the extracted key is discarded again - nothing can compare it"
    )
    assert "if branch_key != story_id:" in body, (
        "nothing compares the branch key against the story being processed"
    )


def test_the_plan_prompt_says_which_key():
    """The durable half. Correcting after the fact works; not needing to is
    better, and the prompt is where the ambiguity was."""
    prompt = (_PROJ_ROOT / "prompts" / "agent2_coder_plan.md").read_text(
        encoding="utf-8")
    lowered = " ".join(prompt.split()).lower()

    assert "story" in lowered and "branch_name" in prompt, "name the field"
    # Strip markdown emphasis before matching. The prompt writes "**not** any
    # of the test-case keys", and a literal match failed on the asterisks -
    # a guard that reads prose has to read it the way a reader does.
    import re
    plain = re.sub(r"[*_`]", "", lowered)

    assert "not any of the test-case keys" in plain, (
        "the prompt must say which key explicitly - 'jira-key' alone is what "
        "let the model reach for the test cases, which appear first in its input"
    )