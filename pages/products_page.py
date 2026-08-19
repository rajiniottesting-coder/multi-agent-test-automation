"""
ProductsPage — the All Products / search listing screen.

Selectors come from `pages.products` in the app inventory. Set INVENTORY_PAGE
and resolve every element via self.sel("<key>"); never write a literal
selector here.

The listing is FAMILY-HEAVY: product_names, product_cards, add_to_cart_buttons
and view_product_links each match many elements, and some render twice per card
(see the inventory notes). Read families with the plural helpers, and act on a
single product by scoping to the card that contains its name via click_in_row.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing with search. Selectors: see `pages.products`."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit. Search matches on product name."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the card containing `product_name`.

        Scopes to the product's card and clicks its View Product link, so the
        multi-match family is never clicked as a whole.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def wait_search_executed(self) -> None:
        """Wait until the 'Searched Products' heading confirms the search ran.

        The result count alone cannot distinguish 'search returned one product'
        from 'search never ran and the full catalogue is still shown', so this
        heading is the only reliable signal that the search executed.
        """
        self.wait_visible(self.sel("searched_products_heading"))

    def has_search_executed(self) -> bool:
        """True if the 'Searched Products' heading is showing (no waiting)."""
        return self.is_visible(self.sel("searched_products_heading"))

    def get_product_names(self) -> List[str]:
        """All visible product names in the results, as a list of strings.

        Read via the plural helper because product_names is a multi-match
        family (and doubled per card); use containment checks against this.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if `product_name` appears in the current result cards."""
        return any(product_name in name for name in self.get_product_names())

    def get_card_count(self) -> int:
        """Number of product cards currently displayed.

        Uses product_cards, which is one-per-card (NOT doubled), so this is a
        true card count. An empty search renders zero cards rather than an
        empty-state message, so assert absence by this count being 0.
        """
        return self.get_count(self.sel("product_cards"))

    def get_price_for_product(self, product_name: str) -> str:
        """Return the visible text of the card that contains `product_name`.

        The card text is the concatenation of the product's name, price and
        controls, so assert the expected price with containment rather than
        equality.
        """
        card = self.row_containing(self.sel("product_cards"), product_name)
        return card.inner_text().strip()
