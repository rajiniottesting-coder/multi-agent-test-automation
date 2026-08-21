"""
NavPage — the shared top navigation present on every page.

The navigation lives here once rather than being repeated on each page object,
because the same links (Products, Cart, Login/Signup, Logout, and the
'Logged in as <name>' banner) render on every screen. Selectors come from the
`nav` page in the app inventory; this file never contains a literal selector.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `nav` in the app inventory.

    Authentication state is read from the nav, not the URL: this app serves the
    same path signed in or out, so the presence of the Logout link (and the
    'Logged in as' banner) is the reliable signal, and the Login/Signup link is
    its mirror — present only while signed out.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click Products in the top navigation and confirm the listing loads.

        The click can be swallowed by an ad interstitial, so we confirm arrival
        on the destination rather than trusting the click alone.
        """
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click Logout in the top navigation. Ends the current session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the top navigation's Home link is on screen. WAITS for it.

        The Home link is present on every page in every auth state, which makes
        it the most state-independent readiness probe for the shared nav.
        """
        return self.is_showing(self.sel("home_link"))

    def wait_until_logged_in(self) -> bool:
        """True once the Logout link appears. WAITS, and times out if it never does.

        Call this only where a session IS expected, e.g. straight after a valid
        login. To assert NO session, use is_logged_in(), which does not wait.
        """
        return self.is_showing(self.sel("logout_link"))

    def is_logged_in(self) -> bool:
        """True if a session is active right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting the
        user is NOT logged in — the waiting reader would time out instead of
        returning False. Also used to branch on optional auth state.
        """
        return self.is_visible(self.sel("logout_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Assert containment
        ('Logged in as' in ...) rather than equality — the banner includes the
        account name.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    def is_signup_login_visible(self) -> bool:
        """True once the Login/Signup link is on screen. WAITS for it.

        Rendered only while signed OUT, so this appearing confirms the user is
        no longer recognised — the mirror of wait_until_logged_in().
        """
        return self.is_showing(self.sel("signup_login_link"))
