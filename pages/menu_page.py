"""
MenuPage — the always-present authenticated left navigation menu.

Injected on every authenticated OrangeHRM page (inventory marks it
`always: true`). Used to navigate between modules — here specifically to the
Admin > User Management module — and to read the global success/error toast.

Selectors: see `pages.menu` in the app inventory. This file never contains a
literal selector; every element is resolved via self.sel("<key>").

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """The authenticated side menu. Selectors: see `pages.menu` in the inventory."""

    INVENTORY_PAGE = "menu"

    # Maps a friendly module name to its inventory element key.
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
        """Click the left-menu link for the named module (e.g. 'Admin').

        Args:
            module: the visible module label as it appears in the side menu.
        """
        key = self._MODULE_LINKS[module]
        self.click(self.sel(key))

    def open_user_menu(self) -> None:
        """Open the top-right user dropdown (reveals the Logout item)."""
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user dropdown and click Logout."""
        self.open_user_menu()
        self.click(self.sel("logout_link"))

    # ── queries ──────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the global success/error toast.

        Waiting reader: use this to assert a toast APPEARED. It waits for the
        toast to become visible before reading, so a non-waiting probe called
        straight after an action cannot race the request.
        """
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently visible. Never waits, never raises.

        The non-waiting counterpart to get_toast_text — use this to assert that
        NO toast appeared (e.g. after cancelling a dialog).
        """
        return self.is_visible(self.sel("toast"))
