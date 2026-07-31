"""
AdminUsersPage — the Admin > User Management > Users list.

Page object for the Users list: exact-match search by username, the
records-found / no-records summary, the row delete icon, the delete
confirmation dialog (confirm / cancel) and the success toast.

Selectors: see `pages.admin_users` in the app inventory. This file holds
NO selector literals — every element is resolved via self.sel("<key>").

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list. Selectors: see `pages.admin_users` in the inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    # ── search ───────────────────────────────────────────────
    def search_by_username(self, username: str) -> None:
        """Enter an exact username into the filter and run the search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("records_found"))

    def get_records_summary(self) -> str:
        """Visible text of the results summary, e.g. '(1) Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_record_count(self) -> int:
        """Number of result rows currently rendered (no waiting)."""
        return self.get_count(self.sel("table_rows"))

    def has_no_records(self) -> bool:
        """True if the summary reports the empty state. Never raises."""
        if not self.is_visible(self.sel("records_found")):
            return False
        return "No Records Found" in self.get_text(self.sel("records_found"))

    def get_row_username(self) -> str:
        """Username shown in the first cell of the first result row.

        Only meaningful after the list is filtered to a single owned record.
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    # ── delete flow ──────────────────────────────────────────
    def click_row_delete(self) -> None:
        """Click the trash icon on the first result row.

        Only safe once the list has been searched down to the single record
        the test created — the icon selector matches every row's icon.
        """
        self.click(self.sel("row_delete_icon"))
        self.wait_visible(self.sel("delete_dialog"))

    def is_delete_dialog_open(self) -> bool:
        """True if the confirmation dialog is on screen. Never raises."""
        return self.is_visible(self.sel("delete_dialog"))

    def confirm_delete(self) -> None:
        """Click 'Yes, Delete' in the confirmation dialog."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Click 'No, Cancel' in the confirmation dialog and wait for close."""
        self.click(self.sel("delete_cancel_button"))
        self.wait_hidden(self.sel("delete_dialog"))

    # ── toast ────────────────────────────────────────────────
    def has_toast(self) -> bool:
        """True if a success/error toast is currently shown. Never raises."""
        return self.is_visible(self.sel("toast"))

    def get_toast_text(self) -> str:
        """Visible text of the toast banner."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
