"""
HomePage — the landing page served at '/' after a successful login.

Selectors come from the `home` entry in the app inventory; this file never
contains a literal selector string. The home page and the login page share the
same path ('/'), so being "on the home page" is confirmed by an element the
home page renders — the site logo — rather than by the URL alone.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """Home page reached after login. Selectors: see `home` in the inventory."""

    INVENTORY_PAGE = "home"

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        The site logo is present in every state of the home page, so it is a
        stable readiness probe — unlike the subscription block, which sits
        below the fold and depends on scroll/lazy-load timing.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
