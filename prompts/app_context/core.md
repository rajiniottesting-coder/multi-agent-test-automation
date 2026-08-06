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

The PRODUCT CATALOGUE is the exception. It is shared, read-only and fixed by
the site owner: 34 products across Women / Men / Kids categories and eight
brands. Products cannot be added or deleted through the UI, so their names and
prices are stable enough to assert on. Prefer asserting that a KNOWN product
appears over asserting that N products do.

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

| Product | Price | Notes |
|---|---|---|
| `Blue Top` | Rs. 500 | First on the all-products page. The default choice. |
| `Men Tshirt` | Rs. 400 | Second. Use when a scenario needs TWO different products. |
| `Sleeveless Dress` | Rs. 1000 | A third, for a three-item cart. |

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