"""
ProductsPage — the /products listing and search screen.

Encapsulates browsing the product catalogue, running a name search, and
opening a specific product from the results. Selectors come from the
`products` page in the app inventory (see INVENTORY_PAGE); this file never
holds a literal selector.

Conventions followed (mirrors pages/login_page.py):
  - business-verb method names that say WHAT they act on
  - every method routes through a BasePage helper — no raw self.page.*
  - no assertions here; those belong in step definitions
  - family selectors (product_names, view_product_links, product_cards) are
    read with the plural helpers or scoped with click_in_row — never clicked
    as a whole

App: https://automationexercise.com
"""
from typing import List, Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """The All Products listing and its search box.

    Readiness: the search box is present on both the unsearched listing AND the
    searched-results view, whereas the 'All Products' heading is REPLACED by
    'Searched Products' once a search runs. is_loaded() therefore probes the
    search input, which survives every state this page can be in.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def search_for(self, term: str) -> None:
        """Type a search term into the product search box and submit it.

        Search matches on product NAME and submits back to /products. The
        search icon button has no accessible name, so it is reached by its id
        via the inventory key.
        """
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page from the (searched) listing by name.

        Scopes to the product CARD containing the given name and clicks the
        View Product link inside it, so the correct product is opened even
        though the View Product links form a family across all cards.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the products page is on screen. WAITS for it.

        Probes the search input, the one element present in both the
        unsearched and searched states of this page.
        """
        return self.is_showing(self.sel("search_input"), timeout_ms=timeout_ms)

    def search_has_run(self, timeout_ms: Optional[int] = None) -> bool:
        """True once a search has executed. WAITS for the 'Searched Products'
        heading.

        This heading REPLACES 'All Products' only after a search submits, and
        is the sole reliable signal that the search actually ran — a result
        count alone cannot distinguish 'search returned one product' from
        'search never ran and the full catalogue is still shown'. Call this
        only where a search is expected to have run; asserting it did NOT run
        would time out here.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_names(self) -> List[str]:
        """Every product name shown in the current listing, in DOM order.

        The name selector is a family (and doubled per card), so this returns
        duplicates; use it for containment checks such as 'Blue Top is present'
        rather than for exact counts.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Number of product cards currently displayed (no waiting).

        The card family is NOT doubled per card (unlike the name and add-to-cart
        families), so this is one per product. Used to assert an empty result
        set: an empty search renders zero cards with no empty-state message.
        """
        return self.get_count(self.sel("product_cards"))
