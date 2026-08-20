"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from `pages.product_detail` in the app inventory; this file
holds no literal selector strings. Adding to cart opens a MODAL rather than
navigating, and that modal blocks the page underneath, so the two ways out of
it — Continue Shopping (dismiss, stay here) and View Cart (navigate away) —
are both exposed as methods.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`.

    The URL is a template (one page per product), so navigation takes a
    product_id. Reaching it by clicking a listing's View Product link is
    preferred — that href already carries the id — but open_product() is here
    for direct access.
    """

    INVENTORY_PAGE = "product_detail"

    # ── navigation ───────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id."""
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear.

        Waiting for the modal here means callers can immediately choose how to
        leave it without racing the modal's render.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath — the
        modal blocks it. Waits for the modal to disappear so the next click
        does not land on a fading overlay.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal, navigating to the cart."""
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The product name is state-independent for this page — unlike the modal
        or review success, which appear only after an interaction — so it is
        the reliable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown on the detail page."""
        return self.get_text(self.sel("product_name"))

    def has_added_modal(self) -> bool:
        """True if the add-to-cart confirmation modal is showing right now.

        Non-waiting probe, for asserting the modal was dismissed. Using the
        waiting reader for that would time out instead of returning False.
        """
        return self.is_visible(self.sel("added_modal"))
