"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once here
rather than being repeated on each page object.

Conventions (copied from the LoginPage reference):
  - selectors come from the inventory via self.sel("<key>"); no literals here
  - methods are business verbs that name their subject
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

Notes on the nav:
  - The Logout link renders ONLY while authenticated, so its presence is a
    reliable readiness signal for "am I logged in" — more reliable than the
    URL, since this app serves the same path either way.
  - The Signup/Login link renders ONLY while signed out — the mirror signal.
  - The "Logged in as <name>" banner is a substring match; assert containment.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation state and actions."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link to go to the /products listing."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click the Logout link, ending the session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Reads the Logout link's presence, which the app renders only while
        authenticated. Use this to assert ABSENCE of a session.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link appears. WAITS for it.

        The waiting counterpart to is_logged_in(), for asserting that a login
        succeeded without racing the redirect.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self) -> bool:
        """True if signed out right now. Never waits, never raises.

        Reads the Signup/Login link's presence, which the app renders only
        while signed out — the mirror of is_logged_in().
        """
        return self.is_visible(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. Assert containment of
        'Logged in as' rather than equality — the name is appended.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
