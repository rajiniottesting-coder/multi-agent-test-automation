"""
ProductsPage — the All Products listing and its search box.

Selectors: see `pages.products` in the app inventory. No literal selector
strings live here — every element is resolved through self.sel("<key>").

Search matching on this site is on product NAME and submits back to the same
/products URL. The single reliable signal that a search EXECUTED is the
"Searched Products" heading replacing the "All Products" heading — a result
count alone cannot distinguish "returned one product" from "never ran and the
page still shows the full catalogue". Assert on the heading first, then read
results.

The product-name, product-card and view-product-link keys are MULTI-MATCH
families (and doubled per card via the hover overlay), so they are only ever
read with get_all_texts / get_count, or acted on one member at a time by
index via BasePage helpers.

App: https://automationexercise.com
"""
from typing import List

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing and search."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Submits to the same /products URL. Call has_searched() afterwards to
        confirm the search actually executed before reading results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product_by_name(self, name: str) -> None:
        """Open one product's detail page via its View Product link.

        The View Product links are a MULTI-MATCH family (one per card) and the
        name family runs in lockstep with the cards, so the index of the name
        is a valid index into the links. Acting on one member by index is done
        through BasePage.click_nth so the index-pinning stays validator-visible.
        """
        index = self._name_index(name)
        self.click_nth(self.sel("view_product_links"), index)

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the All Products listing is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"))

    def has_searched(self) -> bool:
        """True once the 'Searched Products' heading has appeared. WAITS.

        This is the only reliable signal that the search executed. Assert on it
        before asserting on results.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> List[str]:
        """All product names currently shown, in DOM order.

        The names are doubled per card (card + hover overlay), so the same name
        may appear twice — callers asserting presence should use containment.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, name: str) -> bool:
        """True if a product with the given name is among the results."""
        return name in self.get_result_names()

    def get_result_card_count(self) -> int:
        """Number of product cards currently displayed.

        An empty search renders NO result cards (there is no empty-state text),
        so a zero count is the correct assertion for a no-results search.
        """
        return self.get_count(self.sel("product_cards"))

    # ── internal ─────────────────────────────────────────────
    def _name_index(self, name: str) -> int:
        """Index of the first product-name match equal to `name`, else -1."""
        names = self.get_result_names()
        for i, text in enumerate(names):
            if text == name:
                return i
        return -1
