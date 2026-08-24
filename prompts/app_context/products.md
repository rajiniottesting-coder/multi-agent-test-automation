# Products, search and categories

## Catalogue shape (stable, read-only)

34 products. Categories are Women (Dress, Tops, Saree), Men (Tshirts, Jeans)
and Kids (Dress, Tops & Shirts). Eight brands: Polo (6), H&M (5), Madame (5),
Mast & Harbour (3), Babyhug (4), Allen Solly Junior (3), Kookie Kids (3),
Biba (5).

Nothing in the UI can add or remove a product, so a named product is a safe
thing to assert on. The names to use are in `core.md` — `Blue Top` (Rs. 500),
`Men Tshirt` (Rs. 400) and `Sleeveless Dress` (Rs. 1000). Do not invent one:
an unknown name compiles, passes every static check, and then fails in the
browser because the row is never found.

## Reaching one specific product

A product detail page is `/product_details/<id>`, and the id is NOT something a
scenario should carry. Reach the page by clicking that product's `View Product`
link on the listing — the href already holds the right id, so the test works
whatever the catalogue contains and never hardcodes a number.

The same applies to adding one product to the cart. On the listing, the
add-to-cart control is a FAMILY of 68 and clicking it is rejected at generation
time; on the product detail page it is unique. So a scenario that adds a
NAMED product should open its detail page first.

## Every product card is a FAMILY

Each card renders its price, its name and its "Add to cart" control TWICE —
once in the card body and once in the hover overlay. So:

- a selector for a product name matches 2 elements PER PRODUCT
- a selector for "Add to cart" matches 68 elements on the all-products page

Read them with `get_all_texts()` / `get_count()`. To act on ONE product, scope
by the product's own container or use the `View Product` link, which is unique
per card and carries the product id in its href.

The card's price is deliberately NOT in the inventory. `product_names` is the
only text this page exposes, so a price shown on a card cannot be read here
and must not be asserted here. `product_detail.product_price` is unique, and
is where a price assertion belongs.

## Search

Search lives on `/products`, submits to the same page, and matches on product
NAME. A search returning nothing renders no result cards rather than an
explicit "no results" message, so assert absence by counting result cards, not
by looking for empty-state text.

### An EMPTY query returns the WHOLE catalogue, not zero results

Submitting the search box with nothing in it matches everything — the page
comes back with every product on it. A scenario asserting no result cards for
an empty query is asserting something untrue about this application, and it
fails with the full catalogue in the message.

```
Expected zero result cards, got ['<product>', '<product>', ... 34 items]
```

So do NOT write a test case like "an empty search returns no results". If a
scenario needs a search with no matches, use a term that genuinely matches
nothing — a made-up string. If it needs to describe the empty-query
behaviour, the honest expectation is that the full listing is shown.

The two cases are different behaviours and belong in different scenarios;
combining them into one ("a nonexistent product AND an empty query return no
cards") makes a scenario that cannot pass, because half of it is false.

Category and brand links navigate to `/category_products/<id>` and
`/brand_products/<name>` respectively — both are ordinary links, not filters
applied in place.