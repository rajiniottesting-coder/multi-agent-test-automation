"""
AdminUsersPage — the Admin > User Management > Users list.

Opens the Add User form and searches the user list by username so a test can
prove a record was NOT created. Selectors come from the `admin_users` entry in
the app inventory; this file never hardcodes a selector string.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list screen. Selectors: see `pages.admin_users` in the inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.wait_visible(self.sel("add_button"))

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Filter the list by an exact username and run the search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("records_found"))

    # ── queries ──────────────────────────────────────────────
    def get_records_summary(self) -> str:
        """Text of the results summary, e.g. '(0) Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def has_no_records(self) -> bool:
        """True when the list shows zero records for the current filter.

        Reads the application's own results summary rather than counting rows,
        which is safe on this shared demo where the table may still render
        stale rows before a filter applies.
        """
        summary = self.get_records_summary()
        return "(0)" in summary or "No Records Found" in summary
