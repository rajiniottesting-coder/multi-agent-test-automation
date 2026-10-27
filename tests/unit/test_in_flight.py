"""
In-flight protection: stories whose pull requests are open at the same time.

- Agent 2 waits instead of writing a file another open PR is changing, or
  generating a scenario another open PR already adds (core/in_flight.py).
- Duplicate detection compares a test case's title without its `[type]` tag.
- Agent 4's browser runs take turns across pull requests (scripts/e2e_turn.py).
"""
import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
import yaml

from core import in_flight
from core.schemas import CodePlan, FilePlan
from scripts.e2e_turn import runs_ahead
from tests.sandbox.fake_jira import FakeRepoHost
from tests.sandbox.seed import repo_files
from tests.unit.test_agent2_impact import OWN_FEATURE, OWN_STEPS, _hand_over_and_draft
from tests.unit.test_agent2_impact import world as _change_story_world


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """The change-story sandbox of test_agent2_impact (story SBX-5)."""
    return _change_story_world.__wrapped__(tmp_path, monkeypatch)


# ─────────────────────────────────────────────────────────────
# core/in_flight.py
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ref, own", [
    ("auto/PROJ-5-login", True),
    ("auto/PROJ-5-login-update2", True),
    ("context-update/proj-5", True),
    ("auto/PROJ-50-search", False),           # a different story
    ("auto/PROJ-51-x", False),
    ("feature/other", False),
])
def test_a_storys_own_branches_are_recognised(ref, own):
    assert in_flight._own_branch(ref, "PROJ-5") is own


class FakeHost:
    def __init__(self, prs, files, fail=False):
        self.prs, self.files, self.fail = prs, files, fail

    def list_open_prs(self, branch_prefix=""):
        if self.fail:
            raise RuntimeError("api down")
        return self.prs

    def get_pr_changed_files(self, n):
        return self.files[n]


def _host():
    return FakeHost(
        [{"number": 7, "head_ref": "auto/PROJ-9-x", "url": "u7"},
         {"number": 8, "head_ref": "auto/PROJ-5-own", "url": "u8"}],
        {7: [{"filename": "pages/x_page.py", "content": "class X: ..."},
             {"filename": "features/x.feature",
              "content": "Feature: x\n\n  Scenario: Shared title here\n    Then ok\n"}],
         8: [{"filename": "pages/y_page.py", "content": "..."}]})


def test_snapshot_reads_other_prs_only():
    state = in_flight.snapshot(_host(), "PROJ-5")
    assert set(state.by_path) == {"pages/x_page.py", "features/x.feature"}
    assert state.by_path["pages/x_page.py"] == [(7, "u7")]


def test_snapshot_fails_open():
    assert not in_flight.snapshot(FakeHost([], {}, fail=True), "PROJ-5")


def test_file_conflicts_compare_normalised_paths():
    state = in_flight.snapshot(_host(), "PROJ-5")
    hits = in_flight.file_conflicts({"./pages/x_page.py", "pages/z_page.py"}, state)
    assert hits == [{"path": "pages/x_page.py", "pr": 7, "url": "u7"}]
    assert in_flight.file_conflicts({"pages/y_page.py"}, state) == []    # own PR's file


def test_duplicate_scenarios_ignore_the_type_tag():
    from agents.agent2_coder import _feature_titles, plain_test_case_title
    state = in_flight.snapshot(_host(), "PROJ-5")
    cases = [{"key": "PROJ-6", "summary": "[Positive] Shared title HERE"},
             {"key": "PROJ-7", "summary": "[Negative] Something else"}]
    hits = in_flight.duplicate_scenarios(cases, state, _feature_titles,
                                         case_title=plain_test_case_title)
    assert [(h["key"], h["pr"], h["scenario"]) for h in hits] == \
           [("PROJ-6", 7, "Shared title here")]


