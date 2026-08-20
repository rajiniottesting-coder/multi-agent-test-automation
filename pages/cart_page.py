"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never contains
a literal selector string. Methods are business verbs and every one delegates
to a BasePage helper.

The cart persists for a registered account, so absolute assertions ("the cart
is empty") require the scenario to own its starting state. This page object
offers BOTH a relative reader (has_product) for "the product I added is here"
and an absolute one (is_empty) for "nothing remains after I removed it".

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table is the one element present whether the cart holds items
        or (via its empty message region) is empty, so it is a stable
        readiness probe.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in row order.

        cart_product_names is a MULTI-MATCH family, so read it with the plural
        accessor rather than clicking or asserting on the family.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present. Relative assertion.

        Safe on the shared, account-owned cart: it asserts only about the item
        this test added, not about the total row count.
        """
        return any(product_name in name for name in self.get_product_names())

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart.

        Only meaningful when the scenario owns its starting state — see the
        inventory's _starting_state note. Prefer has_product for relative
        checks.
        """
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self) -> bool:
        """True when the cart holds nothing. Non-waiting absolute check.

        Reads the empty-cart message the app itself renders, which is present
        only when no rows remain. Non-waiting so an "is empty" assertion is
        actually reachable; the waiting reader would time out when the message
        is (correctly) absent in a non-empty cart.
        """
        return self.is_visible(self.sel("empty_cart_message"))

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, rather than indexing into the MULTI-MATCH delete
        family. Removal is client-side — no page navigation follows.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    def wait_until_product_removed(
        self, product_name: str, timeout_ms: Optional[int] = None
    ) -> None:
        """Wait until the row for `product_name` is gone.

        Waits on the emptied-cart message so a subsequent absolute empty check
        does not race the client-side removal.
        """
        self.wait_visible(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
