"""
TestCasesPage — the Test Cases listing screen.

New page object. The Test Cases page lists each test case title as a link and
offers a search box that filters the list client-side as text is typed.

Selectors: see `test_cases` in the app inventory. Titles are compared
case-insensitively here because the application renders them in a different case
than the human-readable test-case names used in the feature file.

The title family (`test_case_titles`) is MULTI-MATCH — one anchor per test case.
It is therefore only ever read through the plural helpers (get_all_texts /
wait_for_any / wait_for_row), never clicked, filled or asserted on as a whole.

App: https://automationexercise.com
"""
from typing import List, Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class TestCasesPage(BasePage):
    """Test Cases listing. Selectors: see `test_cases` in the app inventory."""

    INVENTORY_PAGE = "test_cases"

    # ── actions ──────────────────────────────────────────────
    def open_test_cases(self, base_url: str) -> None:
        """Navigate to the Test Cases page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a keyword into the search box to filter the list.

        Fills as its first action, so it confirms it is on this page first;
        otherwise Playwright would wait the full timeout on the field and
        blame the selector rather than the wrong page.
        """
        self.require_own_page()
        self.fill(self.sel("test_case_search_input"), term)

    def clear_search(self) -> None:
        """Empty the search box, restoring the full list."""
        self.require_own_page()
        self.clear(self.sel("test_case_search_input"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Test Cases heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("test_cases_heading"), timeout_ms=timeout_ms)

    def title_texts(self) -> List[str]:
        """Return every currently shown test case title, as a list of strings."""
        return self.get_all_texts(self.sel("test_case_titles"))

    def has_titles(self) -> bool:
        """True once at least one test case title is shown. WAITS for one.

        Call this only where titles are expected. For asserting NO titles are
        shown, use has_no_titles(), which does not wait for rows that are
        legitimately absent.
        """
        self.wait_for_any(self.sel("test_case_titles"))
        return True

    def has_no_titles(self) -> bool:
        """True once no test case title is shown. WAITS while any remain.

        For the empty-result case (a keyword matching nothing), where titles
        are expected to be absent. Prove the page is loaded first, then wait
        for the title family to empty, so this cannot pass on a blank screen.
        The waiting form means it answers False only by running out of time, so
        call it only where emptiness is the expected answer.
        """
        if not self.is_loaded():
            return False
        self.wait_for_any(self.sel("test_case_titles"), present=False)
        return True

    def is_title_shown(self, title: str) -> bool:
        """True once a title matching `title` is shown. WAITS for it.

        Waits for a row whose text contains `title` (case-insensitively via the
        row helper's containment match). Call this only where the title is
        expected to be present; the waiting form answers False only by timing
        out.
        """
        self.wait_for_row(self.sel("test_case_titles"), title, present=True)
        return True

    def is_title_hidden(self, title: str) -> bool:
        """True once no shown title matches `title`. WAITS while one remains.

        For asserting a filter has removed a title. `test_case_titles` is a
        PERMANENT element of this page (not conditional), so it is also absent
        before the page has rendered or on any other page. Prove the page is
        loaded first, then wait for the matching row to be gone, so this cannot
        pass on a blank screen or the wrong page.

        Waits rather than glancing once, because the moment worth checking is
        immediately after the filter has been applied, while the list is still
        settling. The waiting form answers False only by timing out, so call it
        only where the title is expected to be absent.
        """
        if not self.is_loaded():
            return False
        self.wait_for_row(self.sel("test_case_titles"), title, present=False)
        return True

    def is_title_a_link(self, title: str) -> bool:
        """True once a title matching `title` is rendered as a link element.

        The title family IS the anchor elements, so a title present in the list
        is by construction a link. WAITS for the matching row. Call this only
        where the title is expected to be present.
        """
        self.wait_for_row(self.sel("test_case_titles"), title, present=True)
        return True

    def every_title_contains(self, term: str) -> bool:
        """True if every shown title contains `term`. WAITS for titles first.

        Matches case-insensitively and by containment. Call this only where
        titles are expected (after a filter that should match at least one).
        """
        self.wait_for_any(self.sel("test_case_titles"))
        needle = term.strip().lower()
        titles = self.title_texts()
        return bool(titles) and all(needle in t.lower() for t in titles)
