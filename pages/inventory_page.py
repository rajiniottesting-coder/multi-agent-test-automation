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
    BURGER_MENU_BUTTON = "[data-test='open-sidebar']"
    LOGOUT_LINK = "[data-test='logout-sidebar-link']"

    # === URL ===
    URL_PATH = "/inventory.html"

    def is_loaded(self) -> bool:
        """Check whether the inventory page has loaded."""
        return self.URL_PATH in self.page.url and self.is_visible(self.INVENTORY_CONTAINER)

    def get_page_title_text(self) -> str:
        """Return the visible page title (e.g., 'Products')."""
        return self.page.locator(self.PAGE_TITLE).inner_text()

    # === New methods for logout feature ===

    def is_burger_menu_button_visible(self) -> bool:
        """Check if the burger menu button is visible."""
        return self.is_visible(self.BURGER_MENU_BUTTON)

    def open_burger_menu(self) -> None:
        """Click the burger menu button to open the sidebar navigation."""
        self.page.click(self.BURGER_MENU_BUTTON)

    def is_logout_link_visible(self) -> bool:
        """Check if the 'Logout' link is visible within the opened sidebar menu."""
        return self.is_visible(self.LOGOUT_LINK)

    def click_logout(self) -> None:
        """Click the 'Logout' link in the sidebar menu.
        This method ensures the burger menu is open before attempting to click logout.
        """
        # Open the burger menu if it's not already open (e.g., by checking logout link visibility)
        if not self.is_logout_link_visible():
            self.open_burger_menu()
        self.page.click(self.LOGOUT_LINK)
