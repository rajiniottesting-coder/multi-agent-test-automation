"""
MenuPage — the OrangeHRM authenticated left navigation menu.

Injected on every authenticated page (`always: true` in the inventory), so it
provides module navigation (Admin, PIM, etc.) plus the user dropdown, logout
and the global toast reader.

Selectors: see `pages.menu` in the app inventory. No literal selectors here —
each element is looked up by its inventory key via self.sel(...).

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """The authenticated navigation menu. Selectors: see `pages.menu`."""

    INVENTORY_PAGE = "menu"

    # Maps a human module name to its inventory element key.
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
        """Click a top-level module link in the left menu.

        Args:
            module: the visible module name, e.g. 'Admin' or 'PIM'.
        """
        key = self._MODULE_LINKS[module]
        self.click(self.sel(key))
        self.wait_for_page_load("networkidle")

    def open_user_menu(self) -> None:
        """Open the user dropdown in the top bar."""
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user dropdown and click Logout."""
        self.open_user_menu()
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the global success/error toast (e.g. 'Successfully Saved')."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def is_module_active(self, module: str) -> bool:
        """True if the given module link is currently visible in the menu."""
        key = self._MODULE_LINKS[module]
        return self.is_visible(self.sel(key))
