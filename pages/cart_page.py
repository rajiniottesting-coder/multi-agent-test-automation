"""
CartPage — the SauceDemo shopping cart page.

POM principles applied:
- Selectors live HERE, not in tests.
- Methods describe USER INTENT (continue_shopping, checkout),
  not low-level actions (click button X, type Y).
"""
import urllib.parse

from pages.base_page import BasePage


class CartPage(BasePage):
    # === Locators (single source of truth) ===
    CART_ITEMS = "[data-test='inventory-item']"
    CHECKOUT_BUTTON = "[data-test='checkout']"
    CONTINUE_SHOPPING_BUTTON = "[data-test='continue-shopping']"
    REMOVE_BUTTON = "[data-test^='remove-']"

    # The URL path for this page
    URL_PATH = "/cart.html"

    def is_loaded(self) -> bool:
        """
        Verify the cart page is loaded by checking the URL path
        and the visibility of a key element.
        """
        current_path = urllib.parse.urlparse(self.page.url).path
        return current_path == self.URL_PATH and self.is_visible(self.CHECKOUT_BUTTON)

    def continue_shopping(self) -> None:
        """
        Clicks the 'Continue Shopping' button to return to the inventory page.
        """
        self.page.click(self.CONTINUE_SHOPPING_BUTTON)

    def checkout(self) -> None:
        """
        Clicks the 'Checkout' button to proceed to the checkout flow.
        """
        self.page.click(self.CHECKOUT_BUTTON)
