"""
ProductsPage — the All Products / search listing screen.

Page object for browsing and searching the catalogue, reading result cards and
names, and opening a specific product's View Product link.

Selectors come from the app inventory (`pages.products`); this file never holds
a literal selector string. Family keys (product_cards, product_names,
add_to_cart_buttons, view_product_links) are MULTI-MATCH — read them with the
plural helpers, and act on a single member only by scoping to its card via
click_in_row().

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products / search listing. Selectors: see `pages.products` in the
    app inventory.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit; results render on the same page.

        The search matches on product NAME and reloads /products with the
        result cards. Wait for is_search_executed() before reading results —
        a card count alone cannot distinguish a one-result search from a
        search that never ran.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its card's View Product link.

        Scopes to the card containing `product_name` rather than indexing into
        the doubled families, so the correct link is clicked.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_listing_loaded(self, timeout_ms: int = None) -> bool:
        """True once the All Products listing heading is on screen. WAITS."""
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def is_search_executed(self, timeout_ms: int = None) -> bool:
        """True once the 'Searched Products' heading appears. WAITS.

        This is the only reliable signal that a search actually ran, so assert
        on it before asserting on the result cards.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Return the visible name text of every result card, in DOM order."""
        return self.get_all_texts(self.sel("product_names"))

    def get_result_count(self) -> int:
        """Return the number of product cards currently displayed.

        For an empty search this app renders NO cards (no empty-state text),
        so assert absence by expecting this to be zero.
        """
        return self.get_count(self.sel("product_cards"))

    def has_product(self, product_name: str) -> bool:
        """True if any result card's name contains `product_name`.

        Reads the product_names family with get_all_texts (never waits on the
        family as a whole, which would be a strict-mode violation).
        """
        return any(product_name in name for name in self.get_result_names())

    def get_product_card_text(self, product_name: str) -> str:
        """Return the full text of the card containing `product_name`.

        The card blob concatenates the name and the price, so a caller can
        assert 'Rs. 500' is present via containment.
        """
        return self.row_containing(self.sel("product_cards"), product_name).inner_text().strip()
