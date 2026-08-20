"""
NavPage — the shared top navigation present on every page.

Owns the authentication-state signals (Logout link present vs Login/Signup
link present, the 'Logged in as <name>' banner) and navigation to Products
and Logout. Selectors: see `nav` in the app inventory.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.products_page import ProductsPage
from pages.login_page import LoginPage


class NavPage(BasePage):
    """Top navigation shared across all pages.

    The nav is addressed by href rather than by role+name because this app's
    Material Icons pollute the accessible name of most links (see the inventory
    notes). The Logout link exists only while authenticated, which makes its
    presence the most reliable signal of a live session — more reliable than
    the URL, since this app serves the same path signed in or out.
    """

    INVENTORY_PAGE = "nav"

    # ── navigation ───────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top nav and confirm the listing loaded."""
        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click 'Logout' and confirm arrival on the login page."""
        self.click(self.sel("logout_link"))
        LoginPage(self.page).confirm_arrival()

    # ── session-state queries ────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists RIGHT NOW. Never waits, never raises.

        The non-waiting probe, for asserting the ABSENCE of a session. Using
        the waiting reader for that would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link appears. WAITS for it.

        The waiting counterpart to is_logged_in(), for asserting a session was
        established after a login: a non-waiting probe called straight after the
        submit races the redirect and reports False while the app is working.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Login/Signup link appears. WAITS for it.

        The mirror of wait_until_logged_in(): the Login/Signup link is rendered
        only while signed OUT, so its appearance confirms a logout completed.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. To assert NO session, use
        is_logged_in(), which does not wait.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
