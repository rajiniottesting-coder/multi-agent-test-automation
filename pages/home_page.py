"""
HomePage — the Automation Exercise landing page.

Its single job in the shopping-session feature is to confirm the browser has
ARRIVED here after a successful login: this app serves the same '/' path
whether signed in or out, so arrival is proven by the page's own readiness
element rather than by the URL alone.

Selectors come from the app inventory (pages.home). This file contains no
literal selector strings — every element is looked up with self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """The home page. Selectors: see `pages.home` in the app inventory.

    The home page has no readiness key declared in the inventory, so is_loaded()
    probes the most state-independent element on it: the site logo, which is
    present in every state the home page can be in (signed in or signed out).
    """

    INVENTORY_PAGE = "home"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the site logo — the one element present whether the shopper is
        signed in or out, so it holds in every state the home page reaches
        (the inventory declares no explicit readiness key for this page).

        Call this where arrival on the home page is the EXPECTED outcome; it
        waits up to the timeout and logs the selector and URL if it never
        appears, rather than swallowing the failure silently.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
