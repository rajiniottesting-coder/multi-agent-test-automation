"""
AdminAddUserPage — the Admin > User Management > Add User form.

Selectors come from `pages.admin_add_user` in the app inventory; this file
never contains a raw selector literal. The two dropdowns (User Role, Status)
are custom ARIA dropdowns, and Employee Name is an autocomplete — all three are
async families, so selection is done BY TEXT via BasePage.select_custom_option,
never by clicking an index-pinned option key.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role custom dropdown and pick an option by its text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and select the matching suggestion by text."""
        self.type_text(self.sel("employee_name_input"), name)
        self.select_custom_option(self.sel("employee_name_input"), name)

    def enter_employee_name_first_suggestion(self, query: str) -> None:
        """Type a query, wait for real suggestions, then select the first one by its text.

        The autocomplete_option family includes a transient 'Searching....' row,
        so we read the rendered suggestion texts (strict-mode safe via
        get_all_texts), skip that placeholder, and pick the first genuine
        suggestion BY ITS TEXT via select_custom_option — never by index-pinning
        the async family, which would resolve to the loading row.
        """
        self.type_text(self.sel("employee_name_input"), query)
        first = self._first_real_suggestion()
        self.select_custom_option(self.sel("employee_name_input"), first)

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and pick an option by its text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_username(self, username: str) -> None:
        """Fill the Username field."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Fill the Password field."""
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Fill the Confirm Password field."""
        self.fill(self.sel("confirm_password_input"), password)

    def click_save(self) -> None:
        """Submit the Add User form."""
        self.click(self.sel("save_button"))

    # ── queries ──────────────────────────────────────────────
    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name autocomplete input."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_selected_user_role(self) -> str:
        """Visible text of the currently selected User Role."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text of the currently selected Status."""
        return self.get_text(self.sel("status_select"))

    def get_field_error(self) -> str:
        """First per-field validation message on the form (DOM order)."""
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently rendered."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it to appear."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently on screen. Never raises."""
        return self.is_visible(self.sel("toast"))

    def is_loaded(self) -> bool:
        """True if the Add User form is displayed (Username input present)."""
        return self.url_matches(self.page_url()) and self.is_showing(self.sel("username_input"))

    # ── internals ────────────────────────────────────────────
    def _first_real_suggestion(self) -> str:
        """Return the text of the first genuine autocomplete suggestion.

        Reads the rendered suggestion family with get_all_texts, which is
        strict-mode safe (it iterates every match instead of asserting on one)
        and never index-pins the async family. Skips the transient
        'Searching....' placeholder row so we return a real employee name that
        select_custom_option can match by accessible name.
        """
        for text in self.get_all_texts(self.sel("autocomplete_option")):
            if text and "Searching" not in text:
                return text
        raise AssertionError("No employee autocomplete suggestion appeared")
