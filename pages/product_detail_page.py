"""
ProductDetailPage — a single product's detail screen (/product_details/<id>).

Selectors come from the app inventory (page key `product_detail`); this file
never contains a literal selector string. Business-verb methods only; every
method uses a BasePage helper.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """Product detail page. Selectors: see `product_detail` in the inventory.

    The add-to-cart control here is UNIQUE (unlike the listing page's family
    of 68), which is why a cart scenario should add a product from this page.
    Adding opens a MODAL that blocks the page underneath — dismiss it, or leave
    via 'View Cart', before any further interaction.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Prefer reaching this page via a listing 'View Product' link, whose
        href already carries the id. This direct route exists for tests that
        already hold an id.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url(product_id=product_id)}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for this product and wait for the modal.

        Adding opens a modal rather than navigating; waiting for it here means
        callers do not race the modal render.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the 'View Cart' link inside the add-to-cart modal.

        Navigates to the cart, so it also proves the modal appeared.
        """
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Required before any further interaction with the page underneath,
        because the modal blocks it.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is present in every state of this page, which makes
        it a stable readiness probe (the inventory carries no `readiness`
        key for this page).
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """Visible product name (e.g. 'Blue Top'). WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """Visible product price text (rendered as 'Rs. 500'). WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_add_modal_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is expected. To branch on the modal
        being optional, use is_visible() on the same key directly.
        """
        return self.is_showing(self.sel("added_modal"), timeout_ms=timeout_ms)
