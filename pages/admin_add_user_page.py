"""
AdminAddUserPage — the OrangeHRM Admin > Add User form.

New page object for the Add User form. Exposes field entry, per-field
validation getters, and save, using inventory-driven selectors.

Selectors: see `pages.admin_add_user` in the app inventory.

App: https://opensource-demo.orangehrmlive.com

Notes on this form (from the inventory):
  - User Role and Status are CUSTOM ARIA dropdowns, not <select> — open then
    click an `.oxd-select-option`. Use select_custom_option().
  - Employee Name is an autocomplete — type ≥2 chars, wait for the option,
    then click it.
  - Password / Confirm Password are bare input[type='password'] in DOM order
    (nth=0 / nth=1).
  - Validation messages render AS YOU TYPE (on blur/change), NOT on Save, and
    the generic field_error matches EVERY error on the page, so per-field
    getters use the scoped password_field_error / confirm_password_field_error.
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the custom User Role dropdown and choose an option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def select_status(self, status: str) -> None:
        """Open the custom Status dropdown and choose an option by text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and pick the first hint."""
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

    def focus_password(self) -> None:
        """Click into the Password field (to focus it before blurring)."""
        self.click(self.sel("password_input"))

    def focus_confirm_password(self) -> None:
        """Click into the Confirm Password field (to focus before blurring)."""
        self.click(self.sel("confirm_password_input"))

    def blur_password(self) -> None:
        """Leave the Password field, triggering its validation."""
        self.press_key(self.sel("password_input"), "Tab")

    def blur_confirm_password(self) -> None:
        """Leave the Confirm Password field, triggering its validation."""
        self.press_key(self.sel("confirm_password_input"), "Tab")

    def clear_password(self) -> None:
        """Empty the Password field."""
        self.clear(self.sel("password_input"))

    def clear_confirm_password(self) -> None:
        """Empty the Confirm Password field."""
        self.clear(self.sel("confirm_password_input"))

    def click_save(self) -> None:
        """Submit the form via the Save button."""
        self.click(self.sel("save_button"))

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

    def get_password_field_error(self) -> str:
        """Validation message beneath the Password field specifically."""
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def get_confirm_password_field_error(self) -> str:
        """Validation message beneath the Confirm Password field."""
        self.wait_visible(self.sel("confirm_password_field_error"))
        return self.get_text(self.sel("confirm_password_field_error"))

    def has_password_field_error(self) -> bool:
        """True if a Password validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("password_field_error"))) > 0

    def has_confirm_password_field_error(self) -> bool:
        """True if a Confirm Password validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("confirm_password_field_error"))) > 0

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently on the form."""
        return self.get_all_texts(self.sel("field_error"))

    def is_on_add_user_form(self) -> bool:
        """True if we are still on the Add User form (Save button present)."""
        return self.is_visible(self.sel("save_button")) and self.page_url() in self.get_path()
