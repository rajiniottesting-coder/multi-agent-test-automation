"""
NavPage — the shared top navigation.

Present on every page of the app, so navigation actions, the logged-in
readiness signal and the account-name read all live here rather than being
repeated on each page object.

SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then look each
element up with self.sel("<key>"). No literal selector strings in this file.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory.

    The Logout link is rendered ONLY while authenticated, which makes its
    presence a more reliable "am I logged in" signal than the URL — this app
    serves the same path signed in or out.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation to reach the listing."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click 'Cart' in the top navigation."""
        self.click(self.sel("cart_link"))

    def logout(self) -> None:
        """Click 'Logout' — ends the session and redirects to /login."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link is on screen. WAITS for it.

        Use this straight after submitting a login: the non-waiting probe
        would race the redirect and report False while the app is working.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that a login was NOT granted. Using the waiting reader for that would
        time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def is_logged_out(self) -> bool:
        """True if the signed-out state is showing right now. Never waits.

        The signup/login link is rendered only while signed OUT, so its
        presence confirms the user is no longer recognised.
        """
        return self.is_visible(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Reads a substring match,
        so assert containment rather than equality on the result.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
