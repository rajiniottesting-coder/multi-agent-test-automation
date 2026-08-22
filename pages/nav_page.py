"""
NavPage — the top navigation bar shared by every page on the site.

Selectors: see `pages.nav` in the app inventory. The nav lives once here
rather than duplicated on each page object. It carries the authentication
signals (Logout / Login-Signup) and the primary navigation links.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory.

    The presence of the Logout link is the reliable 'am I authenticated'
    signal on this app — the URL is the same signed in or out, so parse the
    nav, not the path.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top nav and confirm the listing loaded.

        The click is expected to land on /products, so it ends by confirming
        arrival there — an ad interstitial can otherwise swallow the first
        navigation and leave the browser where it was.
        """
        from pages.products_page import ProductsPage

        self.dismiss_interstitial()
        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click 'Logout' in the top nav, ending the session."""
        self.dismiss_interstitial()
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link is present. WAITS, times out if it is not.

        Call this only where a session is EXPECTED — it is the presence-side
        assertion helper. To assert NO session, use is_logged_in(), which does
        not wait.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if the Logout link is showing right now. Never waits.

        The non-waiting counterpart to wait_until_logged_in(), for asserting a
        user is NOT authenticated. Using the waiting reader for that would time
        out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Login/Signup link is present. WAITS, times out if not.

        The presence-side helper for asserting the user was logged OUT — the
        Login/Signup link is rendered only while signed out, so its appearance
        confirms the session ended.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. Returns the full banner
        string; assert containment ('Logged in as') rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
