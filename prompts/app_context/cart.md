# Cart and checkout

## Adding to cart opens a modal

Clicking "Add to cart" does NOT navigate. A modal appears reading "Added! Your
product has been added to cart." with two choices:

- **View Cart** — navigates to `/view_cart`
- **Continue Shopping** — dismisses the modal and stays put

The modal blocks the page underneath. A scenario that adds two products must
dismiss it between them, or the second click hits the overlay and fails with
"intercepts pointer events".

## The cart is per-account and per-session

An anonymous cart survives on the session; a logged-in cart belongs to the
account. Adding a product while logged out and then logging in carries the cart
over, which makes "add then log in" a legitimate scenario rather than a trap.

## Cart rows are a family

Each row shows product name, price, quantity and total, plus a delete control.
Row selectors match every row, so narrow to the product the test added rather
than assuming a row index. The cart is test-owned data, so asserting an exact
row count IS safe here — unlike the catalogue.

## Checkout requires an account

Proceeding to checkout while logged out shows a "Register / Login" prompt
rather than the address form. A checkout scenario must therefore either log in
first or register inside the flow.
