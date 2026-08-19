"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from `pages.product_detail` in the app inventory; this file
never contains a literal selector. Methods are business verbs that name their
subject (open_product, add_product_to_cart), per the naming rule.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail screen. Selectors: see `pages.product_detail`."""

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        Opens the add-to-cart modal rather than navigating; wait for the
        modal before interacting with anything underneath.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's 'View Cart' link to the cart page."""
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product."""
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """Visible product name on this detail page. Waits for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price, e.g. 'Rs. 500'. Waits for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def has_added_modal(self) -> bool:
        """True if the add-to-cart modal is showing. Never waits, never raises."""
        return self.is_visible(self.sel("added_modal"))
