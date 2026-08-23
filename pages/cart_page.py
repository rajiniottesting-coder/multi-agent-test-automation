"""
CartPage — the /view_cart shopping cart screen.

Selectors come from the app inventory (`pages.cart`), never from literals here.
Set INVENTORY_PAGE, then look each element up by its `elements` key via
self.sel("<key>").

The cart PERSISTS against the signed-in account across logout and across runs,
so the inventory marks this page persistent_state. A scenario asserting an
absolute state (a row count, emptiness) must OWN its starting state first by
calling empty_the_cart() as a Given. Relative assertions (a product this test
added is present, or is gone) are always safe.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The row-level family (cart_rows) holds whole rows; read individual fields
    through the cell-scoped helpers, never by comparing a row's concatenated
    text against a single value.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the /view_cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so a later absolute assertion (emptiness, an exact
        row count) is honest — the scenario put the state there itself. Each
        removal re-renders the table, so re-read the delete family every pass
        rather than caching a count or iterating a stale list.
        """
        while self.get_count(self.sel("cart_delete_buttons")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            # After a removal the row for the deleted item detaches; wait for
            # the delete family to shrink before the next pass so we do not
            # click a control that is mid-removal.
            self.wait_for_count(
                self.sel("cart_delete_buttons"),
                self.get_count(self.sel("cart_delete_buttons")) - 1
                if self.get_count(self.sel("cart_delete_buttons")) > 0 else 0,
            )

    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Scopes to the row containing the name rather than assuming an index,
        so it removes the intended product even if the cart holds several.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        # The row detaches after deletion; wait for it to be gone so a caller
        # asserting absence immediately afterwards sees the settled state.
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table container is on screen. WAITS for it.

        The cart table is present whether the cart holds items or is empty in
        its rendered structure, making it the most state-independent readiness
        signal on this page.
        """
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in row order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row containing `product_name` is present. WAITS.

        Call this only where the product is EXPECTED to be present — it waits
        for the row and times out if it never appears. To assert a product is
        ABSENT, use wait_until_product_removed().
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def wait_until_product_removed(self, product_name: str) -> None:
        """Wait until no row containing `product_name` remains.

        The waiting form of an absence check: re-checks until the row is gone
        or the timeout expires. Use this after a removal instead of reading the
        name list once, which would race the re-render.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def get_quantity(self, product_name: str) -> int:
        """The quantity for the row containing `product_name`, as an int.

        Reads the quantity CELL for that specific row — the row index is found
        by the product name, then the quantity column is read at that index.
        """
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        if index < 0:
            raise AssertionError(
                f"No cart row contains {product_name!r}; cannot read quantity."
            )
        quantities = self.get_column_values(
            self.sel("cart_rows"), self.sel("cart_quantities"), 0
        )
        return int(quantities[index].strip())

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if it is not empty.

        Call this only where emptiness is the expected answer. A step asking
        "is it empty?" merely to branch on the reply would pay the full timeout
        every time the answer is no. The message is rendered ONLY when the cart
        holds nothing, so its presence is an absolute emptiness signal — valid
        only when the scenario owns its starting state (see empty_the_cart()).
        """
        return self.is_showing(self.sel("empty_cart_message"))
