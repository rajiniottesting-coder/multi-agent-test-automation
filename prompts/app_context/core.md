# Application under test — Automation Exercise

An e-commerce practice site: browse products, search, add to cart, register an
account, place an order.

- URL: https://automationexercise.com
- Signup and login share one page at `/login`.
- After a successful login the user lands on `/` with "Logged in as <name>" in
  the top navigation.

## The single most important property: TEST-OWNED DATA

Unlike a shared admin demo, an account here is YOURS. A registered user's cart,
address book and order history cannot be seen or changed by anyone else. Build
every assertion on data the test itself created — a user it registered, a cart
it filled.

**PRIVATE IS NOT THE SAME AS EMPTY.** That account's state SURVIVES logout, and
survives the end of the run. A scenario that added something and then failed
before removing it leaves that item behind, and the next run finds it: a cart
expected to hold one product holds two, and a cart expected to be empty after a
removal still shows the leftover. The test is correct; its starting assumption
is not.

So a scenario that asserts an ABSOLUTE end state — "the cart is empty", "there
are two items" — must own its starting state. Two ways, in order of preference:

| | |
|---|---|
| **Register a fresh account** | Use the `unique_username` fixture. A brand-new account starts with a genuinely empty cart, every time, with nothing to clean up. This is the only option that cannot be defeated by a previous run. |
| **Empty it first** | Sign in as the shared role, then remove everything before the scenario's own actions. Works, but a run killed mid-way still leaves state behind for the next one. |

If neither is practical, assert RELATIVELY instead: that the cart contains the
product this test added, or that its count went up by one. A relative assertion
is true whatever the account started with.

Scenarios that only READ — searching, browsing, viewing a product — need none
of this. It applies to anything that adds, removes or changes account state.

The PRODUCT CATALOGUE is the exception. It is shared, read-only and fixed by
the site owner: 34 products across Women / Men / Kids categories and eight
brands. Products cannot be added or deleted through the UI, so a product's
name is stable enough to assert on. Prefer asserting that a KNOWN product
appears over asserting that N products do.

A product's PRICE is equally stable, but it is only READABLE on that
product's own detail page. The listing and the search results expose the
product NAME and nothing else, so a test case that asks for a price to be
verified must first open the product. A test case whose expected result
names a price on the listing cannot be automated as written.

## Known test identities

Test cases refer to users by ROLE. Credentials are never stored here, in the
app inventory, or in any generated file — they are resolved at runtime from
environment variables (GitHub Secrets in CI).

| Role | Behaviour |
|---|---|
| `registered` | A pre-registered account used for login scenarios. |

This app has no privilege levels: every account can do the same things. Where a
scenario needs a BRAND NEW account it must register one itself rather than
reuse the shared role — see `account.md`.

Invalid data is different and SHOULD be explicit: empty values, malformed email
addresses and deliberately-wrong passwords are test data, not credentials, so
write them literally in the test case.

## Known products — use these names, do not invent one

The catalogue is read-only: nothing in the UI adds or removes a product, so a
named product is safe to assert on and safe to reuse across scenarios.

| Product | Price (detail page only) | Notes |
|---|---|---|
| `Blue Top` | Rs. 500 | First on the all-products page. The default choice. |
| `Men Tshirt` | Rs. 400 | Second. Use when a scenario needs TWO different products. |
| `Sleeveless Dress` | Rs. 1000 | A third, for a three-item cart. |

The price column is here so a detail-page scenario has a value to expect.
It is not available on the listing: pairing one of these prices with a
search or a browse step produces a test case nothing on that page can
satisfy.

**A scenario must name the product it acts on.** "Search for a product" is not
a test case; "search for `Blue Top`" is. An invented name — `Red Shirt`, `Test
Product` — produces code that is valid, passes every static check, and then
fails at runtime because the row is never found. Nothing catches that before a
browser runs, which makes it one of the more expensive ways to be wrong.

If a scenario genuinely needs an arbitrary product rather than a specific one,
say so explicitly ("the first product in the list") and reach it by position,
not by a guessed name.

## Page flow (end to end)

    /  →  /login  →  register  →  /account_created  →  logged in
                  →  login     →  logged in

    /  →  /products  →  /product_details/<id>  →  cart  →  checkout  →  payment

## Global rules

- **Server-rendered, not a single-page app.** Every navigation is a full page
  load. When the new page has arrived it is FINISHED: nothing appears later, no
  component re-renders underneath you, no model rebinds. Waits remain correct
  practice, but the async traps of an SPA do not apply here.
- The top navigation and the footer subscription block are on every page.
- **Adding to cart opens a MODAL**, it does not navigate. The modal offers
  "View Cart" and "Continue Shopping"; one must be taken before the page is
  usable again.
- **Product cards render "Add to cart" TWICE** — once in the card and once in
  the hover overlay. Any selector for it matches at least two elements per
  product, so it is a family: see `multi_match` on the products page.
- The site carries third-party ads, which shift layout and occasionally overlay
  content. That is a real source of "element is not stable" and "intercepts
  pointer events" failures. Prefer scrolling into view and asserting on text
  over asserting on position.