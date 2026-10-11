# Cart and checkout

## Which products to put in the cart

Use the names from `core.md`: `Blue Top`, `Men Tshirt`, `Sleeveless Dress`. A
cart scenario needs a NAMED product — "add a product to the cart" cannot be
asserted on, because the assertion has nothing to compare against.

Add a named product by opening its detail page first. On the listing the
add-to-cart control matches 68 elements and clicking it is rejected at
generation time; on the detail page it is unique. Adding two DIFFERENT products
means two different names, not the same one twice — quantity and distinct
line items are different behaviours and a scenario should not conflate them.


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

## A logged-out cart starts empty in every test

Every test runs in a fresh browser context (the `page` fixture in
`tests/conftest.py`), and an anonymous cart lives on the session. So a scenario
that never signs in starts with an empty cart on every run, with nothing to
clean up - the one way in this application to own the cart's starting state
without a clearing step.

Use it whenever a scenario depends on a quantity. As a logged-out shopper, add
3 of `Men Tshirt` and the cart shows `Men Tshirt` with quantity 3. Signed in as
the shared `registered` account, the same scenario can find a quantity left
behind by an earlier run.

Even so, phrase cart outcomes RELATIVELY - "the cart contains `Men Tshirt` with
quantity 3" - never "the cart contains only...", "exactly...", or "the cart is
empty". The inventory marks the cart persistent: code generation accepts an
exact quantity only in a scenario that never signs in, and the test-case check
rejects "only", "exactly", a row count and "empty" on the cart in every case.

## Cart rows are a family

Each row shows product name, price, quantity and total, plus a delete control.
Row selectors match every row, so narrow to the product the test added rather
than assuming a row index.


## "Register a fresh account" is not available here in one step

Registration is TWO forms. `start_signup(name, email)` submits the first and
lands on a second asking for password, address and contact details; the
account exists only after that second form is submitted. The method's own
docstring says so.

So a scenario cannot own its starting state by calling `start_signup()` and
then signing in - that signs in as the SHARED account, inheriting whatever a
previous run left. A step named "a newly registered account" that does this is
describing an intention, not a fact, and the cart assertion after it is a
coin toss.

One thing works here: assert RELATIVELY - that what this scenario added is
present, or is gone.

## The cart is test-owned, and test-owned is not the same as empty

Unlike the catalogue, the cart holds only what a test put there. What it does
NOT do is start at zero.

So a row count is NOT something a scenario may assert on. Two routes are
closed here, deliberately:

- this application cannot register a fresh account from generated code (see
  above), and
- generated code does NOT clear the cart. It is emptied by hand BEFORE a run,
  not by a step during one. `_starting_state.establishing_calls` is empty and
  that is the whole statement: no scenario should write a clearing Given, and
  none should assume another scenario left the cart in any particular state.

Assert MEMBERSHIP instead: the product this test added is present, or is gone.
That holds whatever the cart started with, and it is what the test case
usually means.

A test case whose expected result names an exact count or an empty cart cannot
be automated as written. Say so in `notes` and assert what this page can
honestly show.

Private is not the same as empty. The cart survives logout and survives the
run, so a scenario reusing the shared account inherits whatever a previous run
left behind — including a run that died between adding a product and removing
it. Assert an ABSOLUTE state ("the cart is empty", "the cart holds exactly one
row") only from an account this test registered itself; otherwise assert
relatively — that the product this test added is present, or is gone — which
is true whatever the cart started with.

## Checkout requires an account

Proceeding to checkout while logged out shows a "Register / Login" prompt
rather than the address form. A checkout scenario must therefore either log in
first or register inside the flow.