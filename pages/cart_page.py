"""
CartPage — the shopping cart at /view_cart.

Selectors: see `pages.cart` in the app inventory. Every lookup goes through
self.sel("<key>"); no selector literals live in this file.

The cart is scoped to the current session or account, so asserting on the
specific product a test added is reliable. Presence of a named product is
read with the plural family helpers; the empty-cart state is asserted with the
app's own empty-cart message via a non-waiting probe (its mirror, cart_rows,
is a MULTI-MATCH family and must never be clicked, filled or waited on as a
whole).

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class CartPage(BasePage):
    """View Cart. Selectors: see `pages.cart` in the app inventory.

    The row, product-name and delete-button keys are MULTI-MATCH families —
    one member per cart row. Never click, fill or assert on them as a whole;
    scope to the row containing the product's name with click_in_row(), or
    read the whole family with the plural helpers.
    """

    INVENTORY_PAGE = "cart"

    # ── actions ──────────────────────────────────────────────
    def open_cart(self, base_url: str) -> None:
        """Navigate directly to the cart page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def remove_product(self, product_name: str) -> None:
        """Delete the row whose description contains `product_name`.

        Scopes to the row containing the product name and clicks the delete
        control inside it, so the MULTI-MATCH delete family is never clicked
        directly. Removal happens in place with no page navigation.
        """
        self.click_in_row(
            self.sel("cart_rows"),
            product_name,
            self.sel("cart_delete_buttons"),
        )

    def proceed_to_checkout(self) -> None:
        """Click the Proceed To Checkout control."""
        self.click(self.sel("proceed_to_checkout_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the cart table is on screen. WAITS for it."""
        return self.is_showing(self.sel("cart_table"))

    def get_product_names(self) -> list[str]:
        """Every product name currently in the cart, in DOM order."""
        return self.get_all_texts(self.sel("cart_product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a cart row's description contains `product_name`."""
        return any(product_name in name for name in self.get_product_names())

    def get_row_text_for(self, product_name: str) -> str:
        """Full text of the cart row containing `product_name`.

        Returns the whole row — description, price, quantity and total —
        concatenated, so callers assert containment rather than equality.
        WAITS for the row to be present.
        """
        return self.row_containing(
            self.sel("cart_rows"), product_name
        ).inner_text().strip()

    def get_row_count(self) -> int:
        """Number of product rows currently in the cart."""
        return self.get_count(self.sel("cart_rows"))

    def is_empty(self) -> bool:
        """True if the cart shows its own 'Cart is empty!' message.

        Non-waiting probe on the app's empty-state indicator, which is the
        mirror of the cart rows — exactly one of the two is present at any
        moment. Using this rather than counting rows keeps the assertion and
        the app behaviour from drifting apart.
        """
        return self.is_visible(self.sel("empty_cart_message"))
