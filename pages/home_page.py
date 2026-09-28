"""
HomePage — the site homepage a shopper lands on after logging in.

Selectors: see `pages.home` in the app inventory. This page object's job in the
shopping-session feature is narrow: confirm the browser arrived at '/', which
is the redirect target after a successful login. The homepage carries the same
top navigation as every other page, but "am I logged in / recognised by name"
lives on NavPage — this class only answers "am I on the homepage".

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """The homepage served at '/'. Selectors: see `pages.home` in the inventory."""

    INVENTORY_PAGE = "home"

    def open_home(self, base_url: str) -> None:
        """Navigate directly to the homepage and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the homepage is on screen. WAITS for it.

        Probes the site logo, which is present in every state of the homepage
        (logged in or out, before or after subscribing), so it is a
        state-independent readiness signal. The page has no `readiness` key in
        the inventory, so this is the most stable element available.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
