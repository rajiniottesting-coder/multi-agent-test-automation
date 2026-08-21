"""
ProductsPage — the /products listing and search screen.

Selectors come from the app inventory (`pages.products`); this file never
contains a literal selector string. Look each element up with self.sel("<key>").

Search matches on product NAME and submits back to /products. The only reliable
signal that a search EXECUTED is the "Searched Products" heading replacing
"All Products"; a result count alone cannot distinguish "one match" from "the
search never ran". Several families here are doubled per card (product_names,
add_to_cart_buttons) — read them with get_all_texts / get_count, and act on a
single member by scoping to the card that contains the product name.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """Product listing and search. Selectors: see `pages.products` inventory."""

    INVENTORY_PAGE = "products"

    # ── navigation / arrival ─────────────────────────────────
    def confirm_arrival(self, **params: object) -> None:
        """Confirm the browser reached /products; recover if an ad ate the click."""
        super().confirm_arrival(**params)

    def is_loaded(self) -> bool:
        """True once the listing is on screen. WAITS for the All Products heading.

        The unsearched listing always shows this heading; it is the most
        state-independent handle for 'the products page loaded'.
        """
        return self.is_showing(self.sel("all_products_heading"))

    # ── search ───────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search submits back to /products. After this, use is_search_executed()
        to confirm the search actually ran before asserting on results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def is_search_executed(self) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        This is the only reliable proof the search executed — a result count
        alone cannot tell 'returned one product' from 'never ran'.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    # ── results ──────────────────────────────────────────────
    def result_names(self) -> List[str]:
        """Every product name currently listed, as a list of strings.

        The name family is doubled per card, so a name may appear twice. Use
        containment (`expected in result_names()`) rather than an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, name: str) -> bool:
        """True if a product with the given name is present in the listing.

        Waits for the row containing the name to appear, so it is safe to call
        immediately after a search executes.
        """
        try:
            self.wait_for_row(self.sel("product_cards"), name, present=True)
            return True
        except Exception:
            return False

    def get_result_card_count(self) -> int:
        """Number of product result cards on screen (no waiting).

        For the empty-search case: this app renders NO cards and NO empty-state
        message, so absence is asserted by counting cards, not by looking for
        text. product_cards is one-per-card (not doubled), so this is a true
        card count.
        """
        return self.get_count(self.sel("product_cards"))

    def assert_no_results(self) -> None:
        """Wait until zero product result cards are shown.

        Uses wait_for_count so the assertion tolerates the listing still
        settling right after the search submits.
        """
        self.wait_for_count(self.sel("product_cards"), 0)

    # ── acting on a single product ───────────────────────────
    def open_product(self, name: str) -> None:
        """Open the detail page for the product whose card contains `name`.

        Scopes to the card containing the name and clicks its View Product
        link — never the whole family, which matches one link per card and
        would raise a strict-mode violation.
        """
        self.click_in_row(
            self.sel("product_cards"), name, self.sel("view_product_links")
        )
