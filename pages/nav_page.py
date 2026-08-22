"""
NavPage — the top navigation bar shared by every page.

Style copied from pages/login_page.py (the reserved reference):
  - selectors come from the app inventory, never a literal in this file;
    set INVENTORY_PAGE, then use self.sel("<element_key>")
  - methods are business verbs (open_products, logout), not UI mechanics
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

Two readers for authentication state are exposed on purpose:
  - wait_until_logged_in() / wait_until_logged_out() WAIT, for asserting a
    state has been reached after an action
  - is_logged_in() does NOT wait, for asserting a state is ABSENT without
    paying a full timeout

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory.

    Links are pinned by href with `>> nth=0` in the inventory because the
    footer repeats several of them; the header block precedes the footer in
    the DOM, so nth=0 is always the header link.
    """

    INVENTORY_PAGE = "nav"

    # ── navigation actions ───────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation and confirm arrival.

        confirm_arrival() re-issues the navigation if an ad interstitial ate
        the click, so the next step never waits on a page nobody reached.
        """
        self.click(self.sel("products_link"))
        from pages.products_page import ProductsPage
        ProductsPage(self.page).confirm_arrival()

    def open_signup_login(self) -> None:
        """Click the Signup / Login link in the top navigation."""
        self.click(self.sel("signup_login_link"))

    def logout(self) -> None:
        """Click the Logout link. Ends the session and redirects to /login."""
        self.click(self.sel("logout_link"))

    # ── authentication state (WAITING readers, for presence) ──
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link is present. WAITS, times out if it is not.

        Call this only where a logged-in state is the expected answer. A step
        asking 'am I logged in?' to branch on the reply would pay the full
        timeout every time the answer is no — use is_logged_in() for that.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Signup / Login link is present. WAITS, times out if not.

        The Signup / Login link is rendered only while signed OUT, so its
        presence is a direct signal of the logged-out state — more honest than
        asserting the absence of the Logout link, which is also true on an
        error page. Call only where logged-out is the expected answer.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    # ── authentication state (NON-waiting probe, for absence) ─
    def is_logged_in(self) -> bool:
        """True if the Logout link is visible right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that a session does NOT exist. Using the waiting reader for absence
        would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def is_signup_login_visible(self) -> bool:
        """True if the Signup / Login link is visible right now. Never waits.

        For asserting the top navigation offers the signed-out link after a
        logout, without paying a timeout in the case where it is absent.
        """
        return self.is_visible(self.sel("signup_login_link"))

    # ── logged-in banner ─────────────────────────────────────
    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. Reads a substring match, so
        the caller should assert containment rather than equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
