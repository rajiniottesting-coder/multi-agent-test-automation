"""
ProductsPage — the All Products listing at /products.

Selectors come from `pages.products` in the app inventory; this file never
contains a literal selector. Methods are business verbs that name their
subject (open_listing, open_product), per the naming rule.

Opening a product's detail page is done through its View Product link. That
link family is matched by href PREFIX and there is one per card, so the only
safe way to click ONE is to scope to the card containing the product name —
which is what open_product() does via click_in_row().

App: https://automationexercise.com
"""
from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open a product's detail page via its card's View Product link.

        Scopes to the card that contains `product_name` and clicks the View
        Product link inside it, then confirms the detail page was reached.
        Returns a ProductDetailPage for the destination.
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
        """True once the All Products heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"))

    def product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order."""
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a card with the given product name is present."""
        return self.find_row_index_by_text(self.sel("product_cards"), product_name) != -1
