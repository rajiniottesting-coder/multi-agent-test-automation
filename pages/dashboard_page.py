"""
DashboardPage — where OrangeHRM lands after a successful login.

EXTENDABLE: Agent 2 may add methods here as new stories need them. Follow the
conventions in pages/login_page.py — selectors from the app inventory via
self.sel(), business verbs, BasePage helpers only.
"""
from pages.base_page import BasePage


class DashboardPage(BasePage):
    """The post-login landing page. Selectors: `pages.dashboard` in the inventory."""

    INVENTORY_PAGE = "dashboard"

    # ── queries ──────────────────────────────────────────────
    def get_header_title(self) -> str:
        """Breadcrumb title, e.g. 'Dashboard'."""
        self.wait_visible(self.sel("header_title"))
        return self.get_text(self.sel("header_title"))

    def is_loaded(self) -> bool:
        """True once the dashboard header is on screen."""
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