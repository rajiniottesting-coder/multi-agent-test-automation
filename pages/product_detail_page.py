"""
ProductDetailPage — a single product's details page.

One page per product (URL is a template keyed by product id). The cart
scenarios reach it by clicking a product's View Product link on the listing,
so the id never has to be invented here.

Adding to cart opens a MODAL rather than navigating; it blocks the page
underneath, so a scenario adding a product twice MUST dismiss the modal with
Continue Shopping between additions, or the second Add to cart click lands on
the overlay.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A product details page. Selectors: see `product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── readiness ────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The name heading survives every state this page can be in (modal open
        or closed, review submitted or not), so it is a stable readiness probe.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """The displayed product name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The displayed price text, e.g. 'Rs. 500'. WAITS for it to appear."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def availability_label(self) -> str:
        """The Availability label text. WAITS for it to appear.

        Used to assert the label is present; the inventory exposes no separate
        cell for its value, so callers assert on the label itself.
        """
        self.wait_visible(self.sel("availability"))
        return self.get_text(self.sel("availability"))

    def condition_label(self) -> str:
        """The Condition label text. WAITS for it to appear."""
        self.wait_visible(self.sel("condition"))
        return self.get_text(self.sel("condition"))

    def brand_label(self) -> str:
        """The Brand label text. WAITS for it to appear."""
        self.wait_visible(self.sel("brand"))
        return self.get_text(self.sel("brand"))

    def has_availability_label(self) -> bool:
        """True once the Availability label is on screen. WAITS for it.

        A waiting predicate: call it only where the label is expected to be
        present, which is every detail page this app serves.
        """
        return self.is_showing(self.sel("availability"))

    def has_condition_label(self) -> bool:
        """True once the Condition label is on screen. WAITS for it."""
        return self.is_showing(self.sel("condition"))

    def has_brand_label(self) -> bool:
        """True once the Brand label is on screen. WAITS for it."""
        return self.is_showing(self.sel("brand"))

    def current_quantity(self) -> str:
        """The current value typed in the quantity field (DOM value, not text)."""
        return self.get_input_value(self.sel("quantity_input"))

    def has_add_to_cart_control(self) -> bool:
        """True once the Add to cart control is on screen. WAITS for it.

        A waiting predicate: call it only where the control is expected to be
        present. Lets a scenario prove the detail page offers add-to-cart
        before acting on it.
        """
        return self.is_showing(self.sel("add_to_cart_button"))

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the quantity BEFORE adding to cart.

        Changing the quantity after adding does not update the cart, so this
        must be called before add_to_cart().
        """
        self.require_own_page()
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal.

        The add-to-cart control is unique on this page (unlike the listing's
        family of 68), so clicking it directly is safe. Waiting for the modal
        proves the addition registered before the caller moves on.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required between two additions of the same product, because the modal
        blocks the page underneath. Waits for the modal to disappear so the
        next click reaches the page rather than the overlay.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart(self) -> None:
        """Click View Cart in the add-to-cart modal, navigating to the cart.

        Confirming arrival is delegated to the destination page object by the
        caller; this only follows the link out of the modal.
        """
        self.click(self.sel("view_cart_link_in_modal"))
