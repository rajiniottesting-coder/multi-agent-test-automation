"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors live in the app inventory under `pages.product_detail`; this file
never carries a literal selector. See pages/login_page.py for the conventions
this class follows: business-verb methods, BasePage helpers only, no assertions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail`.

    Reached by clicking a product's View Product link on the listing, which
    carries the id in its href, so a test never has to invent one. The add-to
    -cart control here is unique (the listing renders a family of 68), which is
    why a cart scenario adds its product from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """The product's displayed name. WAITS for it to render."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart, which opens the confirmation modal.

        Adding does not navigate — a modal appears over the page. WAITS for the
        modal so callers can immediately act on View Cart / Continue Shopping.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to go to the cart."""
        self.click(self.sel("view_cart_link_in_modal"))
