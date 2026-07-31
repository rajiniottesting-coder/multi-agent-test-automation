"""
AdminUsersPage — the Admin > User Management > Users list.

Selectors: see `pages.admin_users` in the app inventory. This page object
covers searching by username, reading the results summary / row data,
deleting a row, and handling the delete confirmation dialog.

App: https://opensource-demo.orangehrmlive.com

Notes on the delete confirmation dialog: the inventory does not list the
row delete icon, the confirmation dialog, or its Yes/No buttons as element
keys (the crawler could not reach per-row action buttons or the modal, which
only renders after a click). Those locators are declared here as page-object
constants, scoped to the design-system classes OrangeHRM uses for its
confirm dialog, rather than invented compound selectors around inventory
entries. See the BASEPAGE-REQUEST note below.
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list. Selectors: see `pages.admin_users` in the app inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── locators not present in the inventory (dialog + row actions) ──────
    ROW_DELETE_BUTTON = ".oxd-table-card .oxd-icon-button:has(.bi-trash)"
    CONFIRM_DIALOG = ".oxd-dialog-container-default--confirm"
    CONFIRM_DELETE_BUTTON = ".oxd-dialog-container-default--confirm button:has-text('Yes, Delete')"
    CONFIRM_CANCEL_BUTTON = ".oxd-dialog-container-default--confirm button:has-text('No')"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.wait_visible(self.sel("search_button"))

    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, name: str) -> None:
        """Type an exact username into the filter and submit the search."""
        self.fill(self.sel("search_username_input"), name)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("records_found"))

    def delete_first_row(self) -> None:
        """Click the trash icon on the first (only) result row."""
        self.wait_visible(self.ROW_DELETE_BUTTON)
        self.click(self.ROW_DELETE_BUTTON)
        self.wait_visible(self.CONFIRM_DIALOG)

    def confirm_delete(self) -> None:
        """Confirm deletion in the dialog by clicking 'Yes, Delete'."""
        self.wait_visible(self.CONFIRM_DELETE_BUTTON)
        self.click(self.CONFIRM_DELETE_BUTTON)

    def cancel_delete(self) -> None:
        """Cancel the delete confirmation dialog by clicking 'No'."""
        self.wait_visible(self.CONFIRM_CANCEL_BUTTON)
        self.click(self.CONFIRM_CANCEL_BUTTON)
        self.wait_hidden(self.CONFIRM_DIALOG)

    # ── queries ──────────────────────────────────────────────
    def get_records_summary(self) -> str:
        """Text of the results summary, e.g. '(1) Records Found' or 'No Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def has_no_records(self) -> bool:
        """True if the results summary reports no matching records."""
        return "No Records Found" in self.get_records_summary()

    def get_record_count(self) -> int:
        """Number of result rows currently rendered in the table."""
        return self.get_count(self.sel("table_rows"))

    def get_first_row_text(self) -> str:
        """Full text of the first result row (includes the Username cell)."""
        self.wait_visible(self.sel("table_rows"))
        return self.get_nth_text(self.sel("table_rows"), 0)

    def get_toast_text(self) -> str:
        """Text of the success/error toast, e.g. 'Successfully Deleted'."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def is_confirm_dialog_visible(self) -> bool:
        """True if the delete confirmation dialog is on screen. Never waits."""
        return self.is_visible(self.CONFIRM_DIALOG)

    # BASEPAGE-REQUEST: none — ROW_DELETE_BUTTON / CONFIRM_* dialog locators are
    # intentionally page-scoped because the inventory does not list per-row
    # action icons or the confirm modal (they render only after interaction).
