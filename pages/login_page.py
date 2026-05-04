"""
LoginPage — represents https://www.saucedemo.com (the login page).

POM principles applied:
- Selectors live HERE, not in tests.
- Methods describe USER INTENT (login_as, get_error_message),
  not low-level actions (click button X, type Y).
"""
from playwright.sync_api import Page
from pages.base_page import BasePage


class LoginPage(BasePage):
    # === Locators (single source of truth) ===
    USERNAME_INPUT = "[data-test='username']"
    PASSWORD_INPUT = "[data-test='password']"
    LOGIN_BUTTON = "[data-test='login-button']"
    ERROR_MESSAGE = "[data-test='error']"

    # === URL ===
    URL = "https://www.saucedemo.com"
    

    def open(self) -> None:
        """Navigate to the login page."""
        self.navigate(self.URL)

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