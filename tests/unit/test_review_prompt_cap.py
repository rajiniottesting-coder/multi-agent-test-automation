"""X7: the whole review prompt is capped; a larger change is reviewed in
parts, at most `review.max_parts`, and files beyond them are named on the
review. The largest review so far read 138,632 tokens and nothing capped it.

Generic file names; a fake repository host and model.
"""
from types import SimpleNamespace

import pytest

from agents import agent3_reviewer as a3
from core.schemas import ReviewIssue, ReviewReport


def _f(name, patch_chars=100, content=None):
    return {"filename": name, "status": "modified", "additions": 1, "deletions": 1,
            "patch": "+" + "x" * patch_chars, "content": content}


def _report(verdict="approve", issues=(), **checks):
    base = dict(style_compliance=True, type_hints_present=True, no_hardcoded_waits=True,
                pom_compliant=True, coverage_complete=True)
    base.update(checks)
    return ReviewReport(pr_number=7, overall_verdict=verdict, summary=f"{verdict} summary",
                        issues=list(issues), **base)


def _issue(path):
    return ReviewIssue(severity="minor", file_path=path, description="d", suggested_fix="f")


def test_everything_that_fits_is_one_part():
    files = [_f("pages/a_page.py"), _f("pages/b_page.py")]
    parts, left = a3.split_for_review(files, 10_000, 3)
    assert parts == [files] and left == []


def test_a_large_change_is_split_in_order_and_capped():
    files = [_f(f"pages/p{i}_page.py", 4_000) for i in range(6)]
    parts, left = a3.split_for_review(files, 9_000, 2)
    assert [len(p) for p in parts] == [2, 2]
    assert [f["filename"] for f in left] == ["pages/p4_page.py", "pages/p5_page.py"]
    assert [f["filename"] for p in parts for f in p] == [f["filename"] for f in files[:4]]


def test_a_file_bigger_than_the_budget_is_a_part_and_its_diff_is_cut():
    files = [_f("pages/huge_page.py", 50_000), _f("pages/small_page.py")]
    parts, left = a3.split_for_review(files, 10_000, 3)
    assert [len(p) for p in parts] == [1, 1] and left == []
    (cut,) = a3._cut(parts[0], 10_000)
    assert len(cut["patch"]) < 10_000 and "diff cut here" in cut["patch"]
    assert files[0]["patch"].startswith("+x") and len(files[0]["patch"]) > 50_000  # not mutated


def test_parts_merge_into_the_strictest_review():
    merged = a3.merge_reports([
        _report("approve", [_issue("a.py")]),
        _report("request_changes", [_issue("b.py")], pom_compliant=False),
        _report("comment")], 7)
    assert merged.overall_verdict == "request_changes"
    assert [i.file_path for i in merged.issues] == ["a.py", "b.py"]
    assert merged.pom_compliant is False and merged.style_compliance is True
    assert merged.summary.startswith("(Part 1 of 3) approve summary")
    one = _report()
    assert a3.merge_reports([one], 7) is one


def test_files_left_out_are_named():
    issue = a3.left_out_issue([_f(f"pages/p{i}_page.py") for i in range(23)], 3)
    assert issue.severity == "major" and "23 changed file(s) were not reviewed" in issue.description
    assert "and 3 more" in issue.description and "review.max_parts" in issue.description


def test_settings_have_defaults():
    s = a3.review_settings()
    assert 50_000 <= s["max_prompt_tokens"] <= 150_000 and s["max_parts"] >= 1


@pytest.fixture
def world(monkeypatch):
    files = [_f(f"pages/p{i}_page.py", 30_000) for i in range(5)]
    prompts = []

    class Host:
        def get_pr_metadata(self, n):
            return {"number": n, "title": "t", "head_branch": "feature/x", "author": "a",
                    "body": "", "state": "open"}

        def get_pr_changed_files(self, n):
            return files

    class LLM:
        def __init__(self, **k):
            pass

        def invoke_structured(self, system_prompt, user_prompt, output_schema):
            prompts.append(user_prompt)
            return _report("comment", [_issue(f"part{len(prompts)}.py")])

    ctx = SimpleNamespace(name="App", reference_feature="f", reference_step_def="s",
                          reference_page_object="p",
                          load_reference_files=lambda: {"feature": "F", "step_def": "S",
                                                        "page_object": "P"},
                          load_page_inventory_json=lambda: "{}")
    monkeypatch.setattr(a3.AppContext, "load", staticmethod(lambda: ctx))
    monkeypatch.setattr(a3, "get_repo_host", lambda: Host())
    monkeypatch.setattr(a3, "load_prompt", lambda: "RULES {changed_files_section} END")
    monkeypatch.setattr(a3, "LLMClient", LLM)
    monkeypatch.setattr(a3, "review_settings",
                        lambda: {"max_prompt_tokens": 16_000, "max_parts": 2})
    return files, prompts


def test_run_reviews_in_parts_and_names_what_it_left(world, monkeypatch):
    files, prompts = world
    captured = {}
    real = a3.format_review_as_markdown
    monkeypatch.setattr(a3, "format_review_as_markdown",
                        lambda report, *a, **k: captured.setdefault("r", report) and real(report, *a, **k))
    result = a3.run(7, dry_run=True)
    assert len(prompts) == 2
    assert all(len(p) <= 16_000 * 4 for p in prompts)
    assert all(p.startswith("RULES") and p.endswith("END") for p in prompts)
    assert "p0_page.py" in prompts[0] and "p0_page.py" not in prompts[1]
    report = captured["r"]
    assert any("were not reviewed" in i.description for i in report.issues)
    assert result["status"] == "review_generated_dry_run"
