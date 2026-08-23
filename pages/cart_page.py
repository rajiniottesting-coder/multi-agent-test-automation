"""
CartPage — the shopping cart at /view_cart.

Selectors come from the `cart` page in the app inventory. This page carries
persistent state: the cart is stored against the signed-in account and
survives logout and the run, so a scenario asserting an ABSOLUTE state (an
exact row count, or emptiness) must first own that state by calling
empty_the_cart(). See the inventory's persistent_state_note.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `cart` in the app inventory.

    The cart_rows / cart_product_names / cart_delete_buttons keys are all
    MULTI-MATCH families: read them with the plural helpers, and act on ONE
    member by scoping to the row that contains a product name.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def empty_the_cart(self) -> None:
        """Remove every entry, leaving the cart genuinely empty.

        Bind this to a Given so an ABSOLUTE assertion afterwards is honest:
        the scenario put the empty state there itself. The row list
        re-renders after each deletion, so re-read the count every pass
        rather than caching it. get_count() (a non-waiting snapshot) is
        correct here — this is BRANCHING on optional state, not an assertion,
        and waiting for a legitimately empty cart would cost a full timeout.
        """
        while self.get_count(self.sel("cart_rows")) > 0:
            current = self.get_count(self.sel("cart_rows"))
            self.click_nth(self.sel("cart_delete_buttons"), 0)
            self.wait_for_count(self.sel("cart_rows"), current - 1)

    def remove_product(self, product_name: str) -> None:
        """Delete the row for a named product.

        Scopes to the row containing the product name, so it acts on exactly
        one delete control rather than the whole family.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Return every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until the cart holds exactly `expected` product rows.

        Waits rather than snapshotting: the moment worth counting is right
        after a removal or addition, when the table is still re-rendering.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until a row for `product_name` is present, or is gone."""
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def is_empty(self) -> bool:
        """True once the cart shows its empty-state message. WAITS, and times
        out if the cart is not empty.

        Call this only where emptiness is the EXPECTED answer — the scenario
        must own its starting state first (see empty_the_cart), or a leftover
        from a previous run makes this time out. A step asking "is it empty?"
        to branch on the reply would pay the full timeout every time the
        answer is no; branch on has_products() for that.
        """
        return self.is_showing(self.sel("empty_cart_message"))

    def has_products(self) -> bool:
        """True once at least one product row is present. WAITS for a row to
        appear, and times out if none ever does.

        Call this only where products ARE expected — e.g. asserting that a
        product survived a page load — so the wait resolves on the expected
        case. Built on wait_for_any(), which retries until the timeout and
        logs the reason it gave up, rather than get_count(), which snapshots
        once and races a still-settling table. For BRANCHING on whether the
        cart happens to have rows (where waiting on an empty cart would cost a
        full timeout), inspect get_product_names() instead — that does not
        wait.
        """
        try:
            self.wait_for_any(self.sel("cart_rows"), present=True)
            return True
        except Exception:
            return False
