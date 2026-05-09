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

    # New locators for burger menu and logout
    # Note: These elements do not have data-test attributes on SauceDemo,
    # so IDs are used as the most stable alternative, despite general preference for data-test.
    BURGER_MENU_BUTTON = "#react-burger-menu-btn"
    LOGOUT_LINK = "#logout_sidebar_link"
    # The wrapper for the sidebar menu, which becomes visible when the menu is open
    SIDEBAR_MENU_WRAPPER = ".bm-menu-wrap"

    # === URL ===
    URL_PATH = "/inventory.html"

    def is_loaded(self) -> bool:
        """Check whether the inventory page has loaded."""
        return self.URL_PATH in self.page.url and self.is_visible(self.INVENTORY_CONTAINER)

    def get_page_title_text(self) -> str:
        """Return the visible page title (e.g., 'Products')."""
        return self.page.locator(self.PAGE_TITLE).inner_text()

    # === New methods for burger menu and logout ===

    def is_burger_menu_button_visible(self) -> bool:
        """Check if the burger menu button (hamburger icon) is visible."""
        return self.is_visible(self.BURGER_MENU_BUTTON)

    def click_burger_menu_button(self) -> None:
        """Click the burger menu button to open the sidebar menu."""
        self.page.click(self.BURGER_MENU_BUTTON)
        # Wait for the menu wrapper to become visible after clicking the button
        self.wait_for_selector(self.SIDEBAR_MENU_WRAPPER, state='visible')

    def is_logout_link_visible(self) -> bool:
        """Check if the 'Logout' link is visible within the opened sidebar menu.
        This implicitly checks if the menu is open, as the link is inside the menu.
        """
        return self.is_visible(self.LOGOUT_LINK)

    def click_logout_link(self) -> None:
        """Click the 'Logout' link in the sidebar menu.
        Assumes the sidebar menu is already open.
        """
        self.page.click(self.LOGOUT_LINK)
