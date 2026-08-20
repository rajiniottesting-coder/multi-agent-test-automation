"""
NavPage — the persistent top navigation bar.

Present on every page of the app, so it lives once here rather than being
repeated on each page object. Selectors: see `pages.nav` in the app inventory.

Conventions (mirrors pages/login_page.py):
  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then look up
    every element with self.sel("<key>").
  - Methods are business verbs that name their subject.
  - Every method uses a BasePage helper; no raw self.page.* calls.
  - No assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory.

    The Logout link is rendered ONLY while authenticated and the Login/Signup
    link ONLY while signed out, so each is a reliable readiness signal for the
    session state — more reliable than the URL, which this app serves the same
    way logged in or out.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the 'Products' link in the top navigation."""
        self.click(self.sel("products_link"))

    def open_cart(self) -> None:
        """Click the 'Cart' link in the top navigation."""
        self.click(self.sel("cart_link"))

    def open_signup_login(self) -> None:
        """Click the 'Signup / Login' link in the top navigation."""
        self.click(self.sel("signup_login_link"))

    def logout(self) -> None:
        """Click the 'Logout' link, ending the session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link is visible. WAITS for it.

        The Logout link exists only while authenticated, so its presence is the
        readiness signal for a successful login. Use this right after logging
        in; use is_logged_in() (no wait) to assert the ABSENCE of a session.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if the Logout link is showing right now. Never waits.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that NO session exists. Using the waiting reader for that would time
        out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. The banner is a substring
        match, so callers assert containment rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    def is_signup_login_visible(self) -> bool:
        """True if the Login/Signup link is showing. Never waits.

        Rendered only while signed out, so this is the mirror of
        is_logged_in(): use it to confirm the user is no longer recognised
        after logging out.
        """
        return self.is_visible(self.sel("signup_login_link"))
