"""
LoginPage — the OrangeHRM login screen.

RESERVED reference file. Agent 2 copies this style when generating new page
objects, so it is the single worked example of the conventions:

  - SELECTORS COME FROM THE APP INVENTORY, never from a literal in this file.
    Declare INVENTORY_PAGE, then use self.sel("<element_key>"). The keys are
    the `elements` keys on that page in app_inventory/<app>.json.
  - methods are business verbs (login_as), not UI mechanics (type_then_click)
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class LoginPage(BasePage):
    """The login screen. Selectors: see `pages.login` in the app inventory."""

    INVENTORY_PAGE = "login"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the login screen.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture
                      from BASE_URL or config.yaml. The path comes from the
                      inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def login_as(self, username: str, password: str) -> None:
        """Fill both credentials and submit.

        Takes the values rather than a role name: resolving a role to real
        credentials is the `credentials` fixture's job, so this page object
        stays usable with any user, including deliberately invalid ones.
        """
        self.fill(self.sel("username_input"), username)
        self.fill(self.sel("password_input"), password)
        self.click(self.sel("login_button"))

    def clear_credentials(self) -> None:
        """Empty both fields without submitting."""
        self.clear(self.sel("username_input"))
        self.clear(self.sel("password_input"))

    # ── queries ──────────────────────────────────────────────
    def get_error_message(self) -> str:
        """Text of the credentials error banner ('Invalid credentials')."""
        self.wait_visible(self.sel("error_banner"))
        return self.get_text(self.sel("error_banner"))

    def get_field_error(self) -> str:
        """First per-field validation message ('Required').

        Uses field_error_first, not field_error. The generic selector matches
        every field error on the page, and Playwright runs in strict mode, so
        a visibility assertion against it raises a strict mode violation the
        moment two fields are empty - which is exactly what this method is
        used to check. field_error_first pins it to one element.
        """
        self.wait_visible(self.sel("field_error_first"))
        return self.get_text(self.sel("field_error_first"))

    def get_username_field_error(self) -> str:
        """Validation message under the Username field specifically."""
        self.wait_visible(self.sel("username_field_error"))
        return self.get_text(self.sel("username_field_error"))

    def get_password_field_error(self) -> str:
        """Validation message under the Password field specifically."""
        self.wait_visible(self.sel("password_field_error"))
        return self.get_text(self.sel("password_field_error"))

    def has_field_error(self) -> bool:
        """True if ANY per-field validation message is shown. Never raises.

        The non-waiting counterpart to get_field_error. Absence assertions
        must use this: a getter that waits for visibility cannot express
        "nothing is there" - it times out and raises instead.
        """
        # get_all_texts uses all_inner_texts(), which is strict-mode safe:
        # it returns a list over every match rather than asserting on one.
        return len(self.get_all_texts(self.sel("field_error"))) > 0

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.sel("field_error"))

    def is_error_displayed(self) -> bool:
        """True if the credentials error banner is on screen."""
        return self.is_visible(self.sel("error_banner"))

    def is_login_form_displayed(self) -> bool:
        """True if we are still on the login screen."""
        return self.is_visible(self.sel("username_input"))