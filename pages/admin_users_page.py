"""
AdminUsersPage — the OrangeHRM Admin > User Management > Users list.

Selectors: see `pages.admin_users` in the app inventory. This page object never
holds a literal selector — every element is resolved via self.sel("<key>").

Covers the user-lifecycle behaviours: add a user, search by exact username,
read the results summary, inspect the single result row, and drive the
delete-confirmation dialog (confirm or cancel).

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list screen. Selectors: see `pages.admin_users` in the inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Enter an exact username into the filter and submit the search."""
        self.fill(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))

    def wait_for_records_found(self, expected_summary: str) -> None:
        """Wait until the results summary shows the expected text.

        The summary re-renders asynchronously after Search, so reading it
        immediately races the request. Waiting for the expected text avoids a
        stale-value flake.
        """
        self.wait_for_text(self.sel("records_found"), expected_summary)

    def click_row_delete(self) -> None:
        """Click the trash icon on the FIRST (and only) result row.

        Callers MUST prove the list is down to a single owned record
        (row_count() == 1) before calling this on the shared demo.
        """
        self.click(self.sel("row_delete_icon_first"))
        self.wait_visible(self.sel("delete_dialog"))

    def confirm_delete(self) -> None:
        """Confirm the delete-confirmation dialog ('Yes, Delete')."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Cancel the delete-confirmation dialog ('No, Cancel')."""
        self.click(self.sel("delete_cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def get_records_summary(self) -> str:
        """Visible text of the results summary, e.g. '(1) Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def row_count(self) -> int:
        """Number of result rows currently rendered."""
        return self.get_count(self.sel("table_rows"))

    def get_row_username(self) -> str:
        """Username cell of the first result row.

        Only meaningful once the search has narrowed the list to one owned row.
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    def is_delete_dialog_open(self) -> bool:
        """True if the confirmation dialog is currently displayed. Never raises."""
        return self.is_visible(self.sel("delete_dialog"))

    def has_toast(self) -> bool:
        """True if a toast is currently shown. Never raises — safe for absence checks."""
        return self.is_visible(self.sel("toast"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it to appear."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
