"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory; this file never contains
a literal selector. Set INVENTORY_PAGE, then use self.sel("<key>").

The cart PERSISTS against the signed-in account across logout and across runs,
so any scenario asserting an absolute state (a specific row count, or that the
cart is empty) must first own its starting state. empty_the_cart() is the
clearing method for that precondition — it removes every row so a later
absolute assertion is honest.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    The row family (cart_rows) is a repeating container: reading its text gives
    every cell of a row concatenated. Read individual fields through the column
    families and scope actions to the row containing a product name.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the row for `product_name` from the cart.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so the correct row is removed even when several
        products are present.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove EVERY row so the cart starts genuinely empty.

        A precondition helper for scenarios that later assert an absolute state
        (an exact row count, or that the cart is empty). The cart persists
        against the signed-in account, so without this a previous run's
        leftovers would make an emptiness assertion pass or fail for the wrong
        reason.

        Deletes the first row repeatedly rather than iterating a snapshot: each
        deletion re-renders the table, so a snapshot of delete controls goes
        stale. Stops when no rows remain.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            self.wait_for_count(
                self.sel("cart_rows"),
                self.get_count(self.sel("cart_rows")) - 1,
            )

    # ── queries ──────────────────────────────────────────────
    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for `product_name` is present. WAITS for it.

        Call this only where the product IS expected. For absence, use
        wait_for_row(present=False) via a step that expects the row gone.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def get_quantity_for(self, product_name: str) -> int:
        """The quantity in the row for `product_name`, as an integer.

        Scopes the quantity cell to the product's row: the quantity selector is
        relative to a row, so it is read via find_row_index_by_text plus the
        column family for that row.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        index = self.find_row_index_by_text(self.sel("cart_rows"), product_name)
        quantities = self.get_column_values(
            self.sel("cart_rows"),
            self.sel("cart_quantities"),
            0,
        )
        return int(quantities[index].strip())

    def is_empty(self) -> bool:
        """True once the cart is empty. WAITS, and times out if it is not.

        Reads the application's own 'Cart is empty!' message, which is rendered
        only when no rows remain. Call this only where emptiness is the
        expected answer — a step asking whether the cart is empty in order to
        branch would pay the full timeout every time the answer is no.
        """
        return self.is_showing(self.sel("empty_cart_message"))
