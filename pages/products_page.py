"""
ProductsPage — the /products listing screen.

Search the catalogue, confirm a search actually ran, count the result cards,
read the product names present, and open a product via its View Product link.

Selectors come from `pages.products` in the app inventory — never a literal
here. See LoginPage for the worked conventions this file follows.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The /products listing. Selectors: see `pages.products` in the inventory.

    Two headings act as mirror signals: `all_products_heading` on the
    unsearched listing, `searched_products_heading` once a search has run.
    Assert the searched heading BEFORE asserting on results — a result count
    alone cannot tell 'search returned one product' from 'search never ran'.

    Several families here are MULTI-MATCH and some are DOUBLED per card
    (product_names, add_to_cart_buttons). Read them with the plural helpers;
    to open one product, scope by the card containing its name, never by index
    into a doubled family.
    """

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the product listing and confirm arrival."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term into the search box and submit it.

        Matches on product NAME and reloads the same /products page. Call
        wait_until_searched() afterwards to confirm the search executed
        before reading results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its card's View Product link.

        Scopes to the card containing `product_name` rather than indexing a
        doubled family, then clicks that card's View Product link.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the search box, which survives BOTH states of this page — the
        unsearched full listing and the searched-results view. The headings do
        not: each is present in only one state, so a probe built on one would
        report 'not loaded' for a page that has loaded perfectly well.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def wait_until_searched(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        Call this only where a search IS expected to have run — it is the one
        reliable signal that the search executed, since a result count cannot
        distinguish 'one match' from 'search never ran, still full catalogue'.
        It can answer 'no' only by timing out, so do not use it to branch.
        """
        return self.is_showing(
            self.sel("searched_products_heading"), timeout_ms=timeout_ms
        )

    def product_names(self) -> List[str]:
        """Every product name currently shown, as a list of strings.

        The name family is DOUBLED per card, so names appear more than once —
        use containment (`name in product_names()`) rather than a count on this.
        Reads `product_names`, whose selector targets the name element in each
        card (.productinfo p), so each entry is one product name, not a whole
        row.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result_named(self, product_name: str) -> bool:
        """True if a card with the given product name is present. WAITS for it.

        Built on wait_for_row, so it retries until the card appears; call it
        only where the product is EXPECTED, since it can report False only by
        timing out.
        """
        try:
            self.wait_for_row(
                self.sel("product_cards"), product_name, present=True
            )
            return True
        except Exception:
            return False

    def result_card_count(self) -> int:
        """Number of result cards currently shown. Does NOT wait.

        For asserting an EMPTY result set: an empty search renders no cards and
        no empty-state message on this app, so counting cards is the only way
        to assert 'no results'. Use only after wait_until_searched() has
        confirmed the search ran, so the count reflects the search and not the
        still-loading full catalogue.
        """
        return self.get_count(self.sel("product_cards"))
