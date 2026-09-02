"""
CartPage — the /view_cart shopping cart screen.

Selectors: see `pages.cart` in the app inventory. This page object exposes ONLY
relative assertions — that a product row is present or gone — because the cart
persists against the signed-in account across logout and across runs. A
scenario reusing the shared 'registered' account inherits whatever a previous
run left behind, so an absolute row count is not safe here unless the scenario
owns its starting state (a fresh account, or an explicit clear). None of the
scenarios in this batch own that state, so no count/emptiness reader is
provided.

App: https://automationexercise.com
"""
import logging
from typing import Optional

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """Shopping cart at /view_cart. Selectors: see `pages.cart` in the inventory.

    `cart_rows` is the repeating row container (a MULTI-MATCH family). Never
    click or assert on it as a whole — scope to the row that contains the
    product name, or wait for a named row to appear or disappear.
    """

    INVENTORY_PAGE = "cart"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Probes the cart_table container, which is present whether the cart has
        rows or is empty — a state-independent readiness signal for this page.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_for_product_row(self, product_name: str, present: bool = True) -> None:
        """Wait until a cart row containing `product_name` is there, or is gone.

        WAITS. Use present=True after adding a product and present=False after
        removing one. Re-checks until the timeout rather than snapshotting the
        row list, because the moment worth checking is right after the action
        that changed the cart, while the page is still settling.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Delete the cart row for `product_name` via its 'x' control.

        Scopes to the row that contains the product name rather than indexing
        across the delete-button family, so the correct row is removed even if
        the two families do not run in lockstep.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )
