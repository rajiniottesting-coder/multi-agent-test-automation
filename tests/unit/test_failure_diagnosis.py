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


# =========================================================================
# A ROW THAT IS NOT IN THE LIST
#
# click_in_row() raises a careful message naming two selector-shaped causes -
# the text is not exact, or the row locator matches the text element rather
# than the container. It came back `unclassified`, so the reader got the
# generic "open the trace" advice instead.
#
# And the commonest cause in a multi-step scenario is neither of the two the
# message names: the list was FILTERED. A scenario searches for one record,
# adds it, then asks for a second record that the search has hidden. Nothing
# is wrong with the selector or the text; the row is genuinely not displayed.
# =========================================================================

_ROW_NOT_FOUND = """pages/base_page.py:590: in click_in_row
    raise AssertionError(
E   AssertionError: No row matching `.card-wrapper` contains 'Second Item'. Check
    the text is exact and that the row locator matches the repeating CONTAINER
    rather than the text element inside it."""


def test_a_missing_row_is_classified():
    d = diagnose(_ROW_NOT_FOUND)
    assert d.label == "row not present in the list", (
        f"got {d.label!r} - this arrived as 'unclassified' from CI"
    )


def test_the_reading_names_the_filtered_list_first():
    """The two causes click_in_row already names are in its own message. The
    value this adds is the one it does not: the previous step narrowed the
    list. Naming it third would bury it."""
    d = diagnose(_ROW_NOT_FOUND)
    body = (d.cause + " " + d.remedy).lower()

    assert "filter" in body, "the list may be filtered - the usual cause"
    assert "step before" in body or "previous" in body, (
        "point at the step that narrowed the list, which is where the fix is"
    )
    assert "casing" in body or "exact" in body, "keep the text-mismatch cause"
    assert "container" in body, "keep the row-locator cause"


# =========================================================================
# A value expected among texts the step read
#
# The literal `assert 'X' in [...]` form was matched. Two other spellings of
# the SAME failure were not, and both arrived from CI as "unclassified":
#
#   any(v in t for t in texts)          a comprehension over a family
#   "Expected ..., got ['a', 'b']"      a custom assertion message
#
# The real one was a step asserting one KIND of value against a family that
# only ever yields another. That is a third cause the old reading did not
# carry: not a snapshot, not starting state, but an assertion that could
# not have passed on any data in any run. Sending that reader to
# wait_for_row() or to a fresh-account fixture wastes the investigation.
# =========================================================================

# App-agnostic by construction: this file is a framework file, so the shape
# of the failure is reproduced and the application's own nouns are not.
_WRONG_KIND = """tests/step_defs/test_thing.py:180: in assert_attribute_among_results
    assert any(attribute in label for label in labels), (
E   AssertionError: Expected a result showing attribute 'ATTR-1', got ['First Label', 'Second Label', 'Third Label']
E   assert False
E    +  where False = any(<generator object assert_attribute_among_results.<locals>.<genexpr> at 0x7f>)"""

_LITERAL_LIST = "E   assert 'Second Item' not in ['First Item', 'Second Item']"

_ALL_FORM = "E   assert all(wanted in text for text in texts)"


def test_a_comprehension_membership_test_is_classified():
    d = diagnose(_WRONG_KIND)
    assert d.label == "membership assertion", (
        f"got {d.label!r} - this arrived as 'unclassified' from CI"
    )


def test_the_all_spelling_is_classified_too():
    assert diagnose(_ALL_FORM).label == "membership assertion"


def test_the_literal_list_form_still_reads_the_same():
    """The branch that already worked must not change."""
    assert diagnose(_LITERAL_LIST).label == "membership assertion"


def test_the_reading_names_the_wrong_kind_cause():
    """The cause the old text did not carry, and the reason it matters."""
    d = diagnose(_WRONG_KIND)
    body = (d.cause + " " + d.remedy).lower()

    assert "kind" in body, "the expected value may not be that kind of thing"
    assert "could never have passed" in body or "never" in body, (
        "say that no run would have passed it - that is what rules out "
        "waiting and starting state in one step"
    )
    assert "inventory key" in body, (
        "point at the fix: find the key that carries the value, or accept "
        "the value is not readable on that page"
    )


