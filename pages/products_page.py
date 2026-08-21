"""
ProductsPage — the All Products listing and search screen.

Selectors come from `pages.products` in the app inventory; this file never
contains a literal selector string. Methods are business verbs describing
shopper intent, and every one delegates to a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    The listing carries several MULTI-MATCH families (product cards, names,
    Add-to-cart buttons, View Product links). They are read with the plural
    helpers and acted on one member at a time by scoping to the row containing
    a product name — never clicked as a whole.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a term into the search box and submit the search."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the card whose name contains `product_name`.

        Scopes to that product's card and clicks its View Product link, so the
        MULTI-MATCH link family is never clicked as a whole.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products listing is on screen. WAITS for it.

        Probes the All Products heading — the state-independent element present
        on the unsearched listing that this page loads into.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_has_run(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the search has executed. WAITS for the Searched Products
        heading, which is the only reliable signal that a search ran rather
        than the full catalogue still being displayed.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def result_names(self) -> list[str]:
        """Visible names of every product card in the results, in DOM order.

        Reads the MULTI-MATCH product-name family with the plural helper. Note
        the family renders twice per card, so a name may appear more than once.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a card whose name contains `product_name` is present."""
        return any(product_name in name for name in self.result_names())

    def result_card_count(self) -> int:
        """Number of product cards displayed in the results.

        Uses the non-doubled product_cards family, so this is the true card
        count. Used to assert an empty result set — this app renders no
        empty-state text, so zero cards is the only signal.
        """
        return self.get_count(self.sel("product_cards"))
