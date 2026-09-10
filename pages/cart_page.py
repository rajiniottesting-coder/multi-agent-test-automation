"""
CartPage — the shopping cart at /view_cart.

Selectors come from `pages.cart` in the app inventory. This page carries a
family of cart rows; each scenario in this batch acts on ONE product row by
name, so every method here scopes to the row containing the product name
rather than assuming a row index.

The cart PERSISTS against a registered account, so absolute assertions
(exact count, emptiness) are unsafe on a shared account. The methods here
therefore assert RELATIVELY — that a named product is present, or is gone —
which holds whatever the account started with.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart. Selectors: see `pages.cart` in the app inventory."""

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def view_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page.

        The path comes from the inventory, so it is never duplicated here.
        confirm_arrival() re-issues the navigation if an ad interstitial
        swallowed the first one.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def remove_product(self, name: str) -> None:
        """Remove the cart row for `name` via its delete control.

        Scopes to the row containing the product name — the delete control is
        a per-row family, so clicking it directly would be a strict-mode
        violation. After clicking, waits for the row to disappear so callers
        that immediately re-inspect the cart do not race the removal.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=True)
        self.click_in_row(
            self.sel("cart_rows"),
            name,
            self.sel("cart_delete_buttons"),
        )
        self.wait_for_row(self.sel("cart_rows"), name, present=False)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        Call this only where the cart page being loaded is the expected state.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)

    def wait_until_contains(self, name: str) -> None:
        """WAIT until a cart row for `name` is present; times out if it never is.

        Use to assert a product IS in the cart. It re-checks until the timeout,
        so it does not race the navigation or merge that put the product there.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=True)

    def wait_until_absent(self, name: str) -> None:
        """WAIT until no cart row for `name` is present; times out if one remains.

        Use to assert a product is NO LONGER in the cart. The waiting form is
        correct here because absence is what re-checking is watching for — a
        removal is still settling at the moment the assertion runs.
        """
        self.wait_for_row(self.sel("cart_rows"), name, present=False)

    def product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order.

        Reads the name column, not the row family, so each entry is a single
        product name rather than a whole concatenated row.
        """
        return self.get_all_texts(self.sel("cart_product_names"))
