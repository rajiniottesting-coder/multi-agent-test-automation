"""
ProductsPage — the All Products listing (/products).

Navigation surface for cart scenarios: the shopper opens a named product's
details page by clicking the 'View Product' link on that product's card. This
page object does NOT add to cart from the listing — the listing's add-to-cart
family matches 68 elements (doubled per card) and is a strict-mode trap; adding
belongs on the product detail page, which exposes a single unique control.

Selectors: see `products` in the app inventory. No literals live here.

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the inventory.

    The product_cards / product_names / add_to_cart_buttons / view_product_links
    keys are MULTI-MATCH (and the names/buttons are doubled per card). Never act
    on them as a family — scope to the card that contains the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def open_product_details(self, product_name: str) -> None:
        """Open the details page for the named product via its View Product link.

        Scopes to the product CARD containing the name and clicks the View
        Product link inside that card, so the multi-match link family never has
        to be addressed as a whole. Confirms it is on the listing first — a
        scenario that reached this without opening the listing would otherwise
        pay a full timeout and blame the link selector.
        """
        self.require_own_page()
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the All Products heading is on screen. WAITS for it.

        The All Products heading is the state-independent readiness signal on
        the unsearched listing — it is present whenever this page is simply
        navigated to, before any search replaces it.
        """
        return self.is_showing(self.sel("all_products_heading"), timeout_ms=timeout_ms)

    def product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order.

        Reads the multi-match name family with the plural helper. The names are
        doubled per card (card + hover overlay), so expect duplicates — use this
        for containment checks ('is this product listed?'), not for counting.
        """
        return self.get_all_texts(self.sel("product_names"))
