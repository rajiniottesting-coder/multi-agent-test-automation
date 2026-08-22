"""
ProductsPage — the all-products listing at /products.

Selectors come from the app inventory (INVENTORY_PAGE = "products"); this file
never contains a literal selector string. Methods are business verbs that name
what they act on.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    Several keys on this page are MULTI-MATCH families (product_cards,
    product_names, view_product_links). Never click, fill or assert on them as
    a whole — read them with get_all_texts(), or scope to the card containing a
    product name with click_in_row().
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> None:
        """Open a product's detail page via the View Product link in its card.

        Scopes to the card that contains `product_name` so the correct
        product's link is clicked, avoiding the multi-match family of View
        Product links across the whole listing.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products listing is on screen. WAITS for it.

        Probes the All Products heading, which is present on the unsearched
        listing this page object drives.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Visible names of every product card on the listing.

        Read-only accessor over the multi-match product_names family. Use it to
        assert a product IS present rather than indexing into the family.
        """
        return self.get_all_texts(self.sel("product_names"))
