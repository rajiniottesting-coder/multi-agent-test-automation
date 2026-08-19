"""
ProductsPage — the /products catalogue listing and search.

Selectors: see `pages.products` in the app inventory. This page carries a
family of repeated controls per product card (names, cards, add-to-cart
buttons and View Product links), so reading is done with the plural helpers
and acting on ONE product is done by finding its index by text and clicking
the matching member of the parallel family.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The All Products listing and its name-based search.

    The search matches on product NAME and submits back to /products. The
    All Products heading is replaced by a Searched Products heading once a
    search has run — that heading is the only reliable proof the search
    actually executed, so query methods wait on it.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.wait_visible(self.sel("all_products_heading"))

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Waits for the Searched Products heading afterwards, which is the only
        signal that distinguishes 'the search ran and matched one product'
        from 'the search never ran and the full catalogue is still shown'.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its View Product link.

        Finds the product's card by its name, then clicks the View Product
        link at the same index — the two families run one-per-card in lockstep.
        """
        index = self.find_row_index_by_text(self.sel("product_cards"), product_name)
        self.click_nth(self.sel("view_product_links"), index)

    # ── queries ──────────────────────────────────────────────
    def is_search_results_shown(self) -> bool:
        """True once the Searched Products heading is visible. WAITS for it."""
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> list[str]:
        """Return every product name currently displayed, in DOM order.

        The name selector is doubled per card (card body plus hover overlay),
        so the same name appears more than once — assert containment against
        this list rather than treating it as a de-duplicated set.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Return the number of product cards currently displayed.

        Used to assert an empty result set: an unmatched search renders NO
        cards rather than an empty-state message, so zero cards is the
        expected signal for 'no products found'.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result_named(self, product_name: str) -> bool:
        """True if any displayed product name contains the given text."""
        return any(product_name in name for name in self.get_result_names())
