"""
AdminAddUserPage — the OrangeHRM Admin > Add User form.

Page object for the Add User form at /web/index.php/admin/saveSystemUser.
Exposes role/status/employee/username/password entry and per-field error
queries used by the password-validation scenarios.

Conventions (see pages/login_page.py for the worked example):
  - Selectors come from the app inventory via self.sel("<key>"); never a literal.
  - Methods are business verbs; assertions live in step definitions.
  - Every method uses a BasePage helper; no raw self.page.* calls.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the custom User Role dropdown and pick an option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def select_status(self, status: str) -> None:
        """Open the custom Status dropdown and pick an option by text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and select the first suggestion.

        Typing a full name without picking a suggestion leaves the field invalid,
        so this waits for the option list and clicks the first match.
        """
        self.fill(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(self.sel("autocomplete_option"))

    def enter_username(self, username: str) -> None:
        """Fill the Username field."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Fill the Password field (validation renders as you type)."""
        self.fill(self.sel("password_input"), password)

    def clear_password(self) -> None:
        """Empty the Password field."""
        self.clear(self.sel("password_input"))

    def enter_confirm_password(self, password: str) -> None:
        """Fill the Confirm Password field (validation renders as you type)."""
        self.fill(self.sel("confirm_password_input"), password)

    def clear_confirm_password(self) -> None:
        """Empty the Confirm Password field."""
        self.clear(self.sel("confirm_password_input"))

    def blur(self) -> None:
        """Move focus off the current field so blur-triggered validation fires."""
        self.click(self.sel("save_button"))

    def blur_password(self) -> None:
        """Blur the Password field to trigger required-field validation.

        Clicking into Confirm Password moves focus off Password without
        submitting, which fires the 'Required' message beneath Password.
        """
        self.click(self.sel("confirm_password_input"))

    def blur_confirm_password(self) -> None:
        """Blur the Confirm Password field to trigger required-field validation.

        Clicking back into Password moves focus off Confirm Password without
        submitting, which fires the 'Required' message beneath Confirm Password.
        """
        self.click(self.sel("password_input"))

    def click_save(self) -> None:
        """Submit the form."""
        self.click(self.sel("save_button"))

    # ── queries ──────────────────────────────────────────────
    def get_selected_user_role(self) -> str:
        """Visible text of the currently selected User Role option."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text of the currently selected Status option."""
        return self.get_text(self.sel("status_select"))

    def get_username_value(self) -> str:
        """Current value of the Username input."""
        return self.get_input_value(self.sel("username_input"))

    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name autocomplete input."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_password_field_error(self) -> str:
        """Validation message beneath the Password field.

        The Password group selector is scoped and pinned with nth=0 because
        ':has-text' substring-matches the Confirm Password group too.
        """
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def get_confirm_password_field_error(self) -> str:
        """Validation message beneath the Confirm Password field."""
        self.wait_visible(self.sel("confirm_password_field_error"))
        return self.get_text(self.sel("confirm_password_field_error"))

    def has_password_field_error(self) -> bool:
        """True if a message is shown beneath the Password field. Never raises."""
        return self.get_count(self.sel("password_field_error")) > 0

    def has_confirm_password_field_error(self) -> bool:
        """True if a message is shown beneath the Confirm Password field. Never raises."""
        return self.get_count(self.sel("confirm_password_field_error")) > 0

    def is_on_add_user_form(self) -> bool:
        """True if still on the Add User form (Save button visible)."""
        return self.is_visible(self.sel("save_button"))
