"""
ProductsPage — the /products listing screen.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. Search matches on product name and submits to the
same page, replacing the 'All Products' heading with 'Searched Products'.

The product_names / product_cards / view_product_links / add_to_cart_buttons
keys are MULTI-MATCH (the site doubles every card control for its hover
overlay), so they are read only through the plural helpers — get_all_texts /
get_count — and never clicked, filled, waited on, or asserted against directly.

To open ONE product's detail page, the View Product anchors carry the product
id in their href. Rather than trying to isolate one anchor from the multi-match
family (which trips Playwright's strict mode), open_product() clicks the
product's own name via BasePage.click_role, which resolves ONE element by its
accessible name and navigates to that product's detail page.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Product listing: search, read results, open a product."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit; waits for the search to execute."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open the product's detail page by clicking its name link.

        The listing renders each product name as a link whose accessible name
        is the product name; click_role resolves that ONE element by role and
        name, avoiding the multi-match view_product_links family entirely. The
        anchor navigates straight to /product_details/<id>.
        """
        self.click_role("link", product_name)

    # ── queries ──────────────────────────────────────────────
    def is_listing_loaded(self) -> bool:
        """True once the unsearched 'All Products' heading is visible."""
        return self.is_showing(self.sel("all_products_heading"))

    def has_searched(self) -> bool:
        """True once a search has executed and 'Searched Products' is shown.

        This is the only reliable signal that the search RAN — a result count
        alone cannot distinguish 'returned one product' from 'never searched'.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """All product names shown in the results (deduplicated).

        product_names is doubled per card by the hover overlay, so the raw list
        contains each name twice; dedupe while preserving order.
        """
        seen: List[str] = []
        for name in self.get_all_texts(self.sel("product_names")):
            if name and name not in seen:
                seen.append(name)
        return seen

    def get_result_count(self) -> int:
        """Number of product result cards currently displayed.

        Counts cards (unique per product), not names, so it is not inflated by
        the doubled hover-overlay controls.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result(self, product_name: str) -> bool:
        """True if `product_name` appears among the search results."""
        return product_name in self.get_result_names()
