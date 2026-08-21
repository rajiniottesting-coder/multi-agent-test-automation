"""
ProductsPage — the /products listing.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. Business verbs only, no assertions.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    The product families (cards, names, add-to-cart buttons, view links) all
    match many elements — several are even doubled per card. Read them with the
    plural helpers, and reach a single product by scoping to the card that
    contains its name, never by indexing across two families.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term into the search box and submit it.

        Search matches on product name and reloads the same page. Assert the
        'Searched Products' heading afterwards to confirm the search ran.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the product detail page for the card containing `product_name`.

        Scopes to the card that contains the name and clicks its View Product
        link — never indexing across the doubled families.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the All Products heading, which is the listing's stable readiness
        signal before any search has replaced it.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has actually run. WAITS for the results heading.

        The 'Searched Products' heading is the only reliable signal that the
        search executed — a result count alone cannot distinguish 'the search
        returned one product' from 'the search never ran'. Call this only when
        a search IS expected to have run; it times out otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def result_names(self) -> List[str]:
        """Visible product names in the results, in DOM order.

        Names are doubled per card, so a product appears twice — assert
        containment rather than an exact list.
        """
        return self.get_all_texts(self.sel("product_names"))

    def result_card_count(self) -> int:
        """Number of result cards displayed. NOT doubled (unlike names).

        Use this to assert an empty result set: an empty search renders no
        cards rather than an empty-state message.
        """
        return self.get_count(self.sel("product_cards"))
