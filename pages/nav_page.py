"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. The nav lives on every page,
so its queries and actions belong here rather than repeated on each page object.

Presence of the Logout link is the reliable "am I authenticated" signal on this
app, because the same path ('/') is served whether signed in or out. The
signup/login link is the mirror signal, present only while signed out.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation and confirm arrival."""
        self.click(self.sel("products_link"))
        from pages.products_page import ProductsPage

        ProductsPage(self.page).confirm_arrival()

    def logout(self) -> None:
        """Click 'Logout' in the top navigation, ending the session."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        Reads the Logout link, which is rendered ONLY while authenticated.
        Use this to assert ABSENCE of a session (negate it) — the non-waiting
        probe returns False immediately when logged out rather than timing out.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS, and times out if none appears.

        Call this only where being logged in is the expected outcome (e.g.
        right after a successful login). A step asking "am I logged in?" to
        branch on the answer should use is_logged_in() instead, or it pays the
        full timeout every time the answer is no.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS for the signup/login link.

        The signup/login link is rendered ONLY while signed out, so it is the
        direct positive signal for the logged-out state. Assert on this rather
        than negating a logged-in probe — an error page has no Logout link
        either, so absence of Logout does not prove a clean logout.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Returns the whole banner,
        so assert containment ('Logged in as' in ...) rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
