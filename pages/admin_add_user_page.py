"""
AdminAddUserPage — the OrangeHRM Admin > User Management > Add User form.

Selectors: see `pages.admin_add_user` in the app inventory.

Key behaviours encoded here (learned from SCRUM-104):
  - User Role and Status are custom ARIA dropdowns, NOT <select>. Pick by TEXT
    with select_custom_option, never by clicking the multi-match option family.
  - Employee Name is an autocomplete populated asynchronously. Type enough
    characters, then pick a suggestion BY TEXT so the wait resolves to a real
    entry rather than the 'Searching....' placeholder.
  - A success toast is asserted with the WAITING reader (get_toast_text); its
    absence is checked with the non-waiting probe (has_toast).

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── queries: form presence ───────────────────────────────
    def is_loaded(self) -> bool:
        """True if the Add User form is displayed (Username field present)."""
        return self.is_showing(self.sel("username_input"))

    # ── actions: dropdowns ───────────────────────────────────
    def select_user_role(self, role: str) -> None:
        """Open the User Role custom dropdown and choose an option by text."""
        self.select_custom_option(self.sel("user_role_select"), role)

    def get_user_role_label(self) -> str:
        """Visible text currently shown in the User Role trigger."""
        return self.get_text(self.sel("user_role_select"))

    def select_status(self, status: str) -> None:
        """Open the Status custom dropdown and choose an option by text."""
        self.select_custom_option(self.sel("status_select"), status)

    def get_status_label(self) -> str:
        """Visible text currently shown in the Status trigger."""
        return self.get_text(self.sel("status_select"))

    # ── actions: employee autocomplete ───────────────────────
    def enter_employee_name(self, name: str) -> None:
        """Type into the Employee Name autocomplete and pick a suggestion.

        `name` must be enough characters to yield an unambiguous suggestion.
        The suggestion is selected BY TEXT via select_custom_option, which
        matches accessible name and therefore waits for a real entry rather
        than resolving to the 'Searching....' placeholder.
        """
        self.type_text(self.sel("employee_name_input"), name)
        self.select_custom_option(self.sel("employee_name_input"), name)

    def select_first_employee_suggestion(self, typed: str) -> str:
        """Type into the autocomplete, then click the first REAL suggestion.

        Filters out the 'Searching....' placeholder before choosing, so the
        pick is always a genuine employee. Returns the chosen suggestion text.
        """
        self.type_text(self.sel("employee_name_input"), typed)
        # Wait until at least one real (non-'Searching....') suggestion renders.
        self.wait_for_page_load("networkidle")
        options = [
            text
            for text in self.get_all_texts(self.sel("autocomplete_option"))
            if text and "Searching" not in text
        ]
        if not options:
            raise AssertionError(
                f"No employee suggestions rendered for typed value {typed!r}"
            )
        chosen = options[0]
        self.select_custom_option(self.sel("employee_name_input"), chosen)
        return chosen

    def get_employee_name_value(self) -> str:
        """Current value of the Employee Name input."""
        return self.get_input_value(self.sel("employee_name_input"))

    # ── actions: text fields ─────────────────────────────────
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

    # ── queries: validation ──────────────────────────────────
    def get_field_error(self) -> str:
        """First per-field validation message on the form (order-dependent)."""
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises."""
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_password_field_error(self) -> str:
        """Validation message under the Password field specifically."""
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def get_confirm_password_field_error(self) -> str:
        """Validation message under the Confirm Password field specifically."""
        self.wait_visible(self.sel("confirm_password_field_error"))
        return self.get_text(self.sel("confirm_password_field_error"))

    # ── queries: toast ───────────────────────────────────────
    def get_toast_text(self) -> str:
        """Text of the success/error toast. WAITS for it — use to assert one appeared."""
        self.wait_visible(self.sel("toast"))
        return self.get_text(self.sel("toast"))

    def has_toast(self) -> bool:
        """True if a toast is currently shown. Never waits — use for absence checks."""
        return self.is_visible(self.sel("toast"))
