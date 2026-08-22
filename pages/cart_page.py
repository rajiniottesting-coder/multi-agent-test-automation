"""
CartPage — the shopping cart at /view_cart.

Reads cart rows, asserts on a product's presence / quantity / price, deletes
rows, reloads, and detects the empty-cart message. Selectors live in the app
inventory under `pages.cart`; this file only ever names their keys.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart is session/account-owned server-side state, so an ABSOLUTE row
    count or emptiness assertion is only valid when the scenario owns its
    starting state (fresh session). The cart_rows / cart_product_names /
    cart_delete_buttons keys are families — never click, fill or assert on them
    as a whole; scope to the row containing a product's text instead.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def reload_cart(self) -> None:
        """Full page refresh of the cart, then confirm we are still here."""
        self.reload()
        self.confirm_arrival()

    def confirm_arrival(self, **params: object) -> None:  # noqa: D401 - see BasePage
        """Confirm the browser reached the cart page; recover if it did not."""
        super().confirm_arrival(**params)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Scopes to the row containing the product text and clicks the delete
        control inside it, so the family selector is never clicked directly.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Uses the cart table container rather than a row or the empty message,
        because the container is present whether the cart holds items or not.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name currently listed in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def row_count(self) -> int:
        """Number of product rows in the cart right now (no waiting).

        For READING the count. To ASSERT a count after a change, use
        assert_row_count(), which waits for the table to settle.
        """
        return self.get_count(self.sel("cart_rows"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until the cart has exactly `expected` product rows.

        Waits, so it is safe to call immediately after adding or removing a
        row while the page is still updating.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until a row containing `product_name` is present, or is gone.

        Use present=True after adding a product, present=False after removing
        one. Re-checks until the timeout rather than reading a snapshot.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def row_text(self, product_name: str) -> str:
        """The full text of the row containing `product_name`.

        Returns the concatenated cells (description, price, quantity, total),
        so assert containment against it rather than equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self) -> bool:
        """True once the cart shows the 'Cart is empty!' message. WAITS for it.

        Call this only where emptiness is the EXPECTED answer: it can only
        report "no" by exhausting its timeout. To branch on optional emptiness
        use has_empty_message() instead.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def has_empty_message(self) -> bool:
        """True if the empty-cart message is showing right now. Never waits.

        The non-waiting counterpart to is_empty(), for asserting that the cart
        is NOT empty without paying a full timeout.
        """
        return self.is_visible(self.sel("empty_cart_message"))
