"""
AdminUsersPage — the OrangeHRM Admin > User Management > Users list.

Covers the search / results / delete flow for the user-lifecycle story:
navigate to the list, filter by username, read the record-count and the
no-records indicator, read the single result row's username, and drive the
delete confirmation dialog (confirm / cancel) plus the success toast.

Selectors come from the app inventory (`pages.admin_users`), never from
literals here.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list. Selectors: see `pages.admin_users` in the app inventory."""

    INVENTORY_PAGE = "admin_users"

    NO_RECORDS_TEXT = "No Records Found"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def is_loaded(self) -> bool:
        """True once the Add button (page chrome) is visible."""
        return self.is_showing(self.sel("add_button"))

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Click the 'Add' button to open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Type an exact username into the filter and submit the search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        # Wait for the results summary to reflect the new search.
        self.wait_visible(self.sel("records_found"))

    def click_row_delete(self) -> None:
        """Click the trash icon on the single result row.

        Only meaningful once the search has narrowed the list to one record —
        callers must assert get_record_count() == 1 first, so the first
        (and only) row is the one this test owns.
        """
        self.click(self.sel("row_delete_icon_first"))
        self.wait_visible(self.sel("delete_dialog"))

    def confirm_delete(self) -> None:
        """Confirm deletion in the confirmation dialog ('Yes, Delete')."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Cancel the confirmation dialog ('No, Cancel'), leaving the record."""
        self.click(self.sel("delete_cancel_button"))
        self.wait_hidden(self.sel("delete_dialog"))

    # ── queries ──────────────────────────────────────────────
    def get_record_count(self) -> int:
        """Number of result-row cards currently displayed."""
        return self.get_count(self.sel("table_rows"))

    def get_records_summary(self) -> str:
        """Text of the results summary, e.g. '(1) Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def has_no_records(self) -> bool:
        """True if the results summary shows the 'No Records Found' indicator."""
        return self.NO_RECORDS_TEXT in self.get_records_summary()

    def get_row_username(self) -> str:
        """Username cell of the first (and only) result row."""
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    def is_delete_dialog_open(self) -> bool:
        """True if the delete confirmation dialog is on screen."""
        return self.is_showing(self.sel("delete_dialog"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast (waits for it to appear)."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently visible. Never waits — for absence checks."""
        return self.is_visible(self.sel("toast"))
