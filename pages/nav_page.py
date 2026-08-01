"""
NavPage — the top navigation, present on every page.

The navigation is shared, so it lives in one page object rather than being
repeated on each screen. Any scenario that moves between areas of the site
needs this, and its `logout_link` doubles as the readiness signal for "am I
authenticated".

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def go_to_products(self) -> None:
        """Open the all-products page."""
        self.click(self.sel("products_link"))

    def go_to_cart(self) -> None:
        """Open the cart."""
        self.click(self.sel("cart_link"))

    def go_to_login(self) -> None:
        """Open the Signup / Login page."""
        self.click(self.sel("signup_login_link"))

    def logout(self) -> None:
        """Log out, returning to the Signup / Login page."""
        self.click(self.sel("logout_link"))

    def delete_account(self) -> None:
        """Permanently delete the signed-in account.

        A scenario that registers an account should call this at the end.
        This site has no admin cleanup, so abandoned accounts accumulate
        forever — the same litter that makes shared demos unreliable, caused
        by us rather than by someone else.
        """
        self.click(self.sel("delete_account_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session is active right now. Never waits, never raises.

        The Logout link is rendered only while authenticated, which makes its
        presence a more reliable signal than the URL: this app serves the same
        path to signed-in and signed-out visitors.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session is active, WAITING for it.

        The waiting counterpart to is_logged_in(), for asserting that a login
        succeeded. Logs the selector, the wait and the URL when it gives up.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The text of the 'Logged in as <name>' banner. WAITS for it."""
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
