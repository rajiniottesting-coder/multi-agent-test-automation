"""
AdminAddUserPage — the OrangeHRM Add User form.

Page object for the Admin > User Management > Add User screen.
Provides methods to fill password fields, tab away to trigger inline
validation, and read field-level validation errors.

Selectors: see `pages.admin_add_user` in the app inventory.
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `admin_add_user` in the app inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────

    def open(self, base_url: str) -> None:
        """Navigate directly to the Add User form.

        Args:
            base_url: application base URL from the `base_url` fixture.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def enter_password(self, password: str) -> None:
        """Fill the Password field.

        Args:
            password: value to type into the Password input.
        """
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Fill the Confirm Password field.

        Args:
            password: value to type into the Confirm Password input.
        """
        self.fill(self.sel("confirm_password_input"), password)

    def clear_password(self) -> None:
        """Clear the Password field."""
        self.clear(self.sel("password_input"))

    def clear_confirm_password(self) -> None:
        """Clear the Confirm Password field."""
        self.clear(self.sel("confirm_password_input"))

    def tab_away_from_password(self) -> None:
        """Press Tab on the Password field to trigger blur validation."""
        self.press_key(self.sel("password_input"), "Tab")

    def tab_away_from_confirm_password(self) -> None:
        """Press Tab on the Confirm Password field to trigger blur validation."""
        self.press_key(self.sel("confirm_password_input"), "Tab")

    def click_password_field(self) -> None:
        """Click into the Password field (focus it)."""
        self.click(self.sel("password_input"))

    def click_confirm_password_field(self) -> None:
        """Click into the Confirm Password field (focus it)."""
        self.click(self.sel("confirm_password_input"))

    def click_save(self) -> None:
        """Click the Save button."""
        self.click(self.sel("save_button"))

    def select_user_role(self, role: str) -> None:
        """Select a User Role from the custom dropdown.

        Args:
            role: visible text of the role option, e.g. 'Admin' or 'ESS'.
        """
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, name: str) -> None:
        """Type an employee name into the autocomplete field and select the first suggestion.

        Args:
            name: partial or full employee name to search for.
        """
        self.fill(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(self.sel("autocomplete_option"))

    def select_status(self, status: str) -> None:
        """Select a Status from the custom dropdown.

        Args:
            status: visible text of the status option, e.g. 'Enabled' or 'Disabled'.
        """
        self.select_custom_option(self.sel("status_select"), status)

    def enter_username(self, username: str) -> None:
        """Fill the Username field.

        Args:
            username: value to type into the Username input.
        """
        self.fill(self.sel("username_input"), username)

    # ── queries ──────────────────────────────────────────────

    def get_password_field_error(self) -> str:
        """Text of the validation message beneath the Password field.

        Waits for the message to become visible before reading.
        """
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def get_confirm_password_field_error(self) -> str:
        """Text of the validation message beneath the Confirm Password field.

        Waits for the message to become visible before reading.
        """
        self.wait_visible(self.sel("confirm_password_field_error"))
        return self.get_text(self.sel("confirm_password_field_error"))

    def has_password_field_error(self) -> bool:
        """True if a validation message is currently shown under the Password field.

        Non-waiting check — safe for absence assertions.
        """
        return self.is_visible(self.sel("password_field_error"))

    def has_confirm_password_field_error(self) -> bool:
        """True if a validation message is currently shown under the Confirm Password field.

        Non-waiting check — safe for absence assertions.
        """
        return self.is_visible(self.sel("confirm_password_field_error"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown on the form."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def is_form_displayed(self) -> bool:
        """True if the Add User form is currently displayed."""
        return self.is_visible(self.sel("password_input"))
