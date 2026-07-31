"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Selectors: see `pages.admin_add_user` in the app inventory. This page object
covers selecting the User Role and Status (custom ARIA dropdowns), the
Employee Name autocomplete, the Username and both password fields, and Save.

App: https://opensource-demo.orangehrmlive.com

NOTE ON SHARED DATA: this is a PUBLIC shared demo. Any user this page saves
persists, so callers must use a run-unique username and clean up afterwards.
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the custom User Role dropdown and pick an option by text."""
        self.click(self.sel("user_role_select"))
        self.wait_visible(self.sel("dropdown_option"))
        self.click_role("option", role)

    def select_status(self, status: str) -> None:
        """Open the custom Status dropdown and pick an option by text."""
        self.click(self.sel("status_select"))
        self.wait_visible(self.sel("dropdown_option"))
        self.click_role("option", status)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and pick the first hint.

        Typing a full name without selecting a suggestion leaves the field
        invalid, so this always clicks the first rendered suggestion.
        """
        self.type_text(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(f"{self.sel('autocomplete_option')} >> nth=0")

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
        """Abandon the Add User form without saving."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True if the Add User form is displayed (Username field present)."""
        return self.is_visible(self.sel("username_input"))

    def get_selected_user_role(self) -> str:
        """Visible text of the currently selected User Role."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text of the currently selected Status."""
        return self.get_text(self.sel("status_select"))

    def get_employee_name(self) -> str:
        """Current value of the Employee Name autocomplete field."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_field_error(self) -> str:
        """First per-field validation message on the form.

        The generic field_error selector matches every field error on the
        page and Playwright runs in strict mode, so this narrows to the
        first match to stay safe with a visibility wait.
        """
        self.wait_visible(f"{self.sel('field_error')} >> nth=0")
        return self.get_nth_text(self.sel("field_error"), 0)

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
