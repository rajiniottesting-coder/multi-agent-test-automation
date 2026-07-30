"""
AdminAddUserPage — the OrangeHRM Add User form.

Page object for the Admin > User Management > Add User screen.
Provides methods to fill password fields, tab away to trigger inline
validation, and read validation error messages.

Selectors: see `pages.admin_add_user` in the app inventory.
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `admin_add_user` in the app inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── navigation ───────────────────────────────────────────

    def open(self, base_url: str) -> None:
        """Navigate directly to the Add User form.

        Args:
            base_url: application base URL from the `base_url` fixture.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def is_loaded(self) -> bool:
        """True if the Add User form is displayed."""
        return self.is_visible(self.sel("password_input"))

    # ── password actions ─────────────────────────────────────

    def enter_password(self, password: str) -> None:
        """Fill the Password field.

        Args:
            password: the password string to type.
        """
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Fill the Confirm Password field.

        Args:
            password: the confirmation password string to type.
        """
        self.fill(self.sel("confirm_password_input"), password)

    def clear_password(self) -> None:
        """Clear the Password field."""
        self.clear(self.sel("password_input"))

    def clear_confirm_password(self) -> None:
        """Clear the Confirm Password field."""
        self.clear(self.sel("confirm_password_input"))

    def focus_password(self) -> None:
        """Click into the Password field to give it focus."""
        self.click(self.sel("password_input"))

    def focus_confirm_password(self) -> None:
        """Click into the Confirm Password field to give it focus."""
        self.click(self.sel("confirm_password_input"))

    def tab_away_from_password(self) -> None:
        """Press Tab on the Password field to move focus away and trigger validation."""
        self.press_key(self.sel("password_input"), "Tab")

    def tab_away_from_confirm_password(self) -> None:
        """Press Tab on the Confirm Password field to move focus away and trigger validation."""
        self.press_key(self.sel("confirm_password_input"), "Tab")

    # ── other form actions ───────────────────────────────────

    def select_user_role(self, role: str) -> None:
        """Select a User Role from the custom dropdown.

        Args:
            role: visible text of the role option, e.g. 'Admin' or 'ESS'.
        """
        self.click(self.sel("user_role_select"))
        self.wait_visible(self.sel("dropdown_option"))
        self.click(f"{self.sel('dropdown_option')}:has-text('{role}')")

    def select_status(self, status: str) -> None:
        """Select a Status from the custom dropdown.

        Args:
            status: visible text of the status option, e.g. 'Enabled'.
        """
        self.click(self.sel("status_select"))
        self.wait_visible(self.sel("dropdown_option"))
        self.click(f"{self.sel('dropdown_option')}:has-text('{status}')")

    def enter_employee_name(self, name: str) -> None:
        """Type an employee name into the autocomplete field and select the first suggestion.

        Args:
            name: partial or full employee name to search for.
        """
        self.fill(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(self.sel("autocomplete_option"))

    def enter_username(self, username: str) -> None:
        """Fill the Username field.

        Args:
            username: the username string.
        """
        self.fill(self.sel("username_input"), username)

    def click_save(self) -> None:
        """Click the Save button to submit the form."""
        self.click(self.sel("save_button"))

    def click_cancel(self) -> None:
        """Click the Cancel button to discard changes."""
        self.click(self.sel("cancel_button"))

    # ── queries ──────────────────────────────────────────────

    def get_field_error(self) -> str:
        """Text of the first inline validation error message currently shown."""
        self.wait_visible(self.sel("field_error"))
        return self.get_text(self.sel("field_error"))

    def get_all_field_errors(self) -> list[str]:
        """All inline validation error messages currently shown, in DOM order."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if any inline validation error message is currently visible."""
        return self.is_visible(self.sel("field_error"))

    def get_password_field_error(self) -> str:
        """Text of the validation error beneath the Password field.

        The Password field is the first password input (nth=0). Its error
        message is the first `.oxd-input-field-error-message` that appears
        within the same input group. We read the first field error visible
        on the page, which corresponds to the Password field when only
        that field has an error.
        """
        self.wait_visible(self.sel("field_error"))
        return self.get_nth_text(self.sel("field_error"), 0)

    def get_confirm_password_field_error(self) -> str:
        """Text of the validation error beneath the Confirm Password field.

        When both password fields have errors, the confirm password error
        is the second field error. When only the confirm password field
        has an error (password field is valid), it is the first.
        This method reads the last field error visible, which in the
        password-only validation context is the confirm password error.
        """
        self.wait_visible(self.sel("field_error"))
        errors = self.get_all_texts(self.sel("field_error"))
        return errors[-1] if errors else ""

    def get_field_error_count(self) -> int:
        """Number of inline validation error messages currently displayed."""
        return self.get_count(self.sel("field_error"))

    def wait_for_field_error(self, expected_text: str, timeout_ms: int | None = None) -> None:
        """Wait until a field error containing the expected text appears.

        Args:
            expected_text: the validation message text to wait for.
            timeout_ms: optional timeout override in milliseconds.
        """
        self.wait_for_text(self.sel("field_error"), expected_text, timeout_ms=timeout_ms)

    def wait_for_no_field_error(self, timeout_ms: int | None = None) -> None:
        """Wait until all inline field error messages disappear.

        Args:
            timeout_ms: optional timeout override in milliseconds.
        """
        self.wait_hidden(self.sel("field_error"), timeout_ms=timeout_ms)
