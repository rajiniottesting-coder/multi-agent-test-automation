"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Selectors come from `pages.admin_add_user` in the app inventory; this file
never contains a literal selector string. Methods are business verbs; every
one uses a BasePage helper. No assertions here — those live in step defs.

The User Role and Status controls are custom ARIA dropdowns (not <select>),
so they are opened and their `.oxd-select-option` items clicked. The Employee
Name field is an autocomplete: type a couple of characters, wait for the
`.oxd-autocomplete-option` list, then click a suggestion.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role dropdown and pick an option by its visible text."""
        self.click(self.sel("user_role_select"))
        self.wait_visible(self.sel("dropdown_option"))
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee autocomplete and select the first suggestion.

        Types the given text, waits for the suggestion list to appear, then
        clicks the first `.oxd-autocomplete-option`. Selecting a suggestion is
        required — a raw typed name leaves the field invalid.
        """
        self.type_text(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(self.sel("autocomplete_option"))

    def select_status(self, status: str) -> None:
        """Open the Status dropdown and pick an option by its visible text."""
        self.click(self.sel("status_select"))
        self.wait_visible(self.sel("dropdown_option"))
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
        """Abandon the Add User form without saving."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────
    def get_selected_user_role(self) -> str:
        """Visible text currently shown in the User Role dropdown."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text currently shown in the Status dropdown."""
        return self.get_text(self.sel("status_select"))

    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name autocomplete input."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_username_value(self) -> str:
        """Current value of the Username input."""
        return self.get_input_value(self.sel("username_input"))

    def get_field_error(self) -> str:
        """First per-field validation message on the form.

        The generic field_error selector matches every field error, and
        Playwright runs in strict mode, so scope to the first match.
        """
        self.wait_visible(self.sel("field_error"))
        return self.get_nth_text(self.sel("field_error"), 0)

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        Non-waiting counterpart to get_field_error — for absence assertions,
        e.g. 'no validation message under the field'.
        """
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def is_loaded(self) -> bool:
        """True if the Add User form is displayed (Username field present)."""
        return self.is_visible(self.sel("username_input"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast (e.g. 'Successfully Saved')."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
