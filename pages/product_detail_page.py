"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the app inventory (`product_detail` page). This object
reads the product name, sets quantity, adds the product to the cart (which
opens a blocking modal), and offers both ways out of that modal: navigate to
the cart or dismiss it and stay on the product.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (one product per page), unlike the
    listing page's family of 68 controls — which is why cart scenarios add a
    product from here. Adding opens a modal that blocks the page underneath, so
    a scenario touching the page again must dismiss it first.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it.

        The product name is present in every state this page can be in, so it
        is a reliable readiness probe.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name from the detail heading. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Add THIS product to the cart and wait for the modal to appear.

        Adding does not navigate — it opens a blocking modal. Waiting for the
        modal here means callers can act on it immediately.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Click 'View Cart' inside the add-to-cart modal to go to the cart.

        Prefer this over the nav Cart link right after adding a product: it
        also proves the modal appeared. The click leaves this page, so
        arrival at the cart is the caller's concern.
        """
        self.click(self.sel("view_cart_link_in_modal"))
