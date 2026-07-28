"""
DashboardPage — where OrangeHRM lands after a successful login.

EXTENDABLE: Agent 2 may add methods here as new stories need them. Follow the
conventions in pages/login_page.py — selectors as class constants, business
verbs, BasePage helpers only.
"""
from pages.base_page import BasePage


class DashboardPage(BasePage):
    """The post-login landing page at /web/index.php/dashboard/index."""

    PATH = "/web/index.php/dashboard/index"

    # ── selectors ────────────────────────────────────────────
    # The breadcrumb header reads "Dashboard" and is the cheapest proof that
    # login succeeded.
    HEADER_TITLE = ".oxd-topbar-header-breadcrumb h6"
    USER_DROPDOWN = ".oxd-userdropdown-tab"
    USER_NAME = ".oxd-userdropdown-name"
    SIDE_MENU = ".oxd-sidepanel"
    SIDE_MENU_ITEMS = ".oxd-main-menu-item"
    SEARCH_MENU_INPUT = "input[placeholder='Search']"
    LOGOUT_LINK = "role=menuitem[name='Logout']"

    # ── queries ──────────────────────────────────────────────
    def get_header_title(self) -> str:
        """Breadcrumb title, e.g. 'Dashboard'."""
        self.wait_visible(self.HEADER_TITLE)
        return self.get_text(self.HEADER_TITLE)

    def is_loaded(self) -> bool:
        """True once the dashboard header is on screen."""
        return self.is_visible(self.HEADER_TITLE)

    def get_logged_in_user(self) -> str:
        """Display name in the top-right user dropdown."""
        return self.get_text(self.USER_NAME)

    def get_menu_items(self) -> list[str]:
        """Labels of every left-hand menu item."""
        return self.get_all_texts(self.SIDE_MENU_ITEMS)

    # ── actions ──────────────────────────────────────────────
    def open_user_menu(self) -> None:
        """Open the top-right user dropdown."""
        self.click(self.USER_DROPDOWN)

    def logout(self) -> None:
        """Open the user dropdown and sign out."""
        self.open_user_menu()
        self.click(self.LOGOUT_LINK)
