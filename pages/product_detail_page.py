"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the cart-management feature. Selectors come from the
`product_detail` page in the app inventory; this file never contains a literal
selector string.

Responsibilities:
  - open a product by id (or, preferably, reach it via the listing's View
    Product link, which already carries the id)
  - read the product name and price
  - set a quantity and add to cart
  - dismiss the add-to-cart modal via Continue Shopping (stay on this page)
  - navigate to the cart via the modal's View Cart link

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail. Selectors: see `product_detail` in the app inventory.

    The URL is a template — one page per product — so open_product() takes the
    product id. The add-to-cart control here is unique (unlike the listing's
    family of 68), which is why cart scenarios add products from this page.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by id.

        Args:
            base_url: application base URL from the `base_url` fixture.
            product_id: the numeric product id used in the URL template.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    def add_to_cart(self) -> None:
        """Click the single Add to cart control for this product.

        Opens a MODAL rather than navigating. The modal blocks the page
        underneath, so a scenario adding another product must dismiss it via
        continue_shopping() first.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link to the cart page.

        Only exists after add_to_cart() has been clicked. Proves the modal
        appeared and navigates to /view_cart.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product detail page is on screen. WAITS for it.

        Probes the product name heading, which is present in every state of
        this page regardless of whether a product has been added.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_detail_name(self) -> str:
        """The product's name as shown on the detail page. WAITS for it."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_detail_price(self) -> str:
        """The product's price as rendered, e.g. 'Rs. 500'. WAITS for it.

        Assert on the number, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_modal_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is EXPECTED, e.g. right after
        add_to_cart(). To branch on the modal's optional presence, use the
        non-waiting is_visible() on the modal selector instead.
        """
        return self.is_showing(self.sel("added_modal"))
