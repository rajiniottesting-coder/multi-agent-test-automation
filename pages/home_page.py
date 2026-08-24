"""
HomePage — the site home page reached after a successful login redirect.

App: https://automationexercise.com

The home page shares its path ("/") with the login redirect target. Its most
state-independent element is the site logo, which is present regardless of
whether the newsletter has been subscribed to or any other transient state, so
it is used as the readiness probe. The `nav` inventory (via NavPage) owns the
logged-in / logged-out signals, so those are NOT re-implemented here.
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """Home page. Selectors: see `home` in the app inventory."""

    INVENTORY_PAGE = "home"

    def open_home(self, base_url: str) -> None:
        """Navigate directly to the home page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the site logo, which is present in every state the home page
        can be in — it does not depend on the subscription form or any
        post-login banner.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