def test_the_snapshot_and_starting_state_causes_are_kept():
    """Widening must not drop the two readings that were already right."""
    body = (diagnose(_LITERAL_LIST).cause + " " + diagnose(_LITERAL_LIST).remedy).lower()
    assert "snapshot" in body, "keep the snapshot cause"
    assert "survives the run" in body, "keep the starting-state cause"
    assert "wait_for_row" in body, "keep the remedy that fixes the timing case"


def test_the_widened_pattern_steals_nothing():
    """Each of these has its own reading and must keep it.

    The ordering hazard is already documented in this module: a pattern that
    matches more than it should takes a case away from a signature whose
    remedy is the opposite one.
    """
    others = {
        "element present but hidden": _HIDDEN_LOG,
        "element found but empty": "E   AssertionError: Expected 'qa_user', got ''",
        "row not present in the list": _ROW_NOT_FOUND,
        "multi-match selector":
            "E   Error: strict mode violation: locator('.x') resolved to 3 elements",
        "result-count assertion":
            "E   AssertionError: assert '12 results found' == '3 results found'",
    }
    for expected_label, text in others.items():
        assert diagnose(text).label == expected_label, (
            f"the widened membership pattern stole {expected_label!r}"
        )


# =========================================================================
# A PLAIN locator() THAT NEVER RESOLVED
#
# The never-resolved signature listed the get_by_* engines and not `locator`.
# But self.sel() yields a CSS or attribute selector for most elements, so the
# log reads
#
#     waiting for locator("[data-qa='...']")
#
# which fell through to the generic "timed out" reading. That reading says the
# element is present but not actionable - covered, disabled, animating - and
# the truth is the opposite: a wait that never resolved means ZERO matches.
#
# Thirty seconds lost, and the reader sent to inspect an overlay that was
# never there, on a page the browser had never reached.
#
# Safe to add because the discriminator is the negative lookahead on "locator
# resolved to", not the engine name.
# =========================================================================

_PLAIN_LOCATOR_NEVER_RESOLVED = """E   playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.
E   Call log:
E   waiting for locator("[data-qa='some-field']")"""


def test_a_plain_locator_that_never_resolved_is_read_as_the_wrong_page():
    d = diagnose(_PLAIN_LOCATOR_NEVER_RESOLVED)
    assert d.label == "element never appeared - probably the wrong page", (
        f"got {d.label!r} - the generic 'timed out' reading claims the element "
        f"is present but not actionable, which is the opposite of what a wait "
        f"with zero matches means"
    )


def test_a_plain_locator_that_DID_resolve_is_still_the_hidden_reading():
    """Break the thing the guard guards.

    Widening the engine list must not steal the hidden case, whose remedy is
    the opposite. The lookahead on "locator resolved to" is what separates
    them, and it has to keep doing so.
    """
    resolved = (
        "E   TimeoutError: Locator.click: Timeout 30000ms exceeded.\n"
        "E   Call log:\n"
        "E   waiting for locator(\"#thing\")\n"
        "E     locator resolved to <div id=thing></div>\n"
        "E   - unexpected value \"hidden\""
    )
    assert diagnose(resolved).label != "element never appeared - probably the wrong page"


# =========================================================================
# ACTED ON THE WRONG PAGE
#
# A page object raised a clear, specific message - and the classifier said
# "unclassified", so the reader got the generic "open the trace" advice
# instead of the one thing worth knowing: the step that raised is rarely at
# fault. Something BEFORE it navigated away.
# =========================================================================

_WRONG_PAGE = """E   AssertionError: sign_in() was called while the browser is at
    https://app.example/collection, not on /signin. The credential fields are
    not on this page."""


def test_acting_on_the_wrong_page_is_classified():
    d = diagnose(_WRONG_PAGE)
    assert d.label == "acted on the wrong page", (
        f"got {d.label!r} - this arrived as 'unclassified' from CI"
    )


def test_the_reading_points_at_the_step_that_navigated():
    """The value is not restating the message - it is naming the cause, which
    is a step earlier in the scenario."""
    body = (diagnose(_WRONG_PAGE).cause + " " + diagnose(_WRONG_PAGE).remedy).lower()
    assert "before" in body, "the fault is upstream of the step that raised"
    assert "precondition" in body, "name the commonest culprit"
    assert "after the sign-in" in body or "signed-in" in body, (
        "account-scoped state has an ordering requirement of its own"
    )

