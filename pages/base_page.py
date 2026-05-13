"""
BasePage — parent class for all page objects.
Holds the Playwright `page` reference and common actions.

This base class provides Playwright-native helpers for the patterns that
test code most often gets wrong: reading <select> values, selecting options
with verification, extracting text from lists of elements, and waiting for
asserted conditions to actually become true.

All methods here are app-agnostic — they accept locator strings and operate
on whatever element they're pointed at. Concrete locators belong in
subclasses (LoginPage, InventoryPage, etc.), never here.
"""
from typing import List, Optional
from playwright.sync_api import Page, expect


class BasePage:
    """Every page object inherits from this."""

    # Default timeout for "wait and assert" helpers — short enough to fail
    # fast on broken pages, long enough to absorb normal network jitter.
    DEFAULT_TIMEOUT_MS = 5000

    def __init__(self, page: Page):
        self.page = page

    # ============================================================
    # Navigation
    # ============================================================

    def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the page to load."""
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")

    def get_title(self) -> str:
        """Return the page title."""
        return self.page.title()

    # ============================================================
    # Visibility / presence
    # ============================================================

    def is_visible(self, locator: str) -> bool:
        """Check if an element is visible (returns False if not present)."""
        return self.page.locator(locator).is_visible()

    def wait_visible(self, locator: str, timeout_ms: Optional[int] = None) -> None:
        """Wait for an element to be visible. Raises on timeout.

        Use this BEFORE asserting on element text/value when the element
        appears asynchronously (after a click, a network response, etc.).
        """
        self.page.locator(locator).wait_for(
            state="visible",
            timeout=timeout_ms or self.DEFAULT_TIMEOUT_MS,
        )

    # ============================================================
    # Select dropdown helpers
    #
    # Native HTML <select> elements do NOT have CSS classes like
    # ".active_option" or ".selected_option". The correct way to read
    # the selected value or label is via Playwright's built-in APIs.
    # ============================================================

    def get_select_value(self, locator: str) -> str:
        """Return the `value` attribute of the currently selected option.

        Example: a <select> with <option value="lohi">Price low-high</option>
        selected will return "lohi".
        """
        return self.page.locator(locator).input_value()

    def get_select_label(self, locator: str) -> str:
        """Return the visible TEXT of the currently selected option.

        Example: a <select> with <option value="lohi">Price low-high</option>
        selected will return "Price low-high".

        Implementation: reads `el.options[el.selectedIndex].text` from the DOM.
        """
        return self.page.locator(locator).evaluate(
            "el => el.options[el.selectedIndex].text"
        )

    def select_by_label(
        self,
        locator: str,
        label: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        """Select an option by its visible text AND verify the change took effect.

        Plain `page.select_option(locator, label=...)` returns immediately —
        if the page hasn't fully wired up the option list yet, the selection
        may silently no-op. This helper waits for the actual label to appear
        as selected after the call.
        """
        self.page.locator(locator).select_option(label=label)
        # Verify the selection took effect by reading the label back.
        # Uses a polling assertion so transient delays don't fail the test.
        expect.poll(
            lambda: self.get_select_label(locator),
            timeout=timeout_ms or self.DEFAULT_TIMEOUT_MS,
        ).to_be(label)

    def select_by_value(
        self,
        locator: str,
        value: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        """Select an option by its `value` attribute AND verify the change took effect."""
        self.page.locator(locator).select_option(value=value)
        expect(self.page.locator(locator)).to_have_value(
            value,
            timeout=timeout_ms or self.DEFAULT_TIMEOUT_MS,
        )

    # ============================================================
    # Input / textarea helpers
    # ============================================================

    def get_input_value(self, locator: str) -> str:
        """Return the current `value` of an <input> or <textarea>.

        Note: this is the user-facing value, NOT the original `value`
        attribute from the HTML source. Use this to read what's currently
        typed in the field.
        """
        return self.page.locator(locator).input_value()

    # ============================================================
    # List/collection helpers
    #
    # These exist because step defs frequently re-implement string
    # parsing logic that the page object should do once.
    # ============================================================

    def get_all_texts(self, locator: str) -> List[str]:
        """Return all matching elements' inner text as a list of stripped strings.

        Use for "give me all product names", "give me all menu items", etc.
        Returned strings are stripped of leading/trailing whitespace.
        """
        raw = self.page.locator(locator).all_inner_texts()
        return [t.strip() for t in raw]

    def get_count(self, locator: str) -> int:
        """Return the number of matching elements."""
        return self.page.locator(locator).count()

    # ============================================================
    # Wait-and-assert helpers
    #
    # Use these instead of separate "click then assert" patterns where
    # the assertion needs to wait for async UI updates.
    # ============================================================

    def wait_for_text(
        self,
        locator: str,
        expected_text: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        """Wait for an element's text to match exactly. Raises on timeout."""
        expect(self.page.locator(locator)).to_have_text(
            expected_text,
            timeout=timeout_ms or self.DEFAULT_TIMEOUT_MS,
        )

    def wait_for_url_contains(
        self,
        substring: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        """Wait for the page URL to contain a given substring.

        Useful after clicking a link/button that triggers navigation.
        """
        self.page.wait_for_url(
            f"**{substring}**",
            timeout=timeout_ms or self.DEFAULT_TIMEOUT_MS,
        )