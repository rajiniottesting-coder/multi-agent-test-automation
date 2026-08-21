"""
CartPage — the shopping cart at /view_cart.

Selectors live in the app inventory under `pages.cart`; this file never writes
a literal selector and never invents an inventory key. Methods are business
queries and actions:

  - inspect a row BY PRODUCT NAME rather than by index (rows come and go)
  - read a product's price from its own row
  - remove a product by scoping the delete control to its row
  - answer emptiness with a WAITING probe (empty_cart_message), so a step can
    assert the cart is empty

`cart_rows`, `cart_product_names` and `cart_delete_buttons` are all MULTI-MATCH
families (see the inventory's `multi_match`). Playwright runs strict, so this
file never clicks, waits on, or asserts against those keys as a whole. To touch
ONE row it scopes by the product's text via `click_in_row` / `row_containing`;
to count it uses the family-aware readers only for READING, never as a wait.

The cart persists for a registered account across runs, so absolute-emptiness
claims are only valid when the scenario owns its starting state. SCRUM-118 owns
it: it adds exactly one product and removes that same product, so asserting the
cart is empty afterwards is legitimate.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The table container is a single element (not a family) and is present
        whether the cart has rows or not, so it is a stable readiness signal
        for either state.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def has_product(self, product_name: str) -> bool:
        """True if a cart row contains the given product name.

        Scopes to the row by text rather than touching the `cart_rows` family
        directly, so no strict-mode violation is possible.
        """
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) != -1

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in row order.

        `cart_product_names` is a family; get_all_texts is the plural reader
        that is legal on it.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def get_row_price(self, product_name: str) -> str:
        """The full text of the row for the given product.

        Returns the row's concatenated text (id, description, price, quantity,
        total), because the inventory has no cell-scoped price key for the
        cart. Assert on the price as a SUBSTRING, e.g.
        `"Rs. 500" in cart_page.get_row_price("Blue Top")`.
        """
        row = self.row_containing(self.sel("cart_rows"), product_name)
        return row.inner_text().strip()

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart.

        A snapshot read (family-aware), for READING a number rather than
        waiting on a change. Do NOT use this to assert a count that just
        changed — assert emptiness via is_empty() or presence via has_product().
        """
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        The empty-state message and the product rows are mutually exclusive —
        exactly one is present at any moment — so this is the reliable way to
        assert the cart is empty. empty_cart_message is a single element, not a
        family, so waiting on it is safe. Only valid when the scenario owns its
        starting state (SCRUM-118 does).
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the row for the given product by clicking its delete control.

        Scopes the delete control to the row containing the product name, so it
        never depends on a row index and never touches the delete-button family
        as a whole.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
