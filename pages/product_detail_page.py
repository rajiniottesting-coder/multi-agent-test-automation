"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors: see `pages.product_detail` in the app inventory. No selector
literals live here — every element is looked up by its inventory KEY via
self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A single product's detail page.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the product id), or opened directly via page_url(product_id=...).
    Its Add to cart control is unique — unlike the listing's family of 68 — which
    is why cart scenarios add products from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal to appear.

        Adding opens a MODAL rather than navigating; it blocks the page
        underneath, so the caller must dismiss it (continue_shopping) or use it
        to navigate (view_cart_from_modal) before touching the page again.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, because
        the modal blocks it. Waits for the modal to disappear.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Navigates to /view_cart, and proves the modal appeared on the way.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_showing_product(self, product_name: str, timeout_ms: Optional[int] = None) -> bool:
        """True once THIS page is showing the given product's detail. WAITS.

        Call this only where arrival on the product page is the expected
        outcome; it waits up to the timeout for the product name to render and
        times out rather than returning False if it never does.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms) and (
            product_name.lower() in self.product_name().lower()
        )

    def product_name(self) -> str:
        """The product's name as shown in the product information block."""
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as 'Rs. 500'. Assert on the number."""
        return self.get_text(self.sel("product_price"))
