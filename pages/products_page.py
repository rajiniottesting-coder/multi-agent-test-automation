"""
ProductsPage — the Products listing and search screen.

Selectors come from the app inventory (INVENTORY_PAGE = "products"); this file
never contains a literal selector string.

Covers the behaviour SCRUM-188 and SCRUM-190 need on this page:
  - navigating to the listing
  - confirming the all-products listing is shown
  - running a search and confirming it EXECUTED (heading swaps to
    "Searched Products")
  - reading result names to assert a product is present
  - opening a product's detail page via its own View Product link
  - counting result cards to assert an empty search yields nothing

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing and product search.

    Several element families here are DOUBLED per card (product_names,
    add_to_cart_buttons) — the card renders them once inline and once in a
    hover overlay. Never take an index from a doubled family. To open one
    product, scope to the card row that contains its name and click the
    View Product link inside it.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products_page(self, base_url: str) -> None:
        """Navigate to the Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Confirms it is ON this page first: filling a field that is not on
        screen does not fail fast — Playwright waits the full timeout and then
        blames the locator, which reads like a broken selector when the page is
        simply wrong.
        """
        self.require_own_page()
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product_detail_for(self, product_name: str) -> None:
        """Open the detail page for one product via its View Product link.

        Scopes to the card ROW containing the product name and clicks the
        link inside it — never an index into the multi-match family, which is
        doubled per card and would address the wrong element.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the freshly loaded
        listing before any search has run.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def is_showing_all_products(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the unsearched All Products listing is shown. WAITS.

        Call this only where the all-products view is the expected state; it
        can answer 'no' only by exhausting its timeout.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_has_run(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has actually EXECUTED. WAITS for the heading swap.

        The 'Searched Products' heading is the only reliable signal that a term
        was entered AND submitted — a result count alone cannot tell 'the
        search returned one product' from 'the search never ran'. An empty
        query does not run a search and this heading never appears; assert on
        the all-products heading for that case instead.

        Call this only where a search is expected to have run; it can answer
        'no' only by timing out.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> list[str]:
        """Every product name currently shown, as a list of strings.

        The name family is doubled per card, so a product appears more than
        once here — use containment (`name in get_result_names()`) to assert
        presence rather than reasoning about the exact list length.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result_for(self, product_name: str) -> bool:
        """True once a result card for `product_name` is present. WAITS for it.

        Built on wait_for_row so it retries until the results settle rather
        than snapshotting the list the instant after submit, when it may still
        be updating. Call this only where the product IS expected.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True

    def get_result_card_count(self) -> int:
        """Number of product result cards currently displayed (no waiting).

        product_cards is the un-doubled family — one per card — so this is a
        true card count. Used to assert an empty search yields zero cards: the
        site renders NO 'no results' message, so counting cards is the only
        signal available for that case.
        """
        return self.get_count(self.sel("product_cards"))
