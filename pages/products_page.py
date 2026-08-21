"""
ProductsPage — the all-products listing at /products.

Selectors come from `pages.products` in the app inventory. This page object
navigates to the listing and opens a named product via its View Product link.

The listing renders several families that match many elements at once
(product_cards, product_names, add_to_cart_buttons, view_product_links), some
of them DOUBLED per card. This class never clicks a family directly: to open a
named product it scopes to the card containing that product's name via
click_in_row(), so the strict-mode traps in the inventory notes do not apply.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory."""

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the all-products listing page.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is not duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> None:
        """Open a named product's detail page via its View Product link.

        Scopes to the product CARD containing the given name and clicks the
        View Product link inside it, avoiding the multi-match / doubled-family
        traps. Confirms arrival on the product detail page, so a swallowed
        interstitial navigation cannot leave the browser behind on the listing.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        ProductDetailPage(self.page).confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        Uses the unsearched-listing heading, which is present on the plain
        /products page this class always navigates to. (A search would replace
        it with the searched-products heading, but this class never searches.)
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Return all visible product names on the listing.

        Reads the multi-match product_names family with the plural reader; use
        this to assert a product IS present rather than indexing into it.
        """
        return self.get_all_texts(self.sel("product_names"))
