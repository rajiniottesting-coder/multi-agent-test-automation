"""
ProductsPage — the /products catalogue and search screen.

Selectors: see `pages.products` in the app inventory. This page carries two
independent listing states — the full catalogue ("All Products") and the
search results ("Searched Products"). The all_products_heading survives every
state that matters for readiness, so is_loaded() probes it.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The product listing and search page.

    The catalogue is SHARED, so assert product presence by containment
    (get_product_names) rather than by an index. Several keys here match a
    whole FAMILY of elements (product_cards, product_names, view_product_links)
    — never click or assert on them as a whole; scope to the card containing a
    product name instead.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a term into the search box and submit it.

        The search reloads onto the same /products path and replaces the
        'All Products' heading with 'Searched Products'. Wait for that heading
        before reading results — it is the only reliable signal the search
        actually executed.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, product_name: str) -> None:
        """Open the detail page of the card that contains `product_name`.

        Scopes the View Product link to the card carrying the product name, so
        it acts on exactly one member of the view_product_links family.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product listing is on screen. WAITS for it.

        Probes all_products_heading — the state-independent readiness element
        for the unsearched listing.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading is shown. WAITS for it.

        This is the signal that a search actually RAN — distinct from whether
        it returned anything. Assert on this before asserting on results.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every product name currently listed, as a list of strings.

        The product_names family is doubled per card (once in the card, once in
        the hover overlay), so a name may appear twice — assert containment,
        not an exact list.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if `product_name` appears among the listed products."""
        return any(product_name in name for name in self.get_product_names())

    def get_result_card_count(self) -> int:
        """Number of result cards displayed (not doubled — one per card).

        Use for asserting an EMPTY result set: a no-match search renders zero
        cards rather than an empty-state message.
        """
        return self.get_count(self.sel("product_cards"))
