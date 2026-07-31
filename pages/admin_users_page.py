"""
AdminUsersPage — the Admin > User Management > Users list screen.

Selectors: see `pages.admin_users` in the app inventory. Handles adding a
user, filtering the list by username, reading the records-found summary,
and deleting a row through the confirm/cancel dialog.

App: https://opensource-demo.orangehrmlive.com

BASEPAGE-REQUEST: none — the delete confirmation dialog buttons and the
per-row delete icon are not in the admin_users inventory `elements` map, so
they are declared as page-local constants below. See notes in method
docstrings.
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The system Users list. Selectors: see `pages.admin_users` in the inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── page-local selectors not present in the inventory `elements` map ──
    # The per-row delete icon and the confirmation-dialog controls were not
    # captured by the crawler (the dialog renders only after the trash icon
    # is clicked). They use stable OrangeHRM design-system class names.
    ROW_DELETE_ICON = ".oxd-table-card .oxd-icon.bi-trash"
    CONFIRM_DELETE_BUTTON = ".oxd-dialog-container-default button:has-text('Yes, Delete')"
    CANCEL_DELETE_BUTTON = ".oxd-dialog-container-default button:has-text('No, Cancel')"
    DELETE_DIALOG = ".oxd-dialog-container-default"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the Users list screen."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Enter a username into the filter and click Search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        # Let the results summary re-render after the filter applies.
        self.wait_visible(self.sel("records_found"))

    def clear_search(self) -> None:
        """Empty the username filter without searching."""
        self.clear(self.sel("search_username_input"))

    def click_row_delete(self) -> None:
        """Click the trash/delete icon on the first (matching) row.

        In exact-username searches this row is the only one shown, so the
        first delete icon is the record under test.
        """
        self.wait_visible(self.ROW_DELETE_ICON)
        self.click(self.ROW_DELETE_ICON)
        self.wait_visible(self.DELETE_DIALOG)

    def confirm_delete(self) -> None:
        """Confirm deletion in the dialog by clicking 'Yes, Delete'."""
        self.wait_visible(self.CONFIRM_DELETE_BUTTON)
        self.click(self.CONFIRM_DELETE_BUTTON)

    def cancel_delete(self) -> None:
        """Dismiss the delete dialog via its cancel control without deleting."""
        self.wait_visible(self.CANCEL_DELETE_BUTTON)
        self.click(self.CANCEL_DELETE_BUTTON)
        self.wait_hidden(self.DELETE_DIALOG)

    # ── queries ──────────────────────────────────────────────
    def get_records_found_text(self) -> str:
        """Text of the results summary, e.g. '(1) Records Found' or 'No Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_record_count(self) -> int:
        """Number of result rows currently rendered in the table."""
        return self.get_count(self.sel("table_rows"))

    def has_no_records(self) -> bool:
        """True if the summary reports 'No Records Found'."""
        return "No Records Found" in self.get_records_found_text()

    def get_row_usernames(self) -> list[str]:
        """Every value in the Username column across the visible rows."""
        return self.get_all_texts(self.sel("table_rows"))

    def is_delete_dialog_displayed(self) -> bool:
        """True if the delete confirmation dialog is currently on screen."""
        return self.is_visible(self.DELETE_DIALOG)

    def get_toast_text(self) -> str:
        """Text of the success/error toast, e.g. 'Successfully Deleted'."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
