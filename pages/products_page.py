"""
ProductsPage — the /products listing and its search box.

Wraps searching the catalogue, reading the result product names, counting the
rendered product cards, and opening a specific product via its View Product
link. Selectors come from `pages.products` in the app inventory; this file
holds no literal selector strings.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    Several element keys here are MULTI-MATCH families (product cards, names,
    add-to-cart buttons, view-product links) and some render twice per card.
    Read them with the plural helpers (get_all_texts / get_count) and act on a
    single member only by scoping to the row containing its text.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        The icon-only search button has no accessible name, so it is addressed
        by its inventory key rather than by role. Search matches on product
        name and reloads the same /products page.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via the View Product link in its card.

        Scopes to the card containing the product name rather than indexing
        into the doubled product-name family, then clicks the View Product
        link inside that card.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products listing is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading appears. WAITS for it.

        This is the only reliable signal that a search actually RAN — a result
        count alone cannot tell an empty match from a page that never searched.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Return every product name currently shown, in DOM order.

        The name family renders twice per card, so this list contains
        duplicates; use containment checks rather than assuming uniqueness.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a product with the given name is present in the results."""
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of product cards rendered in the results area.

        Uses the card family (one per product, NOT doubled) so this is a true
        product count. Zero means an empty result set.
        """
        return self.get_count(self.sel("product_cards"))
