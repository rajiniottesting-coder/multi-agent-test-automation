"""
CartPage — the shopping cart.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The cart. Selectors: see `pages.cart` in the app inventory.

    The cart is TEST-OWNED data: it belongs to this test's own session or
    account and nobody else can change it. Asserting an exact row count is
    therefore safe here, unlike anything based on the shared catalogue.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate to the cart."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, name: str) -> None:
        """Delete one product's row, found by the product's own name.

        Finds the row by TEXT and deletes that row's control. Clicking the
        bare `cart_delete_buttons` family would be a strict-mode violation
        the moment the cart holds more than one line.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), name)
        self.click(f'{self.sel("cart_delete_buttons")} >> nth={index}')

    def proceed_to_checkout(self) -> None:
        """Start checkout.

        Proceeding while logged out shows a Register/Login prompt rather than
        the address form, so a checkout scenario must authenticate first.
        """
        self.click(self.sel("proceed_to_checkout_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, name: str) -> bool:
        """True if this product is in the cart."""
        return any(name.lower() in t.lower() for t in self.product_names())

    def row_count(self) -> int:
        """Number of line items. Safe to assert exactly — see the class note."""
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self) -> bool:
        """True if the cart shows its empty state. Never waits."""
        return self.is_visible(self.sel("empty_cart_message"))
