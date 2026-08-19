"""
ProductDetailPage — a single product's /product_details/<id> screen.

Selectors come from `pages.product_detail` in the app inventory; this file
never contains a literal selector string. Methods are business verbs that name
what they act on (open_product, add_product_to_cart), per the naming rule.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A product detail page. Selectors: see `pages.product_detail` in the
    app inventory.

    Adding to cart opens a MODAL rather than navigating; it blocks the page
    underneath, so callers must either leave via View Cart or dismiss it with
    Continue Shopping before touching the page again.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for this product and wait for the modal."""
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Follow the View Cart link inside the add-to-cart modal."""
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def product_name(self) -> str:
        """Return the product's name as shown on the detail page."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def is_added_modal_shown(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it."""
        return self.is_showing(self.sel("added_modal"))
