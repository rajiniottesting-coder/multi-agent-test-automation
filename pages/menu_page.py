"""
MenuPage — the OrangeHRM left-side navigation menu.

Present on every authenticated page. Provides navigation to any module
via the sidebar links, user menu actions, and toast message reading.

Selectors: see `pages.menu` in the app inventory.
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """Left-side navigation menu, visible on all authenticated pages."""

    INVENTORY_PAGE = "menu"

    # ── module name → inventory element key mapping ──────────
    _MODULE_KEYS: dict[str, str] = {
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
        """Navigate to a top-level module by its display name.

        Args:
            module: The visible name of the module link, e.g. 'Admin', 'PIM'.
        """
        key = self._MODULE_KEYS.get(module)
        if key is None:
            raise ValueError(
                f"Unknown module {module!r}. "
                f"Valid modules: {', '.join(sorted(self._MODULE_KEYS))}"
            )
        self.click(self.sel(key))
        self.wait_for_page_load()

    def open_user_menu(self) -> None:
        """Click the user dropdown in the top-right corner."""
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user menu and click Logout."""
        self.open_user_menu()
        self.wait_visible(self.sel("logout_link"))
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Return the text of the currently visible toast notification."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
