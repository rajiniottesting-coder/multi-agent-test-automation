"""
ProductDetailPage — a single product's detail screen (/product_details/{product_id}).

Selectors: see `pages.product_detail` in the app inventory. No literal
selectors live here — every element is resolved with self.sel("<key>").

The add-to-cart control on THIS page is unique (unlike the listing page's
family of 68), so adding a product from here is reliable. Adding opens a
blocking modal rather than navigating; use view_cart_from_modal() to leave for
the cart, or dismiss_added_modal() to stay on this page.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: `pages.product_detail` in the inventory."""

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name element, which is present in every state this
        page can be in (before and after adding to cart).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's displayed name. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's displayed price, e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart confirmation modal is showing. WAITS.

        Call this only where the modal is EXPECTED — it times out if the modal
        never appears rather than returning False.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)

    # ── actions ──────────────────────────────────────────────
    def set_quantity(self, quantity: int) -> None:
        """Set the desired quantity BEFORE adding to cart.

        Changing this after adding does not update the cart.
        """
        self.fill(self.sel("quantity_input"), str(quantity))

    def add_product_to_cart(self) -> None:
        """Click the single add-to-cart control for this product.

        Opens a blocking modal rather than navigating. Follow with
        view_cart_from_modal() or dismiss_added_modal().
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def dismiss_added_modal(self) -> None:
        """Close the add-to-cart modal via 'Continue Shopping' and stay here.

        The modal blocks the page underneath, so this is required before any
        further interaction with the product page.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click 'View Cart' in the add-to-cart modal to go to the cart page.

        Proves the modal appeared and navigates to /view_cart.
        """
        self.click(self.sel("view_cart_link_in_modal"))
