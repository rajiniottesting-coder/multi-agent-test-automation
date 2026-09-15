"""
HomePage — the landing page at '/'.

Used to confirm the redirect after a successful login and to navigate onward
to the Products listing. Selectors: see `pages.home` in the app inventory.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """Home / landing page. Selectors: see `pages.home` in the app inventory.

    The home page shares the '/' path with the nav entry, so login/logout
    state is asserted through NavPage. This object's job is the landing page's
    own content (the site logo, subscription block) plus onward navigation.
    """

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate to the home / landing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the site logo, which is present in every state of this page
        regardless of login status.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
