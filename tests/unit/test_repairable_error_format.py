"""Every repairable error must name its file in the shape the repair loop reads.

WHAT HAPPENED
    `_collect_repairable_errors` aggregates every validator whose findings the
    repair loop can act on. `_group_validator_errors_by_file` then routes each
    error to a file with one regex:

        error in '<path>'[ line N]:

    An error that does not match is silently dropped — the comment in the
    grouper says so — and the file never gets a repair attempt. It still fails
    the final gate, so the run dies, but the model is never told which file to
    fix or what is wrong with it.

    Four validators were added over successive sessions emitting
    `<path> line N: ...` instead. Every one of them would have killed a story
    outright rather than repairing it, and nothing would have said why. The
    same hole cost a run before, under SCRUM-103, when the selector validator
    added a line number the regex did not tolerate.

WHY THIS TEST AND NOT A CONVENTION
    The convention was written down, in the docstring of the function that
    aggregates them, and four validators in a row ignored it — including ones
    added while reading that exact file. A convention nobody can violate
    accidentally is a test.
"""
import re
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.agent2_coder import (
    _collect_repairable_errors,
    _group_validator_errors_by_file,
)

# The shape the grouper reads. Kept here deliberately rather than imported:
# if someone loosens the regex to make a failing validator pass, this test
# should still hold them to the documented contract.
_GROUPABLE = re.compile(r"error in '([^']+)'(?: line \d+)?:")


def _files_that_break_everything() -> list:
    """One generated batch violating as many repairable rules as possible.

    Deliberately awful. The point is to make every validator in the repairable
    set speak at once, so the format check covers all of them rather than the
    handful someone remembered to sample.
    """
    return [
        SimpleNamespace(
            file_path="pages/thing_page.py",
            is_new_file=True,
            content=textwrap.dedent('''
                from pages.base_page import BasePage


                class ThingPage(BasePage):
                    INVENTORY_PAGE = "no_such_page"

                    def open(self, base_url: str) -> None:
                        self.navigate(base_url)

                    def open_thing(self, name: str) -> None:
                        self.click(self.sel("no_such_key"))

                    def is_empty(self) -> bool:
                        return self.is_visible(self.sel("another_missing_key"))
            '''),
        ),
        SimpleNamespace(
            file_path="tests/step_defs/test_thing.py",
            is_new_file=True,
            content=textwrap.dedent('''
                from pytest_bdd import scenarios, then

                scenarios("thing.feature")


                @then("something")
                def assert_something(thing_page):
                    assert thing_page.sel("a_key")
                    assert thing_page.is_empty()
            '''),
        ),
    ]


def test_every_repairable_error_names_its_file_the_way_the_grouper_reads():
    errors = _collect_repairable_errors(_files_that_break_everything())

    assert errors, (
        "the deliberately broken batch produced no errors at all - this test "
        "would then pass without checking anything"
    )

    ungroupable = [e for e in errors if not _GROUPABLE.search(e)]
    assert not ungroupable, (
        "these errors reach the repair loop but name no file in the "
        "`error in '<path>'[ line N]:` shape, so the grouper drops them and "
        "the model is never told what to fix:\n  "
        + "\n  ".join(e[:160] for e in ungroupable)
    )


def test_the_grouper_actually_routes_them():
    """The format check above is textual. This one runs the real router and
    requires every error to land on a file."""
    errors = _collect_repairable_errors(_files_that_break_everything())
    grouped = _group_validator_errors_by_file(errors)

    routed = sum(len(v) for v in grouped.values())
    assert routed == len(errors), (
        f"{len(errors) - routed} of {len(errors)} errors were dropped by the "
        f"grouper. A dropped error kills the story at the final gate with no "
        f"repair attempt and no explanation."
    )
    for path in grouped:
        assert path.endswith(".py"), f"routed to a non-file: {path!r}"


def test_a_badly_shaped_error_is_caught_by_this_test():
    """Break the thing the guard guards.

    If the regex were loosened, or the grouper made lenient, this test would
    quietly stop protecting anything.
    """
    assert not _GROUPABLE.search("pages/thing_page.py line 7: something wrong")
    assert _GROUPABLE.search(
        "Method naming error in 'pages/thing_page.py' line 7: something wrong")


def test_the_repairable_set_is_not_empty():
    """A sanity floor: if _collect_repairable_errors is ever refactored into
    returning nothing, both tests above would pass vacuously."""
    from agents import agent2_coder

    source = Path(agent2_coder.__file__).read_text(encoding="utf-8")
    body = source.split("def _collect_repairable_errors", 1)[1]
    body = body.split("\ndef ", 1)[0]

    assert body.count("errors.extend(") >= 5, (
        "the repairable set has shrunk unexpectedly - check nothing was "
        "removed while making this test pass"
    )