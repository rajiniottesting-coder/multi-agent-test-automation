"""
NavPage — the top navigation bar shared by every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once here
rather than being repeated on each page object.

Conventions (copied from pages/login_page.py):
  - INVENTORY_PAGE names the inventory entry; every selector is resolved via
    self.sel("<key>"), never a literal string.
  - methods are business verbs, not UI mechanics.
  - assertions belong in step definitions, not here.
  - presence is asserted with a WAITING probe (is_showing); optional/absent
    state is checked with a non-waiting probe (is_visible) so it does not
    time out.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.products_page import ProductsPage


class NavPage(BasePage):
    """Top navigation: login-state checks, name banner, Products nav, logout.

    The Logout link is rendered ONLY while authenticated and the Signup/Login
    link ONLY while signed out, so their presence is a more reliable session
    signal than the URL — this app serves the same path in either state.
    """

    INVENTORY_PAGE = "nav"

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting probe, for asserting the user is NOT logged in. Using
        a waiting reader for that would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        The waiting counterpart to is_logged_in(), for asserting that a login
        succeeded. Logs the selector and current URL if it never appears.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the signed-out state is on screen. WAITS for it.

        Asserts the user is no longer recognised: the Signup/Login link is
        rendered only while signed out, so its reappearance confirms logout.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. Assert containment on the
        result, not equality — it embeds the account name.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click Products in the top navigation and confirm the listing loads."""
        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click Logout in the top navigation."""
        self.click(self.sel("logout_link"))
