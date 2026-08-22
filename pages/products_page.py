"""
ProductsPage — the /products catalogue listing and its search.

Selectors come from the app inventory (pages.products); this file never
contains a literal selector. Set INVENTORY_PAGE and use self.sel("<key>").

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The All Products / search-results listing.

    Selectors: see `pages.products` in the app inventory.

    Search matching is on product NAME and submits back to /products. The
    'Searched Products' heading is the only reliable signal that the search
    actually EXECUTED — a result count alone cannot tell 'search returned one
    product' from 'search never ran and the full catalogue is still showing'.
    Several families here (product_names, add_to_cart_buttons) render TWICE per
    card, so read them with the plural helpers and act on ONE member by
    scoping to the card that contains the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the product listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit the search.

        Submits to the same /products URL. Assert on the 'Searched Products'
        heading afterwards to confirm the search executed before inspecting
        the results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the card whose name contains `product_name`.

        Scopes to the card carrying the name, then clicks that card's own
        View Product link — the family matches one link per card, so acting on
        the whole family would be a strict-mode violation.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on the listing.

        Only valid after a product has been added — the button lives inside
        the modal, which does not exist on a freshly loaded page.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing — the state this page loads into before any search runs.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def wait_for_search_executed(self, timeout_ms: Optional[int] = None) -> None:
        """Wait until the 'Searched Products' heading confirms a search ran.

        Raises on timeout. This is the reliable signal that the search
        actually executed; a result count cannot distinguish that from the
        full catalogue still being shown.
        """
        self.wait_visible(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def has_search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading appears. WAITS.

        Call this only where a search IS expected to have run; it can only
        answer 'no' by exhausting its timeout.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> List[str]:
        """Return the visible product names across all result cards.

        The name family renders twice per card, so this list contains
        duplicates. Assert presence with containment rather than by index.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if any result card's name contains `product_name`.

        Reads the rendered names once; call after confirming the search
        executed so the results are already present.
        """
        return any(product_name in name for name in self.get_result_names())

    def get_result_card_count(self) -> int:
        """Number of product cards currently shown. Non-waiting snapshot.

        Use for asserting an empty result set: an unmatched search renders NO
        cards rather than an empty-state message, so this is the only signal.
        """
        return self.get_count(self.sel("product_cards"))
