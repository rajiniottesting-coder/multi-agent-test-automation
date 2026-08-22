"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the app inventory (`product_detail` page). This file uses
self.sel("<key>") exclusively — never a literal selector string.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the app inventory.

    Reached by clicking a product's View Product link on the listing (its href
    already carries the product id), or by navigating to the URL template with
    open_product(). Add-to-cart opens a MODAL rather than navigating; the modal
    blocks the page underneath, so dismiss it before any further interaction.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal to open.

        The control is unique on this page (unlike the listing's family of 68),
        so it is safe to click directly.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal to go to the cart."""
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name, which is present in every state this page can
        be in (the add-to-cart modal overlays but does not remove it).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown on the detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is expected. To branch on whether the
        modal is present, use is_visible() on the modal selector instead.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
