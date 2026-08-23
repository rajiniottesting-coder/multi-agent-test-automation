"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions follow
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY. Set INVENTORY_PAGE, then use
    self.sel("<element_key>"); never a literal selector.
  - methods are business verbs that say WHAT they act on (open_product,
    add_product_to_cart), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those belong in step definitions.
  - the add-to-cart modal is CONDITIONAL: it does not exist until Add to cart
    is clicked, so methods that touch it must be called only after adding.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """One product's detail page. Selectors: see `pages.product_detail` in the
    app inventory.

    The URL is a TEMPLATE (/product_details/{product_id}), one page per
    product. Prefer reaching this page by clicking a product's View Product
    link on the listing — that href already carries the id, so a test never
    invents one — and confirm arrival here.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Args:
            base_url: application base URL from the `base_url` fixture.
            product_id: the numeric product id that fills the URL template.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the add-to-cart modal.

        This is the single, unique add-to-cart control for the product — unlike
        the listing page's family of many buttons. The modal appears in place
        rather than navigating.
        """
        self.click(self.sel("add_to_cart_button"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        Only valid after add_product_to_cart(): the modal and its close button
        do not exist until a product has been added. The modal blocks the page
        underneath, so this must be called before any further interaction here.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("continue_shopping_button"))
        self.wait_hidden(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Follow the add-to-cart modal's View Cart link to the cart page.

        Only valid after add_product_to_cart(): the modal is where this link
        lives. Navigates away from this page, so no confirm_arrival() here —
        the cart page object confirms its own arrival.
        """
        self.wait_visible(self.sel("added_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element on this page —
        it is present whether or not the add-to-cart modal is open — so it is
        the right readiness probe.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as displayed. WAITS for it to appear."""
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text (rendered as 'Rs. 500'). WAITS for it.

        Returns the raw price string; a caller asserting on the number should
        match on it rather than requiring an exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_add_to_cart_modal_showing(self) -> bool:
        """True once the add-to-cart modal is visible. WAITS for it.

        Call this only where the modal is expected — for asserting the
        'Added!' confirmation appeared after Add to cart.
        """
        return self.is_showing(self.sel("added_modal"))
