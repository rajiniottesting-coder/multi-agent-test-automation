"""
ProductsPage — the /products all-products listing.

Selectors live in the app inventory under `pages.products`; this file only
references them by KEY via self.sel(). Method names say WHAT they act on, per
the naming rule (open_product, not open).

The listing's Add-to-cart family matches 68 elements (each card doubles its
controls in a hover overlay), so cart scenarios open a product via its
View Product link and add from the detail page instead. This page object
therefore exposes the search/listing readiness checks and the View-Product
navigation, and leaves adding-to-cart to ProductDetailPage.

App: https://automationexercise.com
"""
from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All-products listing. Selectors: see `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open a product's detail page via its 'View Product' link.

        Scopes to the card containing `product_name` rather than indexing into
        the View-Product family, then confirms the browser reached the detail
        page (an ad interstitial can swallow the first navigation).

        Returns the ProductDetailPage so the caller can act on that product.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        detail = ProductDetailPage(self.page)
        detail.confirm_arrival()
        return detail

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the all-products listing is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"))

    def product_names(self) -> list[str]:
        """Every product name shown on the listing (family read)."""
        return self.get_all_texts(self.sel("product_names"))
