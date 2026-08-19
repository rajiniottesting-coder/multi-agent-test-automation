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