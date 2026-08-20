"""
ProductsPage — the /products listing and search screen.

Selectors: see `pages.products` in the app inventory. Every selector is
resolved via self.sel("<key>") — no literal selector strings live here.

Search matches on product NAME and submits back to the same page. The
searched_products_heading is the only reliable signal that a search actually
EXECUTED (a full listing looks the same as a search returning everything), so
methods here expose it as a readiness signal.

Several inventory keys are family selectors (product_cards, product_names,
view_product_links) and are read with plural helpers only. To OPEN one product
we scope to the card containing its name via click_in_row().

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Products listing / search. Selectors: `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit; waits for the search to execute.

        Waits on the 'Searched Products' heading afterwards — the only signal
        that the search actually ran rather than the full catalogue reloading.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the card containing `product_name`.

        Scopes to the card that contains the name and clicks its View Product
        link, rather than indexing across the doubled name family.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_listing_loaded(self) -> bool:
        """True once the full 'All Products' listing is on screen. WAITS."""
        return self.is_showing(self.sel("all_products_heading"))

    def search_has_executed(self) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS."""
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Every product name currently rendered, in DOM order.

        The name family is doubled per card, so callers asserting presence
        should use containment against this list, not an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_count(self) -> int:
        """Number of product cards in the results area.

        Reads the non-doubled product_cards family, so this is a true card
        count. Zero indicates a search that matched nothing (the site renders
        no empty-state text — absence of cards is the signal)."""
        return self.get_count(self.sel("product_cards"))

    def has_product(self, product_name: str) -> bool:
        """True if any rendered card names `product_name` (substring match)."""
        return any(product_name in name for name in self.get_result_names())
