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

Two things work here:

- clear the cart in a Given, using the method the inventory names under
  `_starting_state.establishing_calls`
- assert relatively - that what this scenario added is present, or is gone

## The cart is test-owned, and test-owned is not the same as empty

Unlike the catalogue, the cart holds only what a test put there. What it does
NOT do is start at zero.

So a row count is NOT something a scenario may assert on by default. This
application cannot register a fresh account from generated code (see above),
which leaves exactly one way to earn an absolute assertion: clear the cart
first, in a Given, with `CartPage.empty_the_cart()` - the call named under
`_starting_state.establishing_calls`. Own the state and "exactly two rows" or
"the cart is empty" are honest.

Without that Given, assert MEMBERSHIP instead: the product this test added is
present, or is gone. A test case whose expected result names a count or an
empty cart, in a scenario that never clears it, cannot be automated as
written.

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