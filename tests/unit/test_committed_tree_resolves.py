"""Every method a COMMITTED step definition calls must still exist.

THE CASE THIS CATCHES
    Agent 2 opens a pull request whose step definitions call search_for().
    Someone renames that method to search_catalogue() on their own branch and
    merges first. Agent 2's branch is now stale in a way nothing notices:
    validate_method_resolution ran at generation time and does not run again,
    the diff still looks correct in isolation, and Agent 3 reviews the diff
    rather than the merged tree.

    It surfaces as an AttributeError when Agent 4 executes the suite - after
    Playwright has installed, launched a browser and signed in. Three minutes
    of CI to discover a rename.

WHY A UNIT TEST RATHER THAN A GATE
    The generation gate cannot help: it runs before the branch exists, and the
    breakage is introduced by a DIFFERENT branch afterwards. But GitHub checks
    out the merge result for a pull_request event, so this test sees exactly
    the tree Agent 4 would execute - and it sees it in seconds, with no
    browser, naming the method rather than reporting an AttributeError from
    somewhere inside a page object.

    Third time this shape has earned its keep: one rule, applied both at the
    gate and to what is committed.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import validate_method_resolution

_PROJECT = Path(__file__).resolve().parents[2]


def _committed_files() -> list:
    """Step definitions and page objects, as the validator expects them."""
    paths = sorted(_PROJECT.joinpath("tests", "step_defs").glob("test_*.py"))
    paths += sorted(_PROJECT.joinpath("pages").glob("*_page.py"))
    return [
        SimpleNamespace(
            file_path=str(p.relative_to(_PROJECT)).replace("\\", "/"),
            content=p.read_text(encoding="utf-8"),
        )
        for p in paths
    ]


def test_every_committed_step_def_calls_a_method_that_exists():
    files = _committed_files()
    if not any(f.file_path.startswith("tests/step_defs/") for f in files):
        pytest.skip("no step definitions committed yet")

    errors = validate_method_resolution(files, _PROJECT)
    assert not errors, (
        "a committed step definition calls a page-object method that does not "
        "exist. The usual cause is a rename landing on main while another "
        "branch was open: the diff looked correct in isolation, and nothing "
        "re-checked the two together. Rename the call, or restore the "
        "method.\n  " + "\n  ".join(errors))


def test_the_check_sees_both_halves():
    """A guard on the guard: if the file collection ever stopped picking up
    step definitions, the test above would pass by looking at nothing.

    Skips rather than fails when a half is genuinely absent. A freshly
    onboarded application has page objects and no step definitions yet, and a
    FRAMEWORK test must not fail simply because Agent 2 has not run - that
    turns "nothing generated yet" into a red suite on day one.
    """
    kinds = {f.file_path.split("/")[0] for f in _committed_files()}
    if "tests" not in kinds:
        pytest.skip("no step definitions committed yet - nothing to resolve")
    assert "pages" in kinds, \
        "step definitions exist but no page objects - the check is vacuous"


# =========================================================================
# THE SAME RULE, ONE STAGE EARLIER
#
# The check above reads what is COMMITTED, and it works - it is what caught
# the failure this section exists for. But it caught it on the branch, after
# Agent 2 had spent its budget and opened a pull request. The unit gate went
# red, then three reference E2E tests died on AttributeError.
#
# What happened: a story regenerated the shared navigation page object. Agent 2
# emits a whole file, not a patch, so the replacement kept the two methods that
# story needed and dropped eight it did not - three of which the reference
# login suite calls.
#
# Every check in the batch passed, correctly. The generated step definitions
# resolved perfectly against the generated page object. The callers that
# noticed were already on main and were never in the batch to speak for
# themselves.
#
# validate_method_resolution now reads the current file from disk as well, so
# the same rule applies while the file can still be repaired.
# =========================================================================

def _snake(name: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _page_object(class_name: str, rel: str, methods: list):
    """A generated replacement for `rel`, defining only `methods`."""
    from types import SimpleNamespace
    body = "\n".join(f"    def {m}(self) -> None:\n        pass\n" for m in methods)
    return SimpleNamespace(
        file_path=rel,
        content=("from pages.base_page import BasePage\n\n\n"
                 f"class {class_name}(BasePage):\n"
                 f'    INVENTORY_PAGE = "a_page"\n\n' + body),
    )


def _a_page_object_with_committed_callers():
    """(class_name, relative path, its public methods) - discovered, not named.

    Which page object is this application's business. The check is about the
    SHAPE - a regeneration that drops a method somebody else still calls - so
    the test finds a page object that has callers rather than hardcoding one,
    and works unchanged when the framework is pointed at a different
    application.
    """
    import ast
    import re

    step_defs = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_PROJECT.joinpath("tests", "step_defs").glob("test_*.py"))
    }
    for path in sorted(_PROJECT.joinpath("pages").glob("*_page.py")):
        if path.name == "base_page.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            methods = [n.name for n in cls.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and not n.name.startswith("_")]
            fixture = _snake(cls.name)
            called = [m for m in methods
                      if any(re.search(rf"\b{fixture}\.{m}\s*\(", src)
                             for src in step_defs.values())]
            if len(called) >= 1 and len(methods) > len(called):
                return cls.name, f"pages/{path.name}", methods, called
    return None


def test_dropping_a_method_a_committed_step_def_calls_is_rejected():
    """The exact regeneration that broke the build, in shape."""
    from validators.method_resolution_validator import validate_method_resolution

    found = _a_page_object_with_committed_callers()
    if not found:
        pytest.skip("no committed page object has callers outside its own batch")
    class_name, rel, methods, called = found

    # Keep everything EXCEPT the methods somebody still calls.
    kept = [m for m in methods if m not in called]
    errors = [e for e in validate_method_resolution(
        [_page_object(class_name, rel, kept)], _PROJECT)
        if "no longer defines" in e]

    assert errors, (
        "a regeneration that drops methods the committed step definitions call "
        "must be rejected at the generation gate, not discovered on the branch"
    )
    assert any("tests/step_defs/" in e for e in errors), "name who still calls it"


def test_keeping_every_method_is_accepted():
    """Break the thing the guard guards. A story that ADDS a method to a shared
    page object is the normal case and must not be blocked."""
    from validators.method_resolution_validator import validate_method_resolution

    found = _a_page_object_with_committed_callers()
    if not found:
        pytest.skip("no committed page object has callers outside its own batch")
    class_name, rel, methods, _ = found

    errors = [e for e in validate_method_resolution(
        [_page_object(class_name, rel, methods + ["do_something_new"])], _PROJECT)
        if "no longer defines" in e]

    assert not errors, "adding a method must be allowed:\n  " + "\n  ".join(errors)


def test_a_brand_new_page_object_is_not_judged():
    """Nothing on disk to compare against, so nothing was removed."""
    from validators.method_resolution_validator import validate_method_resolution

    errors = [e for e in validate_method_resolution(
        [_page_object("NoSuchPage", "pages/no_such_page.py", ["do_a_thing"])],
        _PROJECT)
        if "no longer defines" in e]
    assert not errors