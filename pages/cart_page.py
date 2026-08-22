"""
CartPage — the /view_cart shopping cart screen.

New page object for the cart-management feature. Style copied from
pages/login_page.py (the reserved reference):

  - SELECTORS COME FROM THE APP INVENTORY, never a literal string here.
    Set INVENTORY_PAGE, then use self.sel("<element_key>").
  - methods are business verbs (remove_product, reload_cart), not UI mechanics
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions
  - waiting predicates (is_empty) delegate to is_showing so a step can assert
    on them; non-waiting probes are named has_* / is_* and never wait

The cart carries persistent_state, so absolute assertions ('exactly one row',
'cart is empty') are only sound when the scenario owns its starting state
(fresh session / fresh account). This page object exposes both absolute
readers (assert_row_count, is_empty) and relative ones (has_product,
wait_for_product) so the step layer can pick the correct one.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class CartPage(BasePage):
    """Shopping cart. Selectors: see `cart` in the app inventory.

    cart_rows / cart_product_names / cart_delete_buttons are MULTI-MATCH
    families — never clicked or asserted on as a whole. Row-level actions are
    scoped to the row containing the product name via BasePage.click_in_row /
    wait_for_row / row_containing.
    """

    INVENTORY_PAGE = "cart"

    # ── navigation ───────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the /view_cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def reload_cart(self) -> None:
        """Full page refresh of the cart, then wait for it to settle."""
        self.reload()
        self.wait_for_page_load("domcontentloaded")

    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser is on the cart page; recover if a click was
        swallowed by an interstitial. Delegates to BasePage."""
        super().confirm_arrival(**params)

    # ── actions ──────────────────────────────────────────────
    def remove_product(self, product_name: str) -> None:
        """Remove the row whose description contains `product_name`.

        Scopes to the row containing the name and clicks its delete control,
        so it never touches the multi-match delete family as a whole.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    # ── queries: relative (safe on shared/persistent state) ──
    def product_names(self) -> List[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a row for `product_name` is present right now. Never waits.

        Non-waiting probe — safe to negate for an 'is gone' assertion.
        """
        return product_name in self.product_names()

    def wait_for_product(self, product_name: str, present: bool = True) -> None:
        """Wait until a row containing `product_name` is present, or is gone.

        Use present=True after adding, present=False after removing. Re-checks
        until the timeout rather than snapshotting the list once.
        """
        self.wait_for_row(self.sel("cart_rows"), product_name, present=present)

    def get_row_text(self, product_name: str) -> str:
        """The full concatenated text of the row containing `product_name`.

        A cart row includes the name, price, quantity and total, so this is
        used with containment checks (`"Rs. 500" in row_text`), never with
        equality against a single field.
        """
        return self.row_containing(self.sel("cart_rows"), product_name).inner_text().strip()

    # ── queries: absolute (only when the scenario owns the state) ──
    def row_count(self) -> int:
        """Number of product rows currently in the cart. Snapshot, no wait.

        For READING a count only. To ASSERT a count use assert_row_count,
        which waits for the table to settle after an add/remove.
        """
        return self.get_count(self.sel("cart_rows"))

    def assert_row_count(self, expected: int) -> None:
        """Wait until exactly `expected` product rows are present.

        Waits rather than snapshotting because the moment worth counting is
        right after an add or remove, when the table is still updating.
        """
        self.wait_for_count(self.sel("cart_rows"), expected)

    def is_empty(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart shows its 'Cart is empty!' message. WAITS for it,
        and times out if the message never appears.

        Call this only where emptiness is the EXPECTED answer (e.g. after the
        last item is removed). A step asking 'is it empty?' to branch on the
        reply would pay the full timeout every time the answer is no — use
        has_product / row_count for that instead.
        """
        return self.is_showing(self.sel("empty_cart_message"), timeout_ms=timeout_ms)

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the cart table is on screen. WAITS for it.

        The cart table survives whether the cart has rows or not, so it is a
        state-independent readiness signal — unlike the empty-cart message,
        which is present in only one of the two states.
        """
        return self.is_showing(self.sel("cart_table"), timeout_ms=timeout_ms)
