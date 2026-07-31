"""
DashboardPage — where OrangeHRM lands after a successful login.

EXTENDABLE: Agent 2 may add methods here as new stories need them. Follow the
conventions in pages/login_page.py — selectors from the app inventory via
self.sel(), business verbs, BasePage helpers only.
"""
from typing import Optional

from pages.base_page import BasePage


class DashboardPage(BasePage):
    """The post-login landing page. Selectors: `pages.dashboard` in the inventory."""

    INVENTORY_PAGE = "dashboard"

    # ── queries ──────────────────────────────────────────────
    def get_header_title(self) -> str:
        """Breadcrumb title, e.g. 'Dashboard'."""
        self.wait_visible(self.sel("header_title"))
        return self.get_text(self.sel("header_title"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the dashboard header is on screen. WAITS for it.

        THE REFERENCE READINESS PROBE - copy this shape, not an older one.

        Waiting is essential and was the bug this replaced. The app is a
        single-page app: submitting the login form fires an XHR and re-renders
        asynchronously, so the dashboard is never present the instant
        login_as() returns. The previous implementation used is_visible(),
        which BasePage documents as "no waiting" - it checked immediately and
        returned False every time, failing every test that needed a successful
        login, and cascading into timeouts for anything that navigated after.

        Two later corrections are baked in here:

        - `timeout_ms=None` inherits `browser.timeout` from config.yaml. The
          hard-coded 10000 that used to sit here ignored the configured value
          entirely, so tuning the config did nothing for this page.
        - it delegates to BasePage.is_showing() rather than swallowing the
          Playwright error in a bare `except`. A failed readiness check now
          logs the selector, the wait and the current URL; before, the whole
          diagnosis a CI log offered was `assert False`.

        Returns a bool rather than raising, so `assert page.is_loaded()` still
        reads naturally. Use is_displayed_now() for a true zero-wait probe.
        """
        return self.is_showing(self.sel("header_title"), timeout_ms=timeout_ms)

    def is_displayed_now(self) -> bool:
        """True only if the dashboard header is visible RIGHT NOW. No waiting.

        For asserting the dashboard is absent, or probing without cost. Never
        use this immediately after an action that triggers a re-render.
        """
        return self.is_visible(self.sel("header_title"))

    def get_logged_in_user(self) -> str:
        """Display name in the top-right user dropdown."""
        return self.get_text(self.sel("user_name"))

    def get_menu_items(self) -> list[str]:
        """Labels of every left-hand menu item."""
        return self.get_all_texts(self.sel("side_menu_items"))

    # ── actions ──────────────────────────────────────────────
    def open_user_menu(self) -> None:
        """Open the top-right user dropdown."""
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user dropdown and sign out.

        logout_link only renders AFTER the dropdown is open — see the
        elements_notes on `pages.dashboard` in the inventory.
        """
        self.open_user_menu()
        self.click(self.sel("logout_link"))