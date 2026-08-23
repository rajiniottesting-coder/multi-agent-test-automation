"""
CartPage — the shopping cart at /view_cart.

Selectors come from the app inventory (`pages.cart`). This page carries
persistent state: the cart is stored against the signed-in account and
survives logout and the run, so an ABSOLUTE emptiness assertion is honest
only when the scenario owns its starting state (via empty_the_cart()) or
removes exactly what it added.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, product_name: str) -> None:
        """Remove the row for a named product.

        Scopes to the row that contains the product name and clicks the delete
        control inside it — never the delete family as a whole, which matches
        one control per row. Removal re-renders the table in place; there is
        no navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        # Wait for the row to actually disappear before returning.
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so an ABSOLUTE assertion afterwards is honest:
        the scenario put the empty state there itself. The row list re-renders
        after each removal, so re-read it every iteration rather than caching a
        count.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            self.wait_for_count(
                self.sel("cart_rows"),
                self.get_count(self.sel("cart_rows")) - 1,
            )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def has_product(self, product_name: str) -> bool:
        """True once a row for the named product is present. WAITS for it.

        Call this only where the product is EXPECTED. To assert a product is
        gone, use wait_for_row(present=False) via a step that removed it, not a
        negation of this waiting predicate.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)
        return True

    def product_names(self) -> list[str]:
        """Every product name currently in the cart, in order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS for it,
        and times out if the cart is not empty.

        Call this only where emptiness is the expected answer — after a removal
        in a scenario that owns its starting state. A step asking "is it empty?"
        to branch on the reply would pay the full timeout every time the answer
        is no. The empty-state message and the row list are mirrors: exactly one
        is present at any moment, so this waiting probe is the right reader for
        the absence-of-rows condition.
        """
        return self.is_showing(self.sel("empty_cart_message"))
