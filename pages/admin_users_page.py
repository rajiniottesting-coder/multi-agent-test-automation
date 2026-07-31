"""
AdminUsersPage — the Admin > User Management > Users list screen.

Selectors come from `pages.admin_users` in the app inventory; this file never
holds a literal selector. See the inventory `elements_notes` for the many
timing and strict-mode caveats that shaped these methods:

  - search_by_username uses type_and_confirm, never fill/type_text, because
    the Vue model does not bind reliably otherwise.
  - record-count reads WAIT for the expected text; the summary re-renders
    asynchronously after Search, so an immediate read races the request.
  - the row delete icon is only clicked once the list is narrowed to one row
    (row_delete_icon_first), never the multi-match row_delete_icon.
  - toast presence uses a WAITING reader; toast ABSENCE uses a non-waiting
    probe, so a cancelled action can be proven to raise no toast.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list. Selectors: see `pages.admin_users` in the app inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation waits ─────────────────────────────────────
    def wait_for_list(self) -> None:
        """Wait until the Users list URL is active after a Save/redirect.

        The Add User form and this list share a byte-identical username input,
        so we must confirm the list is really the active page before searching.
        """
        self.wait_for_url("**/viewSystemUsers")
        self.wait_visible(self.sel("search_button"))

    # ── actions ──────────────────────────────────────────────
    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    def search_by_username(self, username: str) -> None:
        """Type the username into the filter (model-bound) and submit Search.

        Uses type_and_confirm because fill() sets the value visibly but never
        binds the Vue model, and plain type_text() can be wiped by a re-render
        between keystrokes and the Search click.
        """
        self.type_and_confirm(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))

    def click_row_delete(self) -> None:
        """Click the trash icon on the single (first) result row.

        Only safe once the search has narrowed the list to one row. Clicking
        the multi-match trash icon is a strict-mode violation and, on this
        shared demo, would delete a record the test does not own.
        """
        self.click(self.sel("row_delete_icon_first"))

    def confirm_delete(self) -> None:
        """Confirm deletion in the confirmation dialog ('Yes, Delete')."""
        self.wait_visible(self.sel("delete_dialog"))
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Decline deletion in the confirmation dialog ('No, Cancel')."""
        self.wait_visible(self.sel("delete_dialog"))
        self.click(self.sel("delete_cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def wait_for_record_summary(self, expected_fragment: str) -> None:
        """Wait until the results summary contains the expected fragment.

        The summary re-renders asynchronously after Search, so reading it
        immediately returns the PREVIOUS value. Callers pass a grammatically
        correct fragment such as '(1) Record' or 'No Records Found'.
        """
        self.wait_for_text(self.sel("records_found"), expected_fragment)

    def get_record_summary(self) -> str:
        """Current text of the results summary line."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_row_count(self) -> int:
        """Number of result rows currently rendered."""
        return self.get_count(self.sel("table_rows"))

    def get_row_username(self) -> str:
        """Username shown in the first result row's username cell.

        Only meaningful after the search has narrowed the list to one row.
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    def is_delete_dialog_displayed(self) -> bool:
        """True once the confirmation dialog is visible (waits for it)."""
        return self.is_showing(self.sel("delete_dialog"))

    def has_confirm_delete_button(self) -> bool:
        """True if the dialog's 'Yes, Delete' button is present."""
        return self.is_visible(self.sel("delete_confirm_button"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast. WAITS for it — use for presence."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently shown. Non-waiting — use for absence."""
        return self.is_visible(self.sel("toast"))
