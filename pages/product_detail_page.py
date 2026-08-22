"""
ProductDetailPage — a single product's detail screen.

Selectors come from `pages.product_detail` in the app inventory; this file
never contains a literal selector. Reached by clicking a product's View Product
link on the listing (the href already carries the product id), so there is no
open-by-id method here — the listing page owns navigation.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: `pages.product_detail` inventory.

    The add-to-cart control here is unique (unlike the listing's family of 68),
    so a cart scenario adds a product from this page. Adding opens a blocking
    modal; dismiss it with continue_shopping() before touching the page again,
    or leave via view_cart() to reach the cart.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click Add to cart for this product. Opens the confirmation modal."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath: the
        modal blocks it. Waits for the modal to close so the next click lands.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart(self) -> None:
        """Follow the modal's View Cart link to the cart page.

        Confirms arrival on the cart, recovering from an ad interstitial that
        may have swallowed the navigation.
        """
        from pages.cart_page import CartPage

        self.click(self.sel("view_cart_link_in_modal"))
        CartPage(self.page).confirm_arrival()

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name heading, which is present in every state of
        this page.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible product name for this detail page."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price, rendered like 'Rs. 500'."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_modal_showing(self) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS.

        Call this only where the modal is expected — it is the presence signal
        after add_to_cart(). Times out rather than returning False if the modal
        never appears.
        """
        return self.is_showing(self.sel("added_modal"))
