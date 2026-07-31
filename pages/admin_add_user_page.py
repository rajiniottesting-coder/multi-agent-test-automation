"""
AdminAddUserPage — the OrangeHRM Add System User form (saveSystemUser).

Selectors: see `pages.admin_add_user` in the app inventory. This class NEVER
holds a literal selector — every element is resolved via self.sel("<key>").

Notes on the custom controls, all handled through BasePage helpers:
  - User Role / Status are custom ARIA dropdowns (NOT <select>): opened and
    picked with select_custom_option, which matches by accessible name and so
    never resolves to the '-- Select --' placeholder.
  - Employee Name is an autocomplete: driven with select_autocomplete_suggestion,
    which types, waits out the 'Searching....' row, and clicks a real suggestion.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add System User form. Selectors: see `pages.admin_add_user`."""

    INVENTORY_PAGE = "admin_add_user"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the form's Username field is on screen."""
        return self.is_showing(self.sel("username_input"))

    # ── actions ──────────────────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role dropdown and pick an option by its visible text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def enter_employee_name(self, query: str) -> str:
        """Type into the Employee Name autocomplete and pick a real suggestion.

        Returns the visible text of the suggestion that was selected. Uses the
        BasePage helper so the transient 'Searching....' row is waited out
        rather than accidentally clicked.
        """
        return self.select_autocomplete_suggestion(
            self.sel("employee_name_input"),
            self.sel("autocomplete_option"),
            query,
            placeholder="Searching",
            empty_text="No Records Found",
        )

    def select_status(self, status: str) -> None:
        """Open the Status dropdown and pick an option by its visible text."""
        self.select_custom_option(self.sel("status_select"), status)

    def enter_username(self, username: str) -> None:
        """Type into the Username field."""
        self.fill(self.sel("username_input"), username)

    def enter_password(self, password: str) -> None:
        """Type into the Password field."""
        self.fill(self.sel("password_input"), password)

    def enter_confirm_password(self, password: str) -> None:
        """Type into the Confirm Password field."""
        self.fill(self.sel("confirm_password_input"), password)

    def click_save(self) -> None:
        """Submit the form."""
        self.click(self.sel("save_button"))

    # ── validation queries ───────────────────────────────────
    def get_field_error(self) -> str:
        """First per-field validation message on the form.

        Uses field_error_first, not the generic field_error: this form has five
        required fields, so the generic key can match several messages at once
        and a visibility assertion on it raises a strict-mode violation.
        """
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently rendered."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        Non-waiting counterpart to get_field_error, for absence assertions.
        """
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_username_field_value(self) -> str:
        """Current value of the Username field."""
        return self.get_input_value(self.sel("username_input"))

    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name autocomplete field."""
        return self.get_input_value(self.sel("employee_name_input"))

    # ── toast queries ────────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast. Waits for it to appear (raises on absence)."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently visible. Never raises — use for absence checks."""
        return self.is_visible(self.sel("toast"))
