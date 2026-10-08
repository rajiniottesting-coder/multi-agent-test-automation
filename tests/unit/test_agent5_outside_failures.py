"""Agent 5 must not call a branch green while other tests fail on it.

THE CASE THIS CATCHES
    A story regenerates a shared page object and breaks tests other stories
    own. Agent 4 runs the whole suite, so the PR check goes red. Agent 5
    scopes its report to the step-def modules the PR touched - deliberately,
    so an unrelated failure is not counted as this story's - and computed its
    verdict from that scope. The Jira comment said "passed" next to a red check.

THE RULE
    The story's own counts stay scoped (test_usage_ledger.py pins that). What
    scoping drops is listed separately, by code, and the verdict counts it.
"""
from pathlib import Path

import pytest

import agents.agent5_reporter as a5
from agents.agent5_reporter import (
    _failures_outside_scope,
    _overall_verdict,
    _scope_to_story,
    build_final_comment,
)
from core.schemas import JiraCommentDraft, RunReport
from core.schemas import TestResult as Result   # not 'Test*': pytest would try to collect it


def _tc(mod, name, status="passed", msg=None):
    return Result(name=name, classname=f"tests.step_defs.{mod}", status=status,
                      duration_seconds=1.0,
                      failure_message=msg if status != "passed" else None)


def _session(*extra):
    """The story owns test_story_module; test_older_module belongs to another story."""
    results = [
        _tc("test_story_module", "test_first"),
        _tc("test_story_module", "test_second"),
        _tc("test_older_module", "test_still_fine"),
        _tc("test_older_module", "test_broken_by_this_branch", "failed",
            "TypeError: look_up() missing 1 required positional argument"),
        *extra,
    ]
    failed = sum(r.status == "failed" for r in results)
    errors = sum(r.status == "error" for r in results)
    return RunReport(total=len(results), passed=len(results) - failed - errors,
                     failed=failed, errors=errors, results=results, pr_number=7)


def _story_owns(monkeypatch, *paths):
    monkeypatch.setattr(a5, "get_repo_host", lambda: type("H", (), {
        "get_pr_changed_files": staticmethod(
            lambda n: [{"filename": p} for p in paths])})())


# ── what the story is told ───────────────────────────────────────────────────

def test_a_failure_outside_the_story_is_kept_not_dropped(monkeypatch):
    _story_owns(monkeypatch, "tests/step_defs/test_story_module.py")
    full = _session()
    scoped = _scope_to_story(full)
    assert (scoped.total, scoped.failed) == (2, 0), "the story's own counts stay scoped"
    outside = _failures_outside_scope(full, scoped)
    assert [r.name for r in outside] == ["test_broken_by_this_branch"]


def test_the_verdict_is_failed_when_only_another_storys_test_fails(monkeypatch):
    """The exact contradiction: story green, branch red."""
    _story_owns(monkeypatch, "tests/step_defs/test_story_module.py")
    full = _session()
    scoped = _scope_to_story(full)
    assert _overall_verdict(scoped, _failures_outside_scope(full, scoped)) == "failed"


def test_the_verdict_is_passed_only_when_everything_passes(monkeypatch):
    _story_owns(monkeypatch, "tests/step_defs/test_story_module.py")
    full = RunReport(total=2, passed=2, failed=0, pr_number=7, results=[
        _tc("test_story_module", "test_first"), _tc("test_older_module", "test_ok")])
    scoped = _scope_to_story(full)
    assert _failures_outside_scope(full, scoped) == []
    assert _overall_verdict(scoped, []) == "passed"


def test_the_storys_own_failure_still_fails_it(monkeypatch):
    _story_owns(monkeypatch, "tests/step_defs/test_story_module.py")
    full = _session(_tc("test_story_module", "test_third", "failed", "AssertionError"))
    scoped = _scope_to_story(full)
    assert scoped.failed == 1
    assert _overall_verdict(scoped, _failures_outside_scope(full, scoped)) == "failed"


def test_an_error_outside_the_story_counts_too(monkeypatch):
    _story_owns(monkeypatch, "tests/step_defs/test_story_module.py")
    full = _session(_tc("test_older_module", "test_setup_crash", "error", "fixture boom"))
    scoped = _scope_to_story(full)
    names = [r.name for r in _failures_outside_scope(full, scoped)]
    assert "test_setup_crash" in names


def test_when_scoping_did_not_happen_nothing_is_reported_twice():
    """No PR number - the report stays whole, so 'outside' must be empty."""
    full = _session().model_copy(update={"pr_number": None})
    scoped = _scope_to_story(full)
    assert scoped is full or scoped.total == full.total
    assert _failures_outside_scope(full, scoped) == []
    assert _overall_verdict(scoped, []) == "failed", "the failure is still the verdict"


# ── how the comment shows it ─────────────────────────────────────────────────

def test_without_outside_failures_the_comment_is_unchanged():
    report = RunReport(total=1, passed=1, failed=0)
    body = build_final_comment("All good.", report)
    assert body == build_final_comment("All good.", report, [])
    assert body.startswith("All good.")
    assert "other test" not in body


def test_the_comment_warns_first_and_names_each_failure():
    outside = [_tc("test_older_module", "test_broken_by_this_branch", "failed",
                   "TypeError: look_up() missing 1 required positional argument\nmore")]
    body = build_final_comment("Story tests: 2 passed.", RunReport(total=2, passed=2, failed=0),
                               outside)
    first = body.splitlines()[0]
    assert "Not green" in first and "1 test" in first, "the warning leads"
    assert "test_older_module::test_broken_by_this_branch" in body
    assert "TypeError: look_up() missing 1 required positional argument" in body
    assert "\nmore" not in body, "first line of the message only"
    assert body.index("Story tests: 2 passed.") < body.index("other test failing")
    assert body.rstrip().endswith("_Posted automatically by Agent 5 (Reporter)._")


def test_a_long_list_is_capped():
    outside = [_tc("test_older_module", f"test_{i}", "failed", "x") for i in range(20)]
    body = build_final_comment("p", RunReport(total=20, passed=0, failed=20), outside)
    assert body.count("`test_older_module::test_") == 15
    assert "...and 5 more" in body


# ── the whole agent ──────────────────────────────────────────────────────────

def test_run_reports_the_regression_and_returns_failed(monkeypatch, tmp_path, capsys):
    """run() end to end in dry-run: real scoping, real assembly, real verdict.
    Only the PR lookup and the model are faked."""
    _story_owns(monkeypatch, "tests/step_defs/test_story_module.py")
    monkeypatch.setattr(a5, "parse_junit_xml", lambda path: _session())
    monkeypatch.setattr(a5, "load_prompt", lambda: "{run_report_json}")
    seen = {}

    class FakeLLM:
        def __init__(self, *a, **k):
            pass

        def invoke_structured(self, system_prompt, user_prompt, output_schema):
            seen["prompt"] = user_prompt
            return JiraCommentDraft(title="All 2 tests passed",
                                    body_markdown="All 2 of this story's tests passed.")

    monkeypatch.setattr(a5, "LLMClient", FakeLLM)
    result = a5.run("STORY-1", Path(tmp_path), dry_run=True)

    assert result["verdict"] == "failed"
    assert result["failing_outside_story"] == 1
    assert (result["total"], result["failed"]) == (2, 0), "story counts stay scoped"
    printed = capsys.readouterr().out
    assert "Not green" in printed
    assert "test_older_module::test_broken_by_this_branch" in printed
    assert "test_broken_by_this_branch" not in seen["prompt"], \
        "the model is still given only the story's own tests"
