"""
ProductsPage — the all-products listing at /products.

Selectors come from `pages.products` in the app inventory; this file never
holds a literal selector. Methods are business verbs that name what they act
on (open_listing, open_product), per the naming rule.

The listing renders each product card's controls TWICE (card + hover overlay),
so add-to-cart and product-name families match double. Cart scenarios add
products from the DETAIL page instead; this page's only job here is to reach a
product's detail page via its exact-href View Product link.

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

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open a product's detail page via the View Product link in its card.

        Scopes to the card containing `product_name` before clicking, because
        the View Product link is a family — one per card — and clicking the
        family directly is a strict-mode violation. Confirms arrival on the
        detail page so a consumed navigation (ad interstitial) is recovered
        rather than surfacing as a timeout several steps later.

        Returns the ProductDetailPage for the opened product.
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
        """True once the All Products listing is on screen. WAITS for it.

        Probes the All Products heading — the state-independent readiness
        signal for the unsearched listing this page object drives.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def get_product_names(self) -> list[str]:
        """Every product name on the listing, in DOM order.

        Reads the multi-match name family with the plural accessor. Assert a
        product IS present with containment rather than indexing into this.
        """
        return self.get_all_texts(self.sel("product_names"))
