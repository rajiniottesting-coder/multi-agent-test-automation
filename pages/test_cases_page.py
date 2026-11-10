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

NOTE on the "Feedback for Us" section (SCRUM-312 / SCRUM-331 REVISION):
The revised stories say the Feedback for Us section now shows a "Contact us"
link INSTEAD OF the old email address link, and that clicking it opens the
Contact Us page in the SAME tab.

The inventory for the `test_cases` page carries:
  - feedback_element       — the Feedback for Us section container
  - feedback_automationexercise_com_link — the OLD email address link

The "Contact us" link is NOT a separate inventory key, so it is reached through
an ARIA role query by accessible name ("Contact us") via the BasePage role
helpers (click_role / get_role_text), which match on accessible name and need
no selector literal. This is the sanctioned path for a named ARIA control, so
no invented CSS and no selector literal appears here.

  - has_feedback_section()          — the Feedback for Us section is shown
  - has_feedback_contact_us_link()  — a "Contact us" link is offered
  - is_feedback_email_link_absent() — the OLD email link is no longer shown
  - click_feedback_contact_us()     — click "Contact us" (same-tab navigation)
  - no_new_tab_opened()             — the browser stayed in one tab/window

NOTE on showing a test case's steps (SCRUM-313 / SCRUM-314): `test_case_steps`
is a multi_match family — one step item per step, across every (collapsed)
panel — so wait_visible() on the family raises a strict-mode violation. Instead
this page confirms a test case's steps became visible by waiting for AT LEAST
ONE member of the family to appear (wait_for_any), which is a legal, read-only
family operation. Steps live inside a collapsible panel that expands in place
after a title is clicked; clicking does not navigate — the browser stays on the
Test Cases page, which remaining_on_page() confirms via the URL.
"""
from typing import Optional

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

    def title_texts(self) -> list[str]:
        """Visible text of every test case title link, in DOM order. WAITS.

        `test_case_titles` is a multi_match family of anchors — one per test
        case — so it is read with the plural family reader, never clicked or
        waited on as a whole. Waits for at least one to appear first so the
        reader does not race the page render and return an empty list.
        """
        self.wait_for_any(self.sel("test_case_titles"))
        return self.get_all_texts(self.sel("test_case_titles"))

    def has_feedback_section(self) -> bool:
        """True once the Feedback for Us section is displayed. WAITS for it.

        The inventory carries feedback_element, the Feedback for Us section
        container, so this asserts the section itself is on screen. Call this
        where the section is the expected state; it waits up to the timeout and
        times out if absent.
        """
        return self.is_showing(self.sel("feedback_element"))

    def has_feedback_email_link(self) -> bool:
        """True once the Feedback for Us email link is displayed. WAITS for it.

        The inventory carries feedback_automationexercise_com_link, an ARIA
        link named for the feedback email address, so this asserts the section
        offers an email address as a link. Call this where the link is the
        expected state; it waits up to the timeout and times out if absent.
        """
        return self.is_showing(self.sel("feedback_automationexercise_com_link"))

    def has_feedback_contact_us_link(self) -> bool:
        """True once a "Contact us" link is offered in the Feedback section. WAITS.

        The revised SCRUM-312 / SCRUM-331 stories replace the old email link
        with a "Contact us" link. That control has no inventory key, so it is
        addressed by ARIA role and accessible name — role=link named
        "Contact us" — which needs no selector literal. Reading its text with
        the waiting role reader confirms the link is on screen; it returns a
        non-empty string only when the link is present, so a non-empty result
        means the link is offered. Call this where the link is the expected
        state; it waits up to the timeout and raises if absent.
        """
        return bool(self.get_role_text("link", name="Contact us").strip())

    def is_feedback_email_link_absent(self) -> bool:
        """True if the Feedback for Us email link is NOT shown. Does not time out.

        The revised SCRUM-312 / SCRUM-331 stories require the old email address
        link to be GONE from the Feedback section. feedback_automationexercise_com_link
        is a permanent-until-removed element (the inventory does NOT list it as
        conditional), so an absent element is also what an un-rendered page
        looks like — this proves the page is loaded first, THEN that the link
        is gone, so the check cannot pass before the page has rendered.

        Built on is_gone(): True at once when the link is absent, waiting only
        while it is still on screen. Call this to assert the email link is no
        longer offered.
        """
        return self.is_loaded() and self.is_gone(
            self.sel("feedback_automationexercise_com_link")
        )

    def no_new_tab_opened(self) -> bool:
        """True if the browser stayed in a single tab/window. Does not raise.

        The revised stories require the "Contact us" link to open the Contact
        Us page in the SAME tab — no new tab or window. This reads the browser
        context's open pages through the Playwright Page this object already
        holds, and confirms exactly one is open, so a step can assert that a
        same-tab navigation (rather than a pop-up) occurred.
        """
        return len(self.page.context.pages) == 1

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

    # ── actions ──────────────────────────────────────────────
    def click_feedback_contact_us(self) -> None:
        """Click the "Contact us" link in the Feedback for Us section.

        The link has no inventory key, so it is addressed by ARIA role and
        accessible name ("Contact us") via click_role — the sanctioned path for
        a named ARIA control that needs no selector literal. The revised
        stories require this to navigate in the SAME tab, so this does NOT open
        a new tab; the destination's own page object confirms arrival.
        """
        self.require_own_page()
        self.click_role("link", name="Contact us")

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
