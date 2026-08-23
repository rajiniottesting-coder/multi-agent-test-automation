"""
ProductDetailPage — a single product's detail screen.

Selectors: see `product_detail` in the app inventory. This page renders one
product (the URL carries the product id), so its Add to cart control is unique
here — unlike the listing page's family of 68. That is why the shopping and
cart-persistence scenarios add from here.

Adding to cart opens a MODAL rather than navigating. The modal blocks the page
underneath, so it must be dismissed (Continue Shopping) or followed (View Cart)
before anything else on the page can be touched.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: `product_detail` inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for this product and wait for the modal to open.

        The modal is the confirmation that the add succeeded, and it blocks the
        page underneath, so callers must then either dismiss it with
        continue_shopping() or follow it with view_cart_from_modal().
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, and
        before adding a second product, because the modal intercepts clicks.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link through to the cart page.

        This leaves the product detail page, so it does not confirm arrival
        here — the CartPage confirms its own arrival.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name, which is present in every state this page can
        be in (the add-to-cart modal is an overlay, not a replacement).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible name of the product this page is showing. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible price of the product, e.g. 'Rs. 500'. WAITS for it.

        Rendered with its currency prefix; assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_modal_showing(self) -> bool:
        """True if the add-to-cart modal is on screen right now. Never waits.

        Non-waiting so it can be negated to assert the modal was dismissed
        without paying a timeout when it is legitimately gone.
        """
        return self.is_visible(self.sel("added_modal"))
