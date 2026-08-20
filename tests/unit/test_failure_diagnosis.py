"""A failure's reading must point at the right thing.

Playwright reports "expected to be visible" for both a missing element and one
that is in the DOM and not shown. Those are opposite problems, and the advice
for one is wasted effort on the other.
"""
from core.failure_diagnosis import diagnose


# ─────────────────────────────────────────────────────────────────────────
# Present-but-hidden is not the same failure as not-found
#
# Playwright reports both as "expected to be visible". The readiness-probe
# entry then advised checking the selector against the live page - advice that
# is exactly wrong when the call log says the locator RESOLVED, because the
# selector and the page are both right and only the app's state is not.
#
# A reader following that advice verifies a correct selector, finds nothing
# wrong, and is no closer. Ordering this pattern first costs nothing and
# removes a whole class of wasted investigation.
# ─────────────────────────────────────────────────────────────────────────

_HIDDEN_LOG = '''E   AssertionError: Locator expected to be visible
E   Actual value: False
E     - waiting for locator("text=Some banner")
E     -   locator resolved to <b>Some banner</b>
E     -   unexpected value "hidden"'''

_NOT_FOUND_LOG = '''E   AssertionError: Locator expected to be visible
E   Actual value: False
E     - waiting for locator("#never-rendered")'''


def test_a_hidden_element_is_classified_separately():
    d = diagnose(_HIDDEN_LOG)
    assert d is not None, "the hidden case must not fall through to unclassified"
    assert "hidden" in d.label.lower()


def test_the_hidden_remedy_does_not_send_the_reader_to_the_selector():
    d = diagnose(_HIDDEN_LOG)
    assert "do not go looking at the selector" in d.remedy.lower(), \
        "the selector is correct here - saying otherwise wastes the reader's time"
    assert "state" in d.remedy.lower()


def test_the_hidden_remedy_names_the_commonest_cause():
    """Account data surviving a run is what produced this failure twice."""
    d = diagnose(_HIDDEN_LOG)
    assert "survives" in d.remedy.lower() or "leftover" in d.remedy.lower()


def test_a_missing_element_still_gets_the_selector_advice():
    """The mirror. Ordering the hidden pattern first must not swallow the case
    where checking the selector IS the right move."""
    d = diagnose(_NOT_FOUND_LOG)
    assert d is not None
    assert "hidden" not in d.label.lower(), \
        "an element that never resolved is not a hidden element"


# ─────────────────────────────────────────────────────────────────────────
# A wait that never resolved is a THIRD case
#
# A trace showed a navigation click at +3.7s, the next action starting at
# +4.3s and waiting the full 30 seconds for an element that only exists on the
# destination, and a screenshot at +34.9s showing that destination loaded and
# looking perfectly healthy. Nothing in the evidence pointed at the cause: an
# ad interstitial had swallowed the navigation, parked the URL on a fragment,
# and released it after the wait had already given up.
#
# Three outcomes, three different remedies:
#   never resolved  - the element is on a page the browser never reached
#   resolved hidden - right page, right selector, wrong application state
#   resolved, stuck - present and not actionable: covered, disabled, animating
# ─────────────────────────────────────────────────────────────────────────

_NEVER_RESOLVED = '''E   playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.
E   Call log:
E   waiting for get_by_placeholder("Some hint text")'''


def test_a_wait_that_never_resolved_is_classified_as_the_wrong_page():
    d = diagnose(_NEVER_RESOLVED)
    assert d is not None
    assert "never appeared" in d.label.lower()


def test_that_remedy_names_the_interstitial():
    d = diagnose(_NEVER_RESOLVED)
    assert "interstitial" in d.remedy.lower(), \
        "an ad swallowing the first navigation is the commonest cause and the " \
        "evidence never shows it"
    assert "screenshot" in d.remedy.lower(), \
        "the screenshot looks healthy and proves nothing - say so"


def test_it_does_not_steal_the_hidden_case():
    """The first version of this pattern matched any 'waiting for locator' line
    and hijacked the hidden diagnosis, whose remedy is the opposite."""
    assert "hidden" in diagnose(_HIDDEN_LOG).label.lower()


# =========================================================================
# THE CLASSIFIER MUST BE GIVEN THE TEXT THAT CLASSIFIES
#
# Every test above hands diagnose() a raw Playwright error. The pytest hook
# never had one to hand it. is_showing() catches the Playwright error by
# design and logs it, so a readiness assertion arrives as `assert False` and
# nothing else, and the sentence that names the cause is in the CAPTURED LOG.
# report.caplog carries it; str(report.longrepr) does not.
#
# The hook passed str(report.longrepr). So the whole probe class - the one
# this module was written for - came back "unclassified" in CI while the
# framework's own reading of it was printed six lines higher up. Nine months
# of green unit tests, because the guard tested the function and the bug was
# in the argument.
#
# These run a REAL failing pytest session through the real hook body and read
# what comes out, and one of them asserts the old behaviour still fails.
# =========================================================================

