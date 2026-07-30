"""
MenuPage — the authenticated OrangeHRM left-hand navigation menu.

Selectors: see `pages.menu` in the app inventory. This page is injected on
every authenticated screen, so it is the single entry point for reaching any
module (Admin, PIM, etc.) from a logged-in state.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """The left-hand navigation menu. Selectors: `pages.menu` in the inventory."""

    INVENTORY_PAGE = "menu"

    # ── actions ──────────────────────────────────────────────
    def go_to_admin(self) -> None:
        """Click the Admin link to reach the User Management module."""
        self.click(self.sel("admin_link"))

    def go_to_pim(self) -> None:
        """Click the PIM link to reach the employee list module."""
        self.click(self.sel("pim_link"))

    # ── queries ──────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast, e.g. 'Successfully Saved'."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
