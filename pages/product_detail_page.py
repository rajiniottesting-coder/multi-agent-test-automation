"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the `product_detail` page in the app inventory; this file
never contains a literal selector. Method names say WHAT they act on, per the
generation naming rule (open_product, not open).

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (one per page), unlike the listing
    page's family of buttons, so a cart scenario should add the product from
    here. Adding opens a modal that blocks the page underneath; leave via the
    modal's View Cart link or the Continue Shopping button.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        Opens the add-to-cart modal rather than navigating; use
        wait_for_added_modal() before interacting with the modal.
        """
        self.click(self.sel("add_to_cart_button"))

    def wait_for_added_modal(self, timeout_ms: Optional[int] = None) -> None:
        """Wait for the add-to-cart modal to become visible."""
        self.wait_visible(self.sel("added_modal"), timeout_ms=timeout_ms)

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal to go to the cart."""
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name from the detail heading. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def has_added_modal(self) -> bool:
        """True if the add-to-cart modal is showing right now. Never waits."""
        return self.is_visible(self.sel("added_modal"))
