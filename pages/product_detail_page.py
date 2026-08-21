"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from `pages.product_detail` in the app inventory; this file
declares no literal selector strings. Methods are business verbs that name
what they act on, per the generation naming rule.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail. Selectors: see `pages.product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (one product per page), unlike the
    listing page's family of 68 — which is why cart scenarios add from here.
    Adding opens a blocking modal offering 'View Cart' and 'Continue Shopping'.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name from the detail heading. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the quantity BEFORE adding to cart; later changes are ignored."""
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_product_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Follow 'View Cart' in the add-to-cart modal to the cart page."""
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
