"""A pull request that changes only what no test reads at runtime (prompts,
docs, Markdown) skips the browser run: the rule (core/test_runtime.py), the
workflow step that applies it and fails open, the steps and report that honour
it, and Agent 3 not reading such a unit-only green run as evidence.
"""

from unittest.mock import MagicMock, patch
import pytest
import yaml
from core.test_runtime import runs_app_tests


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
