"""
MenuPage — the OrangeHRM left sidebar menu.

Provides navigation to Admin, PIM, and other modules from any authenticated page.
Also handles the user dropdown (logout) and toast messages.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class MenuPage(BasePage):
    """The left sidebar menu. Selectors: see `pages.menu` in the app inventory."""

    INVENTORY_PAGE = "menu"

    # ── navigation ───────────────────────────────────────────
    def go_to_admin(self) -> None:
        """Click the Admin link in the sidebar menu."""
        self.click(self.sel("admin_link"))
        self.wait_for_page_load()

    def go_to_pim(self) -> None:
        """Click the PIM link in the sidebar menu."""
        self.click(self.sel("pim_link"))
        self.wait_for_page_load()

    def go_to_dashboard(self) -> None:
        """Click the Dashboard link in the sidebar menu."""
        self.click(self.sel("dashboard_link"))
        self.wait_for_page_load()

    def go_to(self, module: str) -> None:
        """Navigate to a module by name.

        Args:
            module: The visible link text, e.g. 'Admin', 'PIM', 'Leave'.
        """
        link_key = f"{module.lower().replace(' ', '_')}_link"
        self.click(self.sel(link_key))
        self.wait_for_page_load()

    # ── user dropdown / logout ───────────────────────────────
    def open_user_menu(self) -> None:
        """Open the user dropdown in the top-right corner."""
        self.click(self.sel("user_dropdown"))

    def logout(self) -> None:
        """Open the user dropdown and click Logout."""
        self.open_user_menu()
        self.wait_visible(self.sel("logout_link"))
        self.click(self.sel("logout_link"))

    # ── toast ────────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Return the text of the currently visible toast notification."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def is_toast_visible(self) -> bool:
        """True if a toast notification is currently visible."""
        return self.is_visible(self.sel("toast"))

    # ── sidebar search ───────────────────────────────────────
    def search_menu(self, term: str) -> None:
        """Type into the sidebar search input to filter menu items.

        Args:
            term: The search text to filter menu links.
        """
        self.fill(self.sel("menu_search_input"), term)
