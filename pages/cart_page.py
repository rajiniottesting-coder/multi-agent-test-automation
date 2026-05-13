"""
CartPage — the SauceDemo shopping cart page.

POM principles applied:
- Selectors live HERE, not in tests.
- Methods describe USER INTENT (continue_shopping, checkout),
  not low-level actions (click button X).
"""
from urllib.parse import urlparse
from pages.base_page import BasePage


class CartPage(BasePage):
    # === Locators (single source of truth) ===
    URL_PATH = "/cart.html"
    CONTINUE_SHOPPING_BUTTON = "[data-test='continue-shopping']"
    CHECKOUT_BUTTON = "[data-test='checkout']"
    CART_ITEMS = "[data-test='inventory-item']"
    # Note: This selector can match multiple remove buttons
    REMOVE_BUTTON = "[data-test^='remove-']"

    def is_loaded(self) -> bool:
        """Verify the user is on the cart page by checking the URL path."""
        return urlparse(self.page.url).path == self.URL_PATH

    def continue_shopping(self) -> None:
        """Click the 'Continue Shopping' button to return to the inventory page."""
        self.page.click(self.CONTINUE_SHOPPING_BUTTON)

    def checkout(self) -> None:
        """Click the 'Checkout' button to proceed to the checkout flow."""
        self.page.click(self.CHECKOUT_BUTTON)
