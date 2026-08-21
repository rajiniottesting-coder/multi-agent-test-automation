"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory; this file never holds a
literal selector. Set INVENTORY_PAGE and resolve every element via self.sel().

The cart is per-account, server-rendered, and PERSISTENT across logout and
runs (see the inventory's persistent_state note). Absolute assertions — an
exact row count, or the empty-cart message — are only safe when the scenario
owns its starting state (fresh session / fresh account). The row family is a
multi_match, so acting on one product row is always scoped to the row that
contains that product's name via click_in_row().

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page by URL."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def reload_cart(self) -> None:
        """Full page refresh of the current cart page."""
        self.reload()

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart page; recover if it did not.

        Overrides the BasePage helper's semantics by also waiting for the cart
        table so callers arriving from the modal / nav have a rendered page.
        """
        super().confirm_arrival(**params)
        self.wait_visible(self.sel("cart_table"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def assert_row_count(self, expected: int) -> None:
        """Wait until the cart holds exactly `expected` product rows.

        Uses wait_for_count so the assertion re-checks while the page settles
        after an add or remove, rather than snapshotting a stale number.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart (no waiting)."""
        return self.get_count(self.sel("cart_rows"))

    def get_product_names(self) -> List[str]:
        """Every product name in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present. WAITS for the table."""
        self.wait_visible(self.sel("cart_table"))
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) != -1

    def get_row_text(self, product_name: str) -> str:
        """Full text of the row containing `product_name` (all columns).

        A row spans description, price, quantity and total, so callers must
        assert containment against this blob, not equality with one field.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return (row.inner_text() or "").strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is showing. WAITS for it.

        Only meaningful when the scenario owns its starting state; the message
        asserts the cart is empty ABSOLUTELY.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row that contains `product_name`."""
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
