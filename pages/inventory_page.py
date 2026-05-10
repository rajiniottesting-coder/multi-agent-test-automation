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
    # New locators for burger menu and logout functionality
    BURGER_MENU_BUTTON = "#react-burger-menu-btn"
    SIDEBAR_MENU_WRAPPER = ".bm-menu-wrap"  # The container that becomes visible when the menu is open
    LOGOUT_LINK = "#logout_sidebar_link"

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
        """Check if the burger menu button is visible on the page."""
        return self.is_visible(self.BURGER_MENU_BUTTON)

    def open_burger_menu(self) -> None:
        """Click the burger menu button to open the sidebar navigation."""
        self.page.click(self.BURGER_MENU_BUTTON)
        # Wait for the sidebar menu to become visible after clicking
        self.page.wait_for_selector(self.SIDEBAR_MENU_WRAPPER, state='visible')

    def is_logout_link_visible(self) -> bool:
        """Check if the 'Logout' link is visible within the opened sidebar menu."""
        # First, ensure the sidebar menu itself is visible
        if self.is_visible(self.SIDEBAR_MENU_WRAPPER):
            return self.is_visible(self.LOGOUT_LINK)
        return False

    def click_logout(self) -> None:
        """Click the 'Logout' link in the sidebar menu.

        This method will open the burger menu if it's not already open
        before attempting to click the logout link.
        """
        if not self.is_visible(self.SIDEBAR_MENU_WRAPPER):
            self.open_burger_menu()
        self.page.click(self.LOGOUT_LINK)
        # After logout, the user should be redirected to the login page,
        # so no need to wait for elements on the inventory page.
