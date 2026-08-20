"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once here
rather than being repeated on each page object.

Conventions (copied from the LoginPage reference):
  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then use
    self.sel("<element_key>"). Never write a literal selector here.
  - Methods are business verbs describing user intent.
  - Every method uses a BasePage helper; no raw self.page.* calls.
  - No assertions here — those belong in the step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation bar.

    The Logout link renders ONLY while authenticated, which makes it a more
    reliable session signal than the URL (this app serves the same path either
    way). The Signup/Login link is its mirror — present only while signed out.
    """

    INVENTORY_PAGE = "nav"

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting probe, for asserting the ABSENT case (logged out).
        Using a waiting reader there would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link appears. WAITS for it.

        The presence counterpart to is_logged_in(), for asserting a login
        succeeded — a non-waiting probe straight after submit would race the
        redirect and report False while the app is working correctly.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Signup/Login link appears. WAITS for it.

        For asserting a logout succeeded: the link returns only after the
        session ends.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Returns a substring-bearing
        string; assert containment rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation and confirm arrival."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click the Cart link in the top navigation."""
        self.click(self.sel("cart_link"))

    def logout(self) -> None:
        """Click the Logout link, ending the current session."""
        self.click(self.sel("logout_link"))
