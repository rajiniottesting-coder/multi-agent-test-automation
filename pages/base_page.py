"""
BasePage — parent class for all page objects.
Holds the Playwright `page` reference and common actions.
"""
from playwright.sync_api import Page, expect


class BasePage:
    """Every page object inherits from this."""

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the page to load."""
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")

    def get_title(self) -> str:
        """Return the page title."""
        return self.page.title()

    def is_visible(self, locator: str) -> bool:
        """Check if an element is visible."""
        return self.page.locator(locator).is_visible()

    def go_back(self) -> None:
        """Navigate to the previous page in history (browser back button)."""
        self.page.go_back()
        # Wait for navigation to complete after going back
        self.page.wait_for_load_state("domcontentloaded")
