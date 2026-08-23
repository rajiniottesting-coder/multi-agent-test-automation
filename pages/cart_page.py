"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory; this file never holds a
literal selector. Every method is a business verb and delegates to a BasePage
helper.

The cart PERSISTS against the signed-in account: it survives logout and the
run. A scenario asserting an absolute state (an exact count, or emptiness) must
own that state first with empty_the_cart(), which is why this class provides it
even for stories that only add a product.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    cart_rows, cart_product_names and cart_delete_buttons are MULTI-MATCH
    families — one member per product. Never click or assert on the family as a
    whole; scope to the row containing a product's name instead.

    The inventory exposes NO quantity-cell key on this page — cart_rows is the
    whole-row family and cart_product_names is the name column. There is no
    cell-scoped selector for the quantity column, so quantity is NOT readable
    here as an isolated field. This class therefore exposes has_product() to
    confirm presence and assert_row_count() to confirm counts, but no
    quantity getter — see notes.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Remove the row for `product_name` by clicking its delete control.

        Scopes to the row containing the product name rather than indexing
        into the delete family, so it acts on the intended product even if the
        row order changes. Waits for the row to disappear before returning, so
        a following assertion does not race the re-render.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so a scenario can own its starting state and then
        assert an absolute condition (an exact count, or emptiness) honestly.
        The list re-renders after each removal, so the row count is re-read
        every iteration rather than snapshotting the delete family once.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            remaining = self.get_count(self.sel("cart_rows"))
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            # each click drops the row count by one; wait for the re-render
            self.wait_for_count(self.sel("cart_rows"), remaining - 1)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product is EXPECTED to be present — it times
        out if the row never appears. To assert a product is absent, use
        remove_product (which already waits for the row to go) or
        wait_for_row(..., present=False).
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def is_empty(self) -> bool:
        """True once the cart shows its 'Cart is empty!' message. WAITS.

        Call this only where emptiness is the EXPECTED answer. It waits for the
        empty-state message and times out if the cart still holds items, so a
        step branching on 'is it empty?' would pay the full timeout on 'no'.
        Asserting emptiness this way is only honest when the scenario owns its
        starting state via empty_the_cart().
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Only honest when the scenario owns its starting state — the cart
        persists across runs against a shared account.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)
