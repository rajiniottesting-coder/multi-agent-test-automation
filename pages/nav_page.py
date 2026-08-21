"""
NavPage — the shared top navigation.

Present on every page of the site. Wraps the login-state signals (Logout link
present ⇒ authenticated), logout, the recognised-by-name banner, and navigation
to the Products listing.

Readiness note: this bar has no single element unique to itself — it is the
same block on every page. The most state-independent handle is the Home link,
which is rendered in the header whether signed in or out. is_loaded() probes it.

Selectors: see `pages.nav` in the app inventory.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Shared top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the top navigation is on screen. WAITS for it.

        Probes the Home link — the one nav element present in both signed-in
        and signed-out states, so it holds whatever the session is.
        """
        return self.is_showing(self.sel("home_link"))

    def is_logged_in(self) -> bool:
        """True if a session exists RIGHT NOW. Never waits, never raises.

        The Logout link is rendered only while authenticated. Used for asserting
        ABSENCE of a session — the waiting reader would time out instead of
        returning False, so branch/absence checks must use this one.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        The waiting counterpart to is_logged_in(), for asserting PRESENCE of a
        session straight after a login submit.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS for the Login/Signup link.

        The Signup/Login link is rendered only while signed out, so its
        appearance is the positive signal that logout completed — more reliable
        than waiting for the Logout link to vanish.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Assert containment on the
        result, not equality — the banner embeds the account name.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top nav and confirm the listing loaded.

        confirm_arrival() is called on the ProductsPage, not here — it must read
        the DESTINATION's declared URL to verify the browser actually moved,
        recovering if an ad interstitial swallowed the click.
        """
        from pages.products_page import ProductsPage

        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click 'Logout' in the top nav and confirm the login page loaded.

        Logout redirects to /login. confirm_arrival() is called on the
        LoginPage so it reads that destination's URL.
        """
        from pages.login_page import LoginPage

        self.click(self.sel("logout_link"))
        LoginPage(self.page).confirm_arrival()
