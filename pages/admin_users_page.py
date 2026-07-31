"""
AdminUsersPage — the Admin > User Management > Users list.

Selectors come from the `admin_users` inventory page; this class never holds a
literal selector string. Business verbs only: add, exact-username search,
record count / empty-state, row delete with the confirm/cancel dialog, and
toast reads.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list. Selectors: see `pages.admin_users` in the app inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def is_loaded(self) -> bool:
        """True once the results table is on screen."""
        return self.is_showing(self.sel("results_table"))

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Enter an exact username into the filter and run the search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        # Let the async result render (records summary updates in place).
        self.wait_visible(self.sel("records_found"))

    def click_row_delete(self) -> None:
        """Click the trash icon on the FIRST result row.

        Only meaningful once the list has been narrowed to the single record
        this test owns — assert the row count is 1 before calling this.
        """
        self.click(self.sel("row_delete_icon_first"))
        self.wait_visible(self.sel("delete_dialog"))

    def confirm_delete(self) -> None:
        """Confirm deletion in the open confirmation dialog."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Cancel/dismiss the open confirmation dialog without deleting."""
        self.click(self.sel("delete_cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def get_record_count(self) -> int:
        """Number of result rows currently displayed."""
        return self.get_count(self.sel("table_rows"))

    def get_records_found_text(self) -> str:
        """Text of the results summary (e.g. '(1) Records Found' or 'No Records Found')."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_row_username(self) -> str:
        """Username cell of the first result row.

        Positional: only meaningful after searching down to a single owned
        record.
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    def is_delete_dialog_open(self) -> bool:
        """True once the delete confirmation dialog is visible."""
        return self.is_showing(self.sel("delete_dialog"))

    def get_delete_confirm_label(self) -> str:
        """Visible label of the confirm button in the delete dialog."""
        self.wait_visible(self.sel("delete_confirm_button"))
        return self.get_text(self.sel("delete_confirm_button"))

    def get_toast_text(self) -> str:
        """Waiting reader for the success/error toast (asserting one APPEARED)."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """Non-waiting probe for the toast (asserting NO toast appeared)."""
        return self.is_visible(self.sel("toast"))
