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

    def is_signup_login_shown(self) -> bool:
        """True if the Signup / Login link is on screen right now.

        The POSITIVE proof that no session is active. `not is_logged_in()`
        proves only that the Logout link is absent, which an error page or a
        half-loaded page satisfies just as well - it is the absence of one
        thing standing in for the presence of another.

        Non-waiting on purpose. `signup_login_link` is declared `conditional`
        in the inventory: it is legitimately absent whenever a session IS
        active, so waiting for it would cost the full timeout on every
        signed-in check.
        """
        return self.is_visible(self.sel("signup_login_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session is active, WAITING for it.

        The waiting counterpart to is_logged_in(), for asserting that a login
        succeeded. Logs the selector, the wait and the URL when it gives up.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session is active, WAITING for it.

        The waiting counterpart to is_signup_login_shown(), and the missing
        half of an otherwise symmetric pair: is_logged_in() had
        wait_until_logged_in(), and the negative side had no waiting form at
        all. A scenario that clicks Logout and then asserts the result needs
        one, because the page is still transitioning when the assertion runs.

        Waits for the Signup / Login link rather than for the Logout link to
        vanish, for the reason is_signup_login_shown() gives: an absence is
        satisfied by an error page or a half-loaded one just as well as by a
        genuine sign-out.
        """
        return self.is_showing(self.sel("signup_login_link"),
                               timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The text of the 'Logged in as <name>' banner. WAITS for it."""
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))