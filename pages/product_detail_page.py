"""
ProductDetailPage — the single-product page at /product_details/{product_id}.

Selectors: see `pages.product_detail` in the app inventory. This page carries
ONE add-to-cart control for its product (unlike the listing's family of 68),
so a cart scenario should add the product from here.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail. Read the product name and add the product to cart via
    its modal.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """Return the product's name as shown on the detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_loaded(self) -> bool:
        """True once the product name is visible. WAITS for it."""
        return self.is_showing(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear.

        Adding opens a MODAL rather than navigating; it blocks the page
        underneath, so the modal must be handled before any further
        interaction with this page.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal (navigates to /view_cart)."""
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))
