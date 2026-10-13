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

## The product detail page

Reached by clicking a product's `View Product` link, as above. It shows the
product's name, its price, and three labelled facts: `Availability:`,
`Condition:` and `Brand:`.

- **Price** is rendered as `Rs. 500`. Expect the NUMBER from the product table
  in `core.md` - `Blue Top` is 500, `Men Tshirt` is 400 - not the formatted
  string.
- **Availability, Condition and Brand** are shown as labels. A scenario can
  check that each label is present. Do not assert a particular VALUE for them:
  nothing here records those values, and an invented one fails in the browser.
- **Quantity** is no longer chosen here: there is no quantity input. Each click
  of Add to cart puts exactly one item in the cart, and adding the same product
  again raises its cart quantity by one. "Add 3 of a product" means: add it three
  times.
- **Add to cart** here is a single control for this product, and it opens the
  same confirmation modal as the listing - see `cart.md`.

### Writing a review

Every product detail page has a review form: a name, an email address, review
text and a submit button. A successful submission shows
**"Thank you for your review."** in place - there is no navigation.

All three fields are required. Submitting with any of them empty is blocked by
the browser's own validation, so nothing app-authored appears and the thank-you
message never renders. That makes "an incomplete review is not accepted" a
legitimate negative case: assert that the thank-you message does NOT appear.
Do not expect an error message from the application - there is none.

The reviewer's name and email are test data, not credentials: write them
literally, for example `Demo Reviewer` and `reviewer@example.com`. Nothing here
records whether a submitted review is displayed on the page afterwards, so do
not write a test case asserting that it is.

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

**And the HEADING does not change either.** An empty submission does not run a
search, so the listing keeps its unsearched heading; the "searched" heading
never appears. A scenario about an empty query that waits for the searched
heading times out after thirty seconds and reports a missing element, which
reads as a broken selector and is nothing of the kind — the page is exactly
where it should be. Assert the unsearched heading, or assert the product
count, but do not use the searched heading as the signal that an empty query
was submitted.

The two cases are different behaviours and belong in different scenarios;
combining them into one ("a nonexistent product AND an empty query return no
cards") makes a scenario that cannot pass, because half of it is false.

Category and brand links navigate to `/category_products/<id>` and
`/brand_products/<name>` respectively — both are ordinary links, not filters
applied in place.