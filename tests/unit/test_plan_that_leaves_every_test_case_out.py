"""A plan that leaves every test case out has no files - and that is valid.

The plan prompt says to plan no files at all when every test case is left out
(each with its "Skipped: <KEY> -- <reason>" line), and Agent 2 then refuses
the story with those reasons (core.blocked). The schema used to require one
file: the model wrote a placeholder, or - obeying the prompt - an empty list
that failed validation, and the run ended with a parse error instead of the
refusal, so nothing was said on the story and no missing page was explored
(17 Nov 2026, run 43999866814).
"""
from pathlib import Path

from core.schemas import CodePlan

BASE = {"feature_name": "x", "branch_name": "auto/PRJ-1-x", "pr_title": "t", "pr_body": "b",
        "notes": "Skipped: PRJ-2 -- needs the list on reports_list, not in the app inventory"}


def test_an_empty_plan_is_valid_and_so_is_one_without_the_field():
    assert CodePlan(**BASE, files_to_create=[]).files_to_create == []
    assert CodePlan(**BASE).files_to_create == []
    assert CodePlan.model_validate_json(
        '{"feature_name": "x", "branch_name": "b", "pr_title": "t", "pr_body": "b"}'
    ).files_to_create == []


def test_the_empty_plan_reaches_the_refusal_before_anything_is_generated():
    source = Path("agents/agent2_coder.py").read_text(encoding="utf-8")
    gate = source.index("or not any(f.file_path.endswith(\".feature\") for f in plan.files_to_create)")
    assert gate < source.index("ordered_files = _sort_files_for_generation(plan.files_to_create)")
    assert "blocked.post_blocked_once(jira, story_id, input_fp, e.errors)" in source[gate:gate + 1200]
