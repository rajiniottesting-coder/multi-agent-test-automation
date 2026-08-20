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