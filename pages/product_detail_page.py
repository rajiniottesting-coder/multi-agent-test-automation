"""
ProductDetailPage — a single product's detail screen (/product_details/<id>).

Selectors: see `pages.product_detail` in the app inventory. Reached by clicking
a product's View Product link on the listing (the href already carries the id),
or opened directly with page_url(product_id=...).

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Reads name and price, adds to cart, and
    dismisses or follows the add-to-cart modal.

    The add-to-cart control here is UNIQUE (unlike the listing's family of 68),
    so a cart scenario should add a product from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name in the product-information block, which is
        present in every state of this page.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible product name shown in the product-information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price, rendered as e.g. 'Rs. 500'.

        Assert on the number, not the format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Only call after clicking Add to cart. The modal is conditional and
        absent from a freshly loaded page.
        """
        return self.is_showing(self.sel("added_modal"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click this product's Add to cart control.

        Opens the add-to-cart modal rather than navigating; the modal blocks
        the page underneath until it is dismissed or followed.
        """
        self.click(self.sel("add_to_cart_button"))

    def view_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Navigates to the cart. Only valid after add_product_to_cart().
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, which
        the modal blocks.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))