def test_the_waiting_note_is_posted_once_per_reason():
    tracker = MagicMock()
    comments = []
    tracker.get_comments.side_effect = lambda k: list(comments)
    tracker.add_comment.side_effect = lambda k, b: comments.append(b)
    files = [{"path": "pages/x_page.py", "pr": 7, "url": "u7"}]
    assert in_flight.post_wait_once(tracker, "PROJ-5", files, []) is True
    assert in_flight.post_wait_once(tracker, "PROJ-5", files, []) is False      # next scan
    assert len(comments) == 1 and "PR #7" in comments[0]
    other = [{"path": "pages/x_page.py", "pr": 9, "url": "u9"}]
    assert in_flight.post_wait_once(tracker, "PROJ-5", other, []) is True       # new reason


def test_the_waiting_note_never_raises():
    tracker = MagicMock()
    tracker.get_comments.side_effect = RuntimeError("down")
    assert in_flight.post_wait_once(tracker, "PROJ-5", [], []) is False


# ─────────────────────────────────────────────────────────────
# Agent 2, end to end in the sandbox
# ─────────────────────────────────────────────────────────────
def _other_story_pr(gh, files: dict, story="SBX-9"):
    """Another story's open pull request changing `files`."""
    branch = f"auto/{story}-other-work"
    gh.branches[branch] = {**gh.branches["main"], **files}
    gh.open_pull_request("other", "b", branch)


def _run(jira, gh):
    import agents.agent2_coder as a2
    plan = CodePlan(feature_name="remember-me", branch_name="auto/SBX-5-remember-me",
                    pr_title="t", pr_body="b", notes="n",
                    files_to_create=[FilePlan(file_path=OWN_FEATURE, file_type="feature",
                                              purpose="own"),
                                     FilePlan(file_path=OWN_STEPS,
                                              file_type="step_definitions", purpose="own")])
    gen = MagicMock(side_effect=lambda llm, fp, *a, **k: (
        "Feature: R\n\n  Scenario: Remember-me expires after a week\n    Then ok\n"
        if fp.file_path == OWN_FEATURE else "# steps\n"))
    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient"), \
         patch.object(a2, "build_plan", return_value=plan) as bp, \
         patch.object(a2, "generate_file_content", gen), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_generate_single_scenario",
                      side_effect=lambda llm, path, tc, ctx, existing: (
                          "  " + a2.format_marker(tc["key"], tc.get("description", ""),
                                                  tc.get("owner"), tc.get("impacted_by", ()))
                          + "\n  Scenario: Revised\n    Then ok\n")), \
         patch.object(a2, "_splice_step_defs_incremental",
                      side_effect=lambda llm, gh_, p, c, sd, *a, **k: (gh_.get_file_content(sd), "unchanged")), \
         patch.object(a2, "_validate_generated_files"):
        result = a2.run("SBX-5")
    return result, bp, gen


def _ready(fake, jira):
    _hand_over_and_draft(jira, {"SBX-11": "approve"})


def test_a_file_another_open_pr_changes_makes_the_story_wait(sandbox):
    fake, jira, root = sandbox
    _ready(fake, jira)
    gh = FakeRepoHost(repo_files(root))
    _other_story_pr(gh, {OWN_STEPS: "# the other story's step definitions\n"})

    result, bp, gen = _run(jira, gh)
    assert result["status"] == "waiting_for_open_pr" and result["waiting_for"] == [1]
    bp.assert_called_once()                      # the plan named the file...
    gen.assert_not_called()                      # ...and nothing was generated
    assert len(gh.prs) == 1                      # no PR of its own
    assert "ai-coded" not in fake.issues["SBX-5"]["labels"]          # retried next scan
    notes = [c for c in fake.comments["SBX-5"] if in_flight.WAITING_MARKER in c]
    assert len(notes) == 1 and OWN_STEPS in notes[0] and "PR #1" in notes[0]

    _run(jira, gh)                               # the next scan: still waiting...
    assert len([c for c in fake.comments["SBX-5"] if in_flight.WAITING_MARKER in c]) == 1

    gh.merge(1)                                  # ...until the other PR is settled
    gh.branches["main"].update(gh.branches["auto/SBX-9-other-work"])
    result, _bp, _gen = _run(jira, gh)
    assert result["status"] == "pr_opened"


