"""
AdminAddUserPage — the OrangeHRM Add User form (saveSystemUser).

Selectors: see `pages.admin_add_user` in the app inventory. Every selector is
resolved through self.sel("<key>"); no literal selector strings live here.

Key behaviours encoded from the inventory notes:
  - User Role / Status are custom ARIA dropdowns → select_custom_option().
  - Employee Name is an autocomplete → select_autocomplete_suggestion(), which
    types, waits for the 'Searching....' placeholder to clear and clicks a real
    suggestion (never the async placeholder).
  - dropdown_option / autocomplete_option are MULTI-MATCH + ASYNC families:
    only read/count them, never click / wait / index-pin them.
  - A missing success toast usually means the form was rejected client-side, so
    field-error assertions come before toast assertions in the step layer.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role custom dropdown and pick an option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and pick an option by text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_employee_name(self, query: str) -> str:
        """Type into the Employee Name autocomplete and select a real suggestion.

        Returns the accessible text of the suggestion that was chosen so callers
        can assert the field was populated with a genuine employee.
        """
        return self.select_autocomplete_suggestion(
            self.sel("employee_name_input"),
            self.sel("autocomplete_option"),
            query,
            placeholder="Searching",
            empty_text="No Records Found",
        )

    def enter_username(self, username: str) -> None:
        """Enter the login username for the new system user."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Enter the password for the new system user."""
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Enter the confirm-password value for the new system user."""
        self.fill(self.sel("confirm_password_input"), password)

    def click_save(self) -> None:
        """Submit the Add User form."""
        self.click(self.sel("save_button"))

    def click_cancel(self) -> None:
        """Abandon the Add User form without saving."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the Add User form's Username field is visible."""
        return self.is_showing(self.sel("username_input"))

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
        """Text of the first per-field validation message on the form.

        Uses field_error_first, not field_error: the generic key matches every
        error at once and a visibility assertion on it is a strict-mode
        violation when several fields are invalid.
        """
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown, in DOM order."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        Non-waiting counterpart to get_field_error, for absence assertions.
        """
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_toast_text(self) -> str:
        """Text of the success/error toast. WAITS — use to assert one appeared."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently visible. Never waits — for absence checks."""
        return self.is_visible(self.sel("toast"))
