"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. The nav is present on every
page, so login-state queries and cross-page navigation actions live here once
rather than being repeated on each page object.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation bar. Selectors: see `pages.nav` in the app inventory.

    The Logout link is rendered ONLY while a session exists, and the
    Signup/Login link ONLY while signed out, so their presence/absence is a
    more reliable authentication signal than the URL — this app serves the
    same path either way.
    """

    INVENTORY_PAGE = "nav"

    # ── navigation actions ───────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click the Logout link, ending the current session."""
        self.click(self.sel("logout_link"))

    # ── login-state queries ──────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The Logout link is present only while authenticated, so its presence
        is the readiness signal. Non-waiting, so this is safe for asserting
        the NEGATIVE case (that no session exists).
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        The waiting counterpart to is_logged_in(), for asserting that a login
        succeeded. Using the non-waiting probe there races the redirect and
        can report False while the app is still authenticating.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS for the Signup/Login link.

        After logout the Signup/Login link reappears; waiting for it confirms
        the sign-out completed rather than racing the redirect.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. The banner is a substring
        match, so callers should assert containment rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
