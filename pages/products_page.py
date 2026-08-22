"""
ProductsPage — the /products listing and search screen.

Selectors come from the app inventory (INVENTORY_PAGE = "products"); this file
never contains a literal selector. Methods are business verbs and every one
delegates to a BasePage helper. No assertions live here — those belong in the
step definitions.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing plus product search.

    Search matches on product NAME and reloads the same /products path, so a
    result count alone cannot tell 'the search returned one product' from 'the
    search never ran'. The reliable execution signal is the Searched Products
    heading — wait for it before reading results.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        The search button is icon-only (no accessible name), so the inventory
        pins it by id — that is the correct locator here.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the card whose name contains `product_name`.

        Scopes to the card containing the product name and clicks that card's
        own View Product link, rather than indexing into the family — the
        Add-to-cart and product-name families are doubled per card, so an index
        taken from one does not map onto another.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing that this page object opens with.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_has_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has actually run. WAITS for the Searched Products
        heading, and times out if it never appears.

        Call this only where a completed search is the expected state. It is the
        one reliable signal that the search executed — assert on it before
        reading results, since a bare result count cannot distinguish a
        one-product result from the full catalogue never having been searched.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def result_names(self) -> List[str]:
        """Every product name currently shown, in DOM order.

        The name family is doubled per card, so this list contains each product
        twice — use it for containment ('is Blue Top present'), not for counting.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True once a card whose name contains `product_name` is on screen.
        WAITS for that row, and times out if it never appears.

        Call this where the product IS expected among the results. For asserting
        a product is ABSENT, use result_card_count() and expect zero.

        Scopes to the card containing the product name rather than probing the
        name family directly, which is multi-match and would raise strict-mode.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def result_card_count(self) -> int:
        """Number of product cards currently rendered. Does NOT wait.

        For asserting an EMPTY result set: this app renders no empty-state
        message for a no-match search, so absence must be asserted by counting
        cards. The product_cards family is one-per-card (not doubled), so this
        count is the real number of matching products.
        """
        return self.get_count(self.sel("product_cards"))

    def product_price(self, product_name: str) -> str:
        """The price text shown alongside `product_name` in the results.

        Reads the whole card that contains the name, so the returned text
        contains the name and the price together (e.g. 'Blue Top Rs. 500').
        Assert on containment of the price, not equality.
        """
        return self.row_containing(self.sel("product_cards"), product_name).inner_text().strip()
