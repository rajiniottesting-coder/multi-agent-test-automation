"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from `pages.product_detail` in the app inventory; this file
holds no literal selector strings. Methods are business verbs that say WHAT
they act on (product_name, add_to_cart, view_cart_from_modal), per the naming
rule, and every one delegates to a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. See `pages.product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing (its href
    already carries the product id), so the test never has to invent an id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name from the product information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as e.g. 'Rs. 500'. Assert on the number."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control, opening the modal."""
        self.click(self.sel("add_to_cart_button"))

    def wait_for_added_modal(self, timeout_ms: Optional[int] = None) -> None:
        """Wait for the add-to-cart confirmation modal to appear."""
        self.wait_visible(self.sel("added_modal"), timeout_ms=timeout_ms)

    def is_added_modal_showing(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart modal is visible. WAITS up to the timeout."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link, navigating to /view_cart."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
