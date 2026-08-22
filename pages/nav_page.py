"""
NavPage — the shared top navigation, present on every page of the site.

Selectors: see `pages.nav` in the app inventory. The nav mixes icon libraries,
so its links are addressed by href (pinned with nth=0 to skip footer repeats)
rather than by ARIA role+name — see the inventory notes for why role-name
matching fails on this site.

Exposes:
  - navigation to the products listing and to logout
  - waiting and non-waiting readers for the logged-in / logged-out state
  - the 'Logged in as <name>' banner text

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Shared top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click 'Products' in the top navigation to reach the listing page.

        The click is a cross-page navigation, so this cannot confirm arrival on
        its own — the destination page object's is_loaded() readiness probe
        does that in the step definition.
        """
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click 'Logout' in the top navigation, ending the session.

        Present only while logged in; the app redirects to /login afterwards.
        """
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a session exists. WAITS, and times out if it never does.

        The Logout link is rendered only while authenticated, which is a more
        reliable signal than the URL — this app serves the same path signed in
        or out. Call this to ASSERT a login succeeded; for a branch-on-state
        check that must not wait, use is_logged_in().
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def is_logged_in(self) -> bool:
        """True if a session exists right now. Never waits, never raises.

        The non-waiting counterpart to wait_until_logged_in(), for asserting
        that NO session exists (negate this) or for branching. Using the
        waiting reader for absence would time out instead of returning False.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once no session exists. WAITS, and times out if one persists.

        The Login/Signup link is rendered only while signed out, so its
        presence proves the user is no longer recognised — stronger than
        asserting the Logout link is merely absent. Call this to ASSERT a
        logout succeeded.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. The banner is a substring
        match ('Logged in as <name>'), so assert containment, not equality.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
