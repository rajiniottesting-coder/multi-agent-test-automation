"""
InventoryPage — represents the products list at /inventory.html.
This is what users see after a successful login.
"""
from typing import List
from pages.base_page import BasePage


class InventoryPage(BasePage):
    # === Locators ===
    PAGE_TITLE = "[data-test='title']"
    INVENTORY_CONTAINER = "[data-test='inventory-container']"
    SHOPPING_CART_LINK = "[data-test='shopping-cart-link']"
    SORT_DROPDOWN = "[data-test='product-sort-container']"
    ACTIVE_SORT_OPTION = "[data-test='active-option']"
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

    def sort_products_by(self, option_text: str) -> None:
        """Selects a sort option from the dropdown.

        Args:
            option_text: The visible text of the option to select,
                         e.g., "Price (low to high)".
        """
        sort_options = {
            "Name (A to Z)": "az",
            "Name (Z to A)": "za",
            "Price (low to high)": "lohi",
            "Price (high to low)": "hilo",
        }
        option_value = sort_options.get(option_text)
        if not option_value:
            raise ValueError(f"Invalid sort option text: '{option_text}'")
        self.page.select_option(self.SORT_DROPDOWN, value=option_value)

    def get_active_sort_option_text(self) -> str:
        """Return the text of the currently selected sort option."""
        return self.page.locator(self.ACTIVE_SORT_OPTION).inner_text()

    def get_product_names(self) -> List[str]:
        """Return a list of all visible product names in their current order."""
        return self.page.locator(self.INVENTORY_ITEM_NAME).all_inner_texts()

    def get_product_prices(self) -> List[float]:
        """Return a list of all visible product prices (as floats) in their current order."""
        price_texts = self.page.locator(self.INVENTORY_ITEM_PRICE).all_inner_texts()
        return [float(p.replace('$', '')) for p in price_texts]

    def click_shopping_cart(self) -> None:
        """Navigates to the shopping cart page."""
        self.page.click(self.SHOPPING_CART_LINK)
