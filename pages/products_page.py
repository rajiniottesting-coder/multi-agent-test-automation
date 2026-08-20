"""
ProductsPage — the /products listing screen.

Selectors come from `pages.products` in the app inventory. Every method here is
a business verb naming what it acts on, and every selector is resolved through
self.sel("<key>"); no literal selector strings live in this file.

Family keys on this page (product_cards, product_names, add_to_cart_buttons,
view_product_links) match many elements — and product_names / add_to_cart are
DOUBLED per card. They are only ever read with plural helpers or scoped to a
single card by text via click_in_row(); never clicked or filled as a whole.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Products listing. Selectors: see `pages.products` in the app inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it. The results render on this page."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the product detail page for the card matching `product_name`.

        Scopes to the card containing the name and clicks its View Product
        link, so the doubled family keys never cause a strict-mode violation.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_listing_loaded(self) -> bool:
        """True once the unsearched All Products listing is on screen. WAITS."""
        return self.is_showing(self.sel("all_products_heading"))

    def wait_for_search_results(self) -> None:
        """Wait for the Searched Products heading — proof the search executed.

        A result count alone cannot tell 'returned one product' from 'never ran
        and still shows the full catalogue', so wait on this heading first.
        """
        self.wait_visible(self.sel("searched_products_heading"))

    def get_result_names(self) -> list[str]:
        """Every product name in the results, in DOM order.

        The family is doubled per card, so names may repeat — callers should
        use containment (`name in get_result_names()`) rather than a count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True if a product with this name appears among the results."""
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of result cards. product_cards is one per card (not doubled),
        so this counts distinct products — 0 for an empty search."""
        return self.get_count(self.sel("product_cards"))

    def get_card_text(self, product_name: str) -> str:
        """The full text of the card containing `product_name`.

        Includes the name and price, so assert with containment (e.g. that
        'Rs. 500' is present) rather than equality.
        """
        return self.row_containing(
            self.sel("product_cards"), product_name
        ).inner_text().strip()