_PROBE_TRACEBACK = """tests/step_defs/test_x.py:151: in assert_state
    assert some_page.is_empty(), "Expected the collection to be empty"
E   AssertionError: Expected the collection to be empty
E   assert False
E    +  where False = is_empty()"""

_PROBE_CAPLOG = (
    "WARNING  pages.base_page:base_page.py:538 SomePage.is_showing("
    "\'text=Nothing here\') is False after 30000 ms at http://app.test/x "
    "\u2014 `text=Nothing here` is PRESENT in the DOM but HIDDEN at "
    "http://app.test/x."
)


def test_the_traceback_alone_is_not_enough():
    """The negative control. If this ever starts passing, the widening below
    is no longer load-bearing and the reason for it has been lost."""
    from core.failure_diagnosis import diagnose

    assert diagnose(_PROBE_TRACEBACK).label == "unclassified", (
        "the traceback of a swallowed probe failure carries no signature - "
        "that is the whole reason the captured log has to be read too"
    )


def test_the_captured_log_rescues_it():
    from core.failure_diagnosis import diagnose_with_context

    d = diagnose_with_context(_PROBE_TRACEBACK, _PROBE_CAPLOG)
    assert d.label == "element present but hidden", (
        f"expected the hidden reading once the log is included, got {d.label!r}"
    )


def test_widening_never_overrides_a_reading_that_already_matched():
    """Widening must be a fallback, not a re-read. A log line from an earlier
    retry can contain any signature going; if it could displace a traceback
    that already classified, this change would break correct readings."""
    from core.failure_diagnosis import diagnose, diagnose_with_context

    noise = "Timeout 30000ms exceeded. ModuleNotFoundError: no such thing"
    for sample in (_HIDDEN_LOG, _NOT_FOUND_LOG, _NEVER_RESOLVED):
        assert diagnose_with_context(sample, noise) is diagnose(sample), (
            "supplementary text changed a reading that the primary text had "
            "already made"
        )


def test_no_supplementary_text_behaves_exactly_like_diagnose():
    from core.failure_diagnosis import diagnose, diagnose_with_context

    for sample in (_HIDDEN_LOG, _NOT_FOUND_LOG, _NEVER_RESOLVED, ""):
        assert diagnose_with_context(sample) is diagnose(sample)


def _run_probe_session(tmp_path, hook_body: str) -> str:
    """Run one failing pytest session in tmp_path and return its output.

    The failure is shaped exactly like the probe class: a helper module logs
    at WARNING and returns False, and the test asserts on the return value.
    The warning must come from a DIFFERENT module than the test, or pytest
    inlines the call into the traceback and the point is lost.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]

    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "probe_helper.py").write_text(
        "import logging\n"
        "logger = logging.getLogger('pages.base_page')\n"
        "def is_empty():\n"
        "    logger.warning(%r)\n"
        "    return False\n" % _PROBE_CAPLOG.split("base_page.py:538 ")[1],
        encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text(
        "import sys, pytest\n"
        f"sys.path.insert(0, {str(root)!r})\n" + hook_body,
        encoding="utf-8",
    )
    (tmp_path / "test_probe.py").write_text(
        "from probe_helper import is_empty\n"
        "def test_probe():\n"
        "    assert is_empty(), 'Expected the collection to be empty'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
         str(tmp_path)],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    return result.stdout + result.stderr


_REAL_HOOK = """
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        from core.failure_diagnosis import attach_diagnosis
        attach_diagnosis(report)
"""

_OLD_HOOK = """
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        from core.failure_diagnosis import diagnose
        d = diagnose(str(report.longrepr))
        report.sections.append(
            ("Why this failed", "CAUSE (%s): %s" % (d.label, d.cause)))
"""


def test_a_real_failing_session_gets_the_right_reading(tmp_path):
    """End to end through the hook body tests/conftest.py actually installs."""
    output = _run_probe_session(tmp_path, _REAL_HOOK)

    assert "element present but hidden" in output, (
        "a real probe-shaped failure was not classified by the hook:\n" + output
    )
    assert "CAUSE (unclassified)" not in output, (
        "the hook still reported a classifiable failure as unclassified"
    )


def test_the_guard_fails_against_the_version_that_had_the_bug(tmp_path):
    """Break the thing the guard guards.

    A guard that has never failed has not been tested. This runs the OLD hook -
    traceback only - and requires it to produce exactly the unclassified
    verdict seen in CI. If this stops holding, the test above is passing for
    some reason other than the fix.
    """
    output = _run_probe_session(tmp_path, _OLD_HOOK)

    assert "CAUSE (unclassified)" in output, (
        "the pre-fix hook should still misread this failure; if it no longer "
        "does, this probe no longer reproduces the bug and proves nothing:\n"
        + output
    )