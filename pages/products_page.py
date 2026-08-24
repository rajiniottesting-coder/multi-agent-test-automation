"""
ProductsPage — the All Products listing and search screen.

Selectors come from `pages.products` in the app inventory; this file never
contains a literal selector string. Set INVENTORY_PAGE and resolve every
element by its inventory KEY via self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing and search. Selectors: see `pages.products`.

    The listing renders several product families (cards, names, add-to-cart
    buttons), and some are DOUBLED per card. Read them with the plural helpers
    and scope to a card by its product text — never click a family directly.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Type a search term and submit; the results render on this same page.

        Waits for the 'Searched Products' heading, which is the only reliable
        signal that the search actually EXECUTED — a result count alone cannot
        tell an empty result from a search that never ran.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))
        self.wait_visible(self.sel("searched_products_heading"))

    def open_product(self, name: str) -> None:
        """Open the detail page for the product whose card contains `name`.

        Scopes to the card by its product text, then clicks that card's
        'View Product' link — never the family as a whole, which would be a
        strict-mode violation.
        """
        self.click_in_row(
            self.sel("product_cards"),
            name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing this page object navigates to.
        """
        return self.is_showing(
            self.sel("all_products_heading"), timeout_ms=timeout_ms
        )

    def get_result_names(self) -> list[str]:
        """Every product name currently rendered, as a list of strings.

        The name family is doubled per card, so callers should assert
        containment rather than an exact length.
        """
        return self.get_all_texts(self.sel("product_names"))

    def has_result(self, name: str) -> bool:
        """True once a card whose text contains `name` is present. WAITS.

        Call this only where the product is EXPECTED. It waits for the card to
        appear and times out if none ever does, so it must not be used to
        assert absence.
        """
        self.wait_for_row(self.sel("product_cards"), name, present=True)
        return True

    def get_result_count(self) -> int:
        """Number of product result cards currently rendered.

        Uses the card family, which is NOT doubled (unlike names and
        add-to-cart buttons), so this is a truthful card count. A search that
        matches nothing renders zero cards — there is no empty-state message on
        this page — so an empty search is asserted as a count of zero.
        """
        return self.get_count(self.sel("product_cards"))
