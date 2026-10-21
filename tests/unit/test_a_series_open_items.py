"""
Open items from the A-series validation, closed together:

- Agent 0's model cost reaches the story's ledger, without Agent 1 later
  discarding it as a "previous run" (and a genuine new attempt still resets).
- The drift job can be started on demand (dispatch mode = drift) without the
  scan or reconcile running alongside it.
- A test case carries its story's components; a project that rejects them
  still gets the test case.

(reconcile.closed_scans is covered in test_impact_reconcile.py, and the
golden-rule prompt scan in test_committed_tree_resolves.py.)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

from core.schemas import TestCase, TestStep
from core.test_runtime import runs_app_tests
from core.usage_ledger import (
    IMPACT_ANALYST,
    RESET_MARKER,
    format_usage_comment,
    has_usage_comments,
)

for _cls in (TestCase, TestStep):
    _cls.__test__ = False

USAGE = {"llm_calls": 2, "input_tokens": 1000, "output_tokens": 100,
         "input_cost_usd": 0.01, "output_cost_usd": 0.002, "estimated_cost_usd": 0.012}


def _entry(agent):
    return format_usage_comment(agent, USAGE)


class FakeTracker:
    def __init__(self, comments=()):
        self.comments = list(comments)

    def get_comments(self, key):
        return list(self.comments)

    def add_comment(self, key, body):
        self.comments.append(body)


# ─────────────────────────────────────────────────────────────
# Item 4 - Agent 0 on the ledger
# ─────────────────────────────────────────────────────────────
class TestLedgerIgnoringAgents:
    def test_only_agent0_entries_do_not_count_as_costed(self):
        assert not has_usage_comments([_entry(IMPACT_ANALYST)], ignore_agents=(IMPACT_ANALYST,))

    def test_a_downstream_entry_still_counts(self):
        comments = [_entry(IMPACT_ANALYST), _entry("Agent 2 (Coder)")]
        assert has_usage_comments(comments, ignore_agents=(IMPACT_ANALYST,))

    def test_default_behaviour_is_unchanged(self):
        assert has_usage_comments([_entry(IMPACT_ANALYST)])
        assert not has_usage_comments([_entry("Agent 1 (Test Designer)"), RESET_MARKER])


class TestAgent0PostsItsUsage:
    def _post(self, tracker, usage=USAGE):
        import agents.agent0_impact as a0
        with patch("core.llm_client.log_usage_summary", return_value=dict(usage)), \
             patch("core.llm_client.reset_usage") as reset:
            a0._post_usage(tracker, "PROJ-1")
        return reset

    def test_a_fresh_story_gets_one_entry(self):
        t = FakeTracker()
        reset = self._post(t)
        assert len(t.comments) == 1 and f'agent="{IMPACT_ANALYST}"' in t.comments[0]
        reset.assert_called_once()                      # next story starts from zero

    def test_reanalysis_in_one_attempt_accumulates(self):
        t = FakeTracker([_entry(IMPACT_ANALYST)])
        self._post(t)
        assert not any(RESET_MARKER in c for c in t.comments)
        assert sum(IMPACT_ANALYST in c for c in t.comments) == 2

    def test_a_new_attempt_after_downstream_agents_resets_first(self):
        t = FakeTracker([_entry(IMPACT_ANALYST), _entry("Agent 1 (Test Designer)"),
                         _entry("Agent 2 (Coder)")])
        self._post(t)
        assert RESET_MARKER in t.comments[-2] and IMPACT_ANALYST in t.comments[-1]

    def test_no_model_call_posts_nothing(self):
        t = FakeTracker()
        self._post(t, dict(USAGE, llm_calls=0))
        assert t.comments == []

    def test_a_tracker_failure_never_fails_agent0(self):
        t = FakeTracker()
        t.get_comments = MagicMock(side_effect=RuntimeError("jira down"))
        self._post(t)                                    # no exception


def test_agent1_keeps_agent0s_entry_on_a_change_story(tmp_path, monkeypatch):
    """End to end in the sandbox: Agent 0's entry is on the story when Agent 1
    drafts it; Agent 1 must not post a reset that would drop it."""
    from tests.unit.test_agent2_impact import _hand_over_and_draft, world
    fake, jira, _root = world.__wrapped__(tmp_path, monkeypatch)
    fake.comments.setdefault("SBX-5", []).append(_entry(IMPACT_ANALYST))
    _hand_over_and_draft(jira, {"SBX-11": "approve"})
    bodies = jira.get_comments("SBX-5")
    assert not any(RESET_MARKER in b for b in bodies)
    assert any(IMPACT_ANALYST in b for b in bodies)


def test_agent1_still_resets_when_the_story_was_costed_downstream(tmp_path, monkeypatch):
    from tests.unit.test_agent2_impact import _hand_over_and_draft, world
    fake, jira, _root = world.__wrapped__(tmp_path, monkeypatch)
    fake.comments.setdefault("SBX-5", []).append(_entry("Agent 2 (Coder)"))
    _hand_over_and_draft(jira, {"SBX-11": "approve"})
    assert any(RESET_MARKER in b for b in jira.get_comments("SBX-5"))


# ─────────────────────────────────────────────────────────────
# Item 5 - drift on demand
# ─────────────────────────────────────────────────────────────
def _workflow():
    from config.paths import PROJECT_ROOT
    return yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "agent0_impact.yml")
                          .read_text(encoding="utf-8"))


def _runs(condition: str, event: str, schedule: str = "", mode: str = "") -> bool:
    """Evaluate a job's `if:` for one event (gate enabled). The expressions
    use only ==, !=, && and || over these names, so a direct translation is
    exact."""
    expr = (condition
            .replace("needs.gate.outputs.enabled", "'true'")
            .replace("github.event_name", repr(event))
            .replace("github.event.schedule", repr(schedule))
            .replace("github.event.inputs.mode", repr(mode))
            .replace("&&", " and ").replace("||", " or "))
    return bool(eval(expr))


@pytest.mark.parametrize("event, schedule, mode, expected", [
    ("schedule", "15 5 * * 1-5", "", {"scan", "reconcile"}),
    ("schedule", "45 1 * * *", "", {"drift"}),
    ("workflow_dispatch", "", "", {"scan", "reconcile"}),          # no mode: as before
    ("workflow_dispatch", "", "scan", {"scan", "reconcile"}),
    ("workflow_dispatch", "", "drift", {"drift"}),
    ("pull_request", "", "", {"code-change"}),
])
def test_each_trigger_runs_exactly_its_jobs(event, schedule, mode, expected):
    jobs = _workflow()["jobs"]
    ran = {name for name, job in jobs.items()
           if name != "gate" and _runs(job.get("if", "false"), event, schedule, mode)}
    assert ran == expected


def test_dispatch_offers_the_drift_mode():
    on = _workflow()[True]                       # YAML 1.1 reads the key `on` as True
    mode = on["workflow_dispatch"]["inputs"]["mode"]
    assert mode["options"] == ["scan", "drift"] and mode["default"] == "scan"


# ─────────────────────────────────────────────────────────────
# Item 6 - the story's components on its test cases
# ─────────────────────────────────────────────────────────────
def _tc():
    return TestCase(title="Valid login", description="d", priority="High", test_type="Positive",
                    preconditions=[], steps=[TestStep(step_number=1, action="a",
                                                      expected_result="b")],
                    expected_outcome="ok", test_data=None)


def _client(create_issue):
    from integrations.jira_client import JiraClient
    c = JiraClient.__new__(JiraClient)
    c.project_key = "PROJ"
    c._client = SimpleNamespace(create_issue=create_issue)
    c._link_to_story = MagicMock()
    return c


def test_components_are_sent_with_the_test_case():
    seen = []
    c = _client(lambda fields: seen.append(fields) or SimpleNamespace(key="PROJ-9"))
    assert c.create_test_case(_tc(), "PROJ-1", components=["ModuleA"]).key == "PROJ-9"
    assert seen[0]["components"] == [{"name": "ModuleA"}]


def test_no_components_sends_no_field():
    seen = []
    c = _client(lambda fields: seen.append(fields) or SimpleNamespace(key="PROJ-9"))
    c.create_test_case(_tc(), "PROJ-1")
    assert "components" not in seen[0]


def test_a_rejected_component_still_creates_the_test_case():
    calls = []

    def create(fields):
        calls.append(dict(fields))
        if "components" in fields:
            raise RuntimeError('400 {"errors":{"components":"Component name \'X\' is not valid"}}')
        return SimpleNamespace(key="PROJ-9")

    c = _client(create)
    assert c.create_test_case(_tc(), "PROJ-1", components=["X"]).key == "PROJ-9"
    assert len(calls) == 2 and "components" not in calls[1]
    c._link_to_story.assert_called_once_with("PROJ-9", "PROJ-1")


def test_any_other_failure_still_surfaces():
    def create(fields):
        raise RuntimeError("401 Unauthorized")
    with pytest.raises(RuntimeError, match="401"):
        _client(create).create_test_case(_tc(), "PROJ-1", components=["ModuleA"])


def test_agent1_test_cases_inherit_the_story_components(tmp_path, monkeypatch):
    """Sandbox run: the change story carries components ["Login"]; its new
    test case is created with them."""
    from tests.unit.test_agent2_impact import _hand_over_and_draft, world
    fake, jira, _root = world.__wrapped__(tmp_path, monkeypatch)
    before = set(fake.issues)
    _hand_over_and_draft(jira, {"SBX-11": "approve"})
    new = [k for k in fake.issues if k not in before and fake.issues[k]["issuetype"] == "Test Case"]
    assert new and all(fake.issues[k]["components"] == ["Login"] for k in new)


# ─────────────────────────────────────────────────────────────
# Item 7 - a prompts/docs-only pull request runs no browser
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("paths, expected", [
    (["prompts/app_context/module.md"], False),                     # notes-only context update
    (["prompts/agent2_coder_generate.md", "docs/GUIDE.md", "README.md"], False),
    (["prompts/app_context/module.md", "app_inventory/app.json"], True),   # inventory is runtime
    (["features/sample.feature"], True),
    (["tests/step_defs/test_sample.py"], True),
    (["pages/sample_page.py"], True),
    (["config/config.yaml"], True),
    (["tests/conftest.py"], True),
    (["requirements.txt"], True),
    (["some/new/kind_of_file.bin"], True),                       # unknown: run
    ([], True), (["", "  "], True),                              # nothing listed: fail open
])
def test_runtime_rule(paths, expected):
    assert runs_app_tests(paths) is expected


def _agent4():
    from config.paths import PROJECT_ROOT
    return yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "agent4_runner.yml")
                          .read_text(encoding="utf-8"))


def _detector_script():
    step = next(s for s in _agent4()["jobs"]["test"]["steps"] if s.get("id") == "pr_changes")
    assert step["if"] == "github.event_name == 'pull_request'"
    assert step.get("continue-on-error") is True
    return step["run"]


def _run_detector(tmp_path, gh_body: str) -> str:
    """Execute the workflow's own step with a fake `gh` on PATH."""
    import os
    import subprocess

    from config.paths import PROJECT_ROOT
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\n" + gh_body)
    (bin_dir / "gh").chmod(0o755)
    out = tmp_path / "out"
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", GITHUB_OUTPUT=str(out),
               GH_TOKEN="x", PR_NUMBER="1", REPO="o/r")
    subprocess.run(["bash", "-e", "-c", _detector_script()], cwd=PROJECT_ROOT, env=env,
                   check=True, capture_output=True, text=True)
    return out.read_text()


