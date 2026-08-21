"""
NavPage — the top navigation bar shared across every page.

Selectors: see `pages.nav` in the app inventory. The nav lives once here
rather than being repeated on each page object.

Two conventions this page leans on:
  - The Logout link is rendered ONLY while authenticated, so its presence is a
    more reliable "am I logged in" signal than the URL (this app serves the
    same path signed in or out).
  - The Signup/Login link is rendered ONLY while signed OUT — the mirror of
    Logout. Its presence confirms the user is not recognised.

Nav links are addressed by href, not by role+name, because this app's icon
markup (Material Icons ligature text) pollutes the accessible name. See the
inventory notes for detail.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class NavPage(BasePage):
    """Top navigation. Selectors: see `pages.nav` in the app inventory."""

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def open_products(self) -> None:
        """Click the Products link in the top navigation and land on /products."""
        self.click(self.sel("products_link"))
        # Confirm arrival on the products listing rather than trusting the click.
        self.wait_for_url("**/products")

    def logout(self) -> None:
        """Click Logout; the app redirects to the login page."""
        self.click(self.sel("logout_link"))
        self.wait_for_url("**/login")

    # ── queries ──────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        """True if a session exists right now. Non-waiting, for ABSENCE checks.

        The Logout link is present only while authenticated. This reads the
        page ONCE and never raises, so it is the right probe for asserting the
        ABSENCE of a session (an invalid login) — waiting for something
        legitimately absent would cost a full timeout every run. For asserting
        a session DID appear, use wait_until_logged_in(), which waits.
        """
        return self.is_visible(self.sel("logout_link"))

    def wait_until_logged_in(self) -> bool:
        """True once a session exists. WAITS for the Logout link to appear.

        The waiting counterpart to is_logged_in(), for asserting that a valid
        login succeeded. is_showing() retries until the timeout and logs the
        reason it gave up, so it will not race the post-login redirect.
        """
        return self.is_showing(self.sel("logout_link"))

    def wait_until_logged_out(self) -> bool:
        """True once no session exists. WAITS for the Signup/Login link.

        The Signup/Login link is rendered only while signed out — the mirror
        of the Logout link — so its appearance confirms the user is no longer
        recognised after logging out. is_showing() retries until the timeout
        and logs the reason it gave up.
        """
        return self.is_showing(self.sel("signup_login_link"))

    def logged_in_name(self) -> str:
        """The 'Logged in as <name>' banner text. WAITS for it to appear.

        Only call this when a session IS expected. To assert no session, use
        is_logged_in(), which does not wait.
        """
        self.wait_visible(self.sel("logged_in_as"))
        return self.get_text(self.sel("logged_in_as"))

    def has_login_link(self) -> bool:
        """True once the Signup/Login link is showing. WAITS for it.

        A step definition asserts on this to confirm the signed-out navigation
        state, so it uses is_showing() — which retries until the timeout and
        logs the reason it gave up — rather than a single-shot read that could
        race a redirect and report False while the app is working correctly.
        """
        return self.is_showing(self.sel("signup_login_link"))
