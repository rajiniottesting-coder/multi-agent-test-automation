"""
ProductDetailPage — a single product's detail screen.

Selectors: see `pages.product_detail` in the app inventory. This page carries
one unique Add to cart control (unlike the listing's family of 68), which is
why a cart scenario adds a product from here. Adding opens a MODAL rather than
navigating; the modal offers 'View Cart' (navigate to cart) and 'Continue
Shopping' (dismiss and stay). Selectors are resolved via self.sel(...) only.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Read the product name, add to cart, go to cart."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name from the product-information heading."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as e.g. 'Rs. 500'."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        This opens the add-to-cart modal rather than navigating. Wait for the
        modal so callers can safely act on its buttons next.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal to open the cart."""
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
