"""
ProductDetailPage — the /product_details/{product_id} screen for a single product.

One page per product. Reach it by clicking a product's View Product link on the
listing (that href already carries the id), or open it directly with a known id.

Selectors: see `pages.product_detail` in the app inventory. This file holds NO
literal selectors — every element is looked up via self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Single-product detail page. Selectors: see `pages.product_detail`."""

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: str) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page via the listing's View Product link, which
        already carries the id; this is the fallback for a known product id.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product; the add-to-cart modal opens.

        The modal blocks the page underneath, so dismiss or navigate from it
        before interacting with the page again.
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
        """Navigate to the cart from inside the add-to-cart modal."""
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element here: it is
        present on every product's detail page regardless of cart or review
        state, so it is a reliable readiness signal.
        """
        return self.is_showing(self.sel("product_name"))

    def product_name(self) -> str:
        """The displayed product name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The displayed price, e.g. 'Rs. 500'. WAITS for it to appear.

        Rendered with a currency prefix; assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))
