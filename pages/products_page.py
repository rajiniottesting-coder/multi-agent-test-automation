"""
ProductsPage — the all-products listing (/products).

Selectors: see `products` in the app inventory. This page renders a family of
product cards; the meaning-bearing action here is opening a specific product's
detail page via its 'View Product' link, which carries the product id in its
href and lands on /product_details/<id>.

Family-selector discipline: product_names, view_product_links, product_cards
and add_to_cart_buttons all match many elements (and several are doubled per
card). Never click a family key directly — scope to the card containing the
product name with click_in_row(), and confirm arrival on the destination page.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All-products listing. Selectors: see `products` in the app inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its 'View Product' link.

        Scopes to the card containing `product_name` rather than indexing into
        the doubled family, then confirms the browser reached the product
        detail page (an ad interstitial can swallow the first navigation).
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        ProductDetailPage(self.page).confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the all-products listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing this page object opens.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name on the listing (family read, no acting)."""
        return self.get_all_texts(self.sel("product_names"))
