"""
ProductsPage — the All Products listing and search results.

Selectors: see `pages.products` in the app inventory. This page carries two
FAMILIES that matter here — product cards and product names — plus a search
box that submits to the same URL. Both families are doubled per card
(inventory notes), so read them with the plural helpers and open a single
product through its View Product link scoped to the card that holds its name.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products / search results. See `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open(self, base_url: str) -> None:
        """Navigate directly to the products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def search_for(self, term: str) -> None:
        """Type a search term and submit it. Search matches on product name."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product(self, product_name: str) -> None:
        """Open the product whose card contains `product_name` via its
        View Product link.

        Scopes to the card holding the name rather than indexing into the
        View Product family, which is doubled per card and would mis-address.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the All Products listing heading is on screen. WAITS."""
        return self.is_showing(self.sel("all_products_heading"))

    def search_executed(self) -> bool:
        """True once the 'Searched Products' heading is shown — the only
        reliable signal that a search actually RAN. WAITS for it."""
        return self.is_showing(self.sel("searched_products_heading"))

    def get_result_names(self) -> list[str]:
        """Visible text of every product name in the results, in DOM order.

        The family is doubled per card, so a name may appear twice; assert
        presence with containment rather than a positional index.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_card_count(self) -> int:
        """Number of product cards currently rendered.

        Uses the product_cards family, which is NOT doubled per card, so this
        is a true card count — the right handle for asserting an empty result
        set, since this app renders no empty-state text.
        """
        return self.get_count(self.sel("product_cards"))

    def has_result(self, product_name: str) -> bool:
        """True if `product_name` appears among the result names."""
        return any(product_name in name for name in self.get_result_names())
