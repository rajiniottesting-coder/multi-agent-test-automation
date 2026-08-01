"""
HomePage — the landing page, and where a successful login lands.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """The landing page. Selectors: see `pages.home` in the app inventory."""

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the home page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def subscribe(self, email: str) -> None:
        """Submit the footer subscription form.

        Confirmation renders in place — there is no navigation and no toast —
        so assert on subscribe_success() rather than on a URL change.
        """
        self.fill(self.sel("subscribe_email_input"), email)
        self.click(self.sel("subscribe_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        THE REFERENCE READINESS PROBE — copy this shape, not an older one.
        It delegates to BasePage.is_showing() rather than swallowing the
        Playwright error in a bare `except`: a failed readiness check logs the
        selector, the wait it used and the current URL, where the older shape
        offered nothing but `assert False`.

        `timeout_ms=None` inherits `browser.timeout` from config.yaml, so a
        hard-coded number here cannot silently override the configured value.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)

    def has_subscribed(self) -> bool:
        """True if the subscription confirmation is showing. Never waits."""
        return self.is_visible(self.sel("subscribe_success"))