def test_a_scenario_another_open_pr_adds_waits_before_any_model_call(sandbox):
    fake, jira, root = sandbox
    _ready(fake, jira)
    gh = FakeRepoHost(repo_files(root))
    _other_story_pr(gh, {"features/elsewhere.feature":
                         "Feature: e\n\n  Scenario: Remember-me expires after a week\n    Then ok\n"})
    result, bp, _gen = _run(jira, gh)
    assert result["status"] == "waiting_for_open_pr"
    bp.assert_not_called()                       # checked before the plan
    note = next(c for c in fake.comments["SBX-5"] if in_flight.WAITING_MARKER in c)
    assert "Remember-me expires after a week" in note


def test_an_unrelated_open_pr_changes_nothing(sandbox):
    fake, jira, root = sandbox
    _ready(fake, jira)
    gh = FakeRepoHost(repo_files(root))
    _other_story_pr(gh, {"pages/unrelated_page.py": "class Unrelated: ...\n"})
    result, _bp, _gen = _run(jira, gh)
    assert result["status"] == "pr_opened"
    assert not any(in_flight.WAITING_MARKER in c for c in fake.comments.get("SBX-5", []))


def test_an_unreadable_pr_list_never_stops_the_story(sandbox):
    fake, jira, root = sandbox
    _ready(fake, jira)
    gh = FakeRepoHost(repo_files(root))
    _other_story_pr(gh, {OWN_STEPS: "# other\n"})
    gh.list_open_prs = MagicMock(side_effect=RuntimeError("api down"))
    result, _bp, _gen = _run(jira, gh)
    assert result["status"] == "pr_opened"


def test_a_waiting_story_is_not_a_failed_scan():
    from agents.agent2_coder import _scan_summary_lines
    lines = _scan_summary_lines([{"story_id": "PROJ-5", "status": "waiting_for_open_pr"}])
    assert any(line.startswith("[WAIT] PROJ-5") for line in lines), lines


# ─────────────────────────────────────────────────────────────
# ai-update
# ─────────────────────────────────────────────────────────────
def test_ai_update_waits_when_its_feature_file_is_in_another_open_pr(tmp_path, monkeypatch):
    import agents.agent2_coder as a2
    from config import paths
    from tests.sandbox.fake_jira import jira_client_over
    from tests.sandbox.seed import build_repo, seed_jira
    fake = seed_jira()
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    fake.issues["SBX-12"]["description"] = "changed"
    gh = FakeRepoHost(repo_files(root))
    target = "features/sandbox_login.feature"
    _other_story_pr(gh, {target: gh.branches["main"][target] + "\n# another story's edit\n"})
    single = MagicMock()
    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient"), \
         patch.object(a2, "_generate_single_scenario", single), \
         patch.object(a2, "_validate_generated_files"):
        result = a2.run_update("SBX-1")
    assert result["status"] == "waiting_for_open_pr"
    single.assert_not_called()                   # before any model call
    assert len(gh.prs) == 1


# ─────────────────────────────────────────────────────────────
# Duplicate detection on main: the `[type]` tag
# ─────────────────────────────────────────────────────────────
def test_a_tagged_summary_matches_its_unmarked_scenario(tmp_path):
    from agents.agent2_coder import build_marker_index, classify_against_index
    (tmp_path / "a.feature").write_text("Feature: a\n\n  Scenario: Valid login\n    Then ok\n")
    result = classify_against_index(
        [{"key": "AB-9", "summary": "[Positive] Valid login", "description": "d"}],
        build_marker_index(tmp_path))
    assert [r["test_case"]["key"] for r in result["legacy"]] == ["AB-9"]


