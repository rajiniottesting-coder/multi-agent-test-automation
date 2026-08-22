"""
NavPage — the top navigation bar shared by every page.

Selectors: see `pages.nav` in the app inventory. The nav is present on every
screen, so its links and the logged-in signal live here once rather than being
repeated on each page object.

The logged-in / logged-out signal is read from the nav rather than the URL:
this app serves the same path ('/') whether or not a session exists, so the
presence of the Logout link (only rendered while authenticated) and the
Login/Signup link (only rendered while signed out) are the reliable signals.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── navigation actions ──────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click the Cart link in the top navigation."""
        self.click(self.sel("cart_link"))

    def logout(self) -> None:
        """Click the Logout link, ending the session."""
        self.click(self.sel("logout_link"))

    # ── logged-in queries ────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Non-waiting probe for BRANCHING or for asserting ABSENCE of a session
        (assert not is_logged_in()). To assert that a login SUCCEEDED, use the
        waiting reader wait_until_logged_in() instead — this one would race the
        login and report False while the app is still authenticating.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self) -> bool:
        """True once a session exists. WAITS, and times out if none appears.

        Call this only where being logged in is the expected answer — after a
        valid login. A step asking merely to branch on the reply will pay the
        full timeout every time the answer is no; use is_logged_in() for that.
        """
        return self.is_showing(self.sel("logout_link"))

    def is_logged_out(self) -> bool:
        """True if no session exists right now. Never waits, never raises.

        Non-waiting probe: the Login/Signup link is rendered only while signed
        out, so its presence is the mirror of is_logged_in(). Safe to negate.
        """
        return self.is_visible(self.sel("signup_login_link"))

    def wait_until_logged_out(self) -> bool:
        """True once no session exists. WAITS, and times out if one persists.

        Call this only where being logged out is the expected answer — after a
        logout. It confirms the Login/Signup link has reappeared, which is the
        signal the app itself renders for 'you are no longer recognised'.
        """
        return self.is_showing(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Assert containment
        ('Logged in as' in ...) rather than equality — the banner includes the
        account name.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
