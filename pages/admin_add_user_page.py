"""
AdminAddUserPage — the OrangeHRM Admin > Add User form.

Selectors: see `pages.admin_add_user` in the app inventory. All field access
goes through inventory keys via self.sel(); no literal selectors live here.

Key behaviours this page object encapsulates:
  - User Role and Status are custom ARIA dropdowns (click to open, click an
    option), NOT native <select>.
  - Employee Name is an autocomplete: type, wait for suggestions, click one.
  - Password / Confirm Password validation messages render AS YOU TYPE, so the
    per-field error getters wait for the scoped error element after filling.
  - Password and Confirm Password error groups are scoped by label; a
    non-waiting predicate is provided for each so absence can be asserted.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── field actions ────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the custom User Role dropdown and pick an option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def select_status(self, status: str) -> None:
        """Open the custom Status dropdown and pick an option by text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and pick the first hint."""
        self.type_text(self.sel("employee_name_input"), name)
        self.wait_visible(self.sel("autocomplete_option"))
        self.click(self.sel("autocomplete_option"))

    def enter_username(self, username: str) -> None:
        """Set the Username field value."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Set the Password field value (validation fires as this is typed)."""
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Set the Confirm Password field value."""
        self.fill(self.sel("confirm_password_input"), password)

    def clear_password(self) -> None:
        """Empty the Password field."""
        self.clear(self.sel("password_input"))

    def clear_confirm_password(self) -> None:
        """Empty the Confirm Password field."""
        self.clear(self.sel("confirm_password_input"))

    def focus_password(self) -> None:
        """Place focus into the Password field without typing."""
        self.click(self.sel("password_input"))

    def focus_confirm_password(self) -> None:
        """Place focus into the Confirm Password field without typing."""
        self.click(self.sel("confirm_password_input"))

    def blur_active_field(self) -> None:
        """Blur the currently focused field by pressing Tab from it.

        Used to trigger 'Required' validation without submitting the form.
        """
        self.press_key(self.sel("username_input"), "Tab")

    def click_save(self) -> None:
        """Submit the form via the Save button."""
        self.click(self.sel("save_button"))

    # ── queries ──────────────────────────────────────────────
    def get_password_field_error(self) -> str:
        """Validation message scoped to the Password field. Waits for it."""
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def get_confirm_password_field_error(self) -> str:
        """Validation message scoped to the Confirm Password field. Waits."""
        self.wait_visible(self.sel("confirm_password_field_error"))
        return self.get_text(self.sel("confirm_password_field_error"))

    def has_password_field_error(self) -> bool:
        """True if a Password field validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("password_field_error"))) > 0

    def has_confirm_password_field_error(self) -> bool:
        """True if a Confirm Password validation message is shown. No wait."""
        return len(self.get_all_texts(self.sel("confirm_password_field_error"))) > 0

    def is_on_add_user_form(self) -> bool:
        """True if the Add User form is still displayed (Save not accepted)."""
        return self.is_visible(self.sel("save_button"))
