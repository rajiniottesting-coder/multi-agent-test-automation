"""
HomePage — the landing page at the site root.

Selectors: see `pages.home` in the app inventory. This page object exists so a
scenario can open the site at its base URL to begin a shopping session. It
does not carry the top navigation — that lives on NavPage — so the only things
it reads are the home page's own elements.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """The home / landing page. Selectors: see `pages.home` in the inventory."""

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate to the site root, where a shopping session begins.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture.
                      The path comes from the inventory, so it is never
                      duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page's logo is on screen. WAITS for it.

        The site logo is present in every state of the home page, so it is a
        state-independent readiness signal, unlike the subscription block which
        sits below the fold and depends on scroll position.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
