"""
AdminUsersPage — the OrangeHRM Admin > User Management > Users list.

Covers: navigating to the list, adding (via the Add button), searching by
exact username, reading the results summary / no-records state, counting
result rows, deleting a single owned row, and confirming or cancelling the
delete confirmation dialog.

Selectors come from the `admin_users` page in the app inventory — never from a
literal in this file.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list. Selectors: see `pages.admin_users` in the app inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.wait_visible(self.sel("search_button"))

    def click_add(self) -> None:
        """Click the 'Add' button to open the Add User form."""
        self.click(self.sel("add_button"))

    # ── search ───────────────────────────────────────────────
    def search_by_username(self, username: str) -> None:
        """Enter an exact username into the filter and click Search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        # The summary text updates once the query returns; wait for it.
        self.wait_visible(self.sel("records_found"))

    # ── results / state ──────────────────────────────────────
    def get_record_count(self) -> int:
        """Number of result row cards currently rendered."""
        return self.get_count(self.sel("table_rows"))

    def get_records_summary(self) -> str:
        """Text of the results summary, e.g. '(1) Records Found' or 'No Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def has_no_records(self) -> bool:
        """True if the results summary reports no matching records."""
        return "No Records Found" in self.get_records_summary()

    def get_row_username(self) -> str:
        """Username cell text of the first (and, for owned searches, only) row.

        Only meaningful after searching down to a single owned record.
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    # ── delete ───────────────────────────────────────────────
    def click_row_delete(self) -> None:
        """Click the trash icon on the first result row.

        Only safe once the search has narrowed the list to the single record
        this test owns.
        """
        self.click(self.sel("row_delete_icon_first"))
        self.wait_visible(self.sel("delete_dialog"))

    def confirm_delete(self) -> None:
        """Confirm the deletion in the confirmation dialog."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Cancel/dismiss the confirmation dialog without deleting."""
        self.click(self.sel("delete_cancel_button"))
        self.wait_hidden(self.sel("delete_dialog"))

    def is_delete_dialog_visible(self) -> bool:
        """True if the delete confirmation dialog is on screen. Never raises."""
        return self.is_visible(self.sel("delete_dialog"))

    def get_delete_dialog_text(self) -> str:
        """Text of the delete confirmation dialog."""
        self.wait_visible(self.sel("delete_dialog"))
        return self.get_text(self.sel("delete_dialog"))

    # ── toast ────────────────────────────────────────────────
    def has_toast(self) -> bool:
        """True if a success/error toast is currently shown. Never raises."""
        return self.is_visible(self.sel("toast"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
