"""
AdminUsersPage — the Admin > User Management > Users list (viewSystemUsers).

Covers username search, record-count / empty-state reads, the per-row delete
icon, and the confirm/cancel controls of the delete dialog.

Selectors: see `pages.admin_users` in the app inventory. This file never holds
a literal selector — every element is resolved through self.sel("<key>").

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

    def is_loaded(self) -> bool:
        """True once the results table container is present."""
        return self.is_showing(self.sel("results_table"))

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Filter the list by username and run the search.

        Uses type_text (real keystrokes) rather than fill: the inventory notes
        that fill() sets the visible value but never binds the Vue model, so
        Search re-requests the unfiltered list.
        """
        self.clear(self.sel("search_username_input"))
        self.type_text(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))

    def click_row_delete(self) -> None:
        """Click the trash icon of the single result row.

        Only safe once the list is narrowed to one row — callers must assert
        get_record_count() == 1 first (clicking a multi-match icon on this
        shared demo would delete someone else's user).
        """
        self.click(self.sel("row_delete_icon_first"))

    def confirm_delete(self) -> None:
        """Confirm deletion in the confirmation dialog ('Yes, Delete')."""
        self.wait_visible(self.sel("delete_dialog"))
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Dismiss the confirmation dialog without deleting ('No, Cancel')."""
        self.wait_visible(self.sel("delete_dialog"))
        self.click(self.sel("delete_cancel_button"))

    # ── waits / synchronisation ──────────────────────────────
    def wait_for_record_count(self, expected_text: str) -> None:
        """Wait for the results summary to read the expected text.

        The summary re-renders asynchronously after Search; reading it straight
        away returns the previous value. Callers pass e.g. '(1) Records Found'
        or 'No Records Found' and this waits for it to settle.
        """
        self.wait_for_text(self.sel("records_found"), expected_text)

    def wait_for_delete_dialog(self) -> None:
        """Wait for the delete confirmation dialog to appear."""
        self.wait_visible(self.sel("delete_dialog"))

    # ── queries ──────────────────────────────────────────────
    def get_record_count(self) -> int:
        """Number of result rows currently rendered."""
        return self.get_count(self.sel("table_rows"))

    def get_records_summary(self) -> str:
        """Text of the results summary, e.g. '(1) Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_row_username(self) -> str:
        """Username cell of the first (and only, when filtered) result row."""
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    def is_delete_dialog_open(self) -> bool:
        """True if the delete confirmation dialog is on screen. Never raises."""
        return self.is_visible(self.sel("delete_dialog"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it to appear."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently shown. Never raises — use for absence."""
        return self.is_visible(self.sel("toast"))
