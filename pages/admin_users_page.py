"""
AdminUsersPage — the OrangeHRM Admin > User Management > Users list
(viewSystemUsers).

Selectors: see `pages.admin_users` in the app inventory. This page object
never contains a literal selector — every element is resolved through
self.sel("<key>").

Covers: navigating from the list to Add User, searching by username,
reading the async results-summary text and record count, reading the single
row's username, and opening / confirming / cancelling the delete dialog, plus
reading the success toast.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminUsersPage(BasePage):
    """The Users list screen. Selectors: `pages.admin_users` in the inventory."""

    INVENTORY_PAGE = "admin_users"

    # ── navigation ───────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the Users list."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def wait_until_loaded(self) -> None:
        """Wait for the list to render after navigation or after Save.

        After Save the app spends a moment still rendering the Add User form
        before it lands here, so waiting on the URL avoids interacting with
        the wrong page.
        """
        self.wait_for_url("**/viewSystemUsers")
        self.wait_visible(self.sel("search_button"))

    def click_add(self) -> None:
        """Open the Add User form."""
        self.click(self.sel("add_button"))

    # ── search ───────────────────────────────────────────────
    def search_by_username(self, username: str) -> None:
        """Type the full username into the filter and click Search.

        Uses type_and_confirm(), not fill() and not plain type_text():
        fill() sets the value visibly but never binds the Vue model, so
        Search re-requests the UNFILTERED list; type_text() can be wiped by a
        re-render between keystrokes and the Search click. type_and_confirm()
        reads the value back and escalates until it sticks.
        """
        self.wait_visible(self.sel("search_username_input"))
        self.type_and_confirm(self.sel("search_username_input"), username)
        self.click(self.sel("search_button"))

    def wait_for_records_summary(self, expected_fragment: str) -> None:
        """Wait until the results-summary text contains the given fragment.

        The summary re-renders asynchronously after Search, so reading it
        immediately races the request and returns the previous value. Callers
        pass a fragment that is safe for the grammatically-variable text,
        e.g. '(1) Record' (a prefix of the singular '(1) Record Found') or
        'No Records Found'.
        """
        self.wait_for_text(self.sel("records_found"), expected_fragment)

    def get_records_summary(self) -> str:
        """Current text of the results summary, e.g. '(1) Record Found'."""
        self.wait_visible(self.sel("records_found"))
        return self.get_text(self.sel("records_found"))

    def get_record_count(self) -> int:
        """Number of result rows currently rendered in the table."""
        return self.get_count(self.sel("table_rows"))

    def has_no_records(self) -> bool:
        """True if the summary shows the 'No Records Found' empty state.

        Reads the summary text (which the app always renders, even for zero
        results) rather than counting rows, so it does not wait for rows that
        will never appear.
        """
        return "No Records Found" in self.get_records_summary()

    # ── row reads ────────────────────────────────────────────
    def get_row_username(self) -> str:
        """Username cell of the first (and, when narrowed to one, only) row.

        Only meaningful once the search has narrowed the list to a single
        owned record — the underlying selector is positional (nth=0).
        """
        self.wait_visible(self.sel("row_username_cell"))
        return self.get_text(self.sel("row_username_cell"))

    # ── delete flow ──────────────────────────────────────────
    def click_row_delete(self) -> None:
        """Click the trash icon on the single result row.

        Guards with a count check first: clicking the multi-match trash icon
        while more than one row is present is a strict-mode violation, and on
        this shared demo it would delete a record the test does not own.
        """
        assert self.get_count(self.sel("table_rows")) == 1, (
            "Refusing to delete: expected exactly one result row, "
            f"found {self.get_count(self.sel('table_rows'))}"
        )
        self.click(self.sel("row_delete_icon_first"))
        self.wait_visible(self.sel("delete_dialog"))

    def is_delete_dialog_open(self) -> bool:
        """True if the delete confirmation dialog is currently displayed."""
        return self.is_visible(self.sel("delete_dialog"))

    def get_confirm_button_text(self) -> str:
        """Visible text of the confirm ('Yes, Delete') button in the dialog."""
        self.wait_visible(self.sel("delete_confirm_button"))
        return self.get_text(self.sel("delete_confirm_button"))

    def confirm_delete(self) -> None:
        """Click 'Yes, Delete' in the confirmation dialog."""
        self.click(self.sel("delete_confirm_button"))

    def cancel_delete(self) -> None:
        """Click 'No, Cancel' in the confirmation dialog."""
        self.click(self.sel("delete_cancel_button"))
        self.wait_hidden(self.sel("delete_dialog"))

    # ── toast ────────────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it to appear."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently visible. Never waits, never raises.

        The non-waiting counterpart to get_toast_text — use it to assert that
        NO toast appeared (e.g. after cancelling the delete dialog).
        """
        return self.is_visible(self.sel("toast"))
