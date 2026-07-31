"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Selectors: see `pages.admin_add_user` in the app inventory. No literal
selectors live here; every element is resolved via self.sel("<key>").

Custom ARIA dropdowns (User Role, Status) are NOT <select> elements — they
must be selected by visible text via BasePage.select_custom_option. The
Employee Name field is an autocomplete driven by
BasePage.select_autocomplete_suggestion, which types, waits past the
'Searching....' placeholder, and clicks a real suggestion.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role ARIA dropdown and pick the option by visible text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, query: str) -> str:
        """Type into the Employee Name autocomplete and select a real suggestion.

        Waits past the 'Searching....' placeholder and the 'No Records Found'
        empty state, then clicks the first genuine suggestion. Returns the
        text of the suggestion that was selected.
        """
        return self.select_autocomplete_suggestion(
            self.sel("employee_name_input"),
            self.sel("autocomplete_option"),
            query,
            placeholder="Searching",
            empty_text="No Records Found",
        )

    def select_status(self, status: str) -> None:
        """Open the Status ARIA dropdown and pick the option by visible text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_username(self, username: str) -> None:
        """Type the username into the Username field."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Type the value into the Password field."""
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Type the value into the Confirm Password field."""
        self.fill(self.sel("confirm_password_input"), password)

    def click_save(self) -> None:
        """Submit the Add User form."""
        self.click(self.sel("save_button"))

    def click_cancel(self) -> None:
        """Abandon the Add User form."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def get_selected_user_role(self) -> str:
        """Visible text currently shown on the User Role dropdown trigger."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text currently shown on the Status dropdown trigger."""
        return self.get_text(self.sel("status_select"))

    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name autocomplete input."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_username_value(self) -> str:
        """Current value of the Username field."""
        return self.get_input_value(self.sel("username_input"))

    def get_field_error(self) -> str:
        """First per-field validation message on the form.

        Uses field_error_first, not field_error: the generic key matches every
        error at once and a visibility wait on it is a Playwright strict-mode
        violation when several fields are invalid.
        """
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        Non-waiting counterpart to get_field_error, for absence assertions.
        """
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_toast_text(self) -> str:
        """Text of the success/error toast. WAITS for it — use to assert one appeared."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently visible. Never waits — use for absence checks."""
        return self.is_visible(self.sel("toast"))
