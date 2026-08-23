"""
ProductsPage — the /products all-products listing.

Selectors come from the app inventory (page key `products`); this file never
contains a literal selector. Business verbs name what they act on.

App: https://automationexercise.com
"""
from pages.base_page import BasePage


class ProductsPage(BasePage):
    """All-products listing and search. Selectors: see `products` in the app
    inventory.

    Readiness note: the listing has no single `readiness` key, so is_loaded()
    probes all_products_heading — the heading shown on the unsearched listing,
    which is the state the page is in when open_products() lands on it. After a
    search this heading is replaced by searched_products_heading, so callers
    that have searched should assert on has_searched() instead.

    Several selectors on this page are families (multi_match). They are read
    with the plural helpers only; to open one product's detail the View Product
    link is scoped to the card containing the product name.
    """

    INVENTORY_PAGE = "products"

    # ── actions ──────────────────────────────────────────────
    def open_products(self, base_url: str) -> None:
        """Navigate to the all-products listing."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")
        self.confirm_arrival()

    def search_for(self, term: str) -> None:
        """Enter a search term and submit; the results render on this page."""
        self.fill(self.sel("search_input"), term)
        self.click(self.sel("search_button"))

    def open_product_detail(self, product_name: str) -> None:
        """Open the detail page for `product_name` via its View Product link.

        The View Product links are a family, one per card, so this scopes to
        the card containing the product name rather than indexing across the
        doubled name/button families. The product-image wrapper card carries
        both the name and the link, so click_in_row finds the right one.
        """
        self.click_in_row(
            self.sel("product_cards"),
            product_name,
            self.sel("view_product_links"),
        )

    def continue_shopping(self) -> None:
        """Dismiss the add-to-cart modal, staying on the current page.

        Only valid after a product has been added, since the modal does not
        exist otherwise.
        """
        self.click(self.sel("continue_shopping_button"))

    def view_cart_from_modal(self) -> None:
        """Follow the modal's View Cart link, navigating to the cart."""
        self.click(self.sel("view_cart_link_in_modal"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self) -> bool:
        """True once the unsearched all-products listing is on screen. WAITS.

        Probes all_products_heading, the state-independent heading for the
        listing before any search runs. Call this only where the listing is
        expected; to confirm a SEARCH executed, use has_searched().
        """
        return self.is_showing(self.sel("all_products_heading"))

    def has_searched(self) -> bool:
        """True once a search has executed. WAITS, and times out if none has.

        The Searched Products heading is the only reliable signal that the
        search ran — a result count alone cannot tell an empty result from a
        page that still shows the full catalogue. Call this only where a
        search is expected to have run; it waits and will time out otherwise.
        """
        return self.is_showing(self.sel("searched_products_heading"))

    def get_product_names(self) -> list[str]:
        """Return every product name currently rendered, in DOM order.

        The name family is doubled per card (card plus hover overlay), so this
        list may contain each name twice. Use it for containment checks such as
        'the results contain X', not for an exact count.
        """
        return self.get_all_texts(self.sel("product_names"))

    def get_result_count(self) -> int:
        """Return the number of product CARDS currently rendered.

        Reads product_cards, which is one element per card and NOT doubled, so
        this is the honest card count. An empty search renders zero cards
        rather than an empty-state message, so a count of 0 is how absence of
        results is asserted on this page.
        """
        return self.get_count(self.sel("product_cards"))

    def has_product(self, product_name: str) -> bool:
        """True if a card for `product_name` is present in the results.

        WAITS for the card to appear, so call this only where the product is
        expected. Scoped to the product-image card family.
        """
        self.wait_for_row(self.sel("product_cards"), product_name, present=True)
        return True
