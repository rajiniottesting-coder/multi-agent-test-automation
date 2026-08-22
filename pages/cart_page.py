"""
CartPage — the /view_cart shopping cart screen.

Selectors live in the app inventory under the `cart` page; this file never
writes a literal selector. Set INVENTORY_PAGE and resolve every element with
self.sel("<key>").

The cart PERSISTS against a registered account across logout and across runs
(inventory: persistent_state). A scenario asserting an ABSOLUTE state here —
"exactly one row", "the cart is empty" — must OWN its starting state first,
either by registering a fresh account (not available in this app) or by
clearing the cart via empty_the_cart(). Otherwise assert RELATIVELY: that the
product this test added is present, or is gone.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart screen."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_on_cart(self) -> None:
        """Confirm the browser reached the cart page; recover if an ad ate the
        navigation that was expected to land here."""
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the row for `product_name` by clicking its delete control.

        Scopes to the row containing the name rather than indexing a family:
        the delete controls are a multi_match family, so clicking the family
        directly is a strict-mode violation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        # The row re-renders in place with no navigation; wait for it to go.
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so a scenario can OWN its starting state; after it,
        an absolute assertion (is_empty / assert_row_count) is honest because
        the scenario put the state there itself. Re-reads the row list after
        each removal because the table re-renders on every delete.
        """
        names = self.product_names()
        while names:
            first = names[0]
            self.click_in_row(
                self.sel("cart_rows"),
                first,
                self.sel("cart_delete_buttons"),
            )
            self.wait_for_row(self.sel("cart_rows"), first, present=False)
            names = self.product_names()

    # ── queries ──────────────────────────────────────────────
    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order.

        A family read via get_all_texts — safe on the multi_match cart names.
        Use it to assert RELATIVELY that a product is present.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this where the product is EXPECTED. To assert a product is gone,
        use wait_for_row(..., present=False) via remove_product, not a negation
        of this waiting probe.
        """
        try:
            self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
            return True
        except Exception:
            return False

    def assert_product_present(self, product_name: str) -> None:
        """Wait until a row containing `product_name` is present.

        The relative assertion that holds whatever the cart started with:
        the product this test added is here.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Absolute — only honest when the scenario owns its starting state
        (a cleared cart). Uses wait_for_count so a just-completed add or
        removal has time to re-render rather than counting a stale snapshot.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if it is not empty.

        Call this only where emptiness is the EXPECTED answer, and only after
        the scenario owns its starting state (see empty_the_cart). A step
        asking "is it empty?" to branch on the reply would pay the full timeout
        every time the answer is no.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)
