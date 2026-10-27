"""Agent 3's review prompt stays within the model's context.

Found on PR #225: the review call failed (exit 1, no review posted) because
every changed file went into the prompt in full - the large guides included -
and the prompt measured ~964,000 characters (~241k tokens). Now a file no test
reads while it runs (`prompts/`, `docs/`, Markdown - core.test_runtime, the
rule Agent 4 uses to skip the browser) is shown as its diff, and the section
has a budget: the largest full contents fall back to their diffs first. A
pull request of test code is shown exactly as before.

Generic file names; no application names.
"""
from agents import agent3_reviewer as a3


def _f(name, content=None, patch="@@ -1 +1 @@\n-a\n+b", status="modified"):
    return {"filename": name, "status": status, "additions": 1, "deletions": 1,
            "patch": patch, "content": content}


def _old_format(files):
    """The formatter before the budget, verbatim - what test code must still get."""
    blocks = []
    for f in files:
        block = f"### File: `{f['filename']}`\n"
        block += f"Status: {f['status']} (+{f['additions']} -{f['deletions']})\n\n"
        if f.get("content"):
            block += f"**Full file content:**\n```\n{f['content']}\n```\n"
        elif f.get("patch"):
            block += f"**Diff (patch):**\n```diff\n{f['patch']}\n```\n"
        else:
            block += "(File content not available — possibly binary or too large)\n"
        blocks.append(block)
    return "\n---\n".join(blocks)


def test_a_pull_request_of_test_code_is_shown_exactly_as_before():
    files = [_f("features/a.feature", "Feature: A\n"), _f("pages/a_page.py", "class A: pass\n"),
             _f("tests/step_defs/test_a.py", "def test(): pass\n"), _f("pages/gone.py", None, None)]
    assert a3.format_changed_files_for_prompt(files) == _old_format(files)


def test_documentation_and_prompts_are_shown_as_their_diff():
    files = [_f("docs/GUIDE.md", "x" * 50_000), _f("prompts/agent9.md", "y" * 100),
             _f("README.md", "z" * 100), _f("core/mod.py", "code = 1\n")]
    text = a3.format_changed_files_for_prompt(files)
    assert "x" * 1000 not in text and "y" * 100 not in text and "z" * 100 not in text
    assert text.count("**Diff (patch):**") == 3
    assert "**Full file content:**\n```\ncode = 1\n" in text, "code is still shown whole"
    assert "the diff is complete" in text


def test_over_budget_the_largest_full_contents_fall_back_to_their_diffs_first():
    files = [_f("pages/big_page.py", "b" * 9_000), _f("pages/mid_page.py", "m" * 5_000),
             _f("pages/small_page.py", "s" * 500)]
    text = a3.format_changed_files_for_prompt(files, budget_chars=7_000)
    assert "b" * 9_000 not in text, "largest first"
    assert "m" * 5_000 in text and "s" * 500 in text, "only as many as needed"
    assert len(text) <= 7_000


def test_a_file_without_a_diff_says_its_content_was_left_out():
    text = a3.format_changed_files_for_prompt([_f("pages/x_page.py", "q" * 5_000, None)],
                                              budget_chars=100)
    assert "Full content and diff left out" in text and "q" * 100 not in text


def test_no_files_and_no_content_keep_their_messages():
    assert a3.format_changed_files_for_prompt([]) == "(No files changed)"
    assert "possibly binary or too large" in a3.format_changed_files_for_prompt(
        [_f("img.png", None, None)])


def test_the_budget_leaves_room_in_the_context():
    assert a3._CHANGED_FILES_BUDGET_CHARS <= 400_000     # ~100k tokens, of ~200k
