"""
HomePage — the Automation Exercise site root.

Entry point for the shopping session. The home page and the top navigation
share the '/' path, but navigation lives on its own page object (NavPage);
this page object exists to LAND the browser on the site root and confirm it.

Selectors: see `home` in the app inventory. No literal selectors here — every
lookup goes through self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """Site root. Selectors: see `pages.home` in the app inventory."""

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate to the site root and confirm the browser arrived.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, so it is never duplicated
                      here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the site logo, which is present in every state of the home page
        — it does not depend on subscription, session or any interaction.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
