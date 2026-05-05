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
    USERNAME_INPUT = "[data-test='username']"
    PASSWORD_INPUT = "[data-test='password']"
    LOGIN_BUTTON = "[data-test='login-button']"
    ERROR_MESSAGE = "[data-test='error']"

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