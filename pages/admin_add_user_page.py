"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Selectors: see `pages.admin_add_user` in the app inventory.

App: https://opensource-demo.orangehrmlive.com

Notes on the tricky controls (from the inventory):
  - User Role and Status are CUSTOM ARIA dropdowns, not <select>. They are
    selected by visible option text via BasePage.select_custom_option, which
    matches on accessible name and therefore waits for a real option (never
    the '-- Select --' placeholder).
  - Employee Name is an autocomplete. It is populated via
    select_autocomplete_suggestion, which types, waits for the 'Searching....'
    row to disappear, and clicks the first REAL suggestion.
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role custom dropdown and pick an option by its text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, query: str) -> str:
        """Type into the Employee Name autocomplete and select the first real suggestion.

        Returns the visible text of the suggestion that was chosen, so callers
        can confirm the field was populated with a genuine employee name.
        """
        return self.select_autocomplete_suggestion(
            self.sel("employee_name_input"),
            self.sel("autocomplete_option"),
            query,
            placeholder="Searching",
            empty_text="No Records Found",
        )

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and pick an option by its text."""
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

    # ── queries ──────────────────────────────────────────────
    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name field."""
        return self.get_input_value(self.sel("employee_name_input"))

    def get_selected_user_role(self) -> str:
        """Visible text currently shown in the User Role dropdown trigger."""
        return self.get_text(self.sel("user_role_select"))

    def get_selected_status(self) -> str:
        """Visible text currently shown in the Status dropdown trigger."""
        return self.get_text(self.sel("status_select"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        Absence assertions must use this rather than a waiting getter: the
        generic field_error selector matches every message on the form, so a
        visibility assertion against it is a strict-mode violation, and a
        waiting getter times out when nothing is there.
        """
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def get_field_error(self) -> str:
        """First per-field validation message. Waits for it to appear."""
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it — use to assert one APPEARED."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))
