"""
CartPage — the /view_cart shopping cart screen.

Selectors come from `pages.cart` in the app inventory; this file uses
self.sel("<key>") and never a literal selector.

The cart persists against a signed-in account (see the inventory's
persistent_state_note), so this page object offers only RELATIVE assertions —
that a named row is present, or is gone — never an absolute count. A scenario
wanting an absolute count would have to own its starting state, which none of
the scenarios in this batch do.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart_page(self, base_url: str) -> None:
        """Navigate directly to the cart, then confirm the browser arrived.

        confirm_arrival() re-issues the navigation if an ad interstitial
        swallowed it — free and silent on an ordinary run.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, name: str) -> None:
        """Remove the cart row for `name` by clicking its delete control.

        Scopes to the row that contains the product name rather than indexing
        a family, so it is safe even if the delete-button family and the
        row family do not run in strict lockstep.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("cart_rows"),
            name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries ──────────────────────────────────────────────
    def has_product_row(self, name: str) -> bool:
        """True once a cart row containing `name` is present. WAITS for it.

        Call this only where the row is EXPECTED. It waits for the row to
        appear and times out if it never does, so it cannot be used to assert
        absence — use wait_until_product_removed for that.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=True)
        return True

    def wait_until_product_removed(self, name: str) -> bool:
        """True once no cart row contains `name`. WAITS for the row to go.

        The correct absence check here: it re-checks until the row is gone
        rather than looking once right after the removal, when the table may
        still be settling.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=False)
        return True