@pytest.mark.parametrize("gh_body, expected", [
    ("printf 'prompts/app_context/module.md\\n'\n", "e2e=false"),
    ("printf 'prompts/app_context/module.md\\napp_inventory/app.json\\n'\n", "e2e=true"),
    ("printf 'features/a.feature\\n'\n", "e2e=true"),
    ("exit 1\n", "e2e=true"),                     # the API failed: run
    ("true\n", "e2e=true"),                       # no files listed: run
])
def test_the_workflow_step_applies_the_rule_and_fails_open(tmp_path, gh_body, expected):
    assert _run_detector(tmp_path, gh_body).strip() == expected


def test_browser_steps_and_the_report_honour_the_verdict():
    jobs = _agent4()["jobs"]
    guarded = [s["name"] for s in jobs["test"]["steps"]
               if "steps.pr_changes.outputs.e2e != 'false'" in (s.get("if") or "")]
    assert {"Cache Playwright browsers", "Install Playwright browsers",
            "Run app tests (generated E2E)"} <= set(guarded)
    assert jobs["test"]["outputs"]["e2e"] == "${{ steps.pr_changes.outputs.e2e }}"
    assert "needs.test.outputs.e2e != 'false'" in jobs["report"]["if"]
    unit = next(s for s in jobs["test"]["steps"] if s["name"] == "Framework self-test (unit tests)")
    assert "if" not in unit                                  # the unit suite always runs


