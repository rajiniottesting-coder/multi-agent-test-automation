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
    BURGER_MENU_BUTTON = "#react-burger-menu-btn"
    LOGOUT_LINK = "[data-test='logout-sidebar-link']"

    # === URL ===
    URL_PATH = "/inventory.html"

    def is_loaded(self) -> bool:
        """Check whether the inventory page has loaded."""
        return self.URL_PATH in self.page.url and self.is_visible(self.INVENTORY_CONTAINER)

    def get_page_title_text(self) -> str:
        """Return the visible page title (e.g., 'Products')."""
        return self.page.locator(self.PAGE_TITLE).inner_text()

    def open_burger_menu(self) -> None:
        """Click the burger menu button to open the sidebar."""
        self.page.click(self.BURGER_MENU_BUTTON)

    def click_logout(self) -> None:
        """Click the logout link from the sidebar menu."""
        self.page.click(self.LOGOUT_LINK)

    def logout(self) -> None:
        """Perform the full logout flow: open menu, click logout."""
        self.open_burger_menu()
        self.click_logout()
