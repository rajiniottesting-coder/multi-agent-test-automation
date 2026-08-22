"""
NavPage — the top navigation bar present on every page.

Selectors live once here rather than repeated on each page, because the nav is
shared site-wide (see `pages.nav` in the app inventory).

Two states matter: signed IN, where the Logout link and the 'Logged in as'
banner are rendered, and signed OUT, where the Login/Signup link is present
instead. Each side exposes a WAITING reader (for asserting the state has
arrived) and a NON-WAITING probe (for asserting the opposite state's absence,
or for branching), because a waiting probe can only answer "no" by timing out.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top nav and confirm the listing loaded.

        The click may be swallowed by an ad interstitial on the first
        navigation after a page load, so confirm_arrival on the destination
        re-issues the navigation if the browser did not actually move.
        """
        self.click(self.sel("products_link"))
        self.confirm_arrival()

    def logout(self) -> None:
        """Click 'Logout' in the top nav, ending the session."""
        self.click(self.sel("logout_link"))

    # ── queries: signed-in state ─────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS, and times out if none arrives.

        The Logout link is rendered only while authenticated, which is a more
        reliable signal than the URL — this app serves the same path signed in
        or out. Call this to assert a login SUCCEEDED; use is_logged_in() to
        assert it did not.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that a rejected login left the user signed OUT. Using the waiting
        reader for that would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. Assert containment of
        'Logged in as', not equality, because the account name follows it.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    # ── queries: signed-out state ────────────────────────────
    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS, and times out if one remains.

        The Login/Signup link is rendered only while signed out, so its
        presence is the direct signal for 'the user is not recognised'. Call
        this to assert a logout SUCCEEDED, rather than inferring it from the
        absence of the Logout link.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def has_signup_login_link(self) -> bool:
        """True if the Login/Signup link is showing right now. Never waits.

        Non-waiting probe for branching or for asserting the signed-out link
        is present without paying a full timeout when it is not.
        """
        return self.is_visible(self.sel("signup_login_link"))
