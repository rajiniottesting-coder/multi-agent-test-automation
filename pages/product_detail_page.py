"""
ProductDetailPage — the /product_details/{product_id} screen for a single product.

Selectors come from the app inventory (`pages.product_detail`), never from a
literal in this file. Methods are business verbs that name what they act on.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A single product's detail page. Selectors: see `pages.product_detail`.

    The add-to-cart control here is UNIQUE (unlike the listing page's family of
    68), which is why a cart scenario should add a product from this page.
    Adding opens a modal that blocks the page underneath; leave via the modal's
    View Cart link or the Continue Shopping button.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id.

        Prefer reaching this page by clicking a listing's View Product link,
        whose href already carries the id — but this is available when a test
        has the id in hand.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart, then wait for the confirmation modal.

        Adding does not navigate; it opens a modal that blocks the page. Waiting
        for the modal here means the caller can immediately act on it.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        This navigates to /view_cart. The modal exists only after
        add_product_to_cart() has been called.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, because
        the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached a product detail page; recover if not.

        Called after a click on another page is expected to land here.
        """
        super().confirm_arrival(**params)

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        present regardless of whether the add-to-cart modal or a review has been
        interacted with.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible name of the product this page shows. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible price of the product, e.g. 'Rs. 500'. WAITS for it.

        Rendered with the 'Rs.' prefix; assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_add_to_cart_confirmed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart modal is showing. WAITS for it.

        Call this only where the modal is expected — it times out otherwise.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
