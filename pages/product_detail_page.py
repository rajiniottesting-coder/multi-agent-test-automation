"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the `product_detail` page in the app inventory; this file
never contains a literal selector string. Set INVENTORY_PAGE, then look each
element up with self.sel("<key>").

The add-to-cart control here is UNIQUE to this product (unlike the listing
page's family of 68), which is why cart scenarios add products from here. Adding
opens a MODAL that blocks the page underneath — a scenario adding a second
product from the same page must dismiss it (Continue Shopping) before the next
click, or that click lands on the overlay.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        The product name heading survives every state this page can be in — it
        is present before adding to cart, while the modal is open and after it
        is dismissed — so it is the reliable readiness probe.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as rendered in the information panel."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as 'Rs. 500'."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_visible(self) -> bool:
        """True once the add-to-cart confirmation modal is showing. WAITS."""
        return self.is_showing(self.sel("added_modal"))

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing this after adding does not update the cart, so it must be set
        first.
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear.

        The modal blocks the page underneath, so callers wanting to interact
        with the page again must dismiss it via continue_shopping().
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link to the cart page.

        Confirms arrival on the cart page, since a click can be consumed by an
        ad interstitial without navigating.
        """
        from pages.cart_page import CartPage

        self.click(self.sel("view_cart_link_in_modal"))
        CartPage(self.page).confirm_arrival()
