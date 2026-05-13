"""
CartPage — the SauceDemo shopping cart page.

This page object encapsulates the locators and actions
available on the shopping cart page (/cart.html). It is used
for tests that involve cart interactions or navigation from the cart.
"""
from playwright.sync_api import Page
from pages.base_page import BasePage


class CartPage(BasePage):
    # === Locators (single source of truth) ===
    URL_PATH = "/cart.html"
    CONTINUE_SHOPPING_BUTTON = "[data-test='continue-shopping']"
    CHECKOUT_BUTTON = "[data-test='checkout']"
    CART_ITEMS = "[data-test='inventory-item']"
    REMOVE_BUTTON = "[data-test^='remove-']"

    def is_loaded(self) -> bool:
        """
        Verify if the cart page is currently displayed by checking the URL.
        """
        return self.URL_PATH in self.page.url

    def continue_shopping(self) -> None:
        """
        Clicks the 'Continue Shopping' button, which navigates the user
        back to the inventory page.
        """
        self.page.click(self.CONTINUE_SHOPPING_BUTTON)

    def go_to_checkout(self) -> None:
        """
        Clicks the 'Checkout' button to proceed to the next step in the
        purchasing flow.
        """
        self.page.click(self.CHECKOUT_BUTTON)
