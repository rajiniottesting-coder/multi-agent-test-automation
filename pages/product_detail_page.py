"""
ProductDetailPage — a single product's detail screen (/product_details/<id>).

Selectors: see `pages.product_detail` in the app inventory. This file never
contains a literal selector — every element is looked up by its inventory key
via self.sel("<key>").

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page.

    Reached by clicking a product's View Product link on the listing, which
    carries the product id in its href, so the test never invents an id. The
    add-to-cart control here is unique (unlike the listing's family of 68),
    which is why a cart scenario should add a product from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name heading, which is present in every state this
        page can be in (before and after the add-to-cart modal is opened).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as e.g. 'Rs. 500'.

        Assert on the number rather than the exact format.
        """
        return self.get_text(self.sel("product_price"))

    def is_added_modal_showing(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS."""
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for this product, opening the confirmation modal.

        The modal blocks the page underneath, so callers must either navigate
        away via view_cart_from_modal() or dismiss it with
        continue_shopping() before interacting with the page again.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Navigates to /view_cart, which also proves the modal appeared.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, since
        the modal blocks it.
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
