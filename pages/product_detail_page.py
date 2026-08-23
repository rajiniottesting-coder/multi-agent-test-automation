"""
ProductDetailPage — a single product's detail screen (/product_details/<id>).

New page object for the shopping-session feature. Responsibilities:
  - read the displayed product name
  - add THIS product to the cart (opens a modal rather than navigating)
  - leave the modal by going to the cart

Selectors come from the app inventory (`product_detail`), never from literals
here. Method names say WHAT they act on, per the naming rule.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail. Selectors: see `product_detail` in the app inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: str) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page by clicking a product's View Product link on
        the listing, since that href already carries the id. This exists for
        scenarios that address a product by id explicitly.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal to open.

        Adding opens a modal rather than navigating, and the modal blocks the
        page underneath. Waiting for it here means the caller can immediately
        choose an exit (View Cart / Continue Shopping) without racing it.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def go_to_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link, landing on the cart page.

        Leaves this page, so it does NOT call confirm_arrival() here — that
        belongs to the cart page object, which owns the destination URL.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state this page can be in, so it
        is a reliable readiness signal — unlike the add-to-cart modal, which
        exists only after a click.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def get_product_name(self) -> str:
        """The displayed product name. WAITS for it to appear.

        Call this to assert the correct product loaded, e.g. after clicking a
        View Product link.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))
