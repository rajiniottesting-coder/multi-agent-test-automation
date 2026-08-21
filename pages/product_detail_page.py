"""
ProductDetailPage — a single product's detail page (/product_details/{id}).

Selectors: see `product_detail` in the app inventory. Never a literal here.

This page is where cart scenarios add products: unlike the listing page, whose
Add to cart control matches 68 elements, this page has exactly ONE add-to-cart
button, so adding from here is unambiguous. Adding opens a MODAL rather than
navigating; the modal blocks the page underneath, so a scenario adding a second
product from the same page must dismiss it first via continue_shopping().
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail screen. Selectors: see `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click the single Add to cart button for this product.

        Opens the add-to-cart modal rather than navigating. Wait for the modal
        with wait_for_added_modal() before acting on the page again.
        """
        self.click(self.sel("add_to_cart_button"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath — the
        modal blocks it, so the next click would land on the overlay otherwise.
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link, landing on the cart page.

        Proves the modal appeared and navigates to /view_cart in one step.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state of this page, so it is a
        state-independent readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible product name (e.g. 'Blue Top'). WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price, rendered as 'Rs. 500'. WAITS for it.

        Assert on the number within, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def wait_for_added_modal(self) -> bool:
        """True once the add-to-cart modal is showing. WAITS for it.

        Only call after add_to_cart(). The modal is conditional and absent from
        a freshly loaded page.
        """
        return self.is_showing(self.sel("added_modal"))
