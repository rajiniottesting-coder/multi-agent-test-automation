"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions copied from
pages/login_page.py:

  - selectors come from the app inventory via self.sel("<key>"); no literal
    selector strings live in this file
  - methods are business verbs that name WHAT they act on (add_product_to_cart,
    open_cart_from_modal), never bare verbs
  - every method uses a BasePage helper; no raw self.page.* calls
  - waiting readers (is_*, product_name) for presence; no assertions here

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: `product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing (its href
    already carries the id) or via page_url(product_id=...). The add-to-cart
    control here is unique, unlike the listing page's family of 68.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id."""
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for this product.

        Opens a blocking modal rather than navigating; it must be dismissed or
        followed (open_cart_from_modal) before any further page interaction.
        """
        self.click(self.sel("add_to_cart_button"))

    def open_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal.

        Navigates to the cart. Confirm arrival on the destination page object
        in the step definition rather than here — this object cannot vouch for
        another page's URL.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page."""
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on the page —
        it is present on every product's detail view regardless of whether the
        add-to-cart modal or a review has been triggered.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price as rendered, e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Only call this after add_product_to_cart(); the modal does not exist on
        a freshly loaded page.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
