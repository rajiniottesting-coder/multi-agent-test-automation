# Products, search and categories

## Catalogue shape (stable, read-only)

34 products. Categories are Women (Dress, Tops, Saree), Men (Tshirts, Jeans)
and Kids (Dress, Tops & Shirts). Eight brands: Polo (6), H&M (5), Madame (5),
Mast & Harbour (3), Babyhug (4), Allen Solly Junior (3), Kookie Kids (3),
Biba (5).

Nothing in the UI can add or remove a product, so a named product is a safe
thing to assert on. "Blue Top" at Rs. 500 and "Men Tshirt" at Rs. 400 are the
first two on the all-products page.

## Every product card is a FAMILY

Each card renders its price, its name and its "Add to cart" control TWICE —
once in the card body and once in the hover overlay. So:

- a selector for a product name matches 2 elements PER PRODUCT
- a selector for "Add to cart" matches 68 elements on the all-products page

Read them with `get_all_texts()` / `get_count()`. To act on ONE product, scope
by the product's own container or use the `View Product` link, which is unique
per card and carries the product id in its href.

## Search

Search lives on `/products`, submits to the same page, and matches on product
NAME. A search returning nothing renders no result cards rather than an
explicit "no results" message, so assert absence by counting result cards, not
by looking for empty-state text.

Category and brand links navigate to `/category_products/<id>` and
`/brand_products/<name>` respectively — both are ordinary links, not filters
applied in place.
