"""
AdminAddUserPage — the OrangeHRM Admin > Add User form.

Selectors: see `pages.admin_add_user` in the app inventory. Every selector is
resolved through self.sel("<key>") — no literal selector strings live here.

Notes on the tricky controls:
  - User Role and Status are custom ARIA dropdowns, NOT <select>. They are
    opened and chosen via BasePage.select_custom_option, matching on option
    text so we never land on the '-- Select --' placeholder.
  - Employee Name is an autocomplete. select_autocomplete_suggestion types the
    query, waits for the 'Searching....' row to disappear and clicks the first
    REAL suggestion, returning its text.

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

    def enter_employee_name(self, prefix: str) -> str:
        """Type into the Employee Name autocomplete and select the first real suggestion.

        Uses the BasePage helper that waits out the 'Searching....' placeholder
        so we never select a transient loading row. Returns the chosen name.
        """
        return self.select_autocomplete_suggestion(
            self.sel("employee_name_input"),
            self.sel("autocomplete_option"),
            prefix,
            placeholder="Searching",
            empty_text="No Records Found",
        )

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and pick an option by its text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_username(self, username: str) -> None:
        """Type the login username into the Username field."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Type the password into the Password field."""
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Type the password into the Confirm Password field."""
        self.fill(self.sel("confirm_password_input"), password)

    def click_save(self) -> None:
        """Submit the Add User form."""
        self.click(self.sel("save_button"))

    # ── queries ──────────────────────────────────────────────
    def get_field_error(self) -> str:
        """First per-field validation message on the form (order-dependent).

        Uses field_error_first, not field_error: the generic key matches every
        error at once and a visibility assertion on it is a strict-mode
        violation when several fields are invalid.
        """
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("field_error"))) > 0
