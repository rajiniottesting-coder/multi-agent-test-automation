"""
ProductsPage — the all-products listing screen.

Browse the full catalogue, then open a named product's detail page via its
'View Product' link. Adding to cart and reading quantities happens on the
product detail page and the cart page respectively, so this page object
restricts itself to listing readiness, navigation and opening one product.

Selectors: see `pages.products` in the app inventory.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    The product name, add-to-cart and view-product families all match MANY
    elements here (several of them doubled per card), so this page object never
    clicks a bare family. To act on ONE product it scopes to the card that
    contains that product's name with click_in_row().
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL, from the `base_url` fixture.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open the detail page for a named product via its View Product link.

        Scopes to the product card containing `product_name` and clicks the
        View Product link INSIDE that card, so the family of one-link-per-card
        never resolves to more than one element. Confirms arrival on the
        product detail page before returning its page object.

        Returns:
            A ProductDetailPage bound to the same browser page, so the caller
            can add the product to the cart next.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        detail = ProductDetailPage(self.page)
        detail.confirm_arrival()
        return detail

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        Call this only where the listing is expected. It is the readiness
        signal for the unsearched catalogue and survives a page reload.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)
