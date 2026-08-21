"""
CartPage — the shopping cart screen (/view_cart).

Reads cart rows, verifies a product is present, deletes a row scoped to the
product name, and checks the empty-cart state.

Selectors: see `pages.cart` in the app inventory. No selector literals live in
this file — every element is looked up by key via self.sel().

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart's contents belong to this test's own session/account, so an exact
    row count is safe here. Presence checks scope to the product name rather
    than assuming a row index. The empty-cart message is the mirror of the
    rows: exactly one of the two is present at any moment.

    Family keys (cart_rows, cart_product_names, cart_delete_buttons) match many
    elements — read them with the plural helpers and act on ONE member by
    scoping to the row that contains its text. Never wait on or assert against
    the family as a whole; Playwright's strict mode rejects it.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is the readiness element: present whether the cart holds
        rows or is empty, so it survives both states of the page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order.

        Reads the product-name family with the plural helper — the only legal
        operation on a multi-match key.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present in the cart.

        Scopes to the row containing the name rather than waiting on the
        product-name family (which matches several elements and would raise in
        strict mode). find_row_index_by_text retries until the row appears, so
        a check made right after arriving at the cart does not race the render.
        """
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) >= 0

    def row_count(self) -> int:
        """Number of product rows currently in the cart (snapshot, no wait)."""
        return self.get_row_count(self.sel("cart_rows"))

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        The message renders only when the cart holds nothing, so this asserts
        the cart is empty ABSOLUTELY. The scenario must own its starting state.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── assertions on state ──────────────────────────────────
    def assert_row_count(self, expected: int) -> None:
        """Wait until the cart holds exactly `expected` product rows.

        Scopes the count to rows containing something (the row family) via the
        row-count helper, which retries until the number settles — the moment
        worth counting is right after a removal, when the page is still updating.
        """
        self.wait_for_text(self.sel("cart_table"), "")  # ensure table is present
        actual = self.get_row_count(self.sel("cart_rows"))
        assert actual == expected, (
            f"Expected {expected} cart row(s), found {actual}"
        )

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row that contains `product_name`.

        Scopes to the row containing the name and clicks the delete control
        inside it, so the correct row is removed regardless of position. This
        removal happens in place — there is no page navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
