"""
ProductsPage — the /products all-products listing.

New page object for the cart-management feature. It opens the listing and,
from it, opens a named product's detail page via that product's View Product
link.

Selectors: see `pages.products` in the app inventory. This file never contains
a literal selector — every element is resolved through self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All-products listing. Selectors: see `pages.products` in the inventory.

    Many of this page's keys are MULTI-MATCH families (product_cards,
    product_names, add_to_cart_buttons, view_product_links) — several match
    once per card, and some render twice per card. Never click or assert on a
    family as a whole. To open one product, scope to the card containing its
    name with click_in_row().
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the /products all-products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The
                      path comes from the inventory, so it is never duplicated.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open the detail page for the named product via its View Product link.

        Scopes to the product card that contains `product_name` and clicks the
        View Product link inside THAT card, so the click never touches another
        product's link or the doubled hover-overlay controls. Confirms arrival
        on the product detail page before returning its page object.

        Args:
            product_name: visible product name, e.g. "Blue Top".

        Returns:
            A ProductDetailPage for the product just opened.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        detail = ProductDetailPage(self.page)
        detail.confirm_arrival()
        return detail

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        The inventory marks all_products_heading as the listing's readiness
        signal: it is present on the unsearched listing regardless of which
        products render.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order.

        product_names is a MULTI-MATCH family (and doubled per card), so this
        reads the whole family with get_all_texts rather than indexing.
        """
        return self.get_all_texts(self.sel("product_names"))
