"""
LoginPage — the SauceDemo login page.

POM principles applied:
- Selectors live HERE, not in tests.
- Methods describe USER INTENT (login_as, get_error_message),
  not low-level actions (click button X, type Y).

Note on URL: the base URL is NOT hardcoded here. It comes from
`config/config.yaml` via the `base_url` pytest fixture. This keeps
the application URL in one place and makes the page object reusable
across environments (dev / staging / prod).
"""
from playwright.sync_api import Page
from pages.base_page import BasePage


class LoginPage(BasePage):
    # === Locators (single source of truth) ===
    # NOTE on error elements: SauceDemo renders the error text inside an
    # <h3 data-test="error"> element, and the (X) close button as a SIBLING
    # <button data-test="error-button">. The close button is NOT a child of
    # the error element, so a selector like "[data-test='error'] button"
    # will not find anything. Use ERROR_BUTTON below to dismiss errors.
    USERNAME_INPUT = "[data-test='username']"
    PASSWORD_INPUT = "[data-test='password']"
    LOGIN_BUTTON = "[data-test='login-button']"
    ERROR_MESSAGE = "[data-test='error']"
    ERROR_BUTTON = "[data-test='error-button']"

    def open(self, base_url: str) -> None:
        """Navigate to the login page.

        Args:
            base_url: The application base URL, supplied by the test fixture
                      from config.yaml. The login form lives at the root path.
        """
        self.navigate(base_url)

    def login_as(self, username: str, password: str) -> None:
        """Perform full login flow."""
        self.page.fill(self.USERNAME_INPUT, username)
        self.page.fill(self.PASSWORD_INPUT, password)
        self.page.click(self.LOGIN_BUTTON)

    def get_error_message(self) -> str:
        """Return error message text (empty string if none)."""
        if self.is_visible(self.ERROR_MESSAGE):
            return self.page.locator(self.ERROR_MESSAGE).inner_text()
        return ""

    def dismiss_error(self) -> None:
        """Click the (X) close button on the error banner to dismiss it.

        Use this between successive failed-login attempts in the same
        scenario so each attempt asserts against a fresh error, not the
        stale one from the previous attempt.
        """
        self.page.click(self.ERROR_BUTTON)

    def clear_credentials(self) -> None:
        """Clear both username and password input fields."""
        self.page.fill(self.USERNAME_INPUT, "")
        self.page.fill(self.PASSWORD_INPUT, "")