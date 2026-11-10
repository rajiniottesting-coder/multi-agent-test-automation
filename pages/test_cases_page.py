"""
TestCasesPage — the Test Cases listing screen.

Brand-new page object for https://automationexercise.com/test_cases.

Conventions (copied from pages/login_page.py):
  - SELECTORS COME FROM THE APP INVENTORY, never a literal here. Declare
    INVENTORY_PAGE, then self.sel("<element key>").
  - methods are business verbs that name WHAT they act on.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

Readiness: the inventory names no explicit `readiness` key, so this page uses
the heading (test_cases_heading), which is present in every state the page can
be in — there is no search-driven view that replaces it, and only the title /
step lists change when a title is clicked.

NOTE on the heading's case (SCRUM-293): the page renders the heading in capitals
via CSS (text-transform), so the DOM text reads "TEST CASES" while the test case
says "Test Cases". heading_matches() therefore compares case-insensitively; the
raw heading_text() reader is left unchanged for any caller that wants the exact
rendered text.

NOTE on the "Feedback for Us" section (SCRUM-312): the inventory for the
`test_cases` page DOES carry a key for the Feedback email link
(feedback_automationexercise_com_link) and the Feedback section container
(feedback_element). SCRUM-312 can therefore be fully asserted: the feedback
email link is reached through the inventory key, no invented selector required.

NOTE on showing a test case's steps (SCRUM-313 / SCRUM-314): `test_case_steps`
is a multi_match family — one step item per step, across every (collapsed)
panel — so wait_visible() on the family raises a strict-mode violation. Instead
this page confirms a test case's steps became visible by waiting for AT LEAST
ONE member of the family to appear (wait_for_any), which is a legal, read-only
family operation. Steps live inside a collapsible panel that expands in place
after a title is clicked; clicking does not navigate — the browser stays on the
Test Cases page, which remaining_on_page() confirms via the URL.

NOTE on search/filter (SCRUM-335 / SCRUM-336 / SCRUM-337): the inventory carries
test_case_search_input, a single keyword box. Submitting it filters the title
family in place — the page stays on /test_cases — so the search helpers below
read titles through the title family (a legal plural operation), enter the
keyword, and submit with Enter. `test_case_titles` is multi_match, so titles are
read with get_all_texts() and existence with wait_for_any(), never waited on,
clicked or probed with is_gone() as a whole — doing so raises a strict-mode
violation.

NOTE on asserting NO titles remain (SCRUM-336): the no-match state is confirmed
by WAITING the title family's count down to zero with wait_for_count(), not by a
snapshot get_count() that reads once and races the in-place filter update, and
not by is_gone()/wait_visible() on the family (a strict-mode violation).
is_titles_absent() proves the page first (is_loaded() — the heading is a single,
permanent element) and then waits for the family's count to settle at zero.
"""
from typing import List, Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class TestCasesPage(BasePage):
    """Test Cases listing. Selectors: see `test_cases` in the app inventory.

    The title links (test_case_titles) and step items (test_case_steps) are
    both families — one per test case / one per step — so they are read and
    acted on through family-aware BasePage helpers, never clicked or waited on
    as a whole.
    """

    INVENTORY_PAGE = "test_cases"

    # ── navigation ───────────────────────────────────────────
    def open_test_cases(self, base_url: str) -> None:
        """Navigate directly to the Test Cases page.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Test Cases page is on screen. WAITS for the heading.

        Call this where being on the page is the expected state. A step asking
        this to branch would pay the full timeout whenever it is not loaded.
        """
        return self.is_showing(self.sel("test_cases_heading"), timeout_ms=timeout_ms)

    def is_on_test_cases_page(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the browser is on the Test Cases page. WAITS.

        Confirms both that this page's readiness heading is showing AND that
        the URL path matches the one this page declares in the inventory, so a
        step asserting "I should be on the Test Cases page" is answered
        directly rather than by inference from some other element.
        """
        return self.is_loaded(timeout_ms=timeout_ms) and (
            self.get_path().rstrip("/") == self.page_url().rstrip("/")
        )

    def heading_text(self) -> str:
        """Visible text of the page heading. WAITS for it to appear.

        Returns the raw rendered text, which CSS renders in capitals
        ("TEST CASES"). Use heading_matches() when comparing against an
        expected heading that is not upper-cased.
        """
        self.wait_visible(self.sel("test_cases_heading"))
        return self.get_text(self.sel("test_cases_heading"))

    def heading_matches(self, expected: str) -> bool:
        """True if the page heading matches `expected`, ignoring letter case.

        The heading is rendered in capitals via CSS, so the DOM text differs
        from the test case ("TEST CASES" vs "Test Cases") in case only. WAITS
        for the heading, then compares case-insensitively.
        """
        return self.heading_text().strip().casefold() == expected.strip().casefold()

    def has_title_links(self) -> bool:
        """True once at least one test case title link is rendered. WAITS.

        Call this where titles-as-links is the expected state. A step asking
        this to branch would pay the full timeout whenever there are none.
        """
        self.wait_for_any(self.sel("test_case_titles"))
        return True

    def all_titles_are_links(self) -> bool:
        """True if every rendered title is an <a> element. WAITS for at least one.

        The title family selector targets anchors (.panel-title a), so any
        match is already a link; this confirms at least one exists and that
        every member carries an href.
        """
        self.wait_for_any(self.sel("test_case_titles"))
        for index in range(self.get_count(self.sel("test_case_titles"))):
            href = self.get_nth_attribute(self.sel("test_case_titles"), index, "href")
            if href is None:
                return False
        return True

    def has_feedback_email_link(self) -> bool:
        """True once the Feedback for Us email link is displayed. WAITS for it.

        The inventory carries feedback_automationexercise_com_link, an ARIA
        link named for the feedback email address, so this asserts the section
        offers an email address as a link. Call this where the link is the
        expected state; it waits up to the timeout and times out if absent.
        """
        return self.is_showing(self.sel("feedback_automationexercise_com_link"))

    def has_visible_steps(self) -> bool:
        """True once at least one step item is present. WAITS for the family.

        Steps live inside collapsed panels until a title is clicked, so call
        this only AFTER expanding a test case. `test_case_steps` is a
        multi_match family, so it is never waited on with wait_visible() (that
        raises in strict mode) — instead this waits for AT LEAST ONE member to
        exist, which is a legal, read-only family operation.
        """
        self.wait_for_any(self.sel("test_case_steps"))
        return True

    def remaining_on_page(self) -> bool:
        """True if the browser is still on the Test Cases page. WAITS for it.

        Clicking a title expands a panel in place rather than navigating, so
        the URL must be unchanged after the click. Built on is_loaded() (a
        waiting heading probe) and a trailing-slash-tolerant URL comparison, so
        it answers "yes, still here" reliably even while the panel is still
        expanding.
        """
        return self.is_loaded() and self.get_path().rstrip("/") == self.page_url().rstrip("/")

    # ── search / filter queries ──────────────────────────────
    def title_texts(self) -> List[str]:
        """All currently displayed test case titles, in DOM order. WAITS.

        `test_case_titles` is a multi_match family — one link per test case —
        so it is read through get_all_texts(), a legal plural operation, never
        clicked or waited on as a whole. WAITS for at least one title first so
        the baseline / filtered list is captured after the page has rendered
        rather than before. Call this only where titles ARE expected (the
        baseline list and a keyword that matches something); for the no-match
        case use is_titles_absent(), which does not wait for titles to appear.
        """
        self.wait_for_any(self.sel("test_case_titles"))
        return self.get_all_texts(self.sel("test_case_titles"))

    def is_titles_absent(self) -> bool:
        """True once no test case title is displayed. WAITS for the title family
        to settle at zero; returns True once none remains, times out otherwise.

        The expected state after a keyword that matches nothing (SCRUM-336).
        `test_case_titles` is a multi_match family, so it must NOT be probed
        with is_gone()/wait_visible() — that raises a strict-mode violation.
        Instead this proves the page first with is_loaded() (the heading is a
        single, permanent element so a blank screen cannot pass), then WAITS for
        the title family's count to reach zero via wait_for_count(), which
        retries until the timeout and logs both numbers if it never settles —
        rather than a snapshot get_count() that reads once and races the
        in-place filter update.
        """
        if not self.is_loaded():
            return False
        self.wait_for_count(self.sel("test_case_titles"), 0)
        return True

    # ── search / filter actions ──────────────────────────────
    def search_test_cases_for(self, keyword: str) -> None:
        """Enter a keyword into the search box and submit it.

        Confirms it is ON this page first: filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a broken selector when the page is
        simply wrong. Submits with Enter, which filters the title family in
        place without navigating away from /test_cases.
        """
        self.require_own_page()
        self.fill(self.sel("test_case_search_input"), keyword)
        self.press_key(self.sel("test_case_search_input"), "Enter")

    def clear_keyword_and_search(self) -> None:
        """Empty the search box, then submit an empty keyword.

        Used by SCRUM-337: clearing the filter and re-searching restores the
        baseline list. Clears the field, then submits with Enter so the page
        re-renders the full set of titles in place.
        """
        self.require_own_page()
        self.clear(self.sel("test_case_search_input"))
        self.press_key(self.sel("test_case_search_input"), "Enter")

    # ── actions ──────────────────────────────────────────────
    def open_first_test_case(self) -> None:
        """Click the first test case title to expand its steps in place.

        The title family matches one link per test case; this acts on the
        first member by index. Clicking does not navigate — the panel below
        the title expands to reveal its steps.
        """
        self.require_own_page()
        self.click_nth(self.sel("test_case_titles"), 0)

    def open_second_test_case(self) -> None:
        """Click the second test case title to expand its steps in place.

        The title family matches one link per test case; this acts on the
        second member (index 1) by position. Like the first, clicking does not
        navigate — the panel below the title expands to reveal its steps.
        """
        self.require_own_page()
        self.click_nth(self.sel("test_case_titles"), 1)
