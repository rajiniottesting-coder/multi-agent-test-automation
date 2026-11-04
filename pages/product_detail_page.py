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

    def has_quantity_input(self) -> bool:
        """True once the quantity input is on screen. WAITS for it.

        A waiting presence predicate — call it only where the field IS expected.
        To assert the field has been REMOVED, use is_quantity_input_absent(),
        which does not wait for a presence that will never happen.
        """
        return self.is_showing(self.sel("quantity_input"))

    def is_quantity_input_absent(self) -> bool:
        """True once the page is loaded AND the quantity input is NOT on it.

        For the story that removed the quantity field. quantity_input is a
        PERMANENT inventory element (not listed under `conditional`), so an
        absence check alone would also pass before the page had rendered or on
        the wrong page entirely. Proving is_loaded() first anchors the absence
        to this product page. is_gone() returns True at once when the element is
        absent, waiting only while it is still shown.
        """
        return self.is_loaded() and self.is_gone(self.sel("quantity_input"))

    # ── review: queries ──────────────────────────────────────
    def has_review_form(self) -> bool:
        """True once the Write Your Review form is on screen. WAITS for it.

        A waiting predicate for asserting the form IS present. Probes the
        review form element, which is always rendered on a product details
        page regardless of sign-in state.
        """
        return self.is_showing(self.sel("review_form_element"))

    def get_review_success(self) -> str:
        """The review thank-you message text. WAITS for it to appear.

        Only call this when the confirmation IS expected. To assert that NO
        confirmation is shown, use is_review_success_absent(), which does not
        wait for a presence that will never happen.
        """
        self.wait_visible(self.sel("review_success"))
        return self.get_text(self.sel("review_success"))

    def is_review_success_absent(self) -> bool:
        """True once the review confirmation is NOT shown. For absence checks.

        review_success is a CONDITIONAL element — it exists only after a review
        submits successfully — so when the form was rejected by the browser's
        own required-field validation it never renders. is_gone() returns True
        at once when the element is absent, waiting only while it is still
        shown, so an incomplete submission is confirmed without paying a full
        presence timeout.
        """
        return self.is_gone(self.sel("review_success"))

    # ── review: actions ──────────────────────────────────────
    def submit_review(self, name: str, email: str, text: str) -> None:
        """Fill the Write Your Review form and click Submit.

        Confirms it is ON this page first. Filling a field that is not there
        would wait the full timeout and then blame the field's locator rather
        than the wrong page.

        Fills whatever values it is given, including empty strings: the
        negative scenarios leave a required field blank on purpose, so the
        browser's own validation blocks the submission and no confirmation
        renders. Scoped by placeholder, so each of Name / Email / Review maps
        to exactly one field.
        """
        self.require_own_page()
        self.scroll_into_view(self.sel("review_form_element"))
        self.fill(self.sel("review_name_input"), name)
        self.fill(self.sel("review_email_input"), email)
        self.fill(self.sel("review_textarea"), text)
        self.click(self.sel("review_submit_button"))

    # ── cart: actions ────────────────────────────────────────
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
