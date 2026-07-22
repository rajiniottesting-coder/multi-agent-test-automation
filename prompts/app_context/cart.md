# Module: Cart

_Injected for stories tagged with the "Cart" Jira Component._

## Behaviour
- `/cart.html` lists added items with name, description, price, quantity (always 1)
- Each line has a "Remove" button; removing updates the badge and the list
- "Continue Shopping" returns to inventory; "Checkout" starts the checkout flow
- Empty cart shows no line items and no cart badge

## Coverage hints
- Positive: items added on inventory appear correctly in the cart
- Negative: remove an item and verify it disappears and the badge decrements
- Edge: empty-cart state; proceeding to checkout with an empty cart