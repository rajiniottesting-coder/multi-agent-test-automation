"""
ProductsPage — the all-products listing (/products).

New page object for the cart-management feature. Provides navigation to the
listing and opening a product's detail page via its View Product link.

Conventions (copied from pages/login_page.py):
  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then use
    self.sel("<element_key>") — never a literal selector string.
  - Methods are business verbs that name WHAT they act on (open_listing,
    open_product), never bare verbs.
  - Every method uses a BasePage helper; no raw self.page.* calls.
  - No assertions here — those belong in step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All-products listing. Selectors: see `pages.products` in the inventory.

    Many keys on this page are MULTI-MATCH families (one per product card, and
    several are doubled per card). To act on ONE product, scope to the card
    that contains its name with click_in_row() rather than indexing — see the
    inventory's multi_match_note.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing at /products.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via its 'View Product' link.

        Scopes to the card CONTAINING the product name and clicks the View
        Product link inside that card, avoiding the multi-match family of
        links across every card.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    def search_for(self, query: str) -> None:
        """Type a query into the product search and submit it."""
        self.fill(self.sel("search_input"), query)
        self.click(self.sel("search_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the all-products listing is on screen. WAITS for it.

        Probes the 'All Products' heading, which is present on the unsearched
        listing this feature always opens.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order.

        The underlying family is doubled per card, so a name may appear twice.
        Use containment checks rather than exact counts on this result.
        """
        return self.get_all_texts(self.sel("product_names"))
