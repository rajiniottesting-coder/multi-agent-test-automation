"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors come from the `product_detail` page in the app inventory; this file
holds none. The page renders the product's name and price, an add-to-cart
control that opens a MODAL rather than navigating, and the two ways out of that
modal (View Cart, Continue Shopping).

Method names say WHAT they act on, per the naming rule: open_product(),
add_to_cart(), view_cart_from_modal() — never bare open() / add() / view().

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ProductDetailPage(BasePage):
    """A product detail page. Selectors: see `product_detail` in the inventory.

    The URL is a TEMPLATE (/product_details/{product_id}), so there is one such
    page per product. Prefer reaching it by clicking a product's View Product
    link on the listing — that href already carries the id — over inventing one.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer clicking the listing's View Product link where possible; this is
        for the case where only the id is known.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_to_cart(self) -> None:
        """Click this product's single Add to cart control.

        Confirms it is on this page first: filling/clicking a control that is
        not on screen does not fail fast — Playwright waits the full timeout
        and then blames the locator, which reads like a broken selector.
        Opens the add-to-cart modal rather than navigating.
        """
        self.require_own_page()
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """From the add-to-cart modal, click View Cart to go to the cart page.

        Only valid after add_to_cart() has opened the modal. This leaves the
        product detail page, so it does NOT confirm arrival here — the cart
        page object confirms the cart.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        The modal blocks the page underneath, so this is needed before any
        further interaction with the detail page once a product was added.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name in the product-information block survives every state
        this page can be in, so it is a stable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name from the product-information block. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, e.g. 'Rs. 500'. WAITS for it.

        Rendered with a currency prefix; assert on the number inside, not the
        exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))
