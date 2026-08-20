"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

Selectors: see `pages.product_detail` in the app inventory. No page object
existed for this page before, so the method names are chosen here per the
naming rule: a method must say WHAT it acts on (add_to_cart, product_name),
never a bare verb.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: `pages.product_detail` in the inventory.

    Reached by clicking a product's View Product link on the listing — that
    href already carries the product id, so tests never invent one. Adding to
    cart here opens a MODAL rather than navigating; the modal blocks the page
    underneath, so dismiss it (Continue Shopping) or leave via View Cart.
    """

    INVENTORY_PAGE = "product_detail"

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """Return the product name shown in the product information block."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_loaded(self) -> bool:
        """True once the product name is on screen. WAITS for it."""
        return self.is_showing(self.sel("product_name"))

    # ── actions ──────────────────────────────────────────────
    def add_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        Opens the add-to-cart modal rather than navigating. Follow with
        open_cart_from_modal() or dismiss_added_modal() before any further
        interaction with the page underneath.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal to go to the cart."""
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def dismiss_added_modal(self) -> None:
        """Click Continue Shopping to close the modal and stay on this page."""
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))
