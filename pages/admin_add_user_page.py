"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Fills the Add User form: pick a User Role and Status from custom ARIA
dropdowns, choose an employee via the autocomplete, set the username and
both password fields, then save.

SELECTORS COME FROM THE APP INVENTORY (page key `admin_add_user`), never
from a literal in this file: declare INVENTORY_PAGE, then use
self.sel("<element_key>").

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role custom dropdown and pick the option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and pick the first suggestion.

        Types the given text, waits for the first suggestion to render, and
        clicks it. The autocomplete_option family is multi-match, so we use the
        _first key pinned to nth=0 rather than waiting on the whole family.
        """
        self.type_text(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option_first"))
        self.click(self.sel("autocomplete_option_first"))

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and pick the option by text."""
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

    def click_cancel(self) -> None:
        """Abandon the Add User form."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def get_selected_user_role(self) -> str:
        """Visible text of the currently selected User Role."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text of the currently selected Status."""
        return self.get_text(self.sel("status_select"))

    def get_employee_name_value(self) -> str:
        """Current value typed into the Employee Name autocomplete field."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_field_error(self) -> str:
        """First per-field validation message on the form.

        Uses field_error_first, not field_error. The generic key matches every
        field error on the page and Playwright runs in strict mode, so a
        visibility assertion against it raises the moment more than one field
        is invalid.
        """
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        The non-waiting counterpart to get_field_error, for absence checks:
        a getter that waits cannot express 'nothing is there'.
        """
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def has_toast(self) -> bool:
        """True if a success/error toast is currently visible."""
        return self.is_visible(self.sel("toast"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
