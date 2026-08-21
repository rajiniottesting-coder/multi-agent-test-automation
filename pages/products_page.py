"""
ProductsPage — the all-products listing at /products.

Selectors come from the `products` page in the app inventory; this file never
carries a literal selector string. Methods are business verbs that name what
they act on, and every one goes through a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `products` in the app inventory.

    The listing is full of families — product cards, names, Add-to-cart
    buttons and View Product links all match many elements — so acting on ONE
    product means scoping to the card that contains its name, never indexing a
    doubled family. This page object exposes only what a cart scenario needs:
    open the listing and step into a product's detail page.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open a product's detail page via its own View Product link.

        Scopes to the card that contains `product_name` and clicks the View
        Product link inside that card, so the correct product is opened even
        though the link selector matches one per card. Returns the detail page
        object and confirms the browser reached it.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        detail_page = ProductDetailPage(self.page)
        detail_page.confirm_arrival()
        return detail_page

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every product name shown on the listing, as a list of strings."""
        return self.get_all_texts(self.sel("product_names"))
