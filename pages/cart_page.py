"""
CartPage — the /view_cart screen.

Wraps the cart table: reads product rows, checks whether a product the test
added is present, removes one product by scoping to its row, and reports the
empty-cart state.

Selectors: see `pages.cart` in the app inventory. Every selector is resolved
through self.sel("<key>"); no literal selectors live in this file.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart belongs to the test's own session, so an exact row count is safe
    here. cart_rows / cart_product_names / cart_delete_buttons are MULTI-MATCH
    families: read them with the plural helpers, and act on a single member by
    scoping to the row that contains the product name.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present in the cart."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Use this to assert the cart is empty — the message is rendered ONLY
        when the cart holds nothing, so waiting for it is correct here.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the row whose product name is `product_name`.

        Scopes to the row containing the product name and clicks its delete
        control, so it acts on exactly one member of the delete-button family.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
