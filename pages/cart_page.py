"""
CartPage — the /view_cart shopping-cart screen.

Selectors come from `pages.cart` in the app inventory; never a literal here.

The cart is PERSISTENT per account and survives logout and the run, so an
absolute assertion (exactly-one-row, empty) is only sound when the scenario
owns its starting state. remove_product() plus wait-based readers let a
scenario verify what IT added and what IT removed relatively, which holds
whatever the account started with.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory.

    cart_rows / cart_product_names / cart_delete_buttons are MULTI-MATCH
    families — one member per product row. Never click or assert on the family
    as a whole; scope to the row containing the product name instead.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the View Cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached the cart page; recover if an ad ate the
        navigation. Called by other page objects after clicking through to here."""
        super().confirm_arrival(**params)

    def remove_product(self, product_name: str) -> None:
        """Click the delete control on the row for `product_name`.

        Scopes to the row containing the product name rather than indexing the
        delete-button family, so a doubled or reordered table cannot delete the
        wrong row. Removal is in-place — there is no page navigation.
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

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True right now if a row for `product_name` is present. Does NOT wait.

        Non-waiting, so it is safe to NEGATE for an absence check. To assert a
        product IS there after adding it, prefer wait_until_product_present,
        which waits out the table settling.
        """
        return product_name in self.get_product_names()

    def wait_until_product_present(self, product_name: str) -> None:
        """WAIT until a row containing `product_name` exists. Times out if not.

        Call this only where the product is expected — right after adding it,
        when the table may still be rendering. Do not negate it for absence:
        it can answer 'no' only by exhausting its timeout.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=True)

    def wait_until_product_removed(self, product_name: str) -> None:
        """WAIT until no row contains `product_name`. Times out if it lingers.

        The waiting form of an absence check, for right after a removal when
        the table is still settling. Re-checks until the row is gone.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=False)

    def row_text_for(self, product_name: str) -> str:
        """Full text of the cart row containing `product_name`.

        The row concatenates every column — product, price, quantity, total —
        so assert containment (price or quantity `in` this text), never `==`.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    def assert_row_count(self, expected: int) -> None:
        """WAIT until exactly `expected` product rows are present.

        Sound only when the scenario owns the cart's starting state, since the
        cart persists per account. Uses wait_for_count so a still-settling
        table after add/remove is not counted early.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Cart is empty!' message is shown. WAITS for it.

        Call this only where emptiness is the EXPECTED answer — it can report
        'not empty' only by timing out. Asserting emptiness is asserting an
        ABSOLUTE state, so the scenario must have owned its starting cart
        (a fresh account, or a prior clear) for this to be meaningful.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)