# ─────────────────────────────────────────────────────────────
# Agent 4: browser runs take turns across pull requests
# ─────────────────────────────────────────────────────────────
def _r(i, status="in_progress", branch="b", event="pull_request"):
    return {"id": i, "status": status, "head_branch": branch, "event": event}


@pytest.mark.parametrize("runs, ahead", [
    ([], []),
    ([_r(10, branch="other")], [10]),                          # earlier, other PR: wait
    ([_r(10, status="queued", branch="other")], [10]),
    ([_r(10, status="completed", branch="other")], []),        # finished
    ([_r(30, branch="other")], []),                            # started after us
    ([_r(10, branch="mine")], []),                             # our own PR: its own group
    ([_r(10, branch="other", event="push")], []),              # not a PR run
    ([_r(10, branch="main", event="schedule")], [10]),         # the nightly run on main (F-21)
    ([_r(10, branch="other", event="workflow_dispatch")], []),
    ([_r(10, branch="x"), _r(12, branch="y"), _r(5, status="completed", branch="z")], [10, 12]),
])
def test_runs_ahead(runs, ahead):
    assert runs_ahead(20, "mine", runs) == ahead


def test_the_nightly_run_waits_for_earlier_pull_requests():
    assert runs_ahead(20, "main", [_r(10, branch="auto/X-1-y"), _r(11, branch="main",
                                                                    event="push")]) == [10]


def test_the_wait_lists_runs_of_every_event():
    run = _wait_step()["run"]
    assert "runs?per_page=100" in run and "event=pull_request" not in run, \
        "the scheduled run must be visible to pull requests"


def _agent4():
    from config.paths import PROJECT_ROOT
    return yaml.safe_load((PROJECT_ROOT / ".github/workflows/agent4_runner.yml").read_text())


def _wait_step():
    steps = _agent4()["jobs"]["test"]["steps"]
    names = [s["name"] for s in steps]
    i = names.index("Wait for earlier pull requests' browser runs")
    assert names[i + 1] == "Run app tests (generated E2E)"        # right before the browser
    return steps[i]


def test_the_wait_step_is_guarded_like_the_browser_run():
    step = _wait_step()
    assert step["if"].startswith("always() && (github.event_name == 'pull_request' "
                                 "|| github.event_name == 'schedule')"), \
        "pull requests and the nightly run on main take turns"
    assert "steps.pr_changes.outputs.e2e != 'false'" in step["if"]
    assert step.get("continue-on-error") is True
    assert int(step["env"]["MAX_WAIT_SECONDS"]) > 0
    assert _agent4()["jobs"]["test"]["timeout-minutes"] >= 15 + int(step["env"]["MAX_WAIT_SECONDS"]) // 60


def _run_wait(tmp_path, gh_body, max_wait="0"):
    from config.paths import PROJECT_ROOT
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\n" + gh_body)
    (bin_dir / "gh").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", GH_TOKEN="x", REPO="o/r",
               RUN_ID="20", BRANCH="mine", MAX_WAIT_SECONDS=max_wait)
    return subprocess.run(["bash", "-e", "-c", _wait_step()["run"]], cwd=PROJECT_ROOT,
                          env=env, capture_output=True, text=True, timeout=60, check=False)


def test_the_wait_step_goes_at_once_when_nobody_is_ahead(tmp_path):
    out = _run_wait(tmp_path, "echo '[]'\n", max_wait="900")
    assert out.returncode == 0 and "our turn" in out.stdout


def test_the_wait_step_is_bounded(tmp_path):
    runs = json.dumps([_r(10, branch="other")])
    out = _run_wait(tmp_path, f"echo '{runs}'\n", max_wait="0")
    assert out.returncode == 0 and "running the tests anyway" in out.stdout


def test_the_wait_step_fails_open(tmp_path):
    out = _run_wait(tmp_path, "exit 1\n", max_wait="900")
    assert out.returncode == 0 and "not waiting" in out.stdout
