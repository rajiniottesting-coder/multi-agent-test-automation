"""
MenuPage — authenticated left-hand navigation for OrangeHRM.

Injected on every authenticated page, so it is used to reach any module
(here: Admin > Users) before a scenario begins its real work.

Selectors: see `pages.menu` in the app inventory. This file holds no literal
selector strings — every element is looked up via self.sel("<key>").

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """The authenticated main menu. Selectors: see `pages.menu` in the app inventory."""

    INVENTORY_PAGE = "menu"

    # Map a human module name to its inventory link key.
    _MODULE_LINKS = {
        "Admin": "admin_link",
        "PIM": "pim_link",
        "Leave": "leave_link",
        "Time": "time_link",
        "Recruitment": "recruitment_link",
        "My Info": "my_info_link",
        "Performance": "performance_link",
        "Dashboard": "dashboard_link",
        "Directory": "directory_link",
        "Maintenance": "maintenance_link",
        "Claim": "claim_link",
        "Buzz": "buzz_link",
    }

    # ── actions ──────────────────────────────────────────────
    def go_to(self, module: str) -> None:
        """Click a top-level module link in the side menu.

        Args:
            module: human module name, e.g. 'Admin' or 'PIM'.
        """
        link_key = self._MODULE_LINKS[module]
        self.click(self.sel(link_key))
        self.wait_for_page_load("networkidle")

    def open_user_menu(self) -> None:
        """Open the top-right user dropdown."""
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user dropdown and click Logout."""
        self.open_user_menu()
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast, e.g. 'Successfully Saved'."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
