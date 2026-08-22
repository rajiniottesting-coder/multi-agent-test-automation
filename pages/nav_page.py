"""
NavPage — the site-wide top navigation.

Present on every page of Automation Exercise. Exposes the authentication
signals (Logout link presence, "Logged in as <name>" banner) and the primary
navigation links. Selectors: see `pages.nav` in the app inventory.

Addressed by href rather than role+name on purpose — this app's nav mixes icon
libraries and Material Icons pollutes the accessible name with ligature text,
so role=link[name='Products'] matches nothing. See the inventory notes.
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        Call this to assert a login SUCCEEDED. To assert the opposite (no
        session) use the non-waiting is_logged_in(), or this will time out
        instead of returning False.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if the Logout link is showing right now. Never waits.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that NO session exists — where waiting would cost a full timeout.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS for the Login/Signup link.

        Call this to assert a logout SUCCEEDED — it proves the signed-out
        state directly, rather than inferring it from the absence of Logout.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. Assert containment, not
        equality — the banner embeds the account name.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link and confirm the listing page was reached."""
        from pages.products_page import ProductsPage

        self.click(self.sel("products_link"))
        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click the Logout link, ending the session and landing on /login."""
        from pages.login_page import LoginPage

        self.click(self.sel("logout_link"))
        LoginPage(self.page).confirm_arrival()
