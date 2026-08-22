"""
ProductDetailPage — a single product's detail page (/product_details/{id}).

Selectors: see `pages.product_detail` in the app inventory. This file follows
the LoginPage reference conventions:

  - INVENTORY_PAGE names the inventory page; every selector comes from
    self.sel("<key>"), never a literal.
  - methods are business verbs that say WHAT they act on (add_product_to_cart,
    view_cart_via_modal), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - a method that clicks through to another page confirms arrival there.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage
from pages.cart_page import CartPage


class ProductDetailPage(BasePage):
    """One product's detail page. See `pages.product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (unlike the listing page's family of
    68), so this is the right place for a cart scenario to add a product.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state this page can be in, so it
        is a state-independent readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product information block.

        WAITS for it, so only call it when the detail page is expected.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear.

        Adding opens a MODAL rather than navigating; it blocks the page
        underneath, so callers must dismiss it or leave via one of its links.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_via_modal(self) -> CartPage:
        """Click 'View Cart' inside the add-to-cart modal and land on the cart.

        Returns the CartPage so the caller can read the cart it navigated to.
        Confirms arrival on the cart page to survive an ad interstitial
        swallowing the first navigation.
        """
        self.click(self.sel("view_cart_link_in_modal"))
        cart_page = CartPage(self.page)
        cart_page.confirm_arrival()
        return cart_page
