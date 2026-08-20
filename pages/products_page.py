"""
ProductsPage — the All Products listing at /products.

Selectors: see `pages.products` in the app inventory. This page object only
opens the listing and navigates to a product's detail page via that product's
View Product link. Adding to cart happens on the detail page, where the
add-to-cart control is unique rather than a family of 68.

App: https://automationexercise.com
"""
from pages.base_page import BasePage
from pages.product_detail_page import ProductDetailPage


class ProductsPage(BasePage):
    """All Products listing. Selectors: see `pages.products` in the app inventory.

    The listing renders each card's name and Add to cart control TWICE (card
    plus hover overlay), so those families are doubled. This page object never
    acts on the Add to cart family — a cart scenario opens the product detail
    page via View Product and adds from there, where the control is unique.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_listing(self, base_url: str) -> None:
        """Navigate to the All Products listing.

        Args:
            base_url: application base URL from the `base_url` fixture. The path
                      comes from the inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def open_product(self, product_name: str) -> ProductDetailPage:
        """Open the detail page for the named product via its View Product link.

        Scopes to the card containing the product name and clicks the View
        Product link inside that card, so the doubled families on this page are
        never touched as a whole. Confirms arrival on the destination page.

        Returns:
            A ProductDetailPage bound to the same browser page.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )
        detail_page = ProductDetailPage(self.page)
        detail_page.confirm_arrival()
        return detail_page

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the All Products listing is on screen. WAITS for it."""
        return self.is_showing(self.sel("all_products_heading"))

    def get_product_names(self) -> list[str]:
        """Every product name shown on the listing, in DOM order.

        The name family is doubled per card, so a name appears twice; use this
        for containment assertions (a product IS present), not for counting.
        """
        return self.get_all_texts(self.sel("product_names"))
