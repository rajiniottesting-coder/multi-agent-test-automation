"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. Links here are addressed by
href rather than by role+name because this app's icon libraries pollute the
accessible name (a Material Icons ligature turns 'Products' into
'card_travel Products'), so role-name matching fails. Each is pinned with
'>> nth=0' in the inventory to hit the header copy, not the footer duplicate.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation: products navigation, logout, and session-state checks.

    The Logout link is rendered ONLY while authenticated and the
    Login/Signup link ONLY while signed out — the two are mirror signals, so
    either one tells us the session state more reliably than the URL (this app
    serves the same path in both states).
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def go_to_products(self) -> None:
        """Click the Products link in the top navigation."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click the Logout link, ending the current session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists RIGHT NOW. Never waits, never raises.

        Reads the Logout link, which the app renders only while authenticated.
        This is the non-waiting probe — use it to assert the ABSENCE of a
        session, where the waiting reader would time out instead of returning
        False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link appears. WAITS for it.

        The waiting counterpart to is_logged_in(), for asserting a login
        SUCCEEDED — the link may render a moment after the submit resolves.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Login/Signup link appears. WAITS for it.

        Rendered only while signed out, so its presence confirms a logout took
        effect.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected; the banner is present only
        while authenticated.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
