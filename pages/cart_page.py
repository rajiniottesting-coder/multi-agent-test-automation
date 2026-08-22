"""
CartPage — the /view_cart shopping-cart screen.

Reads and manipulates the cart table: product rows, per-row delete controls,
reload / navigate-back helpers, and the empty-cart assertion.

Selector keys come from `pages.cart` in the app inventory; this file never
holds a literal selector. The cart is per-session/account and PERSISTS across
logout and across runs (see the inventory's persistent_state note), so absolute
count / emptiness assertions are only safe for a scenario that owns its
starting state — a fresh browser session, as the SCRUM-125/126/127 scenarios
require.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory.

    The cart_rows / cart_product_names / cart_delete_buttons keys are all
    families (multi_match): read them with the plural helpers, and act on a
    single row by scoping to the product name it contains.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the View Cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart page; recover if an ad ate the click."""
        super().confirm_arrival(**params)

    def reload_cart(self) -> None:
        """Full page refresh of the current cart page."""
        self.reload()

    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` via its own 'X' control.

        Scopes to the row containing the product name so the correct member of
        the delete-button family is clicked, avoiding a strict-mode violation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order.

        Snapshot reader — use it to inspect membership, not to wait for a row
        to arrive or disappear (use wait_for_product / assert_row_count).
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until a row containing `product_name` is present (or gone).

        Use present=True after adding, present=False after removing — it
        re-checks until the timeout, unlike a one-shot list read.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are in the cart.

        Safe here because the cart is owned by this scenario's fresh session;
        waits rather than snapshotting so a count taken right after an
        add/remove does not read the pre-update value.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def row_text_for(self, product_name: str) -> str:
        """The full text of the cart row containing `product_name`.

        Returns the concatenated row text (name, price, quantity, total), so
        assert containment of a price/quantity value against it rather than
        equality.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def is_empty(self) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS, and times
        out if it is not.

        Call this only where an empty cart is the EXPECTED answer — it is the
        mirror of a populated cart and waits for the empty-state text to
        render. A step branching on cart contents should not use it, because
        it pays the full timeout whenever the cart is not empty.
        """
        return self.is_showing(self.sel("empty_cart_message"))
