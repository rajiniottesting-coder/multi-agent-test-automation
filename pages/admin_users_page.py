"""
AdminUsersPage — the OrangeHRM Admin > User Management > Users list page.

Provides navigation to the Add User form via click_add().
Selectors: see `pages.admin_users` in the app inventory.
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The system users list under Admin. Selectors come from the inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── actions ──────────────────────────────────────────────

    def open(self, base_url: str) -> None:
        """Navigate directly to the Admin Users list page.

        Args:
            base_url: application base URL from the fixture / environment.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def click_add(self) -> None:
        """Click the '+ Add' button to open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, name: str) -> None:
        """Type a username into the search filter and click Search.

        Args:
            name: the username (or partial) to search for.
        """
        self.fill(self.sel("search_username_input"), name)
        self.click(self.sel("search_button"))

    # ── queries ──────────────────────────────────────────────

    def get_record_count_text(self) -> str:
        """Return the '(N) Records Found' text shown above the table."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def is_loaded(self) -> bool:
        """True if the users list page has rendered its Add button."""
        return self.is_visible(self.sel("add_button"))
