"""
NavPage — the shared top navigation present on every page.

Selectors: see `pages.nav` in the app inventory. Every element here is
addressed by href (pinned with `>> nth=0`) rather than by role+name, because
this app's Material Icons render their glyph from ligature text that pollutes
the accessible name — see the inventory's elements_notes for the full story.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation: login-state queries, logout, account banner, and
    navigation to the Products page.

    The Logout link is rendered only while authenticated and the
    Signup/Login link only while signed out, so each is a reliable readiness
    signal — more reliable than the URL, which is the same path either way.
    """

    INVENTORY_PAGE = "nav"

    # ── navigation ───────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation to reach the listing page."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click 'Logout' in the top navigation, ending the session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        Use this right after logging in, where the app may still be settling.
        To assert the ABSENCE of a session, use is_logged_in() instead, which
        never waits.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that a login attempt did NOT authenticate. Using the waiting reader
        for that would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def is_logged_out(self) -> bool:
        """True if the signed-out Signup/Login link is showing right now.

        The mirror of is_logged_in(): the Signup/Login link replaces Logout
        once the session ends. Never waits, never raises.
        """
        return self.is_visible(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Returns the full banner
        string; assert containment ('Logged in as' in banner) rather than
        equality, since the account name varies.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
