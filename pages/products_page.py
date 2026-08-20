"""
ProductsPage — the All Products / search-results listing at /products.

Selectors come from the app inventory (`pages.products`), never from literals
here. Set INVENTORY_PAGE, then look elements up with self.sel("<key>").

Search on this site submits to the same /products path and swaps the
"All Products" heading for "Searched Products" — the only reliable signal that
the search actually ran. A no-match search renders zero result cards rather
than an empty-state message, so absence is asserted by counting cards.

The result-card families (product_names, view_product_links) match several
elements, so they are read with the plural helpers and acted on ONE member at
a time by scoping to the card that contains the product name.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All Products listing and search. See `pages.products` in the inventory.

    The listing renders some controls twice per card (names and add-to-cart
    buttons appear in both the card and its hover overlay). This class never
    indexes those doubled families; it scopes to the card that contains a
    product name with click_in_row() instead.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        The search reloads /products and replaces the "All Products" heading
        with "Searched Products". This waits for that heading so callers can
        trust the search executed before inspecting results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open the product whose card contains `product_name` via its
        View Product link, then confirm the detail page was reached.

        Scopes to the card containing the name rather than indexing the
        doubled control families, then hands off to the detail page object to
        verify arrival (a click alone is not a guarantee — an ad interstitial
        can swallow the first navigation).
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        ProductDetailPage(self.page).confirm_arrival()

    def dismiss_added_modal(self) -> None:
        """Close the add-to-cart modal and stay on the listing.

        Needed between adding two products on this page, since the modal blocks
        the page underneath.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the search input rather than a heading: the "All Products"
        heading is replaced by "Searched Products" once a search runs, so a
        heading probe would report not-loaded on a perfectly valid results
        page. The search box survives both states.
        """
        return self.is_showing(self.sel("search_input"))

    def has_searched(self) -> bool:
        """True once a search has executed (the "Searched Products" heading
        is showing). WAITS for it."""
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """Visible product names across all result cards, in DOM order.

        The names family is doubled per card, so callers should use containment
        (`expected in names`) rather than exact counts on this list.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if `product_name` appears among the result cards.

        Substring containment against the (possibly doubled) names family, so
        it is robust to the site rendering each name twice per card.
        """
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of result cards currently rendered.

        product_cards is one-per-card (NOT doubled), so this is a reliable card
        count. Used to assert an empty result set — this site renders no
        empty-state message for a no-match search, so zero cards is the signal.
        """
        return self.get_count(self.sel("product_cards"))
