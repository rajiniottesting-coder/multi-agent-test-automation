"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. The nav renders on every page,
so the authentication signals and top-level link clicks live here once rather
than being duplicated onto each page object.

Key facts encoded below:
  - The Logout link is present ONLY while authenticated, so its presence is the
    reliable readiness signal for 'am I logged in' — the URL is not, this app
    serves the same path either way.
  - The Login/Signup link is the mirror: present only while signed OUT.
  - Links are addressed by href (pinned with nth=0) rather than role+name,
    because Material Icons ligature text pollutes the accessible name.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── authentication state ─────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Branches on optional state — the Logout link is legitimately absent
        when signed out — so a non-waiting probe is correct here. Use this to
        assert ABSENCE of a session; use wait_until_logged_in() to assert one
        appeared.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self) -> bool:
        """True once the Logout link is on screen. WAITS for it.

        The waiting counterpart to is_logged_in(), for asserting that a login
        SUCCEEDED. Logs the selector and current URL if it never appears.
        """
        return self.is_showing(self.sel("logout_link"))

    def wait_until_logged_out(self) -> bool:
        """True once the Login/Signup link is on screen. WAITS for it.

        After a logout, use this to confirm the session ended: the Login/Signup
        link returns only while signed out.
        """
        return self.is_showing(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Reads as a substring, so
        the caller should assert containment rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    # ── top-navigation link clicks ───────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation, landing on /products."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click 'Cart' in the top navigation, landing on /view_cart."""
        self.click(self.sel("cart_link"))

    def open_signup_login(self) -> None:
        """Click 'Signup / Login' in the top navigation, landing on /login."""
        self.click(self.sel("signup_login_link"))

    def logout(self) -> None:
        """Click 'Logout' in the top navigation, ending the session.

        Redirects to /login. Confirm the signed-out state afterwards with
        wait_until_logged_out().
        """
        self.click(self.sel("logout_link"))
