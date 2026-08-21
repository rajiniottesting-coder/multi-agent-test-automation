"""
NavPage — the shared top navigation.

Present on every page of the site, so it lives once here rather than being
repeated on each page object. Its job is the cross-page session signals:
whether a user is logged in, the "Logged in as <name>" banner, moving to the
Products listing, and logging out.

Selectors: see `pages.nav` in the app inventory. Every method resolves its
selector through self.sel("<key>") — no literals in this file.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory.

    The Logout link renders ONLY while authenticated, and the Login/Signup
    link renders ONLY while signed out. Each is a reliable session signal —
    more so than the URL, which this app serves the same path for either state.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation and confirm the listing loaded.

        The destination is the /products page, so arrival is confirmed against
        that page object rather than this one — an ad interstitial can swallow
        the first navigation after a page load without the click reporting it.
        """
        from pages.products_page import ProductsPage

        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click 'Logout' in the top navigation.

        Landing on the login page confirms the session ended; the login page
        object owns that URL, so it confirms the arrival.
        """
        from pages.login_page import LoginPage

        self.click(self.sel("logout_link"))
        LoginPage(self.page).confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link is on screen. WAITS for it.

        Use this to assert a login SUCCEEDED — the waiting probe retries and
        logs the reason it gave up, unlike a one-shot read that races the
        session change made by the click before it.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that a login was REJECTED. The waiting reader would time out instead of
        returning False, so the assertion would never be reached.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Login/Signup link is on screen. WAITS for it.

        Use this to assert a logout SUCCEEDED — the Login/Signup link renders
        only while signed out, so its appearance confirms the session ended.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. The banner is a substring
        match ('Logged in as <name>'), so assert containment rather than
        equality on the returned value.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
