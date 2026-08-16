"""
CartPage — the /view_cart shopping-cart screen.

Selectors come from `pages.cart` in the app inventory; this file never holds a
literal selector string. Family selectors (cart_rows, cart_product_names,
cart_delete_buttons) are read with plural helpers only; to act on ONE row the
methods below resolve it by product name via BasePage.find_row_index_by_text.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart belongs to this test's own session, so an exact row count is
    safe here. cart_rows and empty_cart_message are mutually exclusive: exactly
    one is present at any moment, so absence of rows is asserted through the
    empty-state message, not by racing the row locator.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the /view_cart screen."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Resolves the row index by text, then clicks that row's delete control
        by index — never the multi-match delete family directly. Removal is an
        in-place AJAX action, so it does not navigate.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        if index < 0:
            raise AssertionError(f"No cart row found for {product_name!r}")
        delete_at_index = f"{self.sel('cart_delete_buttons')} >> nth={index}"
        self.click(delete_at_index)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_count(self) -> int:
        """Number of product rows in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def has_product(self, product_name: str) -> bool:
        """True if a row's description contains `product_name`."""
        return any(product_name in name for name in self.get_product_names())

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        The empty-state message and the product rows are mutually exclusive, so
        this is the reliable signal that the last item was removed."""
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
