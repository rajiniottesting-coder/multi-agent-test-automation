"""
NavPage — the shared top navigation present on every page.

Selectors: see `pages.nav` in the app inventory. Every link is addressed by
href rather than by role+name (see the inventory's _href_over_role note), and
each is pinned with '>> nth=0' so the header link wins over any footer
duplicate. This page object resolves EVERY selector through self.sel(); it
never carries a literal selector string.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation bar. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click the Cart link in the top navigation."""
        self.click(self.sel("cart_link"))

    def logout(self) -> None:
        """Click the Logout link (present only while authenticated)."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Non-waiting probe for asserting the ABSENT case (not logged in): the
        Logout link is rendered only while authenticated. Using the waiting
        reader for absence would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS, and times out if none appears.

        Call this only where being logged in is the expected answer. A step
        asking 'am I logged in?' to branch on the reply will pay the full
        timeout every time the answer is no.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS for the signed-out signal.

        The Signup / Login link is rendered only while signed OUT, so its
        presence is the direct signal for logged-out. Times out if a session
        is still present.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected — it waits for the banner.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