def test_agent3_does_not_read_a_unit_only_green_as_evidence(monkeypatch):
    """No app test ran on a prompts/docs-only PR, so Agent 3 must not lower a
    predicted failure on the strength of that run's green conclusion."""
    import agents.agent3_reviewer as a3
    seen = {}

    def fake_postprocess(report, get_runner_result=None, changed_lines=None):
        seen["runner"] = get_runner_result
        return report, 0

    def run_with(files):
        seen.clear()
        gh = MagicMock()
        gh.get_pr_metadata.return_value = {"number": 1, "title": "t", "body": "", "state": "open",
                                           "head_branch": "b", "base_branch": "main",
                                           "author": "a", "url": "u"}
        gh.get_pr_changed_files.return_value = [
            {"filename": f, "status": "modified", "patch": "", "content": "x",
             "additions": 1, "deletions": 0} for f in files]
        llm = MagicMock()
        llm.invoke_structured.return_value = MagicMock(overall_verdict="comment", issues=[])
        with patch.object(a3, "get_repo_host", return_value=gh), \
             patch.object(a3, "LLMClient", return_value=llm), \
             patch.object(a3, "postprocess_review", side_effect=fake_postprocess), \
             patch.object(a3, "format_review_as_markdown", return_value="md"), \
             patch.object(a3, "align_labels_with_verdict", side_effect=lambda r: r):
            try:
                a3.run(1)
            except Exception as e:  # noqa: BLE001
                seen.setdefault("error", repr(e))               # only steps after 3b may fail
        assert "runner" in seen, seen.get("error")
        return seen["runner"]

    assert run_with(["prompts/app_context/module.md"]) is None
    assert callable(run_with(["features/sample.feature"]))
