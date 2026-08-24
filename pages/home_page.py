"""
HomePage — the Automation Exercise landing page.

RESERVED-STYLE page object mimicking pages/login_page.py. It confirms the
browser reached the home page after a successful login.

The home page shares its path ("/") with the nav entry, so its readiness
signal must be something that renders on the landing page in every state.
The subscription section at the foot of the page is always present, so its
heading is the most state-independent element available here. There is no
explicit `readiness` key in the inventory for this page; the subscription
heading is chosen for that reason and noted here.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class HomePage(BasePage):
    """Home landing page. Selectors: see `pages.home` in the app inventory."""

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate directly to the home page.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, so it is never duplicated.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the subscription heading in the page footer, which is present on
        the landing page in every state — no search, filter or session change
        removes it — making it a reliable readiness signal for a page that
        shares its path with the site root.
        """
        return self.is_showing(
            self.sel("subscription_heading"), timeout_ms=timeout_ms
        )
