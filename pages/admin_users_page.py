"""
AdminUsersPage — the Admin > User Management > Users list screen.

Used by validation tests to open the Add User form, search the list by
username, and read the record-count text for the 'no user created'
assertion.

Selectors: see `pages.admin_users` in the app inventory.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list screen. Selectors: see `pages.admin_users`."""

    INVENTORY_PAGE = "admin_users"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list screen."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Filter the list by an exact username and run the search."""
        self.wait_visible(self.sel("search_username_input"))
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        # Wait for the record-count text to refresh after the search runs.
        self.wait_visible(self.sel("records_found"))

    # ── queries ──────────────────────────────────────────────
    def get_record_count_text(self) -> str:
        """Raw '(N) Records Found' text shown above the results table."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_record_count(self) -> int:
        """Number of matching user records currently listed."""
        return self.get_count(self.sel("table_rows"))
