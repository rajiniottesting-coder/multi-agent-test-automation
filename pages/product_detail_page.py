"""
ProductDetailPage — a single product's detail screen (/product_details/<id>).

Selectors: see `pages.product_detail` in the app inventory. This page carries
the unique, per-product Add to cart control (unlike the listing page's family
of buttons), so a cart scenario adds the product from here. Adding opens a
MODAL that blocks the page underneath; leave it via View Cart, which both
proves the modal appeared and navigates to the cart.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail. Selectors: see `pages.product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Return the visible product name for this detail page."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click this product's Add to cart control and wait for the modal.

        Waits for the confirmation modal so the caller knows the item was
        added before it interacts with the modal's buttons.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to navigate to the cart.

        Preferred over the nav Cart link right after adding: it also proves the
        modal appeared and clears the blocking overlay.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
