"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Fills the Add User form: pick a User Role and Status from custom ARIA
dropdowns, choose an employee via the autocomplete, enter credentials and
save. Selectors come from the `admin_add_user` inventory page — never a
literal here.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the app inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role custom dropdown and pick an option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and pick an option by text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and select the first suggestion.

        Types the given text, waits for suggestions to render, then clicks the
        first one. Typing without selecting a suggestion leaves the field
        invalid, so selection is part of this action.
        """
        self.type_text(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(self.sel("autocomplete_option"))

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

    def click_cancel(self) -> None:
        """Cancel the Add User form without saving."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def get_selected_user_role(self) -> str:
        """Visible text of the currently selected User Role."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text of the currently selected Status."""
        return self.get_text(self.sel("status_select"))

    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name autocomplete input."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_field_error(self) -> str:
        """First per-field validation message on the form.

        The generic field_error selector matches every field error on the
        page; this narrows to one to stay strict-mode safe.
        """
        self.wait_visible(self.sel("field_error"))
        return self.get_text(self.sel("field_error"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_toast_text(self) -> str:
        """Text of the success/error toast (e.g. 'Successfully Saved')."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def is_displayed(self) -> bool:
        """True if the Add User form is on screen."""
        return self.is_visible(self.sel("username_input"))
