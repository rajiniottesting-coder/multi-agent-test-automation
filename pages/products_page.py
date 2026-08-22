"""
ProductsPage — the /products listing and search screen.

Runs product searches and reads result product names/prices. Selectors come
from `pages.products` in the app inventory; every method uses a BasePage
helper and no method acts on a multi-match family as a whole.

The listing renders several families (product_cards, product_names,
add_to_cart_buttons, view_product_links). This page object reads them with
plural accessors and scopes to a single card by product NAME when it needs to
act on one member — never by index, because product_names and
add_to_cart_buttons are doubled per card while product_cards is not.

Navigation to /products is owned by NavPage (its Products link lives on the
`nav` inventory page). This class assumes the browser is already on /products
and confirms readiness via is_loaded().

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The /products listing and search page.

    Selectors: see `pages.products` in the app inventory.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and reloads the same /products page,
        replacing the 'All Products' heading with 'Searched Products'.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page for the product whose card contains
        `product_name`, by clicking its View Product link.

        Scopes to the card containing the name rather than indexing into the
        view_product_links family, then lands on the product detail page.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing search box is on screen. WAITS for it.

        The search box survives both the unsearched listing and a search that
        returned results or nothing, so it is the state-independent readiness
        signal for this page. The 'All Products' heading is replaced by
        'Searched Products' after a search, so it is not usable here.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def search_executed(self) -> bool:
        """True once a search has actually run. WAITS for the confirmation.

        The 'Searched Products' heading is the only signal that the search
        EXECUTED — a result count alone cannot distinguish 'search returned
        one product' from 'search never ran and the full catalogue is shown'.
        Call this only where a search is expected to have run; to branch on
        whether one ran, this waiting reader would pay the full timeout.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> list[str]:
        """Every product name shown in the results, in DOM order.

        The name family is doubled per card, so a name can appear twice; use
        containment (`name in get_result_names()`) rather than exact counts.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, product_name: str) -> bool:
        """True if a result card containing `product_name` is present. WAITS.

        Call this only when the product IS expected among the results; it waits
        for the row and times out otherwise, so it cannot assert absence.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of result cards currently shown (snapshot, no waiting).

        Read this only to inspect an already-settled result set — for asserting
        a specific count after a search use assert_result_count().
        """
        return self.get_count(self.sel("product_cards"))

    def assert_result_count(self, expected: int) -> None:
        """Wait until exactly `expected` result cards are shown.

        Use this after a search that should return a known number of cards; it
        re-checks until the timeout rather than reading a stale count. For an
        EMPTY search result, pass 0 — this app renders no empty-state message,
        so absence is proven by a zero card count.
        """
        self.wait_for_count(self.sel("product_cards"), expected)

    def row_text_for(self, product_name: str) -> str:
        """The full text of the result card containing `product_name`.

        Contains the name and price together (e.g. 'Blue Top Rs. 500'), so
        assert on containment of the price rather than equality.
        """
        return self.row_containing(
            self.sel("product_cards"), product_name
        ).inner_text().strip()
