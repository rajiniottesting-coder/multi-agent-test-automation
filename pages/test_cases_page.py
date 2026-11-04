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

NOTE on the "Feedback for Us" section (SCRUM-312): the inventory for the
`test_cases` page lists NO element for the Feedback section or its email
address. There is therefore no legal selector to read it, so that part of
SCRUM-312 cannot be asserted from this page object. The feature verifies the
heading and the title-links layout only; the Feedback section is recorded in
`notes` for a human to add an inventory key.

NOTE on showing a test case's steps (SCRUM-313): `test_case_steps` is a
multi_match family — one step item per step, across every (collapsed) panel —
so wait_visible() on the family raises a strict-mode violation. Instead this
page confirms the first test case's steps became visible by waiting for AT
LEAST ONE member of the family to appear (wait_for_any), which is a legal,
read-only family operation. Steps live inside a collapsible panel that expands
in place after the first title is clicked; clicking does not navigate.
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

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Test Cases page is on screen. WAITS for the heading.

        Call this where being on the page is the expected state. A step asking
        this to branch would pay the full timeout whenever it is not loaded.
        """
        return self.is_showing(self.sel("test_cases_heading"), timeout_ms=timeout_ms)

    def heading_text(self) -> str:
        """Visible text of the page heading. WAITS for it to appear."""
        self.wait_visible(self.sel("test_cases_heading"))
        return self.get_text(self.sel("test_cases_heading"))

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

    # ── actions ──────────────────────────────────────────────
    def open_first_test_case(self) -> None:
        """Click the first test case title to expand its steps in place.

        The title family matches one link per test case; this acts on the
        first member by index. Clicking does not navigate — the panel below
        the title expands to reveal its steps.
        """
        self.require_own_page()
        self.click_nth(self.sel("test_case_titles"), 0)
