"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Style copied from
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY, never as literals here. Set
    INVENTORY_PAGE, then use self.sel("<element_key>").
  - methods are business verbs that say WHAT they act on
    (open_product, add_product_to_cart), never bare verbs like open()
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `product_detail` in the app inventory.

    Reached by clicking a product's View Product link on the listing (the href
    already carries the id), or by navigating directly with the id. Adding to
    cart here opens a MODAL rather than navigating, and the modal blocks the
    page underneath — dismiss it before any further interaction.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a specific product's detail page by id."""
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product and wait for the modal to open.

        The click opens a modal instead of navigating, so waiting on the modal
        confirms the action registered before a step tries to read it.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def open_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal to go to the cart."""
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Needed before any further interaction with the page underneath, which
        the modal blocks.
        """
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        it survives the add-to-cart modal opening and closing — so it is the
        reliable readiness signal.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name. WAITS for it to appear.

        Named for the value it returns rather than the DOM element; assert
        containment against the expected product name in the step definition.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price, rendered as e.g. 'Rs. 500'. WAITS for it."""
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_shown(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS, times out if not.

        Call this only where the modal is the expected outcome. A step asking
        the question to branch on the reply would pay the full timeout every
        time the answer is no.
        """
        return self.is_showing(self.sel("added_modal"))
