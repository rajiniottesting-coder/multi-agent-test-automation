"""
AdminAddUserPage — the OrangeHRM Admin > Add User form.

Focuses on password / confirm-password entry and the inline, per-field
validation OrangeHRM renders AS YOU TYPE (not on Save). Selectors come from
the `admin_add_user` inventory page; this file never contains a literal
selector.

Key behaviours the validation tests rely on:
  - error messages appear after a field is touched and left invalid, so a test
    asserts after filling/blurring a field, not after submitting the form.
  - Password and Confirm Password are positional `input[type='password']`
    fields (nth=0 / nth=1) with no name or id.
  - blurring a field (clicking outside / tabbing away) is what triggers the
    'Required' validation, so entry helpers blur after typing.

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class AdminAddUserPage(BasePage):
    """The Add User form. Selectors: see `pages.admin_add_user` in the inventory."""

    INVENTORY_PAGE = "admin_add_user"

    # ── actions ──────────────────────────────────────────────
    def enter_password(self, password: str) -> None:
        """Type into the Password field and blur it to trigger validation.

        Blurring (Tab) is what makes the 'Required' / policy messages render,
        so it is part of entering the value rather than a separate step.
        """
        locator = self.sel("password_input")
        self.fill(locator, password)
        self.press_key(locator, "Tab")

    def enter_confirm_password(self, password: str) -> None:
        """Type into the Confirm Password field and blur it to trigger validation."""
        locator = self.sel("confirm_password_input")
        self.fill(locator, password)
        self.press_key(locator, "Tab")

    def clear_password(self) -> None:
        """Empty the Password field without typing anything new."""
        self.clear(self.sel("password_input"))

    def touch_password(self) -> None:
        """Focus the Password field then blur it without typing.

        Used to trigger the 'Required' validation on an empty field.
        """
        locator = self.sel("password_input")
        self.click(locator)
        self.press_key(locator, "Tab")

    def touch_confirm_password(self) -> None:
        """Focus the Confirm Password field then blur it without typing.

        Used to trigger the 'Required' validation on an empty field.
        """
        locator = self.sel("confirm_password_input")
        self.click(locator)
        self.press_key(locator, "Tab")

    # ── queries ──────────────────────────────────────────────
    def get_password_field_error(self) -> str:
        """Validation message shown beneath the Password field specifically."""
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def get_confirm_password_field_error(self) -> str:
        """Validation message shown beneath the Confirm Password field specifically."""
        self.wait_visible(self.sel("confirm_password_field_error"))
        return self.get_text(self.sel("confirm_password_field_error"))

    def has_password_field_error(self) -> bool:
        """True if any validation message is shown under the Password field.

        Non-waiting counterpart to get_password_field_error, for absence
        assertions — a waiting getter cannot express 'nothing is there'.
        """
        return self.is_visible(self.sel("password_field_error"))

    def has_confirm_password_field_error(self) -> bool:
        """True if any validation message is shown under the Confirm Password field.

        Non-waiting counterpart to get_confirm_password_field_error.
        """
        return self.is_visible(self.sel("confirm_password_field_error"))
