"""Gherkin steps, and the evidence for a failure, must reach the report.

allure-pytest reports PYTEST, and this suite is written in Gherkin. So a
scenario arrived as one row - passed or failed, with a duration - and which
of its five steps failed was nowhere. For a reader who did not write the test
that is the only thing worth knowing, and for a client it is the difference
between "the cart test failed" and "it logged in, searched and added the
product, then failed removing it".

The same gap swallowed the evidence. attach_diagnosis writes its CAUSE/FIX
reading into report.sections, which pytest prints and junit.xml carries and
allure-pytest never reads; the screenshot, video and trace sit on disk under
names nobody following a report will guess.

Both are wiring. Everything reported here already existed.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

_PROJECT = Path(__file__).resolve().parents[2]


def test_a_step_is_titled_the_way_the_feature_file_wrote_it():
    """`When I search for "a thing"`, keyword included.

    A reader scanning a failed scenario is looking for where the
    Given/When/Then arc broke, and a bare phrase makes them count.
    """
    from core.allure_steps import _title

    step = SimpleNamespace(keyword="When", name='I search for "a thing"')
    assert _title(step) == 'When I search for "a thing"'

    # A step with no keyword still reads, rather than starting with a space.
    assert _title(SimpleNamespace(keyword="", name="something")) == "something"


def test_the_step_hooks_are_wired_into_conftest():
    """A reporter nothing calls is this project's recurring shape.

    pytest-bdd announces every step it runs; the gap was that nothing was
    listening, and a module that listens but is never registered is the same
    gap with more code.
    """
    body = " ".join((_PROJECT / "tests" / "conftest.py").read_text(
        encoding="utf-8").split())

    for hook in ("pytest_bdd_before_step_call", "pytest_bdd_after_step",
                 "pytest_bdd_step_error"):
        assert f"def {hook}(" in body, f"{hook} is not registered"

    assert "start_step(request, step)" in body
    assert "fail_step(request, exception)" in body, (
        "without this the failing step is never marked, and the report shows "
        "a scenario that failed with every step green"
    )


def test_the_failing_step_is_the_one_marked():
    """The point of the exercise: earlier steps stay passed.

    Verified on the module's own bookkeeping rather than through Allure,
    which needs a live reporter - the end-to-end proof is a generated report
    showing four green steps and a fifth red.
    """
    from core import allure_steps

    if not allure_steps._ALLURE:
        pytest.skip("allure-pytest not installed")

    node = SimpleNamespace()
    request = SimpleNamespace(node=node)
    step = SimpleNamespace(keyword="Then", name="it fails")

    allure_steps.start_step(request, step)
    assert id(node) in allure_steps._open_step, "the step never opened"

    allure_steps.fail_step(request, AssertionError("boom"))
    assert id(node) not in allure_steps._open_step, (
        "the step was left open - every later step would nest inside it and "
        "the report would be unreadable"
    )


def test_opening_a_step_closes_any_predecessor():
    """Break the thing the guard guards.

    A step left open by an error would nest the rest of the scenario inside
    it and make the report unreadable, so start_step closes any predecessor
    first.

    Checked on the SOURCE. The first version called start_step twice and
    asserted the open-step map held one entry - but the map is keyed by test
    node, so it holds one entry whether or not the predecessor was closed.
    It could not fail, which is the same as not existing.
    """
    source = (_PROJECT / "core" / "allure_steps.py").read_text(encoding="utf-8")
    body = source[source.index("def start_step("):source.index("def _close(")]

    close_at = body.index("_close(key, failed=False)")
    open_at = body.index("allure.step(")
    assert close_at < open_at, (
        "start_step creates the new step before closing the previous one, so "
        "an interrupted scenario nests every later step inside the one that "
        "failed"
    )


def test_the_evidence_attachment_is_wired_into_the_report_hook():
    body = " ".join((_PROJECT / "tests" / "conftest.py").read_text(
        encoding="utf-8").split())

    assert "attach_failure_evidence(report," in body, (
        "the screenshot, video, trace and the CAUSE/FIX reading are captured "
        "and never reach the report anybody is handed"
    )


def test_the_reading_is_attached_before_the_files(tmp_path):
    """An attachment list is read top-down, and the reading is the thing worth
    acting on. A screenshot above it invites scrolling past the answer."""
    source = (_PROJECT / "core" / "allure_steps.py").read_text(encoding="utf-8")

    reading_at = source.index('name="Why this failed"')
    files_at = source.index("_ATTACHMENTS:")
    assert reading_at < files_at, (
        "the evidence files are attached before the reading that explains them"
    )


def test_attaching_never_raises_on_a_missing_directory(tmp_path):
    """This runs while a test is already failing. Decorating a report must not
    turn one failure into two."""
    from core.allure_steps import attach_failure_evidence

    report = SimpleNamespace(sections=[], nodeid="tests/x.py::test_y")
    assert attach_failure_evidence(report, tmp_path / "nope") == 0