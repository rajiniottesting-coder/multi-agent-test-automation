"""
LoginPage — the OrangeHRM login screen.

RESERVED reference file. Agent 2 copies this style when generating new page
objects, so it is the single worked example of the conventions:

  - selectors are CLASS CONSTANTS, never inline in a method
  - methods are business verbs (login_as), not UI mechanics (type_then_click)
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://opensource-demo.orangehrmlive.com
"""
from pages.base_page import BasePage


class LoginPage(BasePage):
    """The login screen at /web/index.php/auth/login."""

    PATH = "/web/index.php/auth/login"

    # ── selectors ────────────────────────────────────────────
    # `name` attributes are used by the app itself, so they are far more stable
    # than the generated oxd-* class names Angular emits.
    USERNAME_INPUT = "input[name='username']"
    PASSWORD_INPUT = "input[name='password']"
    LOGIN_BUTTON = "button[type='submit']"

    # Banner shown for wrong credentials ("Invalid credentials").
    ERROR_BANNER = ".oxd-alert-content-text"
    # Per-field message shown when a field is left empty
    # ("Username cannot be empty" / "Password cannot be empty").
    FIELD_ERROR = ".oxd-input-field-error-message"

    BRANDING = ".orangehrm-login-branding"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the login screen.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture
                      from BASE_URL or config.yaml. OrangeHRM serves the login
                      form at /web/index.php/auth/login and redirects "/" there.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.PATH}")

    def login_as(self, username: str, password: str) -> None:
        """Fill both credentials and submit.

        Takes the values rather than a role name: resolving a role to real
        credentials is the `credentials` fixture's job, so this page object
        stays usable with any user, including deliberately invalid ones.
        """
        self.fill(self.USERNAME_INPUT, username)
        self.fill(self.PASSWORD_INPUT, password)
        self.click(self.LOGIN_BUTTON)

    def clear_credentials(self) -> None:
        """Empty both fields without submitting."""
        self.clear(self.USERNAME_INPUT)
        self.clear(self.PASSWORD_INPUT)

    # ── queries ──────────────────────────────────────────────
    def get_error_message(self) -> str:
        """Text of the credentials error banner."""
        self.wait_visible(self.ERROR_BANNER)
        return self.get_text(self.ERROR_BANNER)

    def get_field_error(self) -> str:
        """First per-field validation message ('Username cannot be empty')."""
        self.wait_visible(self.FIELD_ERROR)
        return self.get_text(self.FIELD_ERROR)

    def get_all_field_errors(self) -> list[str]:
        """Every per-field validation message currently shown."""
        return self.get_all_texts(self.FIELD_ERROR)

    def is_error_displayed(self) -> bool:
        """True if the credentials error banner is on screen."""
        return self.is_visible(self.ERROR_BANNER)

    def is_login_form_displayed(self) -> bool:
        """True if we are still on the login screen."""
        return self.is_visible(self.USERNAME_INPUT)
