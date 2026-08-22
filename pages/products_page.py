"""
ProductsPage — the all-products listing at /products.

Selectors come from the `products` page in the app inventory; this file never
contains a literal selector string. Set INVENTORY_PAGE and look each element up
by its `elements` key with self.sel("<key>").

The listing renders several families that match many elements at once
(product_cards, product_names, view_product_links, add_to_cart_buttons), so
opening ONE product is done by scoping to the card that contains the product's
name and clicking the View Product link inside it — never by clicking a family
selector directly, which would raise a strict-mode violation.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `products` in the app inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> None:
        """Open a named product's detail page via its View Product link.

        Scopes to the product CARD containing `product_name` and clicks the
        View Product link inside it, so the many-per-page link family is never
        clicked as a whole (which would be a strict-mode violation).
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        The unsearched listing always renders this heading, so it is a stable
        readiness signal for the page in its default state.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order.

        Reads the multi-match name family with a plural reader — the only legal
        operation on a family selector.
        """
        return self.get_all_texts(self.sel("product_names"))
