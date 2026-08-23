"""
HomePage — the Automation Exercise landing page ('/').

Confirms the post-login landing page for the full shopping-session scenario:
after a successful login the app redirects to the home page, and this page
object provides the readiness probe and arrival confirmation for it.

Selectors come from `pages.home` in the app inventory — never a literal here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class HomePage(BasePage):
    """The site landing page. Selectors: see `pages.home` in the app inventory.

    The home page has no `readiness` key in the inventory, so `is_loaded()`
    probes `site_logo`: the logo is present on the landing page in every state
    (logged in or out, subscribed or not), which makes it the most
    state-independent element the page exposes.
    """

    INVENTORY_PAGE = "home"

    # ── actions ──────────────────────────────────────────────
    def open_home(self, base_url: str) -> None:
        """Navigate to the home page and confirm the browser arrived."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def confirm_home(self) -> None:
        """Re-issue the home navigation if a click meant to land here did not.

        Called after an action on ANOTHER page (a login submit, a logout) that
        is expected to redirect to the home page. Free and silent when the
        browser is already here.
        """
        self.confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the home page is on screen. WAITS for it.

        Probes the site logo, which is present on the landing page in every
        state, so this readiness check holds whether or not the user is
        logged in.
        """
        return self.is_showing(self.sel("site_logo"), timeout_ms=timeout_ms)
