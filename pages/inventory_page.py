"""
InventoryPage — represents the products list at /inventory.html.
This is what users see after a successful login.
"""
from pages.base_page import BasePage


class InventoryPage(BasePage):
    # === Locators ===
    PAGE_TITLE = "[data-test='title']"
    INVENTORY_CONTAINER = "[data-test='inventory-container']"
    SHOPPING_CART_LINK = "[data-test='shopping-cart-link']"
    SORT_DROPDOWN = "[data-test='product-sort-container']"
    INVENTORY_ITEM_NAME = "[data-test='inventory-item-name']"
    INVENTORY_ITEM_PRICE = "[data-test='inventory-item-price']"

    # === URL ===
    URL_PATH = "/inventory.html"

    def is_loaded(self) -> bool:
        """Check whether the inventory page has loaded."""
        return self.URL_PATH in self.page.url and self.is_visible(self.INVENTORY_CONTAINER)

    def get_page_title_text(self) -> str:
        """Return the visible page title (e.g., 'Products')."""
        return self.page.locator(self.PAGE_TITLE).inner_text()

    def select_sort_option(self, option_text: str) -> None:
        """Selects a sort option from the dropdown by its visible text.

        Args:
            option_text: The visible text of the option to select,
                         e.g., "Price (low to high)".
        """
        self.page.select_option(self.SORT_DROPDOWN, label=option_text)

    def get_active_sort_option(self) -> str:
        """Returns the visible text of the currently active sort option."""
        # For a <select> element, the active option's text can be found
        # by evaluating the DOM element.
        return self.page.locator(self.SORT_DROPDOWN).evaluate(
            "el => el.options[el.selectedIndex].text"
        )

    def get_product_names(self) -> list[str]:
        """Returns a list of all visible product names in their current order."""
        return self.page.locator(self.INVENTORY_ITEM_NAME).all_inner_texts()

    def get_product_prices(self) -> list[float]:
        """
        Returns a list of all visible product prices in their current order.
        Prices are parsed from string (e.g., "$9.99") to float (e.g., 9.99).
        """
        price_texts = self.page.locator(self.INVENTORY_ITEM_PRICE).all_inner_texts()
        return [float(price.replace("$", "")) for price in price_texts]
