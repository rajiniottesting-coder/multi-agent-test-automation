"""
CartPage — the shopping cart at /view_cart.

New page object for the shopping-session feature. Responsibilities:
  - read the rows currently in the cart (product names)
  - remove one product's row by name
  - detect the empty-cart state
  - assert an exact row count after a mutation

Conventions (see pages/login_page.py for the worked reference):
  - selectors come from the app inventory via self.sel("<key>"); never a literal
  - methods are business verbs that name what they act on
  - query methods a test asserts on are built on WAITING probes (is_showing)
  - family selectors (cart_rows, cart_product_names, cart_delete_buttons) are
    read with get_all_texts and acted on one member at a time via
    click_in_row() / find_row_index_by_text() scoped to the product name;
    they are NEVER clicked, filled or asserted on as a whole (strict mode)

The cart PERSISTS against a registered account across logout and across runs,
so ABSOLUTE assertions (empty / exact count) are only sound when the scenario
owns its starting state.

App: https://automationexercise.com

BASEPAGE-REQUEST: wait_for_count(locator, expected) - wait until a family
locator resolves to an exact number, retrying to tolerate a page still
settling after a mutation. Not present in the injected helper list, so the
exact-count assertion is currently done by scoping to the product row and by
reading get_row_count() defensively; a promoted wait_for_count would let
assert_row_count() retry properly.
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory.

    The cart PERSISTS against a registered account across logout and across
    runs, so an ABSOLUTE assertion (empty / exact count) is only sound when the
    scenario owns its starting state. Prefer relative checks (the product this
    test added is present / is gone) otherwise.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the row for `product_name` via its 'X' control.

        Scopes to the row that contains the product name, then clicks the
        delete control INSIDE that row — never the family as a whole, which
        would raise a strict-mode violation. Removal happens without a page
        navigation.
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

    def get_product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order.

        Reads the cart_product_names family with get_all_texts, so it is the
        right reader for asserting a product IS present without indexing.
        """
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present in the cart.

        Uses find_row_index_by_text, which scopes across the cart_rows family
        without clicking or asserting on it as a whole.
        """
        return self.find_row_index_by_text(self.sel("cart_rows"), product_name) != -1

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart (a snapshot read).

        Delegates to BasePage.get_row_count(), which is a snapshot with no
        retry. For asserting a number after a change, prefer waiting on the
        empty-state message (is_empty) or on the product's own presence
        (has_product), which do wait.
        """
        return super().get_row_count(self.sel("cart_rows"))

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        This is an ABSOLUTE empty-state assertion: only call it when the
        scenario owns its starting state (fresh account or a cart it cleared).
        The empty-state text and product rows are mutually exclusive — exactly
        one is present at any moment — so waiting on the message is the correct
        way to confirm a removal completed without a page navigation.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
