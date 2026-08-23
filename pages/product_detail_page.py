"""
ProductDetailPage — a single product's detail screen (/product_details/{id}).

New page object for the shopping-session feature. Conventions copied from
pages/login_page.py:

  - SELECTORS COME FROM THE APP INVENTORY. Declare INVENTORY_PAGE, then use
    self.sel("<element_key>"); never a literal selector string.
  - methods are business verbs that say WHAT they act on (open_product,
    add_product_to_cart), never bare verbs.
  - every method uses a BasePage helper; no raw self.page.* calls.
  - no assertions here — those live in the step definitions.

App: https://automationexercise.com
"""
from typing import Optional

from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """A product's detail page. Selectors: see `product_detail` in the inventory.

    The URL is a TEMPLATE (/product_details/{product_id}); the preferred way
    to arrive is by clicking a product's View Product link on the listing,
    which already carries the id. open_product() is the direct-navigation
    fallback for scenarios that know the id.
    """

    INVENTORY_PAGE = "product_detail"

    # ── actions ──────────────────────────────────────────────
    def open_product(self, base_url: str, product_id: int) -> None:
        """Navigate directly to a product's detail page by its id.

        Args:
            base_url: application base URL from the `base_url` fixture.
            product_id: the numeric product id used in the URL template.
        """
        path = self.page_url(product_id=product_id)
        self.navigate(f"{base_url.rstrip('/')}{path}")
        self.confirm_arrival(product_id=product_id)

    def add_product_to_cart(self) -> None:
        """Click Add to cart for THIS product, opening the add-to-cart modal.

        Unlike the listing page's family of controls, this is the single,
        unique add-to-cart button for the product on this page.
        """
        self.click(self.sel("add_to_cart_button"))
        self.wait_visible(self.sel("added_modal"))

    def view_cart_from_modal(self) -> None:
        """Click View Cart inside the add-to-cart modal, going to the cart.

        Confirms the modal is up first — the link only exists once the product
        has been added.
        """
        self.wait_visible(self.sel("view_cart_link_in_modal"))
        self.click(self.sel("view_cart_link_in_modal"))

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal and stay on this product page.

        The modal blocks the page underneath, so this is required before any
        further interaction with the page after adding to cart.
        """
        self.wait_visible(self.sel("continue_shopping_button"))
        self.click(self.sel("continue_shopping_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the product name is on screen. WAITS for it.

        The product name is the most state-independent element here: it is
        present regardless of whether the add-to-cart modal or a review form
        has been triggered.
        """
        return self.is_showing(self.sel("product_name"), timeout_ms=timeout_ms)

    def product_name(self) -> str:
        """The product's name as shown in the product information block.

        WAITS for it to be visible before reading.
        """
        self.wait_visible(self.sel("product_name"))
        return self.get_text(self.sel("product_name"))

    def product_price(self) -> str:
        """The product's price text, e.g. 'Rs. 500'. WAITS for it.

        Assert on the number within, not the exact format.
        """
        self.wait_visible(self.sel("product_price"))
        return self.get_text(self.sel("product_price"))

    def is_added_modal_showing(self) -> bool:
        """True once the add-to-cart confirmation modal is visible. WAITS.

        Call this only where the modal is EXPECTED. It times out and returns
        False if the modal never appears, so do not use it to branch.
        """
        return self.is_showing(self.sel("added_modal"))
