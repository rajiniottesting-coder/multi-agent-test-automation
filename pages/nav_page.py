"""
NavPage — the top navigation bar shared by every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once here rather
than being repeated on each page object. It carries the login-state signals the
whole suite relies on: the Logout link is present ONLY while authenticated, and
the 'Logged in as <name>' banner names the current user.

Links are addressed by href, not by role+name — this app's Material Icons
render their glyph from ligature text, so Playwright folds e.g. 'card_travel'
into the accessible name and role-name matching fails. Each header link is
pinned with '>> nth=0' because the footer repeats several of them.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation bar. Selectors: `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── navigation actions ───────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click the Cart link in the top navigation."""
        self.click(self.sel("cart_link"))

    def open_home(self) -> None:
        """Click the Home link in the top navigation."""
        self.click(self.sel("home_link"))

    def open_signup_login(self) -> None:
        """Click the Signup / Login link in the top navigation."""
        self.click(self.sel("signup_login_link"))

    def logout(self) -> None:
        """Click the Logout link, ending the authenticated session."""
        self.click(self.sel("logout_link"))

    # ── login-state queries ──────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link is on screen. WAITS for it.

        The Logout link is rendered only while authenticated, which is more
        reliable than the URL: this app serves the same path signed in or out.
        Use this to assert a login SUCCEEDED.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if the Logout link is present right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting a
        session does NOT exist. The waiting reader would time out instead of
        returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Signup / Login link is on screen. WAITS for it.

        The Signup / Login link is rendered only while signed OUT — it is
        replaced by Logout once a session exists. Use this to assert a logout
        SUCCEEDED and the user is no longer recognised.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Reads as 'Logged in as <name>', so assert containment rather than
        equality. Only call this when a session is expected.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    def has_logged_in_name(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Logged in as' banner is on screen. WAITS for it.

        A test asserts on this method's answer, so it must wait: is_showing()
        retries until the timeout and logs the reason it gave up, where
        is_visible() would read the page once and race the action before it.
        Use this to assert the banner is PRESENT after a successful login.
        """
        return self.is_showing(self.sel("logged_in_as"), timeout_ms=timeout_ms)
