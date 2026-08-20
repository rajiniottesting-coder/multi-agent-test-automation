"""
NavPage — the top navigation bar shared by every page.

Selectors: see `pages.nav` in the app inventory. The nav mixes icon libraries,
so links are addressed by href (each pinned with '>> nth=0' to select the
header copy over any footer duplicate), never by role+name.

Logged-in state is read from the presence of the Logout link, which is the
site's most reliable authentication signal — the same path is served whether or
not a session exists.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the header 'Products' link to load the product listing."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click the header 'Logout' link, ending the session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists RIGHT NOW. Never waits, never raises.

        The Logout link is rendered only while authenticated, so its presence
        is the authentication signal. Use this for the ABSENCE case (asserting
        the user is NOT logged in); use wait_until_logged_in() for presence.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link appears. WAITS for it.

        Use this right after submitting the login form, where the session is
        expected to exist but may take a request to establish. The non-waiting
        is_logged_in() would race the redirect and report False too early.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. To assert the user is NOT
        logged in, use is_logged_in() instead, which does not wait.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    def has_login_signup_link(self) -> bool:
        """True if the 'Login/Signup' link is present. Never waits, never raises.

        This link is rendered only while signed OUT — the mirror of the Logout
        link. Use it to confirm the user is no longer recognised after logout.
        """
        return self.is_visible(self.sel("signup_login_link"))
