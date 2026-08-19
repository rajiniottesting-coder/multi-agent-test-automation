"""
NavPage — the top navigation present on every page.

Selectors: see `pages.nav` in the app inventory. This object exposes the two
things scenarios repeatedly need from the nav bar: knowing WHETHER a session
exists (by the presence of the Logout link, which is more reliable than the
URL on this app) and MOVING between the main areas (products, logout).

Login state is read from element PRESENCE, never from the URL: this app serves
the same '/' path signed in and signed out. The Logout link renders only while
authenticated, and the Login/Signup link only while signed out, so each is a
clean binary signal.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── navigation actions ───────────────────────────────────
    def go_to_products(self) -> None:
        """Click 'Products' in the top navigation to open the listing."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click 'Logout' in the top navigation, ending the session."""
        self.click(self.sel("logout_link"))

    # ── login-state queries ──────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Reads the presence of the Logout link, which renders only while
        authenticated. Use this for asserting the ABSENCE of a session; the
        non-waiting probe returns False instead of timing out.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: int = 10000) -> bool:
        """True once a session exists, WAITING up to the timeout.

        The waiting counterpart to is_logged_in(), for asserting that a login
        succeeded. Waits for the Logout link, which appears only while
        authenticated.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def wait_until_logged_out(self, timeout_ms: int = 10000) -> bool:
        """True once no session exists, WAITING up to the timeout.

        Waits for the Login/Signup link, which renders only while signed out —
        the mirror signal to the Logout link. For asserting that a logout
        succeeded.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call when a session is expected. Returns the full banner string;
        assert containment ('Logged in as' in text) rather than equality, since
        the trailing name is account-specific.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
