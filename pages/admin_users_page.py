"""
AdminUsersPage — the Admin > User Management > Users list screen.

Exposes actions for opening the Add User form and searching the users list,
plus a record-count query used to confirm that no user was created.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list screen. Selectors: see `pages.admin_users` in the app inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Open the Add User form via the 'Add' button."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Filter the users list by the given username and submit the search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))

    # ── queries ──────────────────────────────────────────────
    def get_records_found_text(self) -> str:
        """Raw text of the records-found summary, e.g. '(0) Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_record_count(self) -> int:
        """Number of user rows currently shown in the results table."""
        return self.get_count(self.sel("table_rows"))
