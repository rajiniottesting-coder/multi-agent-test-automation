"""
ProductsPage — the /products catalogue listing.

New page object for the shopping-session feature. Conventions follow
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY, never from a literal here.
    Set INVENTORY_PAGE, then use self.sel("<element_key>").
  - methods are business verbs that name their subject (search_for,
    open_product), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    Several element families here are MULTI-MATCH and, worse, doubled per card
    (product_names and add_to_cart_buttons render twice per card). Read them
    with the plural helpers; to act on ONE card, scope to the row containing
    the product name with click_in_row(). Never click or assert on a family
    as a whole.
    """

    INVENTORY_PAGE = "products"

    # ── navigation ───────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the /products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term and submit it.

        Search matches on product NAME and reloads the same /products URL. The
        only reliable signal that the search EXECUTED is the Searched Products
        heading — assert on that via search_executed() before reading results.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the product detail page via the card's View Product link.

        Scopes to the card containing `product_name` so the correct one of the
        many View Product links is clicked, rather than indexing across a
        doubled family. Does NOT call confirm_arrival() — that belongs to the
        destination page object (ProductDetailPage).
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the listing is on screen. WAITS for it.

        Probes the readiness element for this page: the search input is present
        in every state the listing can be in — full catalogue, after a search
        that matched products, and after a search that matched nothing — unlike
        the All Products heading, which a search replaces.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Searched Products heading has appeared. WAITS for it.

        This is the only signal that distinguishes 'the search ran and returned
        one product' from 'the search never ran and the page still shows the
        full catalogue'. Assert on it before asserting on results.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_product_names(self) -> List[str]:
        """Every product name in the results, as a list of strings.

        Use containment against this list to assert a product IS present. The
        family is doubled per card, so names may repeat — do not treat the
        length as the number of distinct products.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Number of result cards shown.

        product_cards is one-per-card (NOT doubled), so this is the reliable
        count of distinct products. For an empty search this returns 0, which
        is how absence is asserted on this listing — there is no empty-state
        message.
        """
        return self.get_count(self.sel("product_cards"))

    def has_product(self, product_name: str) -> bool:
        """True if a product whose name contains `product_name` is present.

        Never waits: built on get_all_texts so it can also assert absence after
        a search that matched nothing.
        """
        return any(product_name in name for name in self.get_product_names())
