"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory; this file never carries
a literal selector. Methods read as shopper intent (open_cart, remove_product)
and every one delegates to a BasePage helper.

The cart is a MULTI-MATCH heavy page: rows, product names and delete buttons
are all families. Acting on ONE product means scoping to the row that contains
its name with click_in_row(), never indexing across families.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory.

    ABSOLUTE emptiness is only assertable when the scenario owns its starting
    state (the cart persists per account across runs). Prefer the relative
    checks — that a named product IS present, or is GONE — which hold whatever
    the account started with.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the /view_cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` via its own 'X' control.

        Scopes to the row containing the name, so the correct delete button is
        clicked even though the delete controls are a family. Removal happens
        in place with no navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart table container, which is present whether the cart has
        rows or is empty, making it a state-independent readiness signal.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Visible names of every product currently in the cart, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until the row for `product_name` is present, or is gone.

        Pass present=False after a removal — it waits for the row to leave and
        returns the moment it does, instead of snapshotting a still-settling
        list.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are shown.

        Waits rather than snapshots, because the moment worth counting is right
        after an add or a remove, when the table is still updating.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def row_text_for(self, product_name: str) -> str:
        """The full text of the row containing `product_name`.

        Returns the concatenated row (name, price, quantity, total), so assert
        containment against it — e.g. that 'Rs. 500' is in the row — never
        equality against a single field.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS, and times
        out if it is not.

        Call this only where emptiness is the EXPECTED answer, and only when
        the scenario owns its starting state — the cart persists per account,
        so a leftover item from a prior run makes this legitimately false. A
        step asking "is it empty?" to branch on the reply would pay the full
        timeout every time the answer is no.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
