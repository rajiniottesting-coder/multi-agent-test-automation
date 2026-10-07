"""
HomePage — the landing page after a successful login.

Used to confirm post-login arrival. This app serves the home page at the
root path "/", the same path the login screen is reached from, so the
reliable readiness signal for "I am on the home page" is the always-present
site logo rather than the URL (which does not distinguish the two).

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """Home / landing page. Selectors: see `pages.home` in the app inventory."""

    INVENTORY_PAGE = "home"

    def open_home(self, base_url: str) -> None:
        """Navigate directly to the home page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the site logo, which is present in every state of the home page,
        making it a state-independent readiness signal.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
