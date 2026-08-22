"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never contains
a literal selector. The cart is persistent per account (see the inventory's
persistent_state note), so scenarios asserting an ABSOLUTE empty state must own
their starting state. Relative assertions ("the product I added is present /
gone") hold whatever the cart started with.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory.

    The row / name / delete keys are all MULTI-MATCH families — one member per
    cart line. Read them with the plural helpers, and act on a single line by
    scoping to the row that contains the product name.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the cart line for `product_name` by clicking the X in its row.

        Scopes to the row containing the product name rather than indexing into
        the delete-button family, so it acts on the correct line even if the
        cart holds several products.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        # Removal is an in-place update with no navigation; confirm the row is gone.
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table, which is present whether the cart holds items or
        is empty, so it is a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED to be present; to assert a
        product is absent, use wait_for_product_absent, which waits for removal.
        """
        return self.is_showing(self.sel("cart_table")) and product_name in self.get_product_names()

    def wait_for_product_absent(self, product_name: str) -> None:
        """Wait until the row for `product_name` is gone. Raises on timeout.

        The waiting form of an absence check — use after a removal rather than
        snapshotting the name list, which can be read before the DOM settles.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def get_row_text(self, product_name: str) -> str:
        """The full text of the cart row containing `product_name`.

        A cart row concatenates every column (name, price, quantity, total), so
        assert containment against this rather than equality with one field.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` cart rows are present. Raises on timeout.

        Uses wait_for_count so the assertion re-checks until the DOM settles
        after an add or remove, instead of snapshotting a mid-update count.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        This asserts the cart is empty ABSOLUTELY, so call it only when the
        scenario owns its starting state. A step branching on emptiness would
        pay the full timeout every time the cart is not empty.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
