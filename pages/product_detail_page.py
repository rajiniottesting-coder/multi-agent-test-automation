"""
ProductDetailPage — the per-product details screen (/product_details/{product_id}).

Selectors: see `product_detail` in the app inventory. No literal selectors
live here — every one is resolved through self.sel("<key>").

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A single product's detail page.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the id) or by page_url(product_id=...). The add-to-cart
    control is unique here, unlike the listing's family of controls, which is
    why cart scenarios add products from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """Visible product name heading. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_loaded(self) -> bool:
        """True once the product name heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_product_to_cart(self) -> None:
        """Click Add to cart and wait for the confirmation modal to appear."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link to the cart page."""
        self.click(self.sel("view_cart_link_in_modal"))
