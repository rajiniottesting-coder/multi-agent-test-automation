"""
NavPage — the top navigation bar shared by every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once in the
inventory rather than being repeated on each page, so login-state queries,
logout and cross-page navigation all resolve through this one object.

Login state is read from the DOM, not the URL: this app serves the same path
signed in or out, so the presence of the Logout link (rendered only while
authenticated) is the reliable signal. Its absence — mirrored by the return
of the Login/Signup link — means no session.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation: login-state queries, logout, and Products navigation.

    Selectors are addressed by href rather than role+name on purpose — the
    site's Material Icons pollute accessible names, so role-name matching
    fails for most links (see the inventory notes).
    """

    INVENTORY_PAGE = "nav"

    # ── navigation ───────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation to open the listing."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click 'Logout', ending the current session and going to /login."""
        self.click(self.sel("logout_link"))

    # ── login-state queries ──────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Reads the Logout link, which is rendered only while authenticated.
        Non-waiting, so it is safe for asserting the ABSENCE of a session —
        the waiting reader would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session is established. WAITS for the Logout link.

        Use this to assert that a login SUCCEEDED — the link appears only
        after the session is created, so a non-waiting probe would race it.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self) -> bool:
        """True if no session exists right now. Never waits, never raises.

        Reads the Login/Signup link, which is rendered only while signed out.
        The mirror of is_logged_in(), for confirming logout completed.
        """
        return self.is_visible(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected; use is_logged_in() to
        assert absence.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
