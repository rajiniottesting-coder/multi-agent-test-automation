"""
AdminUsersPage — the OrangeHRM Admin > User Management > Users list.

Selectors: see `pages.admin_users` in the app inventory. This page object
follows the LoginPage reference conventions:

  - INVENTORY_PAGE + self.sel("<key>"); never a literal selector here.
  - methods are business verbs, not UI mechanics.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

Notes on the tricky elements (from the inventory):
  - search_username_input MUST use type_and_confirm (fill() never binds the
    Vue model, so Search re-requests the unfiltered list).
  - records_found re-renders asynchronously after Search; use wait_for_text to
    wait for the expected fragment rather than reading immediately.
  - row_delete_icon is multi-match: click row_delete_icon_first only after the
    list is proven down to a single row.

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

    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    # ── search ───────────────────────────────────────────────
    def search_by_username(self, username: str) -> None:
        """Filter the list by username and submit the search.

        Uses type_and_confirm because fill() never binds the Vue model on this
        field, which would cause Search to re-request the unfiltered list.
        """
        self.type_and_confirm(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))

    def wait_for_records_summary(self, expected_fragment: str) -> None:
        """Wait until the results summary contains the expected text.

        The summary re-renders asynchronously after Search, so reading it
        immediately is a race. Wait for the expected fragment instead.
        """
        self.wait_for_text(self.sel("records_found"), expected_fragment)

    # ── queries ──────────────────────────────────────────────
    def get_record_count(self) -> int:
        """Number of result rows currently rendered in the table."""
        return self.get_count(self.sel("table_rows"))

    def get_records_summary(self) -> str:
        """Text of the results summary, e.g. '(1) Record Found' or 'No Records Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_row_username(self) -> str:
        """Username shown in the first result row's Username cell.

        Only meaningful after the search has narrowed the list to a single
        owned record.
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    # ── delete dialog flow ───────────────────────────────────
    def click_row_delete(self) -> None:
        """Click the trash icon on the first (and only) result row.

        Callers MUST first assert the list is down to one row; clicking the
        multi-match icon otherwise deletes an unowned record.
        """
        self.click(self.sel("row_delete_icon_first"))
        self.wait_visible(self.sel("delete_dialog"))

    def confirm_delete(self) -> None:
        """Confirm deletion in the confirmation dialog ('Yes, Delete')."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Dismiss the confirmation dialog without deleting ('No, Cancel')."""
        self.click(self.sel("delete_cancel_button"))
        self.wait_hidden(self.sel("delete_dialog"))

    # ── toast ────────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it to appear."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently shown. Never waits, never raises.

        Use for asserting NO toast appeared (e.g. after cancelling delete).
        """
        return self.is_visible(self.sel("toast"))
