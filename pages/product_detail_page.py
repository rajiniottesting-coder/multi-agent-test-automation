"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors: see `pages.product_detail` in the app inventory. No literal
selectors live here; every one is resolved via self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `pages.product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the product id), or by navigating with page_url(product_id=...).
    This page's Add to cart control is UNIQUE — unlike the listing page's family
    of 68 — so a cart scenario should add a product from here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: str) -> None:
        """Navigate directly to a specific product's detail page.

        Prefer reaching this page by clicking a product's View Product link on
        the listing, which already carries the id. This is the fallback for
        opening a product by a known id.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Opens the add-to-cart modal rather than navigating. The modal blocks
        the page underneath, so dismiss it (continue_shopping) or leave via
        view_cart before interacting with the page again.
        """
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, go to the cart page.

        Also proves the modal appeared, since this link lives inside it.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state this page can be in, so it
        is a reliable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def get_product_name(self) -> str:
        """The product's displayed name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def has_added_modal(self) -> bool:
        """True once the add-to-cart modal is showing. WAITS for it.

        Call this only where the modal is the expected result of an Add to cart
        click; it can answer 'no' only by exhausting its timeout.
        """
        return self.is_showing(self.sel("added_modal"))
