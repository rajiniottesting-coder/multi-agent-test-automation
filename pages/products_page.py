"""
ProductsPage — the All Products listing and search screen.

Selectors come from `pages.products` in the app inventory; this file never
contains a literal selector. Methods are business verbs, and every one uses a
BasePage helper — no raw self.page.* calls.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing + search. Selectors: `pages.products` in inventory.

    The listing families (product_cards, product_names, add_to_cart_buttons,
    view_product_links) match MANY elements and some are rendered twice per
    card. Read them with the plural helpers, and act on ONE product by scoping
    to the card that contains its name rather than by index.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate directly to the All Products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit; the page reloads on /products."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def view_product(self, product_name: str) -> None:
        """Open the product detail page for the card containing `product_name`.

        Scopes to the card carrying the name, then clicks its View Product
        link — never indexing into the multi-match family, which is doubled per
        card and could address the wrong element.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        Probes the unsearched-listing heading, which is the state-independent
        readiness signal for a freshly loaded /products page.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def search_executed(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the 'Searched Products' heading appears. WAITS for it.

        This is the only reliable signal that a search actually RAN — a result
        count alone cannot distinguish 'search returned one product' from
        'search never ran and the full catalogue is still shown'.
        """
        return self.is_showing(self.sel("searched_products_heading"), timeout_ms=timeout_ms)

    def get_result_count(self) -> int:
        """Number of product cards currently displayed in the listing."""
        return self.get_count(self.sel("product_cards"))

    def get_result_names(self) -> list[str]:
        """Visible product names across all result cards, in DOM order."""
        return self.get_all_texts(self.sel("product_names"))

    def has_product(self, product_name: str) -> bool:
        """True if a card whose text contains `product_name` is present.

        Non-waiting: reads the current set of names. For an empty-result
        assertion pair this with get_result_count() == 0.
        """
        return any(product_name in name for name in self.get_result_names())
