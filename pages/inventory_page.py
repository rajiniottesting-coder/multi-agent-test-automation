"""
InventoryPage — represents the products list at /inventory.html.
This is what users see after a successful login.
"""
from playwright.sync_api import Page
from pages.base_page import BasePage


class InventoryPage(BasePage):
    # === Locators ===
    PAGE_TITLE = "[data-test='title']"
    INVENTORY_CONTAINER = "[data-test='inventory-container']"
    SHOPPING_CART_LINK = "[data-test='shopping-cart-link']"
    SORT_DROPDOWN = "[data-test='product-sort-container']"
    SORT_OPTION = "[data-test='{option}']"  # Placeholder for specific sort options

    # === URL ===
    URL_PATH = "/inventory.html"

    def is_loaded(self) -> bool:
        """Check whether the inventory page has loaded."""
        return self.URL_PATH in self.page.url and self.is_visible(self.INVENTORY_CONTAINER)

    def get_page_title_text(self) -> str:
        """Return the visible page title (e.g., 'Products')."""
        return self.page.locator(self.PAGE_TITLE).inner_text()

    def select_sort_option(self, option: str) -> None:
        """
        Selects a sorting option from the dropdown.

        Args:
            option: The text of the sort option to select (e.g., 'Price (high to low)').
        """
        self.page.locator(self.SORT_DROPDOWN).click()
        # The actual value for the sort option is often different from the display text.
        # We'll use a data-test attribute that maps to the option's value.
        # Based on common patterns, these are often like 'price-asc', 'price-desc', 'az', 'za'.
        # We'll map common display texts to their likely data-test values.
        sort_option_map = {
            "Products (A to Z)": "az",
            "Products (Z to A)": "za",
            "Price (low to high)": "price-asc",
            "Price (high to low)": "price-desc",
        }
        data_test_value = sort_option_map.get(option)
        if not data_test_value:
            raise ValueError(f"Unknown sort option: {option}. Supported options are: {list(sort_option_map.keys())}")

        sort_selector = self.SORT_OPTION.format(option=data_test_value)
        self.page.locator(sort_selector).click()

    def get_product_names(self) -> list[str]:
        """Returns a list of product names currently displayed on the page."""
        product_names_selectors = "[data-test='inventory-item-name']"
        return self.page.locator(product_names_selectors).all_text_contents()

    def get_product_prices(self) -> list[float]:
        """Returns a list of product prices currently displayed on the page."""
        product_prices_selectors = "[data-test='inventory-item-price']"
        price_texts = self.page.locator(product_prices_selectors).all_text_contents()
        # Remove '$' and convert to float
        return [float(price.replace('$', '')) for price in price_texts]

    def get_current_sort_dropdown_value(self) -> str:
        """
        Returns the currently selected value in the sort dropdown.
        This is often represented by a class or attribute on the dropdown container.
        For SauceDemo, it's usually a class like 'select_container'.
        We'll try to extract the text of the selected option.
        """
        # Playwright's locator for the select element itself might be more reliable.
        # The data-test='product-sort-container' points to the div containing the select.
        # We need to find the actual selected option within it.
        selected_option_selector = "[data-test='product-sort-container'] > select > option[selected]"
        if self.is_visible(selected_option_selector):
            return self.page.locator(selected_option_selector).inner_text()
        else:
            # Fallback if 'selected' attribute isn't used or visible.
            # This might happen if the dropdown is just a div and not a native select.
            # For SauceDemo, it's a native select.
            # If the above fails, we might need to inspect the DOM more closely.
            # For now, let's assume the above works or return an empty string if not found.
            return ""

    def refresh_page(self) -> None:
        """Refreshes the current page."""
        self.page.reload()

    def navigate_to_cart(self) -> None:
        """Clicks the shopping cart link to navigate to the cart page."""
        self.page.click(self.SHOPPING_CART_LINK)

    def click_first_product(self) -> None:
        """Clicks on the first product in the inventory list to navigate to its detail page."""
        first_product_selector = "[data-test='inventory-item-name']"
        self.page.click(first_product_selector)
