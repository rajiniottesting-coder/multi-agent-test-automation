"""
NavPage — the top navigation bar and the session signals it carries.

Present on every page of the site, so it lives here once rather than being
duplicated onto each page object. It answers two kinds of question:

  - navigation: open Products, log out
  - readiness: am I logged in (Logout link present), am I logged out
    (Login / Signup link present), what name does the banner show

Selectors come from `pages.nav` in the app inventory — never a literal here.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory.

    The Logout link is rendered ONLY while authenticated and the Login/Signup
    link ONLY while signed out, so each is a reliable session signal — more
    reliable than the URL, which this app serves the same either way.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link and confirm the listing page loaded."""
        self.click(self.sel("products_link"))

    def logout(self) -> None:
        """Click the Logout link. Present only while logged in."""
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists RIGHT NOW. Never waits, never raises.

        The non-waiting probe, for asserting ABSENCE of a session — the
        waiting reader would time out instead of returning False. For asserting
        that a login SUCCEEDED, use wait_until_logged_in().
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Logout link appears. WAITS, and times out if it does not.

        Call this only where a session is the expected outcome — for example
        straight after submitting valid credentials. A step asking "am I logged
        in?" to branch on the answer would pay the full timeout every time the
        answer is no; use is_logged_in() there instead.
        """
        return self.is_showing(self.sel("logout_link"), timeout_ms=timeout_ms)

    def wait_until_logged_out(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Login / Signup link appears. WAITS, times out if not.

        The direct signal that no session exists — proves the presence of the
        signed-out state rather than merely the absence of the signed-in one.
        Call this only where being logged out is the expected outcome, such as
        after clicking Logout.
        """
        return self.is_showing(self.sel("signup_login_link"), timeout_ms=timeout_ms)

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session is expected. To assert NO session, use
        is_logged_in(), which does not wait.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))
